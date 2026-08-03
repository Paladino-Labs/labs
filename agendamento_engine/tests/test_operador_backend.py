"""S-operador (backend) — rotas e guards do perfil de balcão.

Princípio verificado aqui: **o operador vê a operação corrente (o dia); o dono
vê o acumulado.**

Casos cobertos:
  1.  Caminho do balcão: OPERATOR passa nos 3 guards (POST /payments →
      confirm-manual → PATCH /complete) e o pagamento termina CONFIRMED
  2.  confirm_manual do OPERATOR não deixa Payment PENDING órfão
  3.  GET /payments/today NÃO tem parâmetro de data (a prova da escolha (b))
  4.  /payments/today é declarada ANTES de /payments/{payment_id}
  5.  current_day_bounds_utc recorta o dia CIVIL DO TENANT, não o dia UTC
  6.  list_payments_for_day casa por created_at OU paid_at, dentro da janela
  7.  Continua fechado ao OPERATOR: GET /payments, manual-discount, refund,
      dre, movements, entries, commissions, accounts/{id}/balance
  8.  A proteção real sobrevive: confirm_manual não-CASH/manual → 422
  9.  Sem regressão: OWNER/ADMIN aceitos em tudo que foi tocado
  10. GET /financial/accounts aberto ao OPERATOR (cadastro, sem valor)

⚠️ Este arquivo NÃO importa `app.main` — importar antes de `test_sprint2_rbac`
quebra o monkey-patch de modelos daquele arquivo. Imports ficam dentro dos
testes, como em `test_cash_payment.py`.
"""
import inspect
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _user(role, company_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        company_id=company_id or uuid.uuid4(),
    )


def _guard_of(endpoint, param_name):
    """Extrai o callable de `Depends(...)` realmente wired no endpoint.

    Lê a assinatura da função registrada — não uma redeclaração no teste. Se
    alguém trocar o guard da rota, estes testes falham.
    """
    depends_obj = inspect.signature(endpoint).parameters[param_name].default
    return depends_obj.dependency


def _assert_allows(endpoint, param_name, role):
    guard = _guard_of(endpoint, param_name)
    user = _user(role)
    assert guard(user=user) is user, f"{role} deveria passar em {endpoint.__name__}"


def _assert_sem_restricao_de_papel(endpoint, param_name):
    """A rota autentica, mas não filtra papel — qualquer usuário do tenant passa."""
    guard = _guard_of(endpoint, param_name)
    assert guard.__name__ == "get_current_user", (
        f"{endpoint.__name__} passou a restringir papel — reavaliar o balcão"
    )


def _assert_denies(endpoint, param_name, role):
    guard = _guard_of(endpoint, param_name)
    with pytest.raises(HTTPException) as exc:
        guard(user=_user(role))
    assert exc.value.status_code == 403, (
        f"{role} deveria tomar 403 em {endpoint.__name__}"
    )


def _make_payment(
    payment_id=None,
    company_id=None,
    status="PENDING",
    payment_method="CASH",
    provider="manual",
    net_charged_amount=Decimal("80.00"),
):
    p = MagicMock()
    p.payment_id = payment_id or uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.status = status
    p.payment_method = payment_method
    p.payment_submethod = None
    p.provider = provider
    p.net_charged_amount = Decimal(str(net_charged_amount))
    p.gross_catalog_amount = Decimal(str(net_charged_amount))
    p.provider_fee = Decimal("0.00")
    p.target_account_id = uuid.uuid4()
    p.external_charge_id = None
    p.paid_at = None
    p._sa_instance_state = MagicMock()
    p._sa_instance_state.has_identity = False
    return p


def _db_with_timezone(tz_name):
    """DB stub cujo TenantConfig devolve o timezone informado."""
    db = MagicMock()
    config = SimpleNamespace(timezone=tz_name)
    db.query.return_value.filter.return_value.first.return_value = config
    return db


# ─────────────────────────────────────────────────────────────────────────────
# 1. Caminho do balcão — OPERATOR passa nos 3 guards
# ─────────────────────────────────────────────────────────────────────────────

