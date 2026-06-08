"""Handlers para eventos de pacotes — Sprint 14.

payment.confirmed:
  Busca PackagePurchase por payment_id.
  Se encontrar (PENDING_PAYMENT): chama package_service.activate().
  best-effort — falha não impacta o pagamento confirmado.

payment.refunded:
  Busca PackagePurchase ACTIVE por payment_id.
  Se encontrar: CustomerCredit REVOKED + Commission REVERSED.
  best-effort.
"""
import logging
from uuid import UUID

from app.infrastructure.db.session import SessionLocal
from app.core.db_rls import set_rls_context
from app.infrastructure.event_bus import event_bus

logger = logging.getLogger(__name__)


def handle_payment_confirmed_package(event) -> None:
    """Ativa PackagePurchase se payment_id corresponde a uma compra pendente."""
    payment_id_str = event.payload.get("payment_id")
    company_id = event.company_id

    if not payment_id_str or not company_id:
        return

    db = SessionLocal()
    try:
        set_rls_context(db, company_id)

        from app.infrastructure.db.models.package import PackagePurchase
        pkg_purchase = (
            db.query(PackagePurchase)
            .filter(
                PackagePurchase.company_id == company_id,
                PackagePurchase.payment_id == UUID(payment_id_str),
                PackagePurchase.status == "PENDING_PAYMENT",
            )
            .first()
        )

        if not pkg_purchase:
            return

        from app.modules.packages import service as package_service
        package_service.activate(
            purchase_id=pkg_purchase.purchase_id,
            company_id=company_id,
            db=db,
        )

        logger.info(
            "handle_payment_confirmed_package: ativado purchase_id=%s payment_id=%s",
            pkg_purchase.purchase_id, payment_id_str,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "handle_payment_confirmed_package: erro (best-effort) payment_id=%s event_id=%s",
            payment_id_str, event.event_id,
        )
    finally:
        db.close()


def handle_payment_refunded_package(event) -> None:
    """Revoga crédito e reverte comissão quando pagamento de pacote é estornado."""
    payment_id_str = event.payload.get("payment_id")
    company_id = event.company_id

    if not payment_id_str or not company_id:
        return

    db = SessionLocal()
    try:
        set_rls_context(db, company_id)

        from app.modules.packages import service as package_service
        package_service.revoke_for_refund(
            payment_id=UUID(payment_id_str),
            company_id=company_id,
            db=db,
        )

        logger.info(
            "handle_payment_refunded_package: processado payment_id=%s event_id=%s",
            payment_id_str, event.event_id,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "handle_payment_refunded_package: erro (best-effort) payment_id=%s event_id=%s",
            payment_id_str, event.event_id,
        )
    finally:
        db.close()


def register_handlers() -> None:
    """Registra handlers de pacotes no EventBus global."""
    event_bus.register("payment.confirmed", handle_payment_confirmed_package)
    event_bus.register("payment.refunded", handle_payment_refunded_package)
    logger.info("package_handler: handlers registrados")
