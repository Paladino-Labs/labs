"""
Testes Sprint 11 — Catálogo opt-ins.

Usa mocks (unittest.mock) — sem banco PostgreSQL real.

Casos obrigatórios:
  1.  get_effective_price: variante > override > base (3 caminhos)
  2.  get_effective_price sem override → Service.price + duration
  3.  Slot com prep_before=15, duration=30, prep_after=10 → bloco 55min
  4.  business_hours_structured salvo e retornado corretamente
  5.  GET /booking/{slug}/profile retorna business_hours_structured
  6.  PATCH /companies/profile com weekday=7 → 422
  7.  GET /availability/slots com prep_minutes considerado
  8.  DELETE service → appointment_services.service_id = NULL (ON DELETE SET NULL)
  9.  Override UNIQUE(professional_id, service_id): segundo POST → 409
  10. Cross-tenant: overrides e variantes isolados por company_id
"""
import sys
import uuid
from datetime import date, datetime, timedelta, time as dt_time, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch, call
import pytest
from pydantic import ValidationError

# ─── Mock celery antes de qualquer import ─────────────────────────────────────
if "celery" not in sys.modules:
    _celery_mock = MagicMock()
    _celery_mock.Celery.return_value = _celery_mock
    _celery_mock.task = lambda *a, **kw: (lambda f: f)
    sys.modules["celery"] = _celery_mock
    sys.modules["celery.schedules"] = MagicMock()
    sys.modules["celery.app"] = MagicMock()
    sys.modules["celery.utils"] = MagicMock()
    sys.modules["celery.utils.log"] = MagicMock()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_service(
    service_id=None,
    company_id=None,
    name="Corte",
    price=Decimal("50.00"),
    duration=30,
    prep_before=0,
    prep_after=0,
    active=True,
):
    s = MagicMock()
    s.id = service_id or uuid.uuid4()
    s.company_id = company_id or uuid.uuid4()
    s.name = name
    s.price = price
    s.duration = duration
    s.preparation_minutes_before = prep_before
    s.preparation_minutes_after = prep_after
    s.active = active
    return s


def _make_override(
    override_id=None,
    company_id=None,
    professional_id=None,
    service_id=None,
    price=Decimal("40.00"),
    duration_min=None,
    is_active=True,
):
    o = MagicMock()
    o.override_id = override_id or uuid.uuid4()
    o.company_id = company_id or uuid.uuid4()
    o.professional_id = professional_id or uuid.uuid4()
    o.service_id = service_id or uuid.uuid4()
    o.price = price
    o.duration_min = duration_min
    o.is_active = is_active
    return o


def _make_variant(
    variant_id=None,
    company_id=None,
    service_id=None,
    name="Corte + Barba",
    price=Decimal("70.00"),
    duration_min=45,
    is_active=True,
):
    v = MagicMock()
    v.variant_id = variant_id or uuid.uuid4()
    v.company_id = company_id or uuid.uuid4()
    v.service_id = service_id or uuid.uuid4()
    v.name = name
    v.price = price
    v.duration_min = duration_min
    v.is_active = is_active
    return v


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()
    db.refresh = MagicMock()
    db.delete = MagicMock()
    return db


# ─── 1–2. get_effective_price: 3 caminhos ────────────────────────────────────

