"""Inbox de atendimento humano — /conversations (Sprint 2.7).

RBAC: OWNER/ADMIN/OPERATOR em todos os endpoints.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.infrastructure.db.session import get_db
from app.modules.conversations import service as conversations_service
from app.modules.conversations.schemas import (
    ConversationDetailOut,
    ConversationMessageOut,
    ConversationOut,
    ReplyRequest,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])

_INBOX_ROLES = ("OWNER", "ADMIN", "OPERATOR")


@router.get("", response_model=List[ConversationOut])
def list_conversations(
    status: str = Query("escalated", pattern="^(escalated|resolved)$"),
    current_user=Depends(require_role(*_INBOX_ROLES)),
    db: Session = Depends(get_db),
):
    return conversations_service.list_escalated_conversations(
        db, current_user.company_id, status=status,
    )


@router.get("/{session_id}", response_model=ConversationDetailOut)
def get_conversation(
    session_id: UUID,
    current_user=Depends(require_role(*_INBOX_ROLES)),
    db: Session = Depends(get_db),
):
    return conversations_service.get_conversation_detail(
        db, session_id, current_user.company_id,
    )


@router.get("/{session_id}/messages", response_model=List[ConversationMessageOut])
def get_conversation_messages(
    session_id: UUID,
    current_user=Depends(require_role(*_INBOX_ROLES)),
    db: Session = Depends(get_db),
):
    return conversations_service.get_conversation_messages(
        db, session_id, current_user.company_id,
    )


@router.post("/{session_id}/reply", response_model=ConversationMessageOut)
def reply_to_conversation(
    session_id: UUID,
    body: ReplyRequest,
    current_user=Depends(require_role(*_INBOX_ROLES)),
    db: Session = Depends(get_db),
):
    return conversations_service.reply_to_conversation(
        db, session_id, current_user.company_id,
        agent_user_id=current_user.id, content=body.content,
    )


@router.patch("/{session_id}/resolve", response_model=ConversationOut)
def resolve_conversation(
    session_id: UUID,
    current_user=Depends(require_role(*_INBOX_ROLES)),
    db: Session = Depends(get_db),
):
    conversations_service.resolve_conversation(
        db, session_id, current_user.company_id, agent_user_id=current_user.id,
    )
    return conversations_service._to_summary(
        db, conversations_service._get_session_scoped(
            db, session_id, current_user.company_id,
        ),
    )
