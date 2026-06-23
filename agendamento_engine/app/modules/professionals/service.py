import logging
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Professional, Service, ProfessionalService, User
from app.modules.professionals.schemas import (
    ProfessionalCreate,
    ProfessionalUpdate,
    ProfessionalServiceCreate,
    ProfessionalServiceResponse,
)

logger = logging.getLogger(__name__)


def list_by_service(db: Session, company_id: UUID, service_id: UUID) -> list[Professional]:
    """
    Retorna profissionais ativos que oferecem um serviço específico.
    Usado pelo bot no estado ESCOLHENDO_PROFISSIONAL.
    """
    return (
        db.query(Professional)
        .join(ProfessionalService, Professional.id == ProfessionalService.professional_id)
        .filter(
            Professional.company_id == company_id,
            Professional.active == True,
            ProfessionalService.service_id == service_id,
            ProfessionalService.company_id == company_id,
        )
        .order_by(Professional.name)
        .all()
    )


def list_professionals(db: Session, company_id: UUID, active_only: bool = True):
    q = db.query(Professional).filter(Professional.company_id == company_id)
    if active_only:
        q = q.filter(Professional.active == True)
    return q.order_by(Professional.name).all()


def get_linked_professional(db: Session, user_id: UUID, company_id: UUID) -> Professional | None:
    """Retorna o Professional vinculado à conta de login (role=PROFESSIONAL), ou None.

    Usado por /auth/me, /professionals/me, escopo de /appointments e /commissions/me.
    """
    return (
        db.query(Professional)
        .filter(
            Professional.user_id == user_id,
            Professional.company_id == company_id,
        )
        .first()
    )


def get_professional_or_404(db: Session, company_id: UUID, professional_id: UUID) -> Professional:
    p = db.query(Professional).filter(
        Professional.id == professional_id,
        Professional.company_id == company_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")
    return p


def create_professional(db: Session, company_id: UUID, data: ProfessionalCreate) -> Professional:
    p = Professional(company_id=company_id, **data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def update_professional(
    db: Session, company_id: UUID, professional_id: UUID, data: ProfessionalUpdate
) -> Professional:
    p = get_professional_or_404(db, company_id, professional_id)

    # Vínculo com conta de login (Sprint 27). Tratado à parte porque
    # exclude_none descartaria user_id=None — e None aqui significa "desvincular".
    if "user_id" in data.model_fields_set:
        _apply_user_link(db, p, data.user_id, company_id)

    fields = data.model_dump(exclude_none=True)
    fields.pop("user_id", None)  # já tratado acima
    raw_cpf_cnpj = fields.pop("cpf_cnpj", None)

    for field, value in fields.items():
        setattr(p, field, value)

    if raw_cpf_cnpj is not None:
        _apply_pii(db, p, raw_cpf_cnpj, company_id)

    db.commit()
    db.refresh(p)
    return p


def _apply_user_link(
    db: Session, professional: Professional, user_id: UUID | None, company_id: UUID
) -> None:
    """Vincula/desvincula a conta de login do profissional.

    user_id None → desvincula. user_id preenchido → valida tenant + role=PROFESSIONAL
    e exclusividade (1:1) antes de vincular.
    """
    if user_id is None:
        professional.user_id = None
        return

    target_user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.company_id == company_id,
            User.role == "PROFESSIONAL",
        )
        .first()
    )
    if not target_user:
        raise HTTPException(
            status_code=400,
            detail="Usuário não encontrado ou sem papel de profissional",
        )

    existing = (
        db.query(Professional)
        .filter(
            Professional.user_id == user_id,
            Professional.id != professional.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Este usuário já está vinculado a outro profissional",
        )

    professional.user_id = user_id


def _apply_pii(db: Session, professional: Professional, raw: str, company_id: UUID) -> None:
    """Normaliza, valida e grava CPF/CNPJ como encrypted+hash+masked. Nunca plaintext."""
    from app.modules.payments.validators import (
        normalize_cpf_cnpj,
        encrypt_pii,
        hash_pii,
        mask_cpf_cnpj,
    )

    digits = normalize_cpf_cnpj(raw)

    # Verificar duplicata por hash na mesma empresa, excluindo o próprio profissional
    cpf_hash = hash_pii(digits)
    duplicate = (
        db.query(Professional)
        .filter(
            Professional.company_id == company_id,
            Professional.cpf_cnpj_hash == cpf_hash,
            Professional.id != professional.id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="CPF/CNPJ já cadastrado para outro profissional desta empresa",
        )

    professional.cpf_cnpj_encrypted = encrypt_pii(digits)
    professional.cpf_cnpj_hash = cpf_hash
    professional.cpf_cnpj_masked = mask_cpf_cnpj(digits)
    # plaintext (digits) sai de escopo aqui — nunca gravado
    logger.info(
        "pii_updated",
        extra={
            "professional_id": str(professional.id),
            "company_id": str(company_id),
            "masked": professional.cpf_cnpj_masked,
        },
    )


# ---------------------------------------------------------------------------
# Associação profissional ↔ serviço
# ---------------------------------------------------------------------------

def list_professional_services(
    db: Session, company_id: UUID, professional_id: UUID
) -> list[ProfessionalServiceResponse]:
    get_professional_or_404(db, company_id, professional_id)
    rows = (
        db.query(ProfessionalService, Service)
        .join(Service, ProfessionalService.service_id == Service.id)
        .filter(
            ProfessionalService.professional_id == professional_id,
            ProfessionalService.company_id == company_id,
        )
        .all()
    )
    return [
        ProfessionalServiceResponse(
            id=ps.id,
            service_id=svc.id,
            service_name=svc.name,
            price=svc.price,
            duration=svc.duration,
            commission_percentage=ps.commission_percentage,
        )
        for ps, svc in rows
    ]


def add_professional_service(
    db: Session,
    company_id: UUID,
    professional_id: UUID,
    data: ProfessionalServiceCreate,
) -> ProfessionalServiceResponse:
    get_professional_or_404(db, company_id, professional_id)

    svc = (
        db.query(Service)
        .filter(Service.id == data.service_id, Service.company_id == company_id)
        .first()
    )
    if not svc:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")

    existing = (
        db.query(ProfessionalService)
        .filter(
            ProfessionalService.professional_id == professional_id,
            ProfessionalService.service_id == data.service_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Associação já existe")

    ps = ProfessionalService(
        company_id=company_id,
        professional_id=professional_id,
        service_id=data.service_id,
        commission_percentage=data.commission_percentage,
    )
    db.add(ps)
    db.commit()
    db.refresh(ps)

    return ProfessionalServiceResponse(
        id=ps.id,
        service_id=svc.id,
        service_name=svc.name,
        price=svc.price,
        duration=svc.duration,
        commission_percentage=ps.commission_percentage,
    )


def remove_professional_service(
    db: Session, company_id: UUID, professional_id: UUID, service_id: UUID
) -> None:
    get_professional_or_404(db, company_id, professional_id)

    ps = (
        db.query(ProfessionalService)
        .filter(
            ProfessionalService.professional_id == professional_id,
            ProfessionalService.service_id == service_id,
            ProfessionalService.company_id == company_id,
        )
        .first()
    )
    if not ps:
        raise HTTPException(status_code=404, detail="Associação não encontrada")

    db.delete(ps)
    db.commit()
