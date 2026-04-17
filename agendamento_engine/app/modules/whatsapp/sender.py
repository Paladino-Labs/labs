"""
Helpers de envio de mensagens WhatsApp.

Centraliza chamadas ao evolution_client com fallback automático para texto
quando botões/listas falham. Importado por bot_service e pelos handlers.
"""
import logging

from app.modules.whatsapp import evolution_client

logger = logging.getLogger(__name__)


def send_text(instance: str, to: str, text: str) -> None:
    try:
        evolution_client.send_text(instance, to, text)
    except Exception as e:
        logger.error("send_text failed to=%s: %s", to, e)


def send_buttons(instance: str, to: str, text: str, buttons: list[dict]) -> None:
    """Envia botões interativos com fallback para texto numerado."""
    try:
        evolution_client.send_buttons(instance, to, text, buttons)
    except Exception as e:
        logger.warning("send_buttons falhou, fallback texto. to=%s: %s", to, e)
        lines = [text, ""]
        for i, btn in enumerate(buttons, start=1):
            label = btn.get("buttonText", {}).get("displayText", str(i))
            lines.append(f"*{i}.* {label}")
        lines.append("\n_Digite o número da opção._")
        send_text(instance, to, "\n".join(lines))


def send_list(instance: str, to: str, title: str, description: str, rows: list[dict]) -> None:
    """Envia lista interativa com fallback para texto numerado."""
    try:
        evolution_client.send_list(instance, to, title, description, "Ver opções", rows)
    except Exception as e:
        logger.warning("send_list falhou, fallback texto. to=%s: %s", to, e)
        _send_list_as_text(instance, to, title, description, rows)


def _send_list_as_text(instance: str, to: str, title: str, description: str, rows: list[dict]) -> None:
    lines = [f"*{title}*"]
    if description:
        lines.append(description)
    lines.append("")
    for i, row in enumerate(rows, start=1):
        label = row.get("title", str(i))
        desc  = row.get("description", "")
        lines.append(f"*{i}.* {label}" + (f" — {desc}" if desc else ""))
    lines.append("\n_Digite o número da opção._")
    send_text(instance, to, "\n".join(lines))