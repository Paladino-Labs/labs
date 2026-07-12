"""Testes Bot F4 — turno (manhã/tarde/noite) como SUB-ESTADO do canal bot.

Decisão D1: o turno vive na camada de adaptação do bot (bot_service /
input_parser / response_formatter), NUNCA no FSM compartilhado com o web.
Fluxo do bot: serviço → profissional → data → TURNO → horário → confirmação;
o FSM permanece em AWAITING_TIME durante todo o sub-estado.

Cobertura:
  - Parser: menu de turnos espelha o formatter (números, rowId, voto de
    enquete com contagem/"— indisponível", "← Voltar" como última linha).
  - bot_service: entrada no sub-estado após SELECT_DATE com contagens
    derivadas da MESMA lista entregue (invariante F2 — contagem == lista);
    escolha de turno aplicada SEM engine.update() (handler órfão
    _handle_select_shift); turno esgotado → feedback + re-exibição;
    re-entrada no sub-estado após conflito de confirm (SLOT_UNAVAILABLE);
    guard de expiração no caminho que não passa por update().
  - BACK (F3×F4): menu de turnos → data (via engine); lista de horários
    filtrada → menu de turnos (na camada, com contagens frescas).
  - Alinhamento número→slot DENTRO do turno filtrado (páginas 1 e 2).
  - Canal WEB protegido: FSM sem transições de turno; SELECT_DATE →
    AWAITING_TIME direto com o dia inteiro; update(SELECT_SHIFT) inválido.
  - get_shift_availability é stateless (não recebe sessão).

Estratégia: FakeDB in-memory + monkeypatch (padrão test_bot_f3).
"""
import uuid
from datetime import datetime, date, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.core.config import settings
from app.infrastructure.db.models.booking_session import BookingSession
from app.modules.booking.actions import BookingAction, InvalidActionError
from app.modules.booking.engine import BookingEngine, _BACK_STATE, booking_engine
from app.modules.booking.schemas import ShiftOption, SlotOption
from app.modules.whatsapp import bot_service
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.handlers import inicio as h_inicio
from app.modules.whatsapp.input_parser import whatsapp_input_parser
from app.modules.whatsapp.response_formatter import whatsapp_response_formatter


TZ = "America/Sao_Paulo"
SP = ZoneInfo(TZ)

COMPANY_ID = uuid.uuid4()
PROF_ID    = uuid.uuid4()
SERVICE_ID = uuid.uuid4()


# ─── Fakes (padrão test_bot_f3) ───────────────────────────────────────────────

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


def fake_session(state="AWAITING_TIME", **ctx):
    base = {"customer_id": str(uuid.uuid4()), "customer_name": "Maria"}
    base.update(ctx)
    return SimpleNamespace(id=uuid.uuid4(), state=state, context=base)


def _bs(state="AWAITING_TIME", ctx=None, channel="whatsapp"):
    """BookingSession stub com os campos que o pipeline do bot usa."""
    return SimpleNamespace(
        id=uuid.uuid4(), company_id=COMPANY_ID, channel=channel,
        company_timezone=TZ, state=state, context=dict(ctx or {}),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        last_action=None, last_action_at=None,
        customer_id=uuid.uuid4(), appointment_id=None,
    )


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


def _day_slot_options(counts=(6, 12, 6)):
    """SlotOption de um dia denso (fuso SP): manhã 9h-, tarde 12h-, noite 18h-.

    Espelha a agenda densa do dev (F2): {manhã 6, tarde 12, noite 6} = 24 slots.
    row_key segue a enumeração 1-based do dia inteiro (como list_available_slots).
    """
    m, t, n = counts
    out, i = [], 0

    def _add(hour0, k):
        nonlocal i
        for j in range(k):
            start = datetime(2026, 7, 20, hour0, 0, tzinfo=SP) + timedelta(minutes=30 * j)
            i += 1
            out.append(SlotOption(
                start_at=start, end_at=start + timedelta(minutes=30),
                professional_id=PROF_ID, professional_name="Maria Dev",
                row_key=f"slot_{i}",
            ))

    _add(9, m)    # manhã: 09:00..11:30
    _add(12, t)   # tarde: 12:00..17:30
    _add(18, n)   # noite: 18:00..20:30
    return out


