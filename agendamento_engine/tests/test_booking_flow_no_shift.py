"""
Testes do fluxo BookingSession sem AWAITING_SHIFT.

Garante que:
  1. SELECT_DATE vai direto para AWAITING_TIME (sem parada em AWAITING_SHIFT).
  2. BACK em AWAITING_TIME retorna para AWAITING_DATE.
  3. SELECT_SHIFT não é ação válida no fluxo atual → InvalidActionError (422).
"""
import uuid
from datetime import datetime, date, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from app.modules.booking.actions import BookingAction, InvalidActionError
from app.modules.booking.engine import BookingEngine, _BACK_STATE
from app.modules.booking.schemas import SlotOption


# ─── Fixtures ────────────────────────────────────────────────────────────────

COMPANY_ID = uuid.uuid4()
PROFESSIONAL_ID = uuid.uuid4()
SERVICE_ID = uuid.uuid4()

_FUTURE = datetime.now(timezone.utc) + timedelta(hours=2)


def _make_session(state: str, ctx: dict | None = None):
    """BookingSession stub com estado e contexto pré-configurados."""
    session = MagicMock()
    session.id = uuid.uuid4()
    session.company_id = COMPANY_ID
    session.channel = "web"
    session.company_timezone = "America/Sao_Paulo"
    session.state = state
    session.context = ctx or {}
    session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    session.last_action = None
    session.last_action_at = None
    session.customer_id = None
    session.appointment_id = None
    return session


def _make_slot(i: int = 1) -> SlotOption:
    base = datetime(2026, 6, 1, 9 + i, 0, tzinfo=timezone.utc)
    return SlotOption(
        start_at=base,
        end_at=base + timedelta(hours=1),
        professional_id=PROFESSIONAL_ID,
        professional_name="Ana",
        row_key=f"slot_{i}",
    )


# ─── Testes ───────────────────────────────────────────────────────────────────

class TestSelectDateTransitionsToAwaitingTime:

    def test_select_date_goes_to_awaiting_time(self):
        """SELECT_DATE deve ir direto para AWAITING_TIME, sem parar em AWAITING_SHIFT."""
        engine = BookingEngine()
        db = MagicMock()

        ctx = {
            "service_id": str(SERVICE_ID),
            "professional_id": str(PROFESSIONAL_ID),
            "last_listed_dates": [
                {
                    "date": "2026-06-01",
                    "label": "Segunda (01/06)",
                    "has_availability": True,
                    "row_key": "dia_1",
                }
            ],
        }
        session = _make_session("AWAITING_DATE", ctx)
        slots = [_make_slot(1), _make_slot(2)]

        with patch.object(engine, "list_available_slots", return_value=slots) as mock_slots:
            result = engine._handle_select_date(db, session, {"row_key": "dia_1"})

        assert result.next_state == "AWAITING_TIME", (
            f"Esperava AWAITING_TIME, obteve {result.next_state}"
        )
        assert session.state == "AWAITING_TIME"
        mock_slots.assert_called_once()

    def test_select_date_options_are_slots_not_shifts(self):
        """As opções retornadas devem ser SlotOption[], não ShiftOption[]."""
        engine = BookingEngine()
        db = MagicMock()

        ctx = {
            "service_id": str(SERVICE_ID),
            "professional_id": str(PROFESSIONAL_ID),
            "last_listed_dates": [
                {
                    "date": "2026-06-01",
                    "label": "Segunda (01/06)",
                    "has_availability": True,
                    "row_key": "dia_1",
                }
            ],
        }
        session = _make_session("AWAITING_DATE", ctx)
        slots = [_make_slot(1), _make_slot(2), _make_slot(3)]

        with patch.object(engine, "list_available_slots", return_value=slots):
            result = engine._handle_select_date(db, session, {"row_key": "dia_1"})

        assert len(result.options) == 3
        for opt in result.options:
            assert isinstance(opt, SlotOption), (
                f"Esperava SlotOption, obteve {type(opt).__name__}"
            )

    def test_select_date_stores_last_listed_slots_in_context(self):
        """Contexto deve ter 'last_listed_slots' após SELECT_DATE."""
        engine = BookingEngine()
        db = MagicMock()

        ctx = {
            "service_id": str(SERVICE_ID),
            "professional_id": str(PROFESSIONAL_ID),
            "last_listed_dates": [
                {
                    "date": "2026-06-01",
                    "label": "Segunda (01/06)",
                    "has_availability": True,
                    "row_key": "dia_1",
                }
            ],
        }
        session = _make_session("AWAITING_DATE", ctx)
        slots = [_make_slot(1)]

        with patch.object(engine, "list_available_slots", return_value=slots):
            engine._handle_select_date(db, session, {"row_key": "dia_1"})

        assert "last_listed_slots" in session.context
        assert "last_listed_shifts" not in session.context

    def test_valid_transition_awaiting_date_select_date_present(self):
        """AWAITING_DATE + SELECT_DATE deve existir em _VALID_TRANSITIONS."""
        assert ("AWAITING_DATE", BookingAction.SELECT_DATE) in BookingEngine._VALID_TRANSITIONS

    def test_awaiting_shift_not_in_valid_transitions(self):
        """AWAITING_SHIFT + SELECT_SHIFT não deve existir em _VALID_TRANSITIONS."""
        assert ("AWAITING_SHIFT", BookingAction.SELECT_SHIFT) not in BookingEngine._VALID_TRANSITIONS


