"""ConversationService — inbox de atendimento humano (Sprint 2.7).

Opera sobre BotSession (state HUMANO|RESOLVIDA) e ConversationMessage.
Todos os acessos são tenant-scoped: a sessão precisa pertencer ao company_id
do usuário autenticado (isolamento cross-tenant → 404).
"""
import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import (
    BotSession,
    ConversationMessage,
    Customer,
    WhatsAppConnection,
)
from app.modules.whatsapp import sender
from app.modules.whatsapp import messages as wa_messages
from app.modules.whatsapp.bot_service import STATE_HUMANO, STATE_RESOLVIDA

logger = logging.getLogger(__name__)


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _get_session_scoped(db: Session, session_id: UUID, company_id: UUID) -> BotSession:
    """Carrega a BotSession garantindo isolamento por tenant (404 cross-tenant)."""
    session = (
        db.query(BotSession)
        .filter(
            BotSession.id == session_id,
            BotSession.company_id == company_id,
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return session


def _customer_for_session(db: Session, session: BotSession) -> Optional[Customer]:
    ctx = session.context or {}
    customer_id = ctx.get("customer_id")
    if not customer_id:
        return None
    try:
        cid = UUID(str(customer_id))
    except (ValueError, TypeError):
        return None
    return (
        db.query(Customer)
        .filter(Customer.id == cid, Customer.company_id == session.company_id)
        .first()
    )


def _last_message(db: Session, session_id: UUID) -> Optional[ConversationMessage]:
    return (
        db.query(ConversationMessage)
        .filter(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.desc())
        .first()
    )


def _resolve_instance(db: Session, company_id: UUID) -> Optional[str]:
    """Resolve o instance_name da Evolution API do tenant (inverso do webhook)."""
    conn = (
        db.query(WhatsAppConnection)
        .filter(WhatsAppConnection.company_id == company_id)
        .first()
    )
    return conn.instance_name if conn else None


def _to_summary(db: Session, session: BotSession) -> dict:
    customer = _customer_for_session(db, session)
    ctx = session.context or {}
    last = _last_message(db, session.id)
    return {
        "session_id": session.id,
        "state": session.state,
        "phone": session.whatsapp_id,
        "customer_id": getattr(customer, "id", None),
        "customer_name": getattr(customer, "name", None) or ctx.get("customer_name"),
        "last_message": last.content if last else None,
        # Aproximação: quando chegou em HUMANO/RESOLVIDA (updated_at da sessão).
        "escalated_at": getattr(session, "updated_at", None),
    }


# ─── API do serviço ───────────────────────────────────────────────────────────

def list_escalated_conversations(
    db: Session, company_id: UUID, status: Optional[str] = None,
) -> list[dict]:
    """Lista conversas escaladas (HUMANO) ou resolvidas (RESOLVIDA) do tenant."""
    target_state = STATE_RESOLVIDA if status == "resolved" else STATE_HUMANO
    sessions = (
        db.query(BotSession)
        .filter(
            BotSession.company_id == company_id,
            BotSession.state == target_state,
        )
        .order_by(BotSession.updated_at.desc())
        .all()
    )
    return [_to_summary(db, s) for s in sessions]


def get_conversation_detail(db: Session, session_id: UUID, company_id: UUID) -> dict:
    """Detalhe: resumo da sessão + mensagens (ordem crescente)."""
    session = _get_session_scoped(db, session_id, company_id)
    summary = _to_summary(db, session)
    summary["messages"] = get_conversation_messages(db, session_id, company_id)
    return summary


def get_conversation_messages(
    db: Session, session_id: UUID, company_id: UUID,
) -> list[ConversationMessage]:
    """Lista as mensagens da sessão em ordem crescente (valida isolamento)."""
    _get_session_scoped(db, session_id, company_id)
    return (
        db.query(ConversationMessage)
        .filter(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.asc())
        .all()
    )


def reply_to_conversation(
    db: Session, session_id: UUID, company_id: UUID,
    agent_user_id: UUID, content: str,
) -> ConversationMessage:
    """Atendente responde ao cliente: envia via WhatsApp + persiste como AGENT."""
    session = _get_session_scoped(db, session_id, company_id)

    if session.state != STATE_HUMANO:
        raise HTTPException(
            status_code=422,
            detail="A conversa não está em atendimento humano",
        )

    instance = _resolve_instance(db, company_id)
    if not instance:
        raise HTTPException(
            status_code=422,
            detail="Nenhuma conexão WhatsApp configurada para a empresa",
        )

    sender.send_text(instance, session.whatsapp_id, content)

    message = ConversationMessage(
        company_id=company_id,
        session_id=session.id,
        direction="OUTBOUND",
        content=content,
        content_type="TEXT",
        sender_type="AGENT",
        agent_user_id=agent_user_id,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def resolve_conversation(
    db: Session, session_id: UUID, company_id: UUID, agent_user_id: UUID,
) -> BotSession:
    """Encerra o atendimento humano: estado RESOLVIDA + bot reassume na próxima msg."""
    session = _get_session_scoped(db, session_id, company_id)

    if session.state != STATE_HUMANO:
        raise HTTPException(
            status_code=422,
            detail="A conversa não está em atendimento humano",
        )

    session.state = STATE_RESOLVIDA

    # Mensagem de sistema (registro) + envio ao cliente
    db.add(ConversationMessage(
        company_id=company_id,
        session_id=session.id,
        direction="OUTBOUND",
        content=wa_messages.ATENDIMENTO_ENCERRADO,
        content_type="TEXT",
        sender_type="AGENT",
        agent_user_id=agent_user_id,
    ))

    instance = _resolve_instance(db, company_id)
    if instance:
        sender.send_text(instance, session.whatsapp_id, wa_messages.ATENDIMENTO_ENCERRADO)

    db.commit()
    _publish_conversation_resolved(session, company_id, agent_user_id)
    db.refresh(session)
    return session


def _publish_conversation_resolved(
    session: BotSession, company_id: UUID, agent_user_id: UUID,
) -> None:
    """Publica conversation.resolved best-effort — falha nunca derruba o fluxo."""
    from app.infrastructure.event_bus import event_bus, DomainEvent

    ctx = session.context or {}
    try:
        event_bus.publish(DomainEvent(
            event_id=_uuid.uuid4(),
            event_type="conversation.resolved",
            occurred_at=datetime.now(timezone.utc),
            company_id=company_id,
            idempotency_key=f"conversation.resolved:{session.id}",
            actor={"type": "TENANT_USER", "id": str(agent_user_id)},
            payload={
                "session_id": str(session.id),
                "company_id": str(company_id),
                "customer_id": str(ctx.get("customer_id")) if ctx.get("customer_id") else None,
                "phone": session.whatsapp_id,
                "agent_user_id": str(agent_user_id),
            },
        ))
    except Exception:
        logger.exception("falha ao publicar conversation.resolved session_id=%s", session.id)
