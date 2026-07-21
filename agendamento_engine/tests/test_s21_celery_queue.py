"""S2.1 — Fila Celery: envio externo fora do request + webhook do bot fora do event loop.

Entrega A: create/reschedule/cancel/checkout enfileiram o envio em vez de
  chamá-lo síncrono no request.
Entrega B: o webhook do bot persiste + enfileira; o worker processa fora do
  event loop, serializado por conversa.

Estilo unitário com mocks (não exercita broker/Postgres reais), coerente com
o restante da suíte.
"""
import os
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest


def _raw(task):
    """Função crua da task, para injetar um `self` de teste (retries/max_retries).

    Robusto à contaminação de celery: vários testes da suíte substituem
    sys.modules["celery"] por um MagicMock cujo decorator `task` é no-op
    (`lambda f: f`). Se algum deles for coletado antes deste arquivo, as tasks
    já são funções cruas (sem __wrapped__). Cobrimos os dois casos.
    """
    wrapped = getattr(task, "__wrapped__", None)
    if wrapped is not None:
        return getattr(wrapped, "__func__", wrapped)
    return task  # celery mockado — a "task" já é a função crua


# ─────────────────────────────────────────────────────────────────────────────
# Entrega A — envio de comunicação fora do request
# ─────────────────────────────────────────────────────────────────────────────

def _fake_appointment():
    appt = MagicMock()
    appt.id = uuid4()
    appt.company_id = uuid4()
    return appt


def test_send_booking_confirmation_enqueues_with_correct_params():
    """DoD A.2 — a tarefa é enfileirada com event_type, IDs e manage_token."""
    from app.modules import notifications

    appt = _fake_appointment()
    with patch("app.workers.communication_worker.send_appointment_communication") as task:
        notifications.send_booking_confirmation(MagicMock(), appt, manage_token="tok-123")

    task.apply_async.assert_called_once()
    kwargs = task.apply_async.call_args.kwargs
    assert kwargs["args"] == [
        "appointment.confirmed", str(appt.id), str(appt.company_id), "tok-123",
    ]
    # retry=False: broker fora do ar falha rápido, não bloqueia o request.
    assert kwargs["retry"] is False


def test_send_reschedule_confirmation_enqueues():
    from app.modules import notifications

    appt = _fake_appointment()
    with patch("app.workers.communication_worker.send_appointment_communication") as task:
        notifications.send_reschedule_confirmation(MagicMock(), appt, manage_token=None)

    task.apply_async.assert_called_once()
    assert task.apply_async.call_args.kwargs["args"][0] == "appointment.confirmed"
    assert task.apply_async.call_args.kwargs["args"][3] is None


def test_enqueue_failure_does_not_propagate():
    """DoD A.3 — broker fora do ar não derruba a resposta ao cliente."""
    from app.modules import notifications

    appt = _fake_appointment()
    with patch("app.workers.communication_worker.send_appointment_communication") as task:
        task.apply_async.side_effect = RuntimeError("broker down")
        # não deve levantar
        notifications.send_booking_confirmation(MagicMock(), appt, manage_token="x")


def test_wrapper_does_not_dispatch_synchronously():
    """DoD A.1 — o wrapper NÃO chama CommunicationService.dispatch no request."""
    from app.modules import notifications

    appt = _fake_appointment()
    with patch("app.workers.communication_worker.send_appointment_communication"), \
         patch("app.modules.communication.service.communication_service.dispatch") as dispatch:
        notifications.send_booking_confirmation(MagicMock(), appt, manage_token="x")

    dispatch.assert_not_called()


