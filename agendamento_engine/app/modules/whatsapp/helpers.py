"""
Utilitários puros do bot: parsing de input, formatação de datas, extração de texto.

Sem efeitos colaterais — nenhuma chamada de rede ou banco aqui.
Importado por bot_service e pelos handlers.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

_DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def resolve_input(user_input: str, last_list: list) -> Optional[str]:
    """
    Resolve payload pelo input do usuário.
    Aceita:
    - row_id exato (botões/lista)
    - title exato (texto do botão/opção) — resolve votos de enquete (sendPoll)
    - número digitado ("1", "2", "1.", "1)", etc) — fallback texto numerado

    Retorna None se não encontrado → fallback.
    """
    if not last_list:
        return None

    cleaned = (user_input or "").strip()
    cleaned_lower = cleaned.lower()

    # 🔹 1. Match direto por row_id (case-insensitive)
    for item in last_list:
        row_id = str(item.get("row_id", "")).lower()
        if row_id and row_id == cleaned_lower:
            return item.get("payload")

    # 🔹 2. Match por title — resolve votos de enquete (texto exato da opção selecionada)
    for item in last_list:
        title = str(item.get("title", "")).lower()
        if title and title == cleaned_lower:
            return item.get("payload")

    # 🔹 3. Extrai número (robusto: "1", "1.", "1)", etc.)
    import re
    match = re.match(r"^(\d+)", cleaned)
    if match:
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(last_list):
            return last_list[idx].get("payload")

    return None


def extract_user_text(data: dict) -> str:
    """
    Extrai texto da mensagem da Evolution API (texto, botão ou lista).

    Formatos suportados:
    - Texto simples:         message.conversation
    - Texto extendido:       message.extendedTextMessage.text
    - Lista interativa:      message.listResponseMessage.singleSelectReply.selectedRowId
    - Botão clicado (v1):    message.buttonsResponseMessage.selectedButtonId
    - Botão clicado (v2):    message.templateButtonReplyMessage.selectedId
    - Botão interativo:      message.interactiveResponseMessage.nativeFlowResponseMessage.paramsJson (JSON com id)
    """
    msg = data.get("message") or {}

    # Lista interativa
    list_resp = msg.get("listResponseMessage", {})
    if list_resp:
        selected_id = list_resp.get("singleSelectReply", {}).get("selectedRowId", "")
        if selected_id:
            return selected_id

    # Botão clicado — formato Baileys v1
    btn_resp = msg.get("buttonsResponseMessage", {})
    if btn_resp:
        selected = btn_resp.get("selectedButtonId", "")
        if selected:
            return selected

    # Botão template — formato Baileys v2 alternativo
    tmpl_resp = msg.get("templateButtonReplyMessage", {})
    if tmpl_resp:
        selected = tmpl_resp.get("selectedId", "")
        if selected:
            return selected

    # Botão interativo — formato nativeFlow (Evolution API >= 2.x)
    interactive_resp = msg.get("interactiveResponseMessage", {})
    if interactive_resp:
        native = interactive_resp.get("nativeFlowResponseMessage", {})
        params_raw = native.get("paramsJson", "")
        if params_raw:
            import json as _json
            try:
                params = _json.loads(params_raw)
                btn_id = params.get("id", "")
                if btn_id:
                    return btn_id
            except Exception:
                pass

    # Texto simples
    return msg.get("conversation", "") or msg.get("extendedTextMessage", {}).get("text", "")


# Tipos de mensagem que a Evolution entrega dentro de messages.upsert.
# A ordem importa: `conversation` e `extendedTextMessage` são texto; qualquer
# outra chave é um tipo que o extract_user_text NÃO sabe ler — e todo tipo que
# ele não sabe ler chega ao dispatcher como string vazia.
_KNOWN_TEXT_KEYS = ("conversation", "extendedTextMessage")


def extract_message_type(data: dict) -> str:
    """Nome do tipo de mensagem — para a telemetria discriminar o que chegou.

    Usa `messageType` quando a Evolution o envia; senão deriva da primeira
    chave de `message`. "" quando não há mensagem (evento de conexão, etc.).
    """
    if not isinstance(data, dict):
        return ""
    declared = data.get("messageType")
    if isinstance(declared, str) and declared:
        return declared
    msg = data.get("message") or {}
    if not isinstance(msg, dict):
        return ""
    for k in msg:
        if k not in ("messageContextInfo",):
            return str(k)
    return ""


def extract_reaction(data: dict) -> Optional[dict]:
    """Extrai a reação de emoji, se a mensagem for uma.

    ⚠️ A reação NÃO tem evento próprio. Ela chega dentro de `messages.upsert`
    (o mesmo evento das mensagens normais), como
    `message.reactionMessage = {key: {…mensagem reagida…}, text: "👍"}`.
    Por isso ela atravessava todo o pipeline: `extract_user_text` não conhece
    `reactionMessage` e devolvia "", e texto vazio no MENU_PRINCIPAL reexibe o
    menu — que é o "bot reiniciou" relatado pelo cliente.

    `text` vazio = reação REMOVIDA (o WhatsApp usa o mesmo formato para tirar a
    reação). Ambos os casos são reação, e ambos são ignorados.

    Sem mapa semântico de emoji, deliberadamente: a decisão é ignorar sempre,
    independentemente do estado — reagir 👍 a "qual horário?" não confirma nada.
    Um mapa emoji→significado seria código morto. O emoji é REGISTRADO na
    telemetria para que a decisão possa ser revista depois, com dados.

    Retorna {"emoji", "target_message_id", "removed"} ou None.
    """
    if not isinstance(data, dict):
        return None
    msg = data.get("message")
    if not isinstance(msg, dict):
        return None
    reaction = msg.get("reactionMessage")
    if not isinstance(reaction, dict):
        return None
    emoji = reaction.get("text") or ""
    target = reaction.get("key") or {}
    return {
        "emoji": emoji,
        "target_message_id": (target.get("id") or "") if isinstance(target, dict) else "",
        "removed": not bool(emoji),
    }


def is_universal_command(text: str) -> Optional[str]:
    """Detecta comandos globais independente do estado atual.

    Nota (Sprint 2.6): "cancelar" NÃO é mais um atalho de menu — passou a ser
    intenção CANCELAR (cancelar agendamento) tratada pelo ChainClassifier nos
    estados de texto livre.

    Nota (F3): "voltar" NÃO é mais reset — significa UM passo atrás
    (BookingAction.BACK nos estados do FSM; volta contextual nos handlers
    legados — ver is_back_command). Reset total fica com "0"/"menu"/
    "início"/"sair".
    """
    t = (text or "").strip().lower()
    if t in ("0", "menu", "início", "inicio", "sair"):
        return "menu"
    if t in ("ver agendamentos", "meus agendamentos", "agendamentos"):
        return "ver_agendamentos"
    if t in ("atendente", "humano", "ajuda", "suporte"):
        return "humano"
    return None


# Palavras/payloads que significam "um passo atrás" (F3).
# "nav_voltar" = rowId da opção "← Voltar" nas listas; "← voltar" = voto de
# enquete (título exato da opção, lowercased). Compartilhado entre o
# input_parser (estados do FSM) e o bot_service (handlers legados).
BACK_WORDS = frozenset({"voltar", "volta", "nav_voltar", "← voltar"})


def is_back_command(text: str) -> bool:
    """True se o input significa 'voltar um passo' (F3)."""
    return (text or "").strip().lower() in BACK_WORDS


def to_company_tz(dt: datetime, tz_str: str) -> datetime:
    """Converte datetime para o fuso da empresa — delega ao helper canônico
    do BookingEngine (naive é tratado como UTC; o instante é preservado)."""
    from app.modules.booking.engine import BookingEngine  # import tardio evita ciclo
    return BookingEngine._to_company_tz(dt, tz_str)


def label_date(d, tz_str: str = "America/Sao_Paulo") -> str:
    """Formata data com label contextual em português.

    "Hoje"/"Amanhã" são derivados no fuso da empresa — perto da meia-noite
    a data UTC já virou o dia enquanto o dia local ainda é o anterior.
    """
    today = to_company_tz(datetime.now(timezone.utc), tz_str).date()
    if d == today:
        return f"Hoje ({d.strftime('%d/%m')})"
    if d == today + timedelta(days=1):
        return f"Amanhã ({d.strftime('%d/%m')})"
    weekday = _DIAS_PT[d.weekday()]
    return f"{weekday} ({d.strftime('%d/%m')})"


def first_name(full_name: str) -> str:
    """Retorna o primeiro nome para uso em mensagens."""
    return (full_name or "").strip().split()[0] if full_name else ""