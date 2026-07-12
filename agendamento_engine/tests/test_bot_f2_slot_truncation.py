"""
F2 — truncamentos residuais de horário (3 pontos).

1. Re-listagem pós-conflito (_handle_confirm → SLOT_UNAVAILABLE) usa limit=0:
   um limite gravaria uma lista truncada em last_listed_slots, que a paginação
   reutiliza pelo resto da sessão (mesmo bug corrigido no 7ebde4a, reintroduzido).
2. Caminho legado (escolhendo_horario) busca o dia inteiro (limit=0): a contagem
   por turno (get_shift_availability) é sobre o dia inteiro — um pool truncado
   fazia o menu prometer horários que a lista filtrada não entregava.
3. list_next_available_slots ("qualquer profissional") ordena cronologicamente
   (e deduplica) ANTES de truncar — o corte preserva os mais próximos.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.modules.booking import engine as engine_mod
from app.modules.booking.engine import booking_engine
from app.modules.booking.exceptions import SlotUnavailableError
from app.modules.whatsapp.handlers import escolhendo_horario


def _slot(prof_id, prof_name, hour, day=1):
    """AvailableSlot mínimo (UTC tz-aware, hora cheia)."""
    return SimpleNamespace(
        start_at=datetime(2026, 7, day, hour, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 7, day, hour, 30, tzinfo=timezone.utc),
        professional_id=prof_id,
        professional_name=prof_name,
    )


def _patch_two_profs_dense_day(monkeypatch):
    """
    Agenda densa com manhã, tarde E noite (2 profissionais):
      Ana: 9,10,11,14,15,18,19    Bia: 14,15,16,17,19,20
    União única = 9,10,11 | 14,15,16,17 | 18,19,20
    → manhã=3, tarde=4, noite=3 (10 horários).
    """
    p1, p2 = uuid4(), uuid4()

    def fake_list_by_service(db, company_id, service_id):
        return [SimpleNamespace(id=p1, name="Ana"), SimpleNamespace(id=p2, name="Bia")]

    def fake_get_available_slots(db, company_id, professional_id, service_id, target_date):
        if professional_id == p1:
            return [_slot(p1, "Ana", h) for h in (9, 10, 11, 14, 15, 18, 19)]
        return [_slot(p2, "Bia", h) for h in (14, 15, 16, 17, 19, 20)]

    monkeypatch.setattr(engine_mod.professional_svc, "list_by_service", fake_list_by_service)
    monkeypatch.setattr(engine_mod.availability_svc, "get_available_slots", fake_get_available_slots)
    return p1, p2


# ── PONTO 1: re-listagem pós-conflito com limit=0 ────────────────────────────

def test_conflict_relist_uses_limit_zero_and_records_full_day(monkeypatch):
    captured = {}
    prof_id, svc_id = uuid4(), uuid4()
    full_day = [_slot(prof_id, "Ana", h) for h in (9, 10, 11, 12, 14, 15, 16, 17, 18, 19)]
    for i, s in enumerate(full_day):
        s.row_key = f"slot_{i + 1}"

    def fake_list_available_slots(db, company_id, professional_id, service_id,
                                  target_date, limit=None, company_timezone=None):
        captured["limit"] = limit
        return full_day

    def fake_confirm(db, company_id, intent):
        raise SlotUnavailableError("tomado")

    monkeypatch.setattr(booking_engine, "list_available_slots", fake_list_available_slots)
    monkeypatch.setattr(booking_engine, "confirm", fake_confirm)
    monkeypatch.setattr(
        engine_mod.service_svc, "get_service_or_404",
        lambda db, cid, sid: SimpleNamespace(id=sid),
    )

    session = MagicMock()
    session.company_id = uuid4()
    session.company_timezone = "UTC"
    session.customer_id = uuid4()
    session.last_action = None
    session.appointment_id = None
    session.context = {
        "service_id": str(svc_id),
        "professional_id": str(prof_id),
        "slot_start_at": "2026-07-01T14:00:00+00:00",
        "idempotency_key": "k-f2",
        "selected_date": "2026-07-01",
    }

    result = booking_engine._handle_confirm(MagicMock(), session, {})

    assert result.error == "SLOT_UNAVAILABLE"
    assert result.next_state == "AWAITING_TIME"
    # Era limit=BOT_MAX_SLOTS_DISPLAYED (6) — truncava o resto da sessão
    assert captured["limit"] == 0
    # last_listed_slots grava o dia inteiro (a paginação percorre até a noite)
    assert len(session.context["last_listed_slots"]) == len(full_day)


# ── PONTO 2: contagem de turno == lista entregue ─────────────────────────────

def test_shift_count_matches_delivered_list(monkeypatch):
    _patch_two_profs_dense_day(monkeypatch)
    company_id, svc_id = uuid4(), uuid4()
    target = datetime(2026, 7, 1).date()

    counts = {
        o.shift: o.slot_count
        for o in booking_engine.get_shift_availability(
            None, company_id, None, svc_id, target, company_timezone="UTC",
        )
    }
    assert counts == {"manha": 3, "tarde": 4, "noite": 3}

    # Mesma fonte do caminho legado pós-fix: dia inteiro, limit=0
    slots = booking_engine.list_available_slots(
        None, company_id, None, svc_id, target, limit=0, company_timezone="UTC",
    )

    tz = ZoneInfo("UTC")
    for turno in ("manha", "tarde", "noite"):
        delivered = escolhendo_horario._filter_by_turno(slots, turno, tz)
        assert len(delivered) == counts[turno], (
            f"turno {turno}: menu promete {counts[turno]}, lista entrega {len(delivered)}"
        )


def test_legacy_date_path_fetches_whole_day_and_paginates(monkeypatch):
    captured = {}
    prof_id = uuid4()
    dense = [_slot(prof_id, "Ana", h) for h in range(8, 21)]  # 13 slots, 8h–20h

    def fake_list_available_slots(db, company_id, professional_id, service_id,
                                  target_date, limit=None, company_timezone="America/Sao_Paulo"):
        captured["limit"] = limit
        return dense

    monkeypatch.setattr(booking_engine, "list_available_slots", fake_list_available_slots)

    sent = {}
    monkeypatch.setattr(
        escolhendo_horario.sender, "send_list",
        lambda instance, to, title, desc, rows: sent.update(rows=rows),
    )
    monkeypatch.setattr(
        escolhendo_horario.sender, "send_buttons",
        lambda *a, **k: sent.update(buttons=True),
    )

    session = MagicMock()
    session.context = {
        "service_id": str(uuid4()),
        "service_name": "Corte",
        "professional_id": str(prof_id),
        "professional_name": "Ana",
        "selected_date": "2026-07-01",
        "company_timezone": "UTC",
    }

    escolhendo_horario.start(
        None, session, uuid4(), "inst", "5511999@s.whatsapp.net",
        send_escolher_data=MagicMock(), send_confirmacao_resumo=MagicMock(),
    )

    # Dia inteiro (era limit=pool=30, com viés de manhã no agregado)
    assert captured["limit"] == 0

    # A exibição continua paginada: n slots + "Mais tarde" + "outra data"
    n = settings.BOT_MAX_SLOTS_DISPLAYED
    rows = sent["rows"]
    slot_rows = [r for r in rows if "|" in r["rowId"]]
    assert len(slot_rows) == n
    assert any(r["rowId"] == "opt_mais_horarios" for r in rows)
    # O contexto guarda só a página exibida (payload protegido)
    assert len(session.context["last_list"]) == len(rows)


def test_legacy_turno_filter_delivers_promised_count(monkeypatch):
    """'Noite (3)' → escolher noite → 3 horários aparecem (numa página só)."""
    _patch_two_profs_dense_day(monkeypatch)

    sent = {}
    monkeypatch.setattr(
        escolhendo_horario.sender, "send_list",
        lambda instance, to, title, desc, rows: sent.update(rows=rows),
    )
    monkeypatch.setattr(
        escolhendo_horario.sender, "send_buttons",
        lambda *a, **k: sent.update(buttons=True),
    )

    session = MagicMock()
    session.context = {
        "service_id": str(uuid4()),
        "service_name": "Corte",
        "professional_id": None,          # "qualquer profissional"
        "selected_date": "2026-07-01",
        "selected_turno": "noite",
        "company_timezone": "UTC",
    }

    escolhendo_horario.start(
        None, session, uuid4(), "inst", "5511999@s.whatsapp.net",
        send_escolher_data=MagicMock(), send_confirmacao_resumo=MagicMock(),
    )

    rows = sent["rows"]
    slot_rows = [r for r in rows if "|" in r["rowId"]]
    # A união do dia tem 3 horários de noite (18,19,20) — todos entregues
    assert len(slot_rows) == 3
    assert not any(r["rowId"] == "opt_mais_horarios" for r in rows)


# ── PONTO 3: list_next_available_slots ordena antes de truncar ───────────────

def _patch_next_slots(monkeypatch, per_prof: dict):
    """per_prof: {prof_id: (nome, [horas])} — respeita o limit por profissional."""
    def fake_list_by_service(db, company_id, service_id):
        return [SimpleNamespace(id=pid, name=name) for pid, (name, _) in per_prof.items()]

    def fake_get_next(db, company_id, professional_id, service_id, days, limit):
        name, hours = per_prof[professional_id]
        return [_slot(professional_id, name, h) for h in hours][:limit]

    monkeypatch.setattr(engine_mod.professional_svc, "list_by_service", fake_list_by_service)
    monkeypatch.setattr(engine_mod.availability_svc, "get_next_available_slots", fake_get_next)


def test_next_slots_any_prof_chronological(monkeypatch):
    p1, p2 = uuid4(), uuid4()
    # Ana só tem tarde; Bia tem manhã — antes do fix a lista saía 14,15,16,8,9,10
    _patch_next_slots(monkeypatch, {
        p1: ("Ana", [14, 15, 16]),
        p2: ("Bia", [8, 9, 10]),
    })

    result = booking_engine.list_next_available_slots(
        None, uuid4(), None, uuid4(), days=7, limit=6, company_timezone="UTC",
    )

    starts = [s.start_at for s in result]
    assert starts == sorted(starts), "slots devem sair em ordem cronológica"
    assert [s.start_at.hour for s in result] == [8, 9, 10, 14, 15, 16]


def test_next_slots_truncation_keeps_nearest(monkeypatch):
    p1, p2, p3 = uuid4(), uuid4(), uuid4()
    # 3 profissionais × half=2 → 6 coletados, corte em 4.
    # Antes do fix: [14,15] + [9,10] → break → Caio descartado, lista fora de ordem.
    _patch_next_slots(monkeypatch, {
        p1: ("Ana", [14, 15]),
        p2: ("Bia", [9, 10]),
        p3: ("Caio", [11, 16]),
    })

    result = booking_engine.list_next_available_slots(
        None, uuid4(), None, uuid4(), days=7, limit=4, company_timezone="UTC",
    )

    # O corte preserva os 4 mais próximos cronologicamente (15h e 16h caem)
    assert [s.start_at.hour for s in result] == [9, 10, 11, 14]


def test_next_slots_dedup_one_slot_per_time(monkeypatch):
    p1, p2 = uuid4(), uuid4()
    _patch_next_slots(monkeypatch, {
        p1: ("Ana", [9, 10]),
        p2: ("Bia", [9, 14]),
    })

    result = booking_engine.list_next_available_slots(
        None, uuid4(), None, uuid4(), days=7, limit=6, company_timezone="UTC",
    )

    starts = [s.start_at for s in result]
    assert len(starts) == len(set(starts)), f"horários duplicados: {starts}"
    assert [s.start_at.hour for s in result] == [9, 10, 14]


def test_next_slots_single_prof_unchanged(monkeypatch):
    """Com profissional escolhido, delega direto com o limit efetivo."""
    p1 = uuid4()
    captured = {}

    def fake_get_next(db, company_id, professional_id, service_id, days, limit):
        captured["limit"] = limit
        return [_slot(p1, "Ana", h) for h in (9, 10)]

    monkeypatch.setattr(engine_mod.availability_svc, "get_next_available_slots", fake_get_next)

    result = booking_engine.list_next_available_slots(
        None, uuid4(), p1, uuid4(), days=7, limit=6, company_timezone="UTC",
    )

    assert captured["limit"] == 6
    assert [s.start_at.hour for s in result] == [9, 10]
