"""PromotionEngine + CouponService — Sprint 16 (Decisão D1).

compute_preview(): cálculo puro, ZERO efeito colateral — nenhum add/commit.
effectuate(): chamado pelo promotion_payment_handler em payment.confirmed.
    Revalida tudo (promoção pode ter mudado entre preview e confirm) com
    SELECT FOR UPDATE em uses_count dos cupons. Falha de revalidação NÃO
    bloqueia o pagamento — modo STRICT publica promotion.effectuation_failed
    (decisão de produto registrada no brief do sprint; supersede o "refund
    automático" do DoD original).
revert_for_refund(): chamado em payment.refunded — preenche reverted_at em
    CouponRedemption/DiscountApplication e aplica coupon_reopen_policy.

Algoritmo de seleção (visão):
    elegíveis → cumulative vs exclusive → exclusiva de maior desconto
    (CUSTOMER_FAVORABLE) → sequência (exclusiva, depois cumulativas em
    priority DESC), cada desconto calculado sobre o residual do anterior.
"""
from __future__ import annotations

import logging
import secrets
import uuid as uuid_mod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models.promotion import (
    Coupon,
    CouponRedemption,
    DiscountApplication,
    Promotion,
)
from app.infrastructure.event_bus import DomainEvent, event_bus

logger = logging.getLogger(__name__)

DISCOUNT_TYPES = {"PERCENTAGE", "FIXED_AMOUNT", "OVERRIDE_PRICE", "FREE_ITEM"}
APPLICATION_MODES = {"AUTOMATIC", "COUPON_REQUIRED"}
GENERATION_TYPES = {"BULK", "SINGLE_USE", "PER_CUSTOMER"}
REOPEN_POLICIES = {"NEVER_REOPEN", "REOPEN_ON_REFUND"}

# Transições válidas do FSM de Promotion
_PROMOTION_TRANSITIONS: dict[str, set[str]] = {
    "activate": {"DRAFT", "PAUSED"},
    "pause": {"ACTIVE"},
    "cancel": {"DRAFT", "ACTIVE", "PAUSED"},
}


def _publish(event_type: str, company_id, idempotency_key: str, payload: dict) -> None:
    """Publica evento best-effort — falha nunca propaga."""
    try:
        event_bus.publish(DomainEvent(
            event_id=uuid_mod.uuid4(),
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            company_id=company_id,
            idempotency_key=idempotency_key,
            actor={"type": "SYSTEM", "id": str(company_id)},
            payload=payload,
        ))
    except Exception:
        logger.exception("promotions: falha ao publicar %s", event_type)


# ── CRUD de Promotion ─────────────────────────────────────────────────────────

def _get_promotion(promotion_id: UUID, company_id: UUID, db: Session) -> Promotion:
    promo = (
        db.query(Promotion)
        .filter(Promotion.id == promotion_id, Promotion.company_id == company_id)
        .first()
    )
    if not promo:
        raise HTTPException(status_code=404, detail="Promoção não encontrada")
    return promo


def create_promotion(
    company_id: UUID,
    created_by: UUID,
    db: Session,
    *,
    name: str,
    discount_type: str,
    discount_value: Optional[Decimal] = None,
    description: Optional[str] = None,
    application_mode: str = "AUTOMATIC",
    cumulative: bool = False,
    priority: int = 0,
    valid_from: Optional[datetime] = None,
    valid_until: Optional[datetime] = None,
    max_uses: Optional[int] = None,
    max_uses_per_customer: Optional[int] = None,
    conditions: Optional[dict] = None,
) -> Promotion:
    if discount_type not in DISCOUNT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"discount_type deve ser um de: {sorted(DISCOUNT_TYPES)}",
        )
    if application_mode not in APPLICATION_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"application_mode deve ser um de: {sorted(APPLICATION_MODES)}",
        )
    if discount_type != "FREE_ITEM":
        if discount_value is None or Decimal(str(discount_value)) <= 0:
            raise HTTPException(
                status_code=422,
                detail=f"discount_value (> 0) é obrigatório para {discount_type}",
            )
        if discount_type == "PERCENTAGE" and Decimal(str(discount_value)) > Decimal("100"):
            raise HTTPException(status_code=422, detail="PERCENTAGE não pode exceder 100")
    if valid_from and valid_until and valid_from >= valid_until:
        raise HTTPException(status_code=422, detail="valid_from deve ser anterior a valid_until")

    promo = Promotion(
        company_id=company_id,
        name=name,
        description=description,
        discount_type=discount_type,
        discount_value=discount_value,
        application_mode=application_mode,
        cumulative=cumulative,
        priority=priority,
        status="DRAFT",
        valid_from=valid_from,
        valid_until=valid_until,
        max_uses=max_uses,
        max_uses_per_customer=max_uses_per_customer,
        conditions=conditions,
        created_by=created_by,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)

    _publish(
        "promotion.created", company_id,
        f"promotion.created:{promo.id}",
        {"promotion_id": str(promo.id), "company_id": str(company_id), "name": name},
    )
    return promo


