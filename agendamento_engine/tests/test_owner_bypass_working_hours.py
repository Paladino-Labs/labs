"""
Testes — OWNER pode agendar fora do horário de trabalho.

Cobre o bypass dos passos 1 e 2 de `_assert_slot_available` (dia de trabalho +
janela de horário) para o papel OWNER, mantendo os passos 3 e 4 (conflito de
agendamento + bloqueio manual) para TODOS os papéis.

Usa mocks (unittest.mock / monkeypatch) — sem PostgreSQL real (padrão do projeto).

Casos do DoD:
  - OWNER cria fora do horário de trabalho            → sem 422 (passa)
  - OWNER cria em dia sem escala do profissional      → sem 422 (passa)
  - OWNER cria em conflito com appointment existente  → 409 (conflito mantido)
  - OPERATOR/PROFESSIONAL cria fora do horário        → 422 (bloqueio mantido)
  - OWNER remarca fora do horário                     → propaga bypass=True
  - OPERATOR remarca fora do horário                  → propaga bypass=False
"""
import uuid
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.infrastructure.db.models import (
    Appointment, ScheduleBlock, TenantConfig, WorkingHour,
)
from app.modules.appointments import router as appointment_router
from app.modules.appointments import service as appointment_svc


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _future(hours: float = 48) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


class _FakeQuery:
    """Query que ignora .filter() e devolve um resultado fixo em .first()."""

    def __init__(self, first=None):
        self._first = first

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._first


def _make_slot_db(working_hour=None, config=None, overlap=None, block=None):
    """db roteado por modelo para `_assert_slot_available`."""
    db = MagicMock()

    def _query(model):
        if model is WorkingHour:
            return _FakeQuery(working_hour)
        if model is TenantConfig:
            return _FakeQuery(config)
        if model is Appointment:
            return _FakeQuery(overlap)
        if model is ScheduleBlock:
            return _FakeQuery(block)
        return _FakeQuery(None)

    db.query.side_effect = _query
    return db


def _working_hour(weekday: int):
    return SimpleNamespace(
        weekday=weekday,
        opening_time=time(9, 0),
        closing_time=time(18, 0),
        is_active=True,
    )


# ─── _assert_slot_available — bypass ─────────────────────────────────────────

def test_owner_bypass_dia_sem_escala_passa():
    """bypass=True + nenhum WorkingHour (dia sem escala) → não levanta."""
    start = _future()
    db = _make_slot_db(working_hour=None)  # sem escala neste dia
    # não deve levantar
    appointment_svc._assert_slot_available(
        db, uuid.uuid4(), uuid.uuid4(), start, start + timedelta(minutes=30),
        bypass_working_hours=True,
    )


def test_owner_bypass_fora_da_janela_passa():
    """bypass=True ignora completamente a janela de trabalho (WorkingHour nem é
    consultado) → slot às 23h passa."""
    start = _future().replace(hour=23, minute=0)
    db = _make_slot_db(working_hour=_working_hour(start.weekday()))
    appointment_svc._assert_slot_available(
        db, uuid.uuid4(), uuid.uuid4(), start, start + timedelta(minutes=30),
        bypass_working_hours=True,
    )


def test_owner_bypass_conflito_ainda_levanta_409():
    """bypass=True NÃO afrouxa o passo 3 — conflito de agendamento → 409."""
    start = _future()
    overlap = SimpleNamespace(id=uuid.uuid4())
    db = _make_slot_db(working_hour=None, overlap=overlap)
    with pytest.raises(HTTPException) as exc:
        appointment_svc._assert_slot_available(
            db, uuid.uuid4(), uuid.uuid4(), start, start + timedelta(minutes=30),
            bypass_working_hours=True,
        )
    assert exc.value.status_code == 409


def test_owner_bypass_bloqueio_ainda_levanta_409():
    """bypass=True NÃO afrouxa o passo 4 — bloqueio manual → 409."""
    start = _future()
    block = SimpleNamespace(id=uuid.uuid4())
    db = _make_slot_db(working_hour=None, block=block)
    with pytest.raises(HTTPException) as exc:
        appointment_svc._assert_slot_available(
            db, uuid.uuid4(), uuid.uuid4(), start, start + timedelta(minutes=30),
            bypass_working_hours=True,
        )
    assert exc.value.status_code == 409


def test_sem_bypass_dia_sem_escala_levanta_422():
    """bypass=False (OPERATOR/PROFESSIONAL) + dia sem escala → 422."""
    start = _future()
    db = _make_slot_db(working_hour=None)
    with pytest.raises(HTTPException) as exc:
        appointment_svc._assert_slot_available(
            db, uuid.uuid4(), uuid.uuid4(), start, start + timedelta(minutes=30),
            bypass_working_hours=False,
        )
    assert exc.value.status_code == 422


def test_sem_bypass_fora_da_janela_levanta_422():
    """bypass=False + slot fora da janela de trabalho → 422."""
    start = _future().replace(hour=23, minute=0)
    config = SimpleNamespace(timezone="America/Sao_Paulo")
    db = _make_slot_db(working_hour=_working_hour(start.weekday()), config=config)
    with pytest.raises(HTTPException) as exc:
        appointment_svc._assert_slot_available(
            db, uuid.uuid4(), uuid.uuid4(), start, start + timedelta(minutes=30),
            bypass_working_hours=False,
        )
    assert exc.value.status_code == 422


