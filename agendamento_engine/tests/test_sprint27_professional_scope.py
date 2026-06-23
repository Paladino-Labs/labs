"""
Testes Sprint 27 (backend) — Vínculo User↔Professional e escopo do papel PROFESSIONAL.

Cobre (DoD):
  - GET /auth/me com PROFESSIONAL vinculado → professional_id preenchido
  - GET /auth/me com PROFESSIONAL sem vínculo → professional_id=None
  - Convite com professional_id → ativação linka Professional.user_id
  - Convite sem professional_id → ativação não afeta profissionais
  - PATCH /professionals/{id} com user_id válido → vincula
  - PATCH /professionals/{id} com user_id já vinculado a outro → 409
  - PATCH /professionals/{id} com user_id=None → desvincula
  - GET /professionals/me com vínculo → 200 + dados; sem vínculo → 404; não-prof → 403
  - GET /appointments/ como PROFESSIONAL → força filtro do próprio professional_id
  - GET /appointments/ como OWNER com professional_id → filtra corretamente
  - GET /commissions/me como PROFESSIONAL com vínculo → 200; OWNER → 403

Estratégia (padrão test_user_name.py): SQLite em memória + monkey-patch dos
modelos para tabelas de teste; serviços de appointments/commission são
substituídos por captura de argumentos onde a serialização completa não importa.
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Column, String, Boolean, Text, Numeric, TIMESTAMP, JSON
from sqlalchemy import types as sa_types
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

from app.infrastructure.db.session import get_db
from app.core.security import hash_password, create_access_token

# ── Base e engine SQLite em memória ──────────────────────────────────────────

SQLITE_URL = "sqlite://"
TestBase = declarative_base()


class _UUIDString(sa_types.TypeDecorator):
    """Armazena UUID como String(36); aceita objetos UUID na comparação."""
    impl = sa_types.String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return value


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
    id = Column(_UUIDString(), primary_key=True)
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
    professional_id = Column(_UUIDString(), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


class TProfessional(TestBase):
    __tablename__ = "professionals"
    id = Column(_UUIDString(), primary_key=True)
    company_id = Column(_UUIDString(), nullable=False)
    name = Column(String(255), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    specialty = Column(String(255), nullable=True)
    cpf_cnpj_encrypted = Column(Text, nullable=True)
    cpf_cnpj_hash = Column(Text, nullable=True)
    cpf_cnpj_masked = Column(String(18), nullable=True)
    external_wallet_id = Column(String(255), nullable=True)
    user_id = Column(_UUIDString(), nullable=True, unique=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow)


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
    import app.infrastructure.db.models.professional as prof_module
    import app.infrastructure.db.models as models_pkg
    import app.core.deps as deps_module
    import app.modules.auth.activate_service as activate_module
    import app.modules.users.service as users_svc_module
    import app.modules.professionals.service as prof_svc_module

    saved = {
        "al": al_module.AuditLog,
        "ui": ui_module.UserInvitation,
        "u": u_module.User,
        "prof": prof_module.Professional,
        "pkg_al": models_pkg.AuditLog,
        "pkg_ui": models_pkg.UserInvitation,
        "pkg_u": models_pkg.User,
        "pkg_prof": models_pkg.Professional,
        "deps_u": deps_module.User,
        "act_u": activate_module.User,
        "act_ui": activate_module.UserInvitation,
        "act_prof": activate_module.Professional,
        "svc_u": users_svc_module.User,
        "svc_ui": users_svc_module.UserInvitation,
        "psvc_prof": prof_svc_module.Professional,
        "psvc_u": prof_svc_module.User,
    }

    al_module.AuditLog = TAuditLog
    ui_module.UserInvitation = TUserInvitation
    u_module.User = TUser
    prof_module.Professional = TProfessional
    models_pkg.AuditLog = TAuditLog
    models_pkg.UserInvitation = TUserInvitation
    models_pkg.User = TUser
    models_pkg.Professional = TProfessional
    deps_module.User = TUser
    activate_module.User = TUser
    activate_module.UserInvitation = TUserInvitation
    activate_module.Professional = TProfessional
    users_svc_module.User = TUser
    users_svc_module.UserInvitation = TUserInvitation
    prof_svc_module.Professional = TProfessional
    prof_svc_module.User = TUser

    try:
        yield session
    finally:
        session.close()
        al_module.AuditLog = saved["al"]
        ui_module.UserInvitation = saved["ui"]
        u_module.User = saved["u"]
        prof_module.Professional = saved["prof"]
        models_pkg.AuditLog = saved["pkg_al"]
        models_pkg.UserInvitation = saved["pkg_ui"]
        models_pkg.User = saved["pkg_u"]
        models_pkg.Professional = saved["pkg_prof"]
        deps_module.User = saved["deps_u"]
        activate_module.User = saved["act_u"]
        activate_module.UserInvitation = saved["act_ui"]
        activate_module.Professional = saved["act_prof"]
        users_svc_module.User = saved["svc_u"]
        users_svc_module.UserInvitation = saved["svc_ui"]
        prof_svc_module.Professional = saved["psvc_prof"]
        prof_svc_module.User = saved["psvc_u"]


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


def make_professional(db, company_id, name="Prof", user_id=None):
    p = TProfessional(
        id=_uid(),
        company_id=company_id,
        name=name,
        active=True,
        user_id=user_id,
    )
    db.add(p)
    db.flush()
    return p


def make_invitation(db, company_id, actor_id, email=None, role="PROFESSIONAL", professional_id=None):
    inv = TUserInvitation(
        invitation_id=_uid(),
        company_id=company_id,
        email=email or f"invite_{uuid.uuid4().hex[:6]}@test.com",
        role=role,
        token=_uid(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        status="PENDING",
        invited_by_user_id=actor_id,
        professional_id=professional_id,
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


# ── /auth/me ──────────────────────────────────────────────────────────────────

def test_auth_me_professional_linked_returns_professional_id(client, db_session):
    company = make_company(db_session)
    user = make_user(db_session, company.id, role="PROFESSIONAL")
    prof = make_professional(db_session, company.id, user_id=user.id)
    db_session.commit()

    resp = client.get("/auth/me", headers=auth_header(user))
    assert resp.status_code == 200
    assert resp.json()["professional_id"] == str(prof.id)


def test_auth_me_professional_unlinked_returns_none(client, db_session):
    company = make_company(db_session)
    user = make_user(db_session, company.id, role="PROFESSIONAL")
    db_session.commit()

    resp = client.get("/auth/me", headers=auth_header(user))
    assert resp.status_code == 200
    assert resp.json()["professional_id"] is None


def test_auth_me_owner_professional_id_is_none(client, db_session):
    company = make_company(db_session)
    user = make_user(db_session, company.id, role="OWNER")
    db_session.commit()

    resp = client.get("/auth/me", headers=auth_header(user))
    assert resp.status_code == 200
    assert resp.json()["professional_id"] is None


# ── convite + ativação ────────────────────────────────────────────────────────

def test_activation_with_professional_id_links_user(client, db_session):
    company = make_company(db_session)
    actor = make_user(db_session, company.id, role="OWNER")
    prof = make_professional(db_session, company.id, user_id=None)
    inv = make_invitation(
        db_session, company.id, actor.id,
        email="liga@test.com", role="PROFESSIONAL", professional_id=prof.id,
    )
    db_session.commit()

    resp = client.post("/auth/activate", json={
        "token": inv.token,
        "password": "Senha123",
        "password_confirm": "Senha123",
        "name": "Prof Ativado",
    })
    assert resp.status_code == 200
    new_user_id = resp.json()["user_id"]

    db_session.expire_all()
    refreshed = db_session.query(TProfessional).filter(TProfessional.id == prof.id).first()
    assert str(refreshed.user_id) == str(new_user_id)


def test_activation_without_professional_id_does_not_touch_professionals(client, db_session):
    company = make_company(db_session)
    actor = make_user(db_session, company.id, role="OWNER")
    prof = make_professional(db_session, company.id, user_id=None)
    inv = make_invitation(
        db_session, company.id, actor.id,
        email="sem@test.com", role="PROFESSIONAL", professional_id=None,
    )
    db_session.commit()

    resp = client.post("/auth/activate", json={
        "token": inv.token,
        "password": "Senha123",
        "password_confirm": "Senha123",
    })
    assert resp.status_code == 200

    db_session.expire_all()
    refreshed = db_session.query(TProfessional).filter(TProfessional.id == prof.id).first()
    assert refreshed.user_id is None


def test_invite_accepts_professional_id_field(client, db_session):
    company = make_company(db_session)
    actor = make_user(db_session, company.id, role="OWNER")
    prof = make_professional(db_session, company.id)
    db_session.commit()

    resp = client.post(
        "/users/invite",
        json={"email": "novo@test.com", "role": "PROFESSIONAL", "professional_id": str(prof.id)},
        headers=auth_header(actor),
    )
    assert resp.status_code == 201

    db_session.expire_all()
    inv = db_session.query(TUserInvitation).filter(
        TUserInvitation.email == "novo@test.com"
    ).first()
    assert inv is not None
    assert str(inv.professional_id) == str(prof.id)


# ── PATCH /professionals/{id} (vínculo) ───────────────────────────────────────

def test_patch_professional_user_id_links(client, db_session):
    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    target = make_user(db_session, company.id, role="PROFESSIONAL")
    prof = make_professional(db_session, company.id)
    db_session.commit()

    resp = client.patch(
        f"/professionals/{prof.id}",
        json={"user_id": str(target.id)},
        headers=auth_header(owner),
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == str(target.id)


def test_patch_professional_user_id_already_linked_409(client, db_session):
    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    target = make_user(db_session, company.id, role="PROFESSIONAL")
    prof_a = make_professional(db_session, company.id, name="A", user_id=target.id)
    prof_b = make_professional(db_session, company.id, name="B")
    db_session.commit()

    resp = client.patch(
        f"/professionals/{prof_b.id}",
        json={"user_id": str(target.id)},
        headers=auth_header(owner),
    )
    assert resp.status_code == 409


def test_patch_professional_user_id_not_professional_role_400(client, db_session):
    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    operator = make_user(db_session, company.id, role="OPERATOR")
    prof = make_professional(db_session, company.id)
    db_session.commit()

    resp = client.patch(
        f"/professionals/{prof.id}",
        json={"user_id": str(operator.id)},
        headers=auth_header(owner),
    )
    assert resp.status_code == 400


def test_patch_professional_user_id_null_unlinks(client, db_session):
    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    target = make_user(db_session, company.id, role="PROFESSIONAL")
    prof = make_professional(db_session, company.id, user_id=target.id)
    db_session.commit()

    resp = client.patch(
        f"/professionals/{prof.id}",
        json={"user_id": None},
        headers=auth_header(owner),
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] is None


# ── GET /professionals/me ─────────────────────────────────────────────────────

def test_get_professionals_me_linked_200(client, db_session):
    company = make_company(db_session)
    user = make_user(db_session, company.id, role="PROFESSIONAL")
    prof = make_professional(db_session, company.id, name="Eu Mesmo", user_id=user.id)
    db_session.commit()

    resp = client.get("/professionals/me", headers=auth_header(user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(prof.id)
    assert data["name"] == "Eu Mesmo"


def test_get_professionals_me_unlinked_404(client, db_session):
    company = make_company(db_session)
    user = make_user(db_session, company.id, role="PROFESSIONAL")
    db_session.commit()

    resp = client.get("/professionals/me", headers=auth_header(user))
    assert resp.status_code == 404


def test_get_professionals_me_non_professional_403(client, db_session):
    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    db_session.commit()

    resp = client.get("/professionals/me", headers=auth_header(owner))
    assert resp.status_code == 403


# ── GET /appointments/ (escopo) ───────────────────────────────────────────────

def test_appointments_professional_forces_own_filter(client, db_session, monkeypatch):
    import app.modules.appointments.router as appt_router

    captured = {}

    def fake_list(db, company_id, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(appt_router.svc, "list_appointments", fake_list)

    company = make_company(db_session)
    user = make_user(db_session, company.id, role="PROFESSIONAL")
    prof = make_professional(db_session, company.id, user_id=user.id)
    db_session.commit()

    # Mesmo passando outro professional_id, o filtro é forçado para o próprio.
    resp = client.get(
        f"/appointments/?professional_id={_uid()}",
        headers=auth_header(user),
    )
    assert resp.status_code == 200
    assert str(captured["professional_id"]) == str(prof.id)


def test_appointments_professional_unlinked_returns_empty(client, db_session, monkeypatch):
    import app.modules.appointments.router as appt_router

    called = {"n": 0}

    def fake_list(db, company_id, **kwargs):
        called["n"] += 1
        return []

    monkeypatch.setattr(appt_router.svc, "list_appointments", fake_list)

    company = make_company(db_session)
    user = make_user(db_session, company.id, role="PROFESSIONAL")
    db_session.commit()

    resp = client.get("/appointments/", headers=auth_header(user))
    assert resp.status_code == 200
    assert resp.json() == []
    assert called["n"] == 0  # short-circuit: serviço nem é chamado


def test_appointments_owner_filters_by_professional_id(client, db_session, monkeypatch):
    import app.modules.appointments.router as appt_router

    captured = {}

    def fake_list(db, company_id, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(appt_router.svc, "list_appointments", fake_list)

    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    target_prof_id = _uid()
    db_session.commit()

    resp = client.get(
        f"/appointments/?professional_id={target_prof_id}",
        headers=auth_header(owner),
    )
    assert resp.status_code == 200
    assert str(captured["professional_id"]) == str(target_prof_id)


# ── GET /commissions/me ───────────────────────────────────────────────────────

def test_commissions_me_professional_linked_200(client, db_session, monkeypatch):
    import app.modules.commission.router as comm_router

    captured = {}

    def fake_list(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(comm_router.commission_service, "list_commissions", fake_list)

    company = make_company(db_session)
    user = make_user(db_session, company.id, role="PROFESSIONAL")
    prof = make_professional(db_session, company.id, user_id=user.id)
    db_session.commit()

    resp = client.get("/commissions/me", headers=auth_header(user))
    assert resp.status_code == 200
    assert str(captured["professional_id"]) == str(prof.id)


def test_commissions_me_professional_unlinked_returns_empty(client, db_session):
    company = make_company(db_session)
    user = make_user(db_session, company.id, role="PROFESSIONAL")
    db_session.commit()

    resp = client.get("/commissions/me", headers=auth_header(user))
    assert resp.status_code == 200
    assert resp.json() == []


def test_commissions_me_owner_403(client, db_session):
    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    db_session.commit()

    resp = client.get("/commissions/me", headers=auth_header(owner))
    assert resp.status_code == 403