def list_promotions(company_id: UUID, db: Session) -> list[Promotion]:
    return (
        db.query(Promotion)
        .filter(Promotion.company_id == company_id)
        .order_by(Promotion.created_at.desc())
        .all()
    )


def get_promotion(promotion_id: UUID, company_id: UUID, db: Session) -> Promotion:
    return _get_promotion(promotion_id, company_id, db)


def list_active_promotions(db: Session, company_id: UUID) -> list[Promotion]:
    """Promoções automáticas vigentes do tenant (vitrine pública B2).

    Apenas ACTIVE + AUTOMATIC (COUPON_REQUIRED não se exibe na vitrine),
    dentro da janela de validade e com cota de usos disponível.
    """
    now = datetime.now(timezone.utc)
    return (
        db.query(Promotion)
        .filter(
            Promotion.company_id == company_id,
            Promotion.status == "ACTIVE",
            Promotion.application_mode == "AUTOMATIC",
            (Promotion.valid_from == None) | (Promotion.valid_from <= now),  # noqa: E711
            (Promotion.valid_until == None) | (Promotion.valid_until >= now),  # noqa: E711
            (Promotion.max_uses == None) | (Promotion.uses_count < Promotion.max_uses),  # noqa: E711
        )
        .order_by(Promotion.priority.desc())
        .all()
    )


def transition_promotion(
    promotion_id: UUID, company_id: UUID, action: str, db: Session
) -> Promotion:
    """activate | pause | cancel — valida FSM e publica o evento correspondente."""
    promo = _get_promotion(promotion_id, company_id, db)
    allowed = _PROMOTION_TRANSITIONS.get(action)
    if allowed is None:
        raise HTTPException(status_code=422, detail=f"Ação desconhecida: {action}")
    if promo.status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Transição '{action}' inválida a partir de {promo.status}",
        )

    new_status = {"activate": "ACTIVE", "pause": "PAUSED", "cancel": "CANCELLED"}[action]
    promo.status = new_status
    promo.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(promo)

    event_type = {"activate": "promotion.activated", "pause": "promotion.paused",
                  "cancel": "promotion.cancelled"}[action]
    _publish(
        event_type, company_id,
        f"{event_type}:{promo.id}",
        {"promotion_id": str(promo.id), "company_id": str(company_id)},
    )
    return promo


# ── Cupons ────────────────────────────────────────────────────────────────────

def _random_code(prefix: str = "") -> str:
    code = secrets.token_hex(4).upper()
    return f"{prefix}{code}" if prefix else code


