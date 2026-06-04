import uuid

import sqlalchemy as sa
from sqlalchemy import Column, String, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.infrastructure.db.base import Base


class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"

    credential_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    provider = Column(
        SAEnum(
            "WHATSAPP_EVOLUTION",
            "WHATSAPP_META",
            "SMTP",
            "ASAAS",
            "PAGSEGURO",
            name="credentialprovider",
            create_type=False,
        ),
        nullable=False,
    )
    label = Column(String(100), nullable=True)

    # Segredo criptografado em repouso via Fernet.  Nunca retornar em API.
    secret_encrypted = Column(Text, nullable=False)
    masked_preview = Column(String(20), nullable=True)

    # Configuração não-secreta por provider (retornada em API).
    config = Column(JSONB, nullable=False, default=dict)

    status = Column(
        SAEnum("ACTIVE", "REVOKED", name="credentialstatus", create_type=False),
        nullable=False,
        default="ACTIVE",
    )

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    revoked_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    revoked_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
