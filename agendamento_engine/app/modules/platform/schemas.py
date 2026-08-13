from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class TenantStatusUpdate(BaseModel):
    status: str  # TRIAL | ACTIVE | SUSPENDED | CHURNED
    reason: Optional[str] = None


class ImpersonationGrantCreate(BaseModel):
    company_id: UUID
    mode: str = "READ_ONLY"  # READ_ONLY | ELEVATED
    reason: str
    duration_minutes: int = 30


class FlagUpdate(BaseModel):
    value: Any


class SettingUpdate(BaseModel):
    value: Any


class RedispatchRequest(BaseModel):
    reason: str


class MessageLabelUpdate(BaseModel):
    """Rótulo de UMA mensagem do cliente (S-painel-telemetria).

    Os três campos são opcionais: marcar é opcional por mensagem, e o que está
    certo fica em branco. Todos vazios = apagar o rótulo.

    Os valores aceitos NÃO são um Literal aqui de propósito — o catálogo vive
    em `telemetry_service.EXPECTED_INTENTS`, servido por `GET
    /platform/telemetry/catalog`, para poder crescer durante a leitura sem
    tocar em schema nem em migration.
    """
    understood: Optional[str] = None       # YES | NO | WRONG
    expected_intent: Optional[str] = None  # ver EXPECTED_INTENTS
    note: Optional[str] = None
