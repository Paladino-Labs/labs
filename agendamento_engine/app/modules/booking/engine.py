"""
BookingEngine — orquestrador central de agendamento.

Responsabilidades:
  - Listar serviços, profissionais, datas e horários disponíveis
  - Confirmar, cancelar e reagendar agendamentos
  - Retornar oferta preditiva para clientes recorrentes
  - Gerenciar o ciclo de vida de BookingSession (start_session, update, get_options_for_state)

Contrato:
  - Agnóstico de canal: não importa nada de whatsapp/ nem de routers HTTP
  - Não formata mensagens, não envia notificações
  - Não faz db.commit() — responsabilidade exclusiva do caller (endpoint/handler)
  - Recebe IDs e datetimes, devolve estruturas tipadas de booking/schemas.py
  - Delega toda lógica de domínio aos services existentes (appointments, availability, etc.)
  - Converte HTTPException 409 em SlotUnavailableError (agnóstica de canal)

Correções aplicadas:
  [FIX 1] Ordem do fluxo invertida: IDLE agora vai direto para AWAITING_SERVICE.
          Dados do cliente (SET_CUSTOMER) são coletados após AWAITING_TIME,
          no novo estado AWAITING_CUSTOMER, antes de AWAITING_CONFIRMATION.
  [FIX 2] Trava ao escolher profissional: o contexto (last_listed_*) é montado
          completamente antes de uma única atribuição session.context = ctx,
          garantindo que o SQLAlchemy detecte a mutação corretamente em todos
          os handlers.
  [FIX 3] Fuso horário: slots e datetimes são convertidos para o timezone da
          empresa antes de serem serializados no contexto ou retornados ao
          cliente. Helper _to_company_tz() centraliza a conversão.
"""
import logging
import secrets
from dataclasses import asdict
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.appointments import service as appointment_svc
from app.modules.appointments.schemas import (
    AppointmentCreate,
    RescheduleRequest,
    ServiceRequest,
)
from app.modules.appointments.polices import PolicyViolationError
from app.modules.availability import service as availability_svc
from app.modules.customers import service as customer_svc
from app.modules.professionals import service as professional_svc
from app.modules.services import service as service_svc
from app.core.config import settings

from app.modules.booking.schemas import (
    ServiceOption,
    ProfessionalOption,
    DateOption,
    SlotOption,
    ShiftOption,
    BookingIntent,
    BookingResult,
    AppointmentSummary,
    PredictiveOfferResult,
    CancelResult,
    RescheduleResult,
    SessionUpdateResult,
)
from app.modules.booking.exceptions import SlotUnavailableError, BookingNotFoundError
from app.modules.booking.actions import BookingAction, SessionExpiredError, InvalidActionError

logger = logging.getLogger(__name__)


def _http_exc_to_domain(exc: Exception) -> Exception:
    """
    Translate an HTTPException from the service layer into a domain exception.

    The existing services use FastAPI's HTTPException as their error mechanism.
    This helper converts status codes to domain exceptions without requiring
    the engine to import from fastapi.
    """
    status = getattr(exc, "status_code", None)
    detail = str(getattr(exc, "detail", exc))
    if status == 404:
        return BookingNotFoundError(detail)
    return SlotUnavailableError(detail)


_DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def _label_date(d: date, reference_tz: str = "America/Sao_Paulo") -> str:
    """
    Gera label legível para uma data no timezone da empresa.
    Usa a data "hoje" no fuso da empresa, não UTC — evita label errado à meia-noite.
    """
    try:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo(reference_tz)).date()
    except Exception:
        today = datetime.now(timezone.utc).date()

    if d == today:
        return f"Hoje ({d.strftime('%d/%m')})"
    if d == today + timedelta(days=1):
        return f"Amanhã ({d.strftime('%d/%m')})"
    return f"{_DIAS_PT[d.weekday()]} ({d.strftime('%d/%m')})"


# TTL por canal — centralizado aqui para ser reutilizado em start_session e update()
_CHANNEL_TTL: dict[str, timedelta] = {
    "web":      timedelta(minutes=15),
    "whatsapp": timedelta(minutes=30),
    "admin":    timedelta(hours=2),
}

# [FIX 1] Mapa de estado → estado anterior (para BACK) atualizado com AWAITING_CUSTOMER
_BACK_STATE: dict[str, str] = {
    "AWAITING_PROFESSIONAL":   "AWAITING_SERVICE",
    "AWAITING_DATE":           "AWAITING_PROFESSIONAL",
    "AWAITING_SHIFT":          "AWAITING_DATE",         # novo — volta para seleção de data
    "AWAITING_TIME":           "AWAITING_SHIFT",        # alterado — volta para seleção de turno
    "AWAITING_CUSTOMER":       "AWAITING_TIME",
    "AWAITING_CONFIRMATION":   "AWAITING_CUSTOMER",
    "AWAITING_CANCEL_CONFIRM": "AWAITING_CONFIRMATION",
}


