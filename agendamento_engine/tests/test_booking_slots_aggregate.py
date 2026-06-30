"""
Regressão: list_available_slots no caminho agregado (professional_id=None,
"qualquer profissional") truncava cada profissional a `half` slots mesmo com
limit=0, fazendo sumir os horários da tarde/noite na web E no bot.

Correção: com limit=0 coleta o dia inteiro de cada profissional e ordena
cronologicamente; com limit>0 mantém o corte para paginação.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.modules.booking import engine as engine_mod
from app.modules.booking.actions import BookingAction
from app.modules.booking.engine import booking_engine


def _slot(prof_id, prof_name, hour):
    """AvailableSlot mínimo (UTC tz-aware, hora cheia)."""
    return SimpleNamespace(
        start_at=datetime(2026, 7, 1, hour, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 7, 1, hour, 30, tzinfo=timezone.utc),
        professional_id=prof_id,
        professional_name=prof_name,
    )


def _patch_two_profs_full_day(monkeypatch):
    """
    2 profissionais com horários que se sobrepõem (14,15) e divergem:
      Ana: 9, 10, 11, 14, 15        Bia: 14, 15, 16, 17
    União cronológica única = 9,10,11,14,15,16,17 (7 horários).
    """
    p1, p2 = uuid4(), uuid4()

    def fake_list_by_service(db, company_id, service_id):
        return [SimpleNamespace(id=p1, name="Ana"), SimpleNamespace(id=p2, name="Bia")]

    def fake_get_available_slots(db, company_id, professional_id, service_id, target_date):
        if professional_id == p1:
            return [_slot(p1, "Ana", h) for h in (9, 10, 11, 14, 15)]
        return [_slot(p2, "Bia", h) for h in (14, 15, 16, 17)]

    monkeypatch.setattr(engine_mod.professional_svc, "list_by_service", fake_list_by_service)
    monkeypatch.setattr(engine_mod.availability_svc, "get_available_slots", fake_get_available_slots)
    return p1, p2


def test_aggregate_limit_zero_includes_afternoon(monkeypatch):
    _patch_two_profs_full_day(monkeypatch)

    result = booking_engine.list_available_slots(
        db=None, company_id=uuid4(), professional_id=None,
        service_id=uuid4(), target_date=datetime(2026, 7, 1).date(),
        limit=0, company_timezone="UTC",
    )

    hours = sorted({s.start_at.hour for s in result})
    # Tarde DEVE aparecer (antes da correção parava na manhã)
    assert 14 in hours and 17 in hours, f"tarde ausente: {hours}"
    # União dos dois profissionais, cada horário uma vez
    assert hours == [9, 10, 11, 14, 15, 16, 17]


def test_aggregate_dedup_one_slot_per_time(monkeypatch):
    _patch_two_profs_full_day(monkeypatch)

    result = booking_engine.list_available_slots(
        db=None, company_id=uuid4(), professional_id=None,
        service_id=uuid4(), target_date=datetime(2026, 7, 1).date(),
        limit=0, company_timezone="UTC",
    )

    starts = [s.start_at for s in result]
    # Sem horários repetidos, mesmo com 2 profissionais livres às 14 e 15
    assert len(starts) == len(set(starts)), f"horários duplicados: {starts}"
    assert len(result) == 7


def test_aggregate_limit_zero_is_chronological(monkeypatch):
    _patch_two_profs_full_day(monkeypatch)

    result = booking_engine.list_available_slots(
        db=None, company_id=uuid4(), professional_id=None,
        service_id=uuid4(), target_date=datetime(2026, 7, 1).date(),
        limit=0, company_timezone="UTC",
    )

    starts = [s.start_at for s in result]
    assert starts == sorted(starts), "slots devem vir em ordem cronológica"


def test_aggregate_load_balancing_picks_least_busy(monkeypatch):
    p1, p2 = _patch_two_profs_full_day(monkeypatch)
    # Ana(p1) com 5 agendamentos, Bia(p2) com 0 → Bia tem prioridade nos
    # horários em que ambos estão livres (14h e 15h).
    monkeypatch.setattr(
        booking_engine, "_professional_day_load",
        lambda db, cid, td, tz: {p1: 5, p2: 0},
    )

    result = booking_engine.list_available_slots(
        db=None, company_id=uuid4(), professional_id=None,
        service_id=uuid4(), target_date=datetime(2026, 7, 1).date(),
        limit=0, company_timezone="UTC",
    )

    by_hour = {s.start_at.hour: s.professional_id for s in result}
    # 14h: ambos livres → menos ocupado (Bia/p2)
    assert by_hour[14] == p2
    # 9h: só Ana tem → continua Ana
    assert by_hour[9] == p1


def test_select_time_sets_professional_name_on_context():
    """Após escolher um horário, o ctx guarda o nome real (não 'Qualquer disponível')."""
    prof_id = uuid4()
    start = datetime(2026, 7, 1, 14, 0, tzinfo=timezone.utc)
    session = MagicMock()
    session.company_id = uuid4()
    session.company_timezone = "UTC"
    session.customer_id = None
    session.context = {
        "service_id": str(uuid4()),
        "professional_id": None,
        "professional_name": "Qualquer disponível",   # rótulo da etapa anterior
        "last_listed_slots": [{
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(minutes=30)).isoformat(),
            "professional_id": str(prof_id),
            "professional_name": "Bia",
            "row_key": "slot_1",
        }],
    }

    booking_engine._handle_select_time(None, session, {"row_key": "slot_1"})

    assert session.context["professional_name"] == "Bia"
    assert session.context["professional_id"] == str(prof_id)


def test_aggregate_with_limit_still_caps(monkeypatch):
    _patch_two_profs_full_day(monkeypatch)

    result = booking_engine.list_available_slots(
        db=None, company_id=uuid4(), professional_id=None,
        service_id=uuid4(), target_date=datetime(2026, 7, 1).date(),
        limit=4, company_timezone="UTC",
    )

    assert len(result) == 4
