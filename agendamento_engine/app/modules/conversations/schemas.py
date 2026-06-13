from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ConversationMessageOut(BaseModel):
    id: UUID
    session_id: UUID
    direction: str
    content: str
    content_type: str
    sender_type: str
    agent_user_id: Optional[UUID] = None
    whatsapp_message_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    """Resumo de uma conversa escalada/resolvida para a listagem do inbox."""
    session_id: UUID
    state: str
    phone: str
    customer_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    last_message: Optional[str] = None
    escalated_at: Optional[datetime] = None


class ConversationDetailOut(ConversationOut):
    messages: list[ConversationMessageOut] = Field(default_factory=list)


class ReplyRequest(BaseModel):
    content: str = Field(..., min_length=1)
