"""
BookingSession — sessão unificada de agendamento (todos os canais).

Substitui progressivamente BotSession (WhatsApp) e WebBookingSession (web).
Uma sessão representa um fluxo de agendamento em andamento, independente do canal.

Estados possíveis (FSM):
    IDLE                    — sessão criada, cliente ainda não identificado
    AWAITING_SERVICE        — aguardando seleção de serviço
    AWAITING_PROFESSIONAL   — aguardando seleção de profissional
    AWAITING_DATE           — aguardando seleção de data
    AWAITING_TIME           — aguardando seleção de horário
    AWAITING_CONFIRMATION   — aguardando confirmação final
    CONFIRMING              — em processamento (guard anti-duplicata)
    CONFIRMED               — agendamento criado com sucesso
    AWAITING_CANCEL_CONFIRM — aguardando confirmação de cancelamento
    CANCELLED               — agendamento cancelado
    RESCHEDULING            — em processamento de reagendamento
    ERROR                   — erro irrecuperável (ex: profissional deletado mid-flow)
    EXPIRED                 — TTL esgotado (setado pelo worker de limpeza)

Campos de contexto (JSONB) — snapshot de leitura para UX:
    customer_name, customer_phone, customer_email
    service_id, service_name, service_price, service_duration_minutes
    professional_id, professional_name
    selected_date
    slot_start_at (ISO UTC), slot_end_at (ISO UTC)
    idempotency_key
    managing_appointment_id  — para cancelamento/reagendamento de agendamento existente
    last_listed_services      — [{id, name, price, duration_minutes, row_key}]
    last_listed_professionals — [{id, name, row_key}] (id=null → "qualquer")
    last_listed_dates         — [{date, label, has_availability, row_key}]
    last_listed_slots         — [{start_at, end_at, professional_id, professional_name, row_key}]
"""
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import Column, String, ForeignKey, Index, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class BookingSession(Base, TimestampMixin):
    __tablename__ = "booking_sessions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Empresa dona da sessão
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Canal de origem — determina TTL e comportamento de expiração
    # "web"       → 15 min TTL, retomada via token URL
    # "whatsapp"  → 30 min TTL, reset de contexto ao expirar
    # "admin"     → 2h TTL, sem retomada
    channel = Column(String(20), nullable=False)

    # Estado atual da máquina de estados
    state = Column(String(50), nullable=False, default="IDLE")

    # Dados acumulados durante o fluxo (snapshot — não é source of truth)
    # MutableDict garante que mutações in-place sejam detectadas pelo ORM
    context = Column(
        MutableDict.as_mutable(JSONB(astext_type=String())),
        nullable=False,
        default=dict,
    )

    # Cliente identificado (preenchido em SET_CUSTOMER)
    customer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Agendamento criado (preenchido após CONFIRM bem-sucedido)
    appointment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Token para URL de retomada no canal web (/book/{slug}?t={token})
    # Gerado automaticamente; None para sessões admin/whatsapp que não precisam de URL
    token = Column(
        String(64),
        unique=True,
        nullable=True,
        default=lambda: secrets.token_hex(32),
    )

    # Snapshot do timezone da empresa no momento da criação.
    # Imutável após criação — evita bugs se a empresa alterar o fuso durante a sessão.
    company_timezone = Column(
        String(50),
        nullable=False,
        default="America/Sao_Paulo",
    )

    # Controle de idempotência e auditoria
    last_action    = Column(String(50), nullable=True)
    last_action_at = Column(DateTime(timezone=True), nullable=True)

    # TTL da sessão — resetado a cada ação bem-sucedida
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(minutes=15),
    )

    # Relacionamentos (lazy=select — não carrega automaticamente em queries de lista)
    company  = relationship("Company",  lazy="select", foreign_keys=[company_id])
    customer = relationship("Customer", lazy="select", foreign_keys=[customer_id])

    __table_args__ = (
        # Busca por empresa + canal (ex: listar sessões web ativas de uma empresa)
        Index("ix_booking_sessions_company_channel", "company_id", "channel"),
        # Worker de limpeza: DELETE WHERE expires_at < NOW()
        Index("ix_booking_sessions_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<BookingSession id={self.id} channel={self.channel!r} "
            f"state={self.state!r} expires={self.expires_at}>"
        )
