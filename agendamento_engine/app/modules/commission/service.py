"""CommissionEngine — cálculo, registro e pagamento de comissões."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import SensitiveAuditContext, record_sensitive_action
from app.infrastructure.db.models.commission import Commission, CommissionPayout, CommissionPolicy


# ── Lookup de política ────────────────────────────────────────────────────────

_PRIORITY = [
    # (tem professional_id, tem service_id) — maior prioridade primeiro
    (True,  True),
    (True,  False),
    (False, True),
    (False, False),
]


def _find_active_policy(
    professional_id: UUID,
    service_id: Optional[UUID],
    company_id: UUID,
    db: Session,
) -> Optional[CommissionPolicy]:
    for has_prof, has_svc in _PRIORITY:
        q = db.query(CommissionPolicy).filter(
            CommissionPolicy.company_id == company_id,
            CommissionPolicy.is_active == True,
        )
        if has_prof:
            q = q.filter(CommissionPolicy.professional_id == professional_id)
        else:
            q = q.filter(CommissionPolicy.professional_id == None)

        if has_svc:
            if service_id is None:
                continue
            q = q.filter(CommissionPolicy.service_id == service_id)
        else:
            q = q.filter(CommissionPolicy.service_id == None)

        policy = q.first()
        if policy:
            return policy
    return None


# ── Cálculo ───────────────────────────────────────────────────────────────────

def calculate_commission(
    professional_id: UUID,
    service_id: Optional[UUID],
    gross_amount: Decimal,
    provider_fee: Decimal,
    operation_type: str,
    appointment_id: Optional[UUID],
    company_id: UUID,
    db: Session,
) -> Optional[Commission]:
    """Calcula e persiste uma Commission com base na política ativa.

    Prioridade de política: (prof+serv) > (prof) > (serv) > (global) > None.
    Retorna None se não houver política ativa — sem erro.
    """
    policy = _find_active_policy(professional_id, service_id, company_id, db)
    if policy is None:
        return None

    if policy.commission_base == "CUSTOM_AMOUNT":
        # Valor fixo — ignora fee policy e gross
        commission_amount = Decimal(str(policy.fixed_amount or 0))
    else:
        # Sempre calcula sobre valor bruto
        gross_commission = gross_amount * (
            Decimal(str(policy.rate)) / Decimal("100")
        )

        fee_policy = policy.commission_fee_policy

        if fee_policy == "BARBERSHOP_PAYS":
            commission_amount = gross_commission

        elif fee_policy == "SPLIT_50_50":
            commission_amount = gross_commission - (provider_fee / Decimal("2"))

        elif fee_policy == "BARBER_PAYS":
            commission_amount = gross_commission - provider_fee

        else:
            # Fallback legado — dados não migrados ou rollback parcial
            # AFTER_FEES → subtrai fee completo (comportamento anterior)
            # BEFORE_FEES e valores desconhecidos → gross (conservador)
            if fee_policy == "AFTER_FEES":
                commission_amount = gross_commission - provider_fee
            else:
                commission_amount = gross_commission

    # Nunca negativo; quantize para centavos
    commission_amount = max(
        Decimal("0"),
        commission_amount
    ).quantize(Decimal("0.01"))

    commission = Commission(
        company_id=company_id,
        professional_id=professional_id,
        policy_id=policy.policy_id,
        appointment_id=appointment_id,
        operation_type=operation_type,
        gross_amount=gross_amount,
        commission_amount=commission_amount,
        status="CALCULATED",
    )
    db.add(commission)
    db.commit()
    db.refresh(commission)
    return commission


# ── Transições de estado ──────────────────────────────────────────────────────

def mark_due(
    commission_id: UUID,
    due_date: date,
    company_id: UUID,
    db: Session,
) -> Commission:
    commission = _get_or_404(commission_id, company_id, db)
    if commission.status != "CALCULATED":
        raise HTTPException(
            status_code=409,
            detail=f"Comissão não está em CALCULATED (status atual: {commission.status})",
        )
    commission.status = "DUE"
    commission.due_date = due_date
    db.commit()
    db.refresh(commission)
    return commission


def reverse_commission(
    commission_id: UUID,
    reason: str,
    actor_id: UUID,
    company_id: UUID,
    db: Session,
) -> Commission:
    if not reason or not reason.strip():
        raise HTTPException(status_code=422, detail="reason é obrigatório para reverter comissão")

    commission = _get_or_404(commission_id, company_id, db)
    if commission.status not in ("CALCULATED", "DUE"):
        raise HTTPException(
            status_code=409,
            detail=f"Só é possível reverter comissões em CALCULATED ou DUE (status atual: {commission.status})",
        )

    commission.status = "REVERSED"

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor_id,
            actor_role="OWNER",
            action="reverse_commission",
            resource_type="Commission",
            resource_id=commission.commission_id,
            company_id=company_id,
            reason=reason,
            amount=commission.commission_amount,
            after_snapshot={"status": "REVERSED"},
        ),
        db,
    )

    db.commit()
    db.refresh(commission)
    return commission


# ── Payout ───────────────────────────────────────────────────────────────────

def create_payout(
    professional_id: UUID,
    commission_ids: List[UUID],
    account_id: UUID,
    actor_id: UUID,
    company_id: UUID,
    db: Session,
) -> CommissionPayout:
    """Cria CommissionPayout, atualiza comissões para PAID e registra Movement+Entry.

    Tudo na mesma transação via FinancialCoreEngine.handle_commission_paid.
    """
    if not commission_ids:
        raise HTTPException(status_code=422, detail="commission_ids não pode ser vazio")

    # Busca e valida todas as comissões
    commissions = (
        db.query(Commission)
        .filter(
            Commission.commission_id.in_(commission_ids),
            Commission.company_id == company_id,
        )
        .all()
    )

    if len(commissions) != len(commission_ids):
        raise HTTPException(status_code=404, detail="Uma ou mais comissões não foram encontradas")

    for c in commissions:
        if c.professional_id != professional_id:
            raise HTTPException(
                status_code=422,
                detail=f"Comissão {c.commission_id} não pertence ao profissional informado",
            )
        if c.status not in ("CALCULATED", "DUE"):
            raise HTTPException(
                status_code=409,
                detail=f"Comissão {c.commission_id} não está em CALCULATED ou DUE (status: {c.status})",
            )

    total_amount = sum(c.commission_amount for c in commissions)

    now = datetime.now(timezone.utc)

    payout = CommissionPayout(
        company_id=company_id,
        professional_id=professional_id,
        total_amount=total_amount,
        account_id=account_id,
        status="PAID",
        paid_at=now,
        created_by=actor_id,
    )
    db.add(payout)
    db.flush()

    for c in commissions:
        c.status = "PAID"
        c.paid_at = now
        c.payout_id = payout.payout_id

    # Registra Movement OUTFLOW + Entry COMISSAO
    from app.modules.financial_core import service as financial_service
    financial_service.handle_commission_paid(
        payout_id=payout.payout_id,
        amount=total_amount,
        account_id=account_id,
        professional_id=professional_id,
        company_id=company_id,
        db=db,
    )

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor_id,
            actor_role="OWNER",
            action="create_payout",
            resource_type="CommissionPayout",
            resource_id=payout.payout_id,
            company_id=company_id,
            reason=f"Payout de {len(commissions)} comissão(ões) para profissional {professional_id}",
            amount=total_amount,
            account_id=account_id,
            after_snapshot={
                "professional_id": str(professional_id),
                "commission_count": len(commissions),
                "total_amount": str(total_amount),
                "status": "PAID",
            },
        ),
        db,
    )

    db.commit()
    db.refresh(payout)

    # Emite evento best-effort após commit
    try:
        from app.infrastructure.event_bus import DomainEvent, event_bus
        event_bus.publish(DomainEvent(
            event_id=uuid.uuid4(),
            event_type="commission.payout_created",
            occurred_at=now,
            company_id=company_id,
            idempotency_key=f"commission.payout_created:{payout.payout_id}",
            actor={"type": "USER", "id": str(actor_id)},
            payload={
                "payout_id": str(payout.payout_id),
                "professional_id": str(professional_id),
                "total_amount": str(total_amount),
            },
        ))
    except Exception:
        pass

    return payout


# ── Queries ───────────────────────────────────────────────────────────────────

def list_policies(company_id: UUID, db: Session) -> list[CommissionPolicy]:
    return (
        db.query(CommissionPolicy)
        .filter(CommissionPolicy.company_id == company_id)
        .order_by(CommissionPolicy.created_at)
        .all()
    )


def create_policy(
    company_id: UUID,
    professional_id: Optional[UUID],
    service_id: Optional[UUID],
    commission_base: str,
    commission_fee_policy: str,
    rate: Optional[Decimal],
    fixed_amount: Optional[Decimal],
    db: Session,
) -> CommissionPolicy:
    policy = CommissionPolicy(
        company_id=company_id,
        professional_id=professional_id,
        service_id=service_id,
        commission_base=commission_base,
        commission_fee_policy=commission_fee_policy,
        rate=rate,
        fixed_amount=fixed_amount,
        is_active=True,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def update_policy(
    policy_id: UUID,
    company_id: UUID,
    db: Session,
    **kwargs,
) -> CommissionPolicy:
    policy = _get_policy_or_404(policy_id, company_id, db)
    for k, v in kwargs.items():
        if v is not None:
            setattr(policy, k, v)
    policy.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(policy)
    return policy


def delete_policy(policy_id: UUID, company_id: UUID, db: Session) -> CommissionPolicy:
    policy = _get_policy_or_404(policy_id, company_id, db)
    policy.is_active = False
    policy.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(policy)
    return policy


def list_commissions(
    company_id: UUID,
    db: Session,
    professional_id: Optional[UUID] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[Commission]:
    q = db.query(Commission).filter(Commission.company_id == company_id)
    if professional_id:
        q = q.filter(Commission.professional_id == professional_id)
    if status:
        q = q.filter(Commission.status == status)
    if date_from:
        q = q.filter(Commission.created_at >= date_from)
    if date_to:
        q = q.filter(Commission.created_at <= date_to)
    return q.order_by(Commission.created_at.desc()).all()


def list_payouts(company_id: UUID, db: Session) -> list[CommissionPayout]:
    return (
        db.query(CommissionPayout)
        .filter(CommissionPayout.company_id == company_id)
        .order_by(CommissionPayout.created_at.desc())
        .all()
    )


def get_payout(payout_id: UUID, company_id: UUID, db: Session) -> CommissionPayout:
    payout = (
        db.query(CommissionPayout)
        .filter(CommissionPayout.payout_id == payout_id, CommissionPayout.company_id == company_id)
        .first()
    )
    if not payout:
        raise HTTPException(status_code=404, detail="Payout não encontrado")
    return payout


# ── Helpers internos ──────────────────────────────────────────────────────────

def _get_or_404(commission_id: UUID, company_id: UUID, db: Session) -> Commission:
    commission = (
        db.query(Commission)
        .filter(Commission.commission_id == commission_id, Commission.company_id == company_id)
        .first()
    )
    if not commission:
        raise HTTPException(status_code=404, detail="Comissão não encontrada")
    return commission


def _get_policy_or_404(policy_id: UUID, company_id: UUID, db: Session) -> CommissionPolicy:
    policy = (
        db.query(CommissionPolicy)
        .filter(CommissionPolicy.policy_id == policy_id, CommissionPolicy.company_id == company_id)
        .first()
    )
    if not policy:
        raise HTTPException(status_code=404, detail="Política de comissão não encontrada")
    return policy
