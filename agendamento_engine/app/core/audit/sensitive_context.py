"""
Estrutura compartilhada de auditoria para ações sensíveis.

Usado por: invite_user, assign_role, create_manual_adjustment,
           apply_manual_discount_override, export_audit, IntegrationCredential.*.
Nenhum módulo cria seu próprio esquema de audit — todos passam por aqui.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session


class ActionScope(str, Enum):
    OWN = "OWN"                     # apenas recursos próprios do ator
    OWN_CUSTOMERS = "OWN_CUSTOMERS" # clientes atendidos pelo ator
    TENANT = "TENANT"               # qualquer recurso do tenant
    CROSS_TENANT = "CROSS_TENANT"   # apenas PLATFORM_OWNER


@dataclass
class SensitiveAuditContext:
    actor_id: UUID
    actor_role: str
    action: str
    resource_type: str
    resource_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    reason: Optional[str] = None
    amount: Optional[Decimal] = None
    account_id: Optional[UUID] = None
    correlation_id: Optional[UUID] = None
    before_snapshot: Optional[dict] = None
    after_snapshot: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# Actions que exigem reason obrigatório
REASON_REQUIRED: set[str] = {
    "create_manual_adjustment",
    "apply_manual_discount_override",
    "export_audit",
    "test_connection",
}


def record_sensitive_action(
    ctx: SensitiveAuditContext,
    db: Session,
):
    """Grava em audit_logs e retorna o registro criado.

    Levanta ValueError se ctx.action está em REASON_REQUIRED e ctx.reason é None.
    """
    from app.infrastructure.db.models.audit_log import AuditLog

    if ctx.action in REASON_REQUIRED and not ctx.reason:
        raise ValueError(f"reason obrigatório para action={ctx.action!r}")

    def _s(v) -> Optional[str]:
        return str(v) if v is not None else None

    entry = AuditLog(
        audit_id=_s(uuid.uuid4()),
        company_id=_s(ctx.company_id),
        actor_id=_s(ctx.actor_id),
        actor_role=ctx.actor_role,
        action=ctx.action,
        resource_type=ctx.resource_type,
        resource_id=_s(ctx.resource_id),
        amount=ctx.amount,
        account_id=_s(ctx.account_id),
        reason=ctx.reason,
        correlation_id=_s(ctx.correlation_id),
        before_snapshot=ctx.before_snapshot,
        after_snapshot=ctx.after_snapshot,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
    )
    db.add(entry)
    # Flush para obter occurred_at do banco; commit é responsabilidade do chamador.
    db.flush()
    return entry