def generate_coupons(
    promotion_id: UUID,
    company_id: UUID,
    db: Session,
    *,
    generation_type: str,
    quantity: int = 1,
    code: Optional[str] = None,
    prefix: Optional[str] = None,
    max_uses: Optional[int] = None,
    customer_id: Optional[UUID] = None,
    expires_at: Optional[datetime] = None,
    coupon_reopen_policy: str = "NEVER_REOPEN",
) -> list[Coupon]:
    """Gera cupons para uma promoção. BULK gera `quantity` códigos aleatórios;
    SINGLE_USE força max_uses=1; PER_CUSTOMER exige customer_id."""
    if generation_type not in GENERATION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"generation_type deve ser um de: {sorted(GENERATION_TYPES)}",
        )
    if coupon_reopen_policy not in REOPEN_POLICIES:
        raise HTTPException(
            status_code=422,
            detail=f"coupon_reopen_policy deve ser um de: {sorted(REOPEN_POLICIES)}",
        )
    if generation_type == "PER_CUSTOMER" and not customer_id:
        raise HTTPException(status_code=422, detail="PER_CUSTOMER exige customer_id")
    if generation_type == "BULK" and quantity < 1:
        raise HTTPException(status_code=422, detail="quantity deve ser >= 1")

    promo = _get_promotion(promotion_id, company_id, db)
    if promo.status in ("EXPIRED", "CANCELLED"):
        raise HTTPException(
            status_code=422,
            detail=f"Promoção {promo.status} não pode receber cupons novos",
        )

    n = quantity if generation_type == "BULK" else 1
    effective_max_uses = 1 if generation_type == "SINGLE_USE" else max_uses

    coupons: list[Coupon] = []
    for i in range(n):
        coupon_code = code if (code and n == 1) else _random_code(prefix or "")
        coupon = Coupon(
            company_id=company_id,
            promotion_id=promo.id,
            code=coupon_code.upper(),
            generation_type=generation_type,
            max_uses=effective_max_uses,
            coupon_reopen_policy=coupon_reopen_policy,
            status="ACTIVE",
            customer_id=customer_id if generation_type == "PER_CUSTOMER" else None,
            expires_at=expires_at,
        )
        db.add(coupon)
        coupons.append(coupon)

    db.commit()
    for c in coupons:
        db.refresh(c)
    return coupons


def list_coupons(promotion_id: UUID, company_id: UUID, db: Session) -> list[Coupon]:
    _get_promotion(promotion_id, company_id, db)
    return (
        db.query(Coupon)
        .filter(Coupon.company_id == company_id, Coupon.promotion_id == promotion_id)
        .order_by(Coupon.created_at.desc())
        .all()
    )


def _validate_coupon(
    db: Session,
    company_id: UUID,
    coupon_code: str,
    customer_id: Optional[UUID],
    for_update: bool = False,
) -> Coupon:
    """Valida cupom — 422 se inválido. for_update=True trava a linha (efetivação)."""
    query = db.query(Coupon).filter(
        Coupon.company_id == company_id,
        Coupon.code == coupon_code.upper(),
    )
    if for_update:
        query = query.with_for_update()
    coupon = query.first()

    if not coupon:
        raise HTTPException(status_code=422, detail="Cupom inválido")
    if coupon.status != "ACTIVE":
        raise HTTPException(status_code=422, detail=f"Cupom não está ativo ({coupon.status})")
    now = datetime.now(timezone.utc)
    if coupon.expires_at and now > coupon.expires_at:
        raise HTTPException(status_code=422, detail="Cupom expirado")
    if coupon.max_uses is not None and coupon.uses_count >= coupon.max_uses:
        raise HTTPException(status_code=422, detail="Cupom esgotado")
    if coupon.generation_type == "PER_CUSTOMER" and coupon.customer_id:
        if customer_id is None or str(customer_id) != str(coupon.customer_id):
            raise HTTPException(status_code=422, detail="Cupom pertence a outro cliente")
    return coupon


# ── Engine de cálculo ─────────────────────────────────────────────────────────

def _calc_discount(promo: Promotion, residual: Decimal) -> Decimal:
    """Desconto desta promoção sobre o residual. Nunca excede o residual."""
    if residual <= 0:
        return Decimal("0")
    value = Decimal(str(promo.discount_value)) if promo.discount_value is not None else Decimal("0")
    dtype = promo.discount_type

    if dtype == "PERCENTAGE":
        discount = round(residual * value / Decimal("100"), 2)
    elif dtype == "FIXED_AMOUNT":
        discount = value
    elif dtype == "OVERRIDE_PRICE":
        discount = residual - value
    elif dtype == "FREE_ITEM":
        # FREE_ITEM não tem valor monetário no Estágio 0 — registra com desconto 0
        discount = Decimal("0")
    else:
        discount = Decimal("0")

    return max(Decimal("0"), min(discount, residual))