def _slot_dicts(slot_options):
    return [
        {
            "start_at":          s.start_at.isoformat(),
            "end_at":            s.end_at.isoformat(),
            "professional_id":   str(s.professional_id),
            "professional_name": s.professional_name,
            "row_key":           s.row_key,
        }
        for s in slot_options
    ]


_SHIFT_DICTS = [
    {"shift": "manha", "label": "Manhã", "slot_count": 6,
     "has_availability": True,  "row_key": "manha"},
    {"shift": "tarde", "label": "Tarde", "slot_count": 12,
     "has_availability": True,  "row_key": "tarde"},
    {"shift": "noite", "label": "Noite", "slot_count": 0,
     "has_availability": False, "row_key": "noite"},
]


def _shift_options(dicts=_SHIFT_DICTS):
    return [
        ShiftOption(shift=d["shift"], label=d["label"], slot_count=d["slot_count"],
                    has_availability=d["has_availability"], row_key=d["row_key"])
        for d in dicts
    ]


# ─── Parser: menu de turnos (sub-estado AWAITING_SHIFT) ───────────────────────

class TestShiftParser:
    CTX = {"last_listed_shifts": list(_SHIFT_DICTS)}

    def test_numbers_mirror_displayed_rows(self):
        parse = whatsapp_input_parser.parse
        assert parse("1", "AWAITING_SHIFT", self.CTX, TZ) == \
            (BookingAction.SELECT_SHIFT, {"row_key": "manha"})
        assert parse("2", "AWAITING_SHIFT", self.CTX, TZ) == \
            (BookingAction.SELECT_SHIFT, {"row_key": "tarde"})
        # indisponível ainda resolve — a camada rejeita com feedback amigável
        assert parse("3", "AWAITING_SHIFT", self.CTX, TZ) == \
            (BookingAction.SELECT_SHIFT, {"row_key": "noite"})
        assert parse("4", "AWAITING_SHIFT", self.CTX, TZ) == (BookingAction.BACK, {})
        assert parse("5", "AWAITING_SHIFT", self.CTX, TZ) is None

    def test_rowid_resolves(self):
        assert whatsapp_input_parser.parse("tarde", "AWAITING_SHIFT", self.CTX, TZ) == \
            (BookingAction.SELECT_SHIFT, {"row_key": "tarde"})

    def test_poll_vote_titles_mirror_formatter(self):
        parse = whatsapp_input_parser.parse
        assert parse("Manhã (6 horários)", "AWAITING_SHIFT", self.CTX, TZ) == \
            (BookingAction.SELECT_SHIFT, {"row_key": "manha"})
        assert parse("Tarde (12 horários)", "AWAITING_SHIFT", self.CTX, TZ) == \
            (BookingAction.SELECT_SHIFT, {"row_key": "tarde"})
        assert parse("Noite — indisponível", "AWAITING_SHIFT", self.CTX, TZ) == \
            (BookingAction.SELECT_SHIFT, {"row_key": "noite"})

    def test_singular_count_title(self):
        ctx = {"last_listed_shifts": [
            {"shift": "manha", "label": "Manhã", "slot_count": 1,
             "has_availability": True, "row_key": "manha"},
        ]}
        assert whatsapp_input_parser.parse("Manhã (1 horário)", "AWAITING_SHIFT", ctx, TZ) == \
            (BookingAction.SELECT_SHIFT, {"row_key": "manha"})

    def test_voltar_word_is_back(self):
        assert whatsapp_input_parser.parse("voltar", "AWAITING_SHIFT", self.CTX, TZ) == \
            (BookingAction.BACK, {})

    def test_empty_ctx_returns_none(self):
        assert whatsapp_input_parser.parse("1", "AWAITING_SHIFT", {}, TZ) is None


# ─── Alinhamento formatter × parser no menu de turnos ─────────────────────────

def test_formatter_parser_alignment_shifts(captured):
    ctx = {"last_listed_shifts": list(_SHIFT_DICTS)}
    result = SimpleNamespace(next_state="AWAITING_SHIFT", options=_shift_options(),
                             error=None, confirmation_data=None)
    whatsapp_response_formatter.format_and_send(result, "inst", "5511999", ctx, TZ)

    kind, _title, rows = captured[-1]
    assert kind == "list"
    assert [r["rowId"] for r in rows] == ["manha", "tarde", "noite", "nav_voltar"]
    assert rows[0]["title"] == "Manhã (6 horários)"
    assert rows[1]["title"] == "Tarde (12 horários)"
    assert rows[2]["title"] == "Noite — indisponível"
    assert rows[3]["title"] == "← Voltar"

    # digitar o número da linha N (ou votar no título exato) resolve a linha N
    for i, row in enumerate(rows):
        for user_input in (str(i + 1), row["title"]):
            parsed = whatsapp_input_parser.parse(user_input, "AWAITING_SHIFT", ctx, TZ)
            if row["rowId"] == "nav_voltar":
                assert parsed == (BookingAction.BACK, {})
            else:
                assert parsed == (BookingAction.SELECT_SHIFT, {"row_key": row["rowId"]})