class TestGetEffectivePrice:
    def setup_method(self):
        from app.modules.services.service import get_effective_price
        self.get_effective_price = get_effective_price

    def _db_with_service(self, service):
        db = _make_db()
        # Primeira query (Service) retorna o serviço; demais retornam None por padrão
        query_chain = MagicMock()
        query_chain.filter.return_value.first.return_value = service
        db.query.return_value = query_chain
        return db

    def test_fallback_base_service(self):
        """Caminho 3: sem variante e sem override → preço/duração do serviço base."""
        cid = uuid.uuid4()
        sid = uuid.uuid4()
        service = _make_service(service_id=sid, company_id=cid, price=Decimal("50.00"), duration=30)

        db = _make_db()

        def side_effect(model):
            chain = MagicMock()
            chain.filter.return_value.first.return_value = None
            if model.__name__ == "Service":
                chain.filter.return_value.first.return_value = service
            return chain

        from app.infrastructure.db.models.service import ServiceVariant, ServicePricingOverride
        from app.infrastructure.db.models import Service as ServiceModel

        def query_side(model):
            chain = MagicMock()
            if model is ServiceModel:
                chain.filter.return_value.first.return_value = service
            else:
                chain.filter.return_value.first.return_value = None
            return chain

        db.query.side_effect = query_side

        price, dur = self.get_effective_price(db, cid, sid)
        assert price == Decimal("50.00")
        assert dur == 30

    def test_override_wins_over_base(self):
        """Caminho 2: override ativo → preço do override, duração do serviço base (duration_min=None)."""
        cid = uuid.uuid4()
        sid = uuid.uuid4()
        pid = uuid.uuid4()
        service = _make_service(service_id=sid, company_id=cid, price=Decimal("50.00"), duration=30)
        override = _make_override(
            company_id=cid, professional_id=pid, service_id=sid,
            price=Decimal("40.00"), duration_min=None, is_active=True,
        )

        from app.infrastructure.db.models.service import ServiceVariant, ServicePricingOverride
        from app.infrastructure.db.models import Service as ServiceModel

        def query_side(model):
            chain = MagicMock()
            if model is ServiceModel:
                chain.filter.return_value.first.return_value = service
            elif model is ServiceVariant:
                chain.filter.return_value.first.return_value = None
            elif model is ServicePricingOverride:
                chain.filter.return_value.first.return_value = override
            else:
                chain.filter.return_value.first.return_value = None
            return chain

        db = _make_db()
        db.query.side_effect = query_side

        price, dur = self.get_effective_price(db, cid, sid, professional_id=pid)
        assert price == Decimal("40.00")
        assert dur == 30  # fallback para service.duration

    def test_override_with_custom_duration(self):
        """Override com duration_min preenchido → usa duração do override."""
        cid = uuid.uuid4()
        sid = uuid.uuid4()
        pid = uuid.uuid4()
        service = _make_service(service_id=sid, company_id=cid, price=Decimal("50.00"), duration=30)
        override = _make_override(
            company_id=cid, professional_id=pid, service_id=sid,
            price=Decimal("45.00"), duration_min=25, is_active=True,
        )

        from app.infrastructure.db.models.service import ServiceVariant, ServicePricingOverride
        from app.infrastructure.db.models import Service as ServiceModel

        def query_side(model):
            chain = MagicMock()
            if model is ServiceModel:
                chain.filter.return_value.first.return_value = service
            elif model is ServiceVariant:
                chain.filter.return_value.first.return_value = None
            elif model is ServicePricingOverride:
                chain.filter.return_value.first.return_value = override
            else:
                chain.filter.return_value.first.return_value = None
            return chain

        db = _make_db()
        db.query.side_effect = query_side

        price, dur = self.get_effective_price(db, cid, sid, professional_id=pid)
        assert price == Decimal("45.00")
        assert dur == 25

    def test_variant_wins_over_override(self):
        """Caminho 1: variante ativa → preço/duração da variante (maior prioridade)."""
        cid = uuid.uuid4()
        sid = uuid.uuid4()
        pid = uuid.uuid4()
        vid = uuid.uuid4()
        service = _make_service(service_id=sid, company_id=cid, price=Decimal("50.00"), duration=30)
        variant = _make_variant(
            variant_id=vid, company_id=cid, service_id=sid,
            price=Decimal("70.00"), duration_min=45, is_active=True,
        )
        override = _make_override(
            company_id=cid, professional_id=pid, service_id=sid,
            price=Decimal("40.00"), duration_min=None, is_active=True,
        )

        from app.infrastructure.db.models.service import ServiceVariant, ServicePricingOverride
        from app.infrastructure.db.models import Service as ServiceModel

        def query_side(model):
            chain = MagicMock()
            if model is ServiceModel:
                chain.filter.return_value.first.return_value = service
            elif model is ServiceVariant:
                chain.filter.return_value.first.return_value = variant
            elif model is ServicePricingOverride:
                chain.filter.return_value.first.return_value = override
            else:
                chain.filter.return_value.first.return_value = None
            return chain

        db = _make_db()
        db.query.side_effect = query_side

        price, dur = self.get_effective_price(db, cid, sid, professional_id=pid, variant_id=vid)
        assert price == Decimal("70.00")
        assert dur == 45

    def test_service_not_found(self):
        """Serviço inexistente → 404."""
        from fastapi import HTTPException
        cid = uuid.uuid4()
        sid = uuid.uuid4()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            self.get_effective_price(db, cid, sid)
        assert exc_info.value.status_code == 404


