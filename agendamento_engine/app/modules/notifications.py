"""
Notificações transacionais de agendamento.

Responsabilidades (S2.1):
  - ENFILEIRAR a confirmação de agendamento/reagendamento ao cliente para o
    worker Celery (send_appointment_communication). O envio em si sai do request.

Contrato:
  - send_booking_confirmation/send_reschedule_confirmation apenas ENFILEIRAM.
    O envio real — 3-5 queries + httpx Evolution (timeout 15s) ou SMTP (10s) —
    roda no worker, FORA do request HTTP. Antes do S2.1 era "fire-and-forget"
    só no sentido de "erro não propaga": o TEMPO era integral no request. Agora
    o tempo também sai; a resiliência de envio (retry + dead-letter) é da task.
  - O enfileiramento é best-effort: broker indisponível é logado, nunca propaga
    (o fluxo de negócio não deve ser interrompido por falha de notificação).
  - As funções recebem db + Appointment já commitado — assinatura preservada
    para os callers (appointments/service.py) e para os patches de teste; o
    worker re-hidrata por ID (payload da task é 100% escalar).
  - Os helpers de renderização (_get_company_tz, _fmt_datetime,
    _use_communication_service) são reutilizados pela task — fonte única de
    formatação/kill-switch, sem divergência de contrato.

Sprint I:
  Feature flag TenantConfig.permission_overrides["use_communication_service"]
  funciona como kill-switch: default True (ausente = habilitado).
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.infrastructure.db.models import Appointment
from app.infrastructure.db.models.company_settings import CompanySettings

logger = logging.getLogger(__name__)


def _use_communication_service(db: Session, company_id) -> bool:
    """Kill-switch do CommunicationService. Flag ausente → True (default Sprint I)."""
    try:
        from app.infrastructure.db.models.tenant_config import TenantConfig
        config = db.query(TenantConfig).filter(TenantConfig.company_id == company_id).first()
        overrides = (config.permission_overrides or {}) if config else {}
        return bool(overrides.get("use_communication_service", True))
    except Exception:
        return True

_DEFAULT_TZ = "America/Sao_Paulo"

MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _get_company_tz(db: Session, company_id) -> ZoneInfo:
    try:
        row = (
            db.query(CompanySettings.timezone)
            .filter(CompanySettings.company_id == company_id)
            .first()
        )
        tz_name = (row.timezone if row and row.timezone else _DEFAULT_TZ)
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo(_DEFAULT_TZ)


def _localize(dt: datetime, tz: ZoneInfo) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def _fmt_datetime(dt: datetime, tz: ZoneInfo) -> tuple[str, str]:
    """Retorna (data_legivel, hora) no fuso da empresa. Ex: ('5 de maio', '14:30')"""
    local = _localize(dt, tz)
    data  = f"{local.day} de {MONTHS_PT[local.month - 1]}"
    hora  = f"{local.hour:02d}:{local.minute:02d}"
    return data, hora


def send_booking_confirmation(
    db: Session, appointment: Appointment, manage_token: str | None = None
) -> None:
    """Enfileira a confirmação de agendamento ao cliente (S2.1).

    `db` é mantido na assinatura por compatibilidade com os callers e patches
    de teste; o envio roda no worker, que abre a própria sessão.
    """
    _enqueue_appointment_communication(
        appointment, "appointment.confirmed", manage_token, "send_booking_confirmation",
    )


def send_reschedule_confirmation(
    db: Session, appointment: Appointment, manage_token: str | None = None
) -> None:
    """Enfileira a confirmação de reagendamento ao cliente (S2.1)."""
    _enqueue_appointment_communication(
        appointment, "appointment.confirmed", manage_token, "send_reschedule_confirmation",
    )


def _enqueue_appointment_communication(
    appointment: Appointment,
    event_type: str,
    manage_token: str | None,
    caller: str,
) -> None:
    """Enfileira send_appointment_communication no worker Celery.

    importlib.import_module permite que testes substituam o módulo/task via
    patch de sys.modules (mesmo idioma de reservation_service). O payload é
    100% escalar: IDs + o token CRU (o banco guarda só o hash, irreversível,
    então o token precisa viajar aqui). Broker indisponível é logado e engolido
    — o enfileiramento é best-effort; a resiliência de envio é da própria task.
    """
    try:
        import importlib
        _mod = importlib.import_module("app.workers.communication_worker")
        # retry=False: broker fora do ar falha rápido (não bloqueia o request em
        # retries de publish — o oposto do que este sprint quer). Best-effort.
        _mod.send_appointment_communication.apply_async(
            args=[
                event_type,
                str(appointment.id),
                str(appointment.company_id),
                manage_token,
            ],
            retry=False,
        )
        logger.info("%s: enfileirado appt_id=%s", caller, appointment.id)
    except Exception:
        logger.exception(
            "%s: falha ao enfileirar appt_id=%s",
            caller, getattr(appointment, "id", None),
        )
