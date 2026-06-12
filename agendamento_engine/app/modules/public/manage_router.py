"""
Router público /manage/{token} — gestão de agendamento sem login (Sprint B).

Sem autenticação JWT: a posse do token cru (recebido no WhatsApp) é a
credencial. Erros de token retornam SEMPRE 404 genérico.

Rate limit por IP (slowapi): 10/min no GET, 5/min em cancel/reschedule.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.infrastructure.db.session import get_db
from app.modules.public import manage_service as svc

router = APIRouter(prefix="/manage", tags=["manage"])


class ManageDetailsResponse(BaseModel):
    service_name: Optional[str]
    professional_name: Optional[str]
    scheduled_datetime: datetime
    status: str
    can_cancel: bool
    can_reschedule: bool


class ManageCancelRequest(BaseModel):
    reason: Optional[str] = None


class ManageCancelResponse(BaseModel):
    status: str
    deposit_retained: bool
    message: str


class ManageRescheduleRequest(BaseModel):
    new_datetime: datetime


class ManageRescheduleResponse(BaseModel):
    status: str
    scheduled_datetime: datetime
    message: str


@router.get("/{token}", response_model=ManageDetailsResponse)
@limiter.limit("10/minute")
def get_appointment_details(
    request: Request, token: str, db: Session = Depends(get_db)
):
    """Detalhes do agendamento vinculado ao token (404 genérico se inválido)."""
    return svc.get_details(db, token)


@router.post("/{token}/cancel", response_model=ManageCancelResponse)
@limiter.limit("5/minute")
def cancel_appointment(
    request: Request,
    token: str,
    body: Optional[ManageCancelRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Cancela o agendamento (actor=CLIENT). A janela de cancelamento decide
    a CONSEQUÊNCIA (retenção de sinal via DepositPolicy), não a permissão.
    """
    reason = body.reason if body else None
    return svc.cancel(db, token, reason=reason)


@router.post("/{token}/reschedule", response_model=ManageRescheduleResponse)
@limiter.limit("5/minute")
def reschedule_appointment(
    request: Request,
    token: str,
    body: ManageRescheduleRequest,
    db: Session = Depends(get_db),
):
    """
    Remarca o agendamento. Verifica disponibilidade (mesma lógica do booking);
    slot indisponível → 422. Gera novo token e invalida o anterior.
    """
    return svc.reschedule(db, token, body.new_datetime)
