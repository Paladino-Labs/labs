"""Contrato 1 — FSM de Operações (appointments).

NOTA DE CONTRATO: o enunciado do Sprint 25 assume estados
DRAFT/REQUESTED/CONFIRMED, que **não existem** no Estágio 0. A FSM real
(app/domain/enums/appointment_status.py) tem 5 estados:
    SCHEDULED → {IN_PROGRESS, COMPLETED, CANCELLED, NO_SHOW}
    IN_PROGRESS → {COMPLETED, CANCELLED}
    COMPLETED | CANCELLED | NO_SHOW → terminais
Estes testes validam a FSM **real**.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domain.enums import AppointmentStatus
from app.modules.appointments.transitions import transition
import app.infrastructure.event_bus as event_bus_mod


def _appt(status=AppointmentStatus.SCHEDULED.value):
    return SimpleNamespace(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        professional_id=uuid.uuid4(),
        status=status,
        version=1,
        manage_token_hash="hash",
        manage_token_expires_at="2026-01-01",
        services=[SimpleNamespace(service_id=uuid.uuid4(), price_snapshot=Decimal("100"))],
    )


class TestFSMTransitions:
    def test_scheduled_to_in_progress(self, db):
        a = _appt()
        transition(db, a, AppointmentStatus.IN_PROGRESS)
        assert a.status == "IN_PROGRESS"
        assert a.version == 2

    def test_scheduled_to_completed(self, db):
        """SCHEDULED → COMPLETED (admin conclui diretamente)."""
        a = _appt()
        transition(db, a, AppointmentStatus.COMPLETED)
        assert a.status == "COMPLETED"

    def test_in_progress_to_completed(self, db):
        a = _appt(AppointmentStatus.IN_PROGRESS.value)
        transition(db, a, AppointmentStatus.COMPLETED)
        assert a.status == "COMPLETED"

    def test_scheduled_to_cancelled(self, db):
        a = _appt()
        transition(db, a, AppointmentStatus.CANCELLED)
        assert a.status == "CANCELLED"

    def test_scheduled_to_no_show(self, db):
        a = _appt()
        transition(db, a, AppointmentStatus.NO_SHOW)
        assert a.status == "NO_SHOW"

    def test_terminal_zeroes_manage_token(self, db):
        a = _appt()
        transition(db, a, AppointmentStatus.COMPLETED)
        assert a.manage_token_hash is None
        assert a.manage_token_expires_at is None

    @pytest.mark.parametrize("terminal", ["COMPLETED", "CANCELLED", "NO_SHOW"])
    def test_terminal_is_terminal(self, db, terminal):
        a = _appt(terminal)
        with pytest.raises(HTTPException) as exc:
            transition(db, a, AppointmentStatus.IN_PROGRESS)
        assert exc.value.status_code == 409

    def test_invalid_transition_raises(self, db):
        """IN_PROGRESS → NO_SHOW não é permitida."""
        a = _appt(AppointmentStatus.IN_PROGRESS.value)
        with pytest.raises(HTTPException) as exc:
            transition(db, a, AppointmentStatus.NO_SHOW)
        assert exc.value.status_code == 409

    def test_status_log_recorded(self, db):
        from app.infrastructure.db.models import AppointmentStatusLog
        a = _appt()
        transition(db, a, AppointmentStatus.IN_PROGRESS)
        logs = db.store_for(AppointmentStatusLog)
        assert len(logs) == 1
        assert logs[0].from_status == "SCHEDULED"
        assert logs[0].to_status == "IN_PROGRESS"

    def test_operation_completed_event_published(self, db):
        captured = []
        event_bus_mod.event_bus.register("operation.completed", lambda e: captured.append(e))
        a = _appt()
        transition(db, a, AppointmentStatus.COMPLETED)
        assert len(captured) == 1
        payload = captured[0].payload
        assert payload["appointment_id"] == str(a.id)
        assert payload["company_id"] == str(a.company_id)
        assert payload["customer_id"] == str(a.client_id)
