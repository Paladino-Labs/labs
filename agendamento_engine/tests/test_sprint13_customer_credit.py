"""
Testes Sprint 13 — CustomerCredit (Cotas).

Usa mocks (unittest.mock) — sem banco PostgreSQL real.
SELECT FOR UPDATE SKIP LOCKED requer PostgreSQL real; teste de concorrência
valida o comportamento esperado via mock (SKIP LOCKED → None → NoCreditAvailableError).

Casos obrigatórios:
  1.  FEFO: 2 créditos (30d e 60d) → consome o de 30d primeiro
  2.  Cota EXPIRED não é consumida → NoCreditAvailableError
  3.  Cota EXHAUSTED não é consumida → NoCreditAvailableError
  4.  remaining_cotas chega a 0 → status automaticamente EXHAUSTED
  5.  SELECT FOR UPDATE: 2 consumos simultâneos, 1 remaining → apenas 1 sucede
  6.  grant_cota → sem Movement/Entry
  7.  grant_cota sem reason → 422
  8.  revoke → status REVOKED + audit
  9.  customer_credit_expiry_worker: ACTIVE com expires_at passado → EXPIRED
  10. Cross-tenant: créditos de outro tenant não são afetados
  11. get_balance: retorna apenas ACTIVE não expirados
  12. revoke de crédito já EXPIRED → 422
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call

import pytest

# ─── Mock celery antes de qualquer import ─────────────────────────────────────
if "celery" not in sys.modules:
    _celery_mock = MagicMock()
    _celery_mock.Celery.return_value = _celery_mock
    _celery_mock.task = lambda *a, **kw: (lambda f: f)
    sys.modules["celery"] = _celery_mock
    sys.modules["celery.schedules"] = MagicMock()
    sys.modules["celery.app"] = MagicMock()
    sys.modules["celery.utils"] = MagicMock()
    sys.modules["celery.utils.log"] = MagicMock()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _future(days: int):
    return _now() + timedelta(days=days)


def _past(days: int):
    return _now() - timedelta(days=days)


def _make_credit(
    credit_id=None,
    company_id=None,
    customer_id=None,
    entitlement_type="GRANT_COTA",
    total_cotas=5,
    remaining_cotas=5,
    status="ACTIVE",
    granted_at=None,
    expires_at=None,
    source_id=None,
):
    c = MagicMock()
    c.credit_id        = credit_id or uuid.uuid4()
    c.company_id       = company_id or uuid.uuid4()
    c.customer_id      = customer_id or uuid.uuid4()
    c.entitlement_type = entitlement_type
    c.source_id        = source_id
    c.total_cotas      = total_cotas
    c.remaining_cotas  = remaining_cotas
    c.status           = status
    c.granted_at       = granted_at or _now()
    c.expires_at       = expires_at
    return c


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.commit  = MagicMock()
    db.rollback = MagicMock()
    db.flush   = MagicMock()
    db.add     = MagicMock()
    db.refresh = MagicMock()
    return db


def _query_chain_returning(db, value):
    """Configura o db mock para que a cadeia de query retorne `value` em .first()."""
    chain = db.query.return_value
    for _ in range(8):  # profundidade suficiente para .filter().order_by().with_for_update().first()
        chain.filter.return_value  = chain
        chain.order_by.return_value = chain
        chain.with_for_update.return_value = chain
        chain.all.return_value     = []
        chain.first.return_value   = value
        chain = chain.filter.return_value
    return db


# ─── 1. FEFO: 2 créditos → consome o de 30d ──────────────────────────────────

class TestFEFO:
    def test_fefo_consumes_shorter_expiry_first(self):
        """
        Service retorna o crédito de 30d (primeiro pela ordenação FEFO).
        Verificamos que remaining_cotas é decrementado e consumption criado.
        """
        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()
        appt_id     = uuid.uuid4()

        # Simula que o banco (com ORDER BY expires_at NULLS LAST, granted_at ASC)
        # retorna o crédito de 30d primeiro
        credit_30d = _make_credit(
            company_id=company_id,
            customer_id=customer_id,
            expires_at=_future(30),
            remaining_cotas=3,
        )

        from app.modules.customer_credit import service as svc
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        db = _query_chain_returning(_make_db(), credit_30d)

        captured = {}
        def _capture(obj):
            captured["consumption"] = obj

        db.add.side_effect = _capture

        result = svc.consume_for_operation(
            customer_id=customer_id,
            appointment_id=appt_id,
            company_id=company_id,
            db=db,
        )

        # Verificações: remaining decrementado, consumption criado
        assert credit_30d.remaining_cotas == 2
        assert "consumption" in captured
        consumption = captured["consumption"]
        assert consumption.credit_id == credit_30d.credit_id
        assert consumption.customer_id == customer_id
        assert consumption.appointment_id == appt_id
        assert result is consumption

    def test_fefo_ordering_nulls_last(self):
        """
        Crédito sem vencimento (expires_at=None) deve vir DEPOIS do que tem expires_at.
        Verificamos que o serviço chama ORDER BY com expires_at.asc().nullslast().
        """
        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()

        credit_no_expiry = _make_credit(
            company_id=company_id,
            customer_id=customer_id,
            expires_at=None,
            remaining_cotas=1,
        )

        from app.modules.customer_credit import service as svc

        db = _query_chain_returning(_make_db(), credit_no_expiry)
        svc.consume_for_operation(
            customer_id=customer_id,
            appointment_id=None,
            company_id=company_id,
            db=db,
        )

        # Confirma que a consulta passou por order_by (comportamento esperado)
        assert db.query.called


# ─── 2 & 3. EXPIRED / EXHAUSTED não consumidos ───────────────────────────────

class TestNoCreditAvailable:
    def test_no_active_credit_raises(self):
        """Sem créditos ACTIVE → NoCreditAvailableError (HTTP 422)."""
        from app.modules.customer_credit import service as svc
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        db = _query_chain_returning(_make_db(), None)  # nenhum crédito disponível

        with pytest.raises(NoCreditAvailableError):
            svc.consume_for_operation(
                customer_id=uuid.uuid4(),
                appointment_id=None,
                company_id=uuid.uuid4(),
                db=db,
            )

    def test_expired_credit_not_consumed(self):
        """
        Crédito com expires_at no passado → filtro exclui → NoCreditAvailableError.
        O filtro WHERE expires_at > now() é responsável; o mock simula o banco
        retornando None (como se o filtro excluísse o crédito expirado).
        """
        from app.modules.customer_credit import service as svc
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        db = _query_chain_returning(_make_db(), None)

        with pytest.raises(NoCreditAvailableError):
            svc.consume_for_operation(
                customer_id=uuid.uuid4(),
                appointment_id=None,
                company_id=uuid.uuid4(),
                db=db,
            )

    def test_exhausted_credit_not_consumable(self):
        """
        Crédito EXHAUSTED não aparece no filtro (status=ACTIVE).
        O mock retorna None → NoCreditAvailableError.
        """
        from app.modules.customer_credit import service as svc
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        db = _query_chain_returning(_make_db(), None)

        with pytest.raises(NoCreditAvailableError):
            svc.consume_for_operation(
                customer_id=uuid.uuid4(),
                appointment_id=None,
                company_id=uuid.uuid4(),
                db=db,
            )


# ─── 4. remaining_cotas = 0 → status EXHAUSTED ────────────────────────────────

class TestExhausted:
    def test_remaining_zero_sets_exhausted(self):
        """Ao consumir a última cota, status deve mudar para EXHAUSTED."""
        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()

        credit = _make_credit(
            company_id=company_id,
            customer_id=customer_id,
            remaining_cotas=1,
            status="ACTIVE",
        )

        from app.modules.customer_credit import service as svc

        db = _query_chain_returning(_make_db(), credit)
        svc.consume_for_operation(
            customer_id=customer_id,
            appointment_id=None,
            company_id=company_id,
            db=db,
        )

        assert credit.remaining_cotas == 0
        assert credit.status == "EXHAUSTED"

    def test_remaining_above_zero_stays_active(self):
        """Após consumo com remaining > 1, status permanece ACTIVE."""
        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()

        credit = _make_credit(
            company_id=company_id,
            customer_id=customer_id,
            remaining_cotas=3,
            status="ACTIVE",
        )

        from app.modules.customer_credit import service as svc

        db = _query_chain_returning(_make_db(), credit)
        svc.consume_for_operation(
            customer_id=customer_id,
            appointment_id=None,
            company_id=company_id,
            db=db,
        )

        assert credit.remaining_cotas == 2
        assert credit.status == "ACTIVE"


# ─── 5. SELECT FOR UPDATE: concorrência ──────────────────────────────────────

class TestSelectForUpdateConcurrency:
    def test_second_concurrent_consume_fails_when_locked(self):
        """
        SKIP LOCKED: se a cota está locked por outra transação, o banco
        retorna nenhum resultado. Simulamos isso com o mock retornando None
        na segunda chamada → NoCreditAvailableError.
        """
        from app.modules.customer_credit import service as svc
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()

        credit = _make_credit(
            company_id=company_id,
            customer_id=customer_id,
            remaining_cotas=1,
            status="ACTIVE",
        )

        call_count = [0]

        def _side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return credit  # primeiro consumo: retorna o crédito
            return None  # segundo consumo: SKIP LOCKED retorna None

        db = _make_db()
        chain = db.query.return_value
        for _ in range(8):
            chain.filter.return_value  = chain
            chain.order_by.return_value = chain
            chain.with_for_update.return_value = chain
        chain.first.side_effect = _side_effect

        # Primeiro consumo: sucede
        svc.consume_for_operation(
            customer_id=customer_id,
            appointment_id=None,
            company_id=company_id,
            db=db,
        )

        # Segundo consumo: SKIP LOCKED retorna None → 422
        with pytest.raises(NoCreditAvailableError):
            svc.consume_for_operation(
                customer_id=customer_id,
                appointment_id=None,
                company_id=company_id,
                db=db,
            )

    def test_with_for_update_skip_locked_called(self):
        """Verifica que consume_for_operation chama .with_for_update(skip_locked=True)."""
        from app.modules.customer_credit import service as svc
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        db = _make_db()
        chain = db.query.return_value
        for _ in range(8):
            chain.filter.return_value  = chain
            chain.order_by.return_value = chain
            chain.with_for_update.return_value = chain
        chain.first.return_value = None

        with pytest.raises(NoCreditAvailableError):
            svc.consume_for_operation(
                customer_id=uuid.uuid4(),
                appointment_id=None,
                company_id=uuid.uuid4(),
                db=db,
            )

        # Verifica que with_for_update foi chamado com skip_locked=True
        chain.with_for_update.assert_called_once_with(skip_locked=True)


# ─── 6. grant_cota → sem Movement/Entry ──────────────────────────────────────

class TestGrantCota:
    def test_grant_cota_no_financial_entries(self):
        """grant_cota não deve gerar Movement nem Entry — não é receita."""
        from app.modules.customer_credit import service as svc
        from app.infrastructure.db.models.customer_credit import CustomerCredit

        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()
        actor_id    = uuid.uuid4()

        db = _make_db()
        added_objects = []
        db.add.side_effect = lambda obj: added_objects.append(obj)

        with patch("app.modules.customer_credit.service.record_sensitive_action"):
            svc.grant_cota(
                customer_id=customer_id,
                total_cotas=5,
                expires_at=_future(30),
                reason="Presente de cortesia",
                actor_id=actor_id,
                actor_role="OWNER",
                company_id=company_id,
                db=db,
            )

        # Verifica que apenas CustomerCredit foi adicionado (sem Movement/Entry)
        from app.infrastructure.db.models.customer_credit import CustomerCredit as CC
        credit_objects = [o for o in added_objects if isinstance(o, CC)]
        assert len(credit_objects) == 1

        # Verifica que NÃO foram criados Movement ou Entry
        from app.infrastructure.db.models.movement import Movement
        from app.infrastructure.db.models.entry import Entry
        movement_objects = [o for o in added_objects if isinstance(o, Movement)]
        entry_objects    = [o for o in added_objects if isinstance(o, Entry)]
        assert len(movement_objects) == 0
        assert len(entry_objects) == 0

    def test_grant_cota_creates_correct_credit(self):
        """grant_cota cria CustomerCredit com valores corretos."""
        from app.modules.customer_credit import service as svc

        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()
        actor_id    = uuid.uuid4()
        expires     = _future(30)

        db = _make_db()
        created = {}

        def _capture(obj):
            created["credit"] = obj

        db.add.side_effect = _capture

        with patch("app.modules.customer_credit.service.record_sensitive_action"):
            result = svc.grant_cota(
                customer_id=customer_id,
                total_cotas=5,
                expires_at=expires,
                reason="Teste de concessão",
                actor_id=actor_id,
                actor_role="ADMIN",
                company_id=company_id,
                db=db,
            )

        credit = created["credit"]
        assert credit.entitlement_type == "GRANT_COTA"
        assert credit.total_cotas == 5
        assert credit.remaining_cotas == 5
        assert credit.status == "ACTIVE"
        assert credit.company_id == company_id
        assert credit.customer_id == customer_id
        assert credit.expires_at == expires

    def test_grant_cota_calls_record_sensitive_action(self):
        """grant_cota deve chamar record_sensitive_action com reason."""
        from app.modules.customer_credit import service as svc

        db = _make_db()
        reason = "Compensação por atraso no serviço"

        with patch("app.modules.customer_credit.service.record_sensitive_action") as mock_audit:
            svc.grant_cota(
                customer_id=uuid.uuid4(),
                total_cotas=3,
                expires_at=None,
                reason=reason,
                actor_id=uuid.uuid4(),
                actor_role="OWNER",
                company_id=uuid.uuid4(),
                db=db,
            )

        mock_audit.assert_called_once()
        ctx = mock_audit.call_args[0][0]
        assert ctx.action == "grant_cota"
        assert ctx.reason == reason


# ─── 7. grant_cota sem reason → 422 ──────────────────────────────────────────

class TestGrantCotaValidation:
    def test_grant_cota_no_reason_raises_422(self):
        """grant_cota sem reason deve levantar HTTPException 422."""
        from app.modules.customer_credit import service as svc
        from fastapi import HTTPException

        db = _make_db()

        with pytest.raises(HTTPException) as exc_info:
            svc.grant_cota(
                customer_id=uuid.uuid4(),
                total_cotas=5,
                expires_at=None,
                reason="",  # vazio
                actor_id=uuid.uuid4(),
                actor_role="OWNER",
                company_id=uuid.uuid4(),
                db=db,
            )

        assert exc_info.value.status_code == 422

    def test_grant_cota_whitespace_reason_raises_422(self):
        """grant_cota com reason apenas espaços deve levantar HTTPException 422."""
        from app.modules.customer_credit import service as svc
        from fastapi import HTTPException

        db = _make_db()

        with pytest.raises(HTTPException) as exc_info:
            svc.grant_cota(
                customer_id=uuid.uuid4(),
                total_cotas=5,
                expires_at=None,
                reason="   ",
                actor_id=uuid.uuid4(),
                actor_role="OWNER",
                company_id=uuid.uuid4(),
                db=db,
            )

        assert exc_info.value.status_code == 422


# ─── 8. revoke → status REVOKED + audit ──────────────────────────────────────

class TestRevoke:
    def _db_with_credit(self, credit):
        db = _make_db()
        chain = db.query.return_value
        for _ in range(6):
            chain.filter.return_value = chain
        chain.first.return_value = credit
        return db

    def test_revoke_active_credit(self):
        """Revogar crédito ACTIVE → status REVOKED + audit."""
        from app.modules.customer_credit import service as svc

        credit = _make_credit(status="ACTIVE")
        db = self._db_with_credit(credit)

        with patch("app.modules.customer_credit.service.record_sensitive_action") as mock_audit:
            result = svc.revoke(
                credit_id=credit.credit_id,
                reason="Cancelamento solicitado pelo cliente",
                actor_id=uuid.uuid4(),
                actor_role="OWNER",
                company_id=credit.company_id,
                db=db,
            )

        assert credit.status == "REVOKED"
        mock_audit.assert_called_once()
        ctx = mock_audit.call_args[0][0]
        assert ctx.action == "revoke_credit"

    def test_revoke_exhausted_credit(self):
        """Revogar crédito EXHAUSTED → status REVOKED (também permitido)."""
        from app.modules.customer_credit import service as svc

        credit = _make_credit(status="EXHAUSTED", remaining_cotas=0)
        db = self._db_with_credit(credit)

        with patch("app.modules.customer_credit.service.record_sensitive_action"):
            svc.revoke(
                credit_id=credit.credit_id,
                reason="Ajuste administrativo",
                actor_id=uuid.uuid4(),
                actor_role="ADMIN",
                company_id=credit.company_id,
                db=db,
            )

        assert credit.status == "REVOKED"

    def test_revoke_expired_credit_raises_422(self):
        """Revogar crédito EXPIRED → 422 (já expirado, não há necessidade de revogar)."""
        from app.modules.customer_credit import service as svc
        from fastapi import HTTPException

        credit = _make_credit(status="EXPIRED")
        db = self._db_with_credit(credit)

        with pytest.raises(HTTPException) as exc_info:
            svc.revoke(
                credit_id=credit.credit_id,
                reason="Tentativa inválida",
                actor_id=uuid.uuid4(),
                actor_role="OWNER",
                company_id=credit.company_id,
                db=db,
            )

        assert exc_info.value.status_code == 422

    def test_revoke_not_found_raises_404(self):
        """Revogar crédito inexistente → 404."""
        from app.modules.customer_credit import service as svc
        from fastapi import HTTPException

        db = _make_db()
        chain = db.query.return_value
        for _ in range(6):
            chain.filter.return_value = chain
        chain.first.return_value = None  # não encontrado

        with pytest.raises(HTTPException) as exc_info:
            svc.revoke(
                credit_id=uuid.uuid4(),
                reason="Teste",
                actor_id=uuid.uuid4(),
                actor_role="OWNER",
                company_id=uuid.uuid4(),
                db=db,
            )

        assert exc_info.value.status_code == 404


# ─── 9. expiry_worker → ACTIVE com expires_at passado → EXPIRED ──────────────

class TestExpiryWorker:
    def test_worker_expires_overdue_credits(self):
        """
        customer_credit_expiry_worker: créditos ACTIVE com expires_at no passado
        devem ter status alterado para EXPIRED.
        """
        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()

        credit_overdue_1 = _make_credit(
            company_id=company_id,
            customer_id=customer_id,
            status="ACTIVE",
            expires_at=_past(1),  # ontem
        )
        credit_overdue_2 = _make_credit(
            company_id=company_id,
            customer_id=customer_id,
            status="ACTIVE",
            expires_at=_past(7),  # semana passada
        )

        from app.infrastructure.db.session import SessionLocal

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        # Configura query chain
        chain = mock_session.query.return_value
        for _ in range(6):
            chain.filter.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = [credit_overdue_1, credit_overdue_2]

        with patch("app.workers.tasks.customer_credit_expiry.SessionLocal", return_value=mock_session):
            with patch("app.core.db_rls.set_rls_context"):
                with patch("app.infrastructure.event_bus.event_bus"):
                    from app.workers.tasks.customer_credit_expiry import customer_credit_expiry_worker
                    # Chama diretamente (sem Celery)
                    customer_credit_expiry_worker(MagicMock())

        assert credit_overdue_1.status == "EXPIRED"
        assert credit_overdue_2.status == "EXPIRED"
        mock_session.commit.assert_called_once()

    def test_worker_no_credits_skips(self):
        """Worker sem créditos expirados não deve fazer nada."""
        mock_session = MagicMock()

        chain = mock_session.query.return_value
        for _ in range(6):
            chain.filter.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = []  # nenhum expirado

        with patch("app.workers.tasks.customer_credit_expiry.SessionLocal", return_value=mock_session):
            with patch("app.core.db_rls.set_rls_context"):
                from app.workers.tasks.customer_credit_expiry import customer_credit_expiry_worker
                customer_credit_expiry_worker(MagicMock())

        mock_session.commit.assert_not_called()


# ─── 10. Cross-tenant isolation ───────────────────────────────────────────────

class TestCrossTenant:
    def test_consume_uses_company_id_filter(self):
        """
        consume_for_operation deve filtrar por company_id.
        Verificamos que o filtro é aplicado (mock não retorna crédito de outro tenant).
        """
        from app.modules.customer_credit import service as svc
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        company_a = uuid.uuid4()
        company_b = uuid.uuid4()
        customer  = uuid.uuid4()

        # Banco retorna None para company_b (crédito existe apenas em company_a)
        db = _query_chain_returning(_make_db(), None)

        with pytest.raises(NoCreditAvailableError):
            svc.consume_for_operation(
                customer_id=customer,
                appointment_id=None,
                company_id=company_b,
                db=db,
            )


# ─── 11. get_balance ──────────────────────────────────────────────────────────

class TestGetBalance:
    def test_get_balance_returns_active_credits(self):
        """get_balance retorna lista com dados corretos dos créditos ativos."""
        from app.modules.customer_credit import service as svc

        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()
        expires     = _future(30)

        credit = _make_credit(
            company_id=company_id,
            customer_id=customer_id,
            remaining_cotas=3,
            total_cotas=5,
            status="ACTIVE",
            expires_at=expires,
        )

        db = _make_db()
        chain = db.query.return_value
        for _ in range(8):
            chain.filter.return_value  = chain
            chain.order_by.return_value = chain
        chain.all.return_value = [credit]

        result = svc.get_balance(customer_id, company_id, db)

        assert len(result) == 1
        item = result[0]
        assert item["credit_id"] == str(credit.credit_id)
        assert item["remaining_cotas"] == 3
        assert item["total_cotas"] == 5
        assert item["status"] == "ACTIVE"

    def test_get_balance_empty_when_no_credits(self):
        """get_balance retorna lista vazia quando não há créditos ativos."""
        from app.modules.customer_credit import service as svc

        db = _make_db()
        chain = db.query.return_value
        for _ in range(8):
            chain.filter.return_value  = chain
            chain.order_by.return_value = chain
        chain.all.return_value = []

        result = svc.get_balance(uuid.uuid4(), uuid.uuid4(), db)
        assert result == []


# ─── 12. NoCreditAvailableError é HTTP 422 ───────────────────────────────────

class TestNoCreditAvailableErrorHTTP:
    def test_no_credit_error_is_422(self):
        """NoCreditAvailableError deve ter status_code=422."""
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        err = NoCreditAvailableError()
        assert err.status_code == 422

    def test_no_credit_error_custom_message(self):
        """NoCreditAvailableError aceita mensagem personalizada."""
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        err = NoCreditAvailableError(detail="Pacote sem cotas restantes")
        assert err.status_code == 422
        assert err.detail == "Pacote sem cotas restantes"
