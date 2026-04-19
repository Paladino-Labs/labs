"""
Helpers de envio de mensagens WhatsApp.

Centraliza chamadas ao evolution_client com fallback automático para texto
quando botões/listas/polls falham.

Hierarquia de tentativas:
  BOT_USE_POLLS=True  → sendPoll  (nativo Baileys, WhatsApp entrega corretamente)
  BOT_USE_BUTTONS=True→ sendButtons (Cloud API apenas; Baileys aceita 201 mas não entrega)
  fallback            → texto numerado via sendText (sempre funciona)
"""
import logging

from app.modules.whatsapp import evolution_client
from app.core.config import settings

logger = logging.getLogger(__name__)


def send_text(instance: str, to: str, text: str) -> None:
    try:
        evolution_client.send_text(instance, to, text)
    except Exception as e:
        logger.error("send_text failed to=%s: %s", to, e)


def send_buttons(instance: str, to: str, text: str, buttons: list[dict]) -> None:
    """
    Envia opções ao usuário.

    - BOT_USE_POLLS=True  → enquete WhatsApp (nativo Baileys)
    - BOT_USE_BUTTONS=True→ botões interativos (Cloud API)
    - fallback            → texto numerado
    """
    if settings.BOT_USE_POLLS:
        values = [
            btn.get("buttonText", {}).get("displayText", f"Opção {i + 1}")
            for i, btn in enumerate(buttons)
        ]
        try:
            evolution_client.send_poll(instance, to, name=text, values=values)
            return
        except Exception as e:
            logger.warning("send_poll (buttons) falhou, fallback texto. to=%s: %s", to, e)

    if settings.BOT_USE_BUTTONS:
        try:
            evolution_client.send_buttons(instance, to, text, buttons)
            return
        except Exception as e:
            logger.warning("send_buttons falhou, fallback texto. to=%s: %s", to, e)

    # Fallback: lista numerada em texto simples
    lines = [text, ""]
    for i, btn in enumerate(buttons, start=1):
        label = btn.get("buttonText", {}).get("displayText", str(i))
        lines.append(f"*{i}.* {label}")
    lines.append("\n_Digite o número da opção ou *0* para o menu principal._")
    send_text(instance, to, "\n".join(lines))


def send_list(
    instance: str,
    to: str,
    title: str,
    description: str,
    rows: list[dict],
    section_title: str = "Opções",
) -> None:
    """
    Envia lista de opções ao usuário.

    - BOT_USE_POLLS=True → enquete WhatsApp (nativo Baileys)
    - fallback           → texto numerado
    """
    if settings.BOT_USE_POLLS:
        values = [row.get("title", f"Opção {i + 1}") for i, row in enumerate(rows)]
        poll_name = title[:255]
        try:
            evolution_client.send_poll(instance, to, name=poll_name, values=values)
            return
        except Exception as e:
            logger.warning("send_poll (list) falhou, fallback texto. to=%s: %s", to, e)

    try:
        evolution_client.send_list(
            instance, to, title, description, "Ver opções", rows, section_title
        )
        return
    except Exception as e:
        logger.warning("send_list falhou, fallback texto. to=%s: %s", to, e)

    # Fallback: lista numerada em texto simples
    lines = [f"*{title}*"]
    if description:
        lines.append(description)
    lines.append("")
    for i, row in enumerate(rows, start=1):
        label = row.get("title", str(i))
        desc  = row.get("description", "")
        lines.append(f"*{i}.* {label}" + (f" — {desc}" if desc else ""))
    lines.append("\n_Digite o número da opção ou *0* para o menu principal._")
    send_text(instance, to, "\n".join(lines))
