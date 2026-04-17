"""
Router público de agendamento online.

Acesso por company slug — sem autenticação JWT.
Validação de acesso: empresa deve existir, estar ativa e com online_booking_enabled=True.
Exceção: /info não exige online_booking_enabled (a landing page precisa saber o status).

Endpoints:
  GET  /booking/{slug}/info
  GET  /booking/{slug}/services
  GET  /booking/{slug}/professionals
  GET  /booking/{slug}/dates
  GET  /booking/{slug}/slots
  POST /booking/{slug}/confirm
  GET  /booking/{slug}/appointments
  PATCH /booking/{slug}/appointments/{appointment_id}/cancel
"""
import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.infrastructure.db.models.company import Company
from app.infrastructure.db.models.company_settings import CompanySettings
from app.modules.booking.engine import booking_engine
from app.modules.booking.exceptions import SlotUnavailableError, BookingNotFoundError
from app.modules.booking.http_schemas import (
    CompanyInfoResponse,
    ServiceOptionResponse,
    ProfessionalOptionResponse,
    DateOptionResponse,
    SlotOptionResponse,
    ConfirmBookingRequest,
    BookingResultResponse,
    AppointmentSummaryResponse,
    CancelBookingRequest,
    CancelResultResponse,
)
from app.modules.booking.schemas import BookingIntent
from app.modules.customers import service as customer_svc
from app.modules.appointments.polices import PolicyViolationError
import uuid as uuidlib

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/booking", tags=["booking-public"])


# ─── Dependências de rota ─────────────────────────────────────────────────────

