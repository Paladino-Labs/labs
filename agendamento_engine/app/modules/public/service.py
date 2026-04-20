"""
Serviços da camada pública de agendamento.

Todos os métodos aqui são chamados sem autenticação — os dados retornados
são filtrados para não expor campos internos (company_id, IDs internos, etc.).
"""
import re
import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import (
    Company, CompanySettings, Service, Professional, ProfessionalService,
    Customer, WebBookingSession,
)
from app.modules.availability import service as availability_svc
from app.modules.customers import service as customer_svc
from app.modules.booking.engine import BookingEngine
from app.modules.booking.schemas import BookingIntent
from app.modules.booking.exceptions import SlotUnavailableError
from app.modules.public.schemas import (
    CompanyPublicInfo,
    ServicePublicInfo,
    ProfessionalPublicInfo,
    SlotPublicInfo,
    PublicBookRequest,
    PublicBookResponse,
)

logger = logging.getLogger(__name__)
booking_engine = BookingEngine()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if not digits.startswith("55") and len(digits) <= 11:
        digits = "55" + digits
    return digits


def get_company_or_404(db: Session, slug: str) -> Company:
    company = db.query(Company).filter(
        Company.slug == slug,
        Company.active == True,
    ).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return company


def get_company_settings(db: Session, company_id: UUID) -> CompanySettings:
    return db.query(CompanySettings).filter(
        CompanySettings.company_id == company_id
    ).first()


# ─── Public read endpoints ─────────────────────────────────────────────────────

def get_public_info(db: Session, slug: str) -> CompanyPublicInfo:
    company = get_company_or_404(db, slug)
    cfg = get_company_settings(db, company.id)
    online_booking_enabled = cfg.online_booking_enabled if cfg else False

    if not online_booking_enabled:
        raise HTTPException(
            status_code=403,
            detail="Agendamento online não está disponível para esta empresa",
        )

    return CompanyPublicInfo(
        name=company.name,
        slug=company.slug,
        online_booking_enabled=online_booking_enabled,
    )


def list_public_services(db: Session, slug: str) -> list[ServicePublicInfo]:
    company = get_company_or_404(db, slug)
    _assert_booking_enabled(db, company.id)

    services = (
        db.query(Service)
        .filter(Service.company_id == company.id, Service.active == True)
        .order_by(Service.name)
        .all()
    )
    return [
        ServicePublicInfo(
            id=s.id,
            name=s.name,
            price=str(s.price),
            duration_minutes=s.duration,
            description=s.description,
            image_url=s.image_url,
        )
        for s in services
    ]


def list_public_professionals(
    db: Session, slug: str, service_id: UUID
) -> list[ProfessionalPublicInfo]:
    company = get_company_or_404(db, slug)
    _assert_booking_enabled(db, company.id)

    # Profissionais que atendem este serviço
    rows = (
        db.query(Professional)
        .join(ProfessionalService, ProfessionalService.professional_id == Professional.id)
        .filter(
            Professional.company_id == company.id,
            Professional.active == True,
            ProfessionalService.service_id == service_id,
        )
        .order_by(Professional.name)
        .all()
    )

    result: list[ProfessionalPublicInfo] = [
        ProfessionalPublicInfo(id=p.id, name=p.name) for p in rows
    ]
    # Adiciona opção "Qualquer disponível" ao final
    result.append(ProfessionalPublicInfo(id=None, name="Qualquer disponível"))
    return result


def list_public_slots(
    db: Session,
    slug: str,
    service_id: UUID,
    professional_id: UUID | None,
    target_date: date,
) -> list[SlotPublicInfo]:
    """
    Retorna slots disponíveis para a data.
    Se professional_id=None → agrega slots de TODOS os profissionais do serviço.
    """
    company = get_company_or_404(db, slug)
    _assert_booking_enabled(db, company.id)

    if professional_id is not None:
        raw_slots = _slots_for_prof(db, company.id, professional_id, service_id, target_date)
    else:
        # "Qualquer" — agrega e remove duplicatas de horário
        profs = (
            db.query(Professional)
            .join(ProfessionalService, ProfessionalService.professional_id == Professional.id)
            .filter(
                Professional.company_id == company.id,
                Professional.active == True,
                ProfessionalService.service_id == service_id,
            )
            .all()
        )
        seen: set[str] = set()
        raw_slots = []
        for prof in profs:
            for slot in _slots_for_prof(db, company.id, prof.id, service_id, target_date):
                key = slot.start_at.isoformat()
                if key not in seen:
                    seen.add(key)
                    raw_slots.append(slot)
        raw_slots.sort(key=lambda s: s.start_at)

    return raw_slots


def _slots_for_prof(
    db: Session, company_id: UUID, professional_id: UUID, service_id: UUID, target_date: date
) -> list[SlotPublicInfo]:
    try:
        slots = availability_svc.get_available_slots(
            db, company_id, professional_id, service_id, target_date
        )
    except HTTPException:
        return []

    prof = db.query(Professional).filter(Professional.id == professional_id).first()
    prof_name = prof.name if prof else "—"
    return [
        SlotPublicInfo(
            start_at=s.start_at,
            end_at=s.end_at,
            professional_id=professional_id,
            professional_name=prof_name,
        )
        for s in slots
    ]


# ─── Booking confirmation ──────────────────────────────────────────────────────

def public_book(
    db: Session,
    slug: str,
    data: PublicBookRequest,
) -> PublicBookResponse:
    company = get_company_or_404(db, slug)
    _assert_booking_enabled(db, company.id)

    # Upsert customer by phone
    normalized_phone = _normalize_phone(data.customer_phone)
    customer = customer_svc.get_or_create_by_phone(
        db, company.id, normalized_phone, data.customer_name.strip()
    )

    # Build idempotency key (phone + start_at + service)
    idempotency_key = f"web|{normalized_phone}|{data.service_id}|{data.start_at.isoformat()}"

    intent = BookingIntent(
        company_id=company.id,
        customer_id=customer.id,
        professional_id=data.professional_id,
        service_id=data.service_id,
        start_at=data.start_at,
        idempotency_key=idempotency_key,
    )

    try:
        result = booking_engine.confirm(db, company.id, intent)
    except SlotUnavailableError:
        raise HTTPException(
            status_code=409,
            detail="Este horário não está mais disponível. Escolha outro.",
        )
    except Exception as exc:
        logger.exception("public_book error slug=%s", slug)
        raise HTTPException(status_code=500, detail="Erro ao confirmar agendamento") from exc

    # Record the web booking session
    session = WebBookingSession(
        company_id=company.id,
        appointment_id=result.appointment_id,
        customer_name=data.customer_name.strip(),
        customer_phone=normalized_phone,
        source="web",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return PublicBookResponse(
        token=session.token,
        appointment_id=result.appointment_id,
        service_name=result.service_name,
        professional_name=result.professional_name,
        start_at=result.start_at,
        end_at=result.end_at,
        total_amount=str(result.total_amount),
    )


# ─── Internal helper ──────────────────────────────────────────────────────────

def _assert_booking_enabled(db: Session, company_id: UUID) -> None:
    cfg = get_company_settings(db, company_id)
    if not cfg or not cfg.online_booking_enabled:
        raise HTTPException(
            status_code=403,
            detail="Agendamento online não está disponível para esta empresa",
        )
