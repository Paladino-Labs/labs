"""
WhatsAppInputParser — mapeia texto livre do WhatsApp + estado da sessão → (BookingAction, payload).

Responsabilidade:
  - Parsing de input apenas. Sem lógica de negócio, sem chamadas a DB.
  - Conhece os estados do BookingEngine e como o usuário expressa cada seleção.
  - Agnóstico de canal exceto pelo mapeamento de números para opções (fallback texto).

Uso:
    from app.modules.whatsapp.input_parser import whatsapp_input_parser
    result = whatsapp_input_parser.parse(user_input, state, booking_session.context, tz)
    if result:
        action, payload = result
    else:
        # input não reconhecido → enviar mensagem de fallback
"""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.modules.booking.actions import BookingAction
from app.modules.whatsapp.helpers import resolve_input

# ── Constante exportada — usada em bot_service.py ────────────────────────────
BOOKING_STATES: frozenset[str] = frozenset({
    "AWAITING_SERVICE",
    "AWAITING_PROFESSIONAL",
    "AWAITING_DATE",
    "AWAITING_SHIFT",  
    "AWAITING_TIME",
    "AWAITING_CONFIRMATION",
})

# ── Mapeamento de linguagem natural para confirmação ─────────────────────────
_CONFIRM_WORDS = {
    "confirmar", "confirma", "sim", "yes", "ok", "ótimo", "otimo",
    "bora", "pode ser", "tá bom", "ta bom", "certo",
}
_CHANGE_WORDS = {
    "alterar", "alterar horário", "alterar horario", "trocar", "mudar",
    "outro horário", "outro horario", "voltar", "back", "change",
}
_CANCEL_WORDS = {
    "cancelar", "cancela", "não quero", "nao quero", "desistir",
    "não", "nao", "sair", "cancel",
}

# ── Mapeamento de linguagem natural para cancelamento ────────────────────────
_CONFIRM_CANCEL_WORDS = {
    "confirmar", "confirma", "sim", "yes", "ok", "cancelar", "cancela",
    "pode cancelar", "confirmo",
}
_BACK_WORDS = {
    "voltar", "back", "não", "nao", "não cancela", "nao cancela",
    "deixa", "desistir", "muda não", "muda nao",
}


def _tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Sao_Paulo")


def _slot_title(slot: dict, tz: ZoneInfo) -> str:
    """
    Reconstrói o título visual de um slot para matching via enquete (poll).
    O texto precisa ser idêntico ao usado pelo response_formatter.
    """
    try:
        from datetime import timedelta, date as _date
        _DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

        start = datetime.fromisoformat(slot["start_at"]).astimezone(tz)
        today = datetime.now(tz).date()
        d = start.date()

        if d == today:
            date_label = f"Hoje ({d.strftime('%d/%m')})"
        elif d == today + timedelta(days=1):
            date_label = f"Amanhã ({d.strftime('%d/%m')})"
        else:
            date_label = f"{_DIAS_PT[d.weekday()]} ({d.strftime('%d/%m')})"

        time_label = start.strftime("%H:%M")
        prof = slot.get("professional_name", "")
        if prof:
            return f"{date_label} — {time_label} — {prof}"
        return f"{date_label} — {time_label}"
    except Exception:
        return slot.get("row_key", "")


