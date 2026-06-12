"""
Testes Sprint C — Painel Owner Paladino (backend).

Usa FakeDB in-memory (padrão Sprints A/D) — sem PostgreSQL real.
NÃO importa app.main (quebra o monkey-patch de test_sprint2_rbac).

Casos obrigatórios:
  1.  OWNER de tenant → 403 em /platform/* (require_role)
  2.  PLATFORM_OWNER → acesso a /platform/*
  3.  Suspensão bloqueia login do tenant
  4.  PLATFORM_OWNER nunca bloqueado por suspensão
  5.  Impersonation expirada → 403 no middleware
  6.  Escrita em modo READ_ONLY → 403
  7.  ELEVATED permite escrita
  8.  Revogar grant → 403 imediato
  9.  Redispatch de log FAILED → novo CommunicationLog criado
  10. Redispatch de log não-FAILED → 422
  11. Acesso a /platform/audit gera registro de audit
  12. Tenant vê própria impersonation em /audit/impersonation-accesses
  13. Tenant NÃO vê impersonation de outro tenant
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.core.deps import require_role
from app.core.security import create_access_token
from app.infrastructure.db.models import (
    Company,
    CommunicationLog,
    ImpersonationGrant,
    PlatformSetting,
    TenantConfig,
    User,
    WhatsAppConnection,
)
from app.infrastructure.db.models.audit_log import AuditLog
from app.middleware.impersonation import (
    audit_impersonated_request,
    require_not_read_only,
    validate_impersonation_request,
)
from app.modules.audit.router import list_impersonation_accesses
from app.modules.auth import service as auth_service
from app.modules.platform import service as platform_service


# ─── FakeDB (padrão Sprint A/D) ───────────────────────────────────────────────

def _criterion_matches(obj, c) -> bool:
    key = c.left.key
    actual = getattr(obj, key, None)
    right = c.right
    op_name = getattr(c.operator, "__name__", "")

    if op_name == "in_op":
        values = getattr(right, "value", None) or []
        return actual in values

    right_cls = right.__class__.__name__
    if right_cls == "True_":
        val = True
    elif right_cls == "False_":
        val = False
    elif right_cls == "Null":
        val = None
    else:
        val = getattr(right, "value", None)

    if op_name in ("is_", "is_op"):
        return actual is val
    if op_name in ("ne", "is_not", "is_not_op"):
        return actual != val
    if op_name == "ge":
        return actual is not None and actual >= val
    if op_name == "gt":
        return actual is not None and actual > val
    if op_name == "le":
        return actual is not None and actual <= val
    if op_name == "lt":
        return actual is not None and actual < val
    return actual == val


class FakeQuery:
    def __init__(self, items):
        self.items = list(items)

    def filter(self, *criteria):
        return FakeQuery(
            [i for i in self.items if all(_criterion_matches(i, c) for c in criteria)]
        )

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, n):
        return FakeQuery(self.items[n:])

    def limit(self, n):
        return FakeQuery(self.items[:n])

    def count(self):
        return len(self.items)

    def first(self):
        return self.items[0] if self.items else None

    def all(self):
        return list(self.items)


class FakeDB:
    def __init__(self):
        self.stores = {}
        self.commits = 0

    def _store(self, model):
        return self.stores.setdefault(model, [])

    def query(self, model):
        return FakeQuery(self._store(model))

    def add(self, obj):
        for pk in ("id", "log_id", "audit_id"):
            if hasattr(obj, pk) and getattr(obj, pk) is None:
                setattr(obj, pk, uuid.uuid4())
        self._store(type(obj)).append(obj)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def refresh(self, obj):
        pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _make_company(db, status="ACTIVE"):
    company = Company(id=uuid.uuid4(), name="Barbearia Teste", status=status)
    db._store(Company).append(company)
    return company


def _make_platform_owner():
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="owner@paladino.app",
        role="PLATFORM_OWNER",
        company_id=None,
        active=True,
    )


def _platform_owner_token(user_id):
    return "Bearer " + create_access_token(
        {"sub": str(user_id), "role": "PLATFORM_OWNER", "company_id": None}
    )


def _make_grant(db, platform_user_id, company_id, mode="READ_ONLY", minutes=30):
    grant = ImpersonationGrant(
        id=uuid.uuid4(),
        platform_user_id=platform_user_id,
        company_id=company_id,
        mode=mode,
        reason="suporte ao tenant — diagnóstico de agenda travada",
        expires_at=_now() + timedelta(minutes=minutes),
        created_at=_now(),
    )
    db._store(ImpersonationGrant).append(grant)
    return grant


# ─── 1–2: RBAC /platform/* ────────────────────────────────────────────────────

class TestPlatformRBAC:
    def test_tenant_owner_gets_403(self):
        dep = require_role("PLATFORM_OWNER")
        tenant_owner = SimpleNamespace(role="OWNER")
        with pytest.raises(HTTPException) as exc:
            dep(user=tenant_owner)
        assert exc.value.status_code == 403

    def test_tenant_admin_gets_403(self):
        dep = require_role("PLATFORM_OWNER")
        with pytest.raises(HTTPException) as exc:
            dep(user=SimpleNamespace(role="ADMIN"))
        assert exc.value.status_code == 403

    def test_platform_owner_allowed(self):
        dep = require_role("PLATFORM_OWNER")
        user = _make_platform_owner()
        assert dep(user=user) is user

    def test_platform_owner_can_list_tenants(self):
        db = FakeDB()
        _make_company(db)
        _make_company(db, status="SUSPENDED")
        result = platform_service.list_tenants(db, status="SUSPENDED")
        assert len(result) == 1
        assert result[0].status == "SUSPENDED"


# ─── 3–4: suspensão bloqueia login ────────────────────────────────────────────

class TestSuspensionBlocksLogin:
    def _make_user(self, company_id):
        return User(
            id=uuid.uuid4(),
            email="dono@barbearia.com",
            password_hash="x",
            role="OWNER",
            company_id=company_id,
            active=True,
            last_password_change_at=None,
        )

    def test_suspended_tenant_login_blocked(self):
        db = FakeDB()
        company = _make_company(db, status="SUSPENDED")
        user = self._make_user(company.id)
        db._store(User).append(user)

        with patch("app.modules.auth.service.verify_password", return_value=True):
            with pytest.raises(HTTPException) as exc:
                auth_service.authenticate(db, user.email, "senha")
        assert exc.value.status_code == 403
        assert "suspenso" in exc.value.detail.lower()

    def test_active_tenant_login_ok(self):
        db = FakeDB()
        company = _make_company(db, status="ACTIVE")
        user = self._make_user(company.id)
        db._store(User).append(user)

        with patch("app.modules.auth.service.verify_password", return_value=True):
            result = auth_service.authenticate(db, user.email, "senha")
        assert result["access_token"]

    def test_platform_owner_never_blocked(self):
        db = FakeDB()
        # Mesmo com TODOS os tenants suspensos, PLATFORM_OWNER loga.
        _make_company(db, status="SUSPENDED")
        user = User(
            id=uuid.uuid4(),
            email="root@paladino.app",
            password_hash="x",
            role="PLATFORM_OWNER",
            company_id=None,
            active=True,
            last_password_change_at=None,
        )
        db._store(User).append(user)

        with patch("app.modules.auth.service.verify_password", return_value=True):
            result = auth_service.authenticate(db, user.email, "senha")
        assert result["role"] == "PLATFORM_OWNER"

    def test_suspend_then_reactivate(self):
        db = FakeDB()
        company = _make_company(db)
        actor = _make_platform_owner()

        platform_service.suspend_tenant(db, company.id, "inadimplência", actor.id)
        assert company.status == "SUSPENDED"

        platform_service.reactivate_tenant(db, company.id, actor.id)
        assert company.status == "ACTIVE"

    def test_suspend_without_reason_422(self):
        db = FakeDB()
        company = _make_company(db)
        actor = _make_platform_owner()
        with pytest.raises(HTTPException) as exc:
            platform_service.suspend_tenant(db, company.id, "", actor.id)
        assert exc.value.status_code == 422


# ─── 5–8: impersonation no middleware ─────────────────────────────────────────

class TestImpersonationMiddleware:
    def test_expired_grant_403(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        grant = _make_grant(db, owner.id, company.id, minutes=-5)  # já expirado

        with pytest.raises(HTTPException) as exc:
            validate_impersonation_request(
                db, str(grant.id), _platform_owner_token(owner.id), "GET"
            )
        assert exc.value.status_code == 403

    def test_valid_grant_read_ok(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        grant = _make_grant(db, owner.id, company.id)

        result = validate_impersonation_request(
            db, str(grant.id), _platform_owner_token(owner.id), "GET"
        )
        assert result is grant

    def test_non_platform_owner_jwt_403(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        grant = _make_grant(db, owner.id, company.id)
        tenant_token = "Bearer " + create_access_token(
            {"sub": str(uuid.uuid4()), "role": "OWNER", "company_id": str(company.id)}
        )
        with pytest.raises(HTTPException) as exc:
            validate_impersonation_request(db, str(grant.id), tenant_token, "GET")
        assert exc.value.status_code == 403

    def test_grant_of_another_platform_user_403(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        grant = _make_grant(db, uuid.uuid4(), company.id)  # outro platform user

        with pytest.raises(HTTPException) as exc:
            validate_impersonation_request(
                db, str(grant.id), _platform_owner_token(owner.id), "GET"
            )
        assert exc.value.status_code == 403

    def test_read_only_write_403(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        grant = _make_grant(db, owner.id, company.id, mode="READ_ONLY")

        with pytest.raises(HTTPException) as exc:
            validate_impersonation_request(
                db, str(grant.id), _platform_owner_token(owner.id), "POST"
            )
        assert exc.value.status_code == 403

    def test_read_only_dependency_blocks_write(self):
        grant = ImpersonationGrant(mode="READ_ONLY")
        request = SimpleNamespace(
            state=SimpleNamespace(impersonating=True, impersonation_grant=grant)
        )
        with pytest.raises(HTTPException) as exc:
            require_not_read_only(request)
        assert exc.value.status_code == 403

    def test_elevated_allows_write(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        grant = _make_grant(db, owner.id, company.id, mode="ELEVATED")

        result = validate_impersonation_request(
            db, str(grant.id), _platform_owner_token(owner.id), "POST"
        )
        assert result is grant

        request = SimpleNamespace(
            state=SimpleNamespace(impersonating=True, impersonation_grant=grant)
        )
        require_not_read_only(request)  # não levanta

    def test_no_impersonation_dependency_noop(self):
        request = SimpleNamespace(state=SimpleNamespace())
        require_not_read_only(request)  # não levanta

    def test_revoked_grant_403_immediately(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        grant, grant_id = platform_service.create_impersonation_grant(
            db, owner.id, company.id, "READ_ONLY", "suporte: investigar agenda"
        )
        # Válido antes da revogação
        validate_impersonation_request(
            db, grant_id, _platform_owner_token(owner.id), "GET"
        )

        platform_service.revoke_impersonation_grant(db, grant.id, owner.id)

        with pytest.raises(HTTPException) as exc:
            validate_impersonation_request(
                db, grant_id, _platform_owner_token(owner.id), "GET"
            )
        assert exc.value.status_code == 403


class TestGrantLifecycle:
    def test_elevated_requires_detailed_reason(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        with pytest.raises(HTTPException) as exc:
            platform_service.create_impersonation_grant(
                db, owner.id, company.id, "ELEVATED", "curto"
            )
        assert exc.value.status_code == 422

    def test_create_grant_audited(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        platform_service.create_impersonation_grant(
            db, owner.id, company.id, "READ_ONLY", "suporte ao tenant"
        )
        actions = [a.action for a in db._store(AuditLog)]
        assert "impersonation_grant_created" in actions

    def test_revoke_does_not_delete(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        grant, _ = platform_service.create_impersonation_grant(
            db, owner.id, company.id, "READ_ONLY", "suporte"
        )
        platform_service.revoke_impersonation_grant(db, grant.id, owner.id)
        assert grant.revoked_at is not None
        assert grant in db._store(ImpersonationGrant)

    def test_list_active_grants_excludes_revoked_and_expired(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        active = _make_grant(db, owner.id, company.id)
        expired = _make_grant(db, owner.id, company.id, minutes=-10)
        revoked = _make_grant(db, owner.id, company.id)
        revoked.revoked_at = _now()

        result = platform_service.list_active_grants(db, owner.id)
        assert active in result
        assert expired not in result
        assert revoked not in result


# ─── 9–10: redispatch ─────────────────────────────────────────────────────────

class TestRedispatch:
    def _make_failed_log(self, db, company_id):
        log = CommunicationLog(
            log_id=uuid.uuid4(),
            company_id=company_id,
            event_type="appointment.confirmed",
            channel="WHATSAPP",
            recipient_id=uuid.uuid4(),
            recipient_type="CLIENT",
            status="FAILED",
            rendered_body="Olá! Seu horário está confirmado.",
        )
        db._store(CommunicationLog).append(log)
        return log

    def test_redispatch_failed_creates_new_log(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        log = self._make_failed_log(db, company.id)

        customer = SimpleNamespace(id=log.recipient_id, phone="5511999990000")
        from app.infrastructure.db.models import Customer
        db._store(Customer).append(customer)
        db._store(WhatsAppConnection).append(
            WhatsAppConnection(
                id=uuid.uuid4(),
                company_id=company.id,
                instance_name="paladino-test",
                status="CONNECTED",
            )
        )

        with patch("app.modules.whatsapp.evolution_client.send_text") as send:
            new_log = platform_service.redispatch_communication(
                db, log.log_id, "cliente não recebeu a confirmação", owner.id
            )

        send.assert_called_once()
        assert new_log is not log
        assert new_log.log_id != log.log_id
        assert new_log.status == "SENT"
        assert new_log.rendered_body == log.rendered_body
        assert log.status == "FAILED"  # original intocado
        assert len(db._store(CommunicationLog)) == 2
        actions = [a.action for a in db._store(AuditLog)]
        assert "communication_redispatched" in actions

    def test_redispatch_non_failed_422(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        log = self._make_failed_log(db, company.id)
        log.status = "SENT"

        with pytest.raises(HTTPException) as exc:
            platform_service.redispatch_communication(
                db, log.log_id, "motivo qualquer", owner.id
            )
        assert exc.value.status_code == 422

    def test_redispatch_requires_reason(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        log = self._make_failed_log(db, company.id)
        with pytest.raises(HTTPException) as exc:
            platform_service.redispatch_communication(db, log.log_id, "", owner.id)
        assert exc.value.status_code == 422

    def test_redispatch_send_failure_creates_failed_log(self):
        db = FakeDB()
        owner = _make_platform_owner()
        company = _make_company(db)
        log = self._make_failed_log(db, company.id)
        # Sem WhatsAppConnection nem Customer → reenvio falha
        new_log = platform_service.redispatch_communication(
            db, log.log_id, "tentativa de reenvio", owner.id
        )
        assert new_log.status == "FAILED"
        assert new_log.error_message


# ─── 11: acesso ao audit é auditado (RBAC-4) ──────────────────────────────────

class TestAuditOfAuditAccess:
    def test_platform_audit_access_is_audited(self):
        from app.modules.platform.router import platform_audit

        db = FakeDB()
        actor = _make_platform_owner()
        request = SimpleNamespace(query_params={"action": "tenant_status_changed"})

        platform_audit(
            request=request,
            company_id=None,
            actor_id=None,
            action="tenant_status_changed",
            date_from=None,
            date_to=None,
            page=1,
            limit=50,
            actor=actor,
            db=db,
        )

        meta = [a for a in db._store(AuditLog) if a.action == "platform_audit_access"]
        assert len(meta) == 1
        assert meta[0].after_snapshot["filters"] == {"action": "tenant_status_changed"}


# ─── 12–13: tenant vê impersonation no próprio audit ──────────────────────────

class TestTenantSeesImpersonation:
    def _impersonated_access(self, db, company_id):
        """Simula o middleware auditando uma request impersonada."""
        grant = ImpersonationGrant(
            id=uuid.uuid4(),
            platform_user_id=uuid.uuid4(),
            company_id=company_id,
            mode="READ_ONLY",
            reason="suporte",
            expires_at=_now() + timedelta(minutes=30),
        )
        audit_impersonated_request(
            db, grant, grant.platform_user_id, "/customers", "GET"
        )
        return grant

    def test_tenant_sees_own_impersonation(self):
        db = FakeDB()
        # record_sensitive_action persiste UUIDs como string — usar str ids
        # para que o filtro do endpoint case com actor.company_id no FakeDB.
        company_id = str(uuid.uuid4())
        grant = self._impersonated_access(db, company_id)

        actor = SimpleNamespace(
            id=uuid.uuid4(), role="OWNER", company_id=company_id
        )
        result = list_impersonation_accesses(page=1, limit=50, actor=actor, db=db)
        assert result["total"] == 1
        assert result["items"][0]["grant_id"] == str(grant.id)
        assert result["items"][0]["request"]["path"] == "/customers"

    def test_tenant_does_not_see_other_tenant_impersonation(self):
        db = FakeDB()
        company_a = str(uuid.uuid4())
        company_b = str(uuid.uuid4())
        self._impersonated_access(db, company_a)

        actor_b = SimpleNamespace(
            id=uuid.uuid4(), role="OWNER", company_id=company_b
        )
        result = list_impersonation_accesses(page=1, limit=50, actor=actor_b, db=db)
        assert result["total"] == 0

    def test_platform_owner_redirected_to_platform_audit(self):
        db = FakeDB()
        actor = _make_platform_owner()
        with pytest.raises(HTTPException) as exc:
            list_impersonation_accesses(page=1, limit=50, actor=actor, db=db)
        assert exc.value.status_code == 403


# ─── Flags e platform settings ────────────────────────────────────────────────

class TestFlagsAndSettings:
    def test_get_and_set_tenant_flag(self):
        db = FakeDB()
        company = _make_company(db)
        actor = _make_platform_owner()
        config = TenantConfig(
            tenant_config_id=uuid.uuid4(),
            company_id=company.id,
            permission_overrides={"use_communication_service": True},
        )
        db._store(TenantConfig).append(config)

        flags = platform_service.set_tenant_flag(
            db, company.id, "allow_subscription_pause", True, actor.id
        )
        assert flags["allow_subscription_pause"] is True
        assert flags["use_communication_service"] is True  # preservado

        current = platform_service.get_tenant_flags(db, company.id)
        assert current["allow_subscription_pause"] is True

        actions = [a.action for a in db._store(AuditLog)]
        assert "tenant_flag_changed" in actions

    def test_platform_settings_upsert(self):
        db = FakeDB()
        actor = _make_platform_owner()

        platform_service.set_platform_setting(db, "maintenance_mode", True, actor.id)
        assert platform_service.get_platform_settings(db) == {"maintenance_mode": True}

        platform_service.set_platform_setting(db, "maintenance_mode", False, actor.id)
        settings_now = platform_service.get_platform_settings(db)
        assert settings_now == {"maintenance_mode": False}
        assert len(db._store(PlatformSetting)) == 1  # upsert, não duplica

    def test_health_includes_minimum_metrics(self):
        db = FakeDB()
        company = _make_company(db)
        health = platform_service.get_tenant_health(db, company.id)
        for key in (
            "total_users",
            "total_customers",
            "appointments_30d",
            "last_activity_at",
            "communication_failures_7d",
            "asaas_connected",
            "whatsapp_connected",
        ):
            assert key in health
        assert health["asaas_connected"] is False
        assert health["whatsapp_connected"] is False
