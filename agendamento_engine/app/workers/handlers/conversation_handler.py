"""Handler de conversas — Sprint 2.7.

conversation.escalated:
  Notifica o OWNER/ADMIN do tenant via CommunicationService que uma conversa
  foi escalada para atendimento humano. Best-effort — falha não impacta o bot.
"""
import logging
from uuid import UUID

from app.core.db_rls import set_rls_context
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.event_bus import event_bus

logger = logging.getLogger(__name__)


def handle_conversation_escalated(event) -> None:
    """Notifica o OWNER do tenant via CommunicationService (template conversation.escalated)."""
    company_id = event.company_id
    payload = event.payload or {}
    session_id = payload.get("session_id")
    phone = payload.get("phone")
    customer_id_str = payload.get("customer_id")

    if not company_id:
        return

    db = SessionLocal()
    try:
        set_rls_context(db, company_id)

        from app.infrastructure.db.models import User, Customer
        from app.modules.communication.service import communication_service
        from app.core.config import settings

        owner = (
            db.query(User)
            .filter(
                User.company_id == company_id,
                User.role == "OWNER",
                User.active == True,  # noqa: E712
            )
            .first()
        )
        if owner is None:
            # ⚠️ Saía em silêncio. Um alerta que não sai e não avisa que não saiu
            # é pior que alerta nenhum: cria a impressão de cobertura. Não há
            # CommunicationLog a gravar aqui (não há destinatário, e o log exige
            # recipient_id), então o rastro é o log de aplicação.
            logger.warning(
                "handle_conversation_escalated: tenant sem OWNER ativo — "
                "escalada NÃO notificada company_id=%s session_id=%s",
                company_id, session_id,
            )
            return

        customer_name = "cliente"
        if customer_id_str:
            try:
                customer = (
                    db.query(Customer)
                    .filter(Customer.id == UUID(str(customer_id_str)))
                    .first()
                )
                if customer is not None:
                    customer_name = customer.name
            except (ValueError, TypeError):
                pass

        panel_url = (settings.FRONTEND_BASE_URL or settings.FRONTEND_URL or "").rstrip("/")

        communication_service.dispatch(
            event_type="conversation.escalated",
            company_id=company_id,
            context={
                "customer_name": customer_name,
                # `phone` é o telefone DO CLIENTE que pediu atendimento (vai no
                # corpo da mensagem); `recipient_phone` é o do OWNER, que é para
                # onde o alerta é entregue. Trocar os dois manda o alerta para o
                # cliente.
                "phone": phone or "",
                "session_id": session_id or "",
                "panel_url": f"{panel_url}/conversations" if panel_url else "",
                "recipient_phone": getattr(owner, "phone", None) or "",
                "recipient_email": getattr(owner, "email", None) or "",
            },
            recipient_id=owner.id,
            recipient_type="OWNER",
            db=db,
        )

    except Exception:
        logger.exception(
            "handle_conversation_escalated: erro (best-effort) session_id=%s",
            session_id,
        )
    finally:
        db.close()


def register_handlers() -> None:
    """Registra handlers de conversas no EventBus global."""
    event_bus.register("conversation.escalated", handle_conversation_escalated)
    logger.info("conversation_handler: handlers registrados")