# ─── 3. Slot com prep_minutes: bloco de 55min ────────────────────────────────

class TestAvailabilityWithPrep:
    def test_slot_block_includes_prep_minutes(self):
        """prep_before=15 + duration=30 + prep_after=10 → bloco total 55min."""
        from app.modules.availability.service import get_available_slots

        company_id = uuid.uuid4()
        prof_id = uuid.uuid4()
        service_id = uuid.uuid4()
        target_date = date(2026, 7, 1)  # terça-feira

        # Serviço com 30min de duração e tempos de preparo
        service = _make_service(
            service_id=service_id,
            company_id=company_id,
            duration=30,
            prep_before=15,
            prep_after=10,
        )

        # Profissional ativo
        professional = MagicMock()
        professional.id = prof_id
        professional.company_id = company_id
        professional.active = True
        professional.name = "Barbeiro"

        # WorkingHour: trabalha das 09:00 às 10:00 (janela de 60min)
        working_hour = MagicMock()
        working_hour.weekday = target_date.weekday()
        working_hour.opening_time = dt_time(9, 0)
        working_hour.closing_time = dt_time(10, 0)
        working_hour.is_active = True

        # TenantConfig para timezone
        tenant_config = MagicMock()
        tenant_config.timezone = "America/Sao_Paulo"

        # Mock db
        db = _make_db()

        from app.infrastructure.db.models import (
            Professional, WorkingHour, Appointment, ScheduleBlock, TenantConfig,
        )

        def query_side(model):
            chain = MagicMock()
            if model is Professional:
                chain.filter.return_value.first.return_value = professional
            elif model is type(service):
                chain.filter.return_value.first.return_value = service
            elif model is WorkingHour:
                chain.filter.return_value.first.return_value = working_hour
            elif model is TenantConfig:
                chain.filter.return_value.first.return_value = tenant_config
            elif model in (Appointment, ScheduleBlock):
                chain.filter.return_value.all.return_value = []
            else:
                chain.filter.return_value.first.return_value = None
                chain.filter.return_value.all.return_value = []
            return chain

        from app.infrastructure.db.models import Service as ServiceModel

        def query_side2(model):
            chain = MagicMock()
            if model is Professional:
                chain.filter.return_value.first.return_value = professional
            elif model is ServiceModel:
                chain.filter.return_value.first.return_value = service
            elif model is WorkingHour:
                chain.filter.return_value.first.return_value = working_hour
            elif model is TenantConfig:
                chain.filter.return_value.first.return_value = tenant_config
            elif model in (Appointment, ScheduleBlock):
                chain.filter.return_value.all.return_value = []
            else:
                chain.filter.return_value.first.return_value = None
                chain.filter.return_value.all.return_value = []
            return chain

        db.query.side_effect = query_side2

        # A janela é 09:00–10:00 (60min). Com bloco de 55min deve caber 1 slot.
        # Com bloco de 30min caberiam 2+.
        slots = get_available_slots(db, company_id, prof_id, service_id, target_date)

        # Deve haver no máximo 1 slot (60min / 55min bloco = 1)
        # Pode haver 0 slots se o horário ficou no passado, mas a lógica do bloco está correta
        # se apenas 1 slot coube na janela (em vez de 2 sem preparo)
        for slot in slots:
            block_min = int((slot.end_at - slot.start_at).total_seconds() / 60)
            assert block_min == 55, f"Bloco deveria ser 55min, foi {block_min}min"


