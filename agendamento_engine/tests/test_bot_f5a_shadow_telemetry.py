"""Testes Bot F5a — shadow mode + volante de telemetria de intenção.

Cobertura:
  - Shadow gate: resultado LLM confidence >= 0.7 NÃO roteia em modo shadow
    (persiste + devolve False); em modo live roteia; REGEX roteia sempre.
  - routing_decision gravado na classificação (ROUTED | MENU_FALLBACK |
    SHADOW_NOT_ROUTED | INACTIVE_MODULE_MSG).
  - Write-back 3a: clique de menu pós-fallback registra
    MENU_CLICK_AFTER_FALLBACK com a opção clicada.
  - Write-back 3b: confirmação/cancelamento de fluxo registra
    FLOW_CONFIRMED/FLOW_CANCELLED vinculado à classificação que o iniciou;
    intenção que não casa com o ponto de materialização não é consumida.
  - Correlação: marker no session.context (não por session_id); janela
    temporal descarta marker velho SEM gravar; supersessão → ABANDONED.
  - ChainClassifier persiste fsm_state e devolve classification_id.
  - _CLASSIFY_TOOL: sub-schema fechado de entities (servico/dia/hora/profissional).

Estratégia: FakeDB in-memory + StubClassifier (padrão test_sprint26).
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.infrastructure.db.models.intent_classification import (
    IntentClassification,
    IntentOutcome,
)
from app.modules.whatsapp import bot_service
from app.modules.whatsapp import sender
from app.modules.whatsapp.handlers import cancelando as h_cancelando
from app.modules.whatsapp.handlers import confirmando as h_confirmando
from app.modules.whatsapp.intent import telemetry
from app.modules.whatsapp.intent.classifier import ChainClassifier
from app.modules.whatsapp.intent.llm_classifier import _CLASSIFY_TOOL, NullLLMClassifier
from app.modules.whatsapp.intent.regex_classifier import RegexClassifier
from app.modules.whatsapp.intent.schemas import FALLBACK_INTENT, IntentResult


# ─── Fakes (padrão test_sprint26) ─────────────────────────────────────────────

class FakeDB:
    def __init__(self, results=None):
        self._results = dict(results or {})
        self.added = []
        self.commits = 0

    def query(self, model, *rest):
        db = self

        class Q:
            def filter(self, *a, **k): return self
            def order_by(self, *a, **k): return self
            def all(self_q): return db._results.get(model, [])
            def first(self_q):
                rows = db._results.get(model, [])
                return rows[0] if rows else None

        return Q()

    def add(self, obj): self.added.append(obj)
    def flush(self): pass
    def commit(self): self.commits += 1
    def refresh(self, obj): pass


def fake_session(state="MENU_PRINCIPAL", **ctx):
    base = {"customer_id": str(uuid.uuid4()), "customer_name": "Maria"}
    base.update(ctx)
    return SimpleNamespace(id=uuid.uuid4(), state=state, context=base)


class StubClassifier:
    """IntentResult fixo COM classification_id (simula linha persistida)."""

    def __init__(self, intent, confidence, source="REGEX", classification_id=None):
        self._intent = intent
        self._confidence = confidence
        self._source = source
        self.classification_id = classification_id or uuid.uuid4()

    def classify(self, company_id, text, session_id=None, module_activations=None,
                 fsm_state=None):
        return IntentResult(
            intent=self._intent, confidence=self._confidence,
            source=self._source, raw_input=text,
            classification_id=self.classification_id,
        )


@pytest.fixture
def captured(monkeypatch):
    sent = []
    monkeypatch.setattr(sender, "send_text",
                        lambda inst, to, text: sent.append(("text", text)))
    monkeypatch.setattr(sender, "send_buttons",
                        lambda inst, to, text, buttons: sent.append(("buttons", text)))
    monkeypatch.setattr(sender, "send_list",
                        lambda inst, to, title, desc, rows, *a, **k: sent.append(("list", title)))
    return sent


def _route(session, db, text, classifier):
    return bot_service._classify_and_route(
        db, session, uuid.uuid4(), "inst", "5511999@s.whatsapp.net",
        text, "Barbearia", classifier=classifier,
    )


def _marker(session):
    return (session.context or {}).get(telemetry.MARKER_KEY)


def _fresh_marker(intent="AGENDAR", routed=True, cid=None, minutes_ago=0):
    at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {
        "cid": str(cid or uuid.uuid4()),
        "intent": intent,
        "routed": routed,
        "at": at.isoformat(),
    }


def _outcomes(db):
    return [o for o in db.added if isinstance(o, IntentOutcome)]


# ─── Shadow gate ──────────────────────────────────────────────────────────────

def test_shadow_llm_high_confidence_does_not_route(captured, monkeypatch):
    monkeypatch.setattr(bot_service.settings, "LLM_MODE", "shadow")
    stub = StubClassifier("AGENDAR", 0.95, source="LLM")
    record = SimpleNamespace(id=stub.classification_id, routing_decision=None)
    db = FakeDB({IntentClassification: [record]})
    session = fake_session(state="MENU_PRINCIPAL")

    routed = _route(session, db, "quero marcar pra sexta de tarde", stub)

    assert routed is False                      # chamador exibe o menu, como hoje
    assert session.state == "MENU_PRINCIPAL"    # FSM intocado
    assert captured == []                       # gate não envia nada ao usuário
    assert record.routing_decision == telemetry.ROUTING_SHADOW
    marker = _marker(session)
    assert marker is not None and marker["routed"] is False
    assert marker["intent"] == "AGENDAR"        # sugestão preservada p/ ground truth


def test_live_mode_llm_routes(captured, monkeypatch):
    monkeypatch.setattr(bot_service.settings, "LLM_MODE", "live")
    calls = []
    monkeypatch.setattr(bot_service, "_start_escolhendo_servico",
                        lambda *a, **k: calls.append("servico"))
    stub = StubClassifier("AGENDAR", 0.95, source="LLM")
    record = SimpleNamespace(id=stub.classification_id, routing_decision=None)
    db = FakeDB({IntentClassification: [record]})
    session = fake_session(state="INICIO")

    routed = _route(session, db, "quero marcar um corte", stub)

    assert routed is True
    assert session.state == bot_service.STATE_ESCOLHENDO_SERVICO
    assert calls == ["servico"]
    assert record.routing_decision == telemetry.ROUTING_ROUTED
    assert _marker(session)["routed"] is True


def test_regex_routes_normally_in_shadow(captured, monkeypatch):
    # O shadow gate contém APENAS a LLM — regex é o comportamento atual.
    monkeypatch.setattr(bot_service.settings, "LLM_MODE", "shadow")
    calls = []
    monkeypatch.setattr(bot_service, "_start_escolhendo_servico",
                        lambda *a, **k: calls.append("servico"))
    stub = StubClassifier("AGENDAR", 0.9, source="REGEX")
    db = FakeDB()
    session = fake_session(state="MENU_PRINCIPAL")

    routed = _route(session, db, "agendar", stub)

    assert routed is True
    assert session.state == bot_service.STATE_ESCOLHENDO_SERVICO
    assert calls == ["servico"]


def test_fallback_marks_menu_decision(captured, monkeypatch):
    monkeypatch.setattr(bot_service.settings, "LLM_MODE", "shadow")
    stub = StubClassifier(FALLBACK_INTENT, 0.0, source="FALLBACK")
    record = SimpleNamespace(id=stub.classification_id, routing_decision=None)
    db = FakeDB({IntentClassification: [record]})
    session = fake_session(state="MENU_PRINCIPAL")

    routed = _route(session, db, "oi, tudo bem?", stub)

    assert routed is False
    assert record.routing_decision == telemetry.ROUTING_MENU
    assert _marker(session)["routed"] is False


# ─── Write-back 3a: clique de menu pós-fallback ───────────────────────────────

def test_menu_click_after_fallback_records_outcome():
    db = FakeDB()
    cid = uuid.uuid4()
    company_id = uuid.uuid4()
    session = fake_session(**{
        telemetry.MARKER_KEY: _fresh_marker("AGENDAR", routed=False, cid=cid),
    })

    telemetry.consume_menu_click(db, session, company_id, "opt_ver_agendamentos")

    rows = _outcomes(db)
    assert len(rows) == 1
    assert rows[0].outcome == telemetry.OUTCOME_MENU_CLICK_AFTER_FALLBACK
    assert rows[0].classification_id == cid
    assert rows[0].company_id == company_id
    # ground truth: LLM sugeriu AGENDAR, usuário clicou ver_agendamentos
    assert rows[0].outcome_detail == {
        "menu_option": "opt_ver_agendamentos", "suggested_intent": "AGENDAR",
    }
    assert _marker(session) is None   # marker consumido


def test_menu_click_ignores_routed_marker():
    # Marker de fluxo roteado não é ground truth de menu — fica intacto.
    db = FakeDB()
    session = fake_session(**{telemetry.MARKER_KEY: _fresh_marker(routed=True)})

    telemetry.consume_menu_click(db, session, uuid.uuid4(), "opt_agendar")

    assert _outcomes(db) == []
    assert _marker(session) is not None


def test_stale_marker_discarded_without_recording():
    # Janela temporal: telemetria ambígua NÃO é gravada (fica PENDING).
    db = FakeDB()
    session = fake_session(**{
        telemetry.MARKER_KEY: _fresh_marker(
            routed=False, minutes_ago=telemetry.CORRELATION_WINDOW_MINUTES + 1,
        ),
    })

    telemetry.consume_menu_click(db, session, uuid.uuid4(), "opt_agendar")

    assert _outcomes(db) == []
    assert _marker(session) is None   # descartado, não reaproveitado


# ─── Write-back 3b: desfecho de fluxo ─────────────────────────────────────────

def test_flow_confirmed_consumes_matching_marker():
    db = FakeDB()
    cid = uuid.uuid4()
    session = fake_session(**{
        telemetry.MARKER_KEY: _fresh_marker("AGENDAR", routed=True, cid=cid),
    })

    telemetry.record_flow_outcome(
        db, session, uuid.uuid4(), {"AGENDAR"},
        telemetry.OUTCOME_FLOW_CONFIRMED, {"appointment_id": "abc"},
    )

    rows = _outcomes(db)
    assert len(rows) == 1
    assert rows[0].outcome == telemetry.OUTCOME_FLOW_CONFIRMED
    assert rows[0].classification_id == cid
    assert _marker(session) is None


def test_flow_outcome_intent_mismatch_not_consumed():
    # Fluxo materializado != intenção classificada → não adivinhar.
    db = FakeDB()
    session = fake_session(**{
        telemetry.MARKER_KEY: _fresh_marker("CANCELAR", routed=True),
    })

    telemetry.record_flow_outcome(
        db, session, uuid.uuid4(), {"AGENDAR"},
        telemetry.OUTCOME_FLOW_CONFIRMED,
    )

    assert _outcomes(db) == []
    assert _marker(session) is not None


def test_flow_outcome_ignores_fallback_marker():
    db = FakeDB()
    session = fake_session(**{
        telemetry.MARKER_KEY: _fresh_marker("AGENDAR", routed=False),
    })

    telemetry.record_flow_outcome(
        db, session, uuid.uuid4(), {"AGENDAR"},
        telemetry.OUTCOME_FLOW_CONFIRMED,
    )

    assert _outcomes(db) == []


def test_supersession_abandons_previous_marker(captured, monkeypatch):
    # Nova classificação substitui marker pendente → ABANDONED (superseded).
    monkeypatch.setattr(bot_service.settings, "LLM_MODE", "shadow")
    old_cid = uuid.uuid4()
    stub = StubClassifier(FALLBACK_INTENT, 0.0, source="FALLBACK")
    db = FakeDB()
    session = fake_session(**{
        telemetry.MARKER_KEY: _fresh_marker("AGENDAR", routed=False, cid=old_cid),
    })

    _route(session, db, "hmm sei lá", stub)

    rows = _outcomes(db)
    assert len(rows) == 1
    assert rows[0].outcome == telemetry.OUTCOME_ABANDONED
    assert rows[0].classification_id == old_cid
    assert rows[0].outcome_detail == {"reason": "superseded"}
    # marker novo aponta para a classificação nova
    assert _marker(session)["cid"] == str(stub.classification_id)


def test_outcome_never_duplicated():
    # 1 desfecho por classificação — o primeiro vence (UNIQUE no banco).
    cid = uuid.uuid4()
    existing = SimpleNamespace(classification_id=cid)
    db = FakeDB({IntentOutcome: [existing]})
    session = fake_session(**{
        telemetry.MARKER_KEY: _fresh_marker("AGENDAR", routed=False, cid=cid),
    })

    telemetry.consume_menu_click(db, session, uuid.uuid4(), "opt_agendar")

    assert _outcomes(db) == []


# ─── Write-backs nos handlers reais ───────────────────────────────────────────

def test_confirmando_confirm_writes_flow_confirmed(captured, monkeypatch):
    from app.modules.whatsapp.helpers import resolve_input
    appt_id = uuid.uuid4()
    monkeypatch.setattr(
        h_confirmando.booking_engine, "confirm",
        lambda db, cid, intent: SimpleNamespace(appointment_id=appt_id),
    )
    cid = uuid.uuid4()
    db = FakeDB()
    session = fake_session(
        state="CONFIRMANDO",
        **{
            "slot_start_at": "2026-07-15T14:00:00+00:00",
            "professional_id": str(uuid.uuid4()),
            "service_id": str(uuid.uuid4()),
            telemetry.MARKER_KEY: _fresh_marker("AGENDAR", routed=True, cid=cid),
        },
    )

    h_confirmando.handle(
        db, session, uuid.uuid4(), "to", "inst", "opt_confirmar",
        resolve_input=resolve_input,
        start_escolhendo_horario=lambda *a, **k: None,
    )

    rows = _outcomes(db)
    assert len(rows) == 1
    assert rows[0].outcome == telemetry.OUTCOME_FLOW_CONFIRMED
    assert rows[0].classification_id == cid
    assert rows[0].outcome_detail["appointment_id"] == str(appt_id)


def test_confirmando_user_cancel_writes_flow_cancelled(captured, monkeypatch):
    from app.modules.whatsapp.helpers import resolve_input
    cid = uuid.uuid4()
    db = FakeDB()
    session = fake_session(
        state="CONFIRMANDO",
        **{telemetry.MARKER_KEY: _fresh_marker("AGENDAR", routed=True, cid=cid)},
    )

    h_confirmando.handle(
        db, session, uuid.uuid4(), "to", "inst", "opt_cancelar",
        resolve_input=resolve_input,
        start_escolhendo_horario=lambda *a, **k: None,
    )

    rows = _outcomes(db)
    assert len(rows) == 1
    assert rows[0].outcome == telemetry.OUTCOME_FLOW_CANCELLED
    assert rows[0].classification_id == cid


def test_cancelando_confirm_writes_flow_confirmed(captured, monkeypatch):
    from app.modules.whatsapp.helpers import resolve_input
    monkeypatch.setattr(h_cancelando.booking_engine, "cancel",
                        lambda db, cid, aid, reason=None: None)
    cid = uuid.uuid4()
    appt_id = str(uuid.uuid4())
    db = FakeDB()
    session = fake_session(
        state="CANCELANDO",
        **{
            "managing_appointment_id": appt_id,
            "last_list": [
                {"row_id": "opt_confirmar_cancel", "payload": "confirmar_cancel",
                 "title": "✅ Sim, cancelar"},
            ],
            telemetry.MARKER_KEY: _fresh_marker("CANCELAR", routed=True, cid=cid),
        },
    )

    h_cancelando.handle(
        db, session, uuid.uuid4(), "to", "inst", "opt_confirmar_cancel",
        resolve_input=resolve_input,
        start_gerenciando_agendamento=lambda *a, **k: None,
    )

    rows = _outcomes(db)
    assert len(rows) == 1
    assert rows[0].outcome == telemetry.OUTCOME_FLOW_CONFIRMED
    assert rows[0].classification_id == cid
    assert rows[0].outcome_detail == {"appointment_id": appt_id}


# ─── ChainClassifier: fsm_state + classification_id ───────────────────────────

def test_chain_persists_fsm_state_and_returns_classification_id():
    db = FakeDB()
    chain = ChainClassifier(db, regex_classifier=RegexClassifier(),
                            llm_classifier=NullLLMClassifier())

    result = chain.classify(uuid.uuid4(), "quero marcar um corte",
                            fsm_state="INICIO")

    persisted = [o for o in db.added if isinstance(o, IntentClassification)]
    assert len(persisted) == 1
    assert persisted[0].fsm_state == "INICIO"
    assert persisted[0].id is not None
    assert result.classification_id == persisted[0].id


# ─── _CLASSIFY_TOOL: schema de entities apertado (Parte 4) ────────────────────

def test_classify_tool_entities_schema_is_closed():
    entities = _CLASSIFY_TOOL["input_schema"]["properties"]["entities"]
    assert set(entities["properties"].keys()) == {
        "servico", "dia", "hora", "profissional",
    }
    assert entities["additionalProperties"] is False
    # todos opcionais — a LLM extrai o que houver
    assert "required" not in entities
