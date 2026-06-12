"""
Gestão de agendamento via token único — sem login (Sprint B).

O cliente acessa /manage/{token} com o token cru recebido no WhatsApp.
Lookup é feito pelo SHA-256 do token (appointments.manage_token_hash);
o appointment carrega o company_id, então o isolamento de tenant é
implícito — não existe forma de usar um token contra outro tenant.

Contrato de segurança:
  - Token inválido, expirado ou de agendamento em estado terminal
    → SEMPRE 404 genérico (nunca 401/403 — não revelar existência).
  - Janela decide CONSEQUÊNCIA, não permissão: cancelar fora da janela
    é permitido, com retenção de sinal conforme DepositPolicy.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Appointment
from app.infrastructure.db.models.deposit_policy import DepositPolicy
from app.infrastructure.db.models.payment import Payment
from app.modules.appointments import service as appointment_svc
from app.modules.appointments.manage_tokens import hash_token
from app.modules.appointments.schemas import RescheduleRequest

logger = logging.getLogger(__name__)

_NOT_FOUND = HTTPException(status_code=404, detail="Link inválido ou expirado")


def resolve_appointment(db: Session, raw_token: str) -> Appointment:
    """
    Resolve o token cru para o Appointment. Qualquer falha → 404 genérico.
    """
    appointment = (
        db.query(Appointment)
        .filter(Appointment.manage_token_hash == hash_token(raw_token))
        .first()
    )
    if not appointment:
        raise _NOT_FOUND

    expires_at = appointment.manage_token_expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            raise _NOT_FOUND

    # Defesa em profundidade — estados terminais já têm o token invalidado
    if appointment.status in ("COMPLETED", "CANCELLED", "NO_SHOW"):
        raise _NOT_FOUND

    return appointment


def get_details(db: Session, raw_token: str) -> dict:
    """Detalhes do agendamento sem PII além do necessário."""
    appointment = resolve_appointment(db, raw_token)
    can_act = appointment.status == "SCHEDULED"
    return {
        "service_name": (
            appointment.services[0].service_name if appointment.services else None
        ),
        "professional_name": (
            appointment.professional.name if appointment.professional else None
        ),
        "scheduled_datetime": appointment.start_at,
        "status": appointment.status,
        "can_cancel": can_act,
        "can_reschedule": can_act,
    }


def _deposit_retained(db: Session, appointment: Appointment) -> bool:
    """
    Consequência da janela de cancelamento (DepositPolicy):
      - sem política ou sem sinal pago → nada a reter (False)
      - dentro da janela (antecedência >= refundable_until_hours_before) → False
      - fora da janela → sinal retido (True)
    """
    service_id = (
        appointment.services[0].service_id if appointment.services else None
    )
    policy = None
    if service_id is not None:
        policy = (
            db.query(DepositPolicy)
            .filter(
                DepositPolicy.company_id == appointment.company_id,
                DepositPolicy.service_id == service_id,
            )
            .first()
        )
    if policy is None:
        policy = (
            db.query(DepositPolicy)
            .filter(
                DepositPolicy.company_id == appointment.company_id,
                DepositPolicy.service_id.is_(None),
            )
            .first()
        )
    if policy is None:
        return False

    deposit_paid = (
        db.query(Payment)
        .filter(
            Payment.company_id == appointment.company_id,
            Payment.appointment_id == appointment.id,
            Payment.status == "CONFIRMED",
        )
        .first()
    )
    if deposit_paid is None:
        return False

    start_at = appointment.start_at
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)
    within_window = (start_at - datetime.now(timezone.utc)) >= timedelta(
        hours=policy.refundable_until_hours_before
    )
    return not within_window


def cancel(db: Session, raw_token: str, reason: str | None = None) -> dict:
    """
    Cancela via link — actor CLIENT, transição normal da FSM.
    A janela NUNCA bloqueia (skip_policy=True); fora dela o sinal é retido.
    O token é invalidado pela própria transição para CANCELLED (terminal).
    """
    appointment = resolve_appointment(db, raw_token)

    retained = _deposit_retained(db, appointment)

    note = "Cancelado pelo cliente via link de gestão (actor=CLIENT)"
    if reason:
        note = f"{note}: {reason}"

    appointment_svc.cancel_appointment(
        db, appointment.company_id, appointment.id,
        user_id=None, reason=note, skip_policy=True,
    )

    if retained:
        message = (
            "Agendamento cancelado. Como o cancelamento foi fora do prazo, "
            "o sinal pago foi retido conforme a política do estabelecimento."
        )
    else:
        message = "Agendamento cancelado com sucesso."

    return {"status": "CANCELLED", "deposit_retained": retained, "message": message}


def reschedule(db: Session, raw_token: str, new_datetime: datetime) -> dict:
    """
    Remarca via link — mesma verificação de disponibilidade do booking.
    Gera NOVO token (o anterior deixa de funcionar) e a mensagem de
    confirmação enviada inclui o novo link. Slot indisponível → 422.
    """
    appointment = resolve_appointment(db, raw_token)

    try:
        updated = appointment_svc.reschedule_appointment(
            db, appointment.company_id, appointment.id,
            RescheduleRequest(start_at=new_datetime),
            user_id=None, skip_policy=True,
        )
    except HTTPException as e:
        if e.status_code == 409:
            # Conflito de agenda → contrato público usa 422 (slot indisponível)
            raise HTTPException(status_code=422, detail=e.detail)
        raise

    return {
        "status": updated.status,
        "scheduled_datetime": updated.start_at,
        "message": (
            "Agendamento remarcado com sucesso. Enviamos uma nova "
            "confirmação com o link atualizado."
        ),
    }