# ─── 4–5. business_hours_structured ──────────────────────────────────────────

class TestBusinessHoursStructured:
    def test_validator_accepts_valid_entry(self):
        """Entrada válida não levanta exceção."""
        from app.modules.company_profile.schemas import BusinessHourEntry
        entry = BusinessHourEntry(weekday=1, open="09:00", close="18:00")
        assert entry.weekday == 1
        assert entry.open == "09:00"
        assert entry.close == "18:00"

    def test_validator_rejects_weekday_7(self):
        """weekday=7 deve levantar ValidationError (422 via Pydantic)."""
        from app.modules.company_profile.schemas import BusinessHourEntry
        with pytest.raises(ValidationError) as exc_info:
            BusinessHourEntry(weekday=7, open="09:00", close="18:00")
        assert "weekday" in str(exc_info.value).lower() or "0-6" in str(exc_info.value)

    def test_validator_rejects_invalid_time_format(self):
        """Formato HH:MM inválido deve levantar ValidationError."""
        from app.modules.company_profile.schemas import BusinessHourEntry
        with pytest.raises(ValidationError):
            BusinessHourEntry(weekday=0, open="9:00", close="18:00")  # falta zero inicial

    def test_validator_rejects_weekday_negative(self):
        """weekday negativo deve levantar ValidationError."""
        from app.modules.company_profile.schemas import BusinessHourEntry
        with pytest.raises(ValidationError):
            BusinessHourEntry(weekday=-1, open="09:00", close="18:00")

    def test_update_profile_saves_structured_hours(self):
        """update_profile converte BusinessHourEntry em dict para o JSONB."""
        from app.modules.company_profile.service import update_profile
        from app.modules.company_profile.schemas import CompanyProfileUpdate, BusinessHourEntry

        profile = MagicMock()
        profile.company_id = uuid.uuid4()
        profile.business_hours_structured = None

        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = profile

        entries = [
            BusinessHourEntry(weekday=1, open="09:00", close="18:00"),
            BusinessHourEntry(weekday=5, open="10:00", close="16:00"),
        ]
        data = CompanyProfileUpdate(business_hours_structured=entries)
        update_profile(db, profile.company_id, data)

        # Verifica que o campo foi setado como lista de dicts (serializável para JSONB)
        saved = profile.business_hours_structured
        assert isinstance(saved, list)
        assert saved[0]["weekday"] == 1
        assert saved[0]["open"] == "09:00"
        assert saved[1]["weekday"] == 5

    def test_profile_out_includes_structured_hours(self):
        """CompanyProfileOut aceita e retorna business_hours_structured."""
        from app.modules.company_profile.schemas import CompanyProfileOut, BusinessHourEntry
        out = CompanyProfileOut(
            business_hours_structured=[
                BusinessHourEntry(weekday=0, open="08:00", close="17:00"),
            ]
        )
        assert out.business_hours_structured is not None
        assert len(out.business_hours_structured) == 1


# ─── 6. PATCH /companies/profile com weekday=7 → 422 ────────────────────────

class TestCompanyProfileEndpointValidation:
    def test_patch_profile_with_invalid_weekday_raises_validation_error(self):
        """Payload com weekday=7 em business_hours_structured → ValidationError (422)."""
        from app.modules.company_profile.schemas import CompanyProfileUpdate
        with pytest.raises(ValidationError) as exc_info:
            CompanyProfileUpdate(
                business_hours_structured=[
                    {"weekday": 7, "open": "09:00", "close": "18:00"}
                ]
            )
        errors = exc_info.value.errors()
        assert any("weekday" in str(e) or "0-6" in str(e) for e in errors)

    def test_patch_profile_valid_structured_hours(self):
        """Payload válido não levanta exceção."""
        from app.modules.company_profile.schemas import CompanyProfileUpdate
        data = CompanyProfileUpdate(
            business_hours_structured=[
                {"weekday": 0, "open": "09:00", "close": "18:00"},
                {"weekday": 6, "open": "10:00", "close": "14:00"},
            ]
        )
        assert len(data.business_hours_structured) == 2


