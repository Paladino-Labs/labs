"""
CommunicationService — Sprint 5 (EMAIL adicionado no Sprint 11).

Responsabilidades:
  - dispatch(): enviar mensagem para um destinatário via canal configurado.
  - drain_scheduled(): processar logs SCHEDULED cujo scheduled_send_at já passou.

Seleção de canal em dispatch():
  Tenta EMAIL primeiro se email_enabled=True e existe template EMAIL para o evento.
  Faz fallback para WHATSAPP se whatsapp_enabled=True e existe template WHATSAPP.

Distinção de quiet_hours por tipo de evento:
  Transacionais (appointment.confirmed, appointment.cancelled):
    bypass quiet_hours — cliente acabou de agir; atrasar até 8h é experiência ruim.
  Automáticos (appointment.reminder_*, appointment.no_show):
    respeitam quiet_hours — lembrete → SCHEDULED; no_show → SCHEDULED (não descartado).
"""
import logging
import re
import smtplib
from datetime import datetime, time, timezone
from email.mime.text import MIMEText
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
          1. Busca CommunicationSettings — algum canal habilitado?
          2. Verifica quiet_hours (com distinção transacional vs automático).
          3. Seleciona canal: EMAIL se email_enabled + template EMAIL existe;
             fallback para WHATSAPP se whatsapp_enabled + template WHATSAPP existe.
          4. ConsentRecord: Sprint 20. Skip gracioso por ora.
          5. Renderiza template.
          6. Envia via canal selecionado.
          7. Grava log com status SENT ou FAILED.
        """
        def _log(status: str, channel: str = "WHATSAPP", **kwargs) -> CommunicationLog:
            entry = CommunicationLog(
                company_id=company_id,
                event_type=event_type,
                channel=channel,
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

        # Uso de `is True` para ser seguro com mocks nos testes (MagicMock não é True).
        email_enabled = comm_settings is not None and comm_settings.email_enabled is True
        whatsapp_enabled = comm_settings is not None and comm_settings.whatsapp_enabled is True

        if not email_enabled and not whatsapp_enabled:
            return _log("SKIPPED_CHANNEL_DISABLED", channel="WHATSAPP")

        # Canal preferido para logs de early-exit (antes de encontrar template).
        default_channel = "EMAIL" if email_enabled else "WHATSAPP"

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
                    return _log(
                        "SCHEDULED",
                        channel=default_channel,
                        scheduled_send_at=scheduled_send_at,
                    )
                else:
                    return _log("SKIPPED_QUIET_HOURS", channel=default_channel)

        # 3. Seleciona canal e busca template
        channel_preference = []
        if email_enabled:
            channel_preference.append("EMAIL")
        if whatsapp_enabled:
            channel_preference.append("WHATSAPP")

        template = None
        channel = None
        for candidate in channel_preference:
            tpl = (
                db.query(CommunicationTemplate)
                .filter(
                    CommunicationTemplate.company_id == company_id,
                    CommunicationTemplate.event_type == event_type,
                    CommunicationTemplate.channel == candidate,
                    CommunicationTemplate.audience == recipient_type,
                    CommunicationTemplate.is_active == True,
                )
                .first()
            )
            if tpl:
                channel = candidate
                template = tpl
                break

        if not template:
            return _log("SKIPPED_NO_TEMPLATE", channel=channel_preference[0])

        # 4. Consent: Sprint 20 — skip gracioso

        # 5. Renderiza
        rendered = _render_template(template.body_template, context)

        # 6. Envia
        try:
            if channel == "EMAIL":
                self._send_email(comm_settings, context, rendered, db)
            else:
                self._send_whatsapp(comm_settings, context, rendered, db)
        except Exception as exc:
            logger.exception(
                "CommunicationService.dispatch: falha ao enviar event=%s recipient=%s",
                event_type, recipient_id,
            )
            return _log(
                "FAILED",
                channel=channel,
                template_id=template.template_id,
                rendered_body=rendered,
                error_message=str(exc),
            )

        # 7. Log SENT
        return _log(
            "SENT",
            channel=channel,
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

    def _send_email(
        self,
        comm_settings: CommunicationSetting,
        context: dict,
        rendered_body: str,
        db: Session,
    ) -> None:
        """Envia email via Mailtrap HTTP API (preferencial) ou SMTP (fallback).

        Prioridade:
          1. MAILTRAP_API_TOKEN configurado → HTTP API (funciona em Railway e outros
             ambientes que bloqueiam conexões SMTP de saída).
          2. IntegrationCredential provider=SMTP do tenant.
          3. SMTP_* de settings (fallback global).
        """
        from app.core.config import settings as app_settings

        recipient_email = context.get("recipient_email")
        if not recipient_email:
            raise ValueError("recipient_email ausente no context de dispatch")

        subject = context.get("email_subject", "Mensagem Paladino")
        from_email = app_settings.SMTP_FROM_EMAIL or "noreply@paladino.app"

        # ── Caminho 1: Mailtrap HTTP API ──────────────────────────────────────
        if app_settings.MAILTRAP_API_TOKEN:
            import requests

            if app_settings.MAILTRAP_SANDBOX_INBOX_ID:
                url = f"https://sandbox.api.mailtrap.io/api/send/{app_settings.MAILTRAP_SANDBOX_INBOX_ID}"
            else:
                url = "https://send.api.mailtrap.io/api/send"

            payload = {
                "from": {"email": from_email, "name": "Paladino"},
                "to": [{"email": recipient_email}],
                "subject": subject,
                "text": rendered_body,
            }
            resp = requests.post(
                url,
                json=payload,
                headers={"Api-Token": app_settings.MAILTRAP_API_TOKEN},
                timeout=10,
            )
            if not resp.ok:
                raise RuntimeError(
                    f"Mailtrap HTTP API erro {resp.status_code}: {resp.text}"
                )
            return

        # ── Caminho 2 e 3: SMTP ───────────────────────────────────────────────
        from app.infrastructure.db.models.integration_credential import IntegrationCredential

        smtp_cred = None
        if getattr(comm_settings, "smtp_credential_id", None):
            smtp_cred = (
                db.query(IntegrationCredential)
                .filter(
                    IntegrationCredential.credential_id == comm_settings.smtp_credential_id,
                    IntegrationCredential.provider == "SMTP",
                    IntegrationCredential.status == "ACTIVE",
                )
                .first()
            )

        if smtp_cred:
            from app.core.encryption import decrypt_secret
            cfg = smtp_cred.config or {}
            host = cfg.get("host") or app_settings.SMTP_HOST
            port = int(cfg.get("port") or app_settings.SMTP_PORT)
            from_email = cfg.get("from_email") or from_email
            use_tls = cfg.get("use_tls", app_settings.SMTP_USE_TLS)
            smtp_user = cfg.get("user") or from_email
            smtp_password = decrypt_secret(smtp_cred.secret_encrypted)
        else:
            host = app_settings.SMTP_HOST
            port = app_settings.SMTP_PORT
            use_tls = app_settings.SMTP_USE_TLS
            smtp_user = app_settings.SMTP_USER
            smtp_password = app_settings.SMTP_PASSWORD

        if not host:
            raise RuntimeError("SMTP não configurado: SMTP_HOST ausente e MAILTRAP_API_TOKEN vazio")

        msg = MIMEText(rendered_body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = recipient_email

        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [recipient_email], msg.as_string())

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
