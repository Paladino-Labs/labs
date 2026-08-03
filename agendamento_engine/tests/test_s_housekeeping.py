"""S-housekeeping — provas de que nada mudou (e do único acréscimo).

Item 1 — resolvedor de fuso unificado:
  `appointments/service._resolve_tenant_tz` passou a delegar para o canônico
  `tenant/service.get_tenant_timezone`. Os casos abaixo são os mesmos que o
  antigo cobria — tenant com config, sem config, timezone inválido/vazio — e
  incluem o ponto de uso real (`_normalize_start_at`, caminho de GRAVAÇÃO de
  horário, o que o F0 corrigiu).

Item 2 — `confirm-manual` deixa rastro:
  a confirmação passa a gravar `confirm_manual_payment` em audit_logs, como
  `refund` e `manual-discount` já faziam.

⚠️ Este arquivo NÃO importa celery (nem direta nem indiretamente): o guard
`if "celery" not in sys.modules` de outros arquivos da suíte depende disso.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _db_with_timezone(tz_name):
    """DB stub cujo TenantConfig devolve o timezone informado."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        timezone=tz_name
    )
    return db


def _db_without_config():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


# ─────────────────────────────────────────────────────────────────────────────
# Item 1 — o resolvedor de appointments delega, e resolve igual ao canônico
# ─────────────────────────────────────────────────────────────────────────────

class TestResolvedorDeFusoUnificado:
    @pytest.mark.parametrize("tz_name", ["America/Sao_Paulo", "America/Manaus", "UTC"])
    def test_tenant_com_config_resolve_o_fuso_configurado(self, tz_name):
        from app.modules.appointments.service import _resolve_tenant_tz

        assert str(_resolve_tenant_tz(_db_with_timezone(tz_name), uuid.uuid4())) == tz_name

    @pytest.mark.parametrize("tz_name", [None, "", "Nao/Existe", 123])
    def test_config_vazia_ou_invalida_cai_no_fallback(self, tz_name):
        """Mesmo fallback de antes: America/Sao_Paulo, e nunca levanta."""
        from app.modules.appointments.service import _resolve_tenant_tz

        resolved = _resolve_tenant_tz(_db_with_timezone(tz_name), uuid.uuid4())
        assert str(resolved) == "America/Sao_Paulo"

    def test_tenant_sem_config_cai_no_fallback(self):
        from app.modules.appointments.service import _resolve_tenant_tz

        assert str(_resolve_tenant_tz(_db_without_config(), uuid.uuid4())) == "America/Sao_Paulo"

    @pytest.mark.parametrize(
        "tz_name", ["America/Sao_Paulo", "America/Manaus", "UTC", None, "", "Nao/Existe"]
    )
    def test_os_dois_resolvedores_devolvem_o_mesmo(self, tz_name):
        """Equivalência explícita — é o que torna a delegação segura."""
        from app.modules.appointments.service import _resolve_tenant_tz
        from app.modules.tenant.service import get_tenant_timezone

        company_id = uuid.uuid4()
        assert str(_resolve_tenant_tz(_db_with_timezone(tz_name), company_id)) == str(
            get_tenant_timezone(_db_with_timezone(tz_name), company_id)
        )

    def test_delega_de_fato_ao_canonico(self):
        """Não é cópia nova: a chamada passa pelo canônico."""
        from app.modules.appointments.service import _resolve_tenant_tz

        db, company_id = _db_with_timezone("UTC"), uuid.uuid4()
        with patch("app.modules.tenant.service.get_tenant_timezone") as spy:
            _resolve_tenant_tz(db, company_id)

        spy.assert_called_once_with(db, company_id)


class TestGravacaoDeHorarioIntacta:
    """O ponto de uso real do resolvedor — o que o F0 corrigiu não regride."""

    def test_naive_e_lido_como_hora_local_do_tenant_e_gravado_em_utc(self):
        from app.modules.appointments.service import _normalize_start_at

        # 14h em São Paulo (UTC-3) → 17h UTC
        normalized = _normalize_start_at(
            _db_with_timezone("America/Sao_Paulo"),
            uuid.uuid4(),
            datetime(2026, 8, 3, 14, 0),
        )
        assert normalized.tzinfo is not None
        assert normalized.astimezone(timezone.utc).hour == 17

    def test_naive_em_tenant_de_manaus_usa_o_fuso_daquele_tenant(self):
        from app.modules.appointments.service import _normalize_start_at

        # Manaus é UTC-4 → 14h local = 18h UTC
        normalized = _normalize_start_at(
            _db_with_timezone("America/Manaus"),
            uuid.uuid4(),
            datetime(2026, 8, 3, 14, 0),
        )
        assert normalized.astimezone(timezone.utc).hour == 18

    def test_aware_e_apenas_convertido_para_utc(self):
        from app.modules.appointments.service import _normalize_start_at

        value = datetime(2026, 8, 3, 17, 0, tzinfo=timezone.utc)
        normalized = _normalize_start_at(_db_with_timezone("America/Sao_Paulo"), uuid.uuid4(), value)
        assert normalized == value

    def test_tenant_sem_config_grava_pelo_fallback(self):
        from app.modules.appointments.service import _normalize_start_at

        normalized = _normalize_start_at(
            _db_without_config(), uuid.uuid4(), datetime(2026, 8, 3, 14, 0)
        )
        assert normalized.astimezone(timezone.utc).hour == 17