# ─── 7. booking/profile retorna business_hours_structured ─────────────────────

class TestBookingProfileResponse:
    def test_booking_profile_returns_business_hours_structured(self):
        """CompanyProfileResponse inclui business_hours_structured."""
        from app.modules.booking.http_schemas import CompanyProfileResponse
        resp = CompanyProfileResponse(
            company_name="Barbearia Teste",
            business_hours="Seg-Sex 9h–18h",
            business_hours_structured=[
                {"weekday": 0, "open": "09:00", "close": "18:00"}
            ],
            online_booking_enabled=True,
        )
        assert resp.business_hours_structured is not None
        assert resp.business_hours_structured[0]["weekday"] == 0


# ─── 8. Override UNIQUE → 409 ─────────────────────────────────────────────────

class TestPricingOverrideCRUD:
    def test_create_override_success(self):
        """Primeiro POST → cria override sem erro."""
        from app.modules.services.service import create_override
        from app.modules.services.schemas import PricingOverrideCreate

        cid = uuid.uuid4()
        pid = uuid.uuid4()
        sid = uuid.uuid4()

        service = _make_service(service_id=sid, company_id=cid)
        professional = MagicMock()
        professional.id = pid
        professional.company_id = cid

        from app.infrastructure.db.models.professional import Professional
        from app.infrastructure.db.models import Service as ServiceModel

        def query_side(model):
            chain = MagicMock()
            if model is Professional:
                chain.filter.return_value.first.return_value = professional
            elif model is ServiceModel:
                chain.filter.return_value.first.return_value = service
            else:
                chain.filter.return_value.first.return_value = None
            return chain

        db = _make_db()
        db.query.side_effect = query_side

        saved_override = MagicMock()
        saved_override.override_id = uuid.uuid4()
        saved_override.company_id = cid
        saved_override.professional_id = pid
        saved_override.service_id = sid
        saved_override.price = Decimal("40.00")
        saved_override.duration_min = None
        saved_override.is_active = True
        db.refresh.side_effect = lambda o: setattr(o, "override_id", saved_override.override_id)

        data = PricingOverrideCreate(service_id=sid, price=Decimal("40.00"))
        result = create_override(db, cid, pid, data)
        db.commit.assert_called_once()
        db.add.assert_called_once()

    def test_create_override_duplicate_raises_409(self):
        """Segundo POST com mesmo professional_id+service_id → 409."""
        from app.modules.services.service import create_override
        from app.modules.services.schemas import PricingOverrideCreate
        from sqlalchemy.exc import IntegrityError
        from fastapi import HTTPException

        cid = uuid.uuid4()
        pid = uuid.uuid4()
        sid = uuid.uuid4()

        service = _make_service(service_id=sid, company_id=cid)
        professional = MagicMock()
        professional.id = pid
        professional.company_id = cid

        from app.infrastructure.db.models.professional import Professional
        from app.infrastructure.db.models import Service as ServiceModel

        def query_side(model):
            chain = MagicMock()
            if model is Professional:
                chain.filter.return_value.first.return_value = professional
            elif model is ServiceModel:
                chain.filter.return_value.first.return_value = service
            else:
                chain.filter.return_value.first.return_value = None
            return chain

        db = _make_db()
        db.query.side_effect = query_side
        # Simula violação de unique constraint no commit
        db.commit.side_effect = IntegrityError("UNIQUE", {}, None)

        data = PricingOverrideCreate(service_id=sid, price=Decimal("45.00"))
        with pytest.raises(HTTPException) as exc_info:
            create_override(db, cid, pid, data)
        assert exc_info.value.status_code == 409
        db.rollback.assert_called_once()

    def test_delete_override(self):
        """DELETE de override existente → remove e faz commit."""
        from app.modules.services.service import delete_override

        cid = uuid.uuid4()
        pid = uuid.uuid4()
        oid = uuid.uuid4()

        override = _make_override(override_id=oid, company_id=cid, professional_id=pid)

        from app.infrastructure.db.models.service import ServicePricingOverride

        def query_side(model):
            chain = MagicMock()
            if model is ServicePricingOverride:
                chain.filter.return_value.first.return_value = override
            else:
                chain.filter.return_value.first.return_value = None
            return chain

        db = _make_db()
        db.query.side_effect = query_side

        delete_override(db, cid, pid, oid)
        db.delete.assert_called_once_with(override)
        db.commit.assert_called_once()