def _get_company_or_404(slug: str, db: Session) -> Company:
    """Resolve slug → Company. Levanta 404 se não encontrada ou inativa."""
    company = (
        db.query(Company)
        .filter(Company.slug == slug, Company.active == True)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return company


def _get_settings(company_id: UUID, db: Session) -> Optional[CompanySettings]:
    return (
        db.query(CompanySettings)
        .filter(CompanySettings.company_id == company_id)
        .first()
    )


def _require_online_booking(slug: str, db: Session) -> tuple[Company, CompanySettings]:
    """
    Valida que a empresa aceita agendamento online.
    Usado por todos os endpoints operacionais (não o /info).
    """
    company = _get_company_or_404(slug, db)
    settings = _get_settings(company.id, db)

    if not settings or not settings.online_booking_enabled:
        raise HTTPException(
            status_code=403,
            detail="Esta empresa não aceita agendamentos online no momento",
        )
    return company, settings


# ─── 4.2 — Info da empresa ───────────────────────────────────────────────────

@router.get("/{slug}/info", response_model=CompanyInfoResponse)
def get_company_info(slug: str, db: Session = Depends(get_db)):
    """
    Retorna status público da empresa.
    Não exige online_booking_enabled — a landing page precisa saber se pode abrir o fluxo.
    """
    company = _get_company_or_404(slug, db)
    settings = _get_settings(company.id, db)

    services_count = (
        len(booking_engine.list_services(db, company.id))
        if (settings and settings.online_booking_enabled)
        else 0
    )

    return CompanyInfoResponse(
        company_name=company.name,
        active=company.active,
        online_booking_enabled=bool(settings and settings.online_booking_enabled),
        services_count=services_count,
    )


# ─── 4.1 — Serviços ──────────────────────────────────────────────────────────

@router.get("/{slug}/services", response_model=list[ServiceOptionResponse])
def list_services(slug: str, db: Session = Depends(get_db)):
    """Lista serviços ativos da empresa."""
    company, _ = _require_online_booking(slug, db)
    options = booking_engine.list_services(db, company.id)
    return [
        ServiceOptionResponse(
            id=o.id,
            name=o.name,
            price=o.price,
            duration_minutes=o.duration_minutes,
            row_key=o.row_key,
        )
        for o in options
    ]


# ─── 4.1 — Profissionais ─────────────────────────────────────────────────────

@router.get("/{slug}/professionals", response_model=list[ProfessionalOptionResponse])
def list_professionals(
    slug: str,
    service_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """Lista profissionais disponíveis para o serviço."""
    company, _ = _require_online_booking(slug, db)
    options = booking_engine.list_professionals(db, company.id, service_id)
    return [
        ProfessionalOptionResponse(id=o.id, name=o.name, row_key=o.row_key)
        for o in options
    ]


# ─── 4.1 — Datas disponíveis ─────────────────────────────────────────────────

@router.get("/{slug}/dates", response_model=list[DateOptionResponse])
def list_available_dates(
    slug: str,
    service_id: UUID = Query(...),
    professional_id: Optional[UUID] = Query(None),
    days: int = Query(30, ge=1, le=60),
    db: Session = Depends(get_db),
):
    """
    Retorna os próximos <days> dias com indicação de disponibilidade.
    professional_id omitido = qualquer profissional do serviço.
    """
    company, _ = _require_online_booking(slug, db)
    options = booking_engine.list_available_dates(
        db, company.id, professional_id, service_id, days=days
    )
    return [
        DateOptionResponse(
            date=o.date,
            label=o.label,
            has_availability=o.has_availability,
            row_key=o.row_key,
        )
        for o in options
    ]


# ─── 4.1 — Slots disponíveis ─────────────────────────────────────────────────

@router.get("/{slug}/slots", response_model=list[SlotOptionResponse])
def list_available_slots(
    slug: str,
    service_id: UUID = Query(...),
    target_date: date = Query(...),
    professional_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Retorna slots disponíveis para a data.
    professional_id omitido = agrega todos os profissionais do serviço.
    """
    company, _ = _require_online_booking(slug, db)
    options = booking_engine.list_available_slots(
        db, company.id, professional_id, service_id, target_date
    )
    return [
        SlotOptionResponse(
            start_at=o.start_at,
            end_at=o.end_at,
            professional_id=o.professional_id,
            professional_name=o.professional_name,
            row_key=o.row_key,
        )
        for o in options
    ]


# ─── 4.1 — Confirmar agendamento ─────────────────────────────────────────────

@router.post("/{slug}/confirm", response_model=BookingResultResponse, status_code=201)
def confirm_booking(
    slug: str,
    body: ConfirmBookingRequest,
    db: Session = Depends(get_db),
):
    """
    Identifica ou cria o cliente pelo telefone e confirma o agendamento.
    Retorna 409 se o slot já foi ocupado (race condition).
    """
    company, _ = _require_online_booking(slug, db)

    # Identifica ou cria o cliente pelo telefone
    customer = customer_svc.get_or_create_by_phone(
        db, company.id, body.customer_phone, body.customer_name
    )

    intent = BookingIntent(
        company_id=company.id,
        customer_id=customer.id,
        professional_id=body.professional_id,
        service_id=body.service_id,
        start_at=body.start_at,
        idempotency_key=body.idempotency_key,
    )

    try:
        result = booking_engine.confirm(db, company.id, intent)
    except SlotUnavailableError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return BookingResultResponse(
        appointment_id=result.appointment_id,
        service_name=result.service_name,
        professional_name=result.professional_name,
        start_at=result.start_at,
        end_at=result.end_at,
        total_amount=result.total_amount,
    )


# ─── 4.1 — Agendamentos do cliente ───────────────────────────────────────────

@router.get("/{slug}/appointments", response_model=list[AppointmentSummaryResponse])
def list_customer_appointments(
    slug: str,
    phone: str = Query(..., description="Telefone do cliente para identificação"),
    db: Session = Depends(get_db),
):
    """
    Retorna agendamentos ativos do cliente identificado pelo telefone.
    Retorna lista vazia se cliente não encontrado (não expõe 404 publicamente).
    """
    company, _ = _require_online_booking(slug, db)

    customer = customer_svc.get_by_phone(db, company.id, phone)
    if not customer:
        return []

    summaries = booking_engine.get_customer_appointments(db, company.id, customer.id)
    return [
        AppointmentSummaryResponse(
            id=s.id,
            service_name=s.service_name,
            professional_name=s.professional_name,
            start_at=s.start_at,
            status=s.status,
        )
        for s in summaries
    ]


# ─── 4.1 — Cancelar agendamento ──────────────────────────────────────────────

@router.patch(
    "/{slug}/appointments/{appointment_id}/cancel",
    response_model=CancelResultResponse,
)
def cancel_booking(
    slug: str,
    appointment_id: UUID,
    body: CancelBookingRequest,
    db: Session = Depends(get_db),
):
    """
    Cancela um agendamento.
    Valida que o telefone enviado pertence ao cliente dono do agendamento.
    Retorna 403 se fora do prazo de cancelamento (PolicyViolationError).
    """
    company, _ = _require_online_booking(slug, db)

    # Valida que o telefone corresponde ao dono do agendamento
    customer = customer_svc.get_by_phone(db, company.id, body.phone)
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    try:
        result = booking_engine.cancel(
            db, company.id, appointment_id, reason=body.reason
        )
    except BookingNotFoundError:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    except PolicyViolationError as e:
        raise HTTPException(status_code=403, detail=e.detail)

    return CancelResultResponse(success=result.success, message=result.message)