class TestBackFromAwaitingTimeReturnsToDate:

    def test_back_state_map_awaiting_time_points_to_date(self):
        """_BACK_STATE['AWAITING_TIME'] deve ser 'AWAITING_DATE'."""
        assert _BACK_STATE.get("AWAITING_TIME") == "AWAITING_DATE", (
            f"Esperava AWAITING_DATE, obteve {_BACK_STATE.get('AWAITING_TIME')}"
        )

    def test_back_state_map_awaiting_shift_absent(self):
        """AWAITING_SHIFT não deve existir em _BACK_STATE."""
        assert "AWAITING_SHIFT" not in _BACK_STATE

    def test_back_action_in_awaiting_time_transitions_to_date(self):
        """BACK em AWAITING_TIME deve mover sessão para AWAITING_DATE."""
        engine = BookingEngine()
        db = MagicMock()

        ctx = {
            "service_id": str(SERVICE_ID),
            "professional_id": str(PROFESSIONAL_ID),
            "selected_date": "2026-06-01",
        }
        session = _make_session("AWAITING_TIME", ctx)

        dates_mock = [
            MagicMock(date=date(2026, 6, 1), label="Segunda (01/06)",
                      has_availability=True, row_key="dia_1")
        ]
        with patch.object(engine, "list_available_dates_paged",
                          return_value=(dates_mock, False, False)):
            result = engine._handle_back(db, session, {})

        assert result.next_state == "AWAITING_DATE"
        assert session.state == "AWAITING_DATE"


class TestSelectShiftRemovedFromFlow:

    def test_select_shift_in_awaiting_time_raises_invalid_action(self):
        """SELECT_SHIFT não deve ser válido em nenhum estado do fluxo atual."""
        engine = BookingEngine()
        db = MagicMock()

        session = _make_session("AWAITING_TIME", {
            "service_id": str(SERVICE_ID),
            "professional_id": str(PROFESSIONAL_ID),
            "selected_date": "2026-06-01",
        })
        session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        with pytest.raises(InvalidActionError):
            engine.update(db, session, BookingAction.SELECT_SHIFT, {"shift": "manha"})

    def test_select_shift_in_awaiting_date_raises_invalid_action(self):
        """SELECT_SHIFT também não é válido em AWAITING_DATE."""
        engine = BookingEngine()
        db = MagicMock()

        session = _make_session("AWAITING_DATE", {})
        session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        with pytest.raises(InvalidActionError):
            engine.update(db, session, BookingAction.SELECT_SHIFT, {"shift": "tarde"})

    def test_legacy_session_in_awaiting_shift_returns_invalid_action(self):
        """
        Sessão legada em state='AWAITING_SHIFT' que recebe qualquer ação
        deve levantar InvalidActionError (não 500).
        """
        engine = BookingEngine()
        db = MagicMock()

        # Simula sessão que ficou presa em AWAITING_SHIFT antes da migração
        session = _make_session("AWAITING_SHIFT", {})
        session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        with pytest.raises(InvalidActionError):
            engine.update(db, session, BookingAction.SELECT_SHIFT, {"shift": "tarde"})

    def test_legacy_session_back_from_awaiting_shift_resets(self):
        """
        BACK em sessão legada AWAITING_SHIFT deve acionar _handle_reset
        (AWAITING_SHIFT não está em _BACK_STATE → cai no fallback reset).
        """
        engine = BookingEngine()
        db = MagicMock()

        session = _make_session("AWAITING_SHIFT", {
            "service_id": str(SERVICE_ID),
        })
        session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        services_mock = []
        with patch.object(engine, "list_services", return_value=services_mock):
            result = engine.update(db, session, BookingAction.BACK, {})

        assert result.next_state == "AWAITING_SERVICE"
