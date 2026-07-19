"""
Testes do Sprint S0.2 — fechar os vazamentos cross-tenant do módulo users
(A-ISO: assign_role e deactivate_user sem filtro de company_id).

Cobre:
  1. Vazamento A fechado: OWNER de A não altera papel de usuário de B (404,
     papel intacto).
  2. Vazamento B fechado: OWNER de A não desativa usuário de B (404,
     active intacto).
  3. Caminho feliz preservado: papel/desativação no próprio tenant; regras de
     anti-escalonamento, auto-alteração e último OWNER continuam valendo.
  4. Indistinguibilidade: alvo de outro tenant responde exatamente como alvo
     inexistente (mesmo status + mesmo detail).
  5. PLATFORM_OWNER (company_id NULL): gerencia usuários de plataforma, mas o
     filtro vale para ele também — usuário de tenant → 404 (impersonation não
     é consumida pelo módulo users; ver relatório do sprint).
  6. Filtro active novo em deactivate_user: usuário já inativo → 404.

Estilo FakeDB in-memory com avaliação real dos critérios de filtro do
SQLAlchemy (padrão de tests/contract/conftest.py), usando o modelo User REAL —
sem importar app.main (preserva o monkey-patch de test_sprint2_rbac).
"""
import uuid

import pytest
from fastapi import HTTPException

from app.infrastructure.db.models.user import User
from app.modules.users.service import assign_role, deactivate_user


# ── FakeDB mínimo (padrão tests/contract/conftest.py) ────────────────────────

def _right_value(right):
    cls = right.__class__.__name__
    if cls == "True_":
        return True
    if cls == "False_":
        return False
    if cls == "Null":
        return None
    return getattr(right, "value", None)


def _criterion_matches(obj, c) -> bool:
    key = c.left.key
    actual = getattr(obj, key, None)
    op_name = getattr(c.operator, "__name__", "")
    val = _right_value(c.right)

    if op_name in ("is_", "is_op"):
        return actual is val
    if op_name in ("ne", "is_not", "is_not_op", "isnot"):
        return actual != val
    return actual == val


class FakeQuery:
    def __init__(self, items):
        self.items = list(items)

    def filter(self, *criteria):
        return FakeQuery(
            [i for i in self.items if all(_criterion_matches(i, c) for c in criteria)]
        )

    def first(self):
        return self.items[0] if self.items else None

    def all(self):
        return list(self.items)

    def count(self):
        return len(self.items)


