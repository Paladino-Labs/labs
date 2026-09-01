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
from app.modules.whatsapp import trace
from app.modules.whatsapp.helpers import PROTECTED_ROW_IDS
from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Guard de formato (S2) ────────────────────────────────────────────────────
# Os limites do WhatsApp estavam só nos docstrings do evolution_client (:213,
# :249) e não eram aplicados em lugar nenhum: send_list repassava `rows` inteiro
# e send_buttons repassava `buttons` inteiro. Passar do limite falha no envio —
# e o fallback de texto numerado aceita qualquer tamanho, então a falha só
# apareceria no WhatsApp do cliente.
#
# Vira problema real com o S2: acrescentar a opção de atendimento a uma lista de
# 10 linhas a leva a 11.
MAX_LIST_ROWS   = 10
MAX_BUTTONS     = 3


def _truncate_rows(items: list[dict], limit: int, id_key: str, what: str) -> list[dict]:
    """Corta a lista ao limite do WhatsApp PRESERVANDO as linhas de navegação.

    ⚠️ Cortar pelo fim (`items[:limit]`) descartaria justamente "← Voltar" e
    "💬 Falar com atendente", que são sempre as últimas — e no caso da opção de
    atendimento isso apagaria o objetivo inteiro do fallback. O corte sai do
    CONTEÚDO: as linhas protegidas são reservadas primeiro, o resto preenche o
    que sobra, e a ordem original é mantida.

    Truncar em silêncio troca um defeito por outro — sempre loga.
    """
    if len(items) <= limit:
        return items

    # Trabalha com ÍNDICES, não com os dicts: dois itens podem ser iguais em
    # valor (ou o mesmo objeto repetido) e um `in`/`id()` escolheria errado.
    prot_idx = [
        n for n, i in enumerate(items)
        if str(i.get(id_key, "")) in PROTECTED_ROW_IDS
    ]
    cont_idx = [
        n for n, i in enumerate(items)
        if str(i.get(id_key, "")) not in PROTECTED_ROW_IDS
    ]

    # Lista só de protegidas maior que o limite não deveria existir; se existir,
    # o limite manda — melhor entregar algo que falhar o envio.
    keep = set(prot_idx[:limit]) | set(cont_idx[: max(0, limit - len(prot_idx))])
    result = [items[n] for n in sorted(keep)][:limit]

    logger.warning(
        "guard de formato: %s truncado de %d para %d (protegidas mantidas: %s)",
        what, len(items), len(result),
        [str(i.get(id_key, "")) for i in result if str(i.get(id_key, "")) in PROTECTED_ROW_IDS],
    )
    return result


def send_text(instance: str, to: str, text: str) -> None:
    # Telemetria S-bot-1: a saída é capturada aqui, no ponto único por onde
    # TODO envio do bot passa. É o que responde "o que o bot respondeu" — e,
    # cruzado com o silêncio do cliente depois, é o sinal de abandono.
    try:
        evolution_client.send_text(instance, to, text)
        trace.note_outbound("text", text, ok=True)
    except Exception as e:
        logger.error("send_text failed to=%s: %s", to, e)
        trace.note_outbound("text", text, ok=False)


def send_buttons(instance: str, to: str, text: str, buttons: list[dict]) -> None:
    """
    Envia opções ao usuário.

    - BOT_USE_POLLS=True  → enquete WhatsApp (nativo Baileys)
    - BOT_USE_BUTTONS=True→ botões interativos (Cloud API)
    - fallback            → texto numerado
    """
    buttons = _truncate_rows(buttons, MAX_BUTTONS, "buttonId", "botões")

    if settings.BOT_USE_POLLS:
        values = [
            btn.get("buttonText", {}).get("displayText", f"Opção {i + 1}")
            for i, btn in enumerate(buttons)
        ]
        try:
            evolution_client.send_poll(instance, to, name=text, values=values)
            trace.note_outbound("poll", f"{text} :: {' | '.join(values)}")
            return
        except Exception as e:
            logger.warning("send_poll (buttons) falhou, fallback texto. to=%s: %s", to, e)

    if settings.BOT_USE_BUTTONS:
        try:
            evolution_client.send_buttons(instance, to, text, buttons)
            trace.note_outbound("buttons", text)
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
    rows = _truncate_rows(rows, MAX_LIST_ROWS, "rowId", "linhas da lista")

    if settings.BOT_USE_POLLS:
        values = [row.get("title", f"Opção {i + 1}") for i, row in enumerate(rows)]
        poll_name = title[:255]
        try:
            evolution_client.send_poll(instance, to, name=poll_name, values=values)
            trace.note_outbound("poll", f"{poll_name} :: {' | '.join(values)}")
            return
        except Exception as e:
            logger.warning("send_poll (list) falhou, fallback texto. to=%s: %s", to, e)

    try:
        evolution_client.send_list(
            instance, to, title, description, "Ver opções", rows, section_title
        )
        trace.note_outbound(
            "list", f"{title} :: {' | '.join(r.get('title', '') for r in rows)}",
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
