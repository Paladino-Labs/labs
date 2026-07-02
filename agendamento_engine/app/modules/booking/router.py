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
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.package import Package
from app.infrastructure.db.models.subscription import SubscriptionPlan
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
    ProductOptionResponse,
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
from app.modules.booking.checkout_schemas import (
    PublicPackageOut,
    PublicPackageItemOut,
    PublicPlanOut,
    PublicPlanItemOut,
    PublicPromotionOut,
    CouponValidateRequest,
    CouponValidateResponse,
    CheckoutRequest,
    CheckoutResponse,
    CheckoutAppointmentResult,
    CheckoutPurchaseResult,
    CheckoutSubscriptionResult,
    CheckoutProductResult,
)
from app.modules.customers import service as customer_svc
from app.modules.appointments.polices import PolicyViolationError
from app.modules.appointments import service as appointment_svc
from app.modules.packages import service as package_svc
from app.modules.subscriptions import service as subscription_svc
from app.modules.promotions import service as promotion_svc
from app.modules.payments import service as payment_svc
from app.modules.stock import service as stock_svc
from app.modules.appointments.manage_tokens import build_manage_url
from app.core.config import settings
from decimal import Decimal
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
        business_hours_structured=profile.business_hours_structured if profile else None,
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


# ─── B6 — Vitrine de produtos (público) ──────────────────────────────────────

