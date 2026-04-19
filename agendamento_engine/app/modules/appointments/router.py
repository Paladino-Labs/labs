import logging
from uuid import UUID
from typing import List
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_user, get_current_company_id
from app.infrastructure.db.models import User, WhatsAppConnection
from app.modules.appointments import schemas, service as svc
from app.modules.appointments.polices import PolicyViolationError
from app.modules.whatsapp import evolution_client
from app.modules.whatsapp import messages as wa_messages
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
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.list_appointments(db, company_id)


@router.post("/", response_model=schemas.AppointmentResponse, status_code=201)
def create_appointment(
    body: schemas.AppointmentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.create_appointment(db, user.company_id, body, user.id)


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
        db, user.company_id, appointment_id, body, user.id, skip_policy=True
    )


def _send_pos_atendimento(
    company_id: UUID,
    instance_name: str,
    phone: str,
    customer_name: str,
    service_name: str,
) -> None:
    """Envia mensagem pós-atendimento via WhatsApp (chamada em background task)."""
    try:
        text = wa_messages.pos_atendimento(_first_name(customer_name), service_name)
        evolution_client.send_text(instance_name, phone, text)
    except Exception:
        logger.warning(
            "pos_atendimento notification failed company_id=%s phone=%s",
            company_id, phone,
        )


@router.patch("/{appointment_id}/complete", response_model=schemas.AppointmentResponse)
def complete_appointment(
    appointment_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Marca o agendamento como CONCLUÍDO e envia mensagem pós-atendimento via WhatsApp.
    Endpoint exclusivo do painel — requer autenticação de admin.
    """
    appointment = svc.complete_appointment(db, user.company_id, appointment_id, user.id)

    # Notificação WhatsApp em background (falha silenciosa — não afeta o complete)
    try:
        conn = (
            db.query(WhatsAppConnection)
            .filter(
                WhatsAppConnection.company_id == user.company_id,
                WhatsAppConnection.status == "CONNECTED",
            )
            .first()
        )
        if conn and appointment.customer:
            svc_name = (
                appointment.services[0].service_name
                if appointment.services
                else "atendimento"
            )
            background_tasks.add_task(
                _send_pos_atendimento,
                company_id=user.company_id,
                instance_name=conn.instance_name,
                phone=appointment.customer.phone,
                customer_name=appointment.customer.name,
                service_name=svc_name,
            )
    except Exception:
        logger.warning(
            "complete_appointment: falha ao agendar notificação appt_id=%s", appointment_id
        )

    return appointment
