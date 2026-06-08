from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.infrastructure.db.session import get_db
from app.modules.packages import service as package_service
from app.modules.packages.schemas import (
    PackageCreate,
    PackagePurchaseResponse,
    PackageResponse,
    PackageUpdate,
    SellPackageRequest,
    SellPackageResponse,
)

router = APIRouter(tags=["packages"])


@router.get("/packages", response_model=List[PackageResponse])
def list_packages(
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return package_service.list_packages(current_user.company_id, db)


@router.post("/packages", response_model=PackageResponse, status_code=201)
def create_package(
    body: PackageCreate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return package_service.create_package(
        company_id=current_user.company_id,
        name=body.name,
        total_cotas=body.total_cotas,
        price=body.price,
        service_id=body.service_id,
        validity_days=body.validity_days,
        db=db,
    )


@router.patch("/packages/{package_id}", response_model=PackageResponse)
def update_package(
    package_id: UUID,
    body: PackageUpdate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return package_service.update_package(
        package_id=package_id,
        company_id=current_user.company_id,
        db=db,
        **body.model_dump(exclude_none=True),
    )


@router.delete("/packages/{package_id}", response_model=PackageResponse)
def delete_package(
    package_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return package_service.delete_package(package_id, current_user.company_id, db)


@router.post("/packages/{package_id}/sell", response_model=SellPackageResponse, status_code=201)
def sell_package(
    package_id: UUID,
    body: SellPackageRequest,
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    pkg_purchase = package_service.purchase(
        customer_id=body.customer_id,
        package_id=package_id,
        seller_user_id=body.seller_user_id,
        payment_method=body.payment_method,
        target_account_id=body.target_account_id,
        company_id=current_user.company_id,
        db=db,
    )
    return SellPackageResponse(
        purchase_id=pkg_purchase.purchase_id,
        payment_id=pkg_purchase.payment_id,
    )


@router.get("/package-purchases", response_model=List[PackagePurchaseResponse])
def list_purchases(
    customer_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return package_service.list_purchases(
        company_id=current_user.company_id,
        db=db,
        customer_id=customer_id,
        status=status,
    )


@router.get("/package-purchases/{purchase_id}", response_model=PackagePurchaseResponse)
def get_purchase(
    purchase_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return package_service.get_purchase(purchase_id, current_user.company_id, db)
