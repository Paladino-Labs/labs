"""Factory para resolver o PaymentProvider correto por tenant.

Ordem de resolução:
  1. IntegrationCredential provider=PAGSEGURO + status=ACTIVE → PagSeguroProvider
  2. IntegrationCredential provider=ASAAS    + status=ACTIVE → AsaasProvider
  3. settings.ASAAS_API_KEY                                  → AsaasProvider (fallback global)
  4. AsaasError: nenhum provider disponível
"""
import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.modules.payments.providers.base import PaymentProvider

logger = logging.getLogger(__name__)


def get_payment_provider(company_id: UUID, db: Session) -> PaymentProvider:
    """Resolve o PaymentProvider ativo para o tenant."""
    # 1. Verificar credential PagSeguro
    try:
        from app.infrastructure.db.models.integration_credential import IntegrationCredential
        with db.begin_nested():
            pagseguro_cred = (
                db.query(IntegrationCredential)
                .filter(
                    IntegrationCredential.company_id == company_id,
                    IntegrationCredential.provider == "PAGSEGURO",
                    IntegrationCredential.status == "ACTIVE",
                )
                .first()
            )
        if pagseguro_cred:
            from app.modules.payments.providers.pagseguro import PagSeguroProvider
            return PagSeguroProvider(company_id=company_id, db=db)
    except Exception as exc:
        logger.warning(
            "pagseguro_provider_resolve_failed",
            extra={"company_id": str(company_id), "error": str(exc)},
        )

    # 2 + 3. AsaasProvider (verifica credential + fallback global)
    from app.modules.payments.providers.asaas import AsaasProvider
    return AsaasProvider(company_id=company_id, db=db)
