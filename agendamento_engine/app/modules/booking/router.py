"""
Router público de agendamento online.

Acesso por company slug — sem autenticação JWT.
Validação de acesso: empresa deve existir, estar ativa e com online_booking_enabled=True.
Exceção: /info não exige online_booking_enabled (a landing page precisa saber o status).

Endpoints legados (stateless — mantidos para compatibilidade):
  GET  /booking/{slug}/info
  GET  /booking/{slug}/services
  GET  /booking/{slug}/professionals
  GET  /booking/{slug}/dates
  GET  /booking/{slug}/slots
  POST /booking/{slug}/confirm
  GET  /booking/{slug}/appointments
  PATCH /booking/{slug}/appointments/{appointment_id}/cancel

Endpoints FSM BookingSession (Fase 2):
  POST /booking/{slug}/start              — cria sessão, retorna token
  POST /booking/{slug}/update             — aplica ação FSM (SELECT FOR UPDATE NOWAIT)
  GET  /booking/{slug}/session/{token}    — retoma sessão pelo token
"""
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.infrastructure.db.session import get_db
from app.infrastructure.db.models.company import Company
from app.infrastructure.db.models.company_settings import CompanySettings
from app.infrastructure.db.models.company_profile import CompanyProfile
from app.infrastructure.db.models.booking_session import BookingSession
from app.modules.booking.engine import booking_engine
from app.modules.booking.exceptions import SlotUnavailableError, BookingNotFoundError
from app.modules.booking.actions import BookingAction, SessionExpiredError, InvalidActionError
from app.modules.booking.schemas import (
    BookingIntent,
    ServiceOption,
    ProfessionalOption,
    DateOption,
    SlotOption,
    ShiftOption,
)
from app.modules.booking.http_schemas import (
    # Legados
    CompanyInfoResponse,
    CompanyProfileResponse,
    ServiceOptionResponse,
    ProfessionalOptionResponse,
    DateOptionResponse,
    SlotOptionResponse,
    ConfirmBookingRequest,
    BookingResultResponse,
    AppointmentSummaryResponse,
    CancelBookingRequest,
    CancelResultResponse,
    # FSM
    ServiceOptionHTTP,
    ProfessionalOptionHTTP,
    DateOptionHTTP,
    SlotOptionHTTP,
    ShiftOptionHTTP,
    ConfirmationHTTP,
    CancelConfirmationHTTP,
    ContextSummaryHTTP,
    StartSessionRequest,
    StartSessionResponse,
    UpdateSessionRequest,
    UpdateSessionResponse,
    SessionStateResponse,
    DatesPageResponse,
)
from app.modules.customers import service as customer_svc
from app.modules.appointments.polices import PolicyViolationError
from app.core.config import settings
import uuid as uuidlib

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/booking", tags=["booking-public"])


# ─── Dependências de rota ─────────────────────────────────────────────────────

