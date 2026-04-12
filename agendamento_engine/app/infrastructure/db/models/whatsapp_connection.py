import uuid
from sqlalchemy import Column, String, ForeignKey, Text
from sqlalchemy import TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base


class WhatsAppConnection(Base):
    """
    Conexão WhatsApp de uma empresa com a Evolution API.
    Uma empresa pode ter no máximo 1 conexão ativa.

    Status lifecycle:
        DISCONNECTED → CONNECTING → CONNECTED
             ↑              │              │
             └──────────────┘  (QR timeout)│
             ↑                             │
             └─────────────────────────────┘ (desconexão / ERROR)

    Campos:
      - instance_name  : nome da instância na Evolution API (ex: "paladino-abc12345")
      - qr_code        : base64 do QR sem prefixo "data:image/" — TTL ~60s
      - qr_generated_at: controla expiração do QR no frontend
      - disconnect_reason: motivo de desconexão para exibição no painel
    """
    __tablename__ = "whatsapp_connections"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        unique=True,        # 1 conexão por empresa
    )
    # Nome da instância na Evolution API — determinístico: "paladino-{company_id[:8]}"
    instance_name = Column(String(100), nullable=False, unique=True)

    # DISCONNECTED | CONNECTING | CONNECTED | ERROR
    status = Column(String(20), nullable=False, default="DISCONNECTED", server_default="DISCONNECTED")

    # Preenchido após conexão bem-sucedida
    phone_number = Column(String(30), nullable=True)

    # QR Code base64 (sem prefixo "data:image/png;base64,")
    qr_code = Column(Text, nullable=True)
    qr_generated_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Timestamp da última conexão bem-sucedida
    connected_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Motivo da desconexão (session_timeout, logout, connection_lost, ...)
    disconnect_reason = Column(String(200), nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    company = relationship("Company")