def test_task_renders_manage_url_and_long_date():
    """A.1 (contrato) — a task ressuscitada monta manage_url + data por extenso,
    igual ao caminho vivo (sem divergência)."""
    from app.workers import communication_worker as cw

    company_id = str(uuid4())
    appt = MagicMock()
    appt.client_id = uuid4()
    # 5 de maio, 14:30 (naive → tratado como UTC pelo _localize)
    import datetime as _dt
    appt.start_at = _dt.datetime(2026, 5, 5, 14, 30)
    appt.professional = MagicMock(name="prof")
    appt.professional.name = "Alice"
    svc = MagicMock()
    svc.service_name = "Corte"
    appt.services = [svc]

    customer = MagicMock()
    customer.id = uuid4()
    customer.name = "Bob"
    customer.phone = "5511999999999"

    mock_db = MagicMock()
    # 1ª query = Appointment, 2ª = Customer
    appt_q = MagicMock()
    appt_q.filter.return_value.first.return_value = appt
    cust_q = MagicMock()
    cust_q.filter.return_value.first.return_value = customer
    mock_db.query.side_effect = [appt_q, cust_q]

    fake_self = MagicMock()
    with patch("app.workers.communication_worker.celery_db_session") as cds, \
         patch("app.modules.notifications._use_communication_service", return_value=True), \
         patch("app.modules.notifications._get_company_tz",
               return_value=__import__("zoneinfo").ZoneInfo("America/Sao_Paulo")), \
         patch("app.modules.appointments.manage_tokens.build_manage_url",
               return_value="https://x/manage/tok"), \
         patch("app.modules.communication.service.communication_service.dispatch") as dispatch:
        cds.return_value.__enter__.return_value = mock_db
        cds.return_value.__exit__.return_value = False
        _raw(cw.send_appointment_communication)(
            fake_self, "appointment.confirmed", str(uuid4()), company_id, "tok",
        )

    dispatch.assert_called_once()
    ctx = dispatch.call_args.kwargs["context"]
    assert ctx["manage_url"] == "https://x/manage/tok"
    assert ctx["data"] == "5 de maio"        # por extenso, não %d/%m
    assert ctx["recipient_phone"] == "5511999999999"


def test_task_dead_letter_on_exhausted_retries():
    """DoD A.3 — falha esgotada deixa rastro no dead-letter e re-levanta."""
    from app.workers import communication_worker as cw

    fake_self = MagicMock()
    fake_self.request.retries = 5
    fake_self.max_retries = 5
    fake_self.request.id = "task-1"

    mock_db = MagicMock()
    mock_db.query.side_effect = RuntimeError("db boom")

    with patch("app.workers.communication_worker.celery_db_session") as cds, \
         patch("app.workers.communication_worker._push_dead_letter") as dead_letter:
        cds.return_value.__enter__.return_value = mock_db
        cds.return_value.__exit__.return_value = False
        with pytest.raises(RuntimeError):
            _raw(cw.send_appointment_communication)(
                fake_self, "appointment.confirmed", str(uuid4()), str(uuid4()), None,
            )

    dead_letter.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Entrega A — waitlist do cancel/reschedule via fila
# ─────────────────────────────────────────────────────────────────────────────

def test_waitlist_handler_enqueues_per_scope():
    """DoD A.4 — cancel/reschedule enfileiram a notificação da fila por escopo."""
    from app.workers.handlers import waitlist_handler

    sid1, sid2, prof = str(uuid4()), str(uuid4()), str(uuid4())
    event = MagicMock()
    event.company_id = uuid4()
    event.event_type = "appointment.cancelled"
    event.payload = {"service_ids": [sid1, sid2], "professional_id": prof}

    with patch("app.workers.handlers.waitlist_handler.notify_waitlist_slot_available") as task:
        waitlist_handler.handle_appointment_cancelled_waitlist(event)

    assert task.apply_async.call_count == 3  # 2 serviços + 1 profissional
    scopes = [c.kwargs["args"][1] for c in task.apply_async.call_args_list]
    assert scopes.count("SERVICE") == 2
    assert scopes.count("PROFESSIONAL") == 1


def test_waitlist_handler_enqueue_failure_is_best_effort():
    from app.workers.handlers import waitlist_handler

    event = MagicMock()
    event.company_id = uuid4()
    event.event_type = "appointment.cancelled"
    event.payload = {"service_ids": [str(uuid4())], "professional_id": None}

    with patch("app.workers.handlers.waitlist_handler.notify_waitlist_slot_available") as task:
        task.apply_async.side_effect = RuntimeError("broker down")
        # não deve levantar (não derruba o cancel/reschedule)
        waitlist_handler.handle_appointment_cancelled_waitlist(event)


