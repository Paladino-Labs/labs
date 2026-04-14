"""
Gerencia o ciclo de vida da conexão WhatsApp de uma empresa.

Responsabilidades:
  - Criar / reutilizar instância na Evolution API
  - Gerar / atualizar QR Code
  - Persistir status em whatsapp_connections
  - Processar eventos de connection.update e qrcode.updated
  - Lógica de reconexão automática
"""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import WhatsAppConnection
from app.modules.whatsapp import evolution_client
from app.modules.whatsapp.schemas import ConnectionResponse, QRCodeResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

# Motivos que NÃO acionam reconexão automática
_NO_RECONNECT_REASONS = {"logout", "manual_disconnect"}


def _instance_name(company_id: UUID) -> str:
    """Gera nome determinístico da instância para a empresa."""
    return f"paladino-{str(company_id)[:8]}"


def _get_or_create_record(db: Session, company_id: UUID) -> WhatsAppConnection:
    conn = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.company_id == company_id
    ).first()
    if not conn:
        conn = WhatsAppConnection(
            company_id=company_id,
            instance_name=_instance_name(company_id),
            status="DISCONNECTED",
        )
        db.add(conn)
        db.flush()
    return conn


def get_connection(db: Session, company_id: UUID) -> ConnectionResponse:
    """
    Retorna o estado atual da conexão.
    Se status=CONNECTING, sincroniza com a Evolution API (fresh check).
    """
    conn = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.company_id == company_id
    ).first()

    if not conn:
        return ConnectionResponse(status="DISCONNECTED")

    # Se estiver CONNECTING, pergunta à Evolution API se já conectou
    if conn.status == "CONNECTING":
        try:
            state = evolution_client.get_connection_state(conn.instance_name)
            if state == "open":
                conn.status = "CONNECTED"
                conn.connected_at = datetime.now(timezone.utc)
                conn.qr_code = None
                db.commit()
        except Exception as e:
            logger.warning("Falha ao verificar estado da conexão Evolution API instance=%s: %s",
                           conn.instance_name, e)

    qr_expires_in = None
    if conn.qr_code and conn.qr_generated_at:
        elapsed = (datetime.now(timezone.utc) - conn.qr_generated_at.replace(tzinfo=timezone.utc)).seconds
        remaining = settings.WHATSAPP_QR_TTL_SECONDS - elapsed
        qr_expires_in = max(0, remaining)
        if remaining <= 0:
            # QR expirado — limpa para o frontend exibir botão "Gerar novo QR"
            conn.qr_code = None
            db.commit()
            qr_expires_in = None

    return ConnectionResponse(
        status=conn.status,
        phone_number=conn.phone_number,
        connected_at=conn.connected_at.isoformat() if conn.connected_at else None,
        qr_code=conn.qr_code,
        qr_expires_in=qr_expires_in,
        disconnect_reason=conn.disconnect_reason,
    )


def connect(db: Session, company_id: UUID) -> ConnectionResponse:
    """
    Inicia o processo de conexão:
      1. Cria / reutiliza registro em whatsapp_connections
      2. Chama Evolution API para criar instância (idempotente)
      3. Busca QR Code
      4. Persiste e retorna estado CONNECTING + qr_code
    """
    conn = _get_or_create_record(db, company_id)

    if conn.status == "CONNECTED":
        raise HTTPException(status_code=409, detail="WhatsApp já está conectado")

    # Tenta criar instância (Evolution API ignora se já existir)
    try:
        evolution_client.create_instance(conn.instance_name)
    except Exception as e:
        # Instância pode já existir — tenta buscar QR diretamente
        logger.warning("create_instance falhou (pode já existir) instance=%s: %s",
                       conn.instance_name, e)

    # Registra (ou atualiza) o webhook na Evolution API
    webhook_url = f"{settings.WEBHOOK_BASE_URL.rstrip('/')}/whatsapp/webhook"
    try:
        evolution_client.set_webhook(conn.instance_name, webhook_url)
    except Exception as e:
        # Extrai body da resposta para diagnóstico
        body = ""
        if hasattr(e, "response") and e.response is not None:
            try:
                body = e.response.text
            except Exception:
                pass
        raise HTTPException(
            status_code=502,
            detail=f"Não foi possível configurar o webhook na Evolution API: {e} | body: {body}",
        )

    # Busca QR Code
    try:
        qr_base64 = evolution_client.get_qr(conn.instance_name)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Não foi possível obter QR Code da Evolution API: {e}",
        )

    now = datetime.now(timezone.utc)
    conn.status = "CONNECTING"
    conn.qr_code = qr_base64
    conn.qr_generated_at = now
    conn.disconnect_reason = None
    db.commit()

    return ConnectionResponse(
        status="CONNECTING",
        qr_code=qr_base64,
        qr_expires_in=settings.WHATSAPP_QR_TTL_SECONDS,
    )