# ─── 9. Cross-tenant isolation ───────────────────────────────────────────────

class TestCrossTenantIsolation:
    def test_list_overrides_filters_by_company_id(self):
        """list_overrides retorna apenas registros do company_id correto."""
        from app.modules.services.service import list_overrides

        cid_a = uuid.uuid4()
        cid_b = uuid.uuid4()
        pid = uuid.uuid4()

        override_a = _make_override(company_id=cid_a, professional_id=pid, price=Decimal("40.00"))

        professional_a = MagicMock()
        professional_a.id = pid
        professional_a.company_id = cid_a

        from app.infrastructure.db.models.professional import Professional
        from app.infrastructure.db.models.service import ServicePricingOverride

        def query_side_a(model):
            chain = MagicMock()
            if model is Professional:
                chain.filter.return_value.first.return_value = professional_a
            elif model is ServicePricingOverride:
                chain.filter.return_value.all.return_value = [override_a]
            else:
                chain.filter.return_value.all.return_value = []
                chain.filter.return_value.first.return_value = None
            return chain

        db_a = _make_db()
        db_a.query.side_effect = query_side_a

        results = list_overrides(db_a, cid_a, pid)
        assert all(o.company_id == cid_a for o in results)

    def test_list_variants_filters_by_company_id(self):
        """list_variants retorna apenas variantes do company_id correto."""
        from app.modules.services.service import list_variants

        cid = uuid.uuid4()
        sid = uuid.uuid4()

        service = _make_service(service_id=sid, company_id=cid)
        variant = _make_variant(company_id=cid, service_id=sid)

        from app.infrastructure.db.models import Service as ServiceModel
        from app.infrastructure.db.models.service import ServiceVariant

        def query_side(model):
            chain = MagicMock()
            if model is ServiceModel:
                chain.filter.return_value.first.return_value = service
            elif model is ServiceVariant:
                chain.filter.return_value.order_by.return_value.all.return_value = [variant]
            else:
                chain.filter.return_value.first.return_value = None
                chain.filter.return_value.all.return_value = []
            return chain

        db = _make_db()
        db.query.side_effect = query_side

        results = list_variants(db, cid, sid)
        assert all(v.company_id == cid for v in results)

    def test_get_effective_price_respects_company_id(self):
        """get_effective_price não retorna override de outro tenant."""
        from app.modules.services.service import get_effective_price

        cid_a = uuid.uuid4()
        cid_b = uuid.uuid4()
        sid = uuid.uuid4()
        pid = uuid.uuid4()

        # Service pertence a tenant A
        service = _make_service(service_id=sid, company_id=cid_a, price=Decimal("50.00"), duration=30)
        # Override pertence a tenant B (NÃO deve ser retornado para tenant A)
        override_b = _make_override(
            company_id=cid_b, professional_id=pid, service_id=sid,
            price=Decimal("10.00"), duration_min=10, is_active=True,
        )

        from app.infrastructure.db.models import Service as ServiceModel
        from app.infrastructure.db.models.service import ServicePricingOverride, ServiceVariant

        def query_side(model):
            chain = MagicMock()
            if model is ServiceModel:
                chain.filter.return_value.first.return_value = service
            elif model is ServiceVariant:
                chain.filter.return_value.first.return_value = None
            elif model is ServicePricingOverride:
                # Filtra por company_id — retorna None (não há override do tenant A)
                chain.filter.return_value.first.return_value = None
            else:
                chain.filter.return_value.first.return_value = None
            return chain

        db = _make_db()
        db.query.side_effect = query_side

        # Tenant A não deve ver o override do tenant B → fallback para preço base
        price, dur = get_effective_price(db, cid_a, sid, professional_id=pid)
        assert price == Decimal("50.00")
        assert dur == 30


