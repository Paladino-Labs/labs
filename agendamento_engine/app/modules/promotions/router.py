"""Rotas do módulo Promotions — Sprint 16.

POST   /promotions                       OWNER/ADMIN
GET    /promotions                       OWNER/ADMIN
POST   /promotions/preview               autenticado (zero efeito colateral)
GET    /promotions/{id}                  OWNER/ADMIN
PATCH  /promotions/{id}/activate         OWNER/ADMIN
PATCH  /promotions/{id}/pause            OWNER/ADMIN
PATCH  /promotions/{id}/cancel           OWNER/ADMIN
POST   /promotions/{id}/coupons          OWNER/ADMIN (generate_bulk)
GET    /promotions/{id}/coupons          OWNER/ADMIN
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.infrastructure.db.session import get_db
from app.modules.promotions import service as promotion_service
from app.modules.promotions.schemas import (
    CouponGenerateRequest,
    CouponResponse,
    PreviewRequest,
    PreviewResponse,
    PromotionCreate,
    PromotionResponse,
)

router = APIRouter(prefix="/promotions", tags=["promotions"])

_owner_admin = require_role("OWNER", "ADMIN", "PLATFORM_OWNER")


@router.post("", response_model=PromotionResponse, status_code=201)
def create_promotion(
    body: PromotionCreate,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return promotion_service.create_promotion(
        company_id=user.company_id,
        created_by=user.id,
        db=db,
        **body.model_dump(),
    )


@router.get("", response_model=list[PromotionResponse])
def list_promotions(
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return promotion_service.list_promotions(company_id=user.company_id, db=db)


@router.post("/preview", response_model=PreviewResponse)
def preview_discounts(
    body: PreviewRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview de descontos — não persiste nada."""
    return promotion_service.compute_preview(
        db=db,
        company_id=user.company_id,
        gross_amount=body.gross_amount,
        service_ids=body.service_ids,
        product_ids=body.product_ids,
        customer_id=body.customer_id,
        coupon_code=body.coupon_code,
        subscription_cycle=body.subscription_cycle,
    )


@router.get("/{promotion_id}", response_model=PromotionResponse)
def get_promotion(
    promotion_id: UUID,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return promotion_service.get_promotion(
        promotion_id=promotion_id, company_id=user.company_id, db=db
    )


@router.patch("/{promotion_id}/activate", response_model=PromotionResponse)
def activate_promotion(
    promotion_id: UUID,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return promotion_service.transition_promotion(
        promotion_id=promotion_id, company_id=user.company_id, action="activate", db=db
    )


@router.patch("/{promotion_id}/pause", response_model=PromotionResponse)
def pause_promotion(
    promotion_id: UUID,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return promotion_service.transition_promotion(
        promotion_id=promotion_id, company_id=user.company_id, action="pause", db=db
    )


@router.patch("/{promotion_id}/cancel", response_model=PromotionResponse)
def cancel_promotion(
    promotion_id: UUID,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return promotion_service.transition_promotion(
        promotion_id=promotion_id, company_id=user.company_id, action="cancel", db=db
    )


@router.post("/{promotion_id}/coupons", response_model=list[CouponResponse], status_code=201)
def generate_coupons(
    promotion_id: UUID,
    body: CouponGenerateRequest,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return promotion_service.generate_coupons(
        promotion_id=promotion_id,
        company_id=user.company_id,
        db=db,
        **body.model_dump(),
    )


@router.get("/{promotion_id}/coupons", response_model=list[CouponResponse])
def list_coupons(
    promotion_id: UUID,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return promotion_service.list_coupons(
        promotion_id=promotion_id, company_id=user.company_id, db=db
    )
