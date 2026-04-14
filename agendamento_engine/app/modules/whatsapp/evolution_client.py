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
    resp = httpx.post(url, json=payload, headers=_headers(), timeout=15)
    if not resp.is_success:
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
    Envia mensagem com até 3 botões interativos.
    buttons format: [{"buttonId": "opt_1", "buttonText": {"displayText": "Label"}}]
    """
    url = f"{_base()}/message/sendButtons/{instance_name}"
    number = _normalize_number(to)
    payload = {
        "number": number,
        "buttonsMessage": {
            "text": body_text,
            "footer": footer_text,
            "buttons": buttons,
        },
    }
    resp = httpx.post(url, json=payload, headers=_headers(), timeout=15)
    if not resp.is_success:
        logger.error(
            "send_buttons error status=%s body=%s | instance=%s number=%s",
            resp.status_code, resp.text[:500], instance_name, number,
        )
    resp.raise_for_status()


def send_list(
    instance_name: str,
    to: str,
    title: str,
    description: str,
    button_text: str,
    rows: list[dict],   # [{"rowId": "opt_0", "title": "09:00", "description": ""}]
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
        "listMessage": {
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
        },
    }
    resp = httpx.post(url, json=payload, headers=_headers(), timeout=15)
    if not resp.is_success:
        logger.error(
            "send_list error status=%s body=%s | instance=%s number=%s",
            resp.status_code, resp.text[:500], instance_name, number,
        )
    resp.raise_for_status()