@router.get("/{slug}/products", response_model=list[ProductOptionResponse])
def list_products(slug: str, db: Session = Depends(get_db)):
    """Lista produtos ativos da empresa para a aba Produtos do /book.

    Público (sem auth). 404 se slug inválido; 403 se online_booking off.
    `available` reflete o estoque (sem controle de estoque → disponível).
    """
    company, _ = _require_online_booking(slug, db)
    products = (
        db.query(Product)
        .filter(Product.company_id == company.id, Product.active == True)
        .order_by(Product.name)
        .all()
    )
    return [
        ProductOptionResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            price=p.price,
            image_url=p.image_url,
            available=(p.stock is None or p.stock > 0),
        )
        for p in products
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

    # Identifica ou cria o cliente pelo telefone via resolver de identidade
    # (mesmo padrão de booking/engine.py desde o Sprint B1).
    from app.modules.identity.resolver import (
        resolver, validate_user_phone_input, InvalidUserPhoneError,
    )
    from app.modules.identity.consent_service import (
        grant_consent, ConsentType, SourceChannel,
    )

    # Validação estrita de formulário público (DDI rejeitado, DDD ANATEL)
    try:
        validate_user_phone_input(body.customer_phone)
    except InvalidUserPhoneError as e:
        raise HTTPException(status_code=422, detail=e.message)

    customer, is_new = resolver.resolve_for_tenant(
        db, raw_phone=body.customer_phone,
        company_id=company.id, name=body.customer_name,
    )
    if is_new:
        grant_consent(
            db, customer.identity_id, company.id,
            ConsentType.COMMUNICATION, None, SourceChannel.LINK,
            notes="Agendamento via link público (confirm legado)",
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
        # Resolve via identidade Paladino (mesmo padrão de booking/engine.py).
        from app.modules.identity.resolver import (
            resolver, validate_user_phone_input, InvalidUserPhoneError,
        )
        from app.modules.identity.consent_service import (
            grant_consent, ConsentType, SourceChannel,
        )

        # Validação estrita de formulário público (DDI rejeitado, DDD ANATEL)
        try:
            validate_user_phone_input(body.customer_phone)
        except InvalidUserPhoneError as e:
            raise HTTPException(status_code=422, detail=e.message)

        customer, is_new = resolver.resolve_for_tenant(
            db,
            raw_phone=body.customer_phone,
            company_id=company.id,
            name=body.customer_name or "",
        )
        if is_new:
            grant_consent(
                db, customer.identity_id, company.id,
                ConsentType.COMMUNICATION, None, SourceChannel.LINK,
                notes="Agendamento via link público (start shortcut)",
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
            manage_url=c.manage_url,
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


# ═══════════════════════════════════════════════════════════════════════════════
# Checkout unificado público — Sprint B2
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_owner_user_id(db: Session, company_id: UUID):
    """Primeiro User OWNER ativo do tenant (ator das baixas de estoque).

    Mesma lógica do bot (whatsapp/handlers/comprando_produto._resolve_owner_user_id);
    duplicada aqui para não acoplar o router público ao módulo do bot.
    """
    from app.infrastructure.db.models import User
    owner = (
        db.query(User)
        .filter(
            User.company_id == company_id,
            User.role == "OWNER",
            User.active == True,  # noqa: E712
        )
        .first()
    )
    return owner.id if owner else None


def _serialize_public_package(p: Package) -> PublicPackageOut:
    return PublicPackageOut(
        package_id=p.package_id,
        name=p.name,
        items=[
            PublicPackageItemOut(
                item_type=item.item_type,
                service_name=getattr(item, "service_name", None),
                product_name=getattr(item, "product_name", None),
                quantity=item.quantity,
            )
            for item in p.items
        ],
        total_cotas=p.total_cotas,
        price=str(p.price),
        validity_days=p.validity_days,
    )


def _serialize_public_plan(p: SubscriptionPlan) -> PublicPlanOut:
    return PublicPlanOut(
        plan_id=p.plan_id,
        name=p.name,
        items=[
            PublicPlanItemOut(
                item_type=item.item_type,
                service_name=getattr(item, "service_name", None),
                product_name=getattr(item, "product_name", None),
                quantity=item.quantity,
            )
            for item in p.items
        ],
        total_cotas_per_cycle=getattr(p, "total_cotas_per_cycle", p.cotas_per_cycle),
        price=str(p.price),
        cycle_days=p.cycle_days,
        rollover_enabled=p.rollover_enabled,
    )


# ─── GET /booking/{slug}/packages ─────────────────────────────────────────────

@router.get("/{slug}/packages", response_model=list[PublicPackageOut])
def list_packages(
    slug: str,
    service_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
):
    """Pacotes ativos do tenant. service_id opcional filtra por serviço incluído."""
    company, _ = _require_online_booking(slug, db)
    pkgs = package_svc.get_packages_containing_service(db, company.id, service_id)
    return [_serialize_public_package(p) for p in pkgs]


# ─── GET /booking/{slug}/subscription-plans ───────────────────────────────────

@router.get("/{slug}/subscription-plans", response_model=list[PublicPlanOut])
def list_plans(
    slug: str,
    service_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
):
    """Planos ativos do tenant. service_id opcional filtra por serviço incluído."""
    company, _ = _require_online_booking(slug, db)
    plans = subscription_svc.get_plans_containing_service(db, company.id, service_id)
    return [_serialize_public_plan(p) for p in plans]


# ─── GET /booking/{slug}/promotions ───────────────────────────────────────────

@router.get("/{slug}/promotions", response_model=list[PublicPromotionOut])
def list_promotions(
    slug: str,
    db: Session = Depends(get_db),
):
    """Promoções AUTOMATIC ativas e vigentes (vitrine pública)."""
    company, _ = _require_online_booking(slug, db)
    promos = promotion_svc.list_active_promotions(db, company.id)
    return [
        PublicPromotionOut(
            promotion_id=p.id,
            name=p.name,
            description=p.description,
            discount_type=p.discount_type,
            discount_value=str(p.discount_value) if p.discount_value is not None else None,
            valid_until=p.valid_until,
        )
        for p in promos
    ]


# ─── POST /booking/{slug}/coupon/validate ─────────────────────────────────────

@router.post("/{slug}/coupon/validate", response_model=CouponValidateResponse)
def validate_coupon(
    slug: str,
    body: CouponValidateRequest,
    db: Session = Depends(get_db),
):
    """Valida um cupom sobre um valor bruto. Nunca persiste (compute_preview)."""
    company, _ = _require_online_booking(slug, db)
    try:
        preview = promotion_svc.compute_preview(
            db=db,
            company_id=company.id,
            gross_amount=Decimal(body.gross_amount),
            service_ids=[str(s) for s in body.service_ids] or None,
            product_ids=[str(p) for p in body.product_ids] or None,
            coupon_code=body.coupon_code,
        )
    except HTTPException as e:
        return CouponValidateResponse(valid=False, error=str(e.detail))

    # compute_preview expõe final_amount/discount_total/applications/coupon_valid.
    applications = preview.get("applications") or []
    discount_type = applications[0]["discount_type"] if applications else None
    return CouponValidateResponse(
        valid=bool(preview.get("coupon_valid")),
        discount_type=discount_type,
        discount_value=str(preview.get("discount_total", "0")),
        net_amount=str(preview.get("final_amount")),
        description=None,
    )


# ─── POST /booking/{slug}/checkout ────────────────────────────────────────────

@router.post("/{slug}/checkout", response_model=CheckoutResponse, status_code=201)
def unified_checkout(
    slug: str,
    body: CheckoutRequest,
    db: Session = Depends(get_db),
):
    """Checkout unificado: agendamentos + pacotes + assinaturas + produtos.

    Cupom (se informado) aplicado ao primeiro Payment cobrável, na ordem:
    pacote → assinatura → produto. Agendamentos não são cobrados aqui.
    """
    from app.modules.identity.resolver import (
        resolver, validate_user_phone_input, InvalidUserPhoneError,
    )
    from app.modules.identity.consent_service import (
        grant_consent, ConsentType, SourceChannel,
    )
    from app.modules.appointments.schemas import AppointmentCreate, ServiceRequest

    company, _ = _require_online_booking(slug, db)

    # Validação estrita de formulário público (DDI rejeitado, DDD ANATEL)
    try:
        validate_user_phone_input(body.customer_phone)
    except InvalidUserPhoneError as e:
        raise HTTPException(status_code=422, detail=e.message)

    # 1. Resolver cliente (cria PaladinoIdentity se novo) + consent na primeira vez
    customer, is_new = resolver.resolve_for_tenant(
        db, raw_phone=body.customer_phone,
        company_id=company.id, name=body.customer_name,
    )
    if is_new:
        grant_consent(
            db, customer.identity_id, company.id,
            ConsentType.COMMUNICATION, None, SourceChannel.LINK,
            notes="Checkout via link público",
        )

    warnings: list[str] = []
    appointments_out: list[CheckoutAppointmentResult] = []
    purchases_out: list[CheckoutPurchaseResult] = []
    subscriptions_out: list[CheckoutSubscriptionResult] = []
    product_sales_out: list[CheckoutProductResult] = []
    total_charged = Decimal("0")
    coupon_applied: Optional[str] = None

    # Roteamento do cupom: pacote → assinatura → produto (só um destino).
    coupon = body.coupon_code or None
    coupon_for_packages = coupon if body.packages else None
    coupon_for_subs = coupon if (coupon and not body.packages and body.subscriptions) else None
    coupon_for_products = coupon if (
        coupon and not body.packages and not body.subscriptions and body.products
    ) else None

    # 2. Agendamentos (sem cobrança; validação de slot obrigatória — sem bypass)
    for svc_item in body.services:
        appt_data = AppointmentCreate(
            professional_id=svc_item.professional_id,
            client_id=customer.id,
            start_at=svc_item.start_at,
            services=[ServiceRequest(service_id=svc_item.service_id)],
            idempotency_key=str(uuidlib.uuid4()),
        )
        appt, raw_token = appointment_svc.create_appointment(
            db, company.id, appt_data, user_id=None,
            bypass_working_hours=False,
        )
        appointments_out.append(CheckoutAppointmentResult(
            appointment_id=appt.id,
            service_name=appt.services[0].service_name if appt.services else "",
            professional_name=appt.professional.name if appt.professional else "",
            start_at=appt.start_at,
            total_amount=str(appt.total_amount),
            manage_url=build_manage_url(raw_token) if raw_token else None,
        ))

    # 3. Pacotes
    for i, pkg_item in enumerate(body.packages):
        item_coupon = coupon_for_packages if i == 0 else None
        purchase = package_svc.purchase(
            customer_id=customer.id,
            package_id=pkg_item.package_id,
            seller_user_id=None,
            payment_method=pkg_item.payment_method,
            target_account_id=None,
            company_id=company.id,
            db=db,
            coupon_code=item_coupon,
        )
        if item_coupon:
            coupon_applied = item_coupon
        pkg = db.query(Package).filter(
            Package.package_id == pkg_item.package_id,
            Package.company_id == company.id,
        ).first()
        price = pkg.price if pkg else Decimal("0")
        total_charged += price
        purchases_out.append(CheckoutPurchaseResult(
            purchase_id=purchase.purchase_id,
            package_name=pkg.name if pkg else "",
            total_cotas=pkg.total_cotas if pkg else 0,
            amount_paid=str(price),
        ))

    # 4. Assinaturas
    for i, sub_item in enumerate(body.subscriptions):
        item_coupon = coupon_for_subs if i == 0 else None
        subscription, payment = subscription_svc.subscribe(
            customer_id=customer.id,
            plan_id=sub_item.plan_id,
            company_id=company.id,
            db=db,
            payment_method=sub_item.payment_method,
            coupon_code=item_coupon,
        )
        if item_coupon:
            coupon_applied = item_coupon
        plan = db.query(SubscriptionPlan).filter(
            SubscriptionPlan.plan_id == sub_item.plan_id,
            SubscriptionPlan.company_id == company.id,
        ).first()
        price = plan.price if plan else Decimal("0")
        total_charged += price
        subscriptions_out.append(CheckoutSubscriptionResult(
            subscription_id=subscription.subscription_id,
            plan_name=plan.name if plan else "",
            next_billing_at=subscription.next_billing_at,
            amount_paid=str(price),
        ))

    # 5. Produtos (Payment manual + baixa de estoque VENDA)
    owner_id = _resolve_owner_user_id(db, company.id)
    for i, prod_item in enumerate(body.products):
        product = db.query(Product).filter(
            Product.id == prod_item.product_id,
            Product.company_id == company.id,
        ).first()
        if not product:
            raise HTTPException(404, f"Produto não encontrado: {prod_item.product_id}")
        gross = product.price * prod_item.quantity
        item_coupon = coupon_for_products if i == 0 else None
        payment_svc.create_payment(
            company_id=company.id,
            customer_id=customer.id,
            gross_amount=gross,
            payment_method="CASH",
            provider="manual",
            coupon_code=item_coupon,
            db=db,
        )
        if item_coupon:
            coupon_applied = item_coupon
        if owner_id:
            stock_svc.record_movement(
                company_id=company.id,
                product_id=prod_item.product_id,
                movement_type="VENDA",
                quantity=prod_item.quantity,
                created_by=owner_id,
                db=db,
                source_type="OPERATION",
            )
        else:
            warnings.append(
                f"Estoque não atualizado para {product.name} — OWNER não encontrado"
            )
        total_charged += gross
        product_sales_out.append(CheckoutProductResult(
            product_name=product.name,
            quantity=prod_item.quantity,
            amount_paid=str(gross),
        ))

    return CheckoutResponse(
        customer_id=customer.id,
        appointments=appointments_out,
        purchases=purchases_out,
        subscriptions=subscriptions_out,
        product_sales=product_sales_out,
        coupon_applied=coupon_applied,
        discount_amount=None,
        total_charged=str(total_charged),
        warnings=warnings,
    )