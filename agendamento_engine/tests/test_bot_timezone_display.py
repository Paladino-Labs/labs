"""
Hotfix F0 — exibição de horário no fuso da empresa (bot WhatsApp).

Trava a regressão do bug "+3h": pontos de exibição mostravam o horário UTC
cru ao cliente. A GRAVAÇÃO sempre foi UTC canônico e permanece intocada —
os testes cobrem os dois lados (string exibida local, instante persistido UTC).
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.modules.booking.engine import BookingEngine
from app.modules.booking.schemas import PredictiveOfferResult
from app.modules.whatsapp import helpers
from app.modules.whatsapp.handlers import cancelando
from app.modules.whatsapp.handlers import confirmando
from app.modules.whatsapp.handlers import gerenciando_agendamento
from app.modules.whatsapp.handlers import inicio

TZ_SP = "America/Sao_Paulo"

# 18:00 UTC = 15:00 em America/Sao_Paulo (UTC-3, sem DST desde 2019)
SLOT_UTC = datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc)
SLOT_UTC_ISO = SLOT_UTC.isoformat()          # "2026-07-10T18:00:00+00:00"


class _SenderRecorder:
    """Captura mensagens enviadas via sender.send_text/send_buttons/send_list."""

    def __init__(self, monkeypatch):
        self.texts: list[str] = []
        self.buttons: list[list[dict]] = []
        monkeypatch.setattr(
            "app.modules.whatsapp.sender.send_text",
            lambda instance, to, text: self.texts.append(text),
        )
        monkeypatch.setattr(
            "app.modules.whatsapp.sender.send_buttons",
            lambda instance, to, text, buttons: (
                self.texts.append(text), self.buttons.append(buttons),
            ),
        )
        monkeypatch.setattr(
            "app.modules.whatsapp.sender.send_list",
            lambda instance, to, title, desc, rows: self.texts.append(desc),
        )

    @property
    def all_text(self) -> str:
        button_labels = [
            b.get("buttonText", {}).get("displayText", "")
            for group in self.buttons for b in group
        ]
        return "\n".join(self.texts + button_labels)


def _session(ctx: dict) -> SimpleNamespace:
    return SimpleNamespace(context=dict(ctx), state="INICIO")


def _appt(start_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        start_at=start_at,
        services=[SimpleNamespace(service_id=uuid.uuid4(), service_name="Corte")],
        professional=SimpleNamespace(name="Hemerson"),
        professional_id=uuid.uuid4(),
    )


# ─── Helper canônico ──────────────────────────────────────────────────────────

def test_to_company_tz_converts_utc_to_local():
    local = helpers.to_company_tz(SLOT_UTC, TZ_SP)
    assert local.hour == 15
    assert local.day == 10
    assert local == SLOT_UTC  # mesmo instante


def test_to_company_tz_is_canonical_engine_helper():
    assert helpers.to_company_tz(SLOT_UTC, TZ_SP) == BookingEngine._to_company_tz(SLOT_UTC, TZ_SP)


# ─── label_date: "Hoje" derivado no fuso da empresa ──────────────────────────

def test_label_date_derives_today_in_company_tz(monkeypatch):
    # 01:30 UTC do dia 10 = 22:30 do dia 09 em São Paulo — o dia local NÃO virou
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 7, 10, 1, 30, tzinfo=timezone.utc)
            return fixed if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(helpers, "datetime", _FrozenDatetime)
    assert helpers.label_date(date(2026, 7, 9), TZ_SP) == "Hoje (09/07)"
    assert helpers.label_date(date(2026, 7, 10), TZ_SP) == "Amanhã (10/07)"


# ─── send_resumo (CONFIRMANDO) ────────────────────────────────────────────────

def test_send_resumo_displays_local_time_from_utc(monkeypatch):
    rec = _SenderRecorder(monkeypatch)
    ctx = {
        "slot_start_at": SLOT_UTC_ISO,
        "company_timezone": TZ_SP,
        "service_name": "Corte",
        "professional_name": "Hemerson",
    }
    confirmando.send_resumo("inst", "5562999999999@s.whatsapp.net", ctx)
    assert "15:00" in rec.all_text
    assert "18:00" not in rec.all_text
    assert "10/07/2026" in rec.all_text


def test_send_resumo_does_not_double_convert_local_aware(monkeypatch):
    # Fluxo normal grava slot_start_at já no fuso da empresa (aware -03:00):
    # a conversão deve ser no-op, nunca -3h de novo
    rec = _SenderRecorder(monkeypatch)
    ctx = {
        "slot_start_at": "2026-07-10T15:00:00-03:00",
        "company_timezone": TZ_SP,
        "service_name": "Corte",
        "professional_name": "Hemerson",
    }
    confirmando.send_resumo("inst", "5562999999999@s.whatsapp.net", ctx)
    assert "15:00" in rec.all_text
    assert "12:00" not in rec.all_text


# ─── GERENCIANDO_AGENDAMENTO / CANCELANDO ────────────────────────────────────

def _future_slot_utc() -> datetime:
    base = datetime.now(timezone.utc) + timedelta(days=30)
    return base.replace(hour=18, minute=0, second=0, microsecond=0)


def test_gerenciando_start_displays_local_time(monkeypatch):
    rec = _SenderRecorder(monkeypatch)
    session = _session({"company_timezone": TZ_SP})
    gerenciando_agendamento.start(
        None, session, uuid.uuid4(),
        "5562999999999@s.whatsapp.net", "inst", _appt(_future_slot_utc()),
    )
    assert "às 15:00" in rec.all_text
    assert "às 18:00" not in rec.all_text


def test_cancelando_start_displays_local_time(monkeypatch):
    rec = _SenderRecorder(monkeypatch)
    appt = _appt(_future_slot_utc())
    monkeypatch.setattr(
        cancelando.appointment_svc, "get_appointment_or_404",
        lambda db, cid, aid: appt,
    )
    session = _session({
        "company_timezone": TZ_SP,
        "managing_appointment_id": str(appt.id),
    })
    cancelando.start(
        None, session, uuid.uuid4(),
        "5562999999999@s.whatsapp.net", "inst",
        start_gerenciando_agendamento=lambda *a, **k: None,
    )
    assert "às 15:00" in rec.all_text
    assert "às 18:00" not in rec.all_text


# ─── Oferta preditiva (INICIO) — exibe local, persiste UTC ───────────────────

def test_predictive_offer_displays_local_and_persists_utc(monkeypatch):
    rec = _SenderRecorder(monkeypatch)
    customer = SimpleNamespace(id=uuid.uuid4(), name="João Silva", identity_id=uuid.uuid4())
    offer = PredictiveOfferResult(
        service_id=uuid.uuid4(),
        service_name="Corte",
        professional_id=uuid.uuid4(),
        professional_name="Hemerson",
        next_slot=SLOT_UTC,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    monkeypatch.setattr(inicio.customer_svc, "get_by_phone", lambda db, cid, phone: customer)
    monkeypatch.setattr(inicio.booking_engine, "get_customer_appointments", lambda db, cid, cust: [])
    monkeypatch.setattr(inicio.booking_engine, "get_predictive_offer", lambda *a, **k: offer)

    session = _session({"company_timezone": TZ_SP})
    inicio.handle(
        None, session, uuid.uuid4(),
        "5562999999999@s.whatsapp.net", "inst", "Barbearia Dev", "oi",
        start_escolhendo_servico=lambda *a, **k: None,
        handle_ver_agendamentos=lambda *a, **k: None,
        resolve_input=helpers.resolve_input,
    )

    # Exibição: hora local da empresa
    assert "10/07 às 15:00" in rec.all_text
    assert "às 18:00" not in rec.all_text
    # Persistência: UTC canônico byte a byte (gravação inalterada)
    assert session.context["predicted_slot"]["start_at"] == SLOT_UTC_ISO


# ─── CONFIRMANDO: gravação permanece o mesmo instante UTC ────────────────────

def test_confirm_persists_canonical_utc_and_displays_local(monkeypatch):
    rec = _SenderRecorder(monkeypatch)
    captured = {}
    monkeypatch.setattr(
        confirmando.booking_engine, "confirm",
        lambda db, cid, intent: captured.update(intent=intent),
    )
    session = _session({
        "slot_start_at": SLOT_UTC_ISO,
        "company_timezone": TZ_SP,
        "service_id": str(uuid.uuid4()),
        "service_name": "Corte",
        "professional_id": str(uuid.uuid4()),
        "professional_name": "Hemerson",
        "customer_id": str(uuid.uuid4()),
        "customer_name": "João Silva",
    })
    confirmando.handle(
        None, session, uuid.uuid4(),
        "5562999999999@s.whatsapp.net", "inst", "opt_confirmar",
        resolve_input=helpers.resolve_input,
        start_escolhendo_horario=lambda *a, **k: None,
    )

    intent = captured["intent"]
    # Gravação: o instante enviado ao engine é EXATAMENTE o UTC do contexto
    assert intent.start_at == SLOT_UTC
    assert intent.start_at.utcoffset() == timedelta(0)
    # Exibição: mensagem de confirmação mostra a hora local
    assert "às 15:00" in rec.all_text
    assert "às 18:00" not in rec.all_text
