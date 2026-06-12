import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class PortalCredential(Base):
    """
    Credencial do Portal do Cliente — Sprint D.

    Tabela GLOBAL (sem company_id): vinculada à PaladinoIdentity, RLS
    habilitado SEM policy no banco — acesso exclusivamente via service
    layer (app/modules/portal/).

    password_hash nullable: cliente pode autenticar apenas via magic link.
    """
    __tablename__ = "portal_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paladino_identities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    must_change_password = Column(Boolean, nullable=False, default=False)
    last_login_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PortalMagicToken(Base):
    """
    Token de magic link — Sprint D. Armazena APENAS o SHA-256 do token
    (cru nunca persiste — mesmo padrão do manage_token do Sprint B).
    Single-use: used_at preenchido na verificação.
    """
    __tablename__ = "portal_magic_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paladino_identities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(sa.TIMESTAMP(timezone=True), nullable=False)
    used_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
