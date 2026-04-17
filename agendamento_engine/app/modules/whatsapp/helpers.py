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
    Aceita: row_id exato (botão/lista Evolution) ou número ("1", "2"...).
    Retorna None se não encontrado → fallback.
    """
    if not last_list:
        return None
    cleaned = (user_input or "").strip()
    for item in last_list:
        if item.get("row_id") == cleaned:
            return item.get("payload")
    if cleaned.isdigit():
        idx = int(cleaned) - 1
        if 0 <= idx < len(last_list):
            return last_list[idx].get("payload")
    return None


def extract_user_text(data: dict) -> str:
    """Extrai texto da mensagem da Evolution API (texto, botão ou lista)."""
    msg = data.get("message") or {}
    list_resp = msg.get("listResponseMessage", {})
    if list_resp:
        selected_id = list_resp.get("singleSelectReply", {}).get("selectedRowId", "")
        if selected_id:
            return selected_id
    btn_resp = msg.get("buttonsResponseMessage", {})
    if btn_resp:
        return btn_resp.get("selectedButtonId", "")
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