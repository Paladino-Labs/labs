"""CrmService — Sprint H.

compute_customer_metrics():        métricas dinâmicas, ZERO persistência
classify_customer():               determinístico, regras em ordem de prioridade
recompute_all_classifications():   worker — append em customer_classifications
get_customer_insights():           heurísticas SEM ML; exibição interna apenas
get_crm_alerts():                  dashboard de risco para OWNER/ADMIN

Convenções:
  - "visita" = Appointment COMPLETED (não existe CONFIRMED no enum)
  - gasto    = Payment CONFIRMED (net_charged_amount)
  - FK de cliente em appointments chama-se client_id
  - filtros de status/escopo aplicados em Python sobre o resultado da query
    company+customer — determinístico e compatível com o FakeDB dos testes
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import (
    Appointment, AppointmentService, CrmConfig, Customer,
    CustomerClassification, PackagePurchase, Payment, StockMovement,
)

logger = logging.getLogger(__name__)

CLASSIFICATIONS = ("NOVO", "FREQUENTE", "VIP", "EM_RISCO", "RECUPERADO", "REGULAR")

_RECOMPUTE_MAX_AGE_HOURS = 24
_BATCH_COMMIT_SIZE = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Config ────────────────────────────────────────────────────────────────────

def get_or_create_config(db: Session, company_id: UUID, commit: bool = True) -> CrmConfig:
    config = (
        db.query(CrmConfig)
        .filter(CrmConfig.company_id == company_id)
        .first()
    )
    if config:
        return config
    config = CrmConfig(company_id=company_id)
    db.add(config)
    if commit:
        db.commit()
        db.refresh(config)
    return config


# ── Métricas ──────────────────────────────────────────────────────────────────

def compute_customer_metrics(db: Session, customer_id: UUID, company_id: UUID) -> dict:
    """Calcula métricas do cliente sem persistir nada.

    Retorna:
      visit_count, last_visit_at, first_visit_at, visit_dates,
      avg_frequency_days, avg_ticket, total_spend, days_since_last_visit,
      preferred_service_id, preferred_professional_id
    """
    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.company_id == company_id,
            Appointment.client_id == customer_id,
        )
        .order_by(Appointment.start_at.asc())
        .all()
    )
    completed = [a for a in appointments if a.status == "COMPLETED"]
    visit_dates = sorted(a.start_at for a in completed)
    visit_count = len(visit_dates)
    first_visit_at = visit_dates[0] if visit_dates else None
    last_visit_at = visit_dates[-1] if visit_dates else None

    avg_frequency_days: Optional[float] = None
    if visit_count >= 2:
        span_days = (last_visit_at - first_visit_at).total_seconds() / 86400
        avg_frequency_days = span_days / (visit_count - 1)

    days_since_last_visit: Optional[int] = None
    if last_visit_at is not None:
        days_since_last_visit = (_now() - last_visit_at).days

    payments = (
        db.query(Payment)
        .filter(
            Payment.company_id == company_id,
            Payment.customer_id == customer_id,
        )
        .all()
    )
    confirmed = [p for p in payments if p.status == "CONFIRMED"]
    total_spend = sum(
        (Decimal(str(p.net_charged_amount)) for p in confirmed), Decimal("0")
    )
    avg_ticket = (total_spend / len(confirmed)) if confirmed else Decimal("0")

    service_counter: Counter = Counter()
    professional_counter: Counter = Counter()
    for a in completed:
        if a.professional_id:
            professional_counter[a.professional_id] += 1
        for s in (a.services or []):
            if s.service_id:
                service_counter[s.service_id] += 1

    preferred_service_id = service_counter.most_common(1)[0][0] if service_counter else None
    preferred_professional_id = (
        professional_counter.most_common(1)[0][0] if professional_counter else None
    )

    return {
        "visit_count": visit_count,
        "first_visit_at": first_visit_at,
        "last_visit_at": last_visit_at,
        "visit_dates": visit_dates,
        "avg_frequency_days": avg_frequency_days,
        "avg_ticket": float(avg_ticket),
        "total_spend": float(total_spend),
        "days_since_last_visit": days_since_last_visit,
        "preferred_service_id": preferred_service_id,
        "preferred_professional_id": preferred_professional_id,
    }


def _metrics_snapshot(metrics: dict) -> dict:
    """Subconjunto JSON-serializável persistido em metrics_snapshot."""
    return {
        "visit_count": metrics["visit_count"],
        "avg_ticket": metrics["avg_ticket"],
        "days_since_last_visit": metrics["days_since_last_visit"],
        "avg_frequency_days": metrics["avg_frequency_days"],
        "total_spend": metrics["total_spend"],
    }


# ── Classificação ─────────────────────────────────────────────────────────────

def _is_at_risk(metrics: dict, config: CrmConfig) -> bool:
    """EM_RISCO: sem operação > max(risk_min_days, avg_frequency × risk_multiplier)."""
    if metrics.get("last_visit_at") is None:
        return False
    threshold = float(config.risk_min_days)
    avg_frequency = metrics.get("avg_frequency_days")
    if avg_frequency:
        threshold = max(threshold, avg_frequency * float(config.risk_multiplier))
    return metrics["days_since_last_visit"] > threshold


def classify_customer(
    metrics: dict,
    config: CrmConfig,
    previous_classification: Optional[str] = None,
) -> str:
    """Determinístico — regras em ordem de prioridade (maior ganha):

    1. VIP        — visit_count >= vip_min_visits E total_spend >= vip_min_spend
    2. RECUPERADO — era EM_RISCO e voltou (não está mais em risco, com visita)
    3. EM_RISCO   — sem operação > max(risk_min_days, avg_freq × multiplier)
    4. FREQUENTE  — >= frequent_min_visits nos últimos frequent_period_months
    5. NOVO       — 1ª visita há <= new_customer_days
    6. REGULAR    — fallback
    """
    now = _now()
    visit_count = metrics.get("visit_count", 0)

    if (
        visit_count >= config.vip_min_visits
        and Decimal(str(metrics.get("total_spend", 0))) >= Decimal(str(config.vip_min_spend))
    ):
        return "VIP"

    at_risk = _is_at_risk(metrics, config)

    if previous_classification == "EM_RISCO" and visit_count >= 1 and not at_risk:
        return "RECUPERADO"

    if at_risk:
        return "EM_RISCO"

    period_start = now - timedelta(days=30 * config.frequent_period_months)
    recent_visits = [d for d in metrics.get("visit_dates", []) if d >= period_start]
    if len(recent_visits) >= config.frequent_min_visits:
        return "FREQUENTE"

    first_visit_at = metrics.get("first_visit_at")
    if (
        visit_count >= 1
        and first_visit_at is not None
        and first_visit_at >= now - timedelta(days=config.new_customer_days)
    ):
        return "NOVO"

    return "REGULAR"


def get_latest_classification(
    db: Session, customer_id: UUID, company_id: UUID
) -> Optional[CustomerClassification]:
    return (
        db.query(CustomerClassification)
        .filter(
            CustomerClassification.company_id == company_id,
            CustomerClassification.customer_id == customer_id,
        )
        .order_by(CustomerClassification.computed_at.desc())
        .first()
    )


# ── Recomputação (worker) ─────────────────────────────────────────────────────

def recompute_all_classifications(db: Session, company_id: Optional[UUID] = None) -> int:
    """Itera customers ativos e insere nova CustomerClassification quando:
      - classificação mudou vs. a última, OU
      - última recomputação tem mais de 24h.
    Idempotente dentro da janela de 24h. Commit em lote a cada 100 customers.
    Retorna o número de classificações inseridas.
    """
    query = db.query(Customer).filter(Customer.active == True)  # noqa: E712
    if company_id is not None:
        query = query.filter(Customer.company_id == company_id)
    customers = query.all()

    configs: dict = {}
    inserted = 0
    processed = 0
    now = _now()

    for customer in customers:
        cid = customer.company_id
        if cid not in configs:
            configs[cid] = get_or_create_config(db, cid, commit=False)
        config = configs[cid]

        metrics = compute_customer_metrics(db, customer.id, cid)
        last = get_latest_classification(db, customer.id, cid)
        previous = last.classification if last else None
        new_classification = classify_customer(
            metrics, config, previous_classification=previous
        )

        stale = last is None or (now - last.computed_at) > timedelta(
            hours=_RECOMPUTE_MAX_AGE_HOURS
        )
        if last is None or last.classification != new_classification or stale:
            db.add(CustomerClassification(
                company_id=cid,
                customer_id=customer.id,
                classification=new_classification,
                computed_at=now,
                metrics_snapshot=_metrics_snapshot(metrics),
            ))
            inserted += 1

        processed += 1
        if processed % _BATCH_COMMIT_SIZE == 0:
            db.commit()

    db.commit()
    logger.info(
        "crm_recompute: %d customers processados, %d classificações inseridas%s",
        processed, inserted,
        f" (company_id={company_id})" if company_id else " (multi-tenant)",
    )
    return inserted


# ── Insights heurísticos ──────────────────────────────────────────────────────

_RESCHEDULE_WINDOW_DAYS = 7
_PACKAGE_LOOKBACK_DAYS = 60
_PACKAGE_MIN_VISITS = 3
_CHURN_MEDIUM_FACTOR = 1.5


def get_customer_insights(db: Session, customer_id: UUID, company_id: UUID) -> dict:
    """Insights determinísticos — APENAS exibição interna no painel.
    SEM ML; SEM sugestão automática ao cliente sem trigger manual.
    """
    metrics = compute_customer_metrics(db, customer_id, company_id)
    latest = get_latest_classification(db, customer_id, company_id)
    classification = latest.classification if latest else None

    # churn_risk
    if classification == "EM_RISCO":
        churn_risk = "HIGH"
    elif (
        metrics["days_since_last_visit"] is not None
        and metrics["avg_frequency_days"]
        and metrics["days_since_last_visit"]
        > metrics["avg_frequency_days"] * _CHURN_MEDIUM_FACTOR
    ):
        churn_risk = "MEDIUM"
    else:
        churn_risk = "LOW"

    # janela de retorno esperada
    estimated_return_window = None
    if metrics["last_visit_at"] is not None and metrics["avg_frequency_days"]:
        estimated_return_window = metrics["last_visit_at"] + timedelta(
            days=metrics["avg_frequency_days"]
        )

    suggestions = []
    now = _now()

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.company_id == company_id,
            Appointment.client_id == customer_id,
        )
        .order_by(Appointment.start_at.desc())
        .all()
    )

    # RESCHEDULE: cancelou há < 7 dias e não remarcou (nenhum SCHEDULED)
    recently_cancelled = [
        a for a in appointments
        if a.status == "CANCELLED"
        and (a.cancelled_at or a.start_at) is not None
        and (a.cancelled_at or a.start_at) >= now - timedelta(days=_RESCHEDULE_WINDOW_DAYS)
    ]
    has_active_scheduled = any(
        a.status in ("SCHEDULED", "IN_PROGRESS") for a in appointments
    )
    if recently_cancelled and not has_active_scheduled:
        suggestions.append({
            "type": "RESCHEDULE",
            "reason": "Cancelou recentemente sem remarcar",
        })

    # PACKAGE: mesmo service_id >= 3x nos últimos 60 dias e sem pacote ativo
    package_suggestion = _suggest_package(db, customer_id, company_id, appointments, now)
    if package_suggestion:
        suggestions.append(package_suggestion)

    # PRODUCT: produto mais vendido para o serviço preferido do cliente
    product_suggestion = _suggest_product(db, company_id, metrics["preferred_service_id"])
    if product_suggestion:
        suggestions.append(product_suggestion)

    return {
        "churn_risk": churn_risk,
        "estimated_return_window": estimated_return_window,
        "classification": classification,
        "metrics": _metrics_snapshot(metrics),
        "suggestions": suggestions,
    }


def _suggest_package(
    db: Session,
    customer_id: UUID,
    company_id: UUID,
    appointments: list,
    now: datetime,
) -> Optional[dict]:
    lookback = now - timedelta(days=_PACKAGE_LOOKBACK_DAYS)
    service_counter: Counter = Counter()
    for a in appointments:
        if a.status != "COMPLETED" or a.start_at < lookback:
            continue
        for s in (a.services or []):
            if s.service_id:
                service_counter[s.service_id] += 1

    if not service_counter:
        return None
    top_service_id, count = service_counter.most_common(1)[0]
    if count < _PACKAGE_MIN_VISITS:
        return None

    # Já tem pacote ativo cobrindo esse serviço? (purchase ACTIVE → crédito ativo)
    purchases = (
        db.query(PackagePurchase)
        .filter(
            PackagePurchase.company_id == company_id,
            PackagePurchase.customer_id == customer_id,
        )
        .all()
    )
    for p in purchases:
        if p.status != "ACTIVE":
            continue
        pkg = getattr(p, "package", None)
        # pacote sem service_id é genérico — cobre qualquer serviço
        if pkg is not None and (pkg.service_id is None or pkg.service_id == top_service_id):
            return None

    return {
        "type": "PACKAGE",
        "service_id": top_service_id,
        "reason": (
            f"Usou este serviço {count} vezes nos últimos "
            f"{_PACKAGE_LOOKBACK_DAYS} dias sem pacote ativo"
        ),
    }


def _suggest_product(
    db: Session, company_id: UUID, preferred_service_id: Optional[UUID]
) -> Optional[dict]:
    """Produto mais vendido (StockMovement VENDA) em operações do serviço
    preferido do cliente — perfil de consumo similar."""
    if preferred_service_id is None:
        return None

    service_rows = (
        db.query(AppointmentService)
        .join(Appointment, AppointmentService.appointment_id == Appointment.id)
        .filter(
            Appointment.company_id == company_id,
            AppointmentService.service_id == preferred_service_id,
        )
        .all()
    )
    appointment_ids = {r.appointment_id for r in service_rows}
    if not appointment_ids:
        return None

    movements = (
        db.query(StockMovement)
        .filter(
            StockMovement.company_id == company_id,
            StockMovement.movement_type == "VENDA",
        )
        .all()
    )
    product_counter: Counter = Counter()
    for m in movements:
        if m.movement_type == "VENDA" and m.source_id in appointment_ids:
            product_counter[m.product_id] += 1

    if not product_counter:
        return None
    top_product_id, _ = product_counter.most_common(1)[0]
    return {
        "type": "PRODUCT",
        "product_id": top_product_id,
        "reason": "Clientes com perfil similar adquirem este produto",
    }


# ── Dashboard de alertas ──────────────────────────────────────────────────────

_AT_RISK_TOP_N = 10


def get_crm_alerts(db: Session, company_id: UUID) -> dict:
    """Dashboard para OWNER/ADMIN — contagens sobre a classificação ATUAL
    (linha mais recente por customer)."""
    rows = (
        db.query(CustomerClassification)
        .filter(CustomerClassification.company_id == company_id)
        .order_by(CustomerClassification.computed_at.desc())
        .all()
    )
    latest: dict = {}
    for r in rows:
        latest.setdefault(r.customer_id, r)  # primeira ocorrência = mais recente

    now = _now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    current = list(latest.values())
    at_risk = [r for r in current if r.classification == "EM_RISCO"]
    at_risk_sorted = sorted(
        at_risk,
        key=lambda r: (r.metrics_snapshot or {}).get("days_since_last_visit") or 0,
        reverse=True,
    )

    return {
        "at_risk_count": len(at_risk),
        "at_risk_customers": [
            {
                "customer_id": r.customer_id,
                "days_since_last_visit": (r.metrics_snapshot or {}).get("days_since_last_visit"),
                "computed_at": r.computed_at,
            }
            for r in at_risk_sorted[:_AT_RISK_TOP_N]
        ],
        "new_this_month": sum(
            1 for r in current
            if r.classification == "NOVO" and r.computed_at >= month_start
        ),
        "vip_count": sum(1 for r in current if r.classification == "VIP"),
        "recovered_this_week": sum(
            1 for r in current
            if r.classification == "RECUPERADO" and r.computed_at >= week_ago
        ),
    }
