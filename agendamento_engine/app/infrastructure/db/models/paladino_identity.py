import uuid
from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.infrastructure.db.base import Base, TimestampMixin


class PaladinoIdentity(Base, TimestampMixin):
    """
    Identidade GLOBAL Paladino-wide — Sprint A.

    ATENÇÃO: tabela SEM company_id — quebra o padrão RLS do projeto
    intencionalmente (Risco 1 do plano). RLS está habilitado no banco
    SEM policy permissiva: o acesso é exclusivamente via service layer
    (app/modules/identity/), NUNCA por query direta tenant-scoped.

    CPF segue o padrão PII do Sprint 8 (payments/validators.py):
    cpf_encrypted (Fernet) + cpf_hash (HMAC-SHA256) + cpf_masked.
    Apenas cpf_masked sai em respostas de API.
    """
    __tablename__ = "paladino_identities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # E.164 com '+' (ex.: +5562988887777) — chave canônica da identidade
    phone_e164 = Column(String(20), nullable=False, unique=True)
    # DDD + número local com 9 (ex.: 62988887777)
    phone_national_normalized = Column(String(20), nullable=False, index=True)
    # Variações cruas que já resolveram para esta identidade (ex.: sem o 9)
    possible_aliases = Column(JSONB, nullable=False, default=list)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    cpf_encrypted = Column(Text, nullable=True)
    cpf_hash = Column(String(64), nullable=True)
    cpf_masked = Column(String(14), nullable=True)
