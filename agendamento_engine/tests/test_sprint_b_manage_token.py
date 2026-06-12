"""
Testes Sprint B — Link de gestão com token único.

Usa mocks (unittest.mock) — sem banco PostgreSQL real (padrão do projeto).

Casos obrigatórios:
  1.  Token gerado na confirmação e armazenado como hash (cru nunca persiste)
  2.  GET /manage/{token} retorna dados sem PII sensível
  3.  GET com token inválido → 404 (não 401/403)
  4.  GET com token expirado → 404
  5.  POST cancel → appointment CANCELLED + actor=CLIENT na FSM
  6.  Cancelamento fora da janela: ocorre, mas sinal retido (DepositPolicy)
  7.  Cancelamento dentro da janela: sem retenção
  8.  Reschedule → novo token gerado, anterior inválido
  9.  Reschedule com slot indisponível → 422
  10. Token de agendamento COMPLETED → 404 (token invalidado na transição)
  11. Token de outro tenant inútil (lookup por hash → isolamento implícito)
  12. Idempotência: segundo cancel com mesmo token → 404
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.domain.enums import AppointmentStatus
from app.infrastructure.db.models import Appointment
from app.infrastructure.db.models.deposit_policy import DepositPolicy
from app.infrastructure.db.models.payment import Payment
from app.modules.appointments import service as appointment_svc
from app.modules.appointments.manage_tokens import (
    build_manage_url,
    hash_token,
    invalidate_manage_token,
    issue_manage_token,
)
from app.modules.appointments.transitions import transition
from app.modules.public import manage_service


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _future(hours: float = 48) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _make_appointment(start_in_hours: float = 48, status: str = "SCHEDULED"):
    """Appointment fake com os atributos usados por manage_service e FSM."""
    start_at = _future(start_in_hours)
    a = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        professional_id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        start_at=start_at,
        end_at=start_at + timedelta(minutes=30),
        status=status,
        version=1,
        cancelled_at=None,
        cancelled_by=None,
        cancel_reason=None,
        manage_token_hash=None,
        manage_token_expires_at=None,
        services=[SimpleNamespace(
            service_id=uuid.uuid4(),
            service_name="Corte",
            duration_snapshot=Decimal("30"),
            price_snapshot=Decimal("50.00"),
        )],
        professional=SimpleNamespace(name="João Barbeiro"),
        customer=SimpleNamespace(name="Cliente Teste", phone="+5511999999999"),
    )
    return a


def _make_db(appointment=None, deposit_policies=None, payment=None):
    """
    db mock com roteamento por modelo:
      - query(Appointment).first() emula o lookup por manage_token_hash:
        retorna o appointment apenas se o hash dele ainda estiver setado
        (token nulado → None, como no banco real)
      - query(DepositPolicy).first() consome a fila deposit_policies
      - query(Payment).first() → payment
    """
    db = MagicMock()
    policies = list(deposit_policies or [])

    def _appointment_filter(*criteria):
        """Emula o WHERE real: compara manage_token_hash quando presente."""
        f = MagicMock()
        queried_hash = None
        for c in criteria:
            left = getattr(c, "left", None)
            if getattr(left, "key", None) == "manage_token_hash":
                queried_hash = c.right.value
        if queried_hash is not None:
            match = (
                appointment is not None
                and appointment.manage_token_hash == queried_hash
            )
        else:
            match = appointment is not None  # lookup por id (já resolvido)
        f.first.side_effect = lambda: appointment if match else None
        return f

    def _query(arg):
        q = MagicMock()
        f = q.filter.return_value
        if arg is Appointment:
            q.filter.side_effect = _appointment_filter
        elif arg is DepositPolicy:
            f.first.side_effect = lambda: policies.pop(0) if policies else None
        elif arg is Payment:
            f.first.return_value = payment
        else:
            f.first.return_value = None
            f.all.return_value = []
        return q

    db.query.side_effect = _query
    return db


def _policy(hours_before: int = 24, service_id=None):
    p = MagicMock(spec=DepositPolicy)
    p.refundable_until_hours_before = hours_before
    p.service_id = service_id
    return p


def _confirmed_payment():
    p = MagicMock(spec=Payment)
    p.status = "CONFIRMED"
    return p


# ─── 1. Geração e armazenamento do token ─────────────────────────────────────

class TestTokenIssue:
    def test_token_stored_as_sha256_hash(self):
        appt = _make_appointment()
        raw = issue_manage_token(appt)

        assert appt.manage_token_hash == hash_token(raw)
        assert appt.manage_token_hash != raw          # cru nunca persiste
        assert len(appt.manage_token_hash) == 64      # SHA-256 hex
        assert appt.manage_token_expires_at == appt.start_at
        uuid.UUID(raw)  # token cru é UUID4 válido

    def test_create_appointment_issues_token_and_sends_link(self):
        """Token gerado na confirmação; cru repassado à mensagem de confirmação."""
        captured = {}

        def fake_confirmation(db, appointment, manage_token=None):
            captured["token"] = manage_token
            captured["appointment"] = appointment

        professional = SimpleNamespace(id=uuid.uuid4())
        customer = SimpleNamespace(id=uuid.uuid4())
        service = SimpleNamespace(
            id=uuid.uuid4(), name="Corte", duration=30, price=Decimal("50.00"),
        )

        db = MagicMock()

        def _query(arg):
            q = MagicMock()
            f = q.filter.return_value
            name = getattr(arg, "__name__", "")
            if name == "Professional":
                f.first.return_value = professional
            elif name == "Customer":
                f.first.return_value = customer
            elif name == "Service":
                f.all.return_value = [service]
            else:
                f.first.return_value = None
                f.all.return_value = []
            return q

        db.query.side_effect = _query

        from app.modules.appointments.schemas import AppointmentCreate
        data = AppointmentCreate(
            professional_id=professional.id,
            client_id=customer.id,
            start_at=_future(48),
            services=[{"service_id": service.id}],
            idempotency_key=str(uuid.uuid4()),
        )

        with patch.object(appointment_svc, "_assert_slot_available"), \
             patch.object(appointment_svc, "send_booking_confirmation", fake_confirmation):
            appt = appointment_svc.create_appointment(
                db, uuid.uuid4(), data, user_id=None
            )

        assert captured["token"] is not None
        assert appt.manage_token_hash == hash_token(captured["token"])

    def test_manage_url_contains_raw_token(self):
        raw = str(uuid.uuid4())
        assert build_manage_url(raw).endswith(f"/manage/{raw}")


# ─── 2–4. GET /manage/{token} ─────────────────────────────────────────────────

class TestGetDetails:
    def test_details_without_sensitive_pii(self):
        appt = _make_appointment()
        raw = issue_manage_token(appt)
        db = _make_db(appointment=appt)

        details = manage_service.get_details(db, raw)

        assert set(details.keys()) == {
            "service_name", "professional_name", "scheduled_datetime",
            "status", "can_cancel", "can_reschedule",
        }
        assert details["service_name"] == "Corte"
        assert details["professional_name"] == "João Barbeiro"
        assert details["status"] == "SCHEDULED"
        assert details["can_cancel"] is True
        assert details["can_reschedule"] is True

    def test_invalid_token_returns_404(self):
        db = _make_db(appointment=None)
        with pytest.raises(HTTPException) as exc:
            manage_service.get_details(db, str(uuid.uuid4()))
        assert exc.value.status_code == 404  # nunca 401/403

    def test_expired_token_returns_404(self):
        appt = _make_appointment()
        raw = issue_manage_token(appt)
        appt.manage_token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db = _make_db(appointment=appt)

        with pytest.raises(HTTPException) as exc:
            manage_service.get_details(db, raw)
        assert exc.value.status_code == 404

    def test_completed_appointment_token_returns_404(self):
        """Defesa em profundidade: mesmo com hash ainda setado, terminal → 404."""
        appt = _make_appointment(status="COMPLETED")
        raw = issue_manage_token(appt)
        db = _make_db(appointment=appt)

        with pytest.raises(HTTPException) as exc:
            manage_service.get_details(db, raw)
        assert exc.value.status_code == 404

    def test_cross_tenant_token_useless(self):
        """Token de outro tenant: lookup por hash não encontra → 404 genérico."""
        appt_tenant_a = _make_appointment()
        issue_manage_token(appt_tenant_a)
        forged = str(uuid.uuid4())  # token que não corresponde a hash algum

        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = None  # hash não bate
        db.query.return_value = q

        with pytest.raises(HTTPException) as exc:
            manage_service.get_details(db, forged)
        assert exc.value.status_code == 404


# ─── 5–7, 12. Cancel ──────────────────────────────────────────────────────────

class TestCancel:
    def test_cancel_transitions_to_cancelled_with_client_actor(self):
        appt = _make_appointment()
        raw = issue_manage_token(appt)
        db = _make_db(appointment=appt)

        result = manage_service.cancel(db, raw, reason="imprevisto")

        assert appt.status == "CANCELLED"
        assert result["status"] == "CANCELLED"
        assert result["deposit_retained"] is False
        assert "CLIENT" in appt.cancel_reason
        assert "imprevisto" in appt.cancel_reason
        # Token invalidado pela transição terminal
        assert appt.manage_token_hash is None
        assert appt.manage_token_expires_at is None
        # FSM log registrado
        log = db.add.call_args[0][0]
        assert log.to_status == "CANCELLED"
        assert log.changed_by is None  # actor CLIENT — sem user

    def test_cancel_outside_window_succeeds_with_deposit_retained(self):
        """Janela decide CONSEQUÊNCIA, não permissão: cancela e retém sinal."""
        appt = _make_appointment(start_in_hours=2)  # < 24h de antecedência
        raw = issue_manage_token(appt)
        db = _make_db(
            appointment=appt,
            deposit_policies=[_policy(hours_before=24)],
            payment=_confirmed_payment(),
        )

        result = manage_service.cancel(db, raw)

        assert appt.status == "CANCELLED"          # cancelamento OCORRE
        assert result["deposit_retained"] is True  # sinal retido

    def test_cancel_inside_window_no_retention(self):
        appt = _make_appointment(start_in_hours=72)  # > 24h de antecedência
        raw = issue_manage_token(appt)
        db = _make_db(
            appointment=appt,
            deposit_policies=[_policy(hours_before=24)],
            payment=_confirmed_payment(),
        )

        result = manage_service.cancel(db, raw)

        assert appt.status == "CANCELLED"
        assert result["deposit_retained"] is False

    def test_cancel_outside_window_without_paid_deposit_no_retention(self):
        appt = _make_appointment(start_in_hours=2)
        raw = issue_manage_token(appt)
        db = _make_db(
            appointment=appt,
            deposit_policies=[_policy(hours_before=24)],
            payment=None,  # sem sinal pago — nada a reter
        )

        result = manage_service.cancel(db, raw)
        assert result["deposit_retained"] is False

    def test_second_cancel_with_same_token_returns_404(self):
        """Idempotência: token foi invalidado no primeiro cancel."""
        appt = _make_appointment()
        raw = issue_manage_token(appt)
        db = _make_db(appointment=appt)

        manage_service.cancel(db, raw)

        with pytest.raises(HTTPException) as exc:
            manage_service.cancel(db, raw)
        assert exc.value.status_code == 404


# ─── 8–9. Reschedule ──────────────────────────────────────────────────────────

class TestReschedule:
    def test_reschedule_issues_new_token_and_invalidates_old(self):
        appt = _make_appointment()
        old_raw = issue_manage_token(appt)
        old_hash = appt.manage_token_hash
        db = _make_db(appointment=appt)
        new_dt = _future(96)
        captured = {}

        def fake_confirmation(db_, appointment, manage_token=None):
            captured["token"] = manage_token

        with patch.object(appointment_svc, "_assert_slot_available"), \
             patch.object(appointment_svc, "send_reschedule_confirmation", fake_confirmation):
            result = manage_service.reschedule(db, old_raw, new_dt)

        assert appt.start_at == new_dt
        assert result["scheduled_datetime"] == new_dt
        # Novo token gerado e enviado na mensagem; anterior inválido
        assert captured["token"] is not None
        assert appt.manage_token_hash == hash_token(captured["token"])
        assert appt.manage_token_hash != old_hash
        assert appt.manage_token_hash != hash_token(old_raw)

        # Token antigo agora é inútil
        with pytest.raises(HTTPException) as exc:
            manage_service.get_details(db, old_raw)
        assert exc.value.status_code == 404

    def test_reschedule_unavailable_slot_returns_422(self):
        appt = _make_appointment()
        raw = issue_manage_token(appt)
        db = _make_db(appointment=appt)

        def slot_taken(*args, **kwargs):
            raise HTTPException(status_code=409, detail="Horário já ocupado")

        with patch.object(appointment_svc, "_assert_slot_available", slot_taken), \
             patch.object(appointment_svc, "send_reschedule_confirmation"):
            with pytest.raises(HTTPException) as exc:
                manage_service.reschedule(db, raw, _future(96))
        assert exc.value.status_code == 422

    def test_reschedule_with_invalid_token_returns_404(self):
        db = _make_db(appointment=None)
        with pytest.raises(HTTPException) as exc:
            manage_service.reschedule(db, str(uuid.uuid4()), _future(96))
        assert exc.value.status_code == 404


# ─── 10. Invalidação em estados terminais (B5) ───────────────────────────────

class TestTerminalInvalidation:
    @pytest.mark.parametrize("terminal", [
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.NO_SHOW,
    ])
    def test_transition_to_terminal_clears_token(self, terminal):
        appt = _make_appointment(status="SCHEDULED")
        issue_manage_token(appt)
        db = MagicMock()

        transition(db, appt, terminal)

        assert appt.manage_token_hash is None
        assert appt.manage_token_expires_at is None

    def test_transition_to_in_progress_keeps_token(self):
        appt = _make_appointment(status="SCHEDULED")
        raw = issue_manage_token(appt)
        db = MagicMock()

        transition(db, appt, AppointmentStatus.IN_PROGRESS)

        assert appt.manage_token_hash == hash_token(raw)

    def test_invalidate_helper_clears_both_fields(self):
        appt = _make_appointment()
        issue_manage_token(appt)
        invalidate_manage_token(appt)
        assert appt.manage_token_hash is None
        assert appt.manage_token_expires_at is None
