"""Contrato 4 — Comissão em dois eixos (commission_base × commission_fee_policy).

Eixos de fee_policy reais: BARBERSHOP_PAYS | SPLIT_50_50 | BARBER_PAYS.
gross=100, fee=3, rate=40% → gross_commission=40.
"""
import uuid
from decimal import Decimal

from app.infrastructure.db.models.commission import Commission, CommissionPolicy
from app.modules.commission import service as commission_service


def _policy(company_id, fee_policy, rate=Decimal("40"), professional_id=None,
            service_id=None, commission_base="GROSS_SERVICE"):
    return CommissionPolicy(
        policy_id=uuid.uuid4(),
        company_id=company_id,
        professional_id=professional_id,
        service_id=service_id,
        commission_base=commission_base,
        commission_fee_policy=fee_policy,
        rate=rate,
        is_active=True,
    )


def _calc(db, company_id, professional_id, gross, fee, service_id=None):
    return commission_service.calculate_commission(
        professional_id=professional_id,
        service_id=service_id,
        gross_amount=Decimal(str(gross)),
        provider_fee=Decimal(str(fee)),
        operation_type="SERVICE_RENDERED",
        appointment_id=uuid.uuid4(),
        company_id=company_id,
        db=db,
    )


class TestCommissionContract:
    def test_barbershop_pays(self, db):
        cid, prof = uuid.uuid4(), uuid.uuid4()
        db.add(_policy(cid, "BARBERSHOP_PAYS", professional_id=prof))
        c = _calc(db, cid, prof, 100, 3)
        assert c.commission_amount == Decimal("40.00")

    def test_split_50_50(self, db):
        cid, prof = uuid.uuid4(), uuid.uuid4()
        db.add(_policy(cid, "SPLIT_50_50", professional_id=prof))
        c = _calc(db, cid, prof, 100, 3)
        assert c.commission_amount == Decimal("38.50")

    def test_barber_pays(self, db):
        cid, prof = uuid.uuid4(), uuid.uuid4()
        db.add(_policy(cid, "BARBER_PAYS", professional_id=prof))
        c = _calc(db, cid, prof, 100, 3)
        assert c.commission_amount == Decimal("37.00")

    def test_commission_never_negative(self, db):
        """fee > gross_commission → commission_amount = 0.00."""
        cid, prof = uuid.uuid4(), uuid.uuid4()
        db.add(_policy(cid, "BARBER_PAYS", rate=Decimal("10"), professional_id=prof))
        c = _calc(db, cid, prof, 100, 50)  # gross_comm=10, fee=50 → 0
        assert c.commission_amount == Decimal("0.00")

    def test_policy_priority_specific_over_global(self, db):
        """Política (prof+serviço) ganha sobre a global do tenant."""
        cid, prof, svc = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        db.add(_policy(cid, "BARBERSHOP_PAYS", rate=Decimal("10")))  # global
        db.add(_policy(cid, "BARBERSHOP_PAYS", rate=Decimal("40"),
                       professional_id=prof, service_id=svc))         # específica
        c = _calc(db, cid, prof, 100, 0, service_id=svc)
        assert c.commission_amount == Decimal("40.00")

    def test_multi_tenant_isolation(self, db):
        """Cada comissão usa a política do próprio tenant."""
        a, b = uuid.uuid4(), uuid.uuid4()
        pa, pb = uuid.uuid4(), uuid.uuid4()
        db.add(_policy(a, "BARBERSHOP_PAYS", rate=Decimal("40"), professional_id=pa))
        db.add(_policy(b, "BARBERSHOP_PAYS", rate=Decimal("20"), professional_id=pb))
        ca = _calc(db, a, pa, 100, 0)
        cb = _calc(db, b, pb, 100, 0)
        assert ca.commission_amount == Decimal("40.00")
        assert cb.commission_amount == Decimal("20.00")

    def test_no_policy_returns_none(self, db):
        """Sem política ativa → None (sem erro)."""
        assert _calc(db, uuid.uuid4(), uuid.uuid4(), 100, 3) is None

    def test_commission_persisted_with_real_fee(self, db):
        """Comissão registrada com provider_fee real (não 0)."""
        cid, prof = uuid.uuid4(), uuid.uuid4()
        db.add(_policy(cid, "BARBER_PAYS", professional_id=prof))
        c = _calc(db, cid, prof, 100, 3)
        assert c in db.store_for(Commission)
        assert c.status == "CALCULATED"
        assert c.commission_amount == Decimal("37.00")  # 40 − 3 (fee real)
