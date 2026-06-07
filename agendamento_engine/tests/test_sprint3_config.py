"""
Testes do Sprint 3 — TenantConfig, Categories, Branding, create_company.

Usa mocks (unittest.mock) para evitar dependência de banco PostgreSQL.
Testes que requerem trigger de banco estão marcados com skip + justificativa.
"""
import os
import uuid
import pytest
from unittest.mock import MagicMock, patch


# ── 1. TenantConfig: accounting_mode=ACCRUAL → 422 ────────────────────────────

class TestTenantConfigAccrual:

    def test_accounting_mode_accrual_raises_422_before_write(self):
        """update_tenant_config devolve 422 ao receber ACCRUAL — antes de qualquer escrita."""
        from app.modules.tenant.service import update_tenant_config
        from app.modules.tenant.schemas import TenantConfigUpdate
        from fastapi import HTTPException

        mock_config = MagicMock()
        mock_config.tenant_config_id = uuid.uuid4()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config

        mock_actor = MagicMock()
        mock_actor.id = uuid.uuid4()
        mock_actor.role = "OWNER"

        data = TenantConfigUpdate(accounting_mode="ACCRUAL")

        with pytest.raises(HTTPException) as exc_info:
            update_tenant_config(mock_db, uuid.uuid4(), data, mock_actor)

        assert exc_info.value.status_code == 422
        assert "ACCRUAL" in exc_info.value.detail

    def test_accounting_mode_cash_does_not_raise(self):
        """CASH não ativa o bloqueio."""
        from app.modules.tenant.service import update_tenant_config
        from app.modules.tenant.schemas import TenantConfigUpdate

        mock_config = MagicMock()
        mock_config.tenant_config_id = uuid.uuid4()
        mock_config.timezone = "America/Sao_Paulo"
        mock_config.soft_reservation_ttl_min = 15
        mock_config.draft_expiration_min = 60
        mock_config.requested_expiration_h = 24
        mock_config.no_show_threshold_min = 30
        mock_config.no_penalty_cancel_h = 12
        mock_config.require_payment_upfront = False
        mock_config.default_commission_pct = "40.00"
        mock_config.accounting_mode = "CASH"
        mock_config.permission_overrides = {}

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config

        mock_actor = MagicMock()
        mock_actor.id = uuid.uuid4()
        mock_actor.role = "OWNER"

        # Não deve levantar HTTPException
        update_tenant_config(mock_db, uuid.uuid4(), TenantConfigUpdate(accounting_mode="CASH"), mock_actor)

    @pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="DATABASE_URL não configurado — rodar com Supabase",
    )
    def test_trigger_blocks_accrual_at_db_level(self):
        # Requer PostgreSQL real com triggers instalados.
        # Rodar com: $env:DATABASE_URL="<url_supabase>"; .\venv\Scripts\python.exe -m pytest tests/test_sprint3_config.py::TestTenantConfigAccrual::test_trigger_blocks_accrual_at_db_level -v
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import DBAPIError

        engine = create_engine(os.environ["DATABASE_URL"])

        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT tenant_config_id FROM tenant_configs LIMIT 1"
            )).fetchone()
            if row is None:
                pytest.skip("Nenhuma tenant_config no banco — criar um tenant primeiro")

            tc_id = row[0]
            nested = conn.begin_nested()
            raised = None
            try:
                conn.execute(
                    text("UPDATE tenant_configs SET accounting_mode='ACCRUAL' WHERE tenant_config_id = :id"),
                    {"id": str(tc_id)},
                )
            except DBAPIError as e:
                raised = e
                nested.rollback()
            else:
                nested.rollback()
                pytest.fail("Trigger enforce_cash_mode não bloqueou UPDATE para ACCRUAL")

            conn.rollback()

        assert raised is not None, "Trigger deve ter levantado exceção"
        assert "ACCRUAL" in str(raised.orig)


# ── 2. Category is_default — restrições de DELETE e PATCH ─────────────────────

