from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_company_id, require_admin
from app.modules.companies import schemas, service

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/me", response_model=schemas.CompanyResponse)
def get_my_company(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    """Retorna os dados da empresa do usuário autenticado, incluindo configurações."""
    return service.get_company_with_settings(db, company_id)


@router.patch("/me", response_model=schemas.CompanyResponse)
def update_my_company(
    body: schemas.CompanyPatch,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    """Atualiza nome, slug e/ou configurações operacionais da empresa. Restrito a admins."""
    return service.update_company(db, company_id, body)
