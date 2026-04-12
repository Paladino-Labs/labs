"""
Schemas do módulo WhatsApp.

- EvolutionWebhookPayload: payload recebido da Evolution API via webhook
- ConnectionResponse:      estado da conexão retornado ao painel
- QRCodeResponse:          QR Code para scan
- ConnectRequest:          corpo do POST /whatsapp/connection (não requer body, mas reservado)
"""
from typing import Any, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Webhook (Evolution API → backend)
# ---------------------------------------------------------------------------

class EvolutionWebhookMessage(BaseModel):
    """Mensagem recebida. Campos relevantes do payload da Evolution API v2."""
    conversation: Optional[str] = None                          # texto puro
    buttonsResponseMessage: Optional[dict] = None               # {"selectedButtonId": "opt_1"}
    listResponseMessage: Optional[dict] = None                  # {"singleSelectReply": {"selectedRowId": "opt_0"}}


class EvolutionWebhookKey(BaseModel):
    remoteJid: str          # "5511999999999@s.whatsapp.net"
    id: str                 # message ID único


class EvolutionWebhookData(BaseModel):
    key: EvolutionWebhookKey
    message: Optional[EvolutionWebhookMessage] = None
    messageType: Optional[str] = None  # "conversation" | "buttonsResponseMessage" | "listResponseMessage"


class EvolutionWebhookPayload(BaseModel):
    """Envelope completo enviado pela Evolution API ao webhook."""
    instance: str                       # nome da instância
    event: Optional[str] = None         # "messages.upsert" | "connection.update" | "qrcode.updated"
    data: Optional[Any] = None          # estrutura varia por evento


# ---------------------------------------------------------------------------
# Conexão (backend → painel)
# ---------------------------------------------------------------------------

class ConnectionResponse(BaseModel):
    status: str                         # DISCONNECTED | CONNECTING | CONNECTED | ERROR
    phone_number: Optional[str] = None
    connected_at: Optional[str] = None  # ISO 8601
    qr_code: Optional[str] = None       # base64 sem prefixo
    qr_expires_in: Optional[int] = None # segundos restantes
    disconnect_reason: Optional[str] = None


class QRCodeResponse(BaseModel):
    qr_code: str        # base64 sem prefixo "data:image/png;base64,"
    expires_in: int     # segundos (sempre 60)