class FakeDB:
    def __init__(self):
        self.stores: dict = {}

    def _store(self, model):
        return self.stores.setdefault(model, [])

    def query(self, model, *rest):
        return FakeQuery(self._store(model))

    def add(self, obj):
        self._store(type(obj)).append(obj)

    def commit(self):
        pass

    def flush(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(db, company_id, role, active=True):
    u = User(
        id=str(uuid.uuid4()),
        company_id=str(company_id) if company_id else None,
        email=f"u_{uuid.uuid4().hex[:8]}@test.com",
        password_hash="x",
        role=role,
        active=active,
    )
    db.add(u)
    return u


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def tenants(db):
    """Dois tenants: A (owner_a + prof_a) e B (owner_b + prof_b)."""
    company_a = str(uuid.uuid4())
    company_b = str(uuid.uuid4())
    return {
        "company_a": company_a,
        "company_b": company_b,
        "owner_a": _make_user(db, company_a, "OWNER"),
        "prof_a": _make_user(db, company_a, "PROFESSIONAL"),
        "owner_b": _make_user(db, company_b, "OWNER"),
        "prof_b": _make_user(db, company_b, "PROFESSIONAL"),
    }


# ── 1. Vazamento A fechado — assign_role cross-tenant ────────────────────────

class TestAssignRoleCrossTenant:
    def test_owner_a_cannot_change_role_of_user_in_tenant_b(self, db, tenants):
        with pytest.raises(HTTPException) as exc:
            assign_role(db, tenants["owner_a"], uuid.UUID(tenants["prof_b"].id), "OWNER")
        assert exc.value.status_code == 404
        # Papel do usuário de B permanece inalterado
        assert tenants["prof_b"].role == "PROFESSIONAL"

    def test_owner_a_cannot_promote_user_of_b_to_owner(self, db, tenants):
        """Cenário exato da A-ISO: promoção cross-tenant a OWNER."""
        with pytest.raises(HTTPException) as exc:
            assign_role(db, tenants["owner_a"], uuid.UUID(tenants["owner_b"].id), "OPERATOR")
        assert exc.value.status_code == 404
        assert tenants["owner_b"].role == "OWNER"


# ── 2. Vazamento B fechado — deactivate_user cross-tenant ────────────────────

class TestDeactivateCrossTenant:
    def test_owner_a_cannot_deactivate_user_in_tenant_b(self, db, tenants):
        with pytest.raises(HTTPException) as exc:
            deactivate_user(db, tenants["owner_a"], uuid.UUID(tenants["prof_b"].id))
        assert exc.value.status_code == 404
        assert tenants["prof_b"].active is True


# ── 3. Caminho feliz preservado ──────────────────────────────────────────────

class TestSameTenantHappyPath:
    def test_owner_assigns_role_in_own_tenant(self, db, tenants):
        result = assign_role(
            db, tenants["owner_a"], uuid.UUID(tenants["prof_a"].id), "OPERATOR"
        )
        assert result.role == "OPERATOR"

    def test_owner_deactivates_user_in_own_tenant(self, db, tenants):
        result = deactivate_user(db, tenants["owner_a"], uuid.UUID(tenants["prof_a"].id))
        assert result.active is False

    def test_admin_cannot_assign_admin_anti_escalation(self, db, tenants):
        admin_a = _make_user(db, tenants["company_a"], "ADMIN")
        with pytest.raises(HTTPException) as exc:
            assign_role(db, admin_a, uuid.UUID(tenants["prof_a"].id), "ADMIN")
        assert exc.value.status_code == 403

    def test_user_cannot_change_own_role(self, db, tenants):
        with pytest.raises(HTTPException) as exc:
            assign_role(db, tenants["owner_a"], uuid.UUID(tenants["owner_a"].id), "ADMIN")
        assert exc.value.status_code == 403

    def test_last_owner_cannot_be_deactivated(self, db, tenants):
        with pytest.raises(HTTPException) as exc:
            deactivate_user(db, tenants["owner_a"], uuid.UUID(tenants["owner_a"].id))
        assert exc.value.status_code == 422
        assert tenants["owner_a"].active is True

    def test_non_last_owner_can_be_deactivated(self, db, tenants):
        owner_a2 = _make_user(db, tenants["company_a"], "OWNER")
        result = deactivate_user(db, tenants["owner_a"], uuid.UUID(owner_a2.id))
        assert result.active is False


# ── 4. Indistinguibilidade: outro tenant ≡ inexistente ───────────────────────

class TestIndistinguishability:
    def test_assign_role_same_error_for_missing_and_foreign(self, db, tenants):
        with pytest.raises(HTTPException) as missing:
            assign_role(db, tenants["owner_a"], uuid.uuid4(), "OPERATOR")
        with pytest.raises(HTTPException) as foreign:
            assign_role(db, tenants["owner_a"], uuid.UUID(tenants["prof_b"].id), "OPERATOR")
        assert missing.value.status_code == foreign.value.status_code == 404
        assert missing.value.detail == foreign.value.detail

    def test_deactivate_same_error_for_missing_and_foreign(self, db, tenants):
        with pytest.raises(HTTPException) as missing:
            deactivate_user(db, tenants["owner_a"], uuid.uuid4())
        with pytest.raises(HTTPException) as foreign:
            deactivate_user(db, tenants["owner_a"], uuid.UUID(tenants["prof_b"].id))
        assert missing.value.status_code == foreign.value.status_code == 404
        assert missing.value.detail == foreign.value.detail


# ── 5. PLATFORM_OWNER: escopo = usuários de plataforma (company_id NULL) ─────

class TestPlatformOwnerScope:
    def test_platform_owner_manages_platform_users(self, db, tenants):
        plat_actor = _make_user(db, None, "PLATFORM_OWNER")
        plat_target = _make_user(db, None, "PLATFORM_OWNER")
        result = assign_role(db, plat_actor, uuid.UUID(plat_target.id), "OWNER")
        assert result.role == "OWNER"

    def test_platform_owner_cannot_reach_tenant_user(self, db, tenants):
        """Sem impersonation consumida pelo módulo users, o filtro vale
        também para PLATFORM_OWNER — usuário de tenant → 404."""
        plat_actor = _make_user(db, None, "PLATFORM_OWNER")
        with pytest.raises(HTTPException) as exc:
            assign_role(db, plat_actor, uuid.UUID(tenants["prof_a"].id), "OPERATOR")
        assert exc.value.status_code == 404
        assert tenants["prof_a"].role == "PROFESSIONAL"

    def test_platform_owner_cannot_deactivate_tenant_user(self, db, tenants):
        plat_actor = _make_user(db, None, "PLATFORM_OWNER")
        with pytest.raises(HTTPException) as exc:
            deactivate_user(db, plat_actor, uuid.UUID(tenants["prof_a"].id))
        assert exc.value.status_code == 404
        assert tenants["prof_a"].active is True


# ── 6. Filtro active em deactivate_user ──────────────────────────────────────

class TestDeactivateInactiveUser:
    def test_deactivating_already_inactive_user_returns_404(self, db, tenants):
        inactive = _make_user(db, tenants["company_a"], "PROFESSIONAL", active=False)
        with pytest.raises(HTTPException) as exc:
            deactivate_user(db, tenants["owner_a"], uuid.UUID(inactive.id))
        assert exc.value.status_code == 404