# ─── Contagens derivadas da lista entregue (invariante F2) ────────────────────

class TestShiftCounts:
    def test_counts_derived_from_delivered_list(self):
        slots = _day_slot_options((6, 12, 6))
        opts = bot_service._shift_options_from_slots(slots, TZ)
        assert [(o.shift, o.slot_count, o.has_availability) for o in opts] == [
            ("manha", 6, True), ("tarde", 12, True), ("noite", 6, True),
        ]
        # contagem == lista filtrada pela MESMA primitiva que exibirá os slots
        for o in opts:
            filtered = BookingEngine._filter_slots_by_shift(slots, o.shift, SP)
            assert o.slot_count == len(filtered)

    def test_empty_shift_has_no_availability(self):
        opts = bot_service._shift_options_from_slots(_day_slot_options((6, 12, 0)), TZ)
        noite = opts[2]
        assert noite.shift == "noite"
        assert noite.slot_count == 0
        assert noite.has_availability is False

    def test_counts_sum_equals_delivered_total(self):
        slots = _day_slot_options((6, 12, 6))
        opts = bot_service._shift_options_from_slots(slots, TZ)
        assert sum(o.slot_count for o in opts) == len(slots)


# ─── bot_service: entrada no sub-estado após SELECT_DATE ─────────────────────

def _dates_ctx():
    return {"last_listed_dates": [
        {"row_key": "date_1", "label": "Hoje (20/07)",
         "has_availability": True, "date": "2026-07-20"},
    ]}


def test_select_date_enters_shift_substate(captured, monkeypatch):
    slots = _day_slot_options((6, 12, 6))
    bs = _bs(state="AWAITING_DATE", ctx=_dates_ctx())
    db = FakeDB({BookingSession: [bs]})
    session = fake_session(state="AWAITING_DATE", booking_session_id=str(bs.id))

    def _update(db_, bs_, action, payload):
        assert action == BookingAction.SELECT_DATE
        bs_.state = "AWAITING_TIME"
        ctx2 = dict(bs_.context)
        ctx2["selected_date"] = "2026-07-20"
        ctx2["last_listed_slots"] = _slot_dicts(slots)
        bs_.context = ctx2
        return SimpleNamespace(next_state="AWAITING_TIME", options=slots,
                               error=None, confirmation_data=None)

    monkeypatch.setattr(booking_engine, "update", _update)

    bot_service._handle_booking_state(
        db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "1", TZ,
    )

    # FSM permanece em AWAITING_TIME; sub-estado só no context (D1)
    assert bs.state == "AWAITING_TIME"
    assert session.state == "AWAITING_TIME"
    assert bs.context[bot_service.BOT_SUBSTATE_KEY] == bot_service.SUBSTATE_SHIFT
    listed = bs.context["last_listed_shifts"]
    assert [(s["shift"], s["slot_count"]) for s in listed] == \
        [("manha", 6), ("tarde", 12), ("noite", 6)]

    kind, title, rows = captured[-1]
    assert kind == "list"
    assert title == "Qual período prefere?"
    assert [r["rowId"] for r in rows] == ["manha", "tarde", "noite", "nav_voltar"]


def test_select_date_without_slots_skips_substate(captured, monkeypatch):
    """Dia sem slots → SEM_HORARIOS normal, sem menu de turnos."""
    bs = _bs(state="AWAITING_DATE", ctx=_dates_ctx())
    db = FakeDB({BookingSession: [bs]})
    session = fake_session(state="AWAITING_DATE", booking_session_id=str(bs.id))

    def _update(db_, bs_, action, payload):
        bs_.state = "AWAITING_TIME"
        return SimpleNamespace(next_state="AWAITING_TIME", options=[],
                               error=None, confirmation_data=None)

    monkeypatch.setattr(booking_engine, "update", _update)

    bot_service._handle_booking_state(
        db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "1", TZ,
    )

    assert bot_service.BOT_SUBSTATE_KEY not in (bs.context or {})
    assert captured[-1] == ("text", messages.SEM_HORARIOS)


