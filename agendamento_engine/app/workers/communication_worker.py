"""
Celery tasks para fluxos críticos de comunicação — Sprint 5.

Todos os 4 fluxos de appointment são críticos: Celery task direta (não EventBus).
  appointment.confirmed  — transacional, bypass quiet_hours
  appointment.cancelled  — transacional, bypass quiet_hours
  appointment.reminder_due — automático, respeita quiet_hours
  appointment.no_show      — automático, respeita quiet_hours

O evento publicado para lembretes é único (reminder_due); o handler deriva
o nome do template (reminder_24h ou reminder_2h) via payload["interval"].

Sprint I: chamadas diretas ao evolution_client foram removidas — todo envio
passa pelo CommunicationService. A flag
TenantConfig.permission_overrides["use_communication_service"] é kill-switch
(ausente → True).
"""
import logging
from uuid import UUID

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal
from app.core.celery_db_context import celery_db_session

logger = logging.getLogger(__name__)

_DEAD_LETTER_PREFIX = "dead_letter"


def _push_dead_letter(task_name: str, task_id: str, retries: int, exc: Exception) -> None:
    try:
        import redis as redis_client
        from app.core.config import settings
        r = redis_client.from_url(settings.REDIS_URL)
        r.rpush(
            f"{_DEAD_LETTER_PREFIX}:{task_name}",
            f"task_id={task_id} retries={retries} error={exc!r}",
        )
        logger.error(
            "communication_worker: dead-letter task=%s task_id=%s retries=%d",
            task_name, task_id, retries,
        )
    except Exception:
        logger.exception("communication_worker: falha ao gravar dead-letter task=%s", task_name)


@celery_app.task(
    bind=True,
    name="app.workers.communication_worker.send_appointment_communication",
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,
    retry_jitter=True,
)
def send_appointment_communication(
    self,
    event_type: str,
    appointment_id: str,
    company_id: str,
    manage_token: str | None = None,
    interval: str | None = None,
):
    """
    Envia comunicação de um evento de agendamento via CommunicationService.

    Enfileirada por notifications.send_booking_confirmation/reschedule (S2.1) —
    tira o envio (3-5 queries + httpx Evolution 15s / SMTP 10s) do request HTTP.
    Executa salvo opt-out: permission_overrides["use_communication_service"]=False.

    O contexto (data por extenso + manage_url) reutiliza os helpers de
    renderização de notifications.py, mantendo paridade com o caminho síncrono
    antigo — o payload da task é 100% escalar (IDs + token), re-hidratado aqui.

    Só appointment.confirmed é enfileirado hoje; reminder_due/no_show ficam
    dormantes (lembretes vêm do reminder_worker; no-show é sprint próprio).
    """
    try:
        with celery_db_session(company_id) as db:
            from app.infrastructure.db.models import Appointment, Customer
            from app.modules import notifications
            from app.modules.appointments.manage_tokens import build_manage_url

            company_uuid = UUID(company_id)
            appt_uuid = UUID(appointment_id)

            # Kill-switch (mesmo helper do caminho vivo): ausente → True.
            if not notifications._use_communication_service(db, company_uuid):
                logger.debug(
                    "communication_worker: flag use_communication_service desligado company=%s",
                    company_id,
                )
                return

            appt = db.query(Appointment).filter(
                Appointment.id == appt_uuid,
                Appointment.company_id == company_uuid,
            ).first()
            if not appt:
                logger.warning("communication_worker: appointment não encontrado id=%s", appointment_id)
                return

            customer = db.query(Customer).filter(Customer.id == appt.client_id).first()
            if not customer or not customer.phone:
                logger.debug("communication_worker: cliente sem phone appt_id=%s", appointment_id)
                return

            # Deriva event_type para template de lembrete (dormante)
            template_event = event_type
            if event_type == "appointment.reminder_due" and interval:
                template_event = f"appointment.reminder_{interval}"

            prof_name = appt.professional.name if appt.professional else "profissional"
            svc_name = appt.services[0].service_name if appt.services else "serviço"

            # Renderização idêntica ao caminho vivo (data por extenso + manage_url).
            tz = notifications._get_company_tz(db, company_uuid)
            data, hora = notifications._fmt_datetime(appt.start_at, tz)
            manage_url = build_manage_url(manage_token) if manage_token else ""

            context = {
                "cliente_nome": customer.name,
                "horario": hora,
                "data": data,
                "servico": svc_name,
                "profissional": prof_name,
                "empresa_nome": "",
                "manage_url": manage_url,
                "recipient_phone": customer.phone,
            }

            from app.modules.communication.service import communication_service
            communication_service.dispatch(
                event_type=template_event,
                company_id=company_uuid,
                context=context,
                recipient_id=customer.id,
                recipient_type="CLIENT",
                db=db,
            )

            # Para no_show: notificar PROFESSIONAL também (dormante)
            if event_type == "appointment.no_show" and appt.professional:
                communication_service.dispatch(
                    event_type=template_event,
                    company_id=company_uuid,
                    context=context,
                    recipient_id=getattr(appt.professional, "user_id", None) or appt.professional.id,
                    recipient_type="PROFESSIONAL",
                    db=db,
                )
    except Exception as exc:
        logger.exception(
            "communication_worker: erro event=%s appt=%s attempt=%d",
            event_type, appointment_id, self.request.retries,
        )
        if self.request.retries >= self.max_retries:
            _push_dead_letter(
                "send_appointment_communication",
                str(self.request.id),
                self.request.retries,
                exc,
            )
        raise


@celery_app.task(
    bind=True,
    name="app.workers.communication_worker.drain_scheduled_communications",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def drain_scheduled_communications(self):
    """Task Celery Beat: processa communication_logs SCHEDULED com scheduled_send_at <= now()."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # worker de plataforma — bypass RLS
        from app.modules.communication.service import communication_service
        sent = communication_service.drain_scheduled(db)
        logger.info("drain_scheduled_communications: %d mensagens enviadas", sent)
    except Exception as exc:
        db.rollback()
        logger.exception("drain_scheduled_communications: erro attempt=%d", self.request.retries)
        if self.request.retries >= self.max_retries:
            _push_dead_letter(
                "drain_scheduled_communications",
                str(self.request.id),
                self.request.retries,
                exc,
            )
        raise
    finally:
        db.close()
