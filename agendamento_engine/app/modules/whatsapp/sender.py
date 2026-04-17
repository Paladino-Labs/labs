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
        payload = {
            "number": number,
            "text": text,
            "footer": "",
            "buttons": buttons,
        }

        evolution_client.send_buttons(instance, to, payload)

    except Exception as e:
        logger.warning("send_buttons falhou, fallback texto. to=%s: %s", to, e)
        lines = [text, ""]
        for i, btn in enumerate(buttons, start=1):
            label = btn.get("buttonText", {}).get("displayText", str(i))
            lines.append(f"*{i}.* {label}")
        lines.append("\n_Digite o número da opção._")
        send_text(instance, to, "\n".join(lines))


def send_list(
    instance_name: str,
    to: str,
    title: str,
    description: str,
    button_text: str,
    rows: list[dict],
    section_title: str = "Opções",
) -> None:
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

    resp = httpx.post(url, json=payload, headers=_headers(), timeout=15)

    if not resp.is_success:
        logger.error(
            "send_list error status=%s body=%s | instance=%s number=%s",
            resp.status_code, resp.text[:500], instance_name, number,
        )

    resp.raise_for_status()


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