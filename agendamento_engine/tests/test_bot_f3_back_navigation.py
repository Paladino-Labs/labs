"""Testes Bot F3 — "voltar" = um passo atrás (BACK) em vez de reset total.

Decisão D2: "voltar" digitado vira BookingAction.BACK nos estados do FSM
(o engine já sabia voltar via _BACK_STATE; só o botão "Alterar horário"
emitia BACK). Reset total fica com "0"/"menu"/"início"/"sair".

Cobertura:
  - is_universal_command: "voltar" não é mais reset; demais comandos intactos.
  - is_back_command: conjunto de palavras/payloads de BACK.
  - Parser: "voltar" → BACK em todos os BOOKING_STATES; opção "← Voltar"
    numerada resolve BACK sem deslocar o mapeamento número→item.
  - AWAITING_TIME: matching numérico espelha a PÁGINA exibida (nav + slots +
    Voltar) — digitar um número seleciona o slot CORRETO em qualquer página;
    clique em slot de mensagem antiga (fora da página) segue resolvendo por
    row_id; número fora da página NUNCA seleciona slot invisível.
  - Alinhamento formatter×parser: para cada linha exibida, digitar seu número
    resolve exatamente aquela linha.
  - bot_service: BACK em AWAITING_SERVICE (primeiro estado) → menu principal;
    BACK nos demais estados vai ao engine.
  - _handle_legacy_back: volta contextual (CANCELANDO→GERENCIANDO,
    GERENCIANDO→VER_AGENDAMENTOS limpando is_rescheduling, CONFIRMANDO→
    horários, HORARIO/TURNO→data) e menu como default.

Estratégia: FakeDB in-memory + monkeypatch (padrão test_bot_f1/f5a).
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.infrastructure.db.models.booking_session import BookingSession
from app.modules.booking.actions import BookingAction
from app.modules.booking.engine import _BACK_STATE, booking_engine
from app.modules.whatsapp import bot_service
from app.modules.whatsapp import sender
from app.modules.whatsapp.handlers import inicio as h_inicio
from app.modules.whatsapp.helpers import is_back_command, is_universal_command
from app.modules.whatsapp.input_parser import BOOKING_STATES, whatsapp_input_parser
from app.modules.whatsapp.response_formatter import whatsapp_response_formatter


# ─── Fakes (padrão test_bot_f1) ───────────────────────────────────────────────

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


def fake_session(state="AWAITING_SERVICE", **ctx):
    base = {"customer_id": str(uuid.uuid4()), "customer_name": "Maria"}
    base.update(ctx)
    return SimpleNamespace(id=uuid.uuid4(), state=state, context=base)


@pytest.fixture
def captured(monkeypatch):
    sent = []
    monkeypatch.setattr(sender, "send_text",
                        lambda inst, to, text: sent.append(("text", text)))
    monkeypatch.setattr(sender, "send_buttons",
                        lambda inst, to, text, buttons: sent.append(("buttons", text, buttons)))
    monkeypatch.setattr(sender, "send_list",
                        lambda inst, to, title, desc, rows, *a, **k: sent.append(("list", title, rows)))
    return sent


TZ = "America/Sao_Paulo"


def _slots(n, base=None):
    """n slots consecutivos (row_key slot_1..slot_n) no formato de last_listed_slots."""
    base = base or datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        start = base + timedelta(minutes=30 * i)
        out.append({
            "start_at":          start.isoformat(),
            "end_at":            (start + timedelta(minutes=30)).isoformat(),
            "professional_id":   str(uuid.uuid4()),
            "professional_name": f"Prof{i + 1}",
            "row_key":           f"slot_{i + 1}",
        })
    return out


# ─── Comandos universais (PASSO 1) ────────────────────────────────────────────

def test_voltar_is_not_universal_reset():
    assert is_universal_command("voltar") is None
    assert is_universal_command("Voltar") is None
    assert is_universal_command(" volta ") is None


def test_reset_commands_unchanged():
    for word in ("0", "menu", "início", "inicio", "sair", "MENU"):
        assert is_universal_command(word) == "menu"


def test_other_universal_commands_intact():
    assert is_universal_command("ver agendamentos") == "ver_agendamentos"
    assert is_universal_command("meus agendamentos") == "ver_agendamentos"
    assert is_universal_command("atendente") == "humano"
    assert is_universal_command("humano") == "humano"


def test_is_back_command_word_set():
    for word in ("voltar", "Voltar", "VOLTA", " volta ", "nav_voltar", "← Voltar"):
        assert is_back_command(word) is True
    for word in ("menu", "0", "início", "sair", "voltarei", "volto", "", None):
        assert is_back_command(word) is False


# ─── Parser: "voltar" → BACK em todos os estados do FSM (PASSO 2) ─────────────

@pytest.mark.parametrize("state", sorted(BOOKING_STATES))
@pytest.mark.parametrize("word", ["voltar", "volta", "nav_voltar", "← Voltar"])
def test_back_word_emits_back_in_every_fsm_state(state, word):
    result = whatsapp_input_parser.parse(word, state, {}, TZ)
    assert result == (BookingAction.BACK, {})


def test_menu_words_do_not_reach_parser_as_back():
    # "0"/"menu" são interceptados antes do parser; se chegarem, não são BACK
    result = whatsapp_input_parser.parse("menu", "AWAITING_SERVICE", {}, TZ)
    assert result is None or result[0] != BookingAction.BACK


# ─── Parser: opção "← Voltar" numerada (PASSO 3) ──────────────────────────────

_SERVICES = [
    {"row_key": "serv_1", "name": "Corte"},
    {"row_key": "serv_2", "name": "Barba"},
]


def test_service_number_beyond_list_is_back():
    ctx = {"last_listed_services": list(_SERVICES)}
    assert whatsapp_input_parser.parse("3", "AWAITING_SERVICE", ctx, TZ) == \
        (BookingAction.BACK, {})


def test_service_numbers_still_select_correct_item():
    ctx = {"last_listed_services": list(_SERVICES)}
    assert whatsapp_input_parser.parse("1", "AWAITING_SERVICE", ctx, TZ) == \
        (BookingAction.SELECT_SERVICE, {"row_key": "serv_1"})
    assert whatsapp_input_parser.parse("2", "AWAITING_SERVICE", ctx, TZ) == \
        (BookingAction.SELECT_SERVICE, {"row_key": "serv_2"})
    # além do Voltar → não resolve
    assert whatsapp_input_parser.parse("4", "AWAITING_SERVICE", ctx, TZ) is None


def test_professional_number_beyond_list_is_back():
    ctx = {"last_listed_professionals": [
        {"row_key": "prof_1", "name": "João"},
        {"row_key": "prof_qualquer", "name": "Qualquer disponível"},
    ]}
    assert whatsapp_input_parser.parse("3", "AWAITING_PROFESSIONAL", ctx, TZ) == \
        (BookingAction.BACK, {})
    assert whatsapp_input_parser.parse("1", "AWAITING_PROFESSIONAL", ctx, TZ) == \
        (BookingAction.SELECT_PROFESSIONAL, {"row_key": "prof_1"})


def test_date_number_beyond_list_is_back():
    ctx = {"last_listed_dates": [
        {"row_key": "date_1", "label": "Hoje (20/07)", "has_availability": True},
        {"row_key": "date_2", "label": "Amanhã (21/07)", "has_availability": True},
    ]}
    assert whatsapp_input_parser.parse("3", "AWAITING_DATE", ctx, TZ) == \
        (BookingAction.BACK, {})
    assert whatsapp_input_parser.parse("2", "AWAITING_DATE", ctx, TZ) == \
        (BookingAction.SELECT_DATE, {"row_key": "date_2"})


# ─── Parser: AWAITING_TIME espelha a página exibida (CRÍTICO F2×F3) ──────────

def test_time_page1_numbers_select_correct_slot(monkeypatch):
    monkeypatch.setattr(settings, "BOT_MAX_SLOTS_DISPLAYED", 6)
    ctx = {"last_listed_slots": _slots(12)}  # sem slot_offset → página 1

    # página 1: linhas 1..6 = slot_1..slot_6, 7 = "Mais tarde →", 8 = "← Voltar"
    for n in range(1, 7):
        assert whatsapp_input_parser.parse(str(n), "AWAITING_TIME", ctx, TZ) == \
            (BookingAction.SELECT_TIME, {"row_key": f"slot_{n}"})
    assert whatsapp_input_parser.parse("7", "AWAITING_TIME", ctx, TZ) == \
        (BookingAction.MORE_SLOTS_LATER, {})
    assert whatsapp_input_parser.parse("8", "AWAITING_TIME", ctx, TZ) == \
        (BookingAction.BACK, {})
    # número fora da página NUNCA seleciona slot invisível
    assert whatsapp_input_parser.parse("9", "AWAITING_TIME", ctx, TZ) is None


def test_time_page2_numbers_select_correct_slot(monkeypatch):
    monkeypatch.setattr(settings, "BOT_MAX_SLOTS_DISPLAYED", 6)
    ctx = {"last_listed_slots": _slots(12), "slot_offset": 6}

    # página 2: linha 1 = "← Mais cedo", 2..7 = slot_7..slot_12, 8 = "← Voltar"
    assert whatsapp_input_parser.parse("1", "AWAITING_TIME", ctx, TZ) == \
        (BookingAction.MORE_SLOTS_EARLIER, {})
    for n in range(2, 8):
        assert whatsapp_input_parser.parse(str(n), "AWAITING_TIME", ctx, TZ) == \
            (BookingAction.SELECT_TIME, {"row_key": f"slot_{n + 5}"})
    assert whatsapp_input_parser.parse("8", "AWAITING_TIME", ctx, TZ) == \
        (BookingAction.BACK, {})


def test_time_offpage_rowid_click_still_resolves(monkeypatch):
    # clique em mensagem antiga: slot fora da página resolve por row_id
    monkeypatch.setattr(settings, "BOT_MAX_SLOTS_DISPLAYED", 6)
    ctx = {"last_listed_slots": _slots(12), "slot_offset": 6}
    assert whatsapp_input_parser.parse("slot_2", "AWAITING_TIME", ctx, TZ) == \
        (BookingAction.SELECT_TIME, {"row_key": "slot_2"})


def test_time_stale_offset_falls_back_to_first_page(monkeypatch):
    # offset obsoleto (slots mudaram) — mesmo guard do formatter: página 1
    monkeypatch.setattr(settings, "BOT_MAX_SLOTS_DISPLAYED", 6)
    ctx = {"last_listed_slots": _slots(4), "slot_offset": 12}
    assert whatsapp_input_parser.parse("2", "AWAITING_TIME", ctx, TZ) == \
        (BookingAction.SELECT_TIME, {"row_key": "slot_2"})
    # 4 slots + "← Voltar" = 5 linhas
    assert whatsapp_input_parser.parse("5", "AWAITING_TIME", ctx, TZ) == \
        (BookingAction.BACK, {})


def test_confirmation_voltar_behaves_like_alterar():
    assert whatsapp_input_parser.parse("voltar", "AWAITING_CONFIRMATION", {}, TZ) == \
        (BookingAction.BACK, {})
    assert whatsapp_input_parser.parse("alterar horário", "AWAITING_CONFIRMATION", {}, TZ) == \
        (BookingAction.BACK, {})


# ─── Alinhamento formatter × parser (linha exibida N ↔ número N) ──────────────

def _rendered_rows(captured):
    kind, _title, rows = captured[-1]
    assert kind == "list"
    return rows


def test_formatter_parser_alignment_slots_page1(captured, monkeypatch):
    monkeypatch.setattr(settings, "BOT_MAX_SLOTS_DISPLAYED", 6)
    slot_dicts = _slots(12)
    ctx = {"last_listed_slots": slot_dicts}  # any_prof (sem professional_id)
    options = [
        SimpleNamespace(
            start_at=datetime.fromisoformat(s["start_at"]),
            end_at=datetime.fromisoformat(s["end_at"]),
            professional_id=uuid.UUID(s["professional_id"]),
            professional_name=s["professional_name"],
            row_key=s["row_key"],
        )
        for s in slot_dicts
    ]
    result = SimpleNamespace(next_state="AWAITING_TIME", options=options,
                             error=None, confirmation_data=None)
    whatsapp_response_formatter.format_and_send(result, "inst", "5511999", ctx, TZ)

    rows = _rendered_rows(captured)
    assert rows[-1]["rowId"] == "nav_voltar"        # Voltar é a última linha
    assert rows[-2]["rowId"] == "nav_mais_tarde"    # nav preservada (F2)
    assert [r["rowId"] for r in rows[:6]] == [f"slot_{i}" for i in range(1, 7)]

    # digitar o número da linha N resolve exatamente a linha N
    expected = {
        "slot_1": (BookingAction.SELECT_TIME, {"row_key": "slot_1"}),
        "nav_mais_tarde": (BookingAction.MORE_SLOTS_LATER, {}),
        "nav_voltar": (BookingAction.BACK, {}),
    }
    for i, row in enumerate(rows):
        parsed = whatsapp_input_parser.parse(str(i + 1), "AWAITING_TIME", ctx, TZ)
        if row["rowId"].startswith("slot_"):
            assert parsed == (BookingAction.SELECT_TIME, {"row_key": row["rowId"]})
        else:
            assert parsed == expected[row["rowId"]]


def test_formatter_parser_alignment_services(captured):
    ctx = {"last_listed_services": list(_SERVICES)}
    options = [
        SimpleNamespace(row_key=s["row_key"], name=s["name"],
                        price=Decimal("50.00"), duration_minutes=30)
        for s in _SERVICES
    ]
    result = SimpleNamespace(next_state="AWAITING_SERVICE", options=options,
                             error=None, confirmation_data=None)
    whatsapp_response_formatter.format_and_send(result, "inst", "5511999", ctx, TZ)

    rows = _rendered_rows(captured)
    assert [r["rowId"] for r in rows] == ["serv_1", "serv_2", "nav_voltar"]
    for i, row in enumerate(rows):
        parsed = whatsapp_input_parser.parse(str(i + 1), "AWAITING_SERVICE", ctx, TZ)
        if row["rowId"] == "nav_voltar":
            assert parsed == (BookingAction.BACK, {})
        else:
            assert parsed == (BookingAction.SELECT_SERVICE, {"row_key": row["rowId"]})


def test_formatter_empty_options_has_no_voltar_row(captured):
    result = SimpleNamespace(next_state="AWAITING_SERVICE", options=[],
                             error=None, confirmation_data=None)
    whatsapp_response_formatter.format_and_send(result, "inst", "5511999", {}, TZ)
    assert captured[-1][0] == "text"  # SEM_SERVICOS — sem lista, sem Voltar


# ─── Engine: cadeia _BACK_STATE inalterada ────────────────────────────────────

def test_back_state_chain_unchanged():
    assert _BACK_STATE["AWAITING_PROFESSIONAL"] == "AWAITING_SERVICE"
    assert _BACK_STATE["AWAITING_DATE"] == "AWAITING_PROFESSIONAL"
    assert _BACK_STATE["AWAITING_TIME"] == "AWAITING_DATE"
    assert _BACK_STATE["AWAITING_CONFIRMATION"] == "AWAITING_CUSTOMER"
    assert "AWAITING_SERVICE" not in _BACK_STATE  # primeiro estado: sem anterior


# ─── bot_service: BACK no primeiro estado → menu principal ────────────────────

def _booking_session_db(company_id, state="AWAITING_SERVICE"):
    bs = SimpleNamespace(
        id=uuid.uuid4(), company_id=company_id,
        state=state, context={},
    )
    return bs, FakeDB({BookingSession: [bs]})


def test_back_in_awaiting_service_goes_to_menu(captured, monkeypatch):
    company_id = uuid.uuid4()
    bs, db = _booking_session_db(company_id, state="AWAITING_SERVICE")
    session = fake_session(state="AWAITING_SERVICE", booking_session_id=str(bs.id))

    menu_calls = []
    monkeypatch.setattr(h_inicio, "show_menu_principal",
                        lambda *a, **k: menu_calls.append(a))

    def _update_must_not_run(*a, **k):
        raise AssertionError("engine.update não deve ser chamado no BACK do primeiro estado")

    monkeypatch.setattr(booking_engine, "update", _update_must_not_run)

    bot_service._handle_booking_state(
        db, session, company_id, "inst", "5511999@s.whatsapp.net",
        "voltar", TZ,
    )

    assert len(menu_calls) == 1
    assert session.state == "INICIO"
    # cliente preservado no reset (keep_customer=True)
    assert session.context.get("customer_name") == "Maria"


def test_back_in_later_state_goes_to_engine(captured, monkeypatch):
    company_id = uuid.uuid4()
    bs, db = _booking_session_db(company_id, state="AWAITING_PROFESSIONAL")
    session = fake_session(state="AWAITING_PROFESSIONAL", booking_session_id=str(bs.id))

    engine_calls = []

    def _update(db_, bs_, action, payload):
        engine_calls.append((action, payload))
        bs_.state = "AWAITING_SERVICE"
        return SimpleNamespace(next_state="AWAITING_SERVICE", options=[],
                               error=None, confirmation_data=None)

    monkeypatch.setattr(booking_engine, "update", _update)
    formatter_calls = []
    monkeypatch.setattr(whatsapp_response_formatter, "format_and_send",
                        lambda *a, **k: formatter_calls.append(a))

    bot_service._handle_booking_state(
        db, session, company_id, "inst", "5511999@s.whatsapp.net",
        "voltar", TZ,
    )

    assert engine_calls == [(BookingAction.BACK, {})]
    assert session.state == "AWAITING_SERVICE"
    assert len(formatter_calls) == 1


# ─── _handle_legacy_back: volta contextual (PASSO 4) ──────────────────────────

def test_legacy_back_cancelando_returns_to_gerenciando(captured, monkeypatch):
    appt = SimpleNamespace(id=uuid.uuid4())
    import app.modules.appointments.service as appointment_svc
    monkeypatch.setattr(appointment_svc, "get_appointment_or_404",
                        lambda db, cid, aid: appt)
    started = []
    monkeypatch.setattr(bot_service, "_start_gerenciando_agendamento",
                        lambda db, s, cid, wid, inst, a: started.append(a))

    session = fake_session(state="CANCELANDO",
                           managing_appointment_id=str(uuid.uuid4()))
    bot_service._handle_legacy_back(FakeDB(), session, uuid.uuid4(),
                                    "inst", "5511999", "Barbearia")
    assert started == [appt]


def test_legacy_back_gerenciando_returns_to_lista_and_clears_marker(captured, monkeypatch):
    listed = []
    monkeypatch.setattr(bot_service, "_handle_ver_agendamentos",
                        lambda *a, **k: listed.append(True))

    session = fake_session(state="GERENCIANDO_AGENDAMENTO",
                           managing_appointment_id=str(uuid.uuid4()),
                           is_rescheduling=True)
    bot_service._handle_legacy_back(FakeDB(), session, uuid.uuid4(),
                                    "inst", "5511999", "Barbearia")
    assert listed == [True]
    # voltar aborta o reagendamento em curso — marker não vaza (F1)
    assert "is_rescheduling" not in (session.context or {})


def test_legacy_back_confirmando_relists_horarios(captured, monkeypatch):
    started = []
    monkeypatch.setattr(bot_service, "_start_escolhendo_horario",
                        lambda *a, **k: started.append(True))

    session = fake_session(state="CONFIRMANDO",
                           service_id=str(uuid.uuid4()),
                           slot_start_at="2026-07-20T14:00:00+00:00",
                           selected_date="2026-07-20")
    bot_service._handle_legacy_back(FakeDB(), session, uuid.uuid4(),
                                    "inst", "5511999", "Barbearia")
    assert started == [True]
    # mesma limpeza do botão "Alterar horário"
    assert "slot_start_at" not in session.context
    assert "selected_date" not in session.context


def test_legacy_back_horario_and_turno_return_to_data(captured, monkeypatch):
    for state in ("ESCOLHENDO_HORARIO", "ESCOLHENDO_TURNO"):
        sent_data = []
        monkeypatch.setattr(bot_service, "_send_escolher_data",
                            lambda *a, **k: sent_data.append(True))
        session = fake_session(state=state,
                               service_id=str(uuid.uuid4()),
                               slot_offset=6, selected_turno="tarde")
        bot_service._handle_legacy_back(FakeDB(), session, uuid.uuid4(),
                                        "inst", "5511999", "Barbearia")
        assert sent_data == [True], state
        assert "slot_offset" not in session.context
        assert "selected_turno" not in session.context


@pytest.mark.parametrize("state", [
    "INICIO", "MENU_PRINCIPAL", "OFERTA_RECORRENTE", "VER_AGENDAMENTOS",
    "ESCOLHENDO_SERVICO", "ESCOLHENDO_PROFISSIONAL", "ESCOLHENDO_DATA",
    "ESCOLHENDO_PRODUTO", "CONFIRMANDO_PRODUTO", "ESCOLHENDO_PACOTE",
])
def test_legacy_back_default_is_menu(state, captured, monkeypatch):
    menu_calls = []
    monkeypatch.setattr(h_inicio, "show_menu_principal",
                        lambda *a, **k: menu_calls.append(a))
    session = fake_session(state=state)
    bot_service._handle_legacy_back(FakeDB(), session, uuid.uuid4(),
                                    "inst", "5511999", "Barbearia")
    assert len(menu_calls) == 1
    assert session.state == "INICIO"
