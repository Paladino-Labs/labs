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


def parse_inbound_envelope(data: dict) -> Optional[tuple[str, str]]:
    """Extrai (message_id, whatsapp_id) de um evento messages.upsert, espelhando
    a normalização de bot_service.handle_inbound_message (batch v2, LID
    addressing, skip de fromMe/grupo). Retorna None se a mensagem deve ser
    ignorada (grupo, fromMe, sem remoteJid).

    S2.1: usado pelo webhook para persistir/dedup/rotear ANTES do 200. O
    processamento real continua em handle_inbound_message, que re-parseia o
    mesmo payload — este helper é a fonte da CHAVE de conversa e do id de dedup,
    mantido byte-a-byte alinhado ao parse do processamento.
    """
    if isinstance(data, dict) and "messages" in data:
        messages_list = data.get("messages") or []
        if not messages_list:
            return None
        data = messages_list[0]

    key = data.get("key", {}) if isinstance(data, dict) else {}
    if key.get("fromMe"):
        return None

    message_id = key.get("id", "")

    addressing_mode = key.get("addressingMode", "")
    remote_jid_alt = key.get("remoteJidAlt", "")
    raw_jid = key.get("remoteJid", "")
    remote_jid = remote_jid_alt if (addressing_mode == "lid" and remote_jid_alt) else raw_jid

    if not remote_jid or remote_jid.endswith("@g.us"):
        return None

    return message_id, remote_jid


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