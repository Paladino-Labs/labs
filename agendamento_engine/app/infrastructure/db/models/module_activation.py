import uuid
import enum

import sqlalchemy as sa
from sqlalchemy import Column, Boolean, ForeignKey, Enum as SAEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class ModuleName(str, enum.Enum):
    ESTOQUE = "ESTOQUE"
    COMISSOES = "COMISSOES"
    PACOTES = "PACOTES"
    ASSINATURAS = "ASSINATURAS"
    PROMOCOES = "PROMOCOES"
    CRM = "CRM"
    NPS = "NPS"
    FILA = "FILA"
    BOT_WHATSAPP = "BOT_WHATSAPP"
    LINK_PUBLICO = "LINK_PUBLICO"


class ModuleActivation(Base):
    __tablename__ = "module_activations"
    __table_args__ = (
        UniqueConstraint("company_id", "module_name", name="uq_module_activation"),
    )

    activation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    module_name = Column(
        SAEnum(
            "ESTOQUE", "COMISSOES", "PACOTES", "ASSINATURAS", "PROMOCOES",
            "CRM", "NPS", "FILA", "BOT_WHATSAPP", "LINK_PUBLICO",
            name="modulename",
            create_type=False,
        ),
        nullable=False,
    )
    is_active = Column(Boolean, nullable=False, default=False)
    activated_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    deactivated_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    activated_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
