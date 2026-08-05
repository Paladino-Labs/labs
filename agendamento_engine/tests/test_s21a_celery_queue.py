"""S2.1-A — Fila Celery: envio externo fora do request.

create/reschedule/checkout e a notificação de fila de espera ENFILEIRAM o envio
em vez de chamá-lo síncrono no request. O envio (3-5 queries + httpx Evolution
15s / SMTP 10s) roda no worker.

A Entrega B (webhook do bot fora do event loop) NÃO faz parte deste sprint —
foi adiada; nada aqui a exercita.

Estilo unitário com mocks (não exercita broker/Postgres reais), coerente com o
restante da suíte.
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


def _fake_appointment():
    appt = MagicMock()
    appt.id = uuid4()
    appt.company_id = uuid4()
    return appt


# ─────────────────────────────────────────────────────────────────────────────
# 1+2. Agendar/remarcar/checkout enfileiram — com os parâmetros corretos
# ─────────────────────────────────────────────────────────────────────────────

def test_send_booking_confirmation_enqueues_with_correct_params():
    """DoD 2 — a tarefa é enfileirada com evento, appointment, company e token."""
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


def test_wrapper_does_not_dispatch_synchronously():
    """DoD 1 — o wrapper NÃO chama CommunicationService.dispatch no request.

    Cobre também o checkout: `unified_checkout` envia por `create_appointment`,
    que chama este mesmo wrapper — o enfileiramento é herdado, um por item.
    """
    from app.modules import notifications

    appt = _fake_appointment()
    with patch("app.workers.communication_worker.send_appointment_communication"), \
         patch("app.modules.communication.service.communication_service.dispatch") as dispatch:
        notifications.send_booking_confirmation(MagicMock(), appt, manage_token="x")

    dispatch.assert_not_called()


def test_checkout_path_enqueues_once_per_service_item():
    """DoD 1 — N itens de serviço no checkout ⇒ N tarefas (retry independente),
    não um agregado. Exercita o wrapper no ponto em que o checkout o alcança."""
    from app.modules import notifications

    appts = [_fake_appointment(), _fake_appointment()]
    with patch("app.workers.communication_worker.send_appointment_communication") as task:
        for i, appt in enumerate(appts):
            notifications.send_booking_confirmation(MagicMock(), appt, manage_token=f"tok-{i}")

    assert task.apply_async.call_count == 2
    enfileirados = [c.kwargs["args"][1] for c in task.apply_async.call_args_list]
    assert enfileirados == [str(a.id) for a in appts]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Broker fora do ar não derruba a resposta
# ─────────────────────────────────────────────────────────────────────────────

def test_enqueue_failure_does_not_propagate():
    """DoD 4 — broker fora do ar é logado e engolido; a resposta ao cliente segue."""
    from app.modules import notifications

    appt = _fake_appointment()
    with patch("app.workers.communication_worker.send_appointment_communication") as task:
        task.apply_async.side_effect = RuntimeError("broker down")
        # não deve levantar
        notifications.send_booking_confirmation(MagicMock(), appt, manage_token="x")


# ─────────────────────────────────────────────────────────────────────────────
# Contrato da task ressuscitada — paridade com o caminho vivo
# ─────────────────────────────────────────────────────────────────────────────

def test_task_renders_manage_url_and_long_date():
    """A task ressuscitada monta manage_url + data por extenso, igual ao caminho
    vivo — reusa os helpers de notifications.py, sem renderização própria."""
    from app.workers import communication_worker as cw

    company_id = str(uuid4())
    appt = MagicMock()
    appt.client_id = uuid4()
    # 5 de maio, 14:30 (naive → tratado como UTC pelo _localize)
    import datetime as _dt
    appt.start_at = _dt.datetime(2026, 5, 5, 14, 30)
    appt.professional = MagicMock()
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


def test_task_respects_kill_switch():
    """O kill-switch use_communication_service continua valendo dentro da task —
    mesmo helper do caminho vivo, sem cópia."""
    from app.workers import communication_worker as cw

    fake_self = MagicMock()
    with patch("app.workers.communication_worker.celery_db_session") as cds, \
         patch("app.modules.notifications._use_communication_service", return_value=False), \
         patch("app.modules.communication.service.communication_service.dispatch") as dispatch:
        cds.return_value.__enter__.return_value = MagicMock()
        cds.return_value.__exit__.return_value = False
        _raw(cw.send_appointment_communication)(
            fake_self, "appointment.confirmed", str(uuid4()), str(uuid4()), None,
        )

    dispatch.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Falha no envio não afeta a resposta, e deixa rastro
# ─────────────────────────────────────────────────────────────────────────────

def test_task_dead_letter_on_exhausted_retries():
    """DoD 3 — falha esgotada deixa rastro no dead-letter e re-levanta (a
    exceção fica NO WORKER; a resposta ao cliente já foi entregue)."""
    from app.workers import communication_worker as cw

    fake_self = MagicMock()
    fake_self.request.retries = 5
    fake_self.max_retries = 5
    fake_self.request.id = "task-1"

    mock_db = MagicMock()
    mock_db.query.side_effect = RuntimeError("db boom")

    with patch("app.workers.communication_worker.celery_db_session") as cds, \
         patch("app.modules.notifications._use_communication_service", return_value=True), \
         patch("app.workers.communication_worker._push_dead_letter") as dead_letter:
        cds.return_value.__enter__.return_value = mock_db
        cds.return_value.__exit__.return_value = False
        with pytest.raises(RuntimeError):
            _raw(cw.send_appointment_communication)(
                fake_self, "appointment.confirmed", str(uuid4()), str(uuid4()), None,
            )

    dead_letter.assert_called_once()


def test_task_retries_before_dead_letter():
    """Antes de esgotar, a falha re-levanta SEM dead-letter — é o autoretry do
    Celery que reprocessa (max_retries=5 com backoff)."""
    from app.workers import communication_worker as cw

    fake_self = MagicMock()
    fake_self.request.retries = 1
    fake_self.max_retries = 5
    fake_self.request.id = "task-2"

    mock_db = MagicMock()
    mock_db.query.side_effect = RuntimeError("db boom")

    with patch("app.workers.communication_worker.celery_db_session") as cds, \
         patch("app.modules.notifications._use_communication_service", return_value=True), \
         patch("app.workers.communication_worker._push_dead_letter") as dead_letter:
        cds.return_value.__enter__.return_value = mock_db
        cds.return_value.__exit__.return_value = False
        with pytest.raises(RuntimeError):
            _raw(cw.send_appointment_communication)(
                fake_self, "appointment.confirmed", str(uuid4()), str(uuid4()), None,
            )

    dead_letter.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Waitlist enfileirada no cancel/reschedule, em vez de httpx inline
# ─────────────────────────────────────────────────────────────────────────────

def test_waitlist_handler_enqueues_per_scope():
    """DoD 5 — cancel/reschedule enfileiram a notificação da fila por escopo."""
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


def test_waitlist_handler_does_not_notify_inline():
    """DoD 5 — o handler não abre sessão nem chama notify_waitlist no request."""
    from app.workers.handlers import waitlist_handler

    event = MagicMock()
    event.company_id = uuid4()
    event.event_type = "appointment.rescheduled"
    event.payload = {"service_ids": [str(uuid4())], "professional_id": None}

    with patch("app.workers.handlers.waitlist_handler.notify_waitlist_slot_available"), \
         patch("app.modules.waitlist.service.notify_waitlist") as notify:
        waitlist_handler.handle_appointment_cancelled_waitlist(event)

    notify.assert_not_called()


def test_waitlist_handler_enqueue_failure_is_best_effort():
    """DoD 4/5 — broker fora do ar não derruba o cancel/reschedule."""
    from app.workers.handlers import waitlist_handler

    event = MagicMock()
    event.company_id = uuid4()
    event.event_type = "appointment.cancelled"
    event.payload = {"service_ids": [str(uuid4())], "professional_id": None}

    with patch("app.workers.handlers.waitlist_handler.notify_waitlist_slot_available") as task:
        task.apply_async.side_effect = RuntimeError("broker down")
        # não deve levantar
        waitlist_handler.handle_appointment_cancelled_waitlist(event)


def test_notify_waitlist_task_maps_scope_to_service_id():
    """A task traduz o escopo para o kwarg que notify_waitlist espera."""
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


def test_notify_waitlist_task_dead_letter_on_exhausted_retries():
    """DoD 3 — a task da fila também deixa rastro quando esgota o retry."""
    from app.workers.handlers import waitlist_handler

    fake_self = MagicMock()
    fake_self.request.retries = 3
    fake_self.max_retries = 3
    fake_self.request.id = "wl-1"

    with patch("app.workers.handlers.waitlist_handler.celery_db_session") as cds, \
         patch("app.modules.waitlist.service.notify_waitlist", side_effect=RuntimeError("boom")), \
         patch("app.workers.handlers.waitlist_handler._push_dead_letter") as dead_letter:
        cds.return_value.__enter__.return_value = MagicMock()
        cds.return_value.__exit__.return_value = False
        with pytest.raises(RuntimeError):
            _raw(waitlist_handler.notify_waitlist_slot_available)(
                fake_self, str(uuid4()), "PROFESSIONAL", str(uuid4()), "appointment.cancelled",
            )

    dead_letter.assert_called_once()


def test_stock_entry_waitlist_handler_unchanged():
    """O caminho de reabastecimento NÃO está no escopo do S2.1-A: continua
    notificando inline (não roda em request de cliente — vem do painel)."""
    from app.workers.handlers import waitlist_handler

    pid = str(uuid4())
    event = MagicMock()
    event.company_id = uuid4()
    event.payload = {"product_ids": [pid]}

    with patch("app.workers.handlers.waitlist_handler.SessionLocal") as session_local, \
         patch("app.workers.handlers.waitlist_handler.set_rls_context"), \
         patch("app.modules.waitlist.service.notify_waitlist") as notify:
        session_local.return_value = MagicMock()
        waitlist_handler.handle_stock_entry_recorded_waitlist(event)

    notify.assert_called_once()
    assert notify.call_args.kwargs["product_id"] == UUID(pid)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Regressão — drain_scheduled_communications (caminho independente, do beat)
# ─────────────────────────────────────────────────────────────────────────────

def test_drain_scheduled_communications_still_works():
    """DoD 6 — a task do beat continua drenando os SCHEDULED.

    Caminho independente do enfileiramento deste sprint: não passa por
    celery_db_session (abre a própria sessão) e não foi tocado.
    """
    from app.workers import communication_worker as cw

    fake_self = MagicMock()
    mock_db = MagicMock()

    with patch("app.workers.communication_worker.SessionLocal", return_value=mock_db), \
         patch("app.core.db_rls.set_rls_context") as set_rls, \
         patch("app.modules.communication.service.communication_service.drain_scheduled",
               return_value=7) as drain:
        _raw(cw.drain_scheduled_communications)(fake_self)

    drain.assert_called_once_with(mock_db)
    # worker de plataforma — bypass de RLS (scan multi-tenant)
    assert set_rls.call_args.args[1] is None
    mock_db.close.assert_called_once()
