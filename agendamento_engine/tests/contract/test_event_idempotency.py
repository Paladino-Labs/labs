"""Contrato 5 — Idempotência de eventos críticos.

Dois níveis:
  1. Mecanismo: is_processed/mark_processed (processed_idempotency_keys) —
     base de todos os handlers (package, subscription, nps via UNIQUE/keys).
  2. Guarda de domínio: commission_handler não duplica Commission por reprocesso
     de payment.confirmed.

A idempotência no nível do banco (UNIQUE + ON CONFLICT) é validada contra
PostgreSQL real (mecanismo aqui replica a mesma semântica em memória).
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.idempotency import is_processed, mark_processed


class TestIdempotencyMechanism:
    def test_mark_then_is_processed(self, db):
        key, consumer = "payment.confirmed:" + str(uuid.uuid4()), "commission"
        assert is_processed(key, consumer, db) is False
        mark_processed(key, consumer, uuid.uuid4(), db)
        assert is_processed(key, consumer, db) is True

    def test_double_mark_single_effect(self, db):
        """ON CONFLICT DO NOTHING — marcar duas vezes = um registro lógico."""
        key, consumer = "package.purchased:" + str(uuid.uuid4()), "package"
        mark_processed(key, consumer, uuid.uuid4(), db)
        mark_processed(key, consumer, uuid.uuid4(), db)
        assert is_processed(key, consumer, db) is True
        assert len(db._idem) == 1

    def test_distinct_consumers_independent(self, db):
        """Mesma key, consumers diferentes → processados independentemente."""
        key = "subscription.renewed:" + str(uuid.uuid4())
        mark_processed(key, "subscription", uuid.uuid4(), db)
        assert is_processed(key, "subscription", db) is True
        assert is_processed(key, "billing", db) is False


class TestCommissionHandlerIdempotency:
    def test_payment_confirmed_no_duplicate_commission(self, db, monkeypatch):
        from app.workers.handlers import commission_handler
        from app.infrastructure.db.models.payment import Payment
        from app.infrastructure.db.models.appointment import Appointment
        from app.infrastructure.db.models.commission import Commission, CommissionPolicy
        from app.infrastructure.db.models.appointment import AppointmentService

        cid, prof, svc = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        appt = Appointment(id=uuid.uuid4(), company_id=cid, professional_id=prof,
                           status="COMPLETED")
        appt.services.append(AppointmentService(service_id=svc))
        pay = Payment(payment_id=uuid.uuid4(), company_id=cid, appointment_id=appt.id,
                      gross_catalog_amount=Decimal("100"), net_charged_amount=Decimal("100"),
                      provider_fee=Decimal("3"), payment_method="CASH",
                      provider="manual", target_account_id=uuid.uuid4(), status="CONFIRMED")
        db.add(appt); db.add(pay)
        db.add(CommissionPolicy(policy_id=uuid.uuid4(), company_id=cid,
                                professional_id=prof, commission_base="GROSS_SERVICE",
                                commission_fee_policy="BARBER_PAYS", rate=Decimal("40"),
                                is_active=True))

        monkeypatch.setattr(commission_handler, "SessionLocal", lambda: db)
        monkeypatch.setattr("app.core.db_rls.set_rls_context", lambda *a, **k: None)

        event = SimpleNamespace(
            event_id=uuid.uuid4(),
            payload={"payment_id": str(pay.payment_id), "company_id": str(cid)},
        )
        commission_handler.handle_payment_confirmed_commission(event)
        commission_handler.handle_payment_confirmed_commission(event)  # reprocesso

        commissions = [c for c in db.store_for(Commission) if c.status != "REVERSED"]
        assert len(commissions) == 1
        assert commissions[0].commission_amount == Decimal("37.00")  # 40 − 3
