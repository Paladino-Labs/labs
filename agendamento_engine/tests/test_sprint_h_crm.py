"""
Testes Sprint H — CRM básico (classificações automáticas + insights heurísticos).

Usa FakeDB in-memory (padrão do projeto) — sem PostgreSQL real.

Casos obrigatórios:
  1.  Cliente sem operação há 3× a média → EM_RISCO
  2.  Cliente EM_RISCO que voltou → RECUPERADO
  3.  >= vip_min_visits E >= vip_min_spend → VIP
  4.  Thresholds customizados respeitados (frequent_min_visits=5 → precisa 5)
  5.  Recomputação idempotente: mesma classificação não duplica em < 24h
  6.  Insights determinísticos:
        RESCHEDULE após cancelamento sem remarcar
        PACKAGE após 3+ visitas ao mesmo serviço
        churn_risk HIGH para EM_RISCO
  7.  crm_alerts retorna contagens corretas
  8.  custom_fields atualizados via PATCH
  9.  notes atualizados via PATCH
  10. Cross-tenant: classificação de empresa A invisível para B
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.infrastructure.db.models import (
    Appointment, AppointmentService, CrmConfig, Customer,
    CustomerClassification, PackagePurchase, Payment, StockMovement,
)
from app.modules.crm import service as crm_service
from app.modules.customers import service as customers_service
from app.modules.customers.schemas import CustomerUpdate


def _now():
    return datetime.now(timezone.utc)


# ─── FakeDB ───────────────────────────────────────────────────────────────────

class FakeDB:
    """Roteia query(Model) para filas configuráveis de first()/all()."""

    def __init__(self, first=None, all_=None):
        self._first = {k: list(v) for k, v in (first or {}).items()}
        self._all = dict(all_ or {})
        self.added = []
        self.commits = 0

    def query(self, model, *rest):
        db = self

        class Q:
            def filter(self, *a, **k): return self
            def join(self, *a, **k): return self
            def order_by(self, *a, **k): return self
            def limit(self, n): return self

            def first(self_q):
                queue = db._first.get(model)
                return queue.pop(0) if queue else None

            def all(self_q):
                return db._all.get(model, [])

        return Q()

    def add(self, obj): self.added.append(obj)
    def commit(self): self.commits += 1
    def flush(self): pass
    def refresh(self, obj): pass
    def rollback(self): pass
    def close(self): pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _config(**over):
    base = dict(
        new_customer_days=30,
        frequent_min_visits=3,
        frequent_period_months=3,
        risk_multiplier=2.0,
        risk_min_days=45,
        vip_min_visits=10,
        vip_min_spend=500.00,
    )
    base["company_id"] = uuid.uuid4()
    base.update(over)
    return SimpleNamespace(**base)


def _metrics(**over):
    base = dict(
        visit_count=0,
        first_visit_at=None,
        last_visit_at=None,
        visit_dates=[],
        avg_frequency_days=None,
        avg_ticket=0.0,
        total_spend=0.0,
        days_since_last_visit=None,
        preferred_service_id=None,
        preferred_professional_id=None,
    )
    base.update(over)
    return base


def _appointment(status="COMPLETED", start_delta_days=0, services=None, **over):
    start = _now() - timedelta(days=start_delta_days)
    base = dict(
        id=uuid.uuid4(),
        status=status,
        start_at=start,
        cancelled_at=start if status == "CANCELLED" else None,
        professional_id=uuid.uuid4(),
        services=services or [],
    )
    base.update(over)
    return SimpleNamespace(**base)


def _service_snapshot(service_id=None):
    return SimpleNamespace(service_id=service_id or uuid.uuid4())


def _classification(classification="REGULAR", computed_delta_hours=1, **over):
    base = dict(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        classification=classification,
        computed_at=_now() - timedelta(hours=computed_delta_hours),
        metrics_snapshot={},
    )
    base.update(over)
    return SimpleNamespace(**base)


def _customer(**over):
    base = dict(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        name="Cliente Teste",
        phone="5511999990000",
        email=None,
        notes=None,
        custom_fields={},
        active=True,
    )
    base.update(over)
    return SimpleNamespace(**base)


# ─── classify_customer ────────────────────────────────────────────────────────

class TestClassifyCustomer:
    def test_sem_operacao_ha_3x_a_media_em_risco(self):
        """Média de 20 dias entre visitas, sem operação há 61 dias (>3×) → EM_RISCO."""
        metrics = _metrics(
            visit_count=4,
            last_visit_at=_now() - timedelta(days=61),
            first_visit_at=_now() - timedelta(days=121),
            avg_frequency_days=20.0,
            days_since_last_visit=61,
        )
        assert crm_service.classify_customer(metrics, _config()) == "EM_RISCO"

    def test_dentro_da_frequencia_nao_e_risco(self):
        metrics = _metrics(
            visit_count=4,
            last_visit_at=_now() - timedelta(days=10),
            first_visit_at=_now() - timedelta(days=70),
            avg_frequency_days=20.0,
            days_since_last_visit=10,
        )
        assert crm_service.classify_customer(metrics, _config()) != "EM_RISCO"

    def test_risk_min_days_e_o_piso(self):
        """Frequência média curta (5d × 2.0 = 10d) não derruba o piso de 45 dias."""
        metrics = _metrics(
            visit_count=5,
            last_visit_at=_now() - timedelta(days=30),
            first_visit_at=_now() - timedelta(days=50),
            avg_frequency_days=5.0,
            days_since_last_visit=30,
        )
        assert crm_service.classify_customer(metrics, _config()) != "EM_RISCO"

    def test_em_risco_que_voltou_recuperado(self):
        metrics = _metrics(
            visit_count=3,
            last_visit_at=_now() - timedelta(days=5),
            first_visit_at=_now() - timedelta(days=200),
            avg_frequency_days=20.0,
            days_since_last_visit=5,
        )
        result = crm_service.classify_customer(
            metrics, _config(), previous_classification="EM_RISCO"
        )
        assert result == "RECUPERADO"

    def test_em_risco_que_continua_sumido_permanece_em_risco(self):
        metrics = _metrics(
            visit_count=3,
            last_visit_at=_now() - timedelta(days=90),
            first_visit_at=_now() - timedelta(days=150),
            avg_frequency_days=20.0,
            days_since_last_visit=90,
        )
        result = crm_service.classify_customer(
            metrics, _config(), previous_classification="EM_RISCO"
        )
        assert result == "EM_RISCO"

    def test_vip_composto(self):
        metrics = _metrics(
            visit_count=12,
            total_spend=800.0,
            last_visit_at=_now() - timedelta(days=5),
            first_visit_at=_now() - timedelta(days=300),
            days_since_last_visit=5,
        )
        assert crm_service.classify_customer(metrics, _config()) == "VIP"

    def test_vip_ganha_de_em_risco(self):
        """Prioridade 1: VIP mesmo estando em risco."""
        metrics = _metrics(
            visit_count=12,
            total_spend=800.0,
            last_visit_at=_now() - timedelta(days=100),
            first_visit_at=_now() - timedelta(days=400),
            avg_frequency_days=10.0,
            days_since_last_visit=100,
        )
        assert crm_service.classify_customer(metrics, _config()) == "VIP"

    def test_visitas_sem_gasto_nao_e_vip(self):
        metrics = _metrics(
            visit_count=12,
            total_spend=100.0,
            last_visit_at=_now() - timedelta(days=5),
            first_visit_at=_now() - timedelta(days=300),
            days_since_last_visit=5,
        )
        assert crm_service.classify_customer(metrics, _config()) != "VIP"

    def test_threshold_custom_frequent_min_visits_5(self):
        """Config com frequent_min_visits=5 → 4 visitas não bastam."""
        visit_dates = [_now() - timedelta(days=d) for d in (5, 15, 25, 35)]
        metrics = _metrics(
            visit_count=4,
            visit_dates=visit_dates,
            last_visit_at=visit_dates[0],
            first_visit_at=_now() - timedelta(days=200),
            avg_frequency_days=10.0,
            days_since_last_visit=5,
        )
        custom = _config(frequent_min_visits=5)
        assert crm_service.classify_customer(metrics, custom) == "REGULAR"
        # Com o default (3), as mesmas métricas seriam FREQUENTE
        assert crm_service.classify_customer(metrics, _config()) == "FREQUENTE"

    def test_novo_primeira_visita_recente(self):
        first = _now() - timedelta(days=10)
        metrics = _metrics(
            visit_count=1,
            visit_dates=[first],
            first_visit_at=first,
            last_visit_at=first,
            days_since_last_visit=10,
        )
        assert crm_service.classify_customer(metrics, _config()) == "NOVO"

    def test_sem_historico_regular(self):
        assert crm_service.classify_customer(_metrics(), _config()) == "REGULAR"


# ─── compute_customer_metrics ─────────────────────────────────────────────────

class TestComputeMetrics:
    def test_metricas_sem_persistencia(self):
        svc = uuid.uuid4()
        prof = uuid.uuid4()
        appointments = [
            _appointment(start_delta_days=40, professional_id=prof,
                         services=[_service_snapshot(svc)]),
            _appointment(start_delta_days=20, professional_id=prof,
                         services=[_service_snapshot(svc)]),
            _appointment(start_delta_days=0, professional_id=prof,
                         services=[_service_snapshot(svc)]),
            _appointment(status="CANCELLED", start_delta_days=10),  # não conta
        ]
        payments = [
            SimpleNamespace(status="CONFIRMED", net_charged_amount=50),
            SimpleNamespace(status="CONFIRMED", net_charged_amount=70),
            SimpleNamespace(status="PENDING", net_charged_amount=999),  # não conta
        ]
        db = FakeDB(all_={Appointment: appointments, Payment: payments})

        m = crm_service.compute_customer_metrics(db, uuid.uuid4(), uuid.uuid4())

        assert m["visit_count"] == 3
        assert m["total_spend"] == 120.0
        assert m["avg_ticket"] == 60.0
        assert m["avg_frequency_days"] == pytest.approx(20.0, abs=0.1)
        assert m["days_since_last_visit"] == 0
        assert m["preferred_service_id"] == svc
        assert m["preferred_professional_id"] == prof
        assert db.added == []          # zero persistência
        assert db.commits == 0


# ─── Recomputação ─────────────────────────────────────────────────────────────

class TestRecompute:
    def _run(self, last_classification):
        customer = _customer()
        config = _config(company_id=customer.company_id)
        db = FakeDB(
            first={CrmConfig: [config], CustomerClassification: [last_classification]},
            all_={Customer: [customer], Appointment: [], Payment: []},
        )
        inserted = crm_service.recompute_all_classifications(db)
        return db, inserted

    def test_idempotente_dentro_de_24h(self):
        """Mesma classificação recomputada em < 24h → não duplica."""
        last = _classification(classification="REGULAR", computed_delta_hours=1)
        db, inserted = self._run(last)
        assert inserted == 0
        assert db.added == []

    def test_reinsere_apos_24h(self):
        last = _classification(classification="REGULAR", computed_delta_hours=30)
        db, inserted = self._run(last)
        assert inserted == 1
        assert db.added[0].classification == "REGULAR"

    def test_insere_quando_classificacao_muda(self):
        last = _classification(classification="VIP", computed_delta_hours=1)
        db, inserted = self._run(last)
        assert inserted == 1
        assert db.added[0].classification == "REGULAR"

    def test_primeira_classificacao_inserida_com_snapshot(self):
        db, inserted = self._run(None)
        assert inserted == 1
        row = db.added[0]
        assert isinstance(row, CustomerClassification)
        assert set(row.metrics_snapshot.keys()) == {
            "visit_count", "avg_ticket", "days_since_last_visit",
            "avg_frequency_days", "total_spend",
        }


# ─── Insights ─────────────────────────────────────────────────────────────────

class TestInsights:
    def test_reschedule_apos_cancelamento_sem_remarcar(self):
        cancelled = _appointment(status="CANCELLED", start_delta_days=2)
        db = FakeDB(
            first={CustomerClassification: [None]},
            all_={Appointment: [cancelled], Payment: []},
        )
        insights = crm_service.get_customer_insights(db, uuid.uuid4(), uuid.uuid4())
        types = [s["type"] for s in insights["suggestions"]]
        assert "RESCHEDULE" in types

    def test_reschedule_nao_sugerido_se_remarcou(self):
        cancelled = _appointment(status="CANCELLED", start_delta_days=2)
        rebooked = _appointment(status="SCHEDULED", start_delta_days=-3)
        db = FakeDB(
            first={CustomerClassification: [None]},
            all_={Appointment: [cancelled, rebooked], Payment: []},
        )
        insights = crm_service.get_customer_insights(db, uuid.uuid4(), uuid.uuid4())
        types = [s["type"] for s in insights["suggestions"]]
        assert "RESCHEDULE" not in types

    def test_package_apos_3_visitas_ao_mesmo_servico(self):
        svc = uuid.uuid4()
        appointments = [
            _appointment(start_delta_days=d, services=[_service_snapshot(svc)])
            for d in (10, 25, 40)
        ]
        db = FakeDB(
            first={CustomerClassification: [None]},
            all_={
                Appointment: appointments, Payment: [],
                PackagePurchase: [], AppointmentService: [], StockMovement: [],
            },
        )
        insights = crm_service.get_customer_insights(db, uuid.uuid4(), uuid.uuid4())
        package = [s for s in insights["suggestions"] if s["type"] == "PACKAGE"]
        assert len(package) == 1
        assert package[0]["service_id"] == svc

    def test_package_nao_sugerido_com_pacote_ativo(self):
        svc = uuid.uuid4()
        appointments = [
            _appointment(start_delta_days=d, services=[_service_snapshot(svc)])
            for d in (10, 25, 40)
        ]
        active_purchase = SimpleNamespace(
            status="ACTIVE", package=SimpleNamespace(service_id=svc)
        )
        db = FakeDB(
            first={CustomerClassification: [None]},
            all_={
                Appointment: appointments, Payment: [],
                PackagePurchase: [active_purchase],
                AppointmentService: [], StockMovement: [],
            },
        )
        insights = crm_service.get_customer_insights(db, uuid.uuid4(), uuid.uuid4())
        types = [s["type"] for s in insights["suggestions"]]
        assert "PACKAGE" not in types

    def test_churn_risk_high_para_em_risco(self):
        db = FakeDB(
            first={CustomerClassification: [_classification(classification="EM_RISCO")]},
            all_={Appointment: [], Payment: []},
        )
        insights = crm_service.get_customer_insights(db, uuid.uuid4(), uuid.uuid4())
        assert insights["churn_risk"] == "HIGH"

    def test_churn_risk_low_sem_historico_de_risco(self):
        db = FakeDB(
            first={CustomerClassification: [None]},
            all_={Appointment: [], Payment: []},
        )
        insights = crm_service.get_customer_insights(db, uuid.uuid4(), uuid.uuid4())
        assert insights["churn_risk"] == "LOW"

    def test_janela_de_retorno_estimada(self):
        appointments = [
            _appointment(start_delta_days=30),
            _appointment(start_delta_days=10),
        ]
        db = FakeDB(
            first={CustomerClassification: [None]},
            all_={Appointment: appointments, Payment: []},
        )
        insights = crm_service.get_customer_insights(db, uuid.uuid4(), uuid.uuid4())
        expected = appointments[1].start_at + timedelta(days=20)
        assert abs(insights["estimated_return_window"] - expected) < timedelta(seconds=1)


# ─── Alertas ──────────────────────────────────────────────────────────────────

class TestCrmAlerts:
    def test_contagens_corretas(self):
        c_risk, c_new, c_vip, c_rec = (uuid.uuid4() for _ in range(4))
        rows = [
            # mais recentes primeiro (ordem que a query desc devolve)
            _classification("EM_RISCO", computed_delta_hours=1, customer_id=c_risk,
                            metrics_snapshot={"days_since_last_visit": 80}),
            _classification("NOVO", computed_delta_hours=2, customer_id=c_new),
            _classification("VIP", computed_delta_hours=3, customer_id=c_vip),
            _classification("RECUPERADO", computed_delta_hours=4, customer_id=c_rec),
            # linha antiga do mesmo customer — ignorada (append-only, histórico)
            _classification("VIP", computed_delta_hours=48, customer_id=c_risk),
        ]
        db = FakeDB(all_={CustomerClassification: rows})

        alerts = crm_service.get_crm_alerts(db, uuid.uuid4())

        assert alerts["at_risk_count"] == 1
        assert alerts["vip_count"] == 1
        assert alerts["recovered_this_week"] == 1
        assert alerts["at_risk_customers"][0]["customer_id"] == c_risk
        assert alerts["at_risk_customers"][0]["days_since_last_visit"] == 80

    def test_sem_classificacoes_zerado(self):
        db = FakeDB(all_={CustomerClassification: []})
        alerts = crm_service.get_crm_alerts(db, uuid.uuid4())
        assert alerts["at_risk_count"] == 0
        assert alerts["new_this_month"] == 0
        assert alerts["vip_count"] == 0
        assert alerts["recovered_this_week"] == 0
        assert alerts["at_risk_customers"] == []


# ─── PATCH custom_fields / notes ──────────────────────────────────────────────

class TestCustomerCuratedData:
    def test_patch_custom_fields(self):
        customer = _customer()
        db = FakeDB(first={Customer: [customer]})
        customers_service.update_customer(
            db, customer.company_id, customer.id,
            CustomerUpdate(custom_fields={"preferencia": "navalha", "indicado_por": "João"}),
        )
        assert customer.custom_fields == {"preferencia": "navalha", "indicado_por": "João"}
        assert db.commits == 1

    def test_patch_notes(self):
        customer = _customer()
        db = FakeDB(first={Customer: [customer]})
        customers_service.update_customer(
            db, customer.company_id, customer.id,
            CustomerUpdate(notes="Alérgico a talco"),
        )
        assert customer.notes == "Alérgico a talco"

    def test_patch_parcial_nao_apaga_outros_campos(self):
        customer = _customer(notes="já existia", custom_fields={"a": 1})
        db = FakeDB(first={Customer: [customer]})
        customers_service.update_customer(
            db, customer.company_id, customer.id,
            CustomerUpdate(custom_fields={"b": 2}),
        )
        assert customer.notes == "já existia"
        assert customer.custom_fields == {"b": 2}


# ─── Cross-tenant ─────────────────────────────────────────────────────────────

class TestCrossTenant:
    def test_classificacao_de_outra_empresa_404(self):
        """Customer da empresa A consultado com company_id da B → 404
        (filtro company_id em get_customer_or_404 antes de qualquer insight)."""
        from app.modules.customers.router import get_customer_classification

        db = FakeDB(first={Customer: [None]})
        with pytest.raises(HTTPException) as exc:
            get_customer_classification(
                customer_id=uuid.uuid4(),
                current_user=SimpleNamespace(company_id=uuid.uuid4()),
                db=db,
            )
        assert exc.value.status_code == 404

    def test_insights_de_outra_empresa_404(self):
        from app.modules.customers.router import get_customer_insights

        db = FakeDB(first={Customer: [None]})
        with pytest.raises(HTTPException) as exc:
            get_customer_insights(
                customer_id=uuid.uuid4(),
                current_user=SimpleNamespace(company_id=uuid.uuid4()),
                db=db,
            )
        assert exc.value.status_code == 404


# ─── Worker ───────────────────────────────────────────────────────────────────

class TestWorkerSchedule:
    def test_beat_schedule_crm_as_3h(self):
        pytest.importorskip("celery")
        from celery.schedules import crontab
        from app.workers.beat_schedule import beat_schedule

        entry = beat_schedule["crm-recompute-classifications"]
        assert entry["task"] == "app.workers.tasks.crm_recompute.crm_recompute_worker"
        assert entry["schedule"] == crontab(hour=3, minute=0)
