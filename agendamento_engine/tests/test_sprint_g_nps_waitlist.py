"""
Testes Sprint G — NPS + Fila de espera.

Usa FakeDB in-memory (padrão do projeto) — sem PostgreSQL real.

Casos obrigatórios — NPS:
  1.  Survey agendada apenas após operation.completed
      (operation.confirmed → handler não dispara)
  2.  Intervalo mínimo: pesquisa há 20 dias (min=30d) → skip
  3.  Survey SENT expira após 48h sem resposta
  4.  Score <= threshold → nps.low_score_alert publicado
  5.  Score > threshold → sem alerta
  6.  Resposta pública: survey EXPIRED → 422
  7.  Resposta pública: survey já RESPONDED → 422

Casos obrigatórios — Fila:
  8.  join com operação ativa equivalente → 422
  9.  join duplicado (mesmo escopo) → 409
  10. Cancelamento → notifica 1º da fila (e APENAS o 1º)
  11. Cliente com operação ativa → pulado na notificação
  12. Notificação por reabastecimento de produto
  13. Entry NOTIFIED expira → próximo notificado
  14. Cross-tenant: fila de empresa A invisível para B
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.infrastructure.db.models import (
    Appointment, Customer, NpsConfig, NpsSurvey, User,
    WaitlistConfig, WaitlistEntry,
)
from app.infrastructure.event_bus import DomainEvent, EventBus, event_bus
from app.modules.nps import service as nps_service
from app.modules.waitlist import service as waitlist_service


def _now():
    return datetime.now(timezone.utc)


# ─── FakeDB ───────────────────────────────────────────────────────────────────

class FakeDB:
    """Roteia query(Model) para filas configuráveis de first()/all()."""

    def __init__(self, first=None, all_=None):
        self._first = {k: list(v) for k, v in (first or {}).items()}
        self._all = dict(all_ or {})
        self.added = []
        self.commits = 0

    def query(self, model, *rest):
        db = self

        class Q:
            def filter(self, *a, **k): return self
            def join(self, *a, **k): return self
            def order_by(self, *a, **k): return self
            def limit(self, n): return self

            def first(self_q):
                queue = db._first.get(model)
                return queue.pop(0) if queue else None

            def all(self_q):
                return db._all.get(model, [])

        return Q()

    def add(self, obj): self.added.append(obj)
    def commit(self): self.commits += 1
    def refresh(self, obj): pass
    def rollback(self): pass
    def close(self): pass


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def events(monkeypatch):
    """Captura eventos publicados no EventBus global (singleton)."""
    recorded = []
    monkeypatch.setattr(event_bus, "publish", lambda e: recorded.append(e))
    return recorded


@pytest.fixture
def dispatch(monkeypatch):
    """Substitui CommunicationService.dispatch — registra chamadas, status configurável."""
    from app.modules.communication.service import communication_service

    state = SimpleNamespace(calls=[], statuses=[])

    def fake_dispatch(**kwargs):
        state.calls.append(kwargs)
        status = state.statuses.pop(0) if state.statuses else "SENT"
        return SimpleNamespace(status=status, log_id=uuid.uuid4())

    monkeypatch.setattr(communication_service, "dispatch", fake_dispatch)
    return state


def _nps_config(**over):
    base = dict(
        enabled=True, channel="WHATSAPP", delay_minutes=30,
        min_interval_days=30, low_score_threshold=6,
        low_score_alert_enabled=True,
    )
    base.update(over)
    return SimpleNamespace(company_id=uuid.uuid4(), **base)


def _waitlist_config(**over):
    base = dict(enabled=True, priority_mode="FIFO", notification_window_hours=2)
    base.update(over)
    return SimpleNamespace(company_id=uuid.uuid4(), **base)


def _survey(status="SENT", **over):
    base = dict(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        appointment_id=uuid.uuid4(),
        status=status,
        scheduled_for=_now(),
        sent_at=None,
        responded_at=None,
        expires_at=_now() + timedelta(hours=48),
        communication_log_id=None,
        created_at=_now(),
    )
    base.update(over)
    return SimpleNamespace(**base)


def _customer(**over):
    base = dict(id=uuid.uuid4(), name="Cliente Teste", phone="5511999990000")
    base.update(over)
    return SimpleNamespace(**base)


def _entry(scope_type="SERVICE", status="WAITING", **over):
    base = dict(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        scope_type=scope_type,
        service_id=uuid.uuid4() if scope_type == "SERVICE" else None,
        professional_id=uuid.uuid4() if scope_type == "PROFESSIONAL" else None,
        product_id=uuid.uuid4() if scope_type == "PRODUCT" else None,
        status=status,
        priority=0,
        source_channel="PAINEL",
        notified_at=None,
        expires_at=None,
        created_at=_now(),
    )
    base.update(over)
    return SimpleNamespace(**base)


def _event(event_type, payload=None, company_id=None):
    return DomainEvent(
        event_id=uuid.uuid4(),
        event_type=event_type,
        occurred_at=_now(),
        company_id=company_id or uuid.uuid4(),
        idempotency_key=f"{event_type}:{uuid.uuid4()}",
        actor={"type": "SYSTEM", "id": None},
        payload=payload or {},
    )


# ─── NPS ──────────────────────────────────────────────────────────────────────

class TestNpsTrigger:
    def test_handler_registrado_apenas_em_operation_completed(self, monkeypatch):
        """Sprint G DoD: NPS dispara APENAS após operation.completed."""
        from app.workers.handlers import nps_handler

        fresh_bus = EventBus()
        monkeypatch.setattr(nps_handler, "event_bus", fresh_bus)
        nps_handler.register_handlers()
        assert set(fresh_bus._handlers.keys()) == {"operation.completed"}

    def test_operation_confirmed_nao_dispara_handler(self, monkeypatch):
        """Evento que não é operation.completed → handler nunca é chamado."""
        from app.workers.handlers.nps_handler import handle_operation_completed_nps

        called = []
        bus = EventBus()
        bus.register(
            "operation.completed",
            lambda e: called.append(e) or handle_operation_completed_nps(e),
        )
        bus.publish(_event("operation.confirmed", {"appointment_id": str(uuid.uuid4())}))
        assert called == []

    def test_operation_completed_agenda_survey(self, monkeypatch):
        """Caminho positivo: handler chama schedule_nps_survey."""
        from app.workers.handlers import nps_handler

        company_id = uuid.uuid4()
        appointment_id = uuid.uuid4()
        customer_id = uuid.uuid4()

        scheduled = []
        monkeypatch.setattr(nps_handler, "SessionLocal", lambda: FakeDB())
        monkeypatch.setattr(nps_handler, "set_rls_context", lambda db, cid: None)
        monkeypatch.setattr("app.core.idempotency.is_processed", lambda *a, **k: False)
        monkeypatch.setattr("app.core.idempotency.mark_processed", lambda *a, **k: None)
        monkeypatch.setattr(
            nps_service, "schedule_nps_survey",
            lambda db, appointment_id, company_id, customer_id: scheduled.append(
                (appointment_id, company_id, customer_id)
            ),
        )

        nps_handler.handle_operation_completed_nps(_event(
            "operation.completed",
            {
                "appointment_id": str(appointment_id),
                "customer_id": str(customer_id),
                "company_id": str(company_id),
            },
            company_id=company_id,
        ))
        assert scheduled == [(appointment_id, company_id, customer_id)]

    def test_handler_idempotente(self, monkeypatch):
        """Evento já processado (idempotency key) → schedule não é chamado."""
        from app.workers.handlers import nps_handler

        scheduled = []
        monkeypatch.setattr(nps_handler, "SessionLocal", lambda: FakeDB())
        monkeypatch.setattr(nps_handler, "set_rls_context", lambda db, cid: None)
        monkeypatch.setattr("app.core.idempotency.is_processed", lambda *a, **k: True)
        monkeypatch.setattr(
            nps_service, "schedule_nps_survey",
            lambda *a, **k: scheduled.append(1),
        )
        nps_handler.handle_operation_completed_nps(_event(
            "operation.completed",
            {"appointment_id": str(uuid.uuid4()), "customer_id": str(uuid.uuid4())},
        ))
        assert scheduled == []


class TestNpsSchedule:
    def test_agenda_survey_pending_com_delay(self, events):
        config = _nps_config(delay_minutes=45)
        db = FakeDB(first={
            NpsConfig: [config],
            NpsSurvey: [None, None],  # sem survey p/ appointment, sem recente
        })
        before = _now()
        survey = nps_service.schedule_nps_survey(
            db, appointment_id=uuid.uuid4(),
            company_id=uuid.uuid4(), customer_id=uuid.uuid4(),
        )
        assert survey is not None
        assert survey.status == "PENDING"
        delta = survey.scheduled_for - before
        assert timedelta(minutes=44) < delta < timedelta(minutes=46)
        assert any(e.event_type == "nps.survey_scheduled" for e in events)

    def test_config_disabled_skip(self, events):
        db = FakeDB(first={NpsConfig: [_nps_config(enabled=False)]})
        result = nps_service.schedule_nps_survey(
            db, appointment_id=uuid.uuid4(),
            company_id=uuid.uuid4(), customer_id=uuid.uuid4(),
        )
        assert result is None
        assert db.added == []

    def test_intervalo_minimo_respeitado(self, events):
        """Cliente recebeu NPS há 20 dias com min_interval=30d → skip."""
        recent = _survey(created_at=_now() - timedelta(days=20))
        db = FakeDB(first={
            NpsConfig: [_nps_config(min_interval_days=30)],
            NpsSurvey: [None, recent],  # sem survey do appointment; recente existe
        })
        result = nps_service.schedule_nps_survey(
            db, appointment_id=uuid.uuid4(),
            company_id=uuid.uuid4(), customer_id=uuid.uuid4(),
        )
        assert result is None
        assert db.added == []

    def test_survey_existente_para_appointment_skip(self, events):
        """Idempotência: 1 survey por appointment."""
        db = FakeDB(first={
            NpsConfig: [_nps_config()],
            NpsSurvey: [_survey()],
        })
        result = nps_service.schedule_nps_survey(
            db, appointment_id=uuid.uuid4(),
            company_id=uuid.uuid4(), customer_id=uuid.uuid4(),
        )
        assert result is None


class TestNpsSend:
    def test_envia_pendentes_e_marca_sent(self, dispatch, events):
        survey = _survey(status="PENDING", scheduled_for=_now() - timedelta(minutes=5))
        db = FakeDB(
            first={Customer: [_customer()]},
            all_={NpsSurvey: [survey]},
        )
        sent = nps_service.send_pending_surveys(db)
        assert sent == 1
        assert survey.status == "SENT"
        assert survey.sent_at is not None
        assert survey.expires_at == survey.sent_at + timedelta(hours=48)
        assert dispatch.calls[0]["event_type"] == "nps.survey_request"
        assert dispatch.calls[0]["recipient_type"] == "CLIENT"

    def test_consent_revogado_expira_survey(self, dispatch, events):
        dispatch.statuses.append("SKIPPED_CONSENT_REVOKED")
        survey = _survey(status="PENDING", scheduled_for=_now() - timedelta(minutes=5))
        db = FakeDB(
            first={Customer: [_customer()]},
            all_={NpsSurvey: [survey]},
        )
        sent = nps_service.send_pending_surveys(db)
        assert sent == 0
        assert survey.status == "EXPIRED"

    def test_falha_de_envio_mantem_pending(self, dispatch, events):
        dispatch.statuses.append("FAILED")
        survey = _survey(status="PENDING", scheduled_for=_now() - timedelta(minutes=5))
        db = FakeDB(
            first={Customer: [_customer()]},
            all_={NpsSurvey: [survey]},
        )
        sent = nps_service.send_pending_surveys(db)
        assert sent == 0
        assert survey.status == "PENDING"  # retry no próximo scan


class TestNpsExpiry:
    def test_survey_sent_expira_apos_48h(self, events):
        survey = _survey(status="SENT", expires_at=_now() - timedelta(hours=1))
        db = FakeDB(all_={NpsSurvey: [survey]})
        count = nps_service.expire_surveys(db)
        assert count == 1
        assert survey.status == "EXPIRED"
        assert any(e.event_type == "nps.survey_expired" for e in events)


class TestNpsResponse:
    def test_score_baixo_publica_alerta(self, events):
        survey = _survey(status="SENT")
        db = FakeDB(first={
            NpsSurvey: [survey],
            NpsConfig: [_nps_config(low_score_threshold=6)],
            User: [None],  # sem OWNER → notificação direta vira no-op
        })
        response = nps_service.record_response(db, survey.id, score=4, comment="ruim")
        assert response.score == 4
        assert survey.status == "RESPONDED"
        types = [e.event_type for e in events]
        assert "nps.response_received" in types
        assert "nps.low_score_alert" in types

    def test_score_alto_sem_alerta(self, events):
        survey = _survey(status="SENT")
        db = FakeDB(first={
            NpsSurvey: [survey],
            NpsConfig: [_nps_config(low_score_threshold=6)],
        })
        nps_service.record_response(db, survey.id, score=9)
        types = [e.event_type for e in events]
        assert "nps.response_received" in types
        assert "nps.low_score_alert" not in types

    def test_alerta_desabilitado_nao_publica(self, events):
        survey = _survey(status="SENT")
        db = FakeDB(first={
            NpsSurvey: [survey],
            NpsConfig: [_nps_config(low_score_alert_enabled=False)],
        })
        nps_service.record_response(db, survey.id, score=2)
        assert "nps.low_score_alert" not in [e.event_type for e in events]

    def test_survey_expirada_422(self, events):
        db = FakeDB(first={NpsSurvey: [_survey(status="EXPIRED")]})
        with pytest.raises(HTTPException) as exc:
            nps_service.record_response(db, uuid.uuid4(), score=8)
        assert exc.value.status_code == 422

    def test_survey_ja_respondida_422(self, events):
        db = FakeDB(first={NpsSurvey: [_survey(status="RESPONDED")]})
        with pytest.raises(HTTPException) as exc:
            nps_service.record_response(db, uuid.uuid4(), score=8)
        assert exc.value.status_code == 422

    def test_survey_inexistente_404(self, events):
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            nps_service.record_response(db, uuid.uuid4(), score=8)
        assert exc.value.status_code == 404

    def test_tenant_response_exige_resposta_do_cliente(self, events):
        from app.infrastructure.db.models import NpsResponse as NpsResponseModel
        db = FakeDB(first={
            NpsSurvey: [_survey(status="SENT")],
            NpsResponseModel: [None],
        })
        with pytest.raises(HTTPException) as exc:
            nps_service.add_tenant_response(
                db, uuid.uuid4(), "obrigado",
                actor_id=uuid.uuid4(), company_id=uuid.uuid4(),
            )
        assert exc.value.status_code == 422


# ─── Fila de espera ───────────────────────────────────────────────────────────

class TestWaitlistJoin:
    def test_join_cria_entry_waiting(self, events):
        db = FakeDB(first={
            WaitlistConfig: [_waitlist_config()],
            WaitlistEntry: [None],     # sem duplicata
            Appointment: [None],       # sem operação ativa
        })
        entry = waitlist_service.join_waitlist(
            db, company_id=uuid.uuid4(), customer_id=uuid.uuid4(),
            scope_type="SERVICE", service_id=uuid.uuid4(),
        )
        assert entry.status == "WAITING"
        assert any(e.event_type == "waitlist.entry_created" for e in events)

    def test_join_duplicado_409(self, events):
        db = FakeDB(first={
            WaitlistConfig: [_waitlist_config()],
            WaitlistEntry: [_entry()],  # duplicata WAITING
        })
        with pytest.raises(HTTPException) as exc:
            waitlist_service.join_waitlist(
                db, company_id=uuid.uuid4(), customer_id=uuid.uuid4(),
                scope_type="SERVICE", service_id=uuid.uuid4(),
            )
        assert exc.value.status_code == 409

    def test_join_com_operacao_ativa_equivalente_422(self, events):
        active_appointment = SimpleNamespace(id=uuid.uuid4(), status="SCHEDULED")
        db = FakeDB(first={
            WaitlistConfig: [_waitlist_config()],
            WaitlistEntry: [None],
            Appointment: [active_appointment],
        })
        with pytest.raises(HTTPException) as exc:
            waitlist_service.join_waitlist(
                db, company_id=uuid.uuid4(), customer_id=uuid.uuid4(),
                scope_type="SERVICE", service_id=uuid.uuid4(),
            )
        assert exc.value.status_code == 422
        assert "equivalente" in exc.value.detail

    def test_join_escopo_invalido_422(self, events):
        db = FakeDB(first={WaitlistConfig: [_waitlist_config()]})
        with pytest.raises(HTTPException) as exc:
            waitlist_service.join_waitlist(
                db, company_id=uuid.uuid4(), customer_id=uuid.uuid4(),
                scope_type="SERVICE",  # sem service_id
            )
        assert exc.value.status_code == 422

    def test_join_fila_desabilitada_422(self, events):
        db = FakeDB(first={WaitlistConfig: [_waitlist_config(enabled=False)]})
        with pytest.raises(HTTPException) as exc:
            waitlist_service.join_waitlist(
                db, company_id=uuid.uuid4(), customer_id=uuid.uuid4(),
                scope_type="SERVICE", service_id=uuid.uuid4(),
            )
        assert exc.value.status_code == 422


class TestWaitlistNotify:
    def test_notifica_apenas_primeiro_da_fila(self, dispatch, events):
        company_id = uuid.uuid4()
        service_id = uuid.uuid4()
        e1 = _entry(company_id=company_id, service_id=service_id)
        e2 = _entry(company_id=company_id, service_id=service_id)
        db = FakeDB(
            first={
                WaitlistConfig: [_waitlist_config()],
                Appointment: [None, None],
                Customer: [_customer(), _customer()],
            },
            all_={WaitlistEntry: [e1, e2]},
        )
        notified = waitlist_service.notify_waitlist(
            db, company_id, "SERVICE", service_id=service_id,
        )
        assert notified is e1
        assert e1.status == "NOTIFIED"
        assert e1.expires_at == e1.notified_at + timedelta(hours=2)
        assert e2.status == "WAITING"        # apenas 1 candidato por slot
        assert len(dispatch.calls) == 1
        assert dispatch.calls[0]["event_type"] == "waitlist.slot_available"

    def test_cliente_com_operacao_ativa_e_pulado(self, dispatch, events):
        company_id = uuid.uuid4()
        service_id = uuid.uuid4()
        e1 = _entry(company_id=company_id, service_id=service_id)
        e2 = _entry(company_id=company_id, service_id=service_id)
        active = SimpleNamespace(id=uuid.uuid4(), status="SCHEDULED")
        db = FakeDB(
            first={
                WaitlistConfig: [_waitlist_config()],
                Appointment: [active, None],  # e1 tem operação ativa; e2 não
                Customer: [_customer()],
            },
            all_={WaitlistEntry: [e1, e2]},
        )
        notified = waitlist_service.notify_waitlist(
            db, company_id, "SERVICE", service_id=service_id,
        )
        assert notified is e2
        assert e1.status == "WAITING"   # pulado, segue na fila
        assert e2.status == "NOTIFIED"

    def test_consent_revogado_passa_ao_proximo(self, dispatch, events):
        dispatch.statuses.append("SKIPPED_CONSENT_REVOKED")
        company_id = uuid.uuid4()
        service_id = uuid.uuid4()
        e1 = _entry(company_id=company_id, service_id=service_id)
        e2 = _entry(company_id=company_id, service_id=service_id)
        db = FakeDB(
            first={
                WaitlistConfig: [_waitlist_config()],
                Appointment: [None, None],
                Customer: [_customer(), _customer()],
            },
            all_={WaitlistEntry: [e1, e2]},
        )
        notified = waitlist_service.notify_waitlist(
            db, company_id, "SERVICE", service_id=service_id,
        )
        assert notified is e2
        assert e1.status == "WAITING"

    def test_fila_desabilitada_nao_notifica(self, dispatch, events):
        db = FakeDB(first={WaitlistConfig: [_waitlist_config(enabled=False)]})
        result = waitlist_service.notify_waitlist(
            db, uuid.uuid4(), "SERVICE", service_id=uuid.uuid4(),
        )
        assert result is None
        assert dispatch.calls == []


class TestWaitlistHandlers:
    def test_cancelamento_notifica_fila(self, monkeypatch):
        from app.workers.handlers import waitlist_handler

        calls = []
        monkeypatch.setattr(waitlist_handler, "SessionLocal", lambda: FakeDB())
        monkeypatch.setattr(waitlist_handler, "set_rls_context", lambda db, cid: None)
        monkeypatch.setattr(
            waitlist_service, "notify_waitlist",
            lambda db, company_id, scope_type, **kw: calls.append((scope_type, kw)),
        )

        company_id = uuid.uuid4()
        service_id = uuid.uuid4()
        professional_id = uuid.uuid4()
        waitlist_handler.handle_appointment_cancelled_waitlist(_event(
            "appointment.cancelled",
            {
                "appointment_id": str(uuid.uuid4()),
                "professional_id": str(professional_id),
                "service_ids": [str(service_id)],
            },
            company_id=company_id,
        ))
        scopes = [c[0] for c in calls]
        assert "SERVICE" in scopes
        assert "PROFESSIONAL" in scopes

    def test_reabastecimento_notifica_fila_de_produto(self, monkeypatch):
        from app.workers.handlers import waitlist_handler

        calls = []
        monkeypatch.setattr(waitlist_handler, "SessionLocal", lambda: FakeDB())
        monkeypatch.setattr(waitlist_handler, "set_rls_context", lambda db, cid: None)
        monkeypatch.setattr(
            waitlist_service, "notify_waitlist",
            lambda db, company_id, scope_type, **kw: calls.append((scope_type, kw)),
        )

        product_id = uuid.uuid4()
        waitlist_handler.handle_stock_entry_recorded_waitlist(_event(
            "stock.entry_recorded",
            {"product_ids": [str(product_id)]},
        ))
        assert len(calls) == 1
        assert calls[0][0] == "PRODUCT"
        assert calls[0][1]["product_id"] == product_id

    def test_handlers_registrados_nos_eventos_corretos(self, monkeypatch):
        from app.workers.handlers import waitlist_handler

        fresh_bus = EventBus()
        monkeypatch.setattr(waitlist_handler, "event_bus", fresh_bus)
        waitlist_handler.register_handlers()
        assert set(fresh_bus._handlers.keys()) == {
            "appointment.cancelled",
            "appointment.rescheduled",
            "stock.entry_recorded",
        }


class TestWaitlistExpiry:
    def test_entry_notified_expira_e_proximo_e_notificado(self, monkeypatch, events):
        stale = _entry(status="NOTIFIED", expires_at=_now() - timedelta(hours=1))
        db = FakeDB(all_={WaitlistEntry: [stale]})

        next_calls = []
        monkeypatch.setattr(
            waitlist_service, "notify_waitlist",
            lambda db, company_id, scope_type, **kw: next_calls.append(kw),
        )
        count = waitlist_service.expire_waitlist_entries(db)
        assert count == 1
        assert stale.status == "EXPIRED"
        assert len(next_calls) == 1
        assert next_calls[0]["reason"] == "previous_entry_expired"
        assert any(e.event_type == "waitlist.entry_expired" for e in events)


class TestWaitlistCrossTenant:
    def test_cancel_entry_de_outra_empresa_404(self, events):
        # FakeDB sem entry para o company_id consultado → 404 (filtro company_id)
        db = FakeDB(first={WaitlistEntry: [None]})
        with pytest.raises(HTTPException) as exc:
            waitlist_service.cancel_entry(db, uuid.uuid4(), uuid.uuid4())
        assert exc.value.status_code == 404


# ─── Payloads novos (Sprint G) ────────────────────────────────────────────────

class TestEventPayloads:
    def test_operation_completed_inclui_customer_id(self, monkeypatch):
        """transitions._publish_operation_completed agora carrega customer_id."""
        import app.infrastructure.event_bus as bus_module
        from app.modules.appointments.transitions import _publish_operation_completed

        recorded = []
        fresh_bus = EventBus()
        fresh_bus.publish = lambda e: recorded.append(e)
        monkeypatch.setattr(bus_module, "event_bus", fresh_bus)

        client_id = uuid.uuid4()
        appointment = SimpleNamespace(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            professional_id=uuid.uuid4(),
            client_id=client_id,
            services=[],
        )
        _publish_operation_completed(appointment)
        assert len(recorded) == 1
        assert recorded[0].payload["customer_id"] == str(client_id)

    def test_slot_released_payload(self, monkeypatch):
        import app.infrastructure.event_bus as bus_module
        from app.modules.appointments.service import _publish_slot_released

        recorded = []
        fresh_bus = EventBus()
        fresh_bus.publish = lambda e: recorded.append(e)
        monkeypatch.setattr(bus_module, "event_bus", fresh_bus)

        service_id = uuid.uuid4()
        appointment = SimpleNamespace(
            id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            professional_id=uuid.uuid4(),
            client_id=uuid.uuid4(),
            version=2,
            services=[SimpleNamespace(service_id=service_id)],
        )
        _publish_slot_released(appointment, "appointment.cancelled")
        assert len(recorded) == 1
        event = recorded[0]
        assert event.event_type == "appointment.cancelled"
        assert event.payload["service_ids"] == [str(service_id)]
        assert event.payload["professional_id"] == str(appointment.professional_id)