def _is_eligible(
    promo: Promotion,
    *,
    gross_amount: Decimal,
    service_ids: Optional[list],
    product_ids: Optional[list],
    subscription_cycle: Optional[int],
    customer_classification: Optional[str],
    now: datetime,
) -> bool:
    """Status ACTIVE + janela de validade + limites + conditions JSONB."""
    if promo.status != "ACTIVE":
        return False
    if promo.valid_from and now < promo.valid_from:
        return False
    if promo.valid_until and now > promo.valid_until:
        return False
    if promo.max_uses is not None and (promo.uses_count or 0) >= promo.max_uses:
        return False

    cond = promo.conditions or {}

    if cond.get("min_order_value") is not None:
        if gross_amount < Decimal(str(cond["min_order_value"])):
            return False

    if cond.get("service_ids"):
        wanted = {str(s) for s in cond["service_ids"]}
        if not service_ids or not wanted & {str(s) for s in service_ids}:
            return False

    if cond.get("product_ids"):
        wanted = {str(p) for p in cond["product_ids"]}
        if not product_ids or not wanted & {str(p) for p in product_ids}:
            return False

    if cond.get("subscription_cycle_number_in") is not None:
        if subscription_cycle is None or subscription_cycle not in cond["subscription_cycle_number_in"]:
            return False
    if cond.get("subscription_cycle_min") is not None:
        if subscription_cycle is None or subscription_cycle < cond["subscription_cycle_min"]:
            return False
    if cond.get("subscription_cycle_max") is not None:
        if subscription_cycle is None or subscription_cycle > cond["subscription_cycle_max"]:
            return False

    if cond.get("customer_classification") is not None:
        if customer_classification != cond["customer_classification"]:
            return False

    return True


def _compute(
    db: Session,
    company_id: UUID,
    gross_amount: Decimal,
    service_ids: Optional[list] = None,
    product_ids: Optional[list] = None,
    customer_id: Optional[UUID] = None,
    coupon_code: Optional[str] = None,
    subscription_cycle: Optional[int] = None,
    customer_classification: Optional[str] = None,
    for_update: bool = False,
) -> tuple[dict, dict[str, Promotion], Optional[Coupon]]:
    """Núcleo compartilhado entre compute_preview e effectuate.

    Retorna (resultado, promoções escolhidas por id, cupom validado ou None).
    Levanta 422 se coupon_code informado for inválido.
    """
    now = datetime.now(timezone.utc)
    gross = Decimal(str(gross_amount))

    coupon: Optional[Coupon] = None
    if coupon_code:
        coupon = _validate_coupon(db, company_id, coupon_code, customer_id, for_update=for_update)
        # max_uses_per_customer da promoção do cupom
        if customer_id is not None:
            promo_of_coupon = (
                db.query(Promotion)
                .filter(Promotion.id == coupon.promotion_id, Promotion.company_id == company_id)
                .first()
            )
            limit = promo_of_coupon.max_uses_per_customer if promo_of_coupon else None
            if limit is not None:
                used = (
                    db.query(CouponRedemption)
                    .filter(
                        CouponRedemption.company_id == company_id,
                        CouponRedemption.coupon_id == coupon.id,
                        CouponRedemption.customer_id == customer_id,
                        CouponRedemption.reverted_at == None,  # noqa: E711
                    )
                    .count()
                )
                if used >= limit:
                    raise HTTPException(
                        status_code=422,
                        detail="Limite de usos do cupom por cliente atingido",
                    )

    candidates = (
        db.query(Promotion)
        .filter(Promotion.company_id == company_id, Promotion.status == "ACTIVE")
        .all()
    )

    eligible: list[Promotion] = []
    for promo in candidates:
        if not _is_eligible(
            promo,
            gross_amount=gross,
            service_ids=service_ids,
            product_ids=product_ids,
            subscription_cycle=subscription_cycle,
            customer_classification=customer_classification,
            now=now,
        ):
            continue
        if promo.application_mode == "COUPON_REQUIRED":
            if not coupon or str(coupon.promotion_id) != str(promo.id):
                continue
        eligible.append(promo)

    exclusives = [p for p in eligible if not p.cumulative]
    cumulatives = [p for p in eligible if p.cumulative]

    chosen: list[Promotion] = []
    if exclusives:
        # CUSTOMER_FAVORABLE: entre exclusivas, a de maior desconto sobre o bruto
        best = max(exclusives, key=lambda p: _calc_discount(p, gross))
        chosen.append(best)
    chosen.extend(sorted(cumulatives, key=lambda p: p.priority or 0, reverse=True))

    residual = gross
    applications: list[dict] = []
    sequence = 0
    for promo in chosen:
        discount = _calc_discount(promo, residual)
        if discount <= 0 and promo.discount_type != "FREE_ITEM":
            continue
        sequence += 1
        applications.append({
            "promotion_id": str(promo.id),
            "sequence": sequence,
            "discount_type": promo.discount_type,
            "base_amount": str(residual),
            "discount_amount": str(discount),
        })
        residual -= discount

    result = {
        "final_amount": str(residual),
        "discount_total": str(gross - residual),
        "applications": applications,
        "coupon_valid": coupon is not None,
    }
    promo_map = {str(p.id): p for p in chosen}
    return result, promo_map, coupon