# ─── Propagação service → _assert_slot_available ─────────────────────────────

def test_create_appointment_propaga_bypass(monkeypatch):
    """create_appointment repassa bypass_working_hours para _assert_slot_available."""
    captured = {}

    def _fake_assert(db, company_id, professional_id, start_at, end_at,
                     bypass_working_hours=False, **k):
        captured["bypass"] = bypass_working_hours

    monkeypatch.setattr(appointment_svc, "_assert_slot_available", _fake_assert)
    monkeypatch.setattr(appointment_svc, "issue_manage_token", lambda a: "tok")
    monkeypatch.setattr(appointment_svc, "send_booking_confirmation",
                        lambda *a, **k: None)
    monkeypatch.setattr(appointment_svc, "build_snapshots",
                        lambda services: ([], 0, 30))

    professional = SimpleNamespace(id=uuid.uuid4())
    customer = SimpleNamespace(id=uuid.uuid4())

    db = MagicMock()

    def _query(model):
        q = MagicMock()
        name = getattr(model, "__name__", "")
        if name == "Professional":
            q.filter.return_value.first.return_value = professional
        elif name == "Customer":
            q.filter.return_value.first.return_value = customer
        elif name == "Service":
            q.filter.return_value.all.return_value = []
        else:
            q.filter.return_value.first.return_value = None
        return q

    db.query.side_effect = _query

    data = SimpleNamespace(
        professional_id=professional.id,
        client_id=customer.id,
        services=[],
        start_at=_future(),
        idempotency_key=str(uuid.uuid4()),
    )

    appointment_svc.create_appointment(
        db, uuid.uuid4(), data, uuid.uuid4(), bypass_working_hours=True,
    )
    assert captured["bypass"] is True


def test_reschedule_appointment_propaga_bypass(monkeypatch):
    """reschedule_appointment repassa bypass_working_hours para _assert_slot_available."""
    captured = {}

    appointment = SimpleNamespace(
        id=uuid.uuid4(),
        professional_id=uuid.uuid4(),
        status="SCHEDULED",
        start_at=_future(),
        end_at=_future(),
        services=[SimpleNamespace(duration_snapshot=30)],
    )

    monkeypatch.setattr(appointment_svc, "get_appointment_or_404",
                        lambda db, cid, aid: appointment)

    def _fake_assert(db, company_id, professional_id, start_at, end_at,
                     exclude_appointment_id=None, bypass_working_hours=False, **k):
        captured["bypass"] = bypass_working_hours

    monkeypatch.setattr(appointment_svc, "_assert_slot_available", _fake_assert)
    monkeypatch.setattr(appointment_svc, "issue_manage_token", lambda a: "tok")
    monkeypatch.setattr(appointment_svc, "send_reschedule_confirmation",
                        lambda *a, **k: None)
    monkeypatch.setattr(appointment_svc, "_publish_slot_released",
                        lambda *a, **k: None)

    data = SimpleNamespace(start_at=_future())
    appointment_svc.reschedule_appointment(
        MagicMock(), uuid.uuid4(), appointment.id, data, uuid.uuid4(),
        skip_policy=True, bypass_working_hours=True,
    )
    assert captured["bypass"] is True


# ─── Router — role → bypass ──────────────────────────────────────────────────

@pytest.mark.parametrize("role,expected", [
    ("OWNER", True),
    ("ADMIN", False),
    ("OPERATOR", False),
    ("PROFESSIONAL", False),
])
def test_router_create_bypass_por_role(monkeypatch, role, expected):
    captured = {}

    def _fake_create(db, company_id, body, user_id, bypass_working_hours=False):
        captured["bypass"] = bypass_working_hours
        return "ok"

    monkeypatch.setattr(appointment_router.svc, "create_appointment", _fake_create)

    user = SimpleNamespace(role=role, company_id=uuid.uuid4(), id=uuid.uuid4())
    appointment_router.create_appointment(body=MagicMock(), user=user, db=MagicMock())
    assert captured["bypass"] is expected


@pytest.mark.parametrize("role,expected", [
    ("OWNER", True),
    ("ADMIN", False),
    ("OPERATOR", False),
    ("PROFESSIONAL", False),
])
def test_router_reschedule_bypass_por_role(monkeypatch, role, expected):
    captured = {}

    def _fake_reschedule(db, company_id, appointment_id, body, user_id,
                         skip_policy=False, bypass_working_hours=False):
        captured["bypass"] = bypass_working_hours
        return "ok"

    monkeypatch.setattr(appointment_router.svc, "reschedule_appointment",
                        _fake_reschedule)

    user = SimpleNamespace(role=role, company_id=uuid.uuid4(), id=uuid.uuid4())
    appointment_router.reschedule_appointment(
        appointment_id=uuid.uuid4(), body=MagicMock(), user=user, db=MagicMock(),
    )
    assert captured["bypass"] is expected
