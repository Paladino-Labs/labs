import logging
from datetime import datetime
from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_user, get_current_company_id
from app.infrastructure.db.models import User, Service
from app.modules.appointments import schemas, service as svc
from app.modules.appointments.polices import PolicyViolationError
from app.modules.customer_credit.schemas import (
    AvailableCreditResponse,
    CompleteAppointmentRequest,
)
from app.modules.whatsapp.helpers import first_name as _first_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _handle_policy_error(e: PolicyViolationError) -> JSONResponse:
    """Converte PolicyViolationError em HTTP 422 com código estruturado."""
    return JSONResponse(
        status_code=422,
        content={"code": e.code, "detail": e.detail},
    )


@router.get("/", response_model=List[schemas.AppointmentResponse])
def list_appointments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    start_after: Optional[datetime] = Query(default=None),
    start_before: Optional[datetime] = Query(default=None),
    customer_id: Optional[UUID] = Query(default=None),
    professional_id: Optional[UUID] = Query(default=None),
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    # PROFESSIONAL só vê os próprios agendamentos — o filtro é forçado, ignorando
    # qualquer professional_id enviado. Sem vínculo → lista vazia.
    effective_professional_id = professional_id
    if user.role == "PROFESSIONAL":
        from app.modules.professionals.service import get_linked_professional

        prof = get_linked_professional(db, user.id, company_id)
        if not prof:
            return []
        effective_professional_id = prof.id

    return svc.list_appointments(
        db, company_id,
        page=page, page_size=page_size,
        start_after=start_after, start_before=start_before,
        customer_id=customer_id,
        professional_id=effective_professional_id,
    )


@router.post("/", response_model=schemas.AppointmentResponse, status_code=201)
def create_appointment(
    body: schemas.AppointmentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.create_appointment(
        db, user.company_id, body, user.id,
        bypass_working_hours=(user.role == "OWNER"),
    )


@router.get("/{appointment_id}", response_model=schemas.AppointmentResponse)
def get_appointment(
    appointment_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.get_appointment_or_404(db, company_id, appointment_id)


@router.patch("/{appointment_id}/cancel", response_model=schemas.AppointmentResponse)
def cancel_appointment(
    appointment_id: UUID,
    body: schemas.CancelRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # skip_policy=True: o painel é operado por admins, sem restrição de prazo mínimo
    return svc.cancel_appointment(
        db, user.company_id, appointment_id, user.id, body.reason, skip_policy=True
    )


@router.patch("/{appointment_id}/reschedule", response_model=schemas.AppointmentResponse)
def reschedule_appointment(
    appointment_id: UUID,
    body: schemas.RescheduleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # skip_policy=True: o painel é operado por admins, sem restrição de prazo mínimo
    return svc.reschedule_appointment(
        db, user.company_id, appointment_id, body, user.id, skip_policy=True,
        bypass_working_hours=(user.role == "OWNER"),
    )


def _send_pos_atendimento(
    company_id: UUID,
    customer_id: UUID,
    phone: str,
    customer_name: str,
    service_name: str,
) -> None:
    """Envia mensagem pós-atendimento via CommunicationService (background task).

    Abre sessão própria — background task roda após o response, fora do get_db().
    """
    from app.infrastructure.db.session import SessionLocal

    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, str(company_id))
        from app.modules.communication.service import communication_service
        communication_service.dispatch(
            event_type="appointment.completed",
            company_id=company_id,
            context={
                "cliente_nome": _first_name(customer_name),
                "servico": service_name,
                "empresa_nome": "",
                "recipient_phone": phone,
            },
            recipient_id=customer_id,
            recipient_type="CLIENT",
            db=db,
        )
    except Exception:
        logger.warning(
            "pos_atendimento notification failed company_id=%s phone=%s",
            company_id, phone,
        )
    finally:
        db.close()


@router.get("/{appointment_id}/available-credit", response_model=AvailableCreditResponse)
def available_credit(
    appointment_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    """Verifica (sem consumir) se o cliente tem cota disponível para o serviço
    deste agendamento."""
    from app.modules.customer_credit import service as credit_service

    appointment = svc.get_appointment_or_404(db, company_id, appointment_id)
    service_id = appointment.services[0].service_id if appointment.services else None

    credit = credit_service.find_available_credit(
        customer_id=appointment.client_id,
        company_id=company_id,
        db=db,
        service_id=service_id,
    )
    if credit is None:
        return AvailableCreditResponse(has_credit=False)

    service_name = None
    if credit.service_id:
        svc_obj = db.query(Service).filter(Service.id == credit.service_id).first()
        service_name = svc_obj.name if svc_obj else None

    return AvailableCreditResponse(
        has_credit=True,
        credit_id=credit.credit_id,
        service_name=service_name,
        remaining_cotas=credit.remaining_cotas,
    )


@router.patch("/{appointment_id}/complete", response_model=schemas.AppointmentResponse)
def complete_appointment(
    appointment_id: UUID,
    background_tasks: BackgroundTasks,
    body: CompleteAppointmentRequest = CompleteAppointmentRequest(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Marca o agendamento como CONCLUÍDO e envia mensagem pós-atendimento via WhatsApp.
    Endpoint exclusivo do painel — requer autenticação de admin.

    `use_credit=true` (Sprint 26): consome 1 cota do cliente em vez de abrir
    janela de pagamento. Sem cota disponível → 409.
    """
    appointment = svc.complete_appointment(
        db, user.company_id, appointment_id, user.id, use_credit=body.use_credit
    )

    # Notificação em background (falha silenciosa — não afeta o complete)
    try:
        if appointment.customer and appointment.customer.phone:
            svc_name = (
                appointment.services[0].service_name
                if appointment.services
                else "atendimento"
            )
            background_tasks.add_task(
                _send_pos_atendimento,
                company_id=user.company_id,
                customer_id=appointment.customer.id,
                phone=appointment.customer.phone,
                customer_name=appointment.customer.name,
                service_name=svc_name,
            )
    except Exception:
        logger.warning(
            "complete_appointment: falha ao agendar notificação appt_id=%s", appointment_id
        )

    return appointment