# ─── bot_service: escolha de turno (100% na camada, sem update()) ────────────

def _substate_ctx(slots, shift_dicts=None):
    return {
        "service_id":         str(SERVICE_ID),
        "professional_id":    None,
        "professional_name":  "Qualquer disponível",
        "selected_date":      "2026-07-20",
        bot_service.BOT_SUBSTATE_KEY: bot_service.SUBSTATE_SHIFT,
        "last_listed_shifts": list(shift_dicts if shift_dicts is not None
                                   else _SHIFT_DICTS),
        "last_listed_slots":  _slot_dicts(slots),
    }


def _forbid_update(monkeypatch, reason):
    def _boom(*a, **k):
        raise AssertionError(reason)
    monkeypatch.setattr(booking_engine, "update", _boom)


def test_shift_choice_filters_slots_without_engine_update(captured, monkeypatch):
    monkeypatch.setattr(settings, "BOT_MAX_SLOTS_DISPLAYED", 6)
    slots = _day_slot_options((6, 12, 6))
    bs = _bs(ctx=_substate_ctx(slots))
    db = FakeDB({BookingSession: [bs]})
    session = fake_session(booking_session_id=str(bs.id))

    _forbid_update(monkeypatch, "escolha de turno não deve passar por engine.update()")
    monkeypatch.setattr(booking_engine, "list_available_slots", lambda *a, **k: slots)

    bot_service._handle_booking_state(
        db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "2", TZ,  # 2 = Tarde
    )

    # FSM nunca saiu de AWAITING_TIME; sub-estado consumido
    assert bs.state == "AWAITING_TIME"
    assert session.state == "AWAITING_TIME"
    assert bot_service.BOT_SUBSTATE_KEY not in bs.context
    assert bs.context["selected_shift"] == "tarde"
    assert bs.last_action == BookingAction.SELECT_SHIFT.value

    # last_listed_slots agora só tem os 12 da tarde (12h ≤ hora local < 18h)
    stored = bs.context["last_listed_slots"]
    assert len(stored) == 12
    for s in stored:
        hour = datetime.fromisoformat(s["start_at"]).astimezone(SP).hour
        assert 12 <= hour < 18

    # exibição paginada DENTRO do turno: 6 slots + "Mais tarde →" + "← Voltar"
    kind, _title, rows = captured[-1]
    assert kind == "list"
    slot_rows = [r for r in rows if r["rowId"].startswith("slot_")]
    assert len(slot_rows) == 6
    assert rows[-2]["rowId"] == "nav_mais_tarde"
    assert rows[-1]["rowId"] == "nav_voltar"


def test_number_alignment_inside_filtered_shift(monkeypatch):
    """F3×F4: número digitado = linha exibida DENTRO do turno filtrado."""
    monkeypatch.setattr(settings, "BOT_MAX_SLOTS_DISPLAYED", 6)
    slots = _day_slot_options((6, 12, 6))
    filtered = BookingEngine._filter_slots_by_shift(slots, "tarde", SP)
    assert [s.row_key for s in filtered] == [f"slot_{i}" for i in range(7, 19)]

    parse = whatsapp_input_parser.parse

    # página 1: linhas 1..6 = 6 primeiros da tarde, 7 = "Mais tarde →", 8 = Voltar
    ctx = {"last_listed_slots": _slot_dicts(filtered)}
    for n in range(1, 7):
        assert parse(str(n), "AWAITING_TIME", ctx, TZ) == \
            (BookingAction.SELECT_TIME, {"row_key": filtered[n - 1].row_key})
    assert parse("7", "AWAITING_TIME", ctx, TZ) == (BookingAction.MORE_SLOTS_LATER, {})
    assert parse("8", "AWAITING_TIME", ctx, TZ) == (BookingAction.BACK, {})

    # página 2: linha 1 = "← Mais cedo", 2..7 = slots 7..12 da tarde, 8 = Voltar
    ctx2 = {"last_listed_slots": _slot_dicts(filtered), "slot_offset": 6}
    assert parse("1", "AWAITING_TIME", ctx2, TZ) == (BookingAction.MORE_SLOTS_EARLIER, {})
    for n in range(2, 8):
        assert parse(str(n), "AWAITING_TIME", ctx2, TZ) == \
            (BookingAction.SELECT_TIME, {"row_key": filtered[n + 4].row_key})
    assert parse("8", "AWAITING_TIME", ctx2, TZ) == (BookingAction.BACK, {})


