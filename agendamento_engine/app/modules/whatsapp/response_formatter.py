"""
WhatsAppResponseFormatter — converte SessionUpdateResult em mensagens WhatsApp.

Responsabilidade:
  - Formatação de UX e envio via sender.
  - Conhece WhatsApp (sender.*), messages.py e os estados do BookingEngine.
  - Não acessa DB diretamente. Não modifica BookingSession.

Uso:
    from app.modules.whatsapp.response_formatter import whatsapp_response_formatter
    whatsapp_response_formatter.format_and_send(result, instance, to, ctx, company_tz)
"""
import logging
from datetime import datetime, timedelta, date

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.modules.booking.schemas import SessionUpdateResult, BookingResult
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender

logger = logging.getLogger(__name__)

_DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def _tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Sao_Paulo")


def _label_date(d: date, tz: ZoneInfo) -> str:
    """Gera label legível usando a data 'hoje' no fuso da empresa."""
    today = datetime.now(tz).date()
    if d == today:
        return f"Hoje ({d.strftime('%d/%m')})"
    if d == today + timedelta(days=1):
        return f"Amanhã ({d.strftime('%d/%m')})"
    return f"{_DIAS_PT[d.weekday()]} ({d.strftime('%d/%m')})"


def _slot_label(start_at: datetime, prof_name: str, tz: ZoneInfo, any_prof: bool) -> str:
    """Formata o título de um slot com data, hora e, se 'qualquer prof', nome do profissional."""
    local = start_at.astimezone(tz)
    time_str = local.strftime("%H:%M")
    date_str = _label_date(local.date(), tz)
    if any_prof and prof_name:
        return f"{date_str} — {time_str} — {prof_name}"
    return f"{date_str} — {time_str}"


def _first_name(full_name: str | None) -> str:
    if not full_name:
        return ""
    parts = full_name.strip().split()
    return parts[0] if parts else ""