class TestCategoryDefaultRestrictions:

    def _make_category(self, is_default: bool) -> MagicMock:
        cat = MagicMock()
        cat.category_id = uuid.uuid4()
        cat.company_id = uuid.uuid4()
        cat.name = "Corte"
        cat.entity_type = "SERVICE"
        cat.is_default = is_default
        cat.is_active = True
        cat.sort_order = 0
        return cat

    def _make_db(self, category: MagicMock) -> MagicMock:
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = category
        return mock_db

    def test_delete_default_category_raises_422(self):
        from app.modules.categories.service import delete_category
        from fastapi import HTTPException

        cat = self._make_category(is_default=True)
        mock_db = self._make_db(cat)

        with pytest.raises(HTTPException) as exc_info:
            delete_category(mock_db, cat.company_id, cat.category_id)

        assert exc_info.value.status_code == 422

    def test_patch_name_on_default_category_raises_422(self):
        from app.modules.categories.service import patch_category
        from app.modules.categories.schemas import CategoryPatch
        from fastapi import HTTPException

        cat = self._make_category(is_default=True)
        mock_db = self._make_db(cat)

        with pytest.raises(HTTPException) as exc_info:
            patch_category(mock_db, cat.company_id, cat.category_id, CategoryPatch(name="Novo Nome"))

        assert exc_info.value.status_code == 422
        assert "padrão" in exc_info.value.detail.lower() or "is_active" in exc_info.value.detail

    def test_patch_is_active_on_default_category_is_allowed(self):
        """Desativar categoria padrão deve ser permitido."""
        from app.modules.categories.service import patch_category
        from app.modules.categories.schemas import CategoryPatch

        cat = self._make_category(is_default=True)
        mock_db = self._make_db(cat)

        # Não deve levantar
        result = patch_category(mock_db, cat.company_id, cat.category_id, CategoryPatch(is_active=False))
        # O serviço faz setattr(category, "is_active", False) e depois commit+refresh
        assert cat.is_active is False

    def test_delete_non_default_category_succeeds(self):
        """Categoria não-padrão pode ser deletada."""
        from app.modules.categories.service import delete_category

        cat = self._make_category(is_default=False)
        mock_db = self._make_db(cat)

        # Não deve levantar
        delete_category(mock_db, cat.company_id, cat.category_id)
        mock_db.delete.assert_called_once_with(cat)
        mock_db.commit.assert_called()


# ── 3. create_company — 4 tipos de registro na mesma transação ─────────────────