def test_unavailable_shift_gives_feedback_and_redisplays(captured, monkeypatch):
    slots = _day_slot_options((6, 12, 0))   # noite vazia
    shift_dicts = [
        dict(_SHIFT_DICTS[0]),
        dict(_SHIFT_DICTS[1]),
        {"shift": "noite", "label": "Noite", "slot_count": 0,
         "has_availability": False, "row_key": "noite"},
    ]
    bs = _bs(ctx=_substate_ctx(slots, shift_dicts))
    db = FakeDB({BookingSession: [bs]})
    session = fake_session(booking_session_id=str(bs.id))

    _forbid_update(monkeypatch, "turno esgotado não deve passar por engine.update()")
    monkeypatch.setattr(booking_engine, "list_available_slots", lambda *a, **k: slots)
    monkeypatch.setattr(booking_engine, "get_shift_availability",
                        lambda *a, **k: _shift_options(shift_dicts))

    bot_service._handle_booking_state(
        db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "3", TZ,  # 3 = Noite
    )

    # feedback amigável + menu de turnos re-exibido; sub-estado preservado
    texts = [t for kind, *rest in captured if kind == "text" for t in rest]
    assert any("noite" in t for t in texts)
    assert bs.context[bot_service.BOT_SUBSTATE_KEY] == bot_service.SUBSTATE_SHIFT
    assert "selected_shift" not in bs.context
    kind, title, rows = captured[-1]
    assert kind == "list"
    assert title == "Qual período prefere?"
    assert rows[2]["title"] == "Noite — indisponível"


def test_gibberish_in_substate_keeps_substate(captured, monkeypatch):
    slots = _day_slot_options((6, 12, 6))
    bs = _bs(ctx=_substate_ctx(slots))
    db = FakeDB({BookingSession: [bs]})
    session = fake_session(booking_session_id=str(bs.id))
    _forbid_update(monkeypatch, "input não reconhecido não deve chegar ao engine")

    bot_service._handle_booking_state(
        db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "xyzzy", TZ,
    )

    assert captured[-1] == ("text", messages.ESCOLHA_OPCAO_OPS)
    assert bs.context[bot_service.BOT_SUBSTATE_KEY] == bot_service.SUBSTATE_SHIFT


def test_shift_choice_on_expired_session_resets_to_menu(captured, monkeypatch):
    slots = _day_slot_options((6, 12, 6))
    bs = _bs(ctx=_substate_ctx(slots))
    bs.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db = FakeDB({BookingSession: [bs]})
    session = fake_session(booking_session_id=str(bs.id))

    _forbid_update(monkeypatch, "sessão expirada não deve chegar ao engine")
    menu_calls = []
    monkeypatch.setattr(h_inicio, "show_menu_principal",
                        lambda *a, **k: menu_calls.append(a))

    bot_service._handle_booking_state(
        db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "2", TZ,
    )

    assert len(menu_calls) == 1
    assert "selected_shift" not in (bs.context or {})


# ─── BACK: turno → data; horários filtrados → turno (F3×F4) ──────────────────

def test_back_in_shift_menu_goes_to_date_via_engine(captured, monkeypatch):
    slots = _day_slot_options((6, 12, 6))
    bs = _bs(ctx=_substate_ctx(slots))
    db = FakeDB({BookingSession: [bs]})
    session = fake_session(booking_session_id=str(bs.id))

    engine_calls = []

    def _update(db_, bs_, action, payload):
        engine_calls.append((action, payload))
        bs_.state = "AWAITING_DATE"
        return SimpleNamespace(next_state="AWAITING_DATE", options=[],
                               error=None, confirmation_data=None,
                               dates_has_next=False, dates_has_previous=False)

    monkeypatch.setattr(booking_engine, "update", _update)
    formatter_calls = []
    monkeypatch.setattr(whatsapp_response_formatter, "format_and_send",
                        lambda *a, **k: formatter_calls.append(a))

    bot_service._handle_booking_state(
        db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "voltar", TZ,
    )

    assert engine_calls == [(BookingAction.BACK, {})]
    assert session.state == "AWAITING_DATE"
    # sub-estado desfeito antes do BACK ir ao engine
    assert bot_service.BOT_SUBSTATE_KEY not in bs.context
    assert "last_listed_shifts" not in bs.context
    assert len(formatter_calls) == 1


