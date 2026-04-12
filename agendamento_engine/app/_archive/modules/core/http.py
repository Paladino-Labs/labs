from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.core.policies import require_admin
from app.modules.core.schemas import CompanyOut, UserCreate, UserOut
from app.modules.core.service import create_company_user, get_company_or_404, list_company_users

router = APIRouter(tags=["Core"])


@router.get("/companies/me", response_model=CompanyOut)
def get_current_company(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_company_or_404(db, current_user.company_id)


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)
    return list_company_users(db, current_user.company_id)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)
    return create_company_user(
        db=db,
        company_id=current_user.company_id,
        email=data.email,
        password=data.password,
        is_admin=data.is_admin,
    )
