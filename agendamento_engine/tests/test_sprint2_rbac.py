"""
Testes do Sprint 2 — RBAC: papéis, convite e auditoria.

Usa banco SQLite em memória criando apenas as tabelas necessárias para
o Sprint 2 (sem modelos que dependem de tipos PostgreSQL-only como ARRAY).
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Column, String, Boolean, Text, Numeric, TIMESTAMP, JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.sqlite import TEXT as SQLITE_TEXT

from app.infrastructure.db.session import get_db
from app.core.security import hash_password, create_access_token
from app.core.audit.sensitive_context import (
    ActionScope,
    SensitiveAuditContext,
    REASON_REQUIRED,
    record_sensitive_action,
)
from app.infrastructure.db.models.user import UserRole, SCHEMA_ONLY_ROLES, INVITE_PERMISSION

# ── Base e engine SQLite em memória ─────────────────────────────────────────

SQLITE_URL = "sqlite://"

# Usamos uma Base separada para os testes — cria apenas as tabelas necessárias
TestBase = declarative_base()


class TCompany(TestBase):
    __tablename__ = "companies"
    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True)
    active = Column(Boolean, default=True)
    timezone = Column(String(50), default="America/Sao_Paulo")
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow)


class TUser(TestBase):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True)
    company_id = Column(String(36), nullable=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default="ADMIN")
    active = Column(Boolean, default=True, nullable=False)
    # Coluna name adicionada em h2i3j4k5l6m7 — nullable para compatibilidade
    name = Column(String(100), nullable=True)
    last_password_change_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow)

    @property
    def is_admin(self):
        return self.role in ("ADMIN", "OWNER", "PLATFORM_OWNER")


class TUserInvitation(TestBase):
    __tablename__ = "user_invitations"
    invitation_id = Column(String(36), primary_key=True)
    company_id = Column(String(36), nullable=True)
    email = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False)
    token = Column(String(36), nullable=False, unique=True)
    expires_at = Column(TIMESTAMP, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    invited_by_user_id = Column(String(36), nullable=False)
    professional_id = Column(String(36), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


class TAuditLog(TestBase):
    __tablename__ = "audit_logs"
    audit_id = Column(String(36), primary_key=True)
    company_id = Column(String(36), nullable=True)
    actor_id = Column(String(36), nullable=False)
    actor_role = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(36), nullable=True)
    amount = Column(Numeric(15, 2), nullable=True)
    account_id = Column(String(36), nullable=True)
    reason = Column(Text, nullable=True)
    correlation_id = Column(String(36), nullable=True)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=True)
    occurred_at = Column(TIMESTAMP, default=datetime.utcnow)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def engine():
    e = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestBase.metadata.create_all(bind=e)
    yield e
    TestBase.metadata.drop_all(bind=e)


@pytest.fixture(scope="function")
def db_session(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    # Monkey-patch: o modelo real lê de app.infrastructure.db.models.*
    # mas para testes apontamos para as classes TestBase acima.
    import app.infrastructure.db.models.audit_log as al_module
    import app.infrastructure.db.models.user_invitation as ui_module
    import app.infrastructure.db.models.user as u_module

    # Re-vincula TAMBÉM os namespaces consumidores (idioma de test_user_name.py):
    # users/service e activate_service importam User/UserInvitation no topo do
    # módulo — patchar só os módulos de modelo funciona apenas se este arquivo
    # for o primeiro a importar o service (contaminação de ordem de import).
    import app.modules.users.service as users_svc_module
    import app.modules.auth.activate_service as activate_module

    orig_al = al_module.AuditLog
    orig_ui = ui_module.UserInvitation
    orig_user = u_module.User
    orig_svc_user = users_svc_module.User
    orig_svc_ui = users_svc_module.UserInvitation
    orig_act_user = activate_module.User
    orig_act_ui = activate_module.UserInvitation

    al_module.AuditLog = TAuditLog
    ui_module.UserInvitation = TUserInvitation
    u_module.User = TUser
    users_svc_module.User = TUser
    users_svc_module.UserInvitation = TUserInvitation
    activate_module.User = TUser
    activate_module.UserInvitation = TUserInvitation

    # Também patch nos __init__ imports
    import app.infrastructure.db.models as models_pkg
    models_pkg.AuditLog = TAuditLog
    models_pkg.UserInvitation = TUserInvitation
    models_pkg.User = TUser
    models_pkg.InvitationStatus = None  # não usado diretamente nos testes

    try:
        yield session
    finally:
        session.close()
        al_module.AuditLog = orig_al
        ui_module.UserInvitation = orig_ui
        u_module.User = orig_user
        users_svc_module.User = orig_svc_user
        users_svc_module.UserInvitation = orig_svc_ui
        activate_module.User = orig_act_user
        activate_module.UserInvitation = orig_act_ui
        models_pkg.AuditLog = orig_al
        models_pkg.UserInvitation = orig_ui
        models_pkg.User = orig_user


@pytest.fixture(scope="function")
def client(db_session):
    from app.main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _uid():
    return str(uuid.uuid4())


def make_company(db):
    c = TCompany(id=_uid(), name="Test Co", slug=f"test-{_uid()[:8]}", active=True)
    db.add(c)
    db.flush()
    return c


def make_user(db, company_id=None, role="ADMIN", email=None):
    u = TUser(
        id=_uid(),
        company_id=company_id,
        email=email or f"u_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("senha123"),
        role=role,
        active=True,
    )
    db.add(u)
    db.flush()
    return u


def auth_header(user) -> dict:
    token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "company_id": str(user.company_id) if user.company_id else None,
        "role": user.role,
    })
    return {"Authorization": f"Bearer {token}"}


def make_invitation(db, company_id, role, invited_by, status="PENDING", expires_delta_h=48):
    inv = TUserInvitation(
        invitation_id=_uid(),
        company_id=company_id,
        email=f"inv_{uuid.uuid4().hex[:6]}@test.com",
        role=role,
        token=_uid(),
        expires_at=datetime.utcnow() + timedelta(hours=expires_delta_h),
        status=status,
        invited_by_user_id=str(invited_by.id),
    )
    db.add(inv)
    db.flush()
    return inv


# ── 1. Enum tem 9 valores ─────────────────────────────────────────────────────

class TestUserRoleEnum:
    def test_all_nine_values_exist(self):
        values = {r.value for r in UserRole}
        assert len(values) == 9
        for expected in [
            "OWNER", "ADMIN", "OPERATOR", "PROFESSIONAL", "CLIENT",
            "PLATFORM_OWNER", "PLATFORM_SUPPORT", "PLATFORM_BILLING", "PLATFORM_READONLY",
        ]:
            assert expected in values, f"Missing role: {expected}"

    def test_schema_only_roles_in_set(self):
        assert UserRole.PLATFORM_SUPPORT in SCHEMA_ONLY_ROLES
        assert UserRole.PLATFORM_BILLING in SCHEMA_ONLY_ROLES
        assert UserRole.PLATFORM_READONLY in SCHEMA_ONLY_ROLES
        # Ativos não estão no set de schema-only
        assert UserRole.OWNER not in SCHEMA_ONLY_ROLES
        assert UserRole.ADMIN not in SCHEMA_ONLY_ROLES


# ── 2. SensitiveAuditContext / record_sensitive_action ───────────────────────

class TestSensitiveAuditContext:
    def test_record_invite_user_without_reason_ok(self, db_session):
        company = make_company(db_session)
        actor = make_user(db_session, company.id, "OWNER")
        ctx = SensitiveAuditContext(
            actor_id=uuid.UUID(actor.id),
            actor_role="OWNER",
            action="invite_user",
            resource_type="UserInvitation",
            company_id=uuid.UUID(company.id),
        )
        # invite_user não está em REASON_REQUIRED — não deve levantar
        record_sensitive_action(ctx, db_session)
        db_session.commit()

    def test_record_export_audit_without_reason_raises(self, db_session):
        company = make_company(db_session)
        actor = make_user(db_session, company.id, "OWNER")
        ctx = SensitiveAuditContext(
            actor_id=uuid.UUID(actor.id),
            actor_role="OWNER",
            action="export_audit",
            resource_type="AuditLog",
            company_id=uuid.UUID(company.id),
            reason=None,
        )
        with pytest.raises(ValueError, match="reason obrigatório"):
            record_sensitive_action(ctx, db_session)

    def test_record_export_audit_with_reason_ok(self, db_session):
        company = make_company(db_session)
        actor = make_user(db_session, company.id, "OWNER")
        ctx = SensitiveAuditContext(
            actor_id=uuid.UUID(actor.id),
            actor_role="OWNER",
            action="export_audit",
            resource_type="AuditLog",
            company_id=uuid.UUID(company.id),
            reason="auditoria interna",
        )
        entry = record_sensitive_action(ctx, db_session)
        db_session.commit()
        assert entry.action == "export_audit"
        assert entry.reason == "auditoria interna"

    def test_reason_required_set_contents(self):
        assert "create_manual_adjustment" in REASON_REQUIRED
        assert "export_audit" in REASON_REQUIRED
        assert "test_connection" in REASON_REQUIRED
        assert "invite_user" not in REASON_REQUIRED
        assert "assign_role" not in REASON_REQUIRED

    def test_audit_record_has_before_after_snapshots(self, db_session):
        company = make_company(db_session)
        actor = make_user(db_session, company.id, "OWNER")
        ctx = SensitiveAuditContext(
            actor_id=uuid.UUID(actor.id),
            actor_role="OWNER",
            action="assign_role",
            resource_type="User",
            resource_id=uuid.UUID(actor.id),
            company_id=uuid.UUID(company.id),
            before_snapshot={"role": "ADMIN"},
            after_snapshot={"role": "OWNER"},
        )
        entry = record_sensitive_action(ctx, db_session)
        db_session.commit()
        assert entry.before_snapshot == {"role": "ADMIN"}
        assert entry.after_snapshot == {"role": "OWNER"}


# ── 3. Anti-escalonamento (INVITE_PERMISSION dict) ────────────────────────────

class TestAntiEscalation:
    def test_owner_can_invite_admin(self):
        assert "ADMIN" in INVITE_PERMISSION["OWNER"]

    def test_admin_cannot_invite_admin(self):
        assert "ADMIN" not in INVITE_PERMISSION["ADMIN"]

    def test_admin_cannot_invite_owner(self):
        assert "OWNER" not in INVITE_PERMISSION["ADMIN"]

    def test_admin_can_invite_operator_and_professional(self):
        assert "OPERATOR" in INVITE_PERMISSION["ADMIN"]
        assert "PROFESSIONAL" in INVITE_PERMISSION["ADMIN"]

    def test_operator_cannot_invite_anyone(self):
        assert len(INVITE_PERMISSION["OPERATOR"]) == 0

    def test_platform_owner_can_invite_platform_owner(self):
        assert "PLATFORM_OWNER" in INVITE_PERMISSION["PLATFORM_OWNER"]


# ── 4. POST /users/invite (service-level, sem HTTP) ──────────────────────────

class TestInviteUserService:
    def test_owner_invites_professional_creates_invitation(self, db_session):
        from app.modules.users.service import invite_user

        company = make_company(db_session)
        owner = make_user(db_session, company.id, "OWNER")
        db_session.commit()

        inv = invite_user(db_session, owner, "new@test.com", "PROFESSIONAL")
        assert inv.email == "new@test.com"
        assert inv.role == "PROFESSIONAL"
        assert inv.status == "PENDING"

        # User ainda não foi criado
        user = db_session.query(TUser).filter(TUser.email == "new@test.com").first()
        assert user is None

    def test_admin_invites_admin_raises_403(self, db_session):
        from app.modules.users.service import invite_user
        from fastapi import HTTPException

        company = make_company(db_session)
        admin = make_user(db_session, company.id, "ADMIN")
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            invite_user(db_session, admin, "other@test.com", "ADMIN")
        assert exc_info.value.status_code == 403

    def test_admin_invites_owner_raises_403(self, db_session):
        from app.modules.users.service import invite_user
        from fastapi import HTTPException

        company = make_company(db_session)
        admin = make_user(db_session, company.id, "ADMIN")
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            invite_user(db_session, admin, "boss@test.com", "OWNER")
        assert exc_info.value.status_code == 403

    def test_invite_schema_only_role_raises_422(self, db_session):
        from app.modules.users.service import invite_user
        from fastapi import HTTPException

        company = make_company(db_session)
        owner = make_user(db_session, company.id, "OWNER")
        db_session.commit()

        for bad_role in ("PLATFORM_SUPPORT", "PLATFORM_BILLING", "PLATFORM_READONLY"):
            with pytest.raises(HTTPException) as exc_info:
                invite_user(db_session, owner, f"{bad_role}@test.com", bad_role)
            assert exc_info.value.status_code == 422, f"Expected 422 for {bad_role}"

    def test_owner_invites_platform_owner_raises_403(self, db_session):
        from app.modules.users.service import invite_user
        from fastapi import HTTPException

        company = make_company(db_session)
        owner = make_user(db_session, company.id, "OWNER")
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            invite_user(db_session, owner, "plat@test.com", "PLATFORM_OWNER")
        assert exc_info.value.status_code == 403

    def test_invite_records_audit_log(self, db_session):
        from app.modules.users.service import invite_user

        company = make_company(db_session)
        owner = make_user(db_session, company.id, "OWNER")
        db_session.commit()

        invite_user(db_session, owner, "audit@test.com", "PROFESSIONAL")

        log = db_session.query(TAuditLog).filter(TAuditLog.action == "invite_user").first()
        assert log is not None
        assert log.actor_id == str(owner.id)


# ── 5. Ativação por token (service-level) ────────────────────────────────────

class TestActivateService:
    def test_valid_token_creates_user_and_returns_jwt(self, db_session):
        from app.modules.auth.activate_service import activate_account

        company = make_company(db_session)
        inviter = make_user(db_session, company.id, "OWNER")
        inv = make_invitation(db_session, company.id, "PROFESSIONAL", inviter)
        db_session.commit()

        result = activate_account(db_session, uuid.UUID(inv.token), "senha123", "senha123")
        assert "access_token" in result
        assert result["role"] == "PROFESSIONAL"
        assert result["company_id"] == str(company.id)

        # User criado
        new_user = db_session.query(TUser).filter(TUser.email == inv.email).first()
        assert new_user is not None
        assert new_user.active is True

        # Token invalidado
        db_session.refresh(inv)
        assert inv.status == "ACCEPTED"

    def test_second_use_returns_410(self, db_session):
        from app.modules.auth.activate_service import activate_account
        from fastapi import HTTPException

        company = make_company(db_session)
        inviter = make_user(db_session, company.id, "OWNER")
        inv = make_invitation(db_session, company.id, "OPERATOR", inviter)
        db_session.commit()

        activate_account(db_session, uuid.UUID(inv.token), "senha123", "senha123")

        with pytest.raises(HTTPException) as exc_info:
            activate_account(db_session, uuid.UUID(inv.token), "outra", "outra")
        assert exc_info.value.status_code == 410

    def test_expired_token_returns_410(self, db_session):
        from app.modules.auth.activate_service import activate_account
        from fastapi import HTTPException

        company = make_company(db_session)
        inviter = make_user(db_session, company.id, "OWNER")
        inv = make_invitation(db_session, company.id, "PROFESSIONAL", inviter, expires_delta_h=-1)
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            activate_account(db_session, uuid.UUID(inv.token), "senha123", "senha123")
        assert exc_info.value.status_code == 410

    def test_platform_owner_activation_company_id_null(self, db_session):
        from app.modules.auth.activate_service import activate_account

        inviter = make_user(db_session, None, "PLATFORM_OWNER")
        inv = make_invitation(db_session, None, "PLATFORM_OWNER", inviter)
        db_session.commit()

        result = activate_account(db_session, uuid.UUID(inv.token), "senha123", "senha123")
        assert result["company_id"] is None
        assert result["role"] == "PLATFORM_OWNER"

    def test_operator_activation_has_company_id(self, db_session):
        from app.modules.auth.activate_service import activate_account

        company = make_company(db_session)
        inviter = make_user(db_session, company.id, "OWNER")
        inv = make_invitation(db_session, company.id, "OPERATOR", inviter)
        db_session.commit()

        result = activate_account(db_session, uuid.UUID(inv.token), "senha123", "senha123")
        assert result["company_id"] == str(company.id)


# ── 6. assign_role (service-level) ───────────────────────────────────────────

class TestAssignRoleService:
    def test_assign_role_records_audit_with_before_after(self, db_session):
        from app.modules.users.service import assign_role

        company = make_company(db_session)
        owner = make_user(db_session, company.id, "OWNER")
        target = make_user(db_session, company.id, "PROFESSIONAL")
        db_session.commit()

        assign_role(db_session, owner, uuid.UUID(target.id), "OPERATOR")

        log = db_session.query(TAuditLog).filter(TAuditLog.action == "assign_role").first()
        assert log is not None
        assert log.before_snapshot == {"role": "PROFESSIONAL"}
        assert log.after_snapshot == {"role": "OPERATOR"}

    def test_assign_schema_only_role_raises_422(self, db_session):
        from app.modules.users.service import assign_role
        from fastapi import HTTPException

        company = make_company(db_session)
        owner = make_user(db_session, company.id, "OWNER")
        target = make_user(db_session, company.id, "PROFESSIONAL")
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            assign_role(db_session, owner, uuid.UUID(target.id), "PLATFORM_BILLING")
        assert exc_info.value.status_code == 422

    def test_admin_cannot_assign_platform_owner(self, db_session):
        from app.modules.users.service import assign_role
        from fastapi import HTTPException

        company = make_company(db_session)
        admin = make_user(db_session, company.id, "ADMIN")
        target = make_user(db_session, company.id, "PROFESSIONAL")
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            assign_role(db_session, admin, uuid.UUID(target.id), "PLATFORM_OWNER")
        assert exc_info.value.status_code == 403

    def test_user_cannot_change_own_role(self, db_session):
        from app.modules.users.service import assign_role
        from fastapi import HTTPException

        company = make_company(db_session)
        owner = make_user(db_session, company.id, "OWNER")
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            assign_role(db_session, owner, uuid.UUID(owner.id), "ADMIN")
        assert exc_info.value.status_code == 403


# ── 7. Deactivate + último OWNER ─────────────────────────────────────────────

class TestDeactivateUser:
    def test_last_owner_cannot_be_deactivated(self, db_session):
        from app.modules.users.service import deactivate_user
        from fastapi import HTTPException

        company = make_company(db_session)
        owner = make_user(db_session, company.id, "OWNER")
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            deactivate_user(db_session, owner, uuid.UUID(owner.id))
        assert exc_info.value.status_code == 422

    def test_non_last_owner_can_be_deactivated(self, db_session):
        from app.modules.users.service import deactivate_user

        company = make_company(db_session)
        owner1 = make_user(db_session, company.id, "OWNER")
        owner2 = make_user(db_session, company.id, "OWNER")
        db_session.commit()

        result = deactivate_user(db_session, owner1, uuid.UUID(owner2.id))
        assert result.active is False


# ── 8. Transfer ownership ─────────────────────────────────────────────────────

class TestTransferOwnership:
    def test_non_owner_cannot_transfer(self, db_session):
        from app.modules.users.service import transfer_ownership
        from fastapi import HTTPException

        company = make_company(db_session)
        admin = make_user(db_session, company.id, "ADMIN")
        target = make_user(db_session, company.id, "PROFESSIONAL")
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            transfer_ownership(db_session, admin, uuid.UUID(target.id))
        assert exc_info.value.status_code == 403

    def test_successful_transfer_records_audit(self, db_session):
        from app.modules.users.service import transfer_ownership

        company = make_company(db_session)
        owner = make_user(db_session, company.id, "OWNER")
        new_owner = make_user(db_session, company.id, "ADMIN")
        db_session.commit()

        transfer_ownership(db_session, owner, uuid.UUID(new_owner.id), "ADMIN")

        log = db_session.query(TAuditLog).filter(
            TAuditLog.action == "transfer_ownership"
        ).first()
        assert log is not None
        assert log.before_snapshot["owner_id"] == str(owner.id)
        assert log.after_snapshot["new_owner_role"] == "OWNER"
        assert log.after_snapshot["previous_owner_new_role"] == "ADMIN"


# ── 9. get_current_company_id ─────────────────────────────────────────────────

class TestGetCurrentCompanyId:
    def test_platform_owner_returns_none(self, db_session):
        """PLATFORM_OWNER sem tenant → get_current_company_id retorna None."""
        from app.core.deps import get_current_company_id

        user = make_user(db_session, None, "PLATFORM_OWNER")
        result = get_current_company_id(user)
        assert result is None

    def test_regular_user_returns_company_id(self, db_session):
        from app.core.deps import get_current_company_id
        from fastapi import HTTPException

        company = make_company(db_session)
        admin = make_user(db_session, company.id, "ADMIN")
        result = get_current_company_id(admin)
        assert str(result) == admin.company_id

    def test_regular_user_without_company_raises_403(self, db_session):
        from app.core.deps import get_current_company_id
        from fastapi import HTTPException

        # ADMIN sem company_id (situação inválida) → 403
        user = make_user(db_session, None, "ADMIN")
        with pytest.raises(HTTPException) as exc_info:
            get_current_company_id(user)
        assert exc_info.value.status_code == 403
