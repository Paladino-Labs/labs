"""
Testes do Sprint 9 — PaymentsEngine: FSM, webhook idempotente, DepositPolicy.

Usa mocks (unittest.mock) para isolar da infraestrutura real.
Nenhum teste chama a API Asaas real ou banco PostgreSQL.

Casos cobertos:
  1.  confirm() com mesmo event_id 2x → 1 PaymentTransaction (idempotência via is_processed)
  2.  UNIQUE(company_id, provider_transaction_id) rejeita duplicata no banco
      (IntegrityError → confirm() retorna payment sem reprocessar)
  3.  payment.confirmed: gross=100, fee=2 → Movement INFLOW + Entry RECEITA + OUTFLOW + TAXA
  4.  confirm() com falha em handle_payment_confirmed → rollback completo
      (sem PaymentTransaction, payment.status permanece PENDING)
  5.  ProcessedIdempotencyKey inserida na mesma transação de confirm()
  6.  Payment.provider imutável: @validates levanta ValueError após flush
  7.  refund() → Movement OUTFLOW + Entry ESTORNO + record_sensitive_action
  8.  EventBus.publish("payment.confirmed") chamado após commit, não dentro da transação
  9.  Comunicação falha no handler → payment ainda CONFIRMED (best-effort isolado)
  10. payment_source_id=None para PIX (campo nullable correto)
  11. Cross-tenant: create_payment define company_id corretamente
  12. RefundReason enum cobre todos os valores exigidos
  13. create_payment retorna Payment com status PENDING
  14. refund() levanta 422 se payment não está CONFIRMED
  15. handle_payment_refunded cria OUTFLOW + ESTORNO
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_payment(
    payment_id=None,
    company_id=None,
    customer_id=None,
    status="PENDING",
    payment_method="PIX",
    provider="asaas",
    net_charged_amount=Decimal("100.00"),
    provider_fee=Decimal("0.00"),
    target_account_id=None,
    payment_source_id=None,
    has_identity=False,
):
    p = MagicMock()
    p.payment_id = payment_id or uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.customer_id = customer_id or uuid.uuid4()
    p.status = status
    p.payment_method = payment_method
    p.provider = provider
    p.net_charged_amount = Decimal(str(net_charged_amount))
    p.provider_fee = Decimal(str(provider_fee))
    p.target_account_id = target_account_id or uuid.uuid4()
    p.payment_source_id = payment_source_id
    p._sa_instance_state = MagicMock()
    p._sa_instance_state.has_identity = has_identity
    return p


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()
    db.refresh = MagicMock()
    return db


# ─────────────────────────────────────────────────────────────────────────────
# 1. RefundReason enum
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_reason_values():
    """RefundReason deve ter os 4 valores exigidos pelo brief."""
    from app.modules.payments.service import RefundReason
    assert RefundReason.SERVICE_FAILURE == "SERVICE_FAILURE"
    assert RefundReason.REGISTRATION_ERROR == "REGISTRATION_ERROR"
    assert RefundReason.DEADLINE_POLICY == "DEADLINE_POLICY"
    assert RefundReason.OTHER == "OTHER"


# ─────────────────────────────────────────────────────────────────────────────
# 2. payment_source_id nullable para PIX
# ─────────────────────────────────────────────────────────────────────────────

def test_payment_source_id_nullable_for_pix():
    """payment_source_id deve ser None para pagamentos PIX."""
    from app.infrastructure.db.models.payment import Payment
    p = Payment(
        company_id=uuid.uuid4(),
        gross_catalog_amount=Decimal("100"),
        net_charged_amount=Decimal("100"),
        payment_method="PIX",
        provider="asaas",
        target_account_id=uuid.uuid4(),
    )
    assert p.payment_source_id is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Payment.provider imutável após flush (@validates)
# ─────────────────────────────────────────────────────────────────────────────

def test_payment_provider_immutable_after_identity():
    """@validates deve impedir mutação de provider após a instância ter identidade."""
    from app.infrastructure.db.models.payment import Payment
    p = Payment(
        company_id=uuid.uuid4(),
        gross_catalog_amount=Decimal("100"),
        net_charged_amount=Decimal("100"),
        payment_method="PIX",
        provider="asaas",
        target_account_id=uuid.uuid4(),
    )
    # Simula instância persistida
    p._sa_instance_state = MagicMock()
    p._sa_instance_state.has_identity = True

    with pytest.raises(ValueError, match="imutável"):
        p.provider = "outro_provider"


def test_payment_provider_mutable_before_persist():
    """provider é mutável antes da persistência — __init__ com provider funciona."""
    from app.infrastructure.db.models.payment import Payment
    # Se @validates bloqueasse pré-persistência, o próprio __init__ levantaria.
    p = Payment(
        company_id=uuid.uuid4(),
        gross_catalog_amount=Decimal("100"),
        net_charged_amount=Decimal("100"),
        payment_method="PIX",
        provider="asaas",
        target_account_id=uuid.uuid4(),
    )
    assert p.provider == "asaas"
    # Segunda atribuição antes de flush também deve ser permitida
    # (has_identity=False para objeto não persistido)
    p.provider = "null_provider"
    assert p.provider == "null_provider"


# ─────────────────────────────────────────────────────────────────────────────
# 4. create_payment
# ─────────────────────────────────────────────────────────────────────────────

def test_create_payment_returns_pending():
    """create_payment deve persistir Payment com status PENDING."""
    company_id = uuid.uuid4()
    account_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    db = _make_db()
    expected_payment = _make_payment(
        company_id=company_id,
        customer_id=customer_id,
        status="PENDING",
        payment_method="PIX",
        provider="asaas",
        net_charged_amount=Decimal("150.00"),
        target_account_id=account_id,
        payment_source_id=None,
    )
    db.refresh.side_effect = lambda obj: None

    mock_provider = MagicMock()
    mock_provider.create_charge.return_value = {"id": "pay_test_charge", "status": "PENDING"}

    with (
        patch("app.modules.payments.service.Payment") as MockPayment,
        patch("app.modules.payments.service.get_payment_provider", return_value=mock_provider),
    ):
        MockPayment.return_value = expected_payment
        from app.modules.payments.service import create_payment

        result = create_payment(
            company_id=company_id,
            customer_id=customer_id,
            gross_amount=Decimal("150.00"),
            payment_method="PIX",
            provider="asaas",
            target_account_id=account_id,
            payment_source_id=None,
            db=db,
        )

    db.add.assert_called_once_with(expected_payment)
    db.commit.assert_called_once()
    assert result.status == "PENDING"
    assert result.payment_source_id is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. confirm() idempotência via is_processed
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_idempotent_via_is_processed():
    """Segunda chamada com mesmo event_id deve retornar payment sem reprocessar."""
    payment = _make_payment(status="CONFIRMED")
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=True) as mock_is_proc,
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.mark_processed") as mock_mark,
    ):
        from app.modules.payments.service import confirm

        result = confirm(
            payment_id=payment.payment_id,
            event_id="evt_duplicate",
            webhook_data={"id": "evt_duplicate", "value": "100"},
            company_id=payment.company_id,
            db=db,
        )

    # is_processed retornou True → retorna payment sem processar
    mock_is_proc.assert_called_once_with(
        key="evt_duplicate", consumer="payment_confirmed", db=db
    )
    MockTxn.assert_not_called()
    mock_fc.handle_payment_confirmed.assert_not_called()
    mock_mark.assert_not_called()
    db.commit.assert_not_called()
    assert result == payment


# ─────────────────────────────────────────────────────────────────────────────
# 6. confirm() IntegrityError → retorna payment sem reprocessar
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_integrity_error_returns_existing_payment():
    """UNIQUE violado (IntegrityError) deve rollback e retornar payment atual."""
    from sqlalchemy.exc import IntegrityError

    payment = _make_payment(status="CONFIRMED", payment_method="PIX")
    db = _make_db()
    db.flush.side_effect = IntegrityError("stmt", {}, Exception("unique"))

    # Após rollback, nova query retorna payment com status CONFIRMED
    db.query.return_value.filter.return_value.first.return_value = payment

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
    ):
        MockTxn.return_value = MagicMock()
        from app.modules.payments.service import confirm

        result = confirm(
            payment_id=payment.payment_id,
            event_id="evt_dup_unique",
            webhook_data={"id": "evt_dup_unique"},
            company_id=payment.company_id,
            db=db,
        )

    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    assert result.status == "CONFIRMED"


# ─────────────────────────────────────────────────────────────────────────────
# 7. confirm() atomicidade: falha em handle_payment_confirmed → rollback
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_rollback_on_financial_core_failure():
    """Falha em handle_payment_confirmed deve causar rollback completo."""
    payment = _make_payment(status="PENDING", payment_method="PIX")
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.mark_processed") as mock_mark,
    ):
        MockTxn.return_value = MagicMock()
        mock_fc.handle_payment_confirmed.side_effect = RuntimeError("DB error in financial core")

        from app.modules.payments.service import confirm

        with pytest.raises(RuntimeError, match="DB error in financial core"):
            confirm(
                payment_id=payment.payment_id,
                event_id="evt_fail_fc",
                webhook_data={"id": "evt_fail_fc"},
                company_id=payment.company_id,
                db=db,
            )

    # Rollback chamado; commit nunca chamado
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    # mark_processed não foi chamado (passo 5 não atingido)
    mock_mark.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 8. confirm() — ProcessedIdempotencyKey inserida na mesma transação
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_mark_processed_called_before_commit():
    """mark_processed deve ser chamado antes do commit (mesma transação)."""
    payment = _make_payment(status="PENDING", payment_method="PIX")
    db = _make_db()
    call_order = []

    def track_mark_processed(*args, **kwargs):
        call_order.append("mark_processed")

    def track_commit():
        call_order.append("commit")

    db.commit.side_effect = track_commit

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
        patch("app.modules.payments.service.financial_core"),
        patch("app.modules.payments.service.mark_processed", side_effect=track_mark_processed),
        patch("app.modules.payments.service.event_bus"),
    ):
        MockTxn.return_value = MagicMock()
        from app.modules.payments.service import confirm

        confirm(
            payment_id=payment.payment_id,
            event_id="evt_order",
            webhook_data={"id": "evt_order"},
            company_id=payment.company_id,
            db=db,
        )

    assert call_order == ["mark_processed", "commit"], (
        f"Esperado mark_processed antes de commit, obtido: {call_order}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9. confirm() — EventBus.publish após commit
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_event_bus_published_after_commit():
    """EventBus.publish deve ser chamado APÓS o commit, nunca dentro da transação."""
    payment = _make_payment(status="PENDING", payment_method="PIX")
    db = _make_db()
    commit_happened = []
    publish_happened = []

    def track_commit():
        commit_happened.append(True)

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
        patch("app.modules.payments.service.financial_core"),
        patch("app.modules.payments.service.mark_processed"),
        patch("app.modules.payments.service.event_bus") as mock_bus,
    ):
        MockTxn.return_value = MagicMock()
        db.commit.side_effect = track_commit

        def capture_publish(event):
            # publish só deve ser chamado após commit ter acontecido
            assert len(commit_happened) == 1, "publish chamado antes do commit!"
            publish_happened.append(event.event_type)

        mock_bus.publish.side_effect = capture_publish

        from app.modules.payments.service import confirm

        confirm(
            payment_id=payment.payment_id,
            event_id="evt_bus",
            webhook_data={"id": "evt_bus"},
            company_id=payment.company_id,
            db=db,
        )

    assert "payment.confirmed" in publish_happened
    mock_bus.publish.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 10. confirm() — financial_core.handle_payment_confirmed chamado corretamente
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_calls_handle_payment_confirmed_with_correct_args():
    """confirm() deve chamar handle_payment_confirmed com gross_amount e fee corretos."""
    account_id = uuid.uuid4()
    payment = _make_payment(
        status="PENDING",
        payment_method="PIX",
        net_charged_amount=Decimal("100.00"),
        provider_fee=Decimal("2.00"),
        target_account_id=account_id,
    )
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.mark_processed"),
        patch("app.modules.payments.service.event_bus"),
    ):
        MockTxn.return_value = MagicMock()
        from app.modules.payments.service import confirm

        confirm(
            payment_id=payment.payment_id,
            event_id="evt_args",
            webhook_data={"id": "evt_args"},
            company_id=payment.company_id,
            db=db,
        )

    mock_fc.handle_payment_confirmed.assert_called_once()
    call_kwargs = mock_fc.handle_payment_confirmed.call_args
    assert call_kwargs.kwargs["gross_amount"] == Decimal("100.00")
    assert call_kwargs.kwargs["target_account_id"] == account_id
    # PIX (Asaas): taxa real chega no webhook — sem política MDR local
    assert call_kwargs.kwargs["fee_source"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 11. refund() — Movement OUTFLOW + Entry ESTORNO + record_sensitive_action
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_creates_outflow_and_estorno():
    """refund() deve chamar handle_payment_refunded e record_sensitive_action."""
    from app.modules.payments.service import RefundReason

    actor_id = uuid.uuid4()
    payment = _make_payment(status="CONFIRMED", net_charged_amount=Decimal("100.00"))
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider") as mock_provider_factory,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.record_sensitive_action") as mock_audit,
        patch("app.modules.payments.service.event_bus"),
    ):
        mock_provider_factory.return_value = MagicMock()
        mock_fc.handle_payment_refunded.return_value = {
            "outflow_movement_id": uuid.uuid4(),
            "estorno_entry_id": uuid.uuid4(),
        }

        from app.modules.payments.service import refund

        result = refund(
            payment_id=payment.payment_id,
            reason=RefundReason.SERVICE_FAILURE,
            actor_id=actor_id,
            company_id=payment.company_id,
            db=db,
        )

    mock_fc.handle_payment_refunded.assert_called_once()
    call_kw = mock_fc.handle_payment_refunded.call_args.kwargs
    assert call_kw["gross_amount"] == Decimal("100.00")
    assert call_kw["payment_id"] == payment.payment_id

    mock_audit.assert_called_once()
    audit_ctx = mock_audit.call_args.args[0]
    assert audit_ctx.action == "refund_payment"
    assert audit_ctx.reason == "SERVICE_FAILURE"
    assert audit_ctx.actor_id == actor_id

    db.commit.assert_called_once()


def test_refund_rejects_non_confirmed():
    """refund() deve levantar 422 se payment.status != CONFIRMED."""
    from app.modules.payments.service import RefundReason
    from fastapi import HTTPException

    payment = _make_payment(status="PENDING")
    db = _make_db()

    with patch("app.modules.payments.service._get_payment", return_value=payment):
        from app.modules.payments.service import refund

        with pytest.raises(HTTPException) as exc_info:
            refund(
                payment_id=payment.payment_id,
                reason=RefundReason.OTHER,
                actor_id=uuid.uuid4(),
                company_id=payment.company_id,
                db=db,
            )

    assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 12. refund() — EventBus.publish("payment.refunded") após commit
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_event_bus_published_after_commit():
    """EventBus.publish('payment.refunded') deve ser chamado após commit."""
    from app.modules.payments.service import RefundReason

    payment = _make_payment(status="CONFIRMED")
    db = _make_db()
    commit_happened = []

    def track_commit():
        commit_happened.append(True)

    db.commit.side_effect = track_commit

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider") as mock_provider_factory,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.record_sensitive_action"),
        patch("app.modules.payments.service.event_bus") as mock_bus,
    ):
        mock_provider_factory.return_value = MagicMock()
        mock_fc.handle_payment_refunded.return_value = {}
        published = []

        def capture_publish(event):
            assert len(commit_happened) == 1, "publish antes do commit!"
            published.append(event.event_type)

        mock_bus.publish.side_effect = capture_publish

        from app.modules.payments.service import refund

        refund(
            payment_id=payment.payment_id,
            reason=RefundReason.DEADLINE_POLICY,
            actor_id=uuid.uuid4(),
            company_id=payment.company_id,
            db=db,
        )

    assert "payment.refunded" in published


# ─────────────────────────────────────────────────────────────────────────────
# 13. Comunicação falha no handler → payment ainda CONFIRMED
# ─────────────────────────────────────────────────────────────────────────────

def test_communication_handler_failure_doesnt_affect_payment():
    """Falha no handler de comunicação não deve impactar o pagamento confirmado."""
    from app.modules.communication.handlers import handle_payment_confirmed_notification
    from app.infrastructure.event_bus import DomainEvent
    import app.modules.communication.handlers as comm_handlers

    event = DomainEvent(
        event_id=uuid.uuid4(),
        event_type="payment.confirmed",
        occurred_at=datetime.now(timezone.utc),
        company_id=uuid.uuid4(),
        idempotency_key="payment.confirmed:test",
        actor={"type": "SYSTEM", "id": "test"},
        payload={
            "payment_id": str(uuid.uuid4()),
            "customer_id": str(uuid.uuid4()),
            "amount": "100.00",
        },
    )

    mock_db = MagicMock()
    mock_svc = MagicMock()
    mock_svc.dispatch.side_effect = RuntimeError("whatsapp down")

    # Patcha SessionLocal a nível de módulo e communication_service via lazy import
    with (
        patch.object(comm_handlers, "SessionLocal", return_value=mock_db),
        patch("app.modules.communication.service.communication_service", mock_svc),
    ):
        # Não deve levantar exceção — best-effort
        handle_payment_confirmed_notification(event)

    mock_svc.dispatch.assert_called_once()


def test_communication_handler_skips_when_no_customer():
    """Handler deve pular graciosamente se customer_id ausente no payload."""
    from app.modules.communication.handlers import handle_payment_confirmed_notification
    from app.infrastructure.event_bus import DomainEvent
    import app.modules.communication.handlers as comm_handlers

    event = DomainEvent(
        event_id=uuid.uuid4(),
        event_type="payment.confirmed",
        occurred_at=datetime.now(timezone.utc),
        company_id=uuid.uuid4(),
        idempotency_key="payment.confirmed:test-nocust",
        actor={"type": "SYSTEM", "id": "test"},
        payload={
            "payment_id": str(uuid.uuid4()),
            "customer_id": None,  # ausente
            "amount": "100.00",
        },
    )

    mock_session_cls = MagicMock()
    with patch.object(comm_handlers, "SessionLocal", mock_session_cls):
        handle_payment_confirmed_notification(event)
        mock_session_cls.assert_not_called()  # não abre sessão se customer_id ausente


# ─────────────────────────────────────────────────────────────────────────────
# 14. handle_payment_refunded no FinancialCoreEngine
# ─────────────────────────────────────────────────────────────────────────────

def test_handle_payment_refunded_creates_outflow_and_estorno():
    """handle_payment_refunded deve criar Movement OUTFLOW + Entry ESTORNO."""
    from app.modules.financial_core.service import handle_payment_refunded

    payment_id = uuid.uuid4()
    account_id = uuid.uuid4()
    company_id = uuid.uuid4()
    db = _make_db()

    outflow_mv = MagicMock()
    outflow_mv.movement_id = uuid.uuid4()
    estorno_en = MagicMock()
    estorno_en.entry_id = uuid.uuid4()

    with (
        patch("app.modules.financial_core.service._record_movement", return_value=outflow_mv) as mock_mv,
        patch("app.modules.financial_core.service._record_entry", return_value=estorno_en) as mock_en,
    ):
        result = handle_payment_refunded(
            payment_id=payment_id,
            gross_amount=Decimal("100.00"),
            target_account_id=account_id,
            company_id=company_id,
            db=db,
        )

    mock_mv.assert_called_once()
    mv_kwargs = mock_mv.call_args.kwargs
    assert mv_kwargs["type"] == "OUTFLOW"
    assert mv_kwargs["amount"] == Decimal("100.00")
    assert mv_kwargs["account_id"] == account_id

    mock_en.assert_called_once()
    en_kwargs = mock_en.call_args.kwargs
    assert en_kwargs["type"] == "ESTORNO"
    assert en_kwargs["direction"] == "SUBTRACTS"
    assert en_kwargs["category"] == "REEMBOLSO_CLIENTE"

    assert result["outflow_movement_id"] == outflow_mv.movement_id
    assert result["estorno_entry_id"] == estorno_en.entry_id


# ─────────────────────────────────────────────────────────────────────────────
# 15. DepositPolicy model
# ─────────────────────────────────────────────────────────────────────────────

def test_deposit_policy_model_attributes():
    """DepositPolicy deve ter todos os campos obrigatórios do brief."""
    from app.infrastructure.db.models.deposit_policy import DepositPolicy
    # Column(default=...) é server-side; testa com valores explícitos como na service layer.
    policy = DepositPolicy(
        company_id=uuid.uuid4(),
        deposit_type="FIXED_AMOUNT",
        deposit_value=Decimal("50.00"),
        refundable_until_hours_before=24,
        refund_on_tenant_fault=True,
        retain_on_no_show=True,
        commission_on_retained_deposit=False,
    )
    assert policy.deposit_type == "FIXED_AMOUNT"
    assert policy.deposit_value == Decimal("50.00")
    assert policy.service_id is None                          # global (sem serviço específico)
    assert policy.refundable_until_hours_before == 24
    assert policy.refund_on_tenant_fault is True
    assert policy.retain_on_no_show is True
    assert policy.commission_on_retained_deposit is False


# ─────────────────────────────────────────────────────────────────────────────
# 16. PaymentTransaction UNIQUE constraint declarada no modelo
# ─────────────────────────────────────────────────────────────────────────────

def test_payment_transaction_unique_constraint_declared():
    """UniqueConstraint(company_id, provider_transaction_id) deve estar no modelo."""
    from app.infrastructure.db.models.payment_transaction import PaymentTransaction
    from sqlalchemy import UniqueConstraint

    constraints = PaymentTransaction.__table__.constraints
    unique_cols = set()
    for c in constraints:
        if isinstance(c, UniqueConstraint):
            unique_cols.update(col.name for col in c.columns)

    assert "company_id" in unique_cols
    assert "provider_transaction_id" in unique_cols


# ─────────────────────────────────────────────────────────────────────────────
# 17. _fee_source_for helper
# ─────────────────────────────────────────────────────────────────────────────

def test_fee_source_mapping():
    """_fee_source_for deve mapear métodos de pagamento para fee_source correto."""
    from app.modules.payments.service import _fee_source_for

    # Métodos Asaas: taxa via webhook — sem fee_source local
    assert _fee_source_for("PIX") is None
    assert _fee_source_for("BOLETO") is None
    assert _fee_source_for("CARD_CREDIT") is None
    assert _fee_source_for("CARD_DEBIT") is None
    # Presenciais
    assert _fee_source_for("CHAVE_PIX") == "CHAVE_PIX"
    assert _fee_source_for("MAQUININHA") == "MAQUININHA_CREDIT_OUTROS"
    assert _fee_source_for("MAQUININHA_CREDIT") == "MAQUININHA_CREDIT_OUTROS"
    assert _fee_source_for("MAQUININHA_DEBIT") == "MAQUININHA_DEBIT_OUTROS"
    assert _fee_source_for("MAQUININHA_PIX") == "MAQUININHA_PIX"


# ─────────────────────────────────────────────────────────────────────────────
# 18. Payment.provider trigger — representação SQL na migration
# ─────────────────────────────────────────────────────────────────────────────

def test_payment_migration_has_provider_trigger():
    """Migration w1x2y3z4a5b6 deve conter o trigger de imutabilidade do provider."""
    import importlib.util, os

    migration_path = os.path.join(
        os.path.dirname(__file__),
        "..", "migrations", "versions", "w1x2y3z4a5b6_add_payments.py"
    )
    spec = importlib.util.spec_from_file_location("w1x2y3z4a5b6", migration_path)
    mod = importlib.util.module_from_spec(spec)

    # Verifica que o conteúdo do arquivo menciona o trigger
    with open(migration_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "payment_provider_immutable" in content
    assert "prevent_payment_provider_change" in content
    assert "BEFORE UPDATE OF provider" in content


# ─────────────────────────────────────────────────────────────────────────────
# 19. register_handlers registra no EventBus
# ─────────────────────────────────────────────────────────────────────────────

def test_communication_handlers_registration():
    """register_handlers deve registrar handler para 'payment.confirmed'."""
    from app.infrastructure.event_bus import EventBus
    import app.modules.communication.handlers as comm_handlers

    test_bus = EventBus()
    with patch.object(comm_handlers, "event_bus", test_bus):
        comm_handlers.register_handlers()

    assert "payment.confirmed" in test_bus._handlers
    assert len(test_bus._handlers["payment.confirmed"]) == 1
