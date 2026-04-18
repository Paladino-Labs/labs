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
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_company_id, require_admin
from app.modules.whatsapp import connection_service
from app.modules.whatsapp.schemas import ConnectionResponse, QRCodeResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


# ---------------------------------------------------------------------------
# Endpoints autenticados — gerenciamento de conexão
# ---------------------------------------------------------------------------

@router.post("/connection", response_model=ConnectionResponse)
def start_connection(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    """Inicia a conexão WhatsApp. Retorna QR Code para scan."""
    return connection_service.connect(db, company_id)


@router.get("/connection", response_model=ConnectionResponse)
def get_connection_status(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    """Retorna o estado atual da conexão WhatsApp da empresa."""
    return connection_service.get_connection(db, company_id)


@router.delete("/connection", status_code=204)
def disconnect(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    """Desconecta o WhatsApp e remove a sessão."""
    connection_service.disconnect(db, company_id)


@router.get("/qr", response_model=QRCodeResponse)
def refresh_qr(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    """Gera novo QR Code quando o anterior expirou."""
    return connection_service.refresh_qr(db, company_id)


# ---------------------------------------------------------------------------
# Webhook público — recebe eventos da Evolution API
# IMPORTANTE: sem autenticação JWT — validado por IP ou segredo no header
# ---------------------------------------------------------------------------

@router.post("/webhook", status_code=200)
async def webhook(request: Request, db: Session = Depends(get_db)):
    """
    Recebe eventos da Evolution API (messages.upsert, connection.update, qrcode.updated).
    Sempre retorna 200 — a Evolution API desabilita o webhook em caso de 5xx.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "invalid json"}

    event = payload.get("event", "")
    instance_name = payload.get("instance", "")
    data = payload.get("data", {})

    # Normaliza evento para lowercase com ponto (ex: MESSAGES_UPSERT → messages.upsert)
    event_normalized = event.lower().replace("_", ".")

    # LOG DE DIAGNÓSTICO — remover após confirmar funcionamento
    import json as _json
    logger.info(
        "WEBHOOK RECEBIDO event=%s event_normalized=%s instance=%s data_keys=%s",
        event, event_normalized, instance_name,
        list(data.keys()) if isinstance(data, dict) else type(data).__name__,
    )
    if event_normalized == "messages.upsert":
        logger.info("WEBHOOK DATA COMPLETO: %s", _json.dumps(data, default=str)[:1000])

    try:
        if event_normalized == "connection.update":
            connection_service.handle_connection_update(db, instance_name, data)

        elif event_normalized == "qrcode.updated":
            connection_service.handle_qr_update(db, instance_name, data)

        elif event_normalized == "messages.upsert":
            # Importação tardia para evitar circular import entre bot e router
            from app.modules.whatsapp.bot_service import handle_inbound_message
            await handle_inbound_message(db, instance_name, data)

        elif event_normalized == "messages.update":
            # Votos de enquete (sendPoll) chegam como MESSAGES_UPDATE.
            # Extrai o voto e roteia como se fosse uma mensagem de texto normal.
            from app.modules.whatsapp.bot_service import handle_inbound_message
            import json as _json
            logger.info("MESSAGES_UPDATE DATA: %s", _json.dumps(data, default=str)[:1000])

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
                    # Cria mensagem sintética e roteia pelo dispatcher normal
                    msg_id = key.get("id", "")
                    synthetic = {
                        "key": {
                            "remoteJid": remote_jid,
                            "fromMe": False,
                            "id": f"poll_{msg_id}",
                        },
                        "message": {"conversation": option_name},
                    }
                    await handle_inbound_message(db, instance_name, synthetic)
                    break  # um voto por update

    except Exception:
        logger.exception("webhook processing error event=%s instance=%s", event, instance_name)
        # NÃO re-levanta — retorna 200 para Evolution API não desabilitar o webhook

    return {"status": "ok"}
