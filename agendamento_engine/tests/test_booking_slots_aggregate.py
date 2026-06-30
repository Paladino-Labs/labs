"""
Regressão: list_available_slots no caminho agregado (professional_id=None,
"qualquer profissional") truncava cada profissional a `half` slots mesmo com
limit=0, fazendo sumir os horários da tarde/noite na web E no bot.

Correção: com limit=0 coleta o dia inteiro de cada profissional e ordena
cronologicamente; com limit>0 mantém o corte para paginação.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.modules.booking import engine as engine_mod
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
    """2 profissionais, cada um com manhã (9,10,11) + tarde (14,15,16,17)."""
    p1, p2 = uuid4(), uuid4()

    def fake_list_by_service(db, company_id, service_id):
        return [SimpleNamespace(id=p1, name="Ana"), SimpleNamespace(id=p2, name="Bia")]

    def fake_get_available_slots(db, company_id, professional_id, service_id, target_date):
        name = "Ana" if professional_id == p1 else "Bia"
        return [_slot(professional_id, name, h) for h in (9, 10, 11, 14, 15, 16, 17)]

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
    # Todos os 7 horários dos 2 profissionais = 14 slots, sem truncar
    assert len(result) == 14


def test_aggregate_limit_zero_is_chronological(monkeypatch):
    _patch_two_profs_full_day(monkeypatch)

    result = booking_engine.list_available_slots(
        db=None, company_id=uuid4(), professional_id=None,
        service_id=uuid4(), target_date=datetime(2026, 7, 1).date(),
        limit=0, company_timezone="UTC",
    )

    starts = [s.start_at for s in result]
    assert starts == sorted(starts), "slots devem vir em ordem cronológica"


def test_aggregate_with_limit_still_caps(monkeypatch):
    _patch_two_profs_full_day(monkeypatch)

    result = booking_engine.list_available_slots(
        db=None, company_id=uuid4(), professional_id=None,
        service_id=uuid4(), target_date=datetime(2026, 7, 1).date(),
        limit=4, company_timezone="UTC",
    )

    assert len(result) == 4
