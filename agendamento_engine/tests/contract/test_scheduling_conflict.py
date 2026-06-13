"""Contrato 2 — Conflito de agenda.

A camada de service (`_assert_slot_available`) é defense-in-depth contra
sobreposição de slots; o EXCLUDE CONSTRAINT (btree_gist + tsrange) garante a
exclusividade de forma concorrente no PostgreSQL real.

NOTA DE CONTRATO: "soft + firme" no Estágio 0 são Reservations (domínio
agenda). A exclusão concorrente real (dois inserts simultâneos) só é testável
contra PostgreSQL — coberta pelo teste gated por DATABASE_URL.
"""
import os
import uuid
from datetime import datetime, time, timedelta, timezone

import pytest
from fastapi import HTTPException

from conftest import requires_postgres

from app.infrastructure.db.models import Appointment, WorkingHour
from app.modules.appointments.service import _assert_slot_available


CID = uuid.uuid4()
PROF = uuid.uuid4()
# Slot 15:00–16:00 UTC (= 12:00–13:00 em America/Sao_Paulo — dentro da janela)
START = datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc)
END = datetime(2026, 6, 15, 16, 0, tzinfo=timezone.utc)


def _working_hours(db, professional_id=PROF):
    db.add(WorkingHour(
        id=uuid.uuid4(), company_id=CID, professional_id=professional_id,
        weekday=START.weekday(), opening_time=time(0, 0), closing_time=time(23, 59),
        is_active=True,
    ))


def _appt(professional_id, status="SCHEDULED", start=START, end=END):
    return Appointment(id=uuid.uuid4(), company_id=CID, client_id=uuid.uuid4(),
                       professional_id=professional_id, start_at=start, end_at=end,
                       status=status)


class TestSchedulingConflict:
    def test_free_slot_passes(self, db):
        _working_hours(db)
        _assert_slot_available(db, CID, PROF, START, END)  # não levanta

    def test_overlap_same_professional_conflicts(self, db):
        _working_hours(db)
        db.add(_appt(PROF))  # appointment ativo no mesmo slot
        with pytest.raises(HTTPException) as exc:
            _assert_slot_available(db, CID, PROF, START, END)
        assert exc.value.status_code == 409

    def test_different_professionals_no_conflict(self, db):
        other = uuid.uuid4()
        _working_hours(db, professional_id=other)
        db.add(_appt(PROF))  # ocupa para PROF, mas consultamos `other`
        _assert_slot_available(db, CID, other, START, END)  # não levanta

    def test_cancelled_releases_slot(self, db):
        _working_hours(db)
        db.add(_appt(PROF, status="CANCELLED"))
        _assert_slot_available(db, CID, PROF, START, END)  # não levanta

    def test_no_show_releases_slot(self, db):
        _working_hours(db)
        db.add(_appt(PROF, status="NO_SHOW"))
        _assert_slot_available(db, CID, PROF, START, END)  # não levanta

    def test_no_working_hour_rejects(self, db):
        with pytest.raises(HTTPException) as exc:
            _assert_slot_available(db, CID, PROF, START, END)
        assert exc.value.status_code == 422

    @requires_postgres
    def test_exclude_constraint_active(self):
        """PostgreSQL real → existe EXCLUDE CONSTRAINT garantindo exclusividade."""
        import sqlalchemy as sa
        engine = sa.create_engine(os.environ["DATABASE_URL"])
        with engine.connect() as conn:
            count = conn.execute(sa.text(
                "SELECT count(*) FROM pg_constraint WHERE contype = 'x'"
            )).scalar()
            assert count >= 1  # ao menos uma EXCLUDE constraint (no_overlap_per_professional)
