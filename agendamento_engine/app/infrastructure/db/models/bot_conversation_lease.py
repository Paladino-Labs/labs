import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class BotConversationLease(Base):
    """Lease por conversa (company_id + whatsapp_id) que serializa o drain do
    bot WhatsApp — S2.1 (fix da Entrega B).

    Substitui o advisory lock de sessão, que NÃO funciona no pooler
    transaction-mode do Supabase (o backend é reassinado por transação e o lock
    evapora). O claim é atômico via INSERT ON CONFLICT DO UPDATE ... WHERE
    locked_until < now() — uma transação, pooler-agnóstico. A expiração da lease
    dá recuperação de crash (o próximo drain reassume a conversa).
    """
    __tablename__ = "bot_conversation_leases"

    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True)
    whatsapp_id = Column(String(100), primary_key=True)
    # detentor da lease: host:pid:task_id
    locked_by = Column(String(200), nullable=False)
    locked_until = Column(sa.TIMESTAMP(timezone=True), nullable=False)