class WhatsAppResponseFormatter:
    """
    Envia mensagens WhatsApp de acordo com o estado resultante do BookingEngine.

    Recebe o SessionUpdateResult retornado por booking_engine.update() e
    envia as mensagens apropriadas (lista, botões ou texto) via sender.*.

    Não modifica DB. Não escreve na BookingSession.
    O contexto recebido (ctx) é sempre leitura — snapshot imutável após a chamada ao engine.
    """

    def format_and_send(
        self,
        result: SessionUpdateResult,
        instance: str,
        to: str,
        ctx: dict,
        company_tz: str = "America/Sao_Paulo",
    ) -> None:
        """
        Envia as mensagens correspondentes ao próximo estado.

        Args:
            result:      retorno de booking_engine.update()
            instance:    nome da instância Evolution API
            to:          whatsapp_id do destinatário
            ctx:         booking_session.context (SOMENTE LEITURA)
            company_tz:  timezone da empresa
        """
        tz         = _tz(company_tz)
        state      = result.next_state
        first      = _first_name(ctx.get("customer_name"))

        # ── Erro de slot indisponível → aviso antes de re-listar ───────────────
        if result.error == "SLOT_UNAVAILABLE":
            sender.send_text(instance, to, messages.HORARIO_OCUPADO_CONFIRMANDO)

        # ── Despacha por estado ───────────────────────────────────────────────
        if state == "AWAITING_SERVICE":
            self._send_services(instance, to, result.options, first)

        elif state == "AWAITING_PROFESSIONAL":
            self._send_professionals(instance, to, result.options, ctx)

        elif state == "AWAITING_DATE":
            self._send_dates(instance, to, result.options, ctx, tz, first)

        elif state == "AWAITING_SHIFT":
            self._send_shifts(instance, to, options)

        elif state == "AWAITING_TIME":
            self._send_slots(instance, to, result.options, ctx, tz)

        elif state == "AWAITING_CONFIRMATION":
            self._send_confirmation_summary(instance, to, ctx, tz)

        elif state == "CONFIRMED":
            self._send_booking_confirmed(instance, to, result, ctx, tz, first)

        elif state == "CANCELLED":
            sender.send_text(instance, to, messages.cancelamento_confirmado(first))

        else:
            logger.warning("ResponseFormatter: estado não reconhecido state=%s", state)

    # ── Helpers por estado ────────────────────────────────────────────────────

    def _send_services(
        self, instance: str, to: str, options: list, first_name: str
    ) -> None:
        if not options:
            sender.send_text(instance, to, messages.SEM_SERVICOS)
            return
        rows = [
            {
                "rowId":       o.row_key,
                "title":       o.name,
                "description": f"R$ {o.price:.2f} · {o.duration_minutes} min",
            }
            for o in options
        ]
        sender.send_list(
            instance, to,
            "✂️ Nossos serviços",
            messages.escolha_servico(first_name),
            rows,
        )

    def _send_professionals(
        self, instance: str, to: str, options: list, ctx: dict
    ) -> None:
        svc_name = ctx.get("service_name", "")
        if not options:
            sender.send_text(instance, to, messages.SEM_HORARIOS)
            return
        rows = [
            {"rowId": o.row_key, "title": o.name, "description": ""}
            for o in options
        ]
        sender.send_list(
            instance, to,
            "👤 Escolha o profissional",
            messages.escolha_profissional(svc_name),
            rows,
        )

    def _send_dates(
        self,
        instance: str,
        to: str,
        options: list,
        ctx: dict,
        tz: ZoneInfo,
        first_name: str,
    ) -> None:
        svc_name  = ctx.get("service_name", "")
        prof_name = ctx.get("professional_name", "")

        # Filtrar apenas datas com disponibilidade
        available = [o for o in options if o.has_availability]
        if not available:
            sender.send_text(instance, to, messages.SEM_HORARIOS)
            return

        rows = [
            {"rowId": o.row_key, "title": o.label, "description": ""}
            for o in available
        ]
        sender.send_list(
            instance, to,
            messages.escolha_data_titulo(svc_name),
            messages.escolha_data_descricao(first_name, prof_name),
            rows,
        )

    def _send_shifts(self, instance: str, to: str, options: list[dict]) -> None:
        """Envia lista de turnos disponíveis para o usuário selecionar."""
        if not options:
            self.sender.send_text(instance, to, "Nenhum turno disponível para esta data.")
            return

        rows = [
            {"rowId": opt["row_key"], "title": opt.get("name", opt["row_key"])}
            for opt in options
        ]
        self.sender.send_list(
            instance,
            to,
            title="Selecione o turno",
            body="Qual turno prefere?",
            rows=rows,
        )

    def _send_slots(
        self,
        instance: str,
        to: str,
        options: list,
        ctx: dict,
        tz: ZoneInfo,
    ) -> None:
        # "qualquer prof" → mostrar nome do profissional em cada slot
        any_prof = not ctx.get("professional_id")

        if not options:
            sender.send_text(instance, to, messages.SEM_HORARIOS)
            return

        rows = [
            {
                "rowId":       o.row_key,
                "title":       _slot_label(o.start_at, o.professional_name, tz, any_prof),
                "description": "",
            }
            for o in options
        ]
        prof_name = ctx.get("professional_name", "")
        svc_name  = ctx.get("service_name", "")
        sender.send_list(
            instance, to,
            "🕐 Horários disponíveis",
            messages.escolha_horario(svc_name, prof_name),
            rows,
        )

    def _send_confirmation_summary(
        self, instance: str, to: str, ctx: dict, tz: ZoneInfo
    ) -> None:
        svc_name  = ctx.get("service_name", "")
        prof_name = ctx.get("professional_name") or "Qualquer profissional"
        slot_raw  = ctx.get("slot_start_at", "")

        try:
            local      = datetime.fromisoformat(slot_raw).astimezone(tz)
            date_label = _label_date(local.date(), tz)
            time_label = local.strftime("%H:%M")
        except Exception:
            date_label = "—"
            time_label = "—"

        text = messages.confirmacao_resumo(svc_name, prof_name, date_label, time_label)
        buttons = [
            {"buttonId": "confirm",        "buttonText": {"displayText": "✅ Confirmar"}},
            {"buttonId": "change",         "buttonText": {"displayText": "🕐 Alterar horário"}},
            {"buttonId": "cancel_booking", "buttonText": {"displayText": "❌ Cancelar"}},
        ]
        sender.send_buttons(instance, to, text, buttons)

    def _send_booking_confirmed(
        self,
        instance: str,
        to: str,
        result: SessionUpdateResult,
        ctx: dict,
        tz: ZoneInfo,
        first_name: str,
    ) -> None:
        if result.confirmation_data is None:
            sender.send_text(instance, to, messages.ERRO_CONFIRMAR_AGENDAMENTO)
            return

        data: BookingResult = result.confirmation_data
        try:
            local      = data.start_at.astimezone(tz)
            date_label = _label_date(local.date(), tz)
            slot_label = f"{date_label} às {local.strftime('%H:%M')}"
        except Exception:
            slot_label = "—"

        text = messages.agendamento_confirmado(
            first_name,
            data.service_name,
            data.professional_name,
            slot_label,
            settings.APPOINTMENT_MIN_HOURS_BEFORE_CANCEL,
        )
        sender.send_text(instance, to, text)


# Singleton — importar e reutilizar (stateless)
whatsapp_response_formatter = WhatsAppResponseFormatter()
