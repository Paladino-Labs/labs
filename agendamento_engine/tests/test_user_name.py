"""
Testes — campo User.name (pré-requisito frontend).

Cobre:
  - POST /users/invite com/sem name (campo aceito sem erro)
  - GET /auth/me → resposta inclui campo name (pode ser None)
  - POST /auth/activate com/sem name → name salvo corretamente
  - GET /users → lista inclui name em cada item
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Column, String, Boolean, Text, Numeric, TIMESTAMP, JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

from app.infrastructure.db.session import get_db
from app.core.security import hash_password, create_access_token

# ── Base e engine SQLite em memória ──────────────────────────────────────────

SQLITE_URL = "sqlite://"
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


# ── Fixtures ──────────────────────────────────────────────────────────────────

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

    import app.infrastructure.db.models.audit_log as al_module
    import app.infrastructure.db.models.user_invitation as ui_module
    import app.infrastructure.db.models.user as u_module
    import app.infrastructure.db.models as models_pkg
    import app.core.deps as deps_module
    import app.modules.auth.activate_service as activate_module
    import app.modules.users.service as users_svc_module

    orig_al = al_module.AuditLog
    orig_ui = ui_module.UserInvitation
    orig_user = u_module.User
    orig_deps_user = deps_module.User
    orig_activate_user = activate_module.User
    orig_activate_inv = activate_module.UserInvitation
    orig_svc_user = users_svc_module.User
    orig_svc_inv = users_svc_module.UserInvitation

    al_module.AuditLog = TAuditLog
    ui_module.UserInvitation = TUserInvitation
    u_module.User = TUser

    models_pkg.AuditLog = TAuditLog
    models_pkg.UserInvitation = TUserInvitation
    models_pkg.User = TUser
    models_pkg.InvitationStatus = None

    deps_module.User = TUser
    activate_module.User = TUser
    activate_module.UserInvitation = TUserInvitation
    users_svc_module.User = TUser
    users_svc_module.UserInvitation = TUserInvitation

    try:
        yield session
    finally:
        session.close()
        al_module.AuditLog = orig_al
        ui_module.UserInvitation = orig_ui
        u_module.User = orig_user
        models_pkg.AuditLog = orig_al
        models_pkg.UserInvitation = orig_ui
        models_pkg.User = orig_user
        deps_module.User = orig_deps_user
        activate_module.User = orig_activate_user
        activate_module.UserInvitation = orig_activate_inv
        users_svc_module.User = orig_svc_user
        users_svc_module.UserInvitation = orig_svc_inv


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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _uid():
    return str(uuid.uuid4())


def make_company(db):
    c = TCompany(id=_uid(), name="Test Co", slug=f"test-{_uid()[:8]}")
    db.add(c)
    db.flush()
    return c


def make_user(db, company_id, role="OWNER", email=None, name=None):
    u = TUser(
        id=_uid(),
        company_id=company_id,
        email=email or f"u_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Senha123"),
        role=role,
        active=True,
        name=name,
    )
    db.add(u)
    db.flush()
    return u


def make_invitation(db, company_id, actor_id, email=None, role="ADMIN"):
    inv = TUserInvitation(
        invitation_id=_uid(),
        company_id=company_id,
        email=email or f"invite_{uuid.uuid4().hex[:6]}@test.com",
        role=role,
        token=_uid(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        status="PENDING",
        invited_by_user_id=actor_id,
    )
    db.add(inv)
    db.flush()
    return inv


def auth_header(user) -> dict:
    token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "company_id": str(user.company_id) if user.company_id else None,
        "role": user.role,
    })
    return {"Authorization": f"Bearer {token}"}


# ── Testes ────────────────────────────────────────────────────────────────────

def test_invite_with_name_accepted(client, db_session):
    """POST /users/invite com name → convite criado sem erro (name aceito no body)."""
    company = make_company(db_session)
    actor = make_user(db_session, company.id, role="OWNER")
    db_session.commit()

    resp = client.post(
        "/users/invite",
        json={"email": "novo@test.com", "role": "ADMIN", "name": "João Teste"},
        headers=auth_header(actor),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "invitation_id" in data
    assert "expires_at" in data


def test_invite_without_name_accepted(client, db_session):
    """POST /users/invite sem name → convite criado sem erro."""
    company = make_company(db_session)
    actor = make_user(db_session, company.id, role="OWNER")
    db_session.commit()

    resp = client.post(
        "/users/invite",
        json={"email": "novo2@test.com", "role": "ADMIN"},
        headers=auth_header(actor),
    )
    assert resp.status_code == 201
    assert "invitation_id" in resp.json()


def test_get_me_includes_name_field(client, db_session):
    """GET /auth/me → resposta inclui campo name (pode ser None)."""
    company = make_company(db_session)
    user = make_user(db_session, company.id, name="Maria Silva")
    db_session.commit()

    resp = client.get("/auth/me", headers=auth_header(user))
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert data["name"] == "Maria Silva"


def test_get_me_name_can_be_none(client, db_session):
    """GET /auth/me → name pode ser None para usuários sem nome cadastrado."""
    company = make_company(db_session)
    user = make_user(db_session, company.id, name=None)
    db_session.commit()

    resp = client.get("/auth/me", headers=auth_header(user))
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert data["name"] is None


def test_activate_with_name_saves_name(client, db_session):
    """POST /auth/activate com name → User criado com name salvo."""
    company = make_company(db_session)
    actor = make_user(db_session, company.id, role="OWNER")
    invitation = make_invitation(db_session, company.id, actor.id, email="ativado@test.com")
    db_session.commit()

    resp = client.post(
        "/auth/activate",
        json={
            "token": invitation.token,
            "password": "Senha123",
            "password_confirm": "Senha123",
            "name": "Carlos Ativado",
        },
    )
    assert resp.status_code == 200
    token_data = resp.json()
    assert "access_token" in token_data

    # Verifica que user.name foi salvo
    from app.infrastructure.db.models.user import User
    created = db_session.query(User).filter(User.email == "ativado@test.com").first()
    assert created is not None
    assert created.name == "Carlos Ativado"


def test_activate_without_name_name_is_none(client, db_session):
    """POST /auth/activate sem name → User criado com name=None (sem erro)."""
    company = make_company(db_session)
    actor = make_user(db_session, company.id, role="OWNER")
    invitation = make_invitation(db_session, company.id, actor.id, email="semname@test.com")
    db_session.commit()

    resp = client.post(
        "/auth/activate",
        json={
            "token": invitation.token,
            "password": "Senha123",
            "password_confirm": "Senha123",
        },
    )
    assert resp.status_code == 200

    from app.infrastructure.db.models.user import User
    created = db_session.query(User).filter(User.email == "semname@test.com").first()
    assert created is not None
    assert created.name is None


def test_list_users_includes_name(client, db_session):
    """GET /users → cada item da lista inclui campo name."""
    company = make_company(db_session)
    actor = make_user(db_session, company.id, role="OWNER", name="Dono")
    make_user(db_session, company.id, role="ADMIN", name="Admin Um")
    make_user(db_session, company.id, role="ADMIN", name=None)
    db_session.commit()

    resp = client.get("/users/", headers=auth_header(actor))
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) >= 3
    for u in users:
        assert "name" in u