class TestBalcaoPodeCobrar:
    def test_operator_passa_nos_tres_guards_do_fluxo(self):
        """POST /payments → confirm-manual → PATCH /complete, todos abertos.

        Era o passo 2 que quebrava: `confirm-manual` em `_owner_admin` fazia o
        dialog do painel abortar depois de já ter criado o Payment.
        """
        from app.modules.appointments.router import complete_appointment
        from app.modules.payments.router import confirm_manual_payment, create_payment

        # Passos 1 e 3 nunca restringiram papel — só autenticam.
        _assert_sem_restricao_de_papel(create_payment, "user")
        _assert_sem_restricao_de_papel(complete_appointment, "user")
        # Passo 2 é o que mudou neste sprint.
        _assert_allows(confirm_manual_payment, "user", "OPERATOR")

    def test_operator_confirma_pagamento_cash(self):
        """O confirm_manual do balcão leva o Payment a CONFIRMED."""
        company_id = uuid.uuid4()
        payment = _make_payment(company_id=company_id)
        confirmed = _make_payment(
            payment_id=payment.payment_id, company_id=company_id, status="CONFIRMED"
        )

        with patch("app.modules.payments.service._get_payment", return_value=payment), \
             patch("app.modules.payments.service.confirm", return_value=confirmed) as mock_confirm:
            from app.modules.payments.service import confirm_manual

            result, fee_warning = confirm_manual(
                payment_id=payment.payment_id,
                company_id=company_id,
                db=MagicMock(),
            )

        assert result.status == "CONFIRMED"
        assert fee_warning is None
        # event_id determinístico preservado (idempotência do re-submit)
        assert mock_confirm.call_args.kwargs["event_id"] == f"manual-{payment.payment_id}"

    def test_nao_sobra_payment_pendente_orfao(self):
        """Com o guard aberto, o Payment criado no passo 1 é confirmado no 2.

        O órfão nascia do 403: o POST /payments passava, o confirm-manual não, e
        o PENDING ficava para sempre com o agendamento ainda SCHEDULED.
        """
        company_id = uuid.uuid4()
        payment = _make_payment(company_id=company_id, status="PENDING")

        def _confirm(**kwargs):
            payment.status = "CONFIRMED"
            payment.paid_at = datetime.now(timezone.utc)
            return payment

        with patch("app.modules.payments.service._get_payment", return_value=payment), \
             patch("app.modules.payments.service.confirm", side_effect=_confirm):
            from app.modules.payments.service import confirm_manual

            confirm_manual(
                payment_id=payment.payment_id,
                company_id=company_id,
                db=MagicMock(),
            )

        assert payment.status != "PENDING"
        assert payment.paid_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# 2. O escopo do dia segura — por CONSTRUÇÃO
# ─────────────────────────────────────────────────────────────────────────────

