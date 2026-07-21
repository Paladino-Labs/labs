"""S2.1 — Fila Celery: envio externo fora do request + webhook do bot fora do event loop.

Entrega A: create/reschedule/cancel/checkout enfileiram o envio em vez de
  chamá-lo síncrono no request.
Entrega B: o webhook do bot persiste + enfileira; o worker processa fora do
  event loop, serializado por conversa.

Estilo unitário com mocks (não exercita broker/Postgres reais), coerente com
o restante da suíte.
"""
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
