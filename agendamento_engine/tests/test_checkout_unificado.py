"""
Sprint B1 — manage_url na confirmação FSM + identidade no checkout público.

Cobre:
  - create_appointment retorna tupla (Appointment, str)
  - manage_url propagado BookingResult → ConfirmationHTTP após CONFIRM do FSM
  - _handle_set_customer usa resolve_for_tenant (cria PaladinoIdentity)
  - is_new=True → grant_consent(COMMUNICATION, LINK); is_new=False → não duplica
  - DDD inválido (HTTPException 422 no resolver) → InvalidActionError
  - Router do painel continua devolvendo o Appointment (token cru ignorado)
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.modules.booking.actions import InvalidActionError
from app.modules.booking.engine import BookingEngine
from app.modules.booking.schemas import BookingIntent, BookingResult
from app.modules.booking.http_schemas import ConfirmationHTTP
from app.modules.appointments import service as appointment_svc
from app.modules.appointments.schemas import AppointmentCreate
from app.modules.identity import resolver as resolver_module
from app.modules.identity import consent_service


_NOW = datetime.now(timezone.utc)


def _make_session(state: str = "AWAITING_CUSTOMER", ctx: dict | None = None):
    session = MagicMock()
    session.id = uuid.uuid4()
    session.company_id = uuid.uuid4()
    session.channel = "web"
    session.company_timezone = "America/Sao_Paulo"
    session.state = state
    session.context = ctx or {}
    session.customer_id = None
    session.appointment_id = None
    return session


# ─── PASSO 1 — create_appointment retorna tupla ──────────────────────────────

def test_create_appointment_returns_tuple():
    professional = SimpleNamespace(id=uuid.uuid4())
    customer = SimpleNamespace(id=uuid.uuid4())
    service = SimpleNamespace(
        id=uuid.uuid4(), name="Corte", duration=30, price=Decimal("50.00"),
    )

    db = MagicMock()

    def _query(arg):
        q = MagicMock()
        f = q.filter.return_value
        name = getattr(arg, "__name__", "")
        if name == "Professional":
            f.first.return_value = professional
        elif name == "Customer":
            f.first.return_value = customer
        elif name == "Service":
            f.all.return_value = [service]
        else:
            f.first.return_value = None
            f.all.return_value = []
        return q

    db.query.side_effect = _query

    data = AppointmentCreate(
        professional_id=professional.id,
        client_id=customer.id,
        start_at=_NOW + timedelta(hours=48),
        services=[{"service_id": service.id}],
        idempotency_key=str(uuid.uuid4()),
    )

    with patch.object(appointment_svc, "_assert_slot_available"), \
         patch.object(appointment_svc, "send_booking_confirmation"):
        result = appointment_svc.create_appointment(db, uuid.uuid4(), data, user_id=None)

    assert isinstance(result, tuple)
    appt, raw_token = result
    assert appt is not None
    assert isinstance(raw_token, str) and raw_token


# ─── PASSO 2/3 — manage_url no BookingResult e ConfirmationHTTP ────────────────

def test_confirm_populates_manage_url():
    engine = BookingEngine()
    db = MagicMock()

    appt = SimpleNamespace(
        id=uuid.uuid4(),
        services=[SimpleNamespace(service_name="Corte")],
        professional=SimpleNamespace(name="Ana"),
        start_at=_NOW,
        end_at=_NOW + timedelta(hours=1),
        total_amount=Decimal("50.00"),
    )

    def fake_create(db, company_id, data, user_id=None):
        return appt, "rawtoken123"

    intent = BookingIntent(
        company_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        professional_id=uuid.uuid4(),
        service_id=uuid.uuid4(),
        start_at=_NOW,
        idempotency_key="k",
    )

    with patch.object(appointment_svc, "create_appointment", fake_create):
        result = engine.confirm(db, intent.company_id, intent)

    assert result.manage_url is not None
    assert result.manage_url.endswith("/manage/rawtoken123")


def test_confirmation_http_carries_manage_url():
    """O contrato HTTP de confirmação do FSM expõe manage_url (mapeado de BookingResult)."""
    c = BookingResult(
        appointment_id=uuid.uuid4(),
        service_name="Corte",
        professional_name="Ana",
        start_at=_NOW,
        end_at=_NOW + timedelta(hours=1),
        total_amount=Decimal("50.00"),
        manage_url="https://app.test/manage/abc",
    )
    confirmation = ConfirmationHTTP(
        appointment_id=c.appointment_id,
        service_name=c.service_name,
        professional_name=c.professional_name,
        start_at=c.start_at,
        start_display="09:00",
        end_at=c.end_at,
        total_amount=str(c.total_amount),
        manage_url=c.manage_url,
    )
    assert confirmation.manage_url == "https://app.test/manage/abc"


# ─── PASSO 4 — _handle_set_customer: identidade + consent ─────────────────────

def test_set_customer_resolves_identity(monkeypatch):
    engine = BookingEngine()
    db = MagicMock()
    customer = SimpleNamespace(id=uuid.uuid4(), name="Maria", identity_id=uuid.uuid4())
    calls = {}

    def fake_resolve(db, raw_phone, company_id, name=None):
        calls["phone"] = raw_phone
        calls["name"] = name
        return customer, False

    monkeypatch.setattr(resolver_module.resolver, "resolve_for_tenant", fake_resolve)
    monkeypatch.setattr(consent_service, "grant_consent", lambda *a, **k: None)

    session = _make_session()
    result = engine._handle_set_customer(
        db, session, {"name": "Maria", "phone": "62988887777"}
    )

    assert calls["phone"] == "62988887777"
    assert session.customer_id == customer.id
    assert result.next_state == "AWAITING_CONFIRMATION"


def test_set_customer_grants_consent_when_new(monkeypatch):
    engine = BookingEngine()
    db = MagicMock()
    customer = SimpleNamespace(id=uuid.uuid4(), name="Maria", identity_id=uuid.uuid4())
    consent_calls = []

    monkeypatch.setattr(
        resolver_module.resolver, "resolve_for_tenant",
        lambda db, raw_phone, company_id, name=None: (customer, True),
    )

    def fake_grant(db, identity_id, company_id, consent_type, channel, source_channel, notes=None):
        consent_calls.append((identity_id, consent_type, channel, source_channel))

    monkeypatch.setattr(consent_service, "grant_consent", fake_grant)

    session = _make_session()
    engine._handle_set_customer(db, session, {"name": "Maria", "phone": "62988887777"})

    assert len(consent_calls) == 1
    identity_id, consent_type, channel, source_channel = consent_calls[0]
    assert identity_id == customer.identity_id
    assert consent_type == consent_service.ConsentType.COMMUNICATION
    assert channel is None
    assert source_channel == consent_service.SourceChannel.LINK


def test_set_customer_does_not_duplicate_consent_when_existing(monkeypatch):
    engine = BookingEngine()
    db = MagicMock()
    customer = SimpleNamespace(id=uuid.uuid4(), name="Maria", identity_id=uuid.uuid4())
    consent_calls = []

    monkeypatch.setattr(
        resolver_module.resolver, "resolve_for_tenant",
        lambda db, raw_phone, company_id, name=None: (customer, False),
    )
    monkeypatch.setattr(
        consent_service, "grant_consent",
        lambda *a, **k: consent_calls.append(a),
    )

    session = _make_session()
    engine._handle_set_customer(db, session, {"name": "Maria", "phone": "62988887777"})

    assert consent_calls == []


def test_set_customer_invalid_ddd_raises_invalid_action(monkeypatch):
    engine = BookingEngine()
    db = MagicMock()

    def fake_resolve(db, raw_phone, company_id, name=None):
        raise HTTPException(
            status_code=422,
            detail="Telefone inválido — informe DDD + número (ex.: 62 98888-7777)",
        )

    monkeypatch.setattr(resolver_module.resolver, "resolve_for_tenant", fake_resolve)
    monkeypatch.setattr(consent_service, "grant_consent", lambda *a, **k: None)

    session = _make_session()
    # 10+ dígitos para passar a validação de comprimento e chegar ao resolver
    with pytest.raises(InvalidActionError):
        engine._handle_set_customer(db, session, {"name": "Maria", "phone": "1198887777"})


# ─── PASSO 1 (caller) — router do painel ──────────────────────────────────────

def test_panel_router_returns_appointment_object():
    from app.modules.appointments import router as appt_router

    appt = SimpleNamespace(id=uuid.uuid4())

    def fake_create(db, company_id, body, user_id, bypass_working_hours=False):
        return appt, "rawtoken"

    user = SimpleNamespace(role="ADMIN", company_id=uuid.uuid4(), id=uuid.uuid4())

    with patch.object(appt_router.svc, "create_appointment", fake_create):
        out = appt_router.create_appointment(body=MagicMock(), user=user, db=MagicMock())

    assert out is appt