class TestEscopoDoDia:
    def test_rota_nao_expoe_parametro_de_data(self):
        """A prova da escolha (b): não há parâmetro a manipular.

        Se algum dia alguém acrescentar `date_from`/`day`/`as_of` a esta rota, o
        escopo deixa de ser estrutural e vira disciplina — este teste falha para
        forçar a conversa.
        """
        from app.modules.payments.router import list_payments_today

        for name, param in inspect.signature(list_payments_today).parameters.items():
            default = param.default
            assert hasattr(default, "dependency"), (
                f"'{name}' é entrada do cliente em /payments/today — o recorte do "
                f"dia deve ser calculado no servidor, sem parâmetro manipulável"
            )

    def test_today_declarada_antes_do_path_param(self):
        """`/payments/today` depois de `/payments/{payment_id}` viraria 422 de UUID.

        O FastAPI casa rotas na ordem de declaração.
        """
        from app.modules.payments.router import router

        paths = [r.path for r in router.routes if getattr(r, "path", "").startswith("/payments/")]
        assert "/payments/today" in paths
        assert "/payments/{payment_id}" in paths
        assert paths.index("/payments/today") < paths.index("/payments/{payment_id}")

    def test_janela_e_o_dia_civil_do_tenant_nao_o_dia_utc(self):
        """23h em São Paulo já é o dia seguinte em UTC — a janela segue o tenant.

        É o fim do expediente do balcão: se o recorte fosse o dia UTC, os
        pagamentos das últimas 3 horas cairiam no "amanhã".
        """
        from app.modules.tenant.service import current_day_bounds_utc

        db = _db_with_timezone("America/Sao_Paulo")
        # 2026-08-01 23:30 em SP == 2026-08-02 02:30 UTC
        now = datetime(2026, 8, 2, 2, 30, tzinfo=timezone.utc)

        start, end = current_day_bounds_utc(db, uuid.uuid4(), now=now)

        # O dia do tenant é 01/08 → 03:00Z de 01/08 até 03:00Z de 02/08
        assert start == datetime(2026, 8, 1, 3, 0, tzinfo=timezone.utc)
        assert end == datetime(2026, 8, 2, 3, 0, tzinfo=timezone.utc)
        assert start <= now < end
        assert (end - start) == timedelta(days=1)

    def test_timezone_ausente_ou_invalido_cai_no_fallback(self):
        from app.modules.tenant.service import get_tenant_timezone

        for tz_name in (None, "", "Nao/Existe"):
            db = _db_with_timezone(tz_name)
            assert str(get_tenant_timezone(db, uuid.uuid4())) == "America/Sao_Paulo"

    def test_sem_tenant_config_cai_no_fallback(self):
        from app.modules.tenant.service import get_tenant_timezone

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert str(get_tenant_timezone(db, uuid.uuid4())) == "America/Sao_Paulo"

    def test_query_do_dia_filtra_por_created_at_e_paid_at(self):
        """Casa por created_at OU paid_at — a cobrança de ontem paga hoje conta.

        Sem o `paid_at`, o operador não encontraria o próprio recebimento.
        """
        from app.modules.payments.service import list_payments_for_day

        db = MagicMock()
        start = datetime(2026, 8, 1, 3, 0, tzinfo=timezone.utc)
        end = datetime(2026, 8, 2, 3, 0, tzinfo=timezone.utc)

        list_payments_for_day(
            company_id=uuid.uuid4(), day_start=start, day_end=end, db=db,
        )

        criteria = db.query.return_value.filter.call_args.args
        rendered = " ".join(str(c) for c in criteria)
        assert "company_id" in rendered
        assert "created_at" in rendered
        assert "paid_at" in rendered
        # A janela é fechada dos dois lados — não é "tudo a partir de hoje".
        assert rendered.count(">=") >= 2 and rendered.count("<") >= 2

    def test_lista_do_dia_nao_soma_nada(self):
        """Devolve transações; o agregado é do dono."""
        from app.modules.payments.router import list_payments_today

        source = inspect.getsource(list_payments_today)
        for forbidden in ("sum(", "total", "reduce"):
            assert forbidden not in source.lower().split('"""')[-1], (
                "a rota do balcão não pode agregar valor"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 3. O que continua fechado ao OPERATOR
# ─────────────────────────────────────────────────────────────────────────────

class TestContinuaFechado:
    def test_lista_completa_de_pagamentos(self):
        """O razão do tenant não é do balcão — só o dia."""
        from app.modules.payments.router import list_payments

        _assert_denies(list_payments, "user", "OPERATOR")

    def test_desconto_manual_e_estorno(self):
        from app.modules.payments.router import manual_discount_payment, refund_payment

        _assert_denies(manual_discount_payment, "user", "OPERATOR")
        _assert_denies(refund_payment, "user", "OPERATOR")

    def test_substrato_de_dre(self):
        from app.modules.financial_core.router import (
            get_dre, list_entries, list_movements,
        )

        _assert_denies(get_dre, "actor", "OPERATOR")
        _assert_denies(list_movements, "actor", "OPERATOR")
        _assert_denies(list_entries, "actor", "OPERATOR")

    def test_saldo_consolidado_da_conta(self):
        """Estreitado neste sprint — era `_owner_admin_operator` desde o Sprint 7.

        `compute_balance` soma o histórico inteiro: é acumulado, não o dia.
        """
        from app.modules.financial_core.router import get_account_balance

        _assert_denies(get_account_balance, "actor", "OPERATOR")

    def test_comissoes(self):
        from app.modules.commission.router import list_commissions, list_policies

        _assert_denies(list_commissions, "current_user", "OPERATOR")
        _assert_denies(list_policies, "current_user", "OPERATOR")

    def test_protecao_real_do_confirm_manual_sobrevive(self):
        """Não-CASH/manual → 422, inclusive para o papel novo.

        É este guard — não o papel — que impede confirmar cobrança digital sem
        passar pelo webhook. Ampliar o RBAC não podia tocá-lo.
        """
        company_id = uuid.uuid4()
        pix = _make_payment(
            company_id=company_id, payment_method="PIX", provider="asaas",
        )

        with patch("app.modules.payments.service._get_payment", return_value=pix):
            from app.modules.payments.service import confirm_manual

            with pytest.raises(HTTPException) as exc:
                confirm_manual(
                    payment_id=pix.payment_id,
                    company_id=company_id,
                    db=MagicMock(),
                )

        assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 4. Conferência de gaveta — o cadastro de contas que faltava
# ─────────────────────────────────────────────────────────────────────────────

class TestConferenciaDeGaveta:
    def test_operator_lista_contas(self):
        from app.modules.financial_core.router import list_accounts

        _assert_allows(list_accounts, "actor", "OPERATOR")

    def test_cadastro_de_conta_nao_expoe_valor(self):
        """Por isso abrir o roster não fere o princípio — não há o que escopar."""
        from app.modules.financial_core.schemas import AccountResponse

        campos = set(AccountResponse.model_fields)
        assert not (campos & {"balance", "amount", "expected_amount", "total"})

    def test_cash_counts_seguem_abertos(self):
        """Permissão do Sprint 7 — não tocada aqui."""
        from app.modules.financial_core.router import list_cash_counts, record_cash_count

        _assert_allows(list_cash_counts, "actor", "OPERATOR")
        _assert_allows(record_cash_count, "actor", "OPERATOR")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Sem regressão para os outros papéis
# ─────────────────────────────────────────────────────────────────────────────

class TestSemRegressao:
    @pytest.mark.parametrize("role", ["OWNER", "ADMIN", "PLATFORM_OWNER"])
    def test_papeis_de_gestao_mantem_acesso(self, role):
        from app.modules.financial_core.router import (
            get_account_balance, list_accounts,
        )
        from app.modules.payments.router import (
            confirm_manual_payment, list_payments, list_payments_today,
        )

        _assert_allows(confirm_manual_payment, "user", role)
        _assert_allows(list_payments, "user", role)
        _assert_allows(list_payments_today, "user", role)
        _assert_allows(list_accounts, "actor", role)
        _assert_allows(get_account_balance, "actor", role)

    @pytest.mark.parametrize("role", ["PROFESSIONAL", "CLIENT"])
    def test_papeis_sem_balcao_continuam_de_fora(self, role):
        from app.modules.payments.router import (
            confirm_manual_payment, list_payments_today,
        )

        _assert_denies(confirm_manual_payment, "user", role)
        _assert_denies(list_payments_today, "user", role)
