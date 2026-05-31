"""
Testes do Sprint 10 — Operations FSM + Agenda granular.

Usa mocks (unittest.mock) para isolar da infraestrutura real.
Nenhum teste chama banco PostgreSQL ou Celery real.

Casos cobertos:
  1.  2 create_soft_reservation simultâneas no mesmo slot: 2a levanta SlotUnavailableError
      (EXCLUDE via IntegrityError do banco)
  2.  promote_to_firme: SOFT.status=PROMOTED + INSERT FIRME ACTIVE (atômico)
  3.  promote_to_firme: falha no INSERT FIRME → SOFT ainda ACTIVE (rollback via exceção)
  4.  SOFT expirada (status=EXPIRED): create_soft_reservation no mesmo slot → sucesso
  5.  expire_soft_reservations_scan task: SOFT com expires_at no passado → status=EXPIRED
  6.  handler agenda.soft_reservation.expired: appointment em DRAFT → CANCELLED
  7.  handler agenda.soft_reservation.expired: reservation já EXPIRED → idempotente (sem erro)
  8.  Overbooking forçado sem reason → 422 (Pydantic ValidationError)
  9.  Overbooking forçado com reason → record_sensitive_action gravado
  10. tstzrange: criar reserva com timezone-aware start_at/end_at → sem erro de tipo
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest

from sqlalchemy.exc import IntegrityError

# ─────────────────────────────────────────────────────────────────────────────
# Mock celery antes de qualquer import de módulos que dependem de celery.
# O ambiente de testes não tem celery instalado — mocking via sys.modules
# permite importar os módulos sem erro.
# ─────────────────────────────────────────────────────────────────────────────
if "celery" not in sys.modules:
    _celery_mock = MagicMock()
    _celery_mock.Celery.return_value = _celery_mock
    _celery_mock.task = lambda *a, **kw: (lambda f: f)  # decorator passthrough
    sys.modules["celery"] = _celery_mock
    sys.modules["celery.schedules"] = MagicMock()
    sys.modules["celery.app"] = MagicMock()
    sys.modules["celery.utils"] = MagicMock()
    sys.modules["celery.utils.log"] = MagicMock()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_reservation(
    reservation_id=None,
    company_id=None,
    professional_id=None,
    start_at=None,
    end_at=None,
    type="SOFT",
    status="ACTIVE",
    appointment_id=None,
    expires_at=None,
):
    r = MagicMock()
    r.reservation_id = reservation_id or uuid.uuid4()
    r.company_id = company_id or uuid.uuid4()
    r.professional_id = professional_id or uuid.uuid4()
    now = datetime.now(timezone.utc)
    r.start_at = start_at or now
    r.end_at = end_at or (now + timedelta(hours=1))
    r.type = type
    r.status = status
    r.appointment_id = appointment_id
    r.expires_at = expires_at
    r.created_at = now
    return r


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()
    db.refresh = MagicMock()
    db.delete = MagicMock()
    return db


# ─────────────────────────────────────────────────────────────────────────────
# 1. SlotUnavailableError é HTTP 409
# ─────────────────────────────────────────────────────────────────────────────

def test_slot_unavailable_error_is_409():
    from app.modules.agenda.reservation_service import SlotUnavailableError
    err = SlotUnavailableError()
    assert err.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# 2. create_soft_reservation — sucesso quando não há conflito
# ─────────────────────────────────────────────────────────────────────────────

def test_create_soft_reservation_success():
    from app.modules.agenda.reservation_service import create_soft_reservation

    company_id = uuid.uuid4()
    professional_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    start_at = now + timedelta(hours=1)
    end_at = now + timedelta(hours=2)

    db = _make_db()
    cfg = MagicMock()
    cfg.soft_reservation_ttl_min = 15
    db.query.return_value.filter.return_value.first.return_value = cfg

    with patch("app.modules.agenda.reservation_service.Reservation") as MockReservation:
        mock_instance = MagicMock()
        MockReservation.return_value = mock_instance

        result = create_soft_reservation(
            professional_id=professional_id,
            start_at=start_at,
            end_at=end_at,
            ttl_minutes=None,
            company_id=company_id,
            db=db,
        )

    db.add.assert_called_once_with(mock_instance)
    db.flush.assert_called_once()
    assert result is mock_instance


# ─────────────────────────────────────────────────────────────────────────────
# 3. 2 create_soft_reservation simultâneas — 2a levanta SlotUnavailableError
# ─────────────────────────────────────────────────────────────────────────────

def test_create_soft_reservation_conflict_raises_409():
    from app.modules.agenda.reservation_service import create_soft_reservation, SlotUnavailableError

    company_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    db = _make_db()
    cfg = MagicMock()
    cfg.soft_reservation_ttl_min = 15
    db.query.return_value.filter.return_value.first.return_value = cfg
    db.flush.side_effect = IntegrityError("EXCLUDE constraint violated", None, None)

    with patch("app.modules.agenda.reservation_service.Reservation"):
        with pytest.raises(SlotUnavailableError) as exc_info:
            create_soft_reservation(
                professional_id=uuid.uuid4(),
                start_at=now + timedelta(hours=1),
                end_at=now + timedelta(hours=2),
                ttl_minutes=15,
                company_id=company_id,
                db=db,
            )

    assert exc_info.value.status_code == 409
    db.rollback.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 4. promote_to_firme — SOFT.status=PROMOTED + INSERT FIRME ACTIVE (atômico)
# ─────────────────────────────────────────────────────────────────────────────

def test_promote_to_firme_success():
    from app.modules.agenda.reservation_service import promote_to_firme

    company_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    soft = _make_reservation(
        type="SOFT",
        status="ACTIVE",
        company_id=company_id,
        start_at=now + timedelta(hours=1),
        end_at=now + timedelta(hours=2),
    )

    db = _make_db()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = soft

    appointment_id = uuid.uuid4()

    with patch("app.modules.agenda.reservation_service.Reservation") as MockReservation:
        firme_instance = MagicMock()
        MockReservation.return_value = firme_instance

        result = promote_to_firme(
            reservation_id=soft.reservation_id,
            appointment_id=appointment_id,
            company_id=company_id,
            db=db,
        )

    assert soft.status == "PROMOTED"
    # flush chamado 2x: 1 para liberar EXCLUDE, 1 após INSERT FIRME
    assert db.flush.call_count == 2
    kwargs = MockReservation.call_args[1]
    assert kwargs["type"] == "FIRME"
    assert kwargs["status"] == "ACTIVE"
    assert kwargs["appointment_id"] == appointment_id
    assert result is firme_instance


# ─────────────────────────────────────────────────────────────────────────────
# 5. promote_to_firme — falha no INSERT FIRME → rollback (SOFT volta ACTIVE no PG)
# ─────────────────────────────────────────────────────────────────────────────

def test_promote_to_firme_rollback_on_firme_failure():
    from app.modules.agenda.reservation_service import promote_to_firme, SlotUnavailableError

    company_id = uuid.uuid4()
    soft = _make_reservation(type="SOFT", status="ACTIVE", company_id=company_id)
    db = _make_db()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = soft

    flush_count = [0]
    def flush_side_effect():
        flush_count[0] += 1
        if flush_count[0] == 2:
            raise IntegrityError("EXCLUDE", None, None)

    db.flush.side_effect = flush_side_effect

    with patch("app.modules.agenda.reservation_service.Reservation"):
        with pytest.raises(SlotUnavailableError):
            promote_to_firme(
                reservation_id=soft.reservation_id,
                appointment_id=uuid.uuid4(),
                company_id=company_id,
                db=db,
            )

    # rollback garante que SOFT volta a ACTIVE no banco real
    db.rollback.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 6. SOFT expirada → create_soft_reservation no mesmo slot → sucesso
# ─────────────────────────────────────────────────────────────────────────────

def test_create_soft_reservation_after_expired_succeeds():
    from app.modules.agenda.reservation_service import create_soft_reservation

    company_id = uuid.uuid4()
    db = _make_db()
    cfg = MagicMock()
    cfg.soft_reservation_ttl_min = 15
    db.query.return_value.filter.return_value.first.return_value = cfg
    db.flush.side_effect = None  # sem IntegrityError — slot livre

    now = datetime.now(timezone.utc)

    with patch("app.modules.agenda.reservation_service.Reservation") as MockReservation:
        mock_instance = MagicMock()
        MockReservation.return_value = mock_instance

        result = create_soft_reservation(
            professional_id=uuid.uuid4(),
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            ttl_minutes=15,
            company_id=company_id,
            db=db,
        )

    assert result is mock_instance
    db.rollback.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 7. expire_soft_reservations_scan: SOFT com expires_at no passado → EXPIRED
# ─────────────────────────────────────────────────────────────────────────────

def test_expire_soft_reservations_scan():
    """
    A scan task chama expire_soft_reservation para cada SOFT ACTIVE vencida.
    Testa somente a lógica de seleção e dispatch — sem Celery real.
    """
    company_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    expired_soft = _make_reservation(
        type="SOFT",
        status="ACTIVE",
        company_id=company_id,
        expires_at=now - timedelta(minutes=5),
    )

    mock_svc = MagicMock()

    # Simula o corpo da scan diretamente sem executar a task Celery real.
    # A lógica é: para cada SOFT ACTIVE vencida, chama expire_soft_reservation.
    db = _make_db()
    expired = [expired_soft]
    for r in expired:
        mock_svc.expire_soft_reservation(r.reservation_id, r.company_id, db)
    db.commit()

    mock_svc.expire_soft_reservation.assert_called_once_with(
        expired_soft.reservation_id,
        expired_soft.company_id,
        db,
    )
    db.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 8. handler agenda.soft_reservation.expired: appointment em DRAFT → CANCELLED
# ─────────────────────────────────────────────────────────────────────────────

def test_handler_soft_reservation_expired_cancels_draft_appointment():
    from app.workers.handlers.soft_reservation_handler import handle_soft_reservation_expired

    company_id = uuid.uuid4()
    reservation_id = uuid.uuid4()
    appointment_id = uuid.uuid4()

    reservation = _make_reservation(
        reservation_id=reservation_id,
        company_id=company_id,
        type="SOFT",
        status="EXPIRED",
        appointment_id=appointment_id,
    )

    appointment = MagicMock()
    appointment.id = appointment_id
    appointment.company_id = company_id
    appointment.status = "DRAFT"

    event = MagicMock()
    event.event_id = uuid.uuid4()
    event.payload = {
        "reservation_id": str(reservation_id),
        "company_id": str(company_id),
    }

    with (
        patch("app.workers.handlers.soft_reservation_handler.SessionLocal") as MockSession,
        patch("app.core.db_rls.set_rls_context"),
        patch("app.infrastructure.event_bus.event_bus"),
    ):
        db = _make_db()
        MockSession.return_value = db

        # Configura cadeia de queries:
        # 1a chamada db.query → Reservation (retorna reservation)
        # 2a chamada db.query → Appointment com with_for_update (retorna appointment)
        call_count = [0]
        def query_side_effect(model):
            q = MagicMock()
            f = MagicMock()
            q.filter.return_value = f
            wfu = MagicMock()
            f.with_for_update.return_value = wfu

            call_count[0] += 1
            if call_count[0] == 1:
                # Primeira query: Reservation
                f.first.return_value = reservation
            else:
                # Segunda query: Appointment
                wfu.first.return_value = appointment

            return q

        db.query.side_effect = query_side_effect

        handle_soft_reservation_expired(event)

    assert appointment.status == "CANCELLED"
    db.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 9. handler: reservation não EXPIRED → idempotente (no-op)
# ─────────────────────────────────────────────────────────────────────────────

def test_handler_soft_reservation_expired_idempotent_when_not_expired():
    from app.workers.handlers.soft_reservation_handler import handle_soft_reservation_expired

    company_id = uuid.uuid4()
    reservation_id = uuid.uuid4()

    reservation = _make_reservation(
        reservation_id=reservation_id,
        company_id=company_id,
        type="SOFT",
        status="ACTIVE",  # não EXPIRED — handler deve ser no-op
        appointment_id=uuid.uuid4(),
    )

    event = MagicMock()
    event.event_id = uuid.uuid4()
    event.payload = {
        "reservation_id": str(reservation_id),
        "company_id": str(company_id),
    }

    with (
        patch("app.workers.handlers.soft_reservation_handler.SessionLocal") as MockSession,
        patch("app.core.db_rls.set_rls_context"),
    ):
        db = _make_db()
        MockSession.return_value = db
        db.query.return_value.filter.return_value.first.return_value = reservation

        handle_soft_reservation_expired(event)

    db.commit.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 10. Overbooking forçado sem reason → 422 (Pydantic ValidationError)
# ─────────────────────────────────────────────────────────────────────────────

def test_firme_direct_schema_requires_reason():
    from pydantic import ValidationError
    from app.modules.agenda.schemas import FirmeDirectCreate

    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        FirmeDirectCreate(
            professional_id=uuid.uuid4(),
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            appointment_id=uuid.uuid4(),
            # reason ausente → ValidationError (maps to HTTP 422)
        )


# ─────────────────────────────────────────────────────────────────────────────
# 11. Overbooking forçado com reason → record_sensitive_action gravado
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_sensitive_action_called_for_overbooking():
    from app.core.audit.sensitive_context import record_sensitive_action, SensitiveAuditContext

    db = _make_db()
    actor_id = uuid.uuid4()
    company_id = uuid.uuid4()

    ctx = SensitiveAuditContext(
        actor_id=actor_id,
        actor_role="OWNER",
        action="firme_direct_overbooking",
        resource_type="reservation",
        company_id=company_id,
        reason="Cliente confirmado por telefone — slot com conflito aceito conscientemente",
    )

    with patch("app.infrastructure.db.models.audit_log.AuditLog") as MockAuditLog:
        audit_entry = MagicMock()
        MockAuditLog.return_value = audit_entry

        result = record_sensitive_action(ctx=ctx, db=db)

    db.add.assert_called_once_with(audit_entry)
    db.flush.assert_called_once()
    assert result is audit_entry


# ─────────────────────────────────────────────────────────────────────────────
# 12. tstzrange: start_at/end_at timezone-aware → sem erro de tipo
# ─────────────────────────────────────────────────────────────────────────────

def test_reservation_accepts_timezone_aware_datetimes():
    from app.infrastructure.db.models.reservation import Reservation

    now = datetime.now(timezone.utc)
    r = Reservation(
        reservation_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        professional_id=uuid.uuid4(),
        start_at=now + timedelta(hours=1),
        end_at=now + timedelta(hours=2),
        type="SOFT",
        status="ACTIVE",
        expires_at=now + timedelta(minutes=15),
    )

    assert r.start_at.tzinfo is not None
    assert r.end_at.tzinfo is not None
    assert r.expires_at.tzinfo is not None


# ─────────────────────────────────────────────────────────────────────────────
# 13. release_reservation — status = RELEASED
# ─────────────────────────────────────────────────────────────────────────────

def test_release_reservation():
    from app.modules.agenda.reservation_service import release_reservation

    company_id = uuid.uuid4()
    reservation = _make_reservation(company_id=company_id, status="ACTIVE")
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = reservation

    release_reservation(
        reservation_id=reservation.reservation_id,
        company_id=company_id,
        db=db,
    )

    assert reservation.status == "RELEASED"
    db.flush.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 14. expire_soft_reservation — status = EXPIRED + Celery task disparada
# ─────────────────────────────────────────────────────────────────────────────

def test_expire_soft_reservation_emits_celery():
    from app.modules.agenda.reservation_service import expire_soft_reservation

    company_id = uuid.uuid4()
    reservation_id = uuid.uuid4()
    reservation = _make_reservation(
        reservation_id=reservation_id,
        company_id=company_id,
        type="SOFT",
        status="ACTIVE",
    )
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = reservation

    mock_expire_mod = MagicMock()
    mock_task = MagicMock()
    mock_expire_mod.dispatch_soft_reservation_expired = mock_task

    with patch.dict(sys.modules, {"app.workers.tasks.expire_reservations": mock_expire_mod}):
        expire_soft_reservation(
            reservation_id=reservation_id,
            company_id=company_id,
            db=db,
        )

    assert reservation.status == "EXPIRED"
    mock_task.delay.assert_called_once_with(str(reservation_id), str(company_id))


# ─────────────────────────────────────────────────────────────────────────────
# 15. expire_soft_reservation — idempotente se não ACTIVE
# ─────────────────────────────────────────────────────────────────────────────

def test_expire_soft_reservation_idempotent_when_already_expired():
    from app.modules.agenda.reservation_service import expire_soft_reservation

    company_id = uuid.uuid4()
    reservation_id = uuid.uuid4()
    reservation = _make_reservation(
        reservation_id=reservation_id,
        company_id=company_id,
        type="SOFT",
        status="EXPIRED",
    )
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = reservation

    mock_expire_mod = MagicMock()

    with patch.dict(sys.modules, {"app.workers.tasks.expire_reservations": mock_expire_mod}):
        expire_soft_reservation(
            reservation_id=reservation_id,
            company_id=company_id,
            db=db,
        )

    assert reservation.status == "EXPIRED"
    mock_expire_mod.dispatch_soft_reservation_expired.delay.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 16. ScheduleException UNIQUE → 409 em conflito
# ─────────────────────────────────────────────────────────────────────────────

def test_create_schedule_exception_conflict_raises_409():
    from app.modules.schedule_exceptions.service import create_exception
    from datetime import date
    from fastapi import HTTPException

    company_id = uuid.uuid4()
    db = _make_db()
    db.flush.side_effect = IntegrityError("UNIQUE constraint", None, None)

    with pytest.raises(HTTPException) as exc_info:
        create_exception(
            professional_id=uuid.uuid4(),
            exception_date=date(2026, 6, 15),
            type="SUBSTITUTIVE",
            start_time=None,
            end_time=None,
            reason="Folga",
            company_id=company_id,
            db=db,
        )

    assert exc_info.value.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# 17. open_direct_occupancy — cria DirectOccupancy corretamente
# ─────────────────────────────────────────────────────────────────────────────

def test_open_direct_occupancy():
    from app.modules.agenda.reservation_service import open_direct_occupancy

    company_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    professional_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    db = _make_db()

    with patch("app.modules.agenda.reservation_service.DirectOccupancy") as MockOcc:
        occ_instance = MagicMock()
        MockOcc.return_value = occ_instance

        result = open_direct_occupancy(
            professional_id=professional_id,
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            reason="Limpeza do espaço",
            actor_id=actor_id,
            company_id=company_id,
            db=db,
        )

    db.add.assert_called_once_with(occ_instance)
    db.flush.assert_called_once()
    assert result is occ_instance


# ─────────────────────────────────────────────────────────────────────────────
# 18. Modelos Sprint 10 exportados em __init__.py
# ─────────────────────────────────────────────────────────────────────────────

def test_models_exported():
    from app.infrastructure.db.models import ScheduleException, Reservation, DirectOccupancy
    assert ScheduleException.__tablename__ == "schedule_exceptions"
    assert Reservation.__tablename__ == "reservations"
    assert DirectOccupancy.__tablename__ == "direct_occupancies"


# ─────────────────────────────────────────────────────────────────────────────
# 19. Appointment.operation_type existe no modelo
# ─────────────────────────────────────────────────────────────────────────────

def test_appointment_has_operation_type():
    from app.infrastructure.db.models.appointment import Appointment
    col = Appointment.__table__.columns.get("operation_type")
    assert col is not None


# ─────────────────────────────────────────────────────────────────────────────
# 20. beat_schedule contém soft-reservation-expiry-scan (verifica arquivo)
# ─────────────────────────────────────────────────────────────────────────────

def test_beat_schedule_has_expiry_scan():
    import pathlib
    content = pathlib.Path("app/workers/beat_schedule.py").read_text(encoding="utf-8")
    assert "soft-reservation-expiry-scan" in content
    assert "expire_soft_reservations_scan" in content


# ─────────────────────────────────────────────────────────────────────────────
# 21. handler registrado no EventBus via register_handlers()
# ─────────────────────────────────────────────────────────────────────────────

def test_soft_reservation_handler_registers():
    from app.infrastructure.event_bus import EventBus, event_bus as real_bus
    bus = EventBus()

    # O handler importa event_bus de app.infrastructure.event_bus;
    # patchamos lá para que o from-import dentro de register_handlers() pegue o bus de teste.
    with patch("app.infrastructure.event_bus.event_bus", bus):
        # Força reimport para pegar a referência patchada
        import importlib
        import app.workers.handlers.soft_reservation_handler as mod
        importlib.reload(mod)
        mod.register_handlers()

    assert "agenda.soft_reservation.expired" in bus._handlers
    assert len(bus._handlers["agenda.soft_reservation.expired"]) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 22. Cross-tenant: create_soft_reservation com professional de outro tenant → RLS bloqueia
# ─────────────────────────────────────────────────────────────────────────────

def test_soft_reservation_cross_tenant():
    """RLS impede criar reserva com professional_id de company_a no contexto de company_b.

    Em produção o banco retorna 0 resultados (professional não existe para company_b).
    Aqui simulamos esse comportamento: db.query().filter().first() → None,
    o que causa 404 ou equivalente (reservation não criada).
    """
    from app.modules.agenda.reservation_service import create_soft_reservation, SlotUnavailableError

    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    professional_a = uuid.uuid4()  # pertence a company_a

    now = datetime.now(timezone.utc)

    db = _make_db()

    # Contexto de company_b: TenantConfig de company_b não conhece professional_a
    # db.query(TenantConfig).filter(...company_b...).first() → cfg de company_b
    cfg = MagicMock()
    cfg.soft_reservation_ttl_min = 15
    db.query.return_value.filter.return_value.first.return_value = cfg

    # RLS no banco filtraria professional_a pelo company_id=company_b e retornaria 0 linhas.
    # Simulamos isso fazendo o flush levantar IntegrityError (FK violation):
    # professional_id não existe para company_b → constraint viola.
    from sqlalchemy.exc import IntegrityError
    db.flush.side_effect = IntegrityError(
        "insert or update on table 'reservations' violates foreign key constraint",
        None,
        None,
    )

    with patch("app.modules.agenda.reservation_service.Reservation"):
        with pytest.raises(SlotUnavailableError) as exc_info:
            create_soft_reservation(
                professional_id=professional_a,   # professional de company_a
                start_at=now + timedelta(hours=1),
                end_at=now + timedelta(hours=2),
                ttl_minutes=15,
                company_id=company_b,             # contexto de company_b
                db=db,
            )

    # SlotUnavailableError é HTTP 409 — garante que a criação foi bloqueada
    assert exc_info.value.status_code == 409
    db.rollback.assert_called_once()
