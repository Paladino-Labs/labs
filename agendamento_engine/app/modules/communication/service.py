"""
CommunicationService — Sprint 5.

Responsabilidades:
  - dispatch(): enviar mensagem para um destinatário via canal configurado.
  - drain_scheduled(): processar logs SCHEDULED cujo scheduled_send_at já passou.

Distinção de quiet_hours por tipo de evento:
  Transacionais (appointment.confirmed, appointment.cancelled):
    bypass quiet_hours — cliente acabou de agir; atrasar até 8h é experiência ruim.
  Automáticos (appointment.reminder_*, appointment.no_show):
    respeitam quiet_hours — lembrete → SCHEDULED; no_show → SCHEDULED (não descartado).
"""
import logging
import re
from datetime import datetime, time, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models.communication_setting import CommunicationSetting
from app.infrastructure.db.models.communication_template import CommunicationTemplate
from app.infrastructure.db.models.communication_log import CommunicationLog

logger = logging.getLogger(__name__)

# Eventos automáticos que respeitam quiet_hours (→ SCHEDULED em vez de SKIPPED).
_QUIET_HOURS_SCHEDULED_EVENTS = {
    "appointment.reminder_24h",
    "appointment.reminder_2h",
    "appointment.reminder_due",
    "appointment.no_show",
}

# Eventos transacionais: bypass completo de quiet_hours.
_TRANSACTIONAL_EVENTS = {
    "appointment.confirmed",
    "appointment.cancelled",
}


def _in_quiet_hours(now_time: time, start: time, end: time) -> bool:
    """Retorna True se now_time está dentro do período [start, end) cruzando meia-noite."""
    if start <= end:
        return start <= now_time < end
    # Cruza meia-noite: ex. 22:00 → 08:00
    return now_time >= start or now_time < end


def _render_template(template: str, context: dict) -> str:
    """Substitui {{variavel}} pelo valor em context. Variáveis ausentes ficam no texto."""
    def replacer(match):
        key = match.group(1).strip()
        return str(context.get(key, match.group(0)))

    return re.sub(r"\{\{(.*?)\}\}", replacer, template)


def _next_quiet_hours_end(now_utc: datetime, end_time: time) -> datetime:
    """Calcula o próximo horário em que quiet_hours termina (mesmo dia ou dia seguinte)."""
    candidate = now_utc.replace(
        hour=end_time.hour,
        minute=end_time.minute,
        second=0,
        microsecond=0,
    )
    if candidate <= now_utc:
        from datetime import timedelta
        candidate += timedelta(days=1)
    return candidate