# ─────────────────────────────────────────────────────────────────────────────
# Item 2 — confirm-manual deixa rastro
# ─────────────────────────────────────────────────────────────────────────────

def _make_cash_payment(company_id):
    p = MagicMock()
    p.payment_id = uuid.uuid4()
    p.company_id = company_id
    p.status = "PENDING"
    p.payment_method = "CASH"
    p.payment_submethod = None
    p.provider = "manual"
    p.net_charged_amount = Decimal("100.00")
    p.gross_catalog_amount = Decimal("100.00")
    p.provider_fee = Decimal("0.00")
    p.target_account_id = uuid.uuid4()
    p.external_charge_id = None
    p.paid_at = None
    return p


class TestConfirmManualAuditado:
    def test_confirmacao_grava_audit_log(self):
        from app.modules.payments.service import confirm_manual

        company_id, actor_id = uuid.uuid4(), uuid.uuid4()
        payment = _make_cash_payment(company_id)

        with patch("app.modules.payments.service._get_payment", return_value=payment), \
             patch("app.modules.payments.service.confirm", return_value=payment), \
             patch("app.modules.payments.service.record_sensitive_action") as rec:
            confirm_manual(
                payment_id=payment.payment_id,
                company_id=company_id,
                db=MagicMock(),
                actor_id=actor_id,
                actor_role="OPERATOR",
            )

        ctx = rec.call_args.args[0]
        assert ctx.action == "confirm_manual_payment"
        assert ctx.resource_type == "Payment"
        assert ctx.resource_id == payment.payment_id
        assert ctx.actor_id == actor_id
        assert ctx.actor_role == "OPERATOR"
        assert ctx.company_id == company_id
        assert ctx.amount == Decimal("100.00")

    def test_audit_entra_na_mesma_transacao_do_confirm(self):
        """Registrado ANTES do confirm() — que é quem faz o commit."""
        from app.modules.payments.service import confirm_manual

        company_id = uuid.uuid4()
        payment = _make_cash_payment(company_id)
        ordem = []

        with patch("app.modules.payments.service._get_payment", return_value=payment), \
             patch("app.modules.payments.service.confirm",
                   side_effect=lambda **kw: ordem.append("confirm") or payment), \
             patch("app.modules.payments.service.record_sensitive_action",
                   side_effect=lambda *a, **k: ordem.append("audit")):
            confirm_manual(
                payment_id=payment.payment_id,
                company_id=company_id,
                db=MagicMock(),
                actor_id=uuid.uuid4(),
            )

        assert ordem == ["audit", "confirm"]

    def test_resubmit_idempotente_nao_registra_de_novo(self):
        """Nada novo aconteceu → nenhuma linha nova de auditoria."""
        from app.modules.payments.service import confirm_manual

        company_id = uuid.uuid4()
        payment = _make_cash_payment(company_id)
        payment.status = "CONFIRMED"

        with patch("app.modules.payments.service._get_payment", return_value=payment), \
             patch("app.modules.payments.service.is_processed", return_value=True), \
             patch("app.modules.payments.service.record_sensitive_action") as rec:
            _confirmed, warning = confirm_manual(
                payment_id=payment.payment_id,
                company_id=company_id,
                db=MagicMock(),
                actor_id=uuid.uuid4(),
            )

        assert warning is None
        rec.assert_not_called()

    def test_pagamento_nao_manual_e_rejeitado_antes_de_qualquer_registro(self):
        """O 422 que protege o endpoint continua vindo primeiro."""
        from fastapi import HTTPException

        from app.modules.payments.service import confirm_manual

        company_id = uuid.uuid4()
        payment = _make_cash_payment(company_id)
        payment.payment_method = "PIX"
        payment.provider = "asaas"

        with patch("app.modules.payments.service._get_payment", return_value=payment), \
             patch("app.modules.payments.service.record_sensitive_action") as rec:
            with pytest.raises(HTTPException) as exc:
                confirm_manual(
                    payment_id=payment.payment_id,
                    company_id=company_id,
                    db=MagicMock(),
                    actor_id=uuid.uuid4(),
                )

        assert exc.value.status_code == 422
        rec.assert_not_called()

    def test_router_repassa_o_ator(self):
        """Sem isto o audit registraria ator nulo — o rastro perderia o dono."""
        import inspect

        from app.modules.payments.router import confirm_manual_payment

        src = inspect.getsource(confirm_manual_payment)
        assert "actor_id=user.id" in src
        assert "actor_role=user.role" in src
