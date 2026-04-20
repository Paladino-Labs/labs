"""
Rotas públicas de agendamento — sem autenticação.

Prefixo: /public/{slug}

Exposto apenas quando company_settings.online_booking_enabled = True
(verificado em cada endpoint pelo service layer).
"""
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.modules.public import service as svc
from app.modules.public.schemas import (
    CompanyPublicInfo,
    ServicePublicInfo,
    ProfessionalPublicInfo,
    SlotPublicInfo,
    PublicBookRequest,
    PublicBookResponse,
)

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/{slug}/info", response_model=CompanyPublicInfo)
def get_company_info(slug: str, db: Session = Depends(get_db)):
    """Retorna nome da empresa e se o agendamento online está ativo."""
    return svc.get_public_info(db, slug)


@router.get("/{slug}/services", response_model=List[ServicePublicInfo])
def list_services(slug: str, db: Session = Depends(get_db)):
    """Lista serviços ativos disponíveis para agendamento público."""
    return svc.list_public_services(db, slug)


@router.get("/{slug}/professionals", response_model=List[ProfessionalPublicInfo])
def list_professionals(
    slug: str,
    service_id: UUID = Query(..., description="ID do serviço selecionado"),
    db: Session = Depends(get_db),
):
    """Lista profissionais que atendem o serviço (mais 'Qualquer disponível')."""
    return svc.list_public_professionals(db, slug, service_id)


@router.get("/{slug}/slots", response_model=List[SlotPublicInfo])
def list_slots(
    slug: str,
    service_id: UUID = Query(...),
    target_date: date = Query(..., alias="date", description="Data no formato YYYY-MM-DD"),
    professional_id: Optional[UUID] = Query(None, description="UUID do profissional ou omitir para 'qualquer'"),
    db: Session = Depends(get_db),
):
    """
    Retorna horários disponíveis para um serviço + profissional + data.
    Se professional_id não for enviado → agrega slots de todos os profissionais.
    """
    return svc.list_public_slots(db, slug, service_id, professional_id, target_date)


@router.post("/{slug}/book", response_model=PublicBookResponse, status_code=201)
def book(
    slug: str,
    body: PublicBookRequest,
    db: Session = Depends(get_db),
):
    """
    Confirma o agendamento.
    Cria o cliente (upsert por telefone) e o agendamento atomicamente.
    Retorna token único para a página de confirmação.
    """
    return svc.public_book(db, slug, body)