def test_back_numbered_row_in_shift_menu_also_goes_to_date(captured, monkeypatch):
    """A linha '← Voltar' numerada (4) equivale a 'voltar' digitado."""
    slots = _day_slot_options((6, 12, 6))
    bs = _bs(ctx=_substate_ctx(slots))
    db = FakeDB({BookingSession: [bs]})
    session = fake_session(booking_session_id=str(bs.id))

    engine_calls = []

    def _update(db_, bs_, action, payload):
        engine_calls.append(action)
        bs_.state = "AWAITING_DATE"
        return SimpleNamespace(next_state="AWAITING_DATE", options=[],
                               error=None, confirmation_data=None,
                               dates_has_next=False, dates_has_previous=False)

    monkeypatch.setattr(booking_engine, "update", _update)
    monkeypatch.setattr(whatsapp_response_formatter, "format_and_send",
                        lambda *a, **k: None)

    bot_service._handle_booking_state(
        db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "4", TZ,
    )

    assert engine_calls == [BookingAction.BACK]
    assert session.state == "AWAITING_DATE"


def test_back_on_filtered_times_returns_to_shift_menu(captured, monkeypatch):
    """BACK na lista de horários (dentro de um turno) → menu de turnos,
    NÃO direto para a data — e sem passar pelo engine."""
    slots = _day_slot_options((6, 12, 6))
    filtered = BookingEngine._filter_slots_by_shift(slots, "tarde", SP)
    ctx = {
        "service_id":         str(SERVICE_ID),
        "professional_id":    None,
        "selected_date":      "2026-07-20",
        "selected_shift":     "tarde",
        "last_listed_shifts": list(_SHIFT_DICTS),
        "last_listed_slots":  _slot_dicts(filtered),
    }
    bs = _bs(ctx=ctx)
    db = FakeDB({BookingSession: [bs]})
    session = fake_session(booking_session_id=str(bs.id))

    _forbid_update(monkeypatch, "BACK dos horários filtrados resolve na camada")
    fresh_calls = []

    def _fresh(*a, **k):
        fresh_calls.append(a)
        return _shift_options()

    monkeypatch.setattr(booking_engine, "get_shift_availability", _fresh)

    bot_service._handle_booking_state(
        db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "voltar", TZ,
    )

    assert len(fresh_calls) == 1          # contagens frescas (stateless)
    assert bs.context[bot_service.BOT_SUBSTATE_KEY] == bot_service.SUBSTATE_SHIFT
    assert "selected_shift" not in bs.context
    assert bs.state == "AWAITING_TIME"    # FSM intocado
    kind, title, rows = captured[-1]
    assert kind == "list"
    assert title == "Qual período prefere?"


def test_back_on_times_without_shift_falls_through_to_engine(captured, monkeypatch):
    """Sessão sem selected_shift (ex.: anterior ao F4) → BACK segue ao engine
    (AWAITING_TIME → AWAITING_DATE), comportamento F3 preservado."""
    slots = _day_slot_options((6, 12, 6))
    ctx = {"service_id": str(SERVICE_ID), "selected_date": "2026-07-20",
           "last_listed_slots": _slot_dicts(slots)}
    bs = _bs(ctx=ctx)
    db = FakeDB({BookingSession: [bs]})
    session = fake_session(booking_session_id=str(bs.id))

    engine_calls = []

    def _update(db_, bs_, action, payload):
        engine_calls.append(action)
        bs_.state = "AWAITING_DATE"
        return SimpleNamespace(next_state="AWAITING_DATE", options=[],
                               error=None, confirmation_data=None,
                               dates_has_next=False, dates_has_previous=False)

    monkeypatch.setattr(booking_engine, "update", _update)
    monkeypatch.setattr(whatsapp_response_formatter, "format_and_send",
                        lambda *a, **k: None)

    bot_service._handle_booking_state(
        db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "voltar", TZ,
    )

    assert engine_calls == [BookingAction.BACK]
    assert session.state == "AWAITING_DATE"


# ─── Conflito de confirm re-entra no sub-estado de turno ─────────────────────

