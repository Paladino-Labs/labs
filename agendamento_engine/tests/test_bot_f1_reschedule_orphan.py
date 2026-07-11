"""Testes Bot F1 — BUG C: reagendar mudando serviço cancela o agendamento antigo.

Fluxo real (confirmado em main): "Mudar serviço" (gerenciando_agendamento) entra
no pipeline BookingEngine (AWAITING_SERVICE). O vínculo com o agendamento antigo
viaja no BotSession.context (managing_appointment_id + is_rescheduling) e é
consumido em bot_service._handle_booking_state quando o engine devolve CONFIRMED:
o novo agendamento já existe → o antigo é cancelado com skip_policy=True e
reason "Substituído por reagendamento com serviço diferente".

Cobertura:
  - CONFIRMED com marker de reagendamento → cancela o antigo (ordem: novo
    primeiro; cancelamento depois) + nota ao cliente + reset da sessão.
  - CONFIRMED sem marker (AGENDAR normal) → nenhum cancelamento.
  - Criação do novo falha (slot ocupado ou erro) → o antigo NÃO é cancelado
    e o marker sobrevive (cliente nunca fica sem nada).
  - Cancelamento do antigo falha → fluxo segue (novo já existe), loga e avisa.
  - gerenciando reagendar_mudar preserva o marker ao recomeçar a seleção.
  - reagendar_mesmo (confirmando legado) → reschedule, nunca cancel (não regride).
  - Telemetria: substituição consome marker REMARCAR com service_changed=True.

Estratégia: FakeDB in-memory + monkeypatch (padrão test_bot_f5a).
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.infrastructure.db.models.booking_session import BookingSession
from app.infrastructure.db.models.intent_classification import IntentOutcome
from app.modules.booking.actions import BookingAction
from app.modules.booking.engine import booking_engine
from app.modules.whatsapp import bot_service
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.handlers import confirmando as h_confirmando
from app.modules.whatsapp.handlers import gerenciando_agendamento as h_gerenciando
from app.modules.whatsapp.helpers import resolve_input
from app.modules.whatsapp.input_parser import whatsapp_input_parser
from app.modules.whatsapp.intent import telemetry
from app.modules.whatsapp.response_formatter import whatsapp_response_formatter


# ─── Fakes (padrão test_bot_f5a) ──────────────────────────────────────────────

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


def fake_session(state="AWAITING_CONFIRMATION", **ctx):
    base = {"customer_id": str(uuid.uuid4()), "customer_name": "Maria"}
    base.update(ctx)
    return SimpleNamespace(id=uuid.uuid4(), state=state, context=base)


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


def _confirmed_result(appt_id):
    return SimpleNamespace(
        next_state="CONFIRMED",
        options=[],
        confirmation_data=SimpleNamespace(appointment_id=appt_id),
    )


def _drive_booking_confirm(monkeypatch, db, session, company_id, update_outcome,
                           cancel_calls, formatter_calls):
    """Dirige _handle_booking_state com CONFIRM parseado e engine.update stubado.

    update_outcome: SimpleNamespace (resultado) ou Exception (criação falhou).
    """
    monkeypatch.setattr(whatsapp_input_parser, "parse",
                        lambda *a, **k: (BookingAction.CONFIRM, {}))

    def _update(db_, bs, action, payload):
        if isinstance(update_outcome, Exception):
            raise update_outcome
        return update_outcome

    monkeypatch.setattr(booking_engine, "update", _update)
    monkeypatch.setattr(
        whatsapp_response_formatter, "format_and_send",
        lambda *a, **k: formatter_calls.append(a),
    )

    import app.modules.appointments.service as appointment_svc

    def _cancel(db_, cid, appt_id, user_id=None, reason=None, skip_policy=False):
        cancel_calls.append({
            "appointment_id": appt_id, "user_id": user_id,
            "reason": reason, "skip_policy": skip_policy,
        })

    monkeypatch.setattr(appointment_svc, "cancel_appointment", _cancel)

    bot_service._handle_booking_state(
        db, session, company_id, "inst", "5511999@s.whatsapp.net",
        "1", "America/Sao_Paulo",
    )


def _booking_session_db(company_id):
    bs = SimpleNamespace(
        id=uuid.uuid4(), company_id=company_id,
        state="AWAITING_CONFIRMATION", context={},
    )
    return bs, FakeDB({BookingSession: [bs]})


# ─── Substituição no pipeline BookingEngine ───────────────────────────────────

def test_confirmed_with_reschedule_marker_cancels_old(captured, monkeypatch):
    company_id = uuid.uuid4()
    old_id, new_id = uuid.uuid4(), uuid.uuid4()
    bs, db = _booking_session_db(company_id)
    session = fake_session(
        booking_session_id=str(bs.id),
        managing_appointment_id=str(old_id),
        is_rescheduling=True,
    )
    cancel_calls, formatter_calls = [], []

    _drive_booking_confirm(monkeypatch, db, session, company_id,
                           _confirmed_result(new_id), cancel_calls, formatter_calls)

    assert len(cancel_calls) == 1
    call = cancel_calls[0]
    assert call["appointment_id"] == old_id
    assert call["reason"] == "Substituído por reagendamento com serviço diferente"
    assert call["skip_policy"] is True
    assert call["user_id"] is None
    # sessão resetada — marker não vaza para a próxima conversa
    assert session.state == "INICIO"
    assert "managing_appointment_id" not in (session.context or {})
    assert "is_rescheduling" not in (session.context or {})
    # cliente informado: confirmação (formatter) + nota da substituição
    assert len(formatter_calls) == 1
    assert ("text", messages.REAGENDAMENTO_ANTERIOR_CANCELADO) in captured


def test_confirmed_without_marker_does_not_cancel(captured, monkeypatch):
    company_id = uuid.uuid4()
    bs, db = _booking_session_db(company_id)
    session = fake_session(booking_session_id=str(bs.id))
    cancel_calls, formatter_calls = [], []

    _drive_booking_confirm(monkeypatch, db, session, company_id,
                           _confirmed_result(uuid.uuid4()), cancel_calls, formatter_calls)

    assert cancel_calls == []
    assert len(formatter_calls) == 1
    assert ("text", messages.REAGENDAMENTO_ANTERIOR_CANCELADO) not in captured


def test_managing_id_without_is_rescheduling_does_not_cancel(captured, monkeypatch):
    # managing_appointment_id sozinho (ex.: fluxo de cancelamento abandonado)
    # não caracteriza reagendamento — exige a conjunção com is_rescheduling.
    company_id = uuid.uuid4()
    bs, db = _booking_session_db(company_id)
    session = fake_session(
        booking_session_id=str(bs.id),
        managing_appointment_id=str(uuid.uuid4()),
    )
    cancel_calls, formatter_calls = [], []

    _drive_booking_confirm(monkeypatch, db, session, company_id,
                           _confirmed_result(uuid.uuid4()), cancel_calls, formatter_calls)

    assert cancel_calls == []


def test_creation_failure_keeps_old_and_marker(captured, monkeypatch):
    # Slot ocupado: engine volta a AWAITING_TIME — antigo intacto, marker vivo.
    company_id = uuid.uuid4()
    bs, db = _booking_session_db(company_id)
    session = fake_session(
        booking_session_id=str(bs.id),
        managing_appointment_id=str(uuid.uuid4()),
        is_rescheduling=True,
    )
    cancel_calls, formatter_calls = [], []
    retry = SimpleNamespace(next_state="AWAITING_TIME", options=[],
                            confirmation_data=None, error="SLOT_UNAVAILABLE")

    _drive_booking_confirm(monkeypatch, db, session, company_id,
                           retry, cancel_calls, formatter_calls)

    assert cancel_calls == []
    assert session.context.get("is_rescheduling") is True
    assert session.state == "AWAITING_TIME"


def test_creation_exception_keeps_old(captured, monkeypatch):
    company_id = uuid.uuid4()
    bs, db = _booking_session_db(company_id)
    session = fake_session(
        booking_session_id=str(bs.id),
        managing_appointment_id=str(uuid.uuid4()),
        is_rescheduling=True,
    )
    cancel_calls, formatter_calls = [], []

    _drive_booking_confirm(monkeypatch, db, session, company_id,
                           RuntimeError("boom"), cancel_calls, formatter_calls)

    assert cancel_calls == []
    assert ("text", messages.ERRO_GENERICO) in captured


def test_cancel_failure_does_not_break_flow(captured, monkeypatch):
    # Novo criado, cancel do antigo falha → loga, avisa e segue (órfão é o
    # mal menor vs. cliente sem nenhum agendamento).
    company_id = uuid.uuid4()
    old_id, new_id = uuid.uuid4(), uuid.uuid4()
    bs, db = _booking_session_db(company_id)
    session = fake_session(
        booking_session_id=str(bs.id),
        managing_appointment_id=str(old_id),
        is_rescheduling=True,
    )
    formatter_calls = []

    monkeypatch.setattr(whatsapp_input_parser, "parse",
                        lambda *a, **k: (BookingAction.CONFIRM, {}))
    monkeypatch.setattr(booking_engine, "update",
                        lambda *a, **k: _confirmed_result(new_id))
    monkeypatch.setattr(whatsapp_response_formatter, "format_and_send",
                        lambda *a, **k: formatter_calls.append(a))

    import app.modules.appointments.service as appointment_svc

    def _cancel_boom(*a, **k):
        raise RuntimeError("cancel falhou")

    monkeypatch.setattr(appointment_svc, "cancel_appointment", _cancel_boom)

    bot_service._handle_booking_state(
        db, session, company_id, "inst", "5511999@s.whatsapp.net",
        "1", "America/Sao_Paulo",
    )

    # não propagou; confirmação enviada + aviso honesto sobre o antigo
    assert len(formatter_calls) == 1
    assert ("text", messages.REAGENDAMENTO_ANTERIOR_NAO_CANCELADO) in captured
    assert session.state == "INICIO"


def test_substitution_consumes_remarcar_marker(captured, monkeypatch):
    # Telemetria (F5a): a substituição materializa REMARCAR, não AGENDAR.
    company_id = uuid.uuid4()
    old_id, new_id, cid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    bs, db = _booking_session_db(company_id)
    session = fake_session(
        booking_session_id=str(bs.id),
        managing_appointment_id=str(old_id),
        is_rescheduling=True,
        **{telemetry.MARKER_KEY: {
            "cid": str(cid), "intent": "REMARCAR", "routed": True,
            "at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    cancel_calls, formatter_calls = [], []

    _drive_booking_confirm(monkeypatch, db, session, company_id,
                           _confirmed_result(new_id), cancel_calls, formatter_calls)

    rows = [o for o in db.added if isinstance(o, IntentOutcome)]
    assert len(rows) == 1
    assert rows[0].outcome == telemetry.OUTCOME_FLOW_CONFIRMED
    assert rows[0].classification_id == cid
    assert rows[0].outcome_detail == {
        "appointment_id": str(new_id),
        "service_changed": True,
        "replaced_appointment_id": str(old_id),
    }


# ─── gerenciando: o marker viaja pelo fluxo ───────────────────────────────────

_SUBMENU_LIST = [
    {"row_id": "opt_reagendar_mesmo", "payload": "reagendar_mesmo",
     "title": "🕐 Mesmo serviço e profissional"},
    {"row_id": "opt_reagendar_mudar", "payload": "reagendar_mudar",
     "title": "🔁 Mudar serviço"},
]


def test_reagendar_mudar_preserves_marker(captured, monkeypatch):
    old_id = str(uuid.uuid4())
    db = FakeDB()
    session = fake_session(
        state="GERENCIANDO_AGENDAMENTO",
        managing_appointment_id=old_id,
        is_rescheduling=True,
        service_id=str(uuid.uuid4()),
        service_name="Corte",
        professional_id=str(uuid.uuid4()),
        last_list=list(_SUBMENU_LIST),
    )
    started = []

    h_gerenciando.handle(
        db, session, uuid.uuid4(), "5511999@s.whatsapp.net", "inst",
        "opt_reagendar_mudar",
        resolve_input=resolve_input,
        handle_ver_agendamentos=lambda *a, **k: None,
        start_cancelando=lambda *a, **k: None,
        start_escolhendo_horario=lambda *a, **k: None,
        start_escolhendo_servico=lambda *a, **k: started.append("servico"),
    )

    assert started == ["servico"]
    ctx = session.context or {}
    # o vínculo sobrevive à limpeza de serviço/profissional/slot
    assert ctx.get("managing_appointment_id") == old_id
    assert ctx.get("is_rescheduling") is True
    for key in ("service_id", "service_name", "professional_id"):
        assert key not in ctx


def test_opt_reagendar_sets_marker(captured, monkeypatch):
    appt_id = uuid.uuid4()
    appt = SimpleNamespace(
        start_at=datetime.now(timezone.utc) + timedelta(hours=48),
        services=[SimpleNamespace(service_id=uuid.uuid4(), service_name="Corte")],
        professional_id=uuid.uuid4(),
        professional=SimpleNamespace(name="João"),
    )
    monkeypatch.setattr(h_gerenciando.appointment_svc, "get_appointment_or_404",
                        lambda db, cid, aid: appt)
    db = FakeDB()
    session = fake_session(
        state="GERENCIANDO_AGENDAMENTO",
        managing_appointment_id=str(appt_id),
        last_list=[{"row_id": "opt_reagendar", "payload": "opt_reagendar",
                    "title": "🔄 Reagendar"}],
    )

    h_gerenciando.handle(
        db, session, uuid.uuid4(), "5511999@s.whatsapp.net", "inst",
        "opt_reagendar",
        resolve_input=resolve_input,
        handle_ver_agendamentos=lambda *a, **k: None,
        start_cancelando=lambda *a, **k: None,
        start_escolhendo_horario=lambda *a, **k: None,
        start_escolhendo_servico=lambda *a, **k: None,
    )

    assert session.context.get("is_rescheduling") is True
    assert ("buttons", "Como deseja reagendar?") in captured


# ─── confirmando legado: reagendar_mesmo não regride ─────────────────────────

def test_reagendar_mesmo_reschedules_without_cancel(captured, monkeypatch):
    appt_id = str(uuid.uuid4())
    reschedules, cancels = [], []
    monkeypatch.setattr(
        h_confirmando.booking_engine, "reschedule",
        lambda db, cid, aid, start_at: reschedules.append((aid, start_at)),
    )
    monkeypatch.setattr(
        h_confirmando.booking_engine, "cancel",
        lambda *a, **k: cancels.append(a),
    )
    db = FakeDB()
    session = fake_session(
        state="CONFIRMANDO",
        is_rescheduling=True,
        managing_appointment_id=appt_id,
        slot_start_at="2026-07-20T14:00:00+00:00",
        professional_id=str(uuid.uuid4()),
        service_id=str(uuid.uuid4()),
    )

    h_confirmando.handle(
        db, session, uuid.uuid4(), "5511999@s.whatsapp.net", "inst",
        "opt_confirmar",
        resolve_input=resolve_input,
        start_escolhendo_horario=lambda *a, **k: None,
    )

    assert len(reschedules) == 1
    assert reschedules[0][0] == uuid.UUID(appt_id)
    assert cancels == []
    assert session.state == "INICIO"   # reset após sucesso
