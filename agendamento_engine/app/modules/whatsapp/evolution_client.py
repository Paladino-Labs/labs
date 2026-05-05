"""
Cliente HTTP para a Evolution API.

Todas as chamadas saem daqui. O módulo não faz IO além de requests HTTP —
facilitando mock em testes.

Configuração via variáveis de ambiente:
    EVOLUTION_API_URL    URL base (ex: http://localhost:8080)
    EVOLUTION_API_KEY    API key global da instância Evolution
"""
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "apikey": settings.EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }


def _base() -> str:
    return settings.EVOLUTION_API_URL.rstrip("/")


# ---------------------------------------------------------------------------
# Gerenciamento de instâncias
# ---------------------------------------------------------------------------

def create_instance(instance_name: str) -> dict:
    """Cria uma nova instância na Evolution API."""
    url = f"{_base()}/instance/create"
    payload = {
        "instanceName": instance_name,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS",
    }
    resp = httpx.post(url, json=payload, headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_qr(instance_name: str) -> str:
    """
    Retorna o QR Code base64 da instância.
    Levanta httpx.HTTPStatusError se a instância não existir ou não estiver
    em estado CONNECTING.
    """
    url = f"{_base()}/instance/connect/{instance_name}"
    resp = httpx.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    # Evolution API v2: {"base64": "data:image/png;base64,...", "code": "..."}
    raw = data.get("base64", "")
    # Remove prefixo se presente
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[-1]
    return raw


def get_connection_state(instance_name: str) -> str:
    """
    Retorna o estado da conexão: 'open' (conectado), 'close' (desconectado),
    'connecting'.
    """
    url = f"{_base()}/instance/connectionState/{instance_name}"
    resp = httpx.get(url, headers=_headers(), timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get("instance", {}).get("state", "close")


def logout_instance(instance_name: str) -> None:
    """Desconecta e remove a sessão WhatsApp da instância."""
    url = f"{_base()}/instance/logout/{instance_name}"
    resp = httpx.delete(url, headers=_headers(), timeout=10)
    resp.raise_for_status()


def delete_instance(instance_name: str) -> None:
    """Remove a instância completamente da Evolution API."""
    url = f"{_base()}/instance/delete/{instance_name}"
    resp = httpx.delete(url, headers=_headers(), timeout=10)
    resp.raise_for_status()


def set_webhook(instance_name: str, webhook_url: str) -> dict:
    """
    Configura o webhook da instância na Evolution API.
    Deve ser chamado após criar a instância para que eventos de mensagens,
    conexão e QR Code sejam enviados ao backend.
    """
    url = f"{_base()}/webhook/set/{instance_name}"
    payload = {
        "webhook": {
            "enabled": True,
            "url": webhook_url,
            "events": [
                "MESSAGES_UPSERT",
                "MESSAGES_UPDATE",   # necessário para votos de enquete (sendPoll)
                "CONNECTION_UPDATE",
                "QRCODE_UPDATED",
            ],
        }
    }
    resp = httpx.post(url, json=payload, headers=_headers(), timeout=15)
    if not resp.is_success:
        logger.error(
            "set_webhook error status=%s body=%s | instance=%s",
            resp.status_code, resp.text[:500], instance_name,
        )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Envio de mensagens
# ---------------------------------------------------------------------------

def _normalize_number(number: str) -> str:
    """
    Normaliza número para envio: garante que está no formato JID completo.
    "5511999999999" → "5511999999999@s.whatsapp.net"
    "5511999999999@s.whatsapp.net" → inalterado
    """
    if "@" not in number:
        return f"{number}@s.whatsapp.net"
    return number


def send_text(instance_name: str, to: str, text: str) -> None:
    """Envia mensagem de texto simples."""
    url = f"{_base()}/message/sendText/{instance_name}"
    number = _normalize_number(to)
    payload = {
        "number": number,
        "text": text,
    }
    logger.debug("send_text payload number=%s text=%r", number, text[:60])
    resp = httpx.post(url, json=payload, headers=_headers(), timeout=15)
    if resp.is_success:
        logger.info("send_text ok status=%s number=%s", resp.status_code, number)
    else:
        logger.error(
            "send_text error status=%s body=%s | instance=%s number=%s",
            resp.status_code, resp.text[:500], instance_name, number,
        )
    resp.raise_for_status()


def send_buttons(
    instance_name: str,
    to: str,
    body_text: str,
    buttons: list[dict],  # [{"buttonId": "opt_1", "buttonText": {"displayText": "Sim"}}]
    footer_text: str = "",
) -> None:
    """
    Envia mensagem com botões interativos — funciona apenas com Cloud API (Meta).
    ⚠️  NÃO funciona no Baileys (WhatsApp Web): a API retorna 201 mas a mensagem
    nunca é entregue. Use send_poll() para Baileys.

    Formato v2 (Cloud API):
      buttons[i] = {"type": "reply", "displayText": "Texto", "id": "id_unico"}
    """
    url = f"{_base()}/message/sendButtons/{instance_name}"
    number = _normalize_number(to)

    # Normaliza do formato interno (buttonId/buttonText) para o formato Cloud API (id/displayText)
    formatted_buttons = [
        {
            "type":        "reply",
            "displayText": btn.get("buttonText", {}).get("displayText", ""),
            "id":          btn.get("buttonId", ""),
        }
        for btn in buttons
    ]

    payload = {
        "number":      number,
        "title":       body_text,
        "description": body_text,
        "footer":      footer_text,
        "buttons":     formatted_buttons,
    }

    logger.debug("send_buttons payload=%s", payload)
    resp = httpx.post(url, json=payload, headers=_headers(), timeout=15)
    if resp.is_success:
        logger.info("send_buttons ok status=%s number=%s", resp.status_code, number)
    else:
        logger.error(
            "send_buttons error status=%s body=%s | instance=%s number=%s",
            resp.status_code, resp.text[:500], instance_name, number,
        )
    resp.raise_for_status()


def send_poll(
    instance_name: str,
    to: str,
    name: str,
    values: list[str],
    selectable_count: int = 1,
) -> None:
    """
    Envia enquete interativa — funciona nativamente no Baileys (WhatsApp Web).
    É o substituto correto de sendButtons/sendList para instâncias Baileys.

    Limites WhatsApp: name ≤ 255 chars, cada opção ≤ 100 chars, até 12 opções.
    O voto do usuário chega via evento MESSAGES_UPDATE no webhook.
    """
    url = f"{_base()}/message/sendPoll/{instance_name}"
    number = _normalize_number(to)

    # Trunca para limites do WhatsApp
    payload = {
        "number":           number,
        "name":             name[:255],
        "selectableCount":  selectable_count,
        "values":           [v[:100] for v in values],
    }

    logger.debug("send_poll name=%r values=%s number=%s", name[:60], values, number)
    resp = httpx.post(url, json=payload, headers=_headers(), timeout=15)
    if resp.is_success:
        logger.info("send_poll ok status=%s number=%s", resp.status_code, number)
    else:
        logger.error(
            "send_poll error status=%s body=%s | instance=%s number=%s",
            resp.status_code, resp.text[:500], instance_name, number,
        )
    resp.raise_for_status()


def send_list(
    instance_name: str,
    to: str,
    title: str,
    description: str,
    button_text: str,
    rows: list[dict],
    section_title: str = "Opções",
) -> None:
    """
    Envia mensagem com lista de opções (até 10 itens).
    Ideal para serviços, profissionais e horários.
    """
    url = f"{_base()}/message/sendList/{instance_name}"
    number = _normalize_number(to)

    payload = {
        "number": number,
        "title": title,
        "description": description,
        "buttonText": button_text,
        "footerText": "",
        "sections": [
            {
                "title": section_title,
                "rows": rows,
            }
        ],
    }
    
    import json as _json
    logger.error(
        "sendList PAYLOAD: %s",
        _json.dumps(payload, ensure_ascii=False, indent=2, default=str),
    )

    resp = httpx.post(url, json=payload, headers=_headers(), timeout=15)

    if not resp.is_success:
        logger.error(
            "send_list error status=%s body=%s | instance=%s number=%s",
            resp.status_code, resp.text[:500], instance_name, number,
        )
    resp.raise_for_status()
