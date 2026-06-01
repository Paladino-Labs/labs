"""
Testes pós-produção: specialty em Professional, stock em Product,
e múltiplos períodos por dia em WorkingHour.

Estratégia:
- Schema/validação Pydantic: instância direta, sem banco.
- Lógica de serviço (422s): MagicMock para DB.
- Persistência (DELETe+INSERT, substituição): SQLite em memória com
  tabelas customizadas e monkey-patch nos módulos de modelo.
"""
import uuid
from datetime import time, datetime
from typing import List
from unittest.mock import MagicMock, call, patch

import sqlite3
import pytest
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Boolean,
    Integer,
    Time,
    TIMESTAMP,
)
from sqlalchemy.orm import sessionmaker, declarative_base

# Permite que uuid.UUID seja serializado como string pelo driver pysqlite
sqlite3.register_adapter(uuid.UUID, str)

# ── Base SQLite ────────────────────────────────────────────────────────────────

SQLITE_URL = "sqlite://"
TestBase = declarative_base()


class TWorkingHour(TestBase):
    """WorkingHour sem UniqueConstraint para testes multi-período."""
    __tablename__ = "working_hours"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False)
    professional_id = Column(String(36), nullable=False)
    weekday = Column(Integer, nullable=False)
    opening_time = Column(Time, nullable=False)
    closing_time = Column(Time, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


# ── Fixtures SQLite ────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def sqlite_engine():
    e = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
    TestBase.metadata.create_all(bind=e)
    yield e
    TestBase.metadata.drop_all(bind=e)


@pytest.fixture(scope="function")
def db_session(sqlite_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sqlite_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def patched_db_session(db_session):
    """Session SQLite com WorkingHour patchado para TWorkingHour."""
    import app.infrastructure.db.models.availability_slot as avail_module
    import app.infrastructure.db.models as models_pkg
    import app.modules.schedule.service as svc_module

    orig_wh_avail = avail_module.WorkingHour
    orig_wh_models = models_pkg.WorkingHour
    orig_wh_svc = svc_module.WorkingHour

    avail_module.WorkingHour = TWorkingHour
    models_pkg.WorkingHour = TWorkingHour
    svc_module.WorkingHour = TWorkingHour

    try:
        yield db_session
    finally:
        avail_module.WorkingHour = orig_wh_avail
        models_pkg.WorkingHour = orig_wh_models
        svc_module.WorkingHour = orig_wh_svc


# ── Item 1: specialty em Professional ─────────────────────────────────────────

class TestProfessionalSpecialty:

    def test_patch_professional_specialty_persists(self):
        """update_professional com specialty seta o atributo via setattr."""
        from app.modules.professionals.service import update_professional
        from app.modules.professionals.schemas import ProfessionalUpdate

        company_id = uuid.uuid4()
        prof_id = uuid.uuid4()

        mock_prof = MagicMock()
        mock_prof.id = prof_id
        mock_prof.company_id = company_id

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_prof

        data = ProfessionalUpdate(specialty="Barbeiro Senior")
        update_professional(mock_db, company_id, prof_id, data)

        mock_db.commit.assert_called_once()
        assert mock_prof.specialty == "Barbeiro Senior"

    def test_professional_response_has_specialty_field(self):
        """ProfessionalResponse aceita specialty no modelo Pydantic."""
        from app.modules.professionals.schemas import ProfessionalResponse

        resp = ProfessionalResponse(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            name="Carlos",
            active=True,
            specialty="Colorista",
        )
        assert resp.specialty == "Colorista"

    def test_professional_response_specialty_optional(self):
        """ProfessionalResponse aceita specialty=None."""
        from app.modules.professionals.schemas import ProfessionalResponse

        resp = ProfessionalResponse(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            name="Ana",
            active=True,
        )
        assert resp.specialty is None


# ── Item 2: stock em Product ───────────────────────────────────────────────────

class TestProductStock:

    def test_stock_negative_raises_validation_error(self):
        """ProductUpdate com stock=-1 levanta ValidationError (422)."""
        from pydantic import ValidationError
        from app.modules.products.schemas import ProductUpdate

        with pytest.raises(ValidationError) as exc_info:
            ProductUpdate(stock=-1)

        errors = exc_info.value.errors()
        assert any("stock" in str(e["loc"]) for e in errors)

    def test_stock_zero_is_valid(self):
        """stock=0 é válido (limite inferior)."""
        from app.modules.products.schemas import ProductUpdate

        data = ProductUpdate(stock=0)
        assert data.stock == 0

    def test_stock_positive_is_valid(self):
        """stock=5 é válido."""
        from app.modules.products.schemas import ProductUpdate

        data = ProductUpdate(stock=5)
        assert data.stock == 5

    def test_patch_product_stock_persists(self):
        """update_product com stock=5 persiste via setattr."""
        from app.modules.products.service import update_product
        from app.modules.products.schemas import ProductUpdate

        company_id = uuid.uuid4()
        product_id = uuid.uuid4()

        mock_product = MagicMock()
        mock_product.id = product_id
        mock_product.company_id = company_id

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_product

        data = ProductUpdate(stock=5)
        update_product(mock_db, company_id, product_id, data)

        mock_db.commit.assert_called_once()
        assert mock_product.stock == 5


# ── Item 3: múltiplos períodos por dia ────────────────────────────────────────

class TestWorkingHourValidations:
    """Valida 422s sem precisar de banco real."""

    def _make_period(self, start: str, end: str):
        from app.modules.schedule.schemas import WorkingHourPeriod

        h_s, m_s = start.split(":")
        h_e, m_e = end.split(":")
        return WorkingHourPeriod(
            start_time=time(int(h_s), int(m_s)),
            end_time=time(int(h_e), int(m_e)),
        )

    def _make_mock_db(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.delete.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None
        return mock_db

    def test_four_periods_raises_422(self):
        from app.modules.schedule.service import replace_working_hours_for_day
        from fastapi import HTTPException

        periods = [
            self._make_period("09:00", "10:00"),
            self._make_period("10:30", "11:30"),
            self._make_period("12:00", "13:00"),
            self._make_period("14:00", "15:00"),
        ]
        with pytest.raises(HTTPException) as exc:
            replace_working_hours_for_day(
                self._make_mock_db(), uuid.uuid4(), uuid.uuid4(), 0, periods
            )
        assert exc.value.status_code == 422
        assert "3" in exc.value.detail

    def test_start_after_end_raises_422(self):
        from app.modules.schedule.service import replace_working_hours_for_day
        from fastapi import HTTPException

        periods = [self._make_period("12:00", "09:00")]
        with pytest.raises(HTTPException) as exc:
            replace_working_hours_for_day(
                self._make_mock_db(), uuid.uuid4(), uuid.uuid4(), 0, periods
            )
        assert exc.value.status_code == 422

    def test_equal_start_end_raises_422(self):
        from app.modules.schedule.service import replace_working_hours_for_day
        from fastapi import HTTPException

        periods = [self._make_period("09:00", "09:00")]
        with pytest.raises(HTTPException) as exc:
            replace_working_hours_for_day(
                self._make_mock_db(), uuid.uuid4(), uuid.uuid4(), 0, periods
            )
        assert exc.value.status_code == 422

    def test_overlapping_periods_raises_422(self):
        from app.modules.schedule.service import replace_working_hours_for_day
        from fastapi import HTTPException

        periods = [
            self._make_period("09:00", "12:00"),
            self._make_period("11:00", "14:00"),
        ]
        with pytest.raises(HTTPException) as exc:
            replace_working_hours_for_day(
                self._make_mock_db(), uuid.uuid4(), uuid.uuid4(), 0, periods
            )
        assert exc.value.status_code == 422
        assert "sobrepõem" in exc.value.detail

    def test_three_valid_periods_accepted(self):
        from app.modules.schedule.service import replace_working_hours_for_day

        mock_db = self._make_mock_db()
        periods = [
            self._make_period("08:00", "10:00"),
            self._make_period("10:30", "12:30"),
            self._make_period("14:00", "18:00"),
        ]
        result = replace_working_hours_for_day(
            mock_db, uuid.uuid4(), uuid.uuid4(), 1, periods
        )
        assert mock_db.commit.called
        assert len(result) == 3


class TestWorkingHourPersistence:
    """
    Testes de persistência com SQLite em memória.

    Usa strings para IDs (ao invés de uuid.UUID) para evitar mismatch de tipo
    nas queries SQLite — o adaptador uuid→str funciona no INSERT mas pode falhar
    na comparação do WHERE dependendo do driver.
    """

    def _make_period(self, start: str, end: str):
        from app.modules.schedule.schemas import WorkingHourPeriod

        h_s, m_s = start.split(":")
        h_e, m_e = end.split(":")
        return WorkingHourPeriod(
            start_time=time(int(h_s), int(m_s)),
            end_time=time(int(h_e), int(m_e)),
        )

    def _ids(self):
        """Retorna (company_id_str, professional_id_str) como strings."""
        return str(uuid.uuid4()), str(uuid.uuid4())

    def test_two_periods_inserted_and_listed(self, patched_db_session):
        """PUT com 2 períodos → list_working_hours retorna 2 linhas."""
        from app.modules.schedule.service import replace_working_hours_for_day, list_working_hours

        company_id, professional_id = self._ids()
        weekday = 1

        periods = [
            self._make_period("09:00", "12:00"),
            self._make_period("13:30", "18:00"),
        ]
        replace_working_hours_for_day(
            patched_db_session, company_id, professional_id, weekday, periods
        )

        rows = list_working_hours(patched_db_session, company_id, professional_id)
        assert len(rows) == 2
        times = sorted([(r.opening_time, r.closing_time) for r in rows])
        assert times[0] == (time(9, 0), time(12, 0))
        assert times[1] == (time(13, 30), time(18, 0))

    def test_empty_list_deletes_all(self, patched_db_session):
        """PUT com lista vazia → GET retorna 0 linhas (dia de folga)."""
        from app.modules.schedule.service import replace_working_hours_for_day, list_working_hours

        company_id, professional_id = self._ids()
        weekday = 2

        # Primeiro insere 1 período
        replace_working_hours_for_day(
            patched_db_session, company_id, professional_id, weekday,
            [self._make_period("09:00", "12:00")]
        )
        assert len(list_working_hours(patched_db_session, company_id, professional_id)) == 1

        # Segundo PUT com lista vazia — deve deletar
        replace_working_hours_for_day(
            patched_db_session, company_id, professional_id, weekday, []
        )
        assert len(list_working_hours(patched_db_session, company_id, professional_id)) == 0

    def test_second_put_replaces_previous(self, patched_db_session):
        """Segunda PUT no mesmo weekday substitui completamente os anteriores."""
        from app.modules.schedule.service import replace_working_hours_for_day, list_working_hours

        company_id, professional_id = self._ids()
        weekday = 3

        # Primeira chamada: 2 períodos
        replace_working_hours_for_day(
            patched_db_session, company_id, professional_id, weekday,
            [
                self._make_period("08:00", "12:00"),
                self._make_period("14:00", "18:00"),
            ]
        )
        assert len(list_working_hours(patched_db_session, company_id, professional_id)) == 2

        # Segunda chamada: 1 período diferente
        replace_working_hours_for_day(
            patched_db_session, company_id, professional_id, weekday,
            [self._make_period("10:00", "16:00")]
        )
        rows = list_working_hours(patched_db_session, company_id, professional_id)
        assert len(rows) == 1
        assert rows[0].opening_time == time(10, 0)
        assert rows[0].closing_time == time(16, 0)

    def test_different_weekdays_isolated(self, patched_db_session):
        """PUT em weekday=1 não afeta weekday=2."""
        from app.modules.schedule.service import replace_working_hours_for_day, list_working_hours

        company_id, professional_id = self._ids()

        replace_working_hours_for_day(
            patched_db_session, company_id, professional_id, 1,
            [self._make_period("09:00", "12:00")]
        )
        replace_working_hours_for_day(
            patched_db_session, company_id, professional_id, 2,
            [self._make_period("13:00", "17:00")]
        )

        rows = list_working_hours(patched_db_session, company_id, professional_id)
        assert len(rows) == 2

        # PUT vazia em weekday=1 não afeta weekday=2
        replace_working_hours_for_day(
            patched_db_session, company_id, professional_id, 1, []
        )
        rows_after = list_working_hours(patched_db_session, company_id, professional_id)
        assert len(rows_after) == 1
        assert rows_after[0].opening_time == time(13, 0)
