"""
NpsService — Sprint G.

Pesquisa pós-atendimento configurável por tenant:
  - Trigger APENAS após operation.completed (handler em workers/handlers/nps_handler.py)
  - Intervalo mínimo entre pesquisas ao mesmo cliente (min_interval_days)
  - Envio via CommunicationService (consent COMMUNICATION e quiet hours
    são verificados dentro do dispatch)
  - Nota baixa (score <= low_score_threshold) → nps.low_score_alert +
    notificação best-effort ao OWNER
  - Resposta pública sem auth: o survey_id (UUID) é o token do link
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infrastructure.db.models import (
    Appointment, Customer, NpsConfig, NpsResponse, NpsSurvey, User,
)
from app.infrastructure.event_bus import DomainEvent, event_bus

logger = logging.getLogger(__name__)

SURVEY_EXPIRY_HOURS = 48

# Status considerados "envio bem-sucedido" no dispatch:
# SCHEDULED = quiet hours, será drenado pelo drain_scheduled_communications.
_DISPATCH_OK = {"SENT", "SCHEDULED"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _publish(event_type: str, company_id: UUID, idempotency_key: str, payload: dict) -> None:
    """Publica evento best-effort — falha nunca derruba o fluxo."""
    try:
        event_bus.publish(DomainEvent(
            event_id=uuid.uuid4(),
            event_type=event_type,
            occurred_at=_now(),
            company_id=company_id,
            idempotency_key=idempotency_key,
            actor={"type": "SYSTEM", "id": None},
            payload=payload,
        ))
    except Exception:
        logger.exception("nps: falha ao publicar %s", event_type)


def get_or_create_config(db: Session, company_id: UUID) -> NpsConfig:
    config = db.query(NpsConfig).filter(NpsConfig.company_id == company_id).first()
    if config is None:
        config = NpsConfig(company_id=company_id)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def build_survey_url(survey_id: UUID) -> str:
    base = (settings.FRONTEND_BASE_URL or settings.FRONTEND_URL).rstrip("/")
    return f"{base}/nps/{survey_id}"


def schedule_nps_survey(
    db: Session, appointment_id: UUID, company_id: UUID, customer_id: UUID,
) -> NpsSurvey | None:
    """Chamado pelo handler de operation.completed. Retorna None quando skip."""
    config = db.query(NpsConfig).filter(NpsConfig.company_id == company_id).first()
    if config is not None and config.enabled is not True:
        return None
    if config is None:
        config = get_or_create_config(db, company_id)

    # Idempotência: 1 survey por appointment (UNIQUE no banco como defesa final)
    existing = (
        db.query(NpsSurvey)
        .filter(NpsSurvey.appointment_id == appointment_id)
        .first()
    )
    if existing is not None:
        return None

    # Intervalo mínimo por cliente
    cutoff = _now() - timedelta(days=config.min_interval_days)
    recent = (
        db.query(NpsSurvey)
        .filter(
            NpsSurvey.company_id == company_id,
            NpsSurvey.customer_id == customer_id,
            NpsSurvey.created_at >= cutoff,
        )
        .first()
    )
    if recent is not None:
        return None

    now = _now()
    scheduled_for = now + timedelta(minutes=config.delay_minutes)
    survey = NpsSurvey(
        company_id=company_id,
        customer_id=customer_id,
        appointment_id=appointment_id,
        status="PENDING",
        scheduled_for=scheduled_for,
        # expires_at definitivo é setado no envio (now + 48h);
        # antes do envio vale como guarda de PENDING órfão
        expires_at=scheduled_for + timedelta(hours=SURVEY_EXPIRY_HOURS),
    )
    db.add(survey)
    db.commit()
    db.refresh(survey)

    _publish(
        "nps.survey_scheduled", company_id,
        f"nps.survey_scheduled:{survey.id}",
        {
            "survey_id": str(survey.id),
            "appointment_id": str(appointment_id),
            "customer_id": str(customer_id),
            "company_id": str(company_id),
            "scheduled_for": scheduled_for.isoformat(),
        },
    )
    return survey


def send_pending_surveys(db: Session) -> int:
    """Worker: envia NpsSurveys PENDING com scheduled_for <= now()."""
    from app.modules.communication.service import communication_service

    now = _now()
    pending = (
        db.query(NpsSurvey)
        .filter(NpsSurvey.status == "PENDING", NpsSurvey.scheduled_for <= now)
        .limit(500)
        .all()
    )

    sent = 0
    for survey in pending:
        customer = (
            db.query(Customer).filter(Customer.id == survey.customer_id).first()
        )
        if customer is None:
            survey.status = "EXPIRED"
            continue

        context = {
            "cliente_nome": customer.name,
            "nps_url": build_survey_url(survey.id),
            "recipient_phone": customer.phone,
            "recipient_email": getattr(customer, "email", None) or "",
        }
        try:
            log = communication_service.dispatch(
                event_type="nps.survey_request",
                company_id=survey.company_id,
                context=context,
                recipient_id=survey.customer_id,
                recipient_type="CLIENT",
                db=db,
            )
        except Exception:
            logger.exception("nps: dispatch falhou survey_id=%s", survey.id)
            continue

        if log is not None and log.status in _DISPATCH_OK:
            survey.status = "SENT"
            survey.sent_at = _now()
            survey.expires_at = survey.sent_at + timedelta(hours=SURVEY_EXPIRY_HOURS)
            survey.communication_log_id = getattr(log, "log_id", None) or getattr(log, "id", None)
            sent += 1
        elif log is not None and log.status == "SKIPPED_CONSENT_REVOKED":
            # Consent revogado → não insiste; encerra a pesquisa
            survey.status = "EXPIRED"
        # Demais SKIPPED_*/FAILED: permanece PENDING — retry no próximo scan

    db.commit()
    return sent


def expire_surveys(db: Session) -> int:
    """Worker: SENT com expires_at < now() → EXPIRED."""
    now = _now()
    stale = (
        db.query(NpsSurvey)
        .filter(NpsSurvey.status == "SENT", NpsSurvey.expires_at < now)
        .all()
    )
    for survey in stale:
        survey.status = "EXPIRED"
        _publish(
            "nps.survey_expired", survey.company_id,
            f"nps.survey_expired:{survey.id}",
            {"survey_id": str(survey.id), "company_id": str(survey.company_id)},
        )
    db.commit()
    return len(stale)


def record_response(
    db: Session, survey_id: UUID, score: int, comment: str | None = None,
) -> NpsResponse:
    """Endpoint público (sem auth — survey_id é o token do link)."""
    survey = db.query(NpsSurvey).filter(NpsSurvey.id == survey_id).first()
    if survey is None:
        raise HTTPException(status_code=404, detail="Pesquisa não encontrada")
    if survey.status != "SENT":
        raise HTTPException(
            status_code=422,
            detail="Pesquisa não está disponível para resposta",
        )
    if not (0 <= score <= 10):
        raise HTTPException(status_code=422, detail="score deve estar entre 0 e 10")

    now = _now()
    response = NpsResponse(
        survey_id=survey.id,
        company_id=survey.company_id,
        score=score,
        comment=comment,
        responded_at=now,
    )
    db.add(response)
    survey.status = "RESPONDED"
    survey.responded_at = now
    db.commit()
    db.refresh(response)

    _publish(
        "nps.response_received", survey.company_id,
        f"nps.response_received:{survey.id}",
        {
            "survey_id": str(survey.id),
            "response_id": str(response.id),
            "customer_id": str(survey.customer_id),
            "company_id": str(survey.company_id),
            "score": score,
        },
    )

    config = db.query(NpsConfig).filter(NpsConfig.company_id == survey.company_id).first()
    threshold = config.low_score_threshold if config else 6
    alert_enabled = config.low_score_alert_enabled is not False if config else True
    if score <= threshold and alert_enabled:
        _publish(
            "nps.low_score_alert", survey.company_id,
            f"nps.low_score_alert:{survey.id}",
            {
                "survey_id": str(survey.id),
                "customer_id": str(survey.customer_id),
                "company_id": str(survey.company_id),
                "score": score,
                "comment": comment,
            },
        )
        _notify_owner_low_score(db, survey, score, comment)

    return response


def _notify_owner_low_score(
    db: Session, survey: NpsSurvey, score: int, comment: str | None,
) -> None:
    """Notificação best-effort ao OWNER do tenant — nunca derruba a resposta."""
    try:
        from app.modules.communication.service import communication_service

        owner = (
            db.query(User)
            .filter(
                User.company_id == survey.company_id,
                User.role == "OWNER",
                User.active == True,  # noqa: E712
            )
            .first()
        )
        if owner is None:
            return
        customer = (
            db.query(Customer).filter(Customer.id == survey.customer_id).first()
        )
        communication_service.dispatch(
            event_type="nps.low_score_alert",
            company_id=survey.company_id,
            context={
                "cliente_nome": customer.name if customer else "cliente",
                "nota": str(score),
                "comentario": comment or "(sem comentário)",
                "recipient_email": getattr(owner, "email", None) or "",
            },
            recipient_id=owner.id,
            recipient_type="OWNER",
            db=db,
        )
    except Exception:
        logger.exception("nps: falha na notificação de nota baixa survey_id=%s", survey.id)


def add_tenant_response(
    db: Session, survey_id: UUID, response_text: str, actor_id: UUID, company_id: UUID,
) -> NpsResponse:
    """OWNER/ADMIN responde ao feedback do cliente — só adiciona, nunca edita score."""
    survey = (
        db.query(NpsSurvey)
        .filter(NpsSurvey.id == survey_id, NpsSurvey.company_id == company_id)
        .first()
    )
    if survey is None:
        raise HTTPException(status_code=404, detail="Pesquisa não encontrada")

    response = (
        db.query(NpsResponse).filter(NpsResponse.survey_id == survey.id).first()
    )
    if response is None:
        raise HTTPException(status_code=422, detail="Pesquisa ainda não foi respondida pelo cliente")

    response.tenant_response = response_text
    db.commit()
    db.refresh(response)
    return response