class CommunicationService:
    def dispatch(
        self,
        event_type: str,
        company_id: UUID,
        context: dict,
        recipient_id: UUID,
        recipient_type: str,
        db: Session,
    ) -> CommunicationLog:
        """
        Enviar mensagem para um destinatário.

        Passos:
          1. Busca CommunicationSettings — canal habilitado?
          2. Verifica quiet_hours (com distinção transacional vs automático).
          3. Busca template ativo para (event_type, channel, audience).
          4. ConsentRecord: Sprint 20. Skip gracioso por ora.
          5. Renderiza template.
          6. Envia via canal.
          7. Grava log com status SENT ou FAILED.
        """
        def _log(status: str, **kwargs) -> CommunicationLog:
            entry = CommunicationLog(
                company_id=company_id,
                event_type=event_type,
                channel="WHATSAPP",
                recipient_id=recipient_id,
                recipient_type=recipient_type,
                status=status,
                **kwargs,
            )
            db.add(entry)
            db.commit()
            return entry

        # 1. Busca settings
        comm_settings = (
            db.query(CommunicationSetting)
            .filter(CommunicationSetting.company_id == company_id)
            .first()
        )
        if not comm_settings or not comm_settings.whatsapp_enabled:
            return _log("SKIPPED_CHANNEL_DISABLED")

        channel = "WHATSAPP"

        # 2. Quiet hours — apenas para eventos automáticos
        is_transactional = event_type in _TRANSACTIONAL_EVENTS
        if not is_transactional and comm_settings.quiet_hours_enabled:
            now_utc = datetime.now(timezone.utc)
            now_time = now_utc.time()
            qs = comm_settings.quiet_hours_start
            qe = comm_settings.quiet_hours_end

            if _in_quiet_hours(now_time, qs, qe):
                if event_type in _QUIET_HOURS_SCHEDULED_EVENTS:
                    scheduled_send_at = _next_quiet_hours_end(now_utc, qe)
                    return _log("SCHEDULED", scheduled_send_at=scheduled_send_at)
                else:
                    return _log("SKIPPED_QUIET_HOURS")

        # 3. Busca template
        template = (
            db.query(CommunicationTemplate)
            .filter(
                CommunicationTemplate.company_id == company_id,
                CommunicationTemplate.event_type == event_type,
                CommunicationTemplate.channel == channel,
                CommunicationTemplate.audience == recipient_type,
                CommunicationTemplate.is_active == True,
            )
            .first()
        )
        if not template:
            return _log("SKIPPED_NO_TEMPLATE")

        # 4. Consent: Sprint 20 — skip gracioso

        # 5. Renderiza
        rendered = _render_template(template.body_template, context)

        # 6. Envia
        try:
            self._send_whatsapp(comm_settings, context, rendered, db)
        except Exception as exc:
            logger.exception(
                "CommunicationService.dispatch: falha ao enviar event=%s recipient=%s",
                event_type, recipient_id,
            )
            return _log(
                "FAILED",
                template_id=template.template_id,
                rendered_body=rendered,
                error_message=str(exc),
            )

        # 7. Log SENT
        return _log(
            "SENT",
            template_id=template.template_id,
            rendered_body=rendered,
            sent_at=datetime.now(timezone.utc),
        )

    def _send_whatsapp(
        self,
        comm_settings: CommunicationSetting,
        context: dict,
        rendered_body: str,
        db: Session,
    ) -> None:
        """Envia via Evolution API usando o instance_name da credencial ou connection."""
        from app.modules.whatsapp import evolution_client
        from app.infrastructure.db.models.whatsapp_connection import WhatsAppConnection

        phone = context.get("recipient_phone")
        if not phone:
            raise ValueError("recipient_phone ausente no context de dispatch")

        # Resolve instance_name: via WhatsAppConnection (padrão Estágio 0 — Opção A)
        conn = (
            db.query(WhatsAppConnection)
            .filter(
                WhatsAppConnection.company_id == comm_settings.company_id,
                WhatsAppConnection.status == "CONNECTED",
            )
            .first()
        )
        if not conn:
            raise RuntimeError(
                f"Empresa {comm_settings.company_id} sem WhatsApp conectado"
            )

        evolution_client.send_text(conn.instance_name, phone, rendered_body)

    def drain_scheduled(self, db: Session) -> int:
        """
        Processa communication_logs com status=SCHEDULED e scheduled_send_at <= now().
        Chamado pelo Celery Beat a cada 5 min.
        Retorna quantidade de mensagens enviadas.
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        pending = (
            db.query(CommunicationLog)
            .filter(
                CommunicationLog.status == "SCHEDULED",
                CommunicationLog.scheduled_send_at <= now,
            )
            .all()
        )

        sent_count = 0
        for log_entry in pending:
            try:
                comm_settings = (
                    db.query(CommunicationSetting)
                    .filter(CommunicationSetting.company_id == log_entry.company_id)
                    .first()
                )
                if not comm_settings or not comm_settings.whatsapp_enabled:
                    log_entry.status = "SKIPPED_CHANNEL_DISABLED"
                    db.commit()
                    continue

                if log_entry.rendered_body:
                    from app.infrastructure.db.models.whatsapp_connection import WhatsAppConnection
                    from app.modules.whatsapp import evolution_client

                    conn = (
                        db.query(WhatsAppConnection)
                        .filter(
                            WhatsAppConnection.company_id == log_entry.company_id,
                            WhatsAppConnection.status == "CONNECTED",
                        )
                        .first()
                    )
                    if conn and log_entry.rendered_body:
                        # recipient_id deve ser um customer — buscar phone
                        from app.infrastructure.db.models import Customer
                        customer = db.query(Customer).filter(
                            Customer.id == log_entry.recipient_id,
                        ).first()
                        if customer and customer.phone:
                            evolution_client.send_text(
                                conn.instance_name, customer.phone, log_entry.rendered_body
                            )
                            log_entry.status = "SENT"
                            log_entry.sent_at = datetime.now(timezone.utc)
                            db.commit()
                            sent_count += 1
                            continue

                log_entry.status = "FAILED"
                log_entry.error_message = "drain: dados insuficientes para reenvio"
                db.commit()

            except Exception as exc:
                db.rollback()
                logger.exception(
                    "drain_scheduled: falha ao processar log_id=%s", log_entry.log_id
                )
                try:
                    log_entry.status = "FAILED"
                    log_entry.error_message = str(exc)
                    db.commit()
                except Exception:
                    db.rollback()

        return sent_count


communication_service = CommunicationService()