def test_notify_waitlist_task_maps_scope_to_service_id():
    from app.workers.handlers import waitlist_handler

    company = str(uuid4())
    svc = str(uuid4())
    fake_self = MagicMock()
    with patch("app.workers.handlers.waitlist_handler.celery_db_session") as cds, \
         patch("app.modules.waitlist.service.notify_waitlist") as notify:
        cds.return_value.__enter__.return_value = MagicMock()
        cds.return_value.__exit__.return_value = False
        _raw(waitlist_handler.notify_waitlist_slot_available)(
            fake_self, company, "SERVICE", svc, "appointment.cancelled",
        )

    notify.assert_called_once()
    kwargs = notify.call_args.kwargs
    assert kwargs["service_id"] == UUID(svc)
    assert kwargs["reason"] == "appointment.cancelled"


# ─────────────────────────────────────────────────────────────────────────────
# Entrega B — webhook do bot fora do event loop
# ─────────────────────────────────────────────────────────────────────────────

def test_webhook_persists_and_enqueues_with_dedup():
    """DoD B.4/B.7 — o webhook persiste (com ON CONFLICT p/ dedup) e enfileira
    o drain por conversa; não processa síncrono."""
    from sqlalchemy.dialects import postgresql

    from app.modules.whatsapp import router

    company = uuid4()
    conn = MagicMock()
    conn.company_id = company
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = conn

    captured = {}

    def _capture_execute(stmt, *a, **k):
        captured["stmt"] = stmt
        return MagicMock()

    mock_db.execute.side_effect = _capture_execute

    data = {"key": {"remoteJid": "5511@s.whatsapp.net", "id": "MSG1"},
            "message": {"conversation": "oi"}}
    with patch("app.workers.bot_inbound_worker.drain_bot_inbound") as task:
        router._persist_and_enqueue_inbound(mock_db, "inst", data)

    # persistiu com ON CONFLICT DO NOTHING (dedup durável)
    compiled = str(captured["stmt"].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in compiled.upper()
    mock_db.commit.assert_called()
    # enfileirou o drain da conversa (company_id + whatsapp_id), retry=False
    task.apply_async.assert_called_once()
    assert task.apply_async.call_args.kwargs["args"] == [str(company), "5511@s.whatsapp.net"]
    assert task.apply_async.call_args.kwargs["retry"] is False


def test_webhook_skips_group_message():
    from app.modules.whatsapp import router

    mock_db = MagicMock()
    with patch("app.workers.bot_inbound_worker.drain_bot_inbound") as task:
        router._persist_and_enqueue_inbound(
            mock_db, "inst", {"key": {"remoteJid": "123@g.us", "id": "x"}},
        )
    task.apply_async.assert_not_called()
    mock_db.execute.assert_not_called()


def test_webhook_no_connection_ignored():
    from app.modules.whatsapp import router

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    with patch("app.workers.bot_inbound_worker.drain_bot_inbound") as task:
        router._persist_and_enqueue_inbound(
            mock_db, "inst", {"key": {"remoteJid": "5511@s.whatsapp.net", "id": "M"}},
        )
    task.apply_async.assert_not_called()
    mock_db.execute.assert_not_called()


def test_webhook_returns_200_and_defers_processing():
    """DoD B.4 — o endpoint responde 200 sem processar (mock do get_db + drain)."""
    from fastapi.testclient import TestClient

    from app.infrastructure.db.session import get_db
    from app.main import app

    conn = MagicMock()
    conn.company_id = uuid4()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = conn
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        with patch("app.workers.bot_inbound_worker.drain_bot_inbound") as task, \
             patch("app.modules.whatsapp.bot_service.handle_inbound_message") as handle:
            client = TestClient(app)
            resp = client.post("/whatsapp/webhook", json={
                "event": "messages.upsert",
                "instance": "inst",
                "data": {"key": {"remoteJid": "5511@s.whatsapp.net", "id": "M1"},
                         "message": {"conversation": "oi"}},
            })
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        task.apply_async.assert_called_once()     # enfileirou
        handle.assert_not_called()                # NÃO processou síncrono
    finally:
        app.dependency_overrides.pop(get_db, None)


def _drain_row(payload, rid=None, attempts=0):
    row = MagicMock()
    row.id = rid or uuid4()
    row.instance_name = "inst"
    row.raw_payload = payload
    row.attempts = attempts
    return row


def _make_lease_db(claimed=True, orphans=None, renewed=1,
                   first_side_effect=None, get_side_effect=None):
    """mock_db que roteia db.execute por SQL: CLAIM/REAP/RENEW/RELEASE do lease.
    claimed=False → o claim devolve None (conversa ocupada por outro worker)."""
    mock_db = MagicMock()

    def _execute(stmt, params=None):
        s = str(stmt)
        r = MagicMock()
        if "INSERT INTO bot_conversation_leases" in s:            # claim
            r.fetchone.return_value = ("me",) if claimed else None
        elif "UPDATE bot_inbound_messages" in s:                  # reap órfãos
            r.fetchall.return_value = orphans or []
        elif "UPDATE bot_conversation_leases" in s:               # renew (fencing)
            r.rowcount = renewed
        else:                                                     # release (DELETE)
            r.rowcount = 1
        return r

    mock_db.execute.side_effect = _execute
    if first_side_effect is not None:
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.side_effect = first_side_effect
    if get_side_effect is not None:
        mock_db.get.side_effect = get_side_effect
    return mock_db


def test_drain_processes_received_in_order():
    """DoD B.5/B.6 — sob a lease, o drain processa as RECEIVED da conversa em
    ordem de chegada, chamando handle_inbound_message com o payload persistido."""
    from app.workers import bot_inbound_worker as biw

    row1 = _drain_row({"m": 1})
    row2 = _drain_row({"m": 2})
    rows = {row1.id: row1, row2.id: row2}

    mock_db = _make_lease_db(
        claimed=True, orphans=[], renewed=1,
        first_side_effect=[row1, row2, None],
        get_side_effect=lambda model, rid: rows[rid],
    )

    processed = []

    async def fake_handle(db, instance, payload):
        processed.append(payload)

    fake_self = MagicMock()
    with patch("app.workers.bot_inbound_worker.celery_db_session") as cds, \
         patch("app.modules.whatsapp.bot_service.handle_inbound_message", new=fake_handle):
        cds.return_value.__enter__.return_value = mock_db
        cds.return_value.__exit__.return_value = False
        _raw(biw.drain_bot_inbound)(fake_self, str(uuid4()), "5511@s.whatsapp.net")

    assert processed == [{"m": 1}, {"m": 2}]         # ordem preservada
    assert row1.status == "DONE"
    assert row2.status == "DONE"


def test_drain_reaps_orphan_processing_without_reprocessing():
    """B.2 — mensagem PROCESSING órfã (worker anterior morreu) vira FAILED +
    dead-letter; NÃO é reprocessada (efeito externo ambíguo) nem pulada."""
    from app.workers import bot_inbound_worker as biw

    mock_db = _make_lease_db(
        claimed=True,
        orphans=[(uuid4(), "ORPHANMSG")],   # 1 PROCESSING órfão
        renewed=1,
        first_side_effect=[None],           # nenhuma RECEIVED após o reap
    )

    fake_self = MagicMock()
    with patch("app.workers.bot_inbound_worker.celery_db_session") as cds, \
         patch("app.modules.whatsapp.bot_service.handle_inbound_message") as handle, \
         patch("app.workers.bot_inbound_worker._push_dead_letter") as dead_letter:
        cds.return_value.__enter__.return_value = mock_db
        cds.return_value.__exit__.return_value = False
        _raw(biw.drain_bot_inbound)(fake_self, str(uuid4()), "5511@s.whatsapp.net")

    dead_letter.assert_called_once()   # órfão visível no dead-letter
    handle.assert_not_called()         # NÃO reprocessa o órfão


def test_drain_dead_letter_after_max_attempts():
    """DoD B.8 — falha no worker vira FAILED + dead-letter (visível)."""
    from app.workers import bot_inbound_worker as biw

    row = _drain_row({"m": 1}, attempts=4)  # +1 = 5 = _MAX_ATTEMPTS

    mock_db = _make_lease_db(
        claimed=True, orphans=[], renewed=1,
        first_side_effect=[row, None],
        get_side_effect=lambda model, rid: row,
    )

    async def boom(db, instance, payload):
        raise RuntimeError("boom")

    fake_self = MagicMock()
    with patch("app.workers.bot_inbound_worker.celery_db_session") as cds, \
         patch("app.modules.whatsapp.bot_service.handle_inbound_message", new=boom), \
         patch("app.workers.bot_inbound_worker._push_dead_letter") as dead_letter:
        cds.return_value.__enter__.return_value = mock_db
        cds.return_value.__exit__.return_value = False
        _raw(biw.drain_bot_inbound)(fake_self, str(uuid4()), "5511@s.whatsapp.net")

    assert row.status == "FAILED"
    dead_letter.assert_called_once()


def test_drain_retries_when_conversation_busy():
    """B.6 — lease detida por outro worker → claim None → retry (serialização)."""
    from app.workers import bot_inbound_worker as biw

    mock_db = _make_lease_db(claimed=False)  # claim devolve None

    fake_self = MagicMock()
    fake_self.retry.side_effect = RuntimeError("RETRY")

    with patch("app.workers.bot_inbound_worker.celery_db_session") as cds:
        cds.return_value.__enter__.return_value = mock_db
        cds.return_value.__exit__.return_value = False
        with pytest.raises(RuntimeError):
            _raw(biw.drain_bot_inbound)(fake_self, str(uuid4()), "5511@s.whatsapp.net")

    fake_self.retry.assert_called_once()


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="requer Postgres real")
def test_lease_serialization_against_real_postgres():
    """B.6 (prova que o mock não pode dar) — contra Postgres real, o claim de
    lease dá EXCLUSÃO MÚTUA entre duas conexões. Simétrico ao diagnóstico:
    advisory lock falha no pooler transaction-mode; o lease não.
    """
    from sqlalchemy import create_engine, text

    url = os.environ["DATABASE_URL"]
    probe = create_engine(url)
    with probe.connect() as c0:
        cid = c0.execute(text("SELECT id FROM companies LIMIT 1")).scalar()
    probe.dispose()
    if cid is None:
        pytest.skip("sem company no banco")

    claim = text("""
        INSERT INTO bot_conversation_leases (company_id, whatsapp_id, locked_by, locked_until)
        VALUES (:c, :w, :by, now() + make_interval(secs => 30))
        ON CONFLICT (company_id, whatsapp_id) DO UPDATE
            SET locked_by = EXCLUDED.locked_by, locked_until = EXCLUDED.locked_until
            WHERE bot_conversation_leases.locked_until < now()
        RETURNING locked_by
    """)
    clean = text("DELETE FROM bot_conversation_leases WHERE company_id=:c AND whatsapp_id=:w")
    p = {"c": cid, "w": "__pytest_lease_selftest__"}

    e1 = create_engine(url)
    e2 = create_engine(url)
    c1 = e1.connect()
    c2 = e2.connect()
    try:
        c1.execute(clean, p)
        c1.commit()
        g1 = c1.execute(claim, {**p, "by": "t1"}).fetchone()
        c1.commit()
        g2 = c2.execute(claim, {**p, "by": "t2"}).fetchone()
        c2.commit()
        c1.execute(clean, p)
        c1.commit()
        assert g1 is not None   # worker 1 adquire
        assert g2 is None       # worker 2 bloqueado (exclusão mútua real)
    finally:
        c1.close()
        c2.close()
        e1.dispose()
        e2.dispose()