def _get_company_or_404(slug: str, db: Session) -> Company:
    """Resolve slug → Company. Levanta 404 se não encontrada ou inativa."""
    company = (
        db.query(Company)
        .filter(Company.slug == slug, Company.active == True)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return company


def _get_settings(company_id: UUID, db: Session) -> Optional[CompanySettings]:
    return (
        db.query(CompanySettings)
        .filter(CompanySettings.company_id == company_id)
        .first()
    )


def _require_online_booking(slug: str, db: Session) -> tuple[Company, CompanySettings]:
    """
    Valida que a empresa aceita agendamento online.
    Usado por todos os endpoints operacionais (não o /info).
    """
    company = _get_company_or_404(slug, db)
    settings = _get_settings(company.id, db)

    if not settings or not settings.online_booking_enabled:
        raise HTTPException(
            status_code=403,
            detail="Esta empresa não aceita agendamentos online no momento",
        )
    return company, settings


# ─── 4.2 — Info da empresa ───────────────────────────────────────────────────

@router.get("/{slug}/info", response_model=CompanyInfoResponse)
def get_company_info(slug: str, db: Session = Depends(get_db)):
    """
    Retorna status público da empresa.
    Não exige online_booking_enabled — a landing page precisa saber se pode abrir o fluxo.
    """
    company = _get_company_or_404(slug, db)
    company_settings = _get_settings(company.id, db)

    services_count = (
        len(booking_engine.list_services(db, company.id))
        if (company_settings and company_settings.online_booking_enabled)
        else 0
    )

    return CompanyInfoResponse(
        company_name=company.name,
        active=company.active,
        online_booking_enabled=bool(company_settings and company_settings.online_booking_enabled),
        services_count=services_count,
        booking_url=f"{settings.BOOKING_BASE_URL}/{company.slug}",
    )

@router.get("/{slug}/profile", response_model=CompanyProfileResponse)
def get_company_profile(slug: str, db: Session = Depends(get_db)):
    """
    Retorna o perfil público da empresa para exibição na landing page.
    Não exige online_booking_enabled — a landing page deve sempre carregar.
    """

    company = _get_company_or_404(slug, db)

    profile = db.query(CompanyProfile).filter(
        CompanyProfile.company_id == company.id
    ).first()

    cfg = _get_settings(company.id, db)

    return CompanyProfileResponse(
        company_name=company.name,
        tagline=profile.tagline if profile else None,
        description=profile.description if profile else None,
        logo_url=profile.logo_url if profile else None,
        cover_url=profile.cover_url if profile else None,
        gallery_urls=profile.gallery_urls if (profile and profile.gallery_urls) else [],
        address=profile.address if profile else None,
        city=profile.city if profile else None,
        whatsapp=profile.whatsapp if profile else None,
        maps_url=profile.maps_url if profile else None,
        instagram_url=profile.instagram_url if profile else None,
        facebook_url=profile.facebook_url if profile else None,
        tiktok_url=profile.tiktok_url if profile else None,
        google_review_url=profile.google_review_url if profile else None,
        business_hours=profile.business_hours if profile else None,
        online_booking_enabled=bool(cfg and cfg.online_booking_enabled),
    )

# ─── 4.1 — Serviços ──────────────────────────────────────────────────────────

@router.get("/{slug}/services", response_model=list[ServiceOptionResponse])
def list_services(slug: str, db: Session = Depends(get_db)):
    """Lista serviços ativos da empresa."""
    company, _ = _require_online_booking(slug, db)
    options = booking_engine.list_services(db, company.id)
    return [
        ServiceOptionResponse(
            id=o.id,
            name=o.name,
            price=o.price,
            duration_minutes=o.duration_minutes,
            row_key=o.row_key,
        )
        for o in options
    ]


# ─── 4.1 — Profissionais ─────────────────────────────────────────────────────

@router.get("/{slug}/professionals", response_model=list[ProfessionalOptionResponse])
def list_professionals(
    slug: str,
    service_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """Lista profissionais disponíveis para o serviço."""
    company, _ = _require_online_booking(slug, db)
    options = booking_engine.list_professionals(db, company.id, service_id)
    return [
        ProfessionalOptionResponse(id=o.id, name=o.name, row_key=o.row_key)
        for o in options
    ]


# ─── 4.1 — Datas disponíveis ─────────────────────────────────────────────────

@router.get("/{slug}/dates", response_model=DatesPageResponse)
def list_available_dates(
    slug: str,
    service_id: UUID = Query(...),
    professional_id: Optional[UUID] = Query(None),
    offset_days: int = Query(0, ge=0, le=365),
    window: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """
    Retorna uma janela de <window> dias com indicação de disponibilidade.

    offset_days — dias a partir de hoje para iniciar a janela (default 0).
    window      — tamanho da janela em dias (default 7, máx 30).
    has_next    — True se há disponibilidade em algum dia da próxima janela.
    has_previous — True se offset_days > 0.
    professional_id omitido = qualquer profissional do serviço.
    """
    company, _ = _require_online_booking(slug, db)
    tz = company.timezone or settings.DEFAULT_COMPANY_TIMEZONE
    dates, has_next, has_previous = booking_engine.list_available_dates_paged(
        db, company.id, professional_id, service_id,
        offset_days=offset_days, window=window,
        reference_tz=tz,
    )
    return DatesPageResponse(
        dates=[
            DateOptionResponse(
                date=o.date,
                label=o.label,
                has_availability=o.has_availability,
                row_key=o.row_key,
            )
            for o in dates
        ],
        has_next=has_next,
        has_previous=has_previous,
        offset_days=offset_days,
        window=window,
    )


# ─── 4.1 — Slots disponíveis ─────────────────────────────────────────────────

@router.get("/{slug}/slots", response_model=list[SlotOptionResponse])
def list_available_slots(
    slug: str,
    service_id: UUID = Query(...),
    target_date: date = Query(...),
    professional_id: Optional[UUID] = Query(None),
    shift: Optional[str] = Query(None, description="Filtro de turno: manha | tarde | noite"),
    db: Session = Depends(get_db),
):
    """
    Retorna slots disponíveis para a data.
    professional_id omitido = agrega todos os profissionais do serviço.
    shift (opcional) filtra por período do dia: manha (<12h), tarde (12–18h), noite (≥18h).
    """
    company, _ = _require_online_booking(slug, db)
    tz = company.timezone or settings.DEFAULT_COMPANY_TIMEZONE
    options = booking_engine.list_available_slots(
        db, company.id, professional_id, service_id, target_date,
        company_timezone=tz,
    )

    # Aplicar filtro de turno se fornecido
    if shift and shift in ("manha", "tarde", "noite"):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            company_tz = ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            company_tz = ZoneInfo("America/Sao_Paulo")
        options = booking_engine._filter_slots_by_shift(options, shift, company_tz)

    return [
        SlotOptionResponse(
            start_at=o.start_at,
            end_at=o.end_at,
            professional_id=o.professional_id,
            professional_name=o.professional_name,
            row_key=o.row_key,
        )
        for o in options
    ]


# ─── 4.1 — Confirmar agendamento ─────────────────────────────────────────────

@router.post("/{slug}/confirm", response_model=BookingResultResponse, status_code=201)
def confirm_booking(
    slug: str,
    body: ConfirmBookingRequest,
    db: Session = Depends(get_db),
):
    """
    Identifica ou cria o cliente pelo telefone e confirma o agendamento.
    Retorna 409 se o slot já foi ocupado (race condition).
    """
    company, _ = _require_online_booking(slug, db)

    # Identifica ou cria o cliente pelo telefone
    customer = customer_svc.get_or_create_by_phone(
        db, company.id, body.customer_phone, body.customer_name
    )

    intent = BookingIntent(
        company_id=company.id,
        customer_id=customer.id,
        professional_id=body.professional_id,
        service_id=body.service_id,
        start_at=body.start_at,
        idempotency_key=body.idempotency_key,
    )

    try:
        result = booking_engine.confirm(db, company.id, intent)
    except SlotUnavailableError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return BookingResultResponse(
        appointment_id=result.appointment_id,
        service_name=result.service_name,
        professional_name=result.professional_name,
        start_at=result.start_at,
        end_at=result.end_at,
        total_amount=result.total_amount,
    )


# ─── 4.1 — Agendamentos do cliente ───────────────────────────────────────────

@router.get("/{slug}/appointments", response_model=list[AppointmentSummaryResponse])
def list_customer_appointments(
    slug: str,
    phone: str = Query(..., description="Telefone do cliente para identificação"),
    db: Session = Depends(get_db),
):
    """
    Retorna agendamentos ativos do cliente identificado pelo telefone.
    Retorna lista vazia se cliente não encontrado (não expõe 404 publicamente).
    """
    company, _ = _require_online_booking(slug, db)

    customer = customer_svc.get_by_phone(db, company.id, phone)
    if not customer:
        return []

    summaries = booking_engine.get_customer_appointments(db, company.id, customer.id)
    return [
        AppointmentSummaryResponse(
            id=s.id,
            service_name=s.service_name,
            professional_name=s.professional_name,
            start_at=s.start_at,
            status=s.status,
        )
        for s in summaries
    ]


# ─── 4.1 — Cancelar agendamento ──────────────────────────────────────────────

@router.patch(
    "/{slug}/appointments/{appointment_id}/cancel",
    response_model=CancelResultResponse,
)
def cancel_booking(
    slug: str,
    appointment_id: UUID,
    body: CancelBookingRequest,
    db: Session = Depends(get_db),
):
    """
    Cancela um agendamento.
    Valida que o telefone enviado pertence ao cliente dono do agendamento.
    Retorna 403 se fora do prazo de cancelamento (PolicyViolationError).
    """
    company, _ = _require_online_booking(slug, db)

    # Valida que o telefone corresponde ao dono do agendamento
    customer = customer_svc.get_by_phone(db, company.id, body.phone)
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    try:
        result = booking_engine.cancel(
            db, company.id, appointment_id, reason=body.reason
        )
    except BookingNotFoundError:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    except PolicyViolationError as e:
        raise HTTPException(status_code=403, detail=e.detail)

    return CancelResultResponse(success=result.success, message=result.message)


# ═══════════════════════════════════════════════════════════════════════════════
# BookingSession FSM — Fase 2
# ═══════════════════════════════════════════════════════════════════════════════

def _display_time(dt: datetime, tz_name: str) -> str:
    """Converte datetime UTC para HH:MM no timezone da empresa."""
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("America/Sao_Paulo")
    return dt.astimezone(tz).strftime("%H:%M")


def _build_context_summary(session: BookingSession) -> ContextSummaryHTTP:
    """
    Extrai campos relevantes do context JSONB para o frontend exibir o resumo
    em AWAITING_CONFIRMATION e ao retomar sessões.
    Todos os campos são opcionais — ausentes se o fluxo ainda não chegou lá.
    """
    ctx = session.context or {}
    tz = session.company_timezone or "America/Sao_Paulo"

    slot_display: Optional[str] = None
    slot_raw = ctx.get("slot_start_at")
    if slot_raw:
        try:
            slot_display = _display_time(datetime.fromisoformat(slot_raw), tz)
        except (ValueError, TypeError):
            pass

    dur = ctx.get("service_duration_minutes")

    return ContextSummaryHTTP(
        customer_name=ctx.get("customer_name"),
        service_name=ctx.get("service_name"),
        service_price=ctx.get("service_price"),
        service_duration_minutes=int(dur) if dur is not None else None,
        professional_name=ctx.get("professional_name"),
        selected_date=ctx.get("selected_date"),
        slot_start_at=slot_raw,
        slot_end_at=ctx.get("slot_end_at"),
        slot_start_display=slot_display,
    )


def _serialize_options(options: list, company_timezone: str) -> list[dict]:
    """
    Converte lista de dataclasses do engine (ServiceOption, ProfessionalOption,
    DateOption, SlotOption) em dicts serializáveis pelo Pydantic.

    SlotOption recebe campo extra `start_display` (HH:MM no tz da empresa).
    """
    result: list[dict] = []
    for opt in options:
        if isinstance(opt, SlotOption):
            result.append(SlotOptionHTTP(
                start_at=opt.start_at,
                end_at=opt.end_at,
                start_display=_display_time(opt.start_at, company_timezone),
                professional_id=opt.professional_id,
                professional_name=opt.professional_name,
                row_key=opt.row_key,
            ).model_dump(mode="json"))
        elif isinstance(opt, ServiceOption):
            result.append(ServiceOptionHTTP(
                id=opt.id,
                name=opt.name,
                price=str(opt.price),
                duration_minutes=opt.duration_minutes,
                row_key=opt.row_key,
            ).model_dump(mode="json"))
        elif isinstance(opt, ProfessionalOption):
            result.append(ProfessionalOptionHTTP(
                id=opt.id,
                name=opt.name,
                row_key=opt.row_key,
            ).model_dump(mode="json"))
        elif isinstance(opt, DateOption):
            result.append(DateOptionHTTP(
                date=opt.date,
                label=opt.label,
                has_availability=opt.has_availability,
                row_key=opt.row_key,
            ).model_dump(mode="json"))
        elif isinstance(opt, ShiftOption):
            result.append(ShiftOptionHTTP(
                shift=opt.shift,
                label=opt.label,
                slot_count=opt.slot_count,
                has_availability=opt.has_availability,
                row_key=opt.row_key,
            ).model_dump(mode="json"))
        else:
            # fallback: dataclass genérico ou dict passado direto
            if hasattr(opt, "__dict__"):
                result.append(opt.__dict__)
            else:
                result.append(opt)
    return result


def _get_session_locked(db: Session, session_id: UUID, company_id: UUID) -> BookingSession:
    """
    Carrega a sessão com SELECT FOR UPDATE NOWAIT.
    Lança 404 se não encontrada ou não pertence à empresa.
    Lança 409 se outra requisição está processando a mesma sessão simultaneamente.
    """
    try:
        session = (
            db.query(BookingSession)
            .filter(
                BookingSession.id == session_id,
                BookingSession.company_id == company_id,
            )
            .with_for_update(nowait=True)
            .first()
        )
    except OperationalError:
        # PostgreSQL lança LockNotAvailable (código 55P03) quando NOWAIT falha
        raise HTTPException(
            status_code=409,
            detail="Sessão em uso por outra requisição — tente novamente em instantes",
        )

    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return session


# ─── POST /booking/{slug}/start ──────────────────────────────────────────────

@router.post("/{slug}/start", response_model=StartSessionResponse, status_code=201)
def start_session(
    slug: str,
    body: StartSessionRequest,
    db: Session = Depends(get_db),
):
    """
    Cria uma nova BookingSession para o fluxo de agendamento online.
    A sessão começa sempre em AWAITING_SERVICE — o engine já não usa IDLE.
    Opcionalmente aceita customer_phone para identificar o cliente de imediato.
    """
    company, _ = _require_online_booking(slug, db)

    company_tz = getattr(company, "timezone", "America/Sao_Paulo") or "America/Sao_Paulo"

    # Engine cria a sessão já em AWAITING_SERVICE (sem IDLE)
    session = booking_engine.start_session(
        db,
        company_id=company.id,
        channel="web",
        company_timezone=company_tz,
    )

    # Atalho: cliente se identificou na abertura — salvar no contexto imediatamente
    if body.customer_phone:
        customer = customer_svc.get_or_create_by_phone(
            db,
            company.id,
            body.customer_phone,
            body.customer_name or "",
        )
        session.customer_id = customer.id
        # Não atribuir session.context aqui ainda — será feito junto com
        # last_listed_services logo abaixo para garantir atribuição única

    # Sempre listar serviços (sessão começa em AWAITING_SERVICE)
    # e persistir last_listed_services no contexto em UMA única atribuição
    # para garantir que o SQLAlchemy rastreie a mudança corretamente.
    services = booking_engine.list_services(db, session.company_id)

    ctx = dict(session.context or {})

    # Incluir dados do cliente se veio no /start
    if body.customer_phone:
        ctx["customer_name"]  = customer.name  # type: ignore[name-defined]
        ctx["customer_phone"] = body.customer_phone

    # last_listed_services permite que _handle_select_service resolva row_key
    ctx["last_listed_services"] = [
        {
            "id": str(s.id),
            "name": s.name,
            "price": str(s.price),
            "duration_minutes": s.duration_minutes,
            "row_key": s.row_key,
        }
        for s in services
    ]

    session.context = ctx  # atribuição única — SQLAlchemy detecta a mudança

    # Commit único — elimina o problema de double-commit + refresh perdendo o contexto
    db.commit()
    db.refresh(session)

    initial_options = _serialize_options(services, company_tz)

    return StartSessionResponse(
        session_id=session.id,
        token=session.token,
        state=session.state,
        options=initial_options,
        expires_at=session.expires_at,
        company_timezone=company_tz,
    )


# ─── POST /booking/{slug}/update ─────────────────────────────────────────────

@router.post("/{slug}/update", response_model=UpdateSessionResponse)
def update_session(
    slug: str,
    body: UpdateSessionRequest,
    db: Session = Depends(get_db),
):
    """
    Aplica uma ação FSM à sessão e retorna o novo estado + opções.

    Concorrência: usa SELECT FOR UPDATE NOWAIT — requisições simultâneas
    para a mesma sessão recebem 409 imediatamente (sem espera).

    O caller deve persistir `expires_at` e atualizar o estado local do wizard.
    """
    company, _ = _require_online_booking(slug, db)

    # Validar a action antes de adquirir o lock (falha rápida, sem I/O desnecessário)
    try:
        action = BookingAction(body.action)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Ação desconhecida: '{body.action}'. "
                   f"Valores válidos: {[a.value for a in BookingAction]}",
        )

    # Adquirir lock — lança 409 se sessão já está em uso
    session = _get_session_locked(db, body.session_id, company.id)

    try:
        result = booking_engine.update(db, session, action, body.payload)
    except SessionExpiredError:
        raise HTTPException(
            status_code=410,
            detail="Sessão expirada — inicie uma nova sessão",
        )
    except InvalidActionError as e:
        logger.error("InvalidActionError | session=%s state=%s action=%s payload=%s ctx=%s | %s",
        session.id, session.state, action, body.payload,
        dict(session.context or {}),
        e.detail,
        )
        raise HTTPException(status_code=422, detail=e.detail)
    except SlotUnavailableError as e:
        # Slot foi tomado durante a confirmação — engine já voltou para AWAITING_TIME
        # com novos slots disponíveis. Retornamos 200 com error code para o frontend tratar.
        db.commit()
        db.refresh(session)
        return UpdateSessionResponse(
            state=session.state,
            options=_serialize_options(result.options if result else [], session.company_timezone),
            context_summary=_build_context_summary(session),
            error="SLOT_UNAVAILABLE",
            expires_at=session.expires_at,
        )
    except PolicyViolationError as e:
        raise HTTPException(status_code=403, detail=e.detail)

    # Commit persiste o estado atualizado (state, context, expires_at, last_action)
    flag_modified(session, "context")
    db.commit()
    db.refresh(session)

    # Serializar resposta
    tz = session.company_timezone
    confirmation = None
    cancel_result = None

    if result.confirmation_data:
        c = result.confirmation_data
        confirmation = ConfirmationHTTP(
            appointment_id=c.appointment_id,
            service_name=c.service_name,
            professional_name=c.professional_name,
            start_at=c.start_at,
            start_display=_display_time(c.start_at, tz),
            end_at=c.end_at,
            total_amount=str(c.total_amount),
        )

    if result.cancel_data:
        c = result.cancel_data
        cancel_result = CancelConfirmationHTTP(
            success=c.success,
            message=c.message,
        )

    return UpdateSessionResponse(
        state=result.next_state,
        options=_serialize_options(result.options, tz),
        context_summary=_build_context_summary(session),
        confirmation=confirmation,
        cancel_result=cancel_result,
        error=result.error,
        idempotent=result.idempotent_replay,
        expires_at=session.expires_at,
        dates_has_next=result.dates_has_next,
        dates_has_previous=result.dates_has_previous,
    )


# ─── GET /booking/{slug}/session/{token} ─────────────────────────────────────

@router.get("/{slug}/session/{token}", response_model=SessionStateResponse)
def resume_session(
    slug: str,
    token: str,
    db: Session = Depends(get_db),
):
    """
    Retoma uma sessão existente pelo token (ex: ?t={token} na URL do frontend).

    As opções são re-geradas do banco — slots podem ter mudado desde a última visita.
    Se a sessão estiver expirada, retorna 410 para o frontend redirecionar ao /start.
    """
    company, _ = _require_online_booking(slug, db)

    session = (
        db.query(BookingSession)
        .filter(
            BookingSession.token == token,
            BookingSession.company_id == company.id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    # Verificar TTL — sessões expiradas retornam 410 (não 404, para o frontend distinguir)
    now = datetime.now(timezone.utc)
    if session.expires_at and now > session.expires_at:
        raise HTTPException(
            status_code=410,
            detail="Sessão expirada — inicie uma nova sessão",
        )

    # Re-listar opções do estado atual (slots podem ter mudado)
    options = booking_engine.get_options_for_state(db, session)
    tz = session.company_timezone

    # Confirmação se sessão já está em CONFIRMED
    confirmation = None
    if session.state == "CONFIRMED" and session.appointment_id:
        ctx = session.context or {}
        start_at_raw = ctx.get("slot_start_at")
        end_at_raw   = ctx.get("slot_end_at")
        if start_at_raw and end_at_raw:
            start_at = datetime.fromisoformat(start_at_raw)
            end_at   = datetime.fromisoformat(end_at_raw)
            confirmation = ConfirmationHTTP(
                appointment_id=session.appointment_id,
                service_name=ctx.get("service_name", ""),
                professional_name=ctx.get("professional_name", ""),
                start_at=start_at,
                start_display=_display_time(start_at, tz),
                end_at=end_at,
                total_amount=str(ctx.get("total_amount", "0")),
            )

    # Ler flags de paginação de datas do contexto (atualizados por get_options_for_state)
    ctx_after = session.context or {}
    return SessionStateResponse(
        session_id=session.id,
        token=session.token,
        state=session.state,
        options=_serialize_options(options, tz),
        context_summary=_build_context_summary(session),
        confirmation=confirmation,
        expires_at=session.expires_at,
        company_timezone=tz,
        dates_has_next=bool(ctx_after.get("dates_has_next", False)),
        dates_has_previous=bool(ctx_after.get("dates_has_previous", False)),
    )