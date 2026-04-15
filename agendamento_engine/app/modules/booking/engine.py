"""
BookingEngine — orquestrador central de agendamento.

Responsabilidades:
  - Listar serviços, profissionais, datas e horários disponíveis
  - Confirmar, cancelar e reagendar agendamentos
  - Retornar oferta preditiva para clientes recorrentes

Contrato:
  - Agnóstico de canal: não importa nada de whatsapp/ nem de routers HTTP
  - Não formata mensagens, não gerencia sessões, não envia notificações
  - Recebe IDs e datetimes, devolve estruturas tipadas de booking/schemas.py
  - Delega toda lógica de domínio aos services existentes (appointments, availability, etc.)
  - Converte HTTPException 409 em SlotUnavailableError (agnóstica de canal)
"""
import logging
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from typing import Optional
from uuid import UUID

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
from app.modules.professionals import service as professional_svc
from app.modules.services import service as service_svc
from app.core.config import settings

from app.modules.booking.schemas import (
    ServiceOption,
    ProfessionalOption,
    DateOption,
    SlotOption,
    BookingIntent,
    BookingResult,
    AppointmentSummary,
    PredictiveOfferResult,
    CancelResult,
    RescheduleResult,
)
from app.modules.booking.exceptions import SlotUnavailableError, BookingNotFoundError

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


def _label_date(d: date) -> str:
    today = datetime.now(timezone.utc).date()
    if d == today:
        return f"Hoje ({d.strftime('%d/%m')})"
    if d == today + timedelta(days=1):
        return f"Amanhã ({d.strftime('%d/%m')})"
    return f"{_DIAS_PT[d.weekday()]} ({d.strftime('%d/%m')})"


class BookingEngine:
    """
    Orquestrador central de agendamento.
    Instanciar uma vez por módulo; é stateless (sem estado de instância).
    """

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

    def list_available_dates(
        self,
        db: Session,
        company_id: UUID,
        professional_id: Optional[UUID],
        service_id: UUID,
        days: int = 30,
    ) -> list[DateOption]:
        """
        Retorna os próximos <days> dias com indicação de disponibilidade.
        Se professional_id=None, verifica qualquer profissional do serviço.
        """
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
                label=_label_date(d),
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
    ) -> list[SlotOption]:
        """
        Retorna slots disponíveis para a data.
        Se professional_id=None, agrega slots de todos os profissionais do serviço.
        limit=0 significa sem limite.
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
                start_at=s.start_at,
                end_at=s.end_at,
                professional_id=s.professional_id,
                professional_name=s.professional_name,
                row_key=f"slot_{i + 1}",
            )
            for i, s in enumerate(raw)
        ]

    def list_next_available_slots(
        self,
        db: Session,
        company_id: UUID,
        professional_id: Optional[UUID],
        service_id: UUID,
        days: int = 30,
        limit: int = 0,
    ) -> list[SlotOption]:
        """
        Retorna os próximos slots disponíveis nos próximos <days> dias.
        Usado quando o cliente ainda não escolheu uma data.
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
                start_at=s.start_at,
                end_at=s.end_at,
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


# Instância singleton — stateless, segura para reuso
booking_engine = BookingEngine()