def compute_preview(
    db: Session,
    company_id: UUID,
    gross_amount: Decimal,
    service_ids: Optional[list] = None,
    product_ids: Optional[list] = None,
    customer_id: Optional[UUID] = None,
    coupon_code: Optional[str] = None,
    subscription_cycle: Optional[int] = None,
    customer_classification: Optional[str] = None,
) -> dict:
    """Preview de descontos — ZERO efeito colateral (nada é persistido).

    422 se coupon_code informado for inválido (esgotado, expirado,
    PER_CUSTOMER de outro cliente, etc.).
    """
    result, _, _ = _compute(
        db=db,
        company_id=company_id,
        gross_amount=gross_amount,
        service_ids=service_ids,
        product_ids=product_ids,
        customer_id=customer_id,
        coupon_code=coupon_code,
        subscription_cycle=subscription_cycle,
        customer_classification=customer_classification,
        for_update=False,
    )
    return result


def effectuate(
    db: Session,
    company_id: UUID,
    payment_id: UUID,
    gross_amount: Decimal,
    coupon_code: Optional[str] = None,
    customer_id: Optional[UUID] = None,
    subscription_cycle: Optional[int] = None,
) -> Optional[dict]:
    """Efetiva descontos no payment.confirmed — revalida tudo.

    Idempotente: DiscountApplications já existentes para o payment → no-op.
    SELECT FOR UPDATE em coupons.uses_count (race de cupom SINGLE_USE).
    Promoção/cupom inválido na revalidação → publica
    promotion.effectuation_failed e NÃO bloqueia o pagamento.
    """
    existing = (
        db.query(DiscountApplication)
        .filter(
            DiscountApplication.company_id == company_id,
            DiscountApplication.payment_id == payment_id,
            DiscountApplication.promotion_id != None,  # noqa: E711 — manuais não contam
        )
        .first()
    )
    if existing:
        logger.info("effectuate: já efetivado payment_id=%s — no-op", payment_id)
        return None

    try:
        result, promo_map, coupon = _compute(
            db=db,
            company_id=company_id,
            gross_amount=gross_amount,
            customer_id=customer_id,
            coupon_code=coupon_code,
            subscription_cycle=subscription_cycle,
            for_update=True,
        )
    except HTTPException as exc:
        # Cupom inválido agora (modo STRICT): registra falha sem bloquear o pagamento
        logger.warning(
            "effectuate: revalidação falhou payment_id=%s detail=%s",
            payment_id, exc.detail,
        )
        _publish(
            "promotion.effectuation_failed", company_id,
            f"promotion.effectuation_failed:{payment_id}",
            {"payment_id": str(payment_id), "company_id": str(company_id),
             "reason": str(exc.detail), "coupon_code": coupon_code},
        )
        return None

    # Cupom válido mas a promoção dele saiu do ar entre preview e confirm
    coupon_applied = coupon is not None and any(
        app["promotion_id"] == str(coupon.promotion_id) for app in result["applications"]
    )
    if coupon and not coupon_applied:
        logger.warning(
            "effectuate: promoção do cupom não está mais elegível payment_id=%s coupon=%s",
            payment_id, coupon.code,
        )
        _publish(
            "promotion.effectuation_failed", company_id,
            f"promotion.effectuation_failed:{payment_id}",
            {"payment_id": str(payment_id), "company_id": str(company_id),
             "reason": "promotion_no_longer_eligible", "coupon_code": coupon.code},
        )
        coupon = None  # não redime cupom de promoção inelegível

    if not result["applications"]:
        return None

    for app_data in result["applications"]:
        promo = promo_map[app_data["promotion_id"]]
        db.add(DiscountApplication(
            company_id=company_id,
            payment_id=payment_id,
            promotion_id=promo.id,
            sequence=app_data["sequence"],
            discount_type=app_data["discount_type"],
            base_amount_at_application=Decimal(app_data["base_amount"]),
            discount_amount=Decimal(app_data["discount_amount"]),
        ))
        promo.uses_count = (promo.uses_count or 0) + 1

    redemption = None
    if coupon:
        coupon.uses_count = (coupon.uses_count or 0) + 1
        if coupon.max_uses is not None and coupon.uses_count >= coupon.max_uses:
            coupon.status = "EXHAUSTED"
        redemption = CouponRedemption(
            company_id=company_id,
            coupon_id=coupon.id,
            customer_id=customer_id,
            payment_id=payment_id,
        )
        db.add(redemption)

    db.commit()

    if coupon and redemption is not None:
        _publish(
            "coupon.redeemed", company_id,
            f"coupon.redeemed:{coupon.id}:{payment_id}",
            {"coupon_id": str(coupon.id), "payment_id": str(payment_id),
             "company_id": str(company_id), "code": coupon.code},
        )

    _publish(
        "promotion.effectuated", company_id,
        f"promotion.effectuated:{payment_id}",
        {
            "payment_id": str(payment_id),
            "company_id": str(company_id),
            "discount_breakdown": result["applications"],
            "promotion_ids": [app["promotion_id"] for app in result["applications"]],
            "coupon_ids": [str(coupon.id)] if coupon else [],
            "final_amount": result["final_amount"],
            "discount_total": result["discount_total"],
        },
    )
    return result


