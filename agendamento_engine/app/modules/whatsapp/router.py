"""
Router do módulo WhatsApp.

Endpoints autenticados (admin only):
  POST   /whatsapp/connection          Inicia conexão / gera QR
  GET    /whatsapp/connection          Estado atual da conexão
  DELETE /whatsapp/connection          Desconecta
  GET    /whatsapp/qr                  Gera novo QR (quando expirou)

Endpoint público (webhook da Evolution API):
  POST   /whatsapp/webhook             Recebe eventos da Evolution API
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.config import settings
from app.core.deps import get_current_company_id, require_role
from app.modules.whatsapp import connection_service
from app.modules.whatsapp.schemas import ConnectionResponse, QRCodeResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

_owner_admin = require_role("OWNER", "ADMIN", "PLATFORM_OWNER")


# ---------------------------------------------------------------------------
# Endpoints autenticados — gerenciamento de conexão
# ---------------------------------------------------------------------------

@router.post("/connection", response_model=ConnectionResponse)
def start_connection(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
    _: object = Depends(_owner_admin),
):
    """Inicia a conexão WhatsApp. Retorna QR Code para scan."""
    return connection_service.connect(db, company_id)


@router.get("/connection", response_model=ConnectionResponse)
def get_connection_status(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
    _: object = Depends(_owner_admin),
):
    """Retorna o estado atual da conexão WhatsApp da empresa."""
    return connection_service.get_connection(db, company_id)


@router.delete("/connection", status_code=204)
def disconnect(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
    _: object = Depends(_owner_admin),
):
    """Desconecta o WhatsApp e remove a sessão."""
    connection_service.disconnect(db, company_id)


@router.get("/qr", response_model=QRCodeResponse)
def refresh_qr(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
    _: object = Depends(_owner_admin),
):
    """Gera novo QR Code quando o anterior expirou."""
    return connection_service.refresh_qr(db, company_id)


# ---------------------------------------------------------------------------
# Webhook público — recebe eventos da Evolution API
# IMPORTANTE: sem autenticação JWT — validado por IP ou segredo no header
# ---------------------------------------------------------------------------

def _persist_and_enqueue_inbound(db: Session, instance_name: str, data: dict) -> None:
    """S2.1 (Entrega B): persiste a mensagem recebida (RECEIVED) e enfileira o
    processamento no worker — o webhook responde 200 sem tocar em httpx/LLM/FSM.

    Fronteira do desacoplamento: a mensagem é durável ANTES do 200. Se o worker
    cair depois, a linha fica RECEIVED e o sweeper a re-enfileira. Dedup durável
    por (company_id, whatsapp_message_id) via ON CONFLICT DO NOTHING — resolve
    também a re-entrega da Evolution.
    """
    import uuid as _uuid
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.infrastructure.db.models import BotInboundMessage, WhatsAppConnection
    from app.modules.whatsapp.helpers import parse_inbound_envelope

    envelope = parse_inbound_envelope(data)
    if envelope is None:
        return  # grupo/fromMe/sem jid — ignorado (mesmo critério do processamento)
    message_id, whatsapp_id = envelope
    if not message_id:
        # id vazio não deduplica por chave — sintetiza um id único por mensagem.
        message_id = f"noid_{_uuid.uuid4()}"

    conn = (
        db.query(WhatsAppConnection)
        .filter(WhatsAppConnection.instance_name == instance_name)
        .first()
    )
    if not conn:
        logger.warning("webhook: instance_name=%s sem conexão, ignorado", instance_name)
        return
    company_id = conn.company_id

    stmt = (
        pg_insert(BotInboundMessage.__table__)
        .values(
            company_id=company_id,
            instance_name=instance_name,
            whatsapp_id=whatsapp_id,
            whatsapp_message_id=message_id,
            raw_payload=data,
            status="RECEIVED",
        )
        .on_conflict_do_nothing(index_elements=["company_id", "whatsapp_message_id"])
    )
    db.execute(stmt)
    db.commit()

    # Enfileira o drain da conversa. Best-effort (retry=False): broker fora do ar
    # é logado — o sweeper re-enfileira a linha RECEIVED depois.
    try:
        import importlib
        _mod = importlib.import_module("app.workers.bot_inbound_worker")
        _mod.drain_bot_inbound.apply_async(
            args=[str(company_id), whatsapp_id], retry=False,
        )
    except Exception:
        logger.exception("webhook: falha ao enfileirar drain conv=%s", whatsapp_id)


@router.post("/webhook", status_code=200)
async def webhook(request: Request, db: Session = Depends(get_db)):
    """
    Recebe eventos da Evolution API (messages.upsert, connection.update, qrcode.updated).

    Segurança: se EVOLUTION_WEBHOOK_SECRET estiver configurado, o header
    "apikey" enviado pela Evolution API deve corresponder ao segredo; caso
    contrário retorna 401. Sem segredo configurado, qualquer request é aceito.
    """
    # Nota: Evolution API v2 (axios/1.x) NÃO envia header de autenticação
    # nos webhooks. EVOLUTION_WEBHOOK_SECRET deve ficar vazio/não configurado.
    # A segurança é garantida pela URL privada do webhook.
    if settings.EVOLUTION_WEBHOOK_SECRET:
        incoming_key = (
            request.headers.get("apikey")
            or request.headers.get("x-evolution-global-apikey")
            or ""
        )
        if incoming_key != settings.EVOLUTION_WEBHOOK_SECRET:
            logger.warning("webhook: segredo inválido, request rejeitado")
            return JSONResponse(status_code=401, content={"status": "rejected"})

    try:
        payload = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "invalid json"}

    event = payload.get("event", "")
    instance_name = payload.get("instance", "")
    data = payload.get("data", {})

    # Normaliza evento para lowercase com ponto (ex: MESSAGES_UPSERT → messages.upsert)
    event_normalized = event.lower().replace("_", ".")

    try:
        if event_normalized == "connection.update":
            connection_service.handle_connection_update(db, instance_name, data)

        elif event_normalized == "qrcode.updated":
            connection_service.handle_qr_update(db, instance_name, data)

        elif event_normalized == "messages.upsert":
            # S2.1: persiste + enfileira; o processamento (SQLAlchemy + httpx +
            # LLM shadow) roda no worker, fora do event loop. Responde 200 já.
            _persist_and_enqueue_inbound(db, instance_name, data)

        elif event_normalized == "messages.update":
            # Votos de enquete (sendPoll) chegam como MESSAGES_UPDATE.
            # Extrai o voto e roteia como se fosse uma mensagem de texto normal.
            updates = data if isinstance(data, list) else [data]
            for update in updates:
                key = update.get("key", {})
                if key.get("fromMe"):
                    continue
                remote_jid = key.get("remoteJid", "")
                if not remote_jid or remote_jid.endswith("@g.us"):
                    continue

                # Tenta extrair a opção selecionada na enquete
                update_content = update.get("update", {})
                poll_updates = update_content.get("pollUpdates", [])

                for pu in poll_updates:
                    vote = pu.get("vote", {})
                    selected = vote.get("selectedOptions", [])
                    if not selected:
                        continue
                    option_name = selected[0].get("name", "")
                    if not option_name:
                        continue

                    logger.info(
                        "POLL VOTE: jid=%s option=%r", remote_jid, option_name
                    )
                    # Cria mensagem sintética e enfileira (mesmo caminho S2.1)
                    msg_id = key.get("id", "")
                    synthetic = {
                        "key": {
                            "remoteJid": remote_jid,
                            "fromMe": False,
                            "id": f"poll_{msg_id}",
                        },
                        "message": {"conversation": option_name},
                    }
                    _persist_and_enqueue_inbound(db, instance_name, synthetic)
                    break  # um voto por update

    except Exception:
        logger.exception("webhook processing error event=%s instance=%s", event, instance_name)
        # NÃO re-levanta — retorna 200 para Evolution API não desabilitar o webhook

    return {"status": "ok"}
