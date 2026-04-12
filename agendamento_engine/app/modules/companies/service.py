from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models.company import Company
from app.infrastructure.db.models.company_settings import CompanySettings
from app.modules.companies.schemas import CompanyPatch


def get_company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return company


def get_company_with_settings(db: Session, company_id: UUID) -> Company:
    """Retorna a company com settings carregado (para o GET /me)."""
    company = get_company_or_404(db, company_id)

    # Carrega settings explicitamente para evitar lazy-load fora de contexto
    settings = (
        db.query(CompanySettings)
        .filter(CompanySettings.company_id == company_id)
        .first()
    )
    # Injeta no objeto para serialização pelo schema (from_attributes)
    company.settings = settings
    return company


def update_company(db: Session, company_id: UUID, data: CompanyPatch) -> Company:
    company = get_company_or_404(db, company_id)

    # Atualiza campos da Company
    if data.company is not None:
        company_fields = data.company.model_dump(exclude_none=True)

        # Valida unicidade do slug (ignora a própria company)
        if "slug" in company_fields:
            slug_conflict = (
                db.query(Company)
                .filter(
                    Company.slug == company_fields["slug"],
                    Company.id != company_id,
                )
                .first()
            )
            if slug_conflict:
                raise HTTPException(
                    status_code=409,
                    detail=f"Slug '{company_fields['slug']}' já está em uso por outra empresa",
                )

        for field, value in company_fields.items():
            setattr(company, field, value)

    # Atualiza (ou cria) CompanySettings
    if data.settings is not None:
        settings_fields = data.settings.model_dump(exclude_none=True)

        settings = (
            db.query(CompanySettings)
            .filter(CompanySettings.company_id == company_id)
            .first()
        )

        if settings is None:
            # Cria com os valores fornecidos; demais campos usam defaults do modelo
            settings = CompanySettings(company_id=company_id, **settings_fields)
            db.add(settings)
        else:
            for field, value in settings_fields.items():
                setattr(settings, field, value)

    db.commit()
    db.refresh(company)

    # Recarrega settings após commit para retornar estado atualizado
    settings = (
        db.query(CompanySettings)
        .filter(CompanySettings.company_id == company_id)
        .first()
    )
    company.settings = settings
    return company