def revert_for_refund(
    db: Session,
    company_id: UUID,
    payment_id: UUID,
    reason: str = "payment.refunded",
) -> None:
    """Reverte aplicações e redenções no payment.refunded (best-effort).

    coupon_reopen_policy: NEVER_REOPEN (default) mantém uses_count;
    REOPEN_ON_REFUND decrementa e reativa cupom EXHAUSTED.
    """
    now = datetime.now(timezone.utc)

    applications = (
        db.query(DiscountApplication)
        .filter(
            DiscountApplication.company_id == company_id,
            DiscountApplication.payment_id == payment_id,
            DiscountApplication.reverted_at == None,  # noqa: E711
        )
        .all()
    )
    for app_row in applications:
        app_row.reverted_at = now
        if app_row.promotion_id:
            promo = (
                db.query(Promotion)
                .filter(Promotion.id == app_row.promotion_id, Promotion.company_id == company_id)
                .first()
            )
            if promo and (promo.uses_count or 0) > 0:
                promo.uses_count = promo.uses_count - 1
            _publish(
                "promotion.application_reverted", company_id,
                f"promotion.application_reverted:{app_row.id}",
                {"application_id": str(app_row.id), "payment_id": str(payment_id),
                 "promotion_id": str(app_row.promotion_id), "company_id": str(company_id)},
            )

    redemptions = (
        db.query(CouponRedemption)
        .filter(
            CouponRedemption.company_id == company_id,
            CouponRedemption.payment_id == payment_id,
            CouponRedemption.reverted_at == None,  # noqa: E711
        )
        .all()
    )
    for redemption in redemptions:
        redemption.reverted_at = now
        redemption.reverted_reason = reason
        coupon = (
            db.query(Coupon)
            .filter(Coupon.id == redemption.coupon_id, Coupon.company_id == company_id)
            .with_for_update()
            .first()
        )
        if coupon and coupon.coupon_reopen_policy == "REOPEN_ON_REFUND":
            coupon.uses_count = max(0, (coupon.uses_count or 0) - 1)
            if coupon.status == "EXHAUSTED":
                coupon.status = "ACTIVE"
        _publish(
            "coupon.redemption_reverted", company_id,
            f"coupon.redemption_reverted:{redemption.id}",
            {"redemption_id": str(redemption.id), "payment_id": str(payment_id),
             "coupon_id": str(redemption.coupon_id), "company_id": str(company_id),
             "reason": reason},
        )

    if applications or redemptions:
        db.commit()