def test_confirm_conflict_reenters_shift_menu(captured, monkeypatch):
    slots = _day_slot_options((6, 12, 6))
    bs = _bs(state="AWAITING_CONFIRMATION",
             ctx={"service_id": str(SERVICE_ID), "selected_date": "2026-07-20",
                  "selected_shift": "tarde"})
    db = FakeDB({BookingSession: [bs]})
    session = fake_session(state="AWAITING_CONFIRMATION", booking_session_id=str(bs.id))

    def _update(db_, bs_, action, payload):
        assert action == BookingAction.CONFIRM
        bs_.state = "AWAITING_TIME"
        return SimpleNamespace(next_state="AWAITING_TIME", options=slots,
                               error="SLOT_UNAVAILABLE", confirmation_data=None)

    monkeypatch.setattr(booking_engine, "update", _update)

    bot_service._handle_booking_state(
        db, session, COMPANY_ID, "inst", "5511999@s.whatsapp.net", "confirmar", TZ,
    )

    texts = [t for kind, *rest in captured if kind == "text" for t in rest]
    assert messages.HORARIO_OCUPADO_CONFIRMANDO in texts
    assert texts.count(messages.HORARIO_OCUPADO_CONFIRMANDO) == 1
    assert bs.context[bot_service.BOT_SUBSTATE_KEY] == bot_service.SUBSTATE_SHIFT
    assert "selected_shift" not in bs.context   # nova escolha de turno pendente
    kind, title, rows = captured[-1]
    assert kind == "list"
    assert title == "Qual período prefere?"
    assert session.state == "AWAITING_TIME"


# ─── Canal WEB protegido — o FSM não conhece o turno ──────────────────────────

def _make_web_session(state, ctx=None):
    session = MagicMock()
    session.id = uuid.uuid4()
    session.company_id = COMPANY_ID
    session.channel = "web"
    session.company_timezone = TZ
    session.state = state
    session.context = ctx or {}
    session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    session.last_action = None
    session.last_action_at = None
    session.customer_id = None
    session.appointment_id = None
    return session


class TestWebChannelUntouched:
    def test_fsm_has_no_shift_state_or_action(self):
        for (st, act) in BookingEngine._VALID_TRANSITIONS:
            assert st != "AWAITING_SHIFT"
            assert act != BookingAction.SELECT_SHIFT
        assert "AWAITING_SHIFT" not in _BACK_STATE

    def test_web_select_date_goes_straight_to_full_day(self):
        """O teste que protege o canal web: DATE → TIME direto, dia inteiro,
        sem turno e sem chaves de sub-estado no contexto."""
        engine = BookingEngine()
        db = MagicMock()
        slots = _day_slot_options((6, 12, 6))
        session = _make_web_session("AWAITING_DATE", {
            "service_id": str(SERVICE_ID),
            "professional_id": str(PROF_ID),
        })

        with patch.object(engine, "list_available_slots", return_value=slots):
            result = engine.update(
                db, session, BookingAction.SELECT_DATE, {"date": "2026-07-20"},
            )

        assert result.next_state == "AWAITING_TIME"
        assert session.state == "AWAITING_TIME"
        assert len(result.options) == 24            # dia inteiro, sem filtro
        assert "bot_substate" not in session.context
        assert "last_listed_shifts" not in session.context
        assert "selected_shift" not in session.context

    def test_web_select_shift_via_update_remains_invalid(self):
        engine = BookingEngine()
        db = MagicMock()
        session = _make_web_session("AWAITING_TIME", {
            "service_id": str(SERVICE_ID),
            "selected_date": "2026-07-20",
        })
        with pytest.raises(InvalidActionError):
            engine.update(db, session, BookingAction.SELECT_SHIFT, {"shift": "tarde"})


# ─── get_shift_availability é stateless ───────────────────────────────────────

def test_get_shift_availability_is_stateless():
    import inspect
    params = inspect.signature(BookingEngine.get_shift_availability).parameters
    assert "session" not in params   # não recebe sessão — não pode mutá-la

    engine = BookingEngine()
    db = MagicMock()
    with patch.object(engine, "list_available_slots",
                      return_value=_day_slot_options((6, 12, 6))):
        opts = engine.get_shift_availability(
            db, COMPANY_ID, None, SERVICE_ID, date(2026, 7, 20),
            company_timezone=TZ,
        )
    assert [(o.shift, o.slot_count) for o in opts] == \
        [("manha", 6), ("tarde", 12), ("noite", 6)]