def refresh_qr(db: Session, company_id: UUID) -> QRCodeResponse:
    """
    Gera novo QR Code (chamado quando o anterior expirou).
    Só funciona se status = CONNECTING.
    """
    conn = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.company_id == company_id
    ).first()

    if not conn or conn.status not in ("CONNECTING", "DISCONNECTED"):
        raise HTTPException(
            status_code=409,
            detail="Não é possível gerar QR no estado atual. Inicie uma nova conexão.",
        )

    try:
        qr_base64 = evolution_client.get_qr(conn.instance_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Evolution API: {e}")

    conn.qr_code = qr_base64
    conn.qr_generated_at = datetime.now(timezone.utc)
    conn.status = "CONNECTING"
    db.commit()

    return QRCodeResponse(qr_code=qr_base64, expires_in=settings.WHATSAPP_QR_TTL_SECONDS)


def disconnect(db: Session, company_id: UUID) -> None:
    """Desconecta o WhatsApp e marca status=DISCONNECTED."""
    conn = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.company_id == company_id
    ).first()

    if not conn:
        return

    try:
        evolution_client.logout_instance(conn.instance_name)
    except Exception as e:
        logger.warning("logout_instance falhou instance=%s: %s", conn.instance_name, e)

    conn.status = "DISCONNECTED"
    conn.phone_number = None
    conn.qr_code = None
    conn.qr_generated_at = None
    conn.disconnect_reason = "manual_disconnect"
    db.commit()


# ---------------------------------------------------------------------------
# Handlers de webhook de conexão
# ---------------------------------------------------------------------------

def handle_connection_update(db: Session, instance_name: str, data: dict) -> None:
    """
    Processa evento 'connection.update' da Evolution API.
    Atualiza status, phone_number, ou tenta reconexão automática.
    """
    conn = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.instance_name == instance_name
    ).first()
    if not conn:
        return

    state = data.get("state", "")
    number = data.get("number", None)

    if state == "open":
        conn.status = "CONNECTED"
        conn.phone_number = number
        conn.connected_at = datetime.now(timezone.utc)
        conn.qr_code = None
        conn.disconnect_reason = None

    elif state in ("close", "logout"):
        reason = "logout" if state == "logout" else data.get("reason", "connection_lost")
        conn.status = "DISCONNECTED"
        conn.disconnect_reason = reason

        # Reconexão automática (exceto logout manual)
        if reason not in _NO_RECONNECT_REASONS:
            try:
                evolution_client.create_instance(conn.instance_name)
                qr = evolution_client.get_qr(conn.instance_name)
                conn.status = "CONNECTING"
                conn.qr_code = qr
                conn.qr_generated_at = datetime.now(timezone.utc)
            except Exception:
                conn.status = "ERROR"

    db.commit()


def handle_qr_update(db: Session, instance_name: str, data: dict) -> None:
    """
    Processa evento 'qrcode.updated' da Evolution API.
    Atualiza o QR Code no banco para que o painel (polling) possa exibir o novo.
    """
    conn = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.instance_name == instance_name
    ).first()
    if not conn:
        return

    raw = data.get("qrcode", {}).get("base64", "")
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[-1]

    if raw:
        conn.qr_code = raw
        conn.qr_generated_at = datetime.now(timezone.utc)
        conn.status = "CONNECTING"
        db.commit()