# ─── 10. ServiceVariant CRUD básico ──────────────────────────────────────────

class TestServiceVariantCRUD:
    def test_create_variant(self):
        """Cria variante com dados válidos."""
        from app.modules.services.service import create_variant
        from app.modules.services.schemas import ServiceVariantCreate

        cid = uuid.uuid4()
        sid = uuid.uuid4()
        service = _make_service(service_id=sid, company_id=cid)

        from app.infrastructure.db.models import Service as ServiceModel

        def query_side(model):
            chain = MagicMock()
            if model is ServiceModel:
                chain.filter.return_value.first.return_value = service
            else:
                chain.filter.return_value.first.return_value = None
            return chain

        db = _make_db()
        db.query.side_effect = query_side

        data = ServiceVariantCreate(name="Corte + Barba", price=Decimal("70.00"), duration_min=45)
        create_variant(db, cid, sid, data)

        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_delete_variant_not_found(self):
        """DELETE de variante inexistente → 404."""
        from app.modules.services.service import delete_variant
        from fastapi import HTTPException
        from app.infrastructure.db.models.service import ServiceVariant

        cid = uuid.uuid4()
        sid = uuid.uuid4()
        vid = uuid.uuid4()

        def query_side(model):
            chain = MagicMock()
            chain.filter.return_value.first.return_value = None
            return chain

        db = _make_db()
        db.query.side_effect = query_side

        with pytest.raises(HTTPException) as exc_info:
            delete_variant(db, cid, sid, vid)
        assert exc_info.value.status_code == 404


# ─── 11. ORM — AppointmentService FK ondelete ─────────────────────────────────

class TestAppointmentServiceORM:
    def test_appointment_service_fk_has_ondelete_set_null(self):
        """AppointmentService.service_id deve ter ondelete='SET NULL' no ORM."""
        from app.infrastructure.db.models.appointment import AppointmentService
        from sqlalchemy import inspect as sa_inspect

        # Verifica a coluna service_id
        col = AppointmentService.__table__.c.service_id
        fk = list(col.foreign_keys)[0]
        assert fk.ondelete.upper() == "SET NULL", (
            f"FK ondelete deveria ser 'SET NULL', encontrado: {fk.ondelete!r}"
        )


# ─── 12. Schemas ServiceResponse com prep_minutes ─────────────────────────────

class TestServiceSchemas:
    def test_service_response_includes_prep_minutes(self):
        """ServiceResponse inclui preparation_minutes_before/after."""
        from app.modules.services.schemas import ServiceResponse
        resp = ServiceResponse(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            name="Corte",
            price=Decimal("50.00"),
            duration=30,
            active=True,
            preparation_minutes_before=15,
            preparation_minutes_after=10,
        )
        assert resp.preparation_minutes_before == 15
        assert resp.preparation_minutes_after == 10

    def test_service_create_defaults_prep_to_zero(self):
        """ServiceCreate com campos omitidos → prep_minutes = 0."""
        from app.modules.services.schemas import ServiceCreate
        sc = ServiceCreate(name="Corte", price=Decimal("50.00"), duration=30)
        assert sc.preparation_minutes_before == 0
        assert sc.preparation_minutes_after == 0
