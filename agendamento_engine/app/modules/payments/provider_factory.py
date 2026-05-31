"""Factory para resolver o PaymentProvider correto por tenant."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.payments.providers.base import PaymentProvider


def get_payment_provider(company_id: UUID, db: Session) -> PaymentProvider:
    """
    Resolve o PaymentProvider do tenant.
    Atualmente retorna AsaasProvider para todos os tenants.
    """
    from app.modules.payments.providers.asaas import AsaasProvider
    return AsaasProvider(company_id=company_id, db=db)