class WhatsAppInputParser:
    """
    Converte texto livre do WhatsApp em (BookingAction, payload) consumível pelo BookingEngine.

    O parser:
    - Tenta match por row_id exato (Evolution API retorna o rowId quando usuário seleciona)
    - Tenta match por título exato (Evolution API retorna o texto quando usuário vota em enquete)
    - Tenta match por número digitado ("1", "2", etc.) — fallback texto numerado
    - Tenta match por palavras-chave de linguagem natural (apenas nos estados de confirmação)
    """

    def parse(
        self,
        user_input: str,
        state: str,
        ctx: dict,
        company_tz: str = "America/Sao_Paulo",
    ) -> tuple[BookingAction, dict] | None:
        """
        Retorna (BookingAction, payload) ou None se o input não corresponde a nenhuma ação válida.

        Args:
            user_input: texto bruto recebido do WhatsApp (já extraído por extract_user_text)
            state:      estado atual da BotSession (ex: "AWAITING_SERVICE")
            ctx:        booking_session.context (JSONB com last_listed_*)
            company_tz: timezone da empresa para cálculo de títulos de slots
        """
        if state == "AWAITING_SERVICE":
            return self._parse_by_list(
                user_input,
                items=ctx.get("last_listed_services", []),
                title_field="name",
                action=BookingAction.SELECT_SERVICE,
            )

        if state == "AWAITING_PROFESSIONAL":
            return self._parse_by_list(
                user_input,
                items=ctx.get("last_listed_professionals", []),
                title_field="name",
                action=BookingAction.SELECT_PROFESSIONAL,
            )

        if state == "AWAITING_DATE":
            return self._parse_date(user_input, ctx)
        
        if state == "AWAITING_SHIFT":
            return self._parse_by_list(
                user_input,
                items=ctx.get("last_listed_shifts", []),
                title_field="name",
                action=BookingAction.SELECT_SHIFT,
            )

        if state == "AWAITING_TIME":
            return self._parse_time(user_input, ctx, company_tz)

        if state == "AWAITING_CONFIRMATION":
            return self._parse_confirmation(user_input)

        return None

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _parse_by_list(
        self,
        user_input: str,
        items: list[dict],
        title_field: str,
        action: BookingAction,
    ) -> tuple[BookingAction, dict] | None:
        """
        Tenta resolver o input contra uma lista de itens via resolve_input().
        Retorna (action, {row_key}) ou None.
        """
        if not items:
            return None
        last_list = [
            {
                "row_id":  item["row_key"],
                "payload": item["row_key"],
                "title":   item.get(title_field, ""),
            }
            for item in items
        ]
        row_key = resolve_input(user_input, last_list)
        if row_key:
            return (action, {"row_key": row_key})
        return None

    def _parse_date(
        self, user_input: str, ctx: dict
    ) -> tuple[BookingAction, dict] | None:
        """Resolve input contra a lista de datas disponíveis."""
        dates = ctx.get("last_listed_dates", [])
        if not dates:
            return None
        # Exibir apenas datas com disponibilidade para matching
        available = [d for d in dates if d.get("has_availability", False)]
        if not available:
            available = dates  # fallback: tentar contra todas
        last_list = [
            {"row_id": d["row_key"], "payload": d["row_key"], "title": d.get("label", "")}
            for d in available
        ]
        row_key = resolve_input(user_input, last_list)
        if row_key:
            return (BookingAction.SELECT_DATE, {"row_key": row_key})
        return None

    def _parse_time(
        self, user_input: str, ctx: dict, company_tz: str
    ) -> tuple[BookingAction, dict] | None:
        """
        Resolve input contra a lista de slots.
        Reconstrói o título visual (mesma lógica do formatter) para matching via enquete.
        """
        slots = ctx.get("last_listed_slots", [])
        if not slots:
            return None
        tz = _tz(company_tz)
        last_list = [
            {
                "row_id":  s["row_key"],
                "payload": s["row_key"],
                "title":   _slot_title(s, tz),
            }
            for s in slots
        ]
        row_key = resolve_input(user_input, last_list)
        if row_key:
            return (BookingAction.SELECT_TIME, {"row_key": row_key})
        return None

    def _parse_confirmation(
        self, user_input: str
    ) -> tuple[BookingAction, dict] | None:
        """
        Interpreta input no estado AWAITING_CONFIRMATION.

        Botões enviados pelo formatter:
          confirm        → Confirmar
          change         → Alterar horário
          cancel_booking → Cancelar

        Fallback texto: 1 = confirmar, 2 = alterar, 3 = cancelar
        """
        # Match direto por row_id do botão
        t = (user_input or "").strip().lower()
        if t in ("confirm", "btn_confirm", "confirmar"):
            return (BookingAction.CONFIRM, {})
        if t in ("change", "btn_change", "alterar horário", "alterar horario"):
            return (BookingAction.BACK, {})
        if t in ("cancel_booking", "btn_cancel"):
            return (BookingAction.RESET, {})

        # Matching via lista numerada (fallback texto)
        last_list = [
            {"row_id": "confirm",        "payload": "confirm",        "title": "Confirmar"},
            {"row_id": "change",         "payload": "change",         "title": "Alterar horário"},
            {"row_id": "cancel_booking", "payload": "cancel_booking", "title": "Cancelar"},
        ]
        payload = resolve_input(user_input, last_list)
        if payload == "confirm":
            return (BookingAction.CONFIRM, {})
        if payload == "change":
            return (BookingAction.BACK, {})
        if payload == "cancel_booking":
            return (BookingAction.RESET, {})

        # Linguagem natural
        if t in _CONFIRM_WORDS:
            return (BookingAction.CONFIRM, {})
        if t in _CHANGE_WORDS:
            return (BookingAction.BACK, {})
        if t in _CANCEL_WORDS:
            return (BookingAction.RESET, {})

        return None


# Singleton — importar e reutilizar (stateless)
whatsapp_input_parser = WhatsAppInputParser()
