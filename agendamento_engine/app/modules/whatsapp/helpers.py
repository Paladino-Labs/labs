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
    - número ("1", "2", "1.", "1)", etc)

    Retorna None se não encontrado → fallback.
    """
    if not last_list:
        return None

    cleaned = (user_input or "").strip().lower()

    # 🔹 1. Match direto por row_id
    for item in last_list:
        row_id = str(item.get("row_id", "")).lower()
        if row_id and row_id == cleaned:
            return item.get("payload")

    # 🔹 2. Extrai número (robusto)
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


def is_universal_command(text: str) -> Optional[str]:
    """Detecta comandos globais independente do estado atual."""
    t = (text or "").strip().lower()
    if t in ("0", "menu", "início", "inicio", "voltar", "sair", "cancelar"):
        return "menu"
    if t in ("ver agendamentos", "meus agendamentos", "agendamentos"):
        return "ver_agendamentos"
    if t in ("atendente", "humano", "ajuda", "suporte"):
        return "humano"
    return None


def label_date(d) -> str:
    """Formata data com label contextual em português."""
    today = datetime.now(timezone.utc).date()
    if d == today:
        return f"Hoje ({d.strftime('%d/%m')})"
    if d == today + timedelta(days=1):
        return f"Amanhã ({d.strftime('%d/%m')})"
    weekday = _DIAS_PT[d.weekday()]
    return f"{weekday} ({d.strftime('%d/%m')})"


def first_name(full_name: str) -> str:
    """Retorna o primeiro nome para uso em mensagens."""
    return (full_name or "").strip().split()[0] if full_name else ""