class TestCreateCompanyTransaction:

    def test_creates_all_4_onboarding_record_types(self):
        """create_company deve criar TenantConfig, ModuleActivation, TenantBranding e Category
        na mesma transação, além de CommunicationSetting e CommunicationTemplate."""
        from app.modules.companies.service import create_company
        from app.modules.companies.schemas import CompanyCreate

        added_objects: list = []

        mock_db = MagicMock()
        mock_db.add.side_effect = lambda obj: added_objects.append(obj)
        # slug conflict check → sem conflito
        mock_db.query.return_value.filter.return_value.first.return_value = None

        data = CompanyCreate(name="Barbearia Sprint3", slug=f"sprint3-{uuid.uuid4().hex[:6]}")
        create_company(mock_db, data)

        type_names = {type(obj).__name__ for obj in added_objects}

        assert "TenantConfig" in type_names, (
            f"TenantConfig não foi adicionado. Tipos criados: {type_names}"
        )
        assert "ModuleActivation" in type_names, (
            f"ModuleActivation não foi adicionado. Tipos criados: {type_names}"
        )
        assert "TenantBranding" in type_names, (
            f"TenantBranding não foi adicionado. Tipos criados: {type_names}"
        )
        assert "Category" in type_names, (
            f"Category não foi adicionado. Tipos criados: {type_names}"
        )

    def test_creates_10_module_activations(self):
        """create_company deve criar exatamente 10 ModuleActivations (um por ModuleName)."""
        from app.modules.companies.service import create_company
        from app.modules.companies.schemas import CompanyCreate
        from app.infrastructure.db.models.module_activation import ModuleName

        added_objects: list = []
        mock_db = MagicMock()
        mock_db.add.side_effect = lambda obj: added_objects.append(obj)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        data = CompanyCreate(name="Barbearia Módulos", slug=f"modulos-{uuid.uuid4().hex[:6]}")
        create_company(mock_db, data)

        module_count = sum(1 for obj in added_objects if type(obj).__name__ == "ModuleActivation")
        expected = len(list(ModuleName))
        assert module_count == expected, (
            f"Esperado {expected} ModuleActivations, criou {module_count}"
        )

    def test_creates_16_default_categories(self):
        """create_company deve criar 16 categorias padrão (5 SERVICE + 4 PRODUCT + 7 EXPENSE)."""
        from app.modules.companies.service import create_company
        from app.modules.companies.schemas import CompanyCreate

        added_objects: list = []
        mock_db = MagicMock()
        mock_db.add.side_effect = lambda obj: added_objects.append(obj)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        data = CompanyCreate(name="Barbearia Categorias", slug=f"cats-{uuid.uuid4().hex[:6]}")
        create_company(mock_db, data)

        category_count = sum(1 for obj in added_objects if type(obj).__name__ == "Category")
        assert category_count == 16, (
            f"Esperado 16 Categories, criou {category_count}"
        )

    def test_commit_called_once(self):
        """Toda a criação deve ser commit numa única transação."""
        from app.modules.companies.service import create_company
        from app.modules.companies.schemas import CompanyCreate

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        data = CompanyCreate(name="Barbearia TX", slug=f"tx-{uuid.uuid4().hex[:6]}")
        create_company(mock_db, data)

        mock_db.commit.assert_called_once()


# ── 4. GET /tenant/branding — endpoint público sem autenticação ───────────────

class TestBrandingPublicEndpoint:

    def test_branding_router_has_no_auth_dependency(self):
        """O endpoint GET /tenant/branding não deve exigir autenticação.
        Verificado via inspeção do código-fonte — evita import de módulos com deps pesadas.
        """
        import ast
        import pathlib

        router_path = (
            pathlib.Path(__file__).parent.parent
            / "app" / "modules" / "tenant" / "router.py"
        )
        source = router_path.read_text(encoding="utf-8")

        # Garante que o endpoint público não usa require_role nem _owner_admin
        # Procura a definição de get_branding e verifica que company_id vem de Query
        assert "get_branding" in source, "Endpoint get_branding não encontrado no router"
        assert "Query(" in source, (
            "company_id de get_branding deve vir de Query, não de Depends(get_current_company_id)"
        )

        # Garante que a função get_branding usa company_id via Query (public)
        # e não via _owner_admin ou _owner_admin_operator
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_branding":
                func_source = ast.unparse(node)
                assert "require_role" not in func_source, (
                    "get_branding não deve usar require_role"
                )
                assert "_owner_admin" not in func_source, (
                    "get_branding não deve usar _owner_admin"
                )
                assert "get_current_user" not in func_source, (
                    "get_branding não deve usar get_current_user"
                )
                break

    def test_get_branding_service_returns_branding(self):
        """get_branding_or_404 retorna o branding sem verificar auth."""
        from app.modules.tenant.service import get_branding_or_404

        mock_branding = MagicMock()
        mock_branding.branding_id = uuid.uuid4()
        mock_branding.company_id = uuid.uuid4()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_branding

        result = get_branding_or_404(mock_db, mock_branding.company_id)
        assert result == mock_branding

    def test_get_branding_service_raises_404_for_unknown_company(self):
        """get_branding_or_404 levanta 404 para company inexistente."""
        from app.modules.tenant.service import get_branding_or_404
        from fastapi import HTTPException

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_branding_or_404(mock_db, uuid.uuid4())

        assert exc_info.value.status_code == 404