class BookingEngine:
    """
    Orquestrador central de agendamento.
    Instanciar uma vez por módulo; é stateless (sem estado de instância).
    """

    # ─── Timezone helper ──────────────────────────────────────────────────────

    @staticmethod
    def _to_company_tz(dt: datetime, tz_str: str) -> datetime:
        """
        [FIX 3] Converte datetime para o fuso da empresa, preservando o instante.
        Datetimes naive são tratados como UTC antes da conversão.
        """
        try:
            from zoneinfo import ZoneInfo
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(ZoneInfo(tz_str))
        except Exception:
            return dt

    # ─── Serviços ─────────────────────────────────────────────────────────────

    def list_services(self, db: Session, company_id: UUID) -> list[ServiceOption]:
        """Retorna serviços ativos da empresa com row_key 1-based."""
        services = service_svc.list_services(db, company_id, active_only=True)
        return [
            ServiceOption(
                id=s.id,
                name=s.name,
                price=Decimal(str(s.price)),
                duration_minutes=int(s.duration),
                row_key=f"serv_{i + 1}",
            )
            for i, s in enumerate(services)
        ]

    # ─── Profissionais ────────────────────────────────────────────────────────

    def list_professionals(
        self, db: Session, company_id: UUID, service_id: UUID
    ) -> list[ProfessionalOption]:
        """
        Retorna profissionais vinculados ao serviço.
        Inclui sempre a opção 'Qualquer disponível' ao final (row_key='prof_any').
        """
        profs = professional_svc.list_by_service(db, company_id, service_id)
        options = [
            ProfessionalOption(id=p.id, name=p.name, row_key=f"prof_{i + 1}")
            for i, p in enumerate(profs)
        ]
        options.append(
            ProfessionalOption(id=None, name="Qualquer disponível", row_key="prof_any")
        )
        return options

    # ─── Datas disponíveis ────────────────────────────────────────────────────

    def list_available_dates_paged(
        self,
        db: Session,
        company_id: UUID,
        professional_id: Optional[UUID],
        service_id: UUID,
        offset_days: int = 0,
        window: int = 7,
        reference_tz: str = "America/Sao_Paulo",
    ) -> tuple[list[DateOption], bool, bool]:
        """
        Retorna uma janela de <window> dias com indicação de disponibilidade.

        Parâmetros:
          offset_days — dias a partir de hoje para iniciar a janela (mínimo 0).
          window      — tamanho da janela em dias.
          reference_tz — fuso da empresa para gerar labels corretos.

        Retorna: (dates, has_next, has_previous)
          dates        — DateOption[] para os dias [offset, offset+window-1]
          has_next     — True se há disponibilidade em algum dia da próxima janela
          has_previous — True se offset_days > 0
        """
        offset_days = max(0, offset_days)

        try:
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo(reference_tz)).date()
        except Exception:
            today = datetime.now(timezone.utc).date()

        if professional_id:
            profs_to_check = [professional_id]
        else:
            profs = professional_svc.list_by_service(db, company_id, service_id)
            profs_to_check = [p.id for p in profs]

        def _has(d: date) -> bool:
            for pid in profs_to_check:
                try:
                    slots = availability_svc.get_available_slots(
                        db, company_id, pid, service_id, d
                    )
                    if slots:
                        return True
                except HTTPException:
                    continue
            return False

        # Janela atual
        dates: list[DateOption] = []
        for i in range(window):
            d = today + timedelta(days=offset_days + i)
            dates.append(DateOption(
                date=d,
                label=_label_date(d, reference_tz),
                has_availability=_has(d),
                row_key=f"dia_{i + 1}",
            ))

        # Verificar próxima janela — curto-circuita no primeiro dia disponível
        has_next = False
        for i in range(window, window * 2):
            d = today + timedelta(days=offset_days + i)
            if _has(d):
                has_next = True
                break

        return dates, has_next, bool(offset_days > 0)

    def list_available_dates(
        self,
        db: Session,
        company_id: UUID,
        professional_id: Optional[UUID],
        service_id: UUID,
        days: int = 30,
        reference_tz: str = "America/Sao_Paulo",
    ) -> list[DateOption]:
        """
        Retorna os próximos <days> dias com indicação de disponibilidade.
        Se professional_id=None, verifica qualquer profissional do serviço.
        reference_tz: timezone da empresa para geração correta de labels de data.
        """
        try:
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo(reference_tz)).date()
        except Exception:
            today = datetime.now(timezone.utc).date()

        profs_to_check: list[UUID] = []

        if professional_id:
            profs_to_check = [professional_id]
        else:
            profs = professional_svc.list_by_service(db, company_id, service_id)
            profs_to_check = [p.id for p in profs]

        result: list[DateOption] = []
        for offset in range(days):
            d = today + timedelta(days=offset)
            has = False
            for pid in profs_to_check:
                try:
                    slots = availability_svc.get_available_slots(
                        db, company_id, pid, service_id, d
                    )
                    if slots:
                        has = True
                        break
                except HTTPException:
                    continue
            result.append(DateOption(
                date=d,
                label=_label_date(d, reference_tz),
                has_availability=has,
                row_key=f"dia_{offset + 1}",
            ))

        return result

    # ─── Slots disponíveis ────────────────────────────────────────────────────

    def list_available_slots(
        self,
        db: Session,
        company_id: UUID,
        professional_id: Optional[UUID],
        service_id: UUID,
        target_date: date,
        limit: int = 0,
        company_timezone: str = "America/Sao_Paulo",
    ) -> list[SlotOption]:
        """
        Retorna slots disponíveis para a data.
        Se professional_id=None, agrega slots de todos os profissionais do serviço.
        limit=0 significa sem limite.
        [FIX 3] Os datetimes dos slots são convertidos para o fuso da empresa.
        """
        if professional_id:
            raw = availability_svc.get_available_slots(
                db, company_id, professional_id, service_id, target_date
            )
        else:
            raw = []
            profs = professional_svc.list_by_service(db, company_id, service_id)
            half = max(1, (limit or settings.BOT_MAX_SLOTS_DISPLAYED) // 2)
            for p in profs:
                try:
                    slots = availability_svc.get_available_slots(
                        db, company_id, p.id, service_id, target_date
                    )
                    raw.extend(slots[:half])
                    if len(raw) >= (limit or settings.BOT_MAX_SLOTS_DISPLAYED):
                        break
                except HTTPException:
                    continue

        if limit:
            raw = raw[:limit]

        return [
            SlotOption(
                # [FIX 3] Converter para timezone da empresa antes de expor ao cliente
                start_at=self._to_company_tz(s.start_at, company_timezone),
                end_at=self._to_company_tz(s.end_at, company_timezone),
                professional_id=s.professional_id,
                professional_name=s.professional_name,
                row_key=f"slot_{i + 1}",
            )
            for i, s in enumerate(raw)
        ]

    @staticmethod
    def _filter_slots_by_shift(slots: list, shift: str, tz) -> list:
        """
        Filtra slots pelo turno usando hora local da empresa.
        Reutilizado em get_shift_availability e _handle_select_shift.
        """
        if shift == "manha":
            return [s for s in slots if s.start_at.astimezone(tz).hour < 12]
        if shift == "tarde":
            return [s for s in slots if 12 <= s.start_at.astimezone(tz).hour < 18]
        if shift == "noite":
            return [s for s in slots if s.start_at.astimezone(tz).hour >= 18]
        return slots

    def get_shift_availability(
        self,
        db: Session,
        company_id: UUID,
        professional_id: Optional[UUID],
        service_id: UUID,
        target_date: date,
        company_timezone: str = "America/Sao_Paulo",
    ) -> list[ShiftOption]:
        """
        Retorna os três turnos do dia com a contagem de slots disponíveis em cada um.
        Usado ao entrar no estado AWAITING_SHIFT (selecione o período do dia).
        """
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        all_slots = self.list_available_slots(
            db, company_id, professional_id, service_id, target_date,
            limit=0, company_timezone=company_timezone,
        )

        try:
            tz = ZoneInfo(company_timezone)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("America/Sao_Paulo")

        options: list[ShiftOption] = []
        for shift, label, row_key, min_h, max_h in self._SHIFT_DEFS:
            filtered = [s for s in all_slots if min_h <= s.start_at.astimezone(tz).hour < max_h]
            options.append(ShiftOption(
                shift=shift,
                label=label,
                slot_count=len(filtered),
                has_availability=bool(filtered),
                row_key=row_key,
            ))

        return options

    def list_next_available_slots(
        self,
        db: Session,
        company_id: UUID,
        professional_id: Optional[UUID],
        service_id: UUID,
        days: int = 30,
        limit: int = 0,
        company_timezone: str = "America/Sao_Paulo",
    ) -> list[SlotOption]:
        """
        Retorna os próximos slots disponíveis nos próximos <days> dias.
        Usado quando o cliente ainda não escolheu uma data.
        [FIX 3] Os datetimes dos slots são convertidos para o fuso da empresa.
        """
        effective_limit = limit or settings.BOT_MAX_SLOTS_DISPLAYED

        if professional_id:
            raw = availability_svc.get_next_available_slots(
                db, company_id, professional_id, service_id,
                days=days, limit=effective_limit,
            )
        else:
            raw = []
            profs = professional_svc.list_by_service(db, company_id, service_id)
            half = max(1, effective_limit // 2)
            for p in profs:
                raw.extend(
                    availability_svc.get_next_available_slots(
                        db, company_id, p.id, service_id,
                        days=days, limit=half,
                    )
                )
                if len(raw) >= effective_limit:
                    break
            raw = raw[:effective_limit]

        return [
            SlotOption(
                # [FIX 3] Converter para timezone da empresa antes de expor ao cliente
                start_at=self._to_company_tz(s.start_at, company_timezone),
                end_at=self._to_company_tz(s.end_at, company_timezone),
                professional_id=s.professional_id,
                professional_name=s.professional_name,
                row_key=f"slot_{i + 1}",
            )
            for i, s in enumerate(raw)
        ]

    # ─── Confirmar ────────────────────────────────────────────────────────────

    def confirm(
        self, db: Session, company_id: UUID, intent: BookingIntent
    ) -> BookingResult:
        """
        Cria o agendamento.
        Converte HTTPException 409 em SlotUnavailableError (agnóstica de canal).
        """
        appt_data = AppointmentCreate(
            professional_id=intent.professional_id,
            client_id=intent.customer_id,
            services=[{"service_id": intent.service_id}],
            start_at=intent.start_at,
            idempotency_key=intent.idempotency_key,
        )
        try:
            appt = appointment_svc.create_appointment(
                db, company_id, appt_data, user_id=None
            )
        except HTTPException as e:
            if e.status_code == 409:
                raise SlotUnavailableError(e.detail)
            raise

        svc_name  = appt.services[0].service_name if appt.services else ""
        prof_name = appt.professional.name if appt.professional else ""

        return BookingResult(
            appointment_id=appt.id,
            service_name=svc_name,
            professional_name=prof_name,
            start_at=appt.start_at,
            end_at=appt.end_at,
            total_amount=appt.total_amount,
        )

    # ─── Cancelar ─────────────────────────────────────────────────────────────

    def cancel(
        self,
        db: Session,
        company_id: UUID,
        appointment_id: UUID,
        reason: str | None = None,
    ) -> CancelResult:
        """
        Cancela um agendamento.
        Levanta PolicyViolationError se fora do prazo.
        """
        try:
            appointment_svc.cancel_appointment(
                db, company_id, appointment_id,
                user_id=None, reason=reason,
            )
        except PolicyViolationError:
            raise
        except HTTPException as e:
            if e.status_code == 404:
                raise BookingNotFoundError(appointment_id)
            raise

        return CancelResult(success=True, message="Agendamento cancelado com sucesso.")

    # ─── Reagendar ────────────────────────────────────────────────────────────

    def reschedule(
        self,
        db: Session,
        company_id: UUID,
        appointment_id: UUID,
        new_start_at: datetime,
    ) -> RescheduleResult:
        """
        Reagenda para new_start_at.
        Levanta PolicyViolationError se fora do prazo.
        Converte HTTPException 409 em SlotUnavailableError.
        """
        try:
            appt = appointment_svc.reschedule_appointment(
                db, company_id, appointment_id,
                RescheduleRequest(start_at=new_start_at),
                user_id=None,
            )
        except PolicyViolationError:
            raise
        except HTTPException as e:
            if e.status_code == 409:
                raise SlotUnavailableError(e.detail)
            if e.status_code == 404:
                raise BookingNotFoundError(appointment_id)
            raise

        return RescheduleResult(
            success=True,
            new_start_at=appt.start_at,
            message="Agendamento remarcado com sucesso.",
        )

    # ─── Agendamentos do cliente ──────────────────────────────────────────────

    def get_customer_appointments(
        self, db: Session, company_id: UUID, customer_id: UUID
    ) -> list[AppointmentSummary]:
        """Retorna agendamentos ativos futuros do cliente."""
        appts = appointment_svc.list_active_by_client(db, company_id, customer_id)
        return [
            AppointmentSummary(
                id=a.id,
                service_name=a.services[0].service_name if a.services else "Serviço",
                professional_name=a.professional.name if a.professional else "?",
                start_at=a.start_at,
                status=a.status,
            )
            for a in appts
        ]

    # ─── Oferta preditiva ─────────────────────────────────────────────────────

    def get_predictive_offer(
        self,
        db: Session,
        company_id: UUID,
        customer_id: UUID,
        offer_ttl_minutes: int = 5,
    ) -> Optional[PredictiveOfferResult]:
        """
        Busca último agendamento concluído do cliente e retorna uma oferta
        preditiva com o próximo slot disponível para o mesmo serviço+profissional.
        Retorna None se não houver histórico ou disponibilidade.
        """
        last_list = appointment_svc.list_completed_by_client(
            db, company_id, customer_id, limit=1
        )
        if not last_list:
            return None

        last = last_list[0]
        svc_id  = last.services[0].service_id if last.services else None
        prof_id = last.professional_id

        if not svc_id or not prof_id:
            return None

        slots = availability_svc.get_next_available_slots(
            db, company_id, prof_id, svc_id, days=7, limit=1
        )
        if not slots:
            return None

        svc_name  = last.services[0].service_name
        prof_name = last.professional.name if last.professional else "Profissional"

        return PredictiveOfferResult(
            service_id=svc_id,
            service_name=svc_name,
            professional_id=prof_id,
            professional_name=prof_name,
            next_slot=slots[0].start_at,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=offer_ttl_minutes),
        )


    # ─── BookingSession FSM ───────────────────────────────────────────────────

    # [FIX 1] Transições válidas atualizadas:
    #   - IDLE agora inicia em AWAITING_SERVICE (sem SET_CUSTOMER inicial)
    #   - Novo estado AWAITING_CUSTOMER inserido entre AWAITING_TIME e AWAITING_CONFIRMATION
    _VALID_TRANSITIONS: dict[tuple[str, str], str] = {
        ("IDLE",                    BookingAction.SELECT_SERVICE):      "_handle_select_service",
        ("AWAITING_SERVICE",        BookingAction.SELECT_SERVICE):      "_handle_select_service",
        ("AWAITING_PROFESSIONAL",   BookingAction.SELECT_PROFESSIONAL): "_handle_select_professional",
        ("AWAITING_DATE",           BookingAction.SELECT_DATE):         "_handle_select_date",
        ("AWAITING_DATE",           BookingAction.NAVIGATE_DATES):      "_handle_navigate_dates",
        ("AWAITING_SHIFT",          BookingAction.SELECT_SHIFT):        "_handle_select_shift",
        ("AWAITING_TIME",           BookingAction.SELECT_TIME):         "_handle_select_time",
        ("AWAITING_CUSTOMER",       BookingAction.SET_CUSTOMER):        "_handle_set_customer",  # [FIX 1] movido para cá
        ("AWAITING_CONFIRMATION",   BookingAction.CONFIRM):             "_handle_confirm",
        ("CONFIRMED",               BookingAction.RESCHEDULE_START):    "_handle_reschedule_start",
        ("CONFIRMED",               BookingAction.CANCEL_START):        "_handle_cancel_start",
        ("AWAITING_CANCEL_CONFIRM", BookingAction.CONFIRM_CANCEL):      "_handle_confirm_cancel",
    }

    # Definição dos turnos — ordem, labels e faixas de hora local
    _SHIFT_DEFS: list[tuple[str, str, str, int, int]] = [
        ("manha", "🌅 Manhã (até 12h)",    "turno_manha",  0, 12),
        ("tarde", "🌤 Tarde (12h – 18h)", "turno_tarde", 12, 18),
        ("noite", "🌙 Noite (após 18h)",  "turno_noite", 18, 24),
    ]

    def start_session(
        self,
        db: Session,
        company_id: UUID,
        channel: str,
        company_timezone: str = "America/Sao_Paulo",
    ) -> "BookingSession":
        """
        Cria e persiste uma nova BookingSession no estado IDLE.
        [FIX 1] O estado inicial é AWAITING_SERVICE — o fluxo começa pela
        escolha do serviço, sem solicitar dados do cliente antecipadamente.
        db.flush() popula o ID sem commitar — o caller controla o commit.
        """
        from app.infrastructure.db.models.booking_session import BookingSession

        session = BookingSession(
            company_id=company_id,
            channel=channel,
            company_timezone=company_timezone,
            # [FIX 1] Começa diretamente em AWAITING_SERVICE, não em IDLE
            state="AWAITING_SERVICE",
            expires_at=self._new_expiry(channel),
        )
        db.add(session)
        db.flush()
        return session

    def update(
        self,
        db: Session,
        session: "BookingSession",
        action: BookingAction,
        payload: dict,
    ) -> SessionUpdateResult:
        """
        Aplica uma ação ao BookingSession e retorna o novo estado + opções.

        Responsabilidades:
          - Validar que a ação é válida para o estado atual
          - Executar o handler correspondente
          - Atualizar last_action, last_action_at, expires_at
          - Retornar SessionUpdateResult (com opções prontas para o próximo passo)

        NÃO faz db.commit() — responsabilidade do caller.
        NÃO adquire lock — responsabilidade do endpoint (SELECT FOR UPDATE NOWAIT).
        """
        now = datetime.now(timezone.utc)

        # Guard: sessão expirada
        if session.expires_at and now > session.expires_at:
            raise SessionExpiredError(session_id=session.id)

        # Ações polimórficas — não dependem do estado atual
        if action == BookingAction.RESET:
            result = self._handle_reset(db, session, payload)
        elif action == BookingAction.BACK:
            result = self._handle_back(db, session, payload)
        elif action == BookingAction.CONFIRM and session.state == "CONFIRMED":
            # Idempotency replay: CONFIRM re-enviado após agendamento já criado.
            result = self._handle_confirm_replay(session)
        else:
            # Validar transição
            handler_name = self._VALID_TRANSITIONS.get((session.state, action))
            if not handler_name:
                raise InvalidActionError(
                    f"Ação '{action}' não é válida no estado '{session.state}'"
                )
            handler = getattr(self, handler_name)
            result = handler(db, session, payload)

        # Atualizar metadados de controle após ação bem-sucedida
        session.last_action    = action.value
        session.last_action_at = now
        session.expires_at     = self._new_expiry(session.channel)

        return result

    def get_options_for_state(self, db: Session, session: "BookingSession") -> list:
        """
        Re-lista as opções para o estado atual da sessão.
        Usado ao hidratar uma sessão retomada via token.
        [FIX 1] Inclui AWAITING_CUSTOMER (sem opções — formulário de dados).
        """
        ctx = session.context or {}
        state = session.state
        company_id = session.company_id
        tz = session.company_timezone

        if state in ("IDLE", "AWAITING_SERVICE"):
            return self.list_services(db, company_id)

        if state == "AWAITING_PROFESSIONAL":
            service_id = UUID(ctx["service_id"])
            return self.list_professionals(db, company_id, service_id)

        if state == "AWAITING_DATE":
            service_id  = UUID(ctx["service_id"])
            prof_id     = UUID(ctx["professional_id"]) if ctx.get("professional_id") else None
            offset_days = int(ctx.get("date_offset_days", 0))
            dates, has_next, has_previous = self.list_available_dates_paged(
                db, company_id, prof_id, service_id,
                offset_days=offset_days, window=settings.DATE_WINDOW_SIZE,
                reference_tz=tz,
            )
            # Atualiza context em memória para que o router possa ler os flags
            ctx = dict(ctx)
            ctx["dates_has_next"]    = has_next
            ctx["dates_has_previous"] = has_previous
            session.context = ctx
            return dates

        if state == "AWAITING_SHIFT":
            service_id   = UUID(ctx["service_id"])
            prof_id      = UUID(ctx["professional_id"]) if ctx.get("professional_id") else None
            target_date  = date.fromisoformat(ctx["selected_date"])
            return self.get_shift_availability(
                db, company_id, prof_id, service_id, target_date,
                company_timezone=tz,
            )

        if state == "AWAITING_TIME":
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            service_id  = UUID(ctx["service_id"])
            prof_id     = UUID(ctx["professional_id"]) if ctx.get("professional_id") else None
            target_date = date.fromisoformat(ctx["selected_date"])
            all_slots   = self.list_available_slots(
                db, company_id, prof_id, service_id, target_date,
                company_timezone=tz,
            )
            # Aplicar filtro de turno se selecionado (sessão retomada mantém o turno escolhido)
            selected_shift = ctx.get("selected_shift")
            if selected_shift:
                try:
                    company_tz = ZoneInfo(tz)
                except ZoneInfoNotFoundError:
                    company_tz = ZoneInfo("America/Sao_Paulo")
                all_slots = self._filter_slots_by_shift(all_slots, selected_shift, company_tz)
            return all_slots

        # [FIX 1] AWAITING_CUSTOMER: sem lista — frontend exibe formulário de dados
        # AWAITING_CONFIRMATION, AWAITING_CANCEL_CONFIRM, CONFIRMED, CANCELLED:
        # sem lista de opções — o cliente usa botões de confirmação
        return []

    # ─── Handlers privados ────────────────────────────────────────────────────

    def _handle_set_customer(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        [FIX 1] Identificação do cliente movida para APÓS a seleção de horário.
        Identifica ou cria o cliente pelo telefone.
        Armazena customer_id na sessão e snapshot de nome/telefone no context.
        Transição: AWAITING_CUSTOMER → AWAITING_CONFIRMATION.

        Atalho WhatsApp: se o payload contiver "customer_id", o cliente já foi
        identificado pelo canal (ex: WhatsApp com LID) e não é necessário coletar
        nome/telefone — o engine simplesmente carrega o cliente pelo ID.
        """
        # ── Atalho: WhatsApp já tem o cliente identificado ────────────────────
        direct_id = payload.get("customer_id")
        if direct_id:
            try:
                customer = customer_svc.get_customer_or_404(
                    db, session.company_id, UUID(str(direct_id))
                )
            except Exception as exc:
                raise InvalidActionError(
                    f"Cliente não encontrado: {direct_id}"
                ) from exc

            ctx = dict(session.context or {})
            ctx.update({
                "customer_name":  customer.name,
                "customer_phone": getattr(customer, "phone", "") or "",
                "customer_email": getattr(customer, "email", None),
            })
            session.customer_id = customer.id
            session.context = ctx
            session.state = "AWAITING_CONFIRMATION"
            return SessionUpdateResult(next_state="AWAITING_CONFIRMATION", options=[])

        # ── Fluxo web: coleta nome e telefone do usuário ──────────────────────
        name  = str(payload.get("name", "")).strip()
        phone = str(payload.get("phone", "")).strip()

        if len(name) < 2:
            raise InvalidActionError("Nome deve ter pelo menos 2 caracteres")
        if len(phone) < 10:
            raise InvalidActionError("Telefone inválido")

        customer = customer_svc.get_or_create_by_phone(
            db,
            company_id=session.company_id,
            phone=phone,
            name=name,
        )

        # [FIX 2] Montar ctx completo antes de uma única atribuição
        ctx = dict(session.context or {})
        ctx.update({
            "customer_name":  customer.name,
            "customer_phone": phone,
            "customer_email": payload.get("email"),
        })
        session.customer_id = customer.id
        session.context = ctx  # atribuição única — SQLAlchemy detecta corretamente
        session.state = "AWAITING_CONFIRMATION"

        return SessionUpdateResult(next_state="AWAITING_CONFIRMATION", options=[])

    def _handle_select_service(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Valida e armazena o serviço selecionado.
        [FIX 1] Aceita IDLE como estado de origem (além de AWAITING_SERVICE).
        [FIX 2] Contexto montado completamente antes de uma única atribuição.
        Transição: AWAITING_SERVICE → AWAITING_PROFESSIONAL.
        """
        service_id = self._resolve_id_from_payload(
            payload, "service_id", session.context.get("last_listed_services", [])
        )
        svc = service_svc.get_service_or_404(db, session.company_id, service_id)

        # [FIX 2] Listar opções ANTES de montar o ctx final
        options = self.list_professionals(db, session.company_id, svc.id)

        # [FIX 2] Montar ctx completo (incluindo last_listed_professionals) antes
        # de uma única atribuição — garante que o SQLAlchemy rastreie a mudança
        ctx = dict(session.context or {})
        ctx.update({
            "service_id":               str(svc.id),
            "service_name":             svc.name,
            "service_price":            str(svc.price),
            "service_duration_minutes": int(svc.duration),
            "last_listed_professionals": [
                {"id": str(o.id) if o.id else None, "name": o.name, "row_key": o.row_key}
                for o in options
            ],
        })
        session.context = ctx  # atribuição única
        session.state = "AWAITING_PROFESSIONAL"

        return SessionUpdateResult(next_state="AWAITING_PROFESSIONAL", options=options)

    def _handle_select_professional(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Valida e armazena o profissional selecionado (ou None para "qualquer").
        [FIX 2] Contexto montado completamente antes de uma única atribuição.
        Transição: AWAITING_PROFESSIONAL → AWAITING_DATE.
        """
        ctx = dict(session.context or {})

        if payload.get("row_key") == "prof_any" or payload.get("professional_id") == "any":
            prof_id = None
            prof_name = "Qualquer disponível"
        else:
            prof_id = self._resolve_id_from_payload(
                payload, "professional_id",
                ctx.get("last_listed_professionals", [])
            )
            prof = professional_svc.get_professional_or_404(db, session.company_id, prof_id)
            prof_name = prof.name

        # [FIX 2] Listar opções ANTES de montar o ctx final (paginado, janela inicial)
        options, has_next, _ = self.list_available_dates_paged(
            db, session.company_id, prof_id,
            UUID(ctx["service_id"]),
            offset_days=0, window=settings.DATE_WINDOW_SIZE,
            reference_tz=session.company_timezone,
        )

        # [FIX 2] Montar ctx completo e fazer uma única atribuição
        ctx.update({
            "professional_id":   str(prof_id) if prof_id else None,
            "professional_name": prof_name,
            "date_offset_days":  0,
            "dates_has_next":    has_next,
            "dates_has_previous": False,
            "last_listed_dates": [
                {"date": str(o.date), "label": o.label,
                 "has_availability": o.has_availability, "row_key": o.row_key}
                for o in options
            ],
        })
        session.context = ctx  # atribuição única
        session.state = "AWAITING_DATE"

        return SessionUpdateResult(
            next_state="AWAITING_DATE", options=options,
            dates_has_next=has_next, dates_has_previous=False,
        )

    def _handle_select_date(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Armazena a data e lista os turnos disponíveis do dia.
        [FIX 2] Contexto montado completamente antes de uma única atribuição.
        Transição: AWAITING_DATE → AWAITING_SHIFT.
        """
        ctx = dict(session.context or {})

        if "row_key" in payload:
            listed = ctx.get("last_listed_dates", [])
            matched = next((d for d in listed if d["row_key"] == payload["row_key"]), None)
            if not matched:
                raise InvalidActionError(f"row_key '{payload['row_key']}' não encontrado na sessão")
            selected_date = date.fromisoformat(matched["date"])
        elif "date" in payload:
            selected_date = date.fromisoformat(str(payload["date"]))
        else:
            raise InvalidActionError("payload deve ter 'date' ou 'row_key'")

        prof_id = UUID(ctx["professional_id"]) if ctx.get("professional_id") else None

        # [FIX 2] Calcular disponibilidade por turno ANTES de montar o ctx final
        shift_options = self.get_shift_availability(
            db, session.company_id, prof_id, UUID(ctx["service_id"]), selected_date,
            company_timezone=session.company_timezone,
        )

        # [FIX 2] Montar ctx completo e fazer uma única atribuição
        # Limpar metadados de navegação de datas e turno anterior — não são mais necessários
        ctx.pop("date_offset_days", None)
        ctx.pop("dates_has_next", None)
        ctx.pop("dates_has_previous", None)
        ctx.pop("selected_shift", None)
        ctx.pop("last_listed_slots", None)
        ctx.update({
            "selected_date": selected_date.isoformat(),
            "last_listed_shifts": [
                {
                    "shift":            o.shift,
                    "label":            o.label,
                    "slot_count":       o.slot_count,
                    "has_availability": o.has_availability,
                    "row_key":          o.row_key,
                }
                for o in shift_options
            ],
        })
        session.context = ctx  # atribuição única
        session.state = "AWAITING_SHIFT"

        return SessionUpdateResult(next_state="AWAITING_SHIFT", options=shift_options)

    def _handle_select_shift(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Armazena o turno selecionado e lista os slots filtrados.
        Rejeita turnos sem disponibilidade (has_availability=False).
        Transição: AWAITING_SHIFT → AWAITING_TIME.
        """
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        shift = str(payload.get("shift", "")).lower()
        if shift not in ("manha", "tarde", "noite"):
            raise InvalidActionError("Turno inválido. Use: manha, tarde ou noite")

        ctx = dict(session.context or {})

        # Verificar disponibilidade do turno (usa cache do ctx se disponível)
        listed_shifts = ctx.get("last_listed_shifts", [])
        cached = next((s for s in listed_shifts if s.get("shift") == shift), None)
        if cached and not cached.get("has_availability", True):
            raise InvalidActionError(
                f"O turno '{shift}' não tem horários disponíveis. "
                "Escolha outro turno ou outra data."
            )

        selected_date = date.fromisoformat(ctx["selected_date"])
        prof_id = UUID(ctx["professional_id"]) if ctx.get("professional_id") else None

        # [FIX 2] Listar slots ANTES de montar o ctx final
        all_slots = self.list_available_slots(
            db, session.company_id, prof_id, UUID(ctx["service_id"]), selected_date,
            limit=0, company_timezone=session.company_timezone,
        )

        try:
            tz = ZoneInfo(session.company_timezone)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("America/Sao_Paulo")

        filtered = self._filter_slots_by_shift(all_slots, shift, tz)
        display_slots = filtered[:settings.BOT_MAX_SLOTS_DISPLAYED]

        if not display_slots:
            raise InvalidActionError(
                f"Não há horários disponíveis neste turno. "
                "Escolha outro turno ou outra data."
            )

        # [FIX 2] Montar ctx completo e fazer uma única atribuição
        ctx.update({
            "selected_shift": shift,
            "last_listed_slots": [
                {
                    "start_at":          o.start_at.isoformat(),
                    "end_at":            o.end_at.isoformat(),
                    "professional_id":   str(o.professional_id),
                    "professional_name": o.professional_name,
                    "row_key":           o.row_key,
                }
                for o in display_slots
            ],
        })
        session.context = ctx  # atribuição única
        session.state = "AWAITING_TIME"

        return SessionUpdateResult(next_state="AWAITING_TIME", options=display_slots)

    def _handle_select_time(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Armazena o slot selecionado e gera a idempotency_key.
        [FIX 1] Transição: AWAITING_TIME → AWAITING_CUSTOMER (não mais AWAITING_CONFIRMATION).
        [FIX 2] Contexto montado completamente antes de uma única atribuição.
        [FIX 3] slot_start_at serializado com timezone da empresa já aplicado.
        """
        ctx = dict(session.context or {})

        if "row_key" in payload:
            listed = ctx.get("last_listed_slots", [])
            matched = next((s for s in listed if s["row_key"] == payload["row_key"]), None)
            if not matched:
                raise InvalidActionError(f"row_key '{payload['row_key']}' não encontrado na sessão")
            slot_start = matched["start_at"]
            slot_end   = matched["end_at"]
            prof_id    = matched["professional_id"]
        elif "start_at" in payload:
            # [FIX 3] Web envia ISO — converter para timezone da empresa antes de salvar
            raw_start = datetime.fromisoformat(str(payload["start_at"]))
            slot_start = self._to_company_tz(raw_start, session.company_timezone).isoformat()
            raw_end = payload.get("end_at")
            slot_end = (
                self._to_company_tz(datetime.fromisoformat(str(raw_end)), session.company_timezone).isoformat()
                if raw_end else ""
            )
            prof_id = str(payload.get("professional_id", ctx.get("professional_id", "")))
        else:
            raise InvalidActionError("payload deve ter 'start_at' ou 'row_key'")

        # Gerar chave de idempotência — evita double-booking por duplo clique
        customer_phone = ctx.get("customer_phone", str(session.customer_id or ""))
        idempotency_key = (
            f"session|{customer_phone}|{ctx.get('service_id', '')}|{slot_start}"
        )

        # [FIX 2] Montar ctx completo e fazer uma única atribuição
        ctx.update({
            "slot_start_at":   slot_start,
            "slot_end_at":     slot_end,
            "professional_id": prof_id,
            "idempotency_key": idempotency_key,
        })
        session.context = ctx  # atribuição única
        # [FIX 1] Próximo estado é AWAITING_CUSTOMER, não AWAITING_CONFIRMATION
        session.state = "AWAITING_CUSTOMER"

        return SessionUpdateResult(next_state="AWAITING_CUSTOMER", options=[])

    def _handle_confirm(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Cria o agendamento.

        Proteção em 3 camadas:
          1. SELECT FOR UPDATE NOWAIT no endpoint (exclui requisições simultâneas)
          2. Transição para CONFIRMING + db.flush() antes de criar (guard de state)
          3. idempotency_key UNIQUE no banco (fallback final)

        Idempotência: se last_action já for CONFIRM e appointment_id existir,
        retorna o resultado existente sem re-criar.
        """
        ctx = session.context or {}

        # Camada de idempotência — replay de CONFIRM após sucesso anterior
        if (session.last_action == BookingAction.CONFIRM.value
                and session.appointment_id is not None):
            try:
                existing = appointment_svc.get_appointment_or_404(
                    db, session.company_id, session.appointment_id
                )
                svc_name  = existing.services[0].service_name if existing.services else ctx.get("service_name", "")
                prof_name = existing.professional.name if existing.professional else ctx.get("professional_name", "")
                return SessionUpdateResult(
                    next_state="CONFIRMED",
                    options=[],
                    confirmation_data=BookingResult(
                        appointment_id=existing.id,
                        service_name=svc_name,
                        professional_name=prof_name,
                        start_at=existing.start_at,
                        end_at=existing.end_at,
                        total_amount=existing.total_amount,
                    ),
                    idempotent_replay=True,
                )
            except Exception:
                pass

        if not session.customer_id:
            raise InvalidActionError("Cliente não identificado na sessão")

        for field_name in ("service_id", "professional_id", "slot_start_at", "idempotency_key"):
            if not ctx.get(field_name):
                raise InvalidActionError(f"Contexto incompleto: falta '{field_name}'")

        # Camada 2: transição para CONFIRMING antes de criar
        session.state = "CONFIRMING"
        db.flush()

        service_id = UUID(ctx["service_id"])
        svc = service_svc.get_service_or_404(db, session.company_id, service_id)

        intent = BookingIntent(
            company_id=session.company_id,
            customer_id=session.customer_id,
            professional_id=UUID(ctx["professional_id"]),
            service_id=svc.id,
            start_at=datetime.fromisoformat(ctx["slot_start_at"]),
            idempotency_key=ctx["idempotency_key"],
        )

        try:
            result = self.confirm(db, session.company_id, intent)
        except SlotUnavailableError:
            # Slot tomado — voltar para seleção de horário e re-listar slots
            ctx2 = dict(ctx)
            ctx2.pop("slot_start_at", None)
            ctx2.pop("slot_end_at", None)
            ctx2.pop("idempotency_key", None)

            prof_id = UUID(ctx["professional_id"]) if ctx.get("professional_id") else None
            try:
                target_date = date.fromisoformat(ctx["selected_date"])
                # [FIX 3] Passar company_timezone na re-listagem de slots
                options = self.list_available_slots(
                    db, session.company_id, prof_id, svc.id, target_date,
                    limit=settings.BOT_MAX_SLOTS_DISPLAYED,
                    company_timezone=session.company_timezone,
                )
                # [FIX 2] Atualizar last_listed_slots na mesma atribuição
                ctx2["last_listed_slots"] = [
                    {
                        "start_at":          o.start_at.isoformat(),
                        "end_at":            o.end_at.isoformat(),
                        "professional_id":   str(o.professional_id),
                        "professional_name": o.professional_name,
                        "row_key":           o.row_key,
                    }
                    for o in options
                ]
            except Exception:
                options = []

            session.context = ctx2  # atribuição única
            session.state = "AWAITING_TIME"

            return SessionUpdateResult(
                next_state="AWAITING_TIME",
                options=options,
                error="SLOT_UNAVAILABLE",
            )

        session.appointment_id = result.appointment_id
        session.state = "CONFIRMED"
        return SessionUpdateResult(
            next_state="CONFIRMED",
            options=[],
            confirmation_data=result,
        )

    def _handle_confirm_replay(self, session: "BookingSession") -> SessionUpdateResult:
        """
        Idempotency replay: retorna os dados do agendamento já criado sem DB adicional.
        Chamado quando CONFIRM é enviado com a sessão já em estado CONFIRMED.
        """
        ctx = session.context or {}
        start_raw = ctx.get("slot_start_at")
        end_raw   = ctx.get("slot_end_at")

        if not start_raw or not session.appointment_id:
            return SessionUpdateResult(next_state="CONFIRMED", options=[], idempotent_replay=True)

        confirmation = BookingResult(
            appointment_id=session.appointment_id,
            service_name=ctx.get("service_name", ""),
            professional_name=ctx.get("professional_name", ""),
            start_at=datetime.fromisoformat(start_raw),
            end_at=datetime.fromisoformat(end_raw) if end_raw else datetime.fromisoformat(start_raw),
            total_amount=Decimal(str(ctx.get("service_price", "0"))),
        )
        return SessionUpdateResult(
            next_state="CONFIRMED",
            options=[],
            confirmation_data=confirmation,
            idempotent_replay=True,
        )

    def _handle_cancel_start(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Inicia fluxo de cancelamento.
        [FIX 2] Contexto montado completamente antes de uma única atribuição.
        Transição: CONFIRMED → AWAITING_CANCEL_CONFIRM.
        """
        appt_id = payload.get("appointment_id")
        if not appt_id:
            raise InvalidActionError("payload deve ter 'appointment_id'")

        appointment_svc.get_appointment_or_404(db, session.company_id, UUID(appt_id))

        # [FIX 2] Montar ctx completo e fazer uma única atribuição
        ctx = dict(session.context or {})
        ctx["managing_appointment_id"] = str(appt_id)
        session.context = ctx  # atribuição única
        session.state = "AWAITING_CANCEL_CONFIRM"

        return SessionUpdateResult(next_state="AWAITING_CANCEL_CONFIRM", options=[])

    def _handle_confirm_cancel(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Executa o cancelamento confirmado pelo usuário.
        Transição: AWAITING_CANCEL_CONFIRM → CANCELLED.
        """
        appt_id_str = (session.context or {}).get("managing_appointment_id")
        if not appt_id_str:
            raise InvalidActionError("Nenhum agendamento selecionado para cancelamento")

        result = self.cancel(
            db, session.company_id, UUID(appt_id_str),
            reason="Cancelado pelo cliente"
        )

        session.state = "CANCELLED"
        return SessionUpdateResult(
            next_state="CANCELLED",
            options=[],
            cancel_data=result,
        )

    def _handle_reschedule_start(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Inicia fluxo de reagendamento.
        [FIX 2] Contexto montado completamente antes de uma única atribuição.
        [FIX 3] Datas listadas com timezone da empresa.
        Transição: CONFIRMED → AWAITING_DATE.
        """
        appt_id = payload.get("appointment_id")
        if not appt_id:
            raise InvalidActionError("payload deve ter 'appointment_id'")

        appt = appointment_svc.get_appointment_or_404(db, session.company_id, UUID(appt_id))

        ctx = dict(session.context or {})
        ctx["managing_appointment_id"] = str(appt_id)
        ctx["is_rescheduling"] = True

        if not ctx.get("service_id") and appt.services:
            ctx["service_id"] = str(appt.services[0].service_id)
        if not ctx.get("professional_id"):
            ctx["professional_id"] = str(appt.professional_id)

        prof_id = UUID(ctx["professional_id"]) if ctx.get("professional_id") else None

        # [FIX 2] Listar datas ANTES de montar o ctx final (paginado, janela inicial)
        options, has_next, _ = self.list_available_dates_paged(
            db, session.company_id, prof_id,
            UUID(ctx["service_id"]),
            offset_days=0, window=settings.DATE_WINDOW_SIZE,
            reference_tz=session.company_timezone,
        )

        # [FIX 2] Montar ctx completo e fazer uma única atribuição
        ctx["date_offset_days"]  = 0
        ctx["dates_has_next"]    = has_next
        ctx["dates_has_previous"] = False
        ctx["last_listed_dates"] = [
            {"date": str(o.date), "label": o.label,
             "has_availability": o.has_availability, "row_key": o.row_key}
            for o in options
        ]
        session.context = ctx  # atribuição única
        session.state = "AWAITING_DATE"

        return SessionUpdateResult(
            next_state="AWAITING_DATE", options=options,
            dates_has_next=has_next, dates_has_previous=False,
        )

    def _handle_navigate_dates(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Avança ou recua a janela de datas exibidas — não muda o estado FSM.
        payload: {offset_days: int}  (0 = hoje, 7 = próxima semana, ...)
        Transição: AWAITING_DATE → AWAITING_DATE (self-transition).
        """
        offset_days = max(0, int(payload.get("offset_days", 0)))
        ctx = dict(session.context or {})

        svc_id  = UUID(ctx["service_id"])
        prof_id = UUID(ctx["professional_id"]) if ctx.get("professional_id") else None

        dates, has_next, has_previous = self.list_available_dates_paged(
            db, session.company_id, prof_id, svc_id,
            offset_days=offset_days, window=settings.DATE_WINDOW_SIZE,
            reference_tz=session.company_timezone,
        )

        ctx["date_offset_days"]  = offset_days
        ctx["dates_has_next"]    = has_next
        ctx["dates_has_previous"] = has_previous
        ctx["last_listed_dates"] = [
            {"date": str(o.date), "label": o.label,
             "has_availability": o.has_availability, "row_key": o.row_key}
            for o in dates
        ]
        session.context = ctx
        # estado permanece AWAITING_DATE

        return SessionUpdateResult(
            next_state="AWAITING_DATE", options=dates,
            dates_has_next=has_next, dates_has_previous=has_previous,
        )

    def _handle_reset(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Volta ao início — limpa seleções mas preserva dados do cliente se já coletados.
        [FIX 1] Preserva também customer_id caso o cliente já tenha se identificado.
        Válido em qualquer estado.
        """
        ctx = session.context or {}
        preserved = {
            k: ctx[k] for k in (
                "customer_name", "customer_phone", "customer_email",
                "last_service_id", "last_professional_id",
            )
            if k in ctx
        }

        options = self.list_services(db, session.company_id)

        # [FIX 2] Montar ctx completo e fazer uma única atribuição
        preserved["last_listed_services"] = [
            {"id": str(o.id), "name": o.name, "price": str(o.price),
             "duration_minutes": o.duration_minutes, "row_key": o.row_key}
            for o in options
        ]
        session.context = preserved  # atribuição única
        session.state = "AWAITING_SERVICE"

        return SessionUpdateResult(next_state="AWAITING_SERVICE", options=options)

    def _handle_back(
        self, db: Session, session: "BookingSession", payload: dict
    ) -> SessionUpdateResult:
        """
        Volta um passo no fluxo e re-lista as opções do passo anterior.
        """
        prev_state = _BACK_STATE.get(session.state)
        if not prev_state:
            return self._handle_reset(db, session, payload)

        session.state = prev_state
        options = self.get_options_for_state(db, session)
        return SessionUpdateResult(next_state=prev_state, options=options)

    # ─── Helpers internos ─────────────────────────────────────────────────────

    @staticmethod
    def _new_expiry(channel: str) -> datetime:
        ttl = _CHANNEL_TTL.get(channel, timedelta(minutes=15))
        return datetime.now(timezone.utc) + ttl

    @staticmethod
    def _resolve_id_from_payload(
        payload: dict,
        id_key: str,
        listed: list,
    ) -> UUID:
        """
        Resolve UUID a partir de payload com 'row_key' ou com o id direto.
        Suporta:
          - Web: envia {service_id: "uuid"}
          - Bot: envia {row_key: "serv_1"}
        """
        if "row_key" in payload:
            row_key = payload["row_key"]
            matched = next((item for item in listed if item.get("row_key") == row_key), None)
            if not matched:
                raise InvalidActionError(f"row_key '{row_key}' não encontrado na sessão")
            raw_id = matched.get("id")
            if not raw_id:
                raise InvalidActionError(f"Item com row_key '{row_key}' não tem id")
            return UUID(str(raw_id))

        if id_key in payload:
            return UUID(str(payload[id_key]))

        raise InvalidActionError(f"payload deve ter '{id_key}' ou 'row_key'")


# Instância singleton — stateless, segura para reuso
booking_engine = BookingEngine()