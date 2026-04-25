from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
 
from app.infrastructure.db.session import get_db
from app.core.deps import get_current_user   # mesmo helper usado nos outros routers
from app.modules.company_profile import service as profile_svc
from app.modules.company_profile.schemas import CompanyProfileOut, CompanyProfileUpdate
 
router = APIRouter(prefix="/company", tags=["company-profile"])
 
 
@router.get("/profile", response_model=CompanyProfileOut)
def get_profile(
    db: Session = Depends(get_db),
    company_id = Depends(get_current_user),
):
    """Retorna o perfil público da empresa autenticada."""
    profile = profile_svc.get_or_create(db, company_id)
    return profile
 
 
@router.patch("/profile", response_model=CompanyProfileOut)
def update_profile(
    data: CompanyProfileUpdate,
    db: Session = Depends(get_db),
    company_id = Depends(get_current_user),
):
    """Atualiza o perfil público da empresa (campos parciais)."""
    return profile_svc.update_profile(db, company_id, data)
