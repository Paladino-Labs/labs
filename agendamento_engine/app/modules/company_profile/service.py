from uuid import UUID
from sqlalchemy.orm import Session

from app.infrastructure.db.models.company_profile import CompanyProfile
from app.modules.company_profile.schemas import CompanyProfileUpdate


def get_or_create(db: Session, company_id: UUID) -> CompanyProfile:
    """Retorna o perfil existente ou cria um em branco."""
    profile = db.query(CompanyProfile).filter(
        CompanyProfile.company_id == company_id
    ).first()
    if not profile:
        profile = CompanyProfile(company_id=company_id)
        db.add(profile)
        db.flush()
    return profile


def update_profile(
    db: Session, company_id: UUID, data: CompanyProfileUpdate
) -> CompanyProfile:
    """Atualiza apenas os campos enviados (PATCH semântico)."""
    profile = get_or_create(db, company_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "business_hours_structured" and value is not None:
            # model_dump() já serializa BusinessHourEntry → dicts; value já é lista de dicts
            setattr(profile, field, value)
        else:
            setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile
