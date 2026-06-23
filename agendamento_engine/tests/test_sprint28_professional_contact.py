"""
Testes Sprint 28 (backend complementar) — email/phone do Professional e
filtro de clientes por profissional em GET /customers/.

Cobre (DoD):
  - POST /professionals com email + phone → campos persistidos
  - PATCH /professionals/{id} com email + phone → atualiza
  - GET /professionals/{id} → resposta inclui email e phone
  - GET /customers/?professional_id=X → só clientes com appointment com X
  - GET /customers/ como PROFESSIONAL vinculado → só os próprios
  - GET /customers/ como PROFESSIONAL sem vínculo → lista vazia
  - GET /customers/ como OWNER sem filtro → todos os clientes

Estratégia (padrão test_sprint27_professional_scope.py): SQLite em memória +
monkey-patch dos modelos para tabelas de teste.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Column, String, Boolean, Text, TIMESTAMP, JSON
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


class TProfessional(TestBase):
    __tablename__ = "professionals"
    id = Column(_UUIDString(), primary_key=True, default=uuid.uuid4)
    company_id = Column(_UUIDString(), nullable=False)
    name = Column(String(255), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    specialty = Column(String(255), nullable=True)
    cpf_cnpj_encrypted = Column(Text, nullable=True)
    cpf_cnpj_hash = Column(Text, nullable=True)
    cpf_cnpj_masked = Column(String(18), nullable=True)
    external_wallet_id = Column(String(255), nullable=True)
    user_id = Column(_UUIDString(), nullable=True, unique=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow)


class TCustomer(TestBase):
    __tablename__ = "customers"
    id = Column(_UUIDString(), primary_key=True)
    company_id = Column(_UUIDString(), nullable=False)
    name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    custom_fields = Column(JSON, nullable=True, default=dict)
    active = Column(Boolean, default=True, nullable=False)
    identity_id = Column(_UUIDString(), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow)


class TAppointment(TestBase):
    __tablename__ = "appointments"
    id = Column(_UUIDString(), primary_key=True)
    company_id = Column(_UUIDString(), nullable=False)
    client_id = Column(_UUIDString(), nullable=True)
    professional_id = Column(_UUIDString(), nullable=True)
    status = Column(String(30), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


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

    import app.core.deps as deps_module
    import app.modules.professionals.service as prof_svc_module
    import app.modules.customers.service as cust_svc_module

    saved = {
        "deps_u": deps_module.User,
        "psvc_prof": prof_svc_module.Professional,
        "psvc_u": prof_svc_module.User,
        "csvc_customer": cust_svc_module.Customer,
        "csvc_appt": cust_svc_module.Appointment,
    }

    deps_module.User = TUser
    prof_svc_module.Professional = TProfessional
    prof_svc_module.User = TUser
    cust_svc_module.Customer = TCustomer
    cust_svc_module.Appointment = TAppointment

    try:
        yield session
    finally:
        session.close()
        deps_module.User = saved["deps_u"]
        prof_svc_module.Professional = saved["psvc_prof"]
        prof_svc_module.User = saved["psvc_u"]
        cust_svc_module.Customer = saved["csvc_customer"]
        cust_svc_module.Appointment = saved["csvc_appt"]


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


def make_customer(db, company_id, name="Cliente", phone=None):
    c = TCustomer(
        id=_uid(),
        company_id=company_id,
        name=name,
        phone=phone or f"5562{uuid.uuid4().hex[:9]}",
        custom_fields={},
        active=True,
    )
    db.add(c)
    db.flush()
    return c


def make_appointment(db, company_id, client_id, professional_id):
    a = TAppointment(
        id=_uid(),
        company_id=company_id,
        client_id=client_id,
        professional_id=professional_id,
        status="SCHEDULED",
    )
    db.add(a)
    db.flush()
    return a


def auth_header(user) -> dict:
    token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "company_id": str(user.company_id) if user.company_id else None,
        "role": user.role,
    })
    return {"Authorization": f"Bearer {token}"}


# ── Professional email/phone ────────────────────────────────────────────────

def test_create_professional_persists_email_and_phone(client, db_session):
    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    db_session.commit()

    resp = client.post(
        "/professionals/",
        json={"name": "João", "email": "joao@test.com", "phone": "+5562999998888"},
        headers=auth_header(owner),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "joao@test.com"
    assert data["phone"] == "+5562999998888"

    db_session.expire_all()
    saved = db_session.query(TProfessional).filter(TProfessional.id == data["id"]).first()
    assert saved.email == "joao@test.com"
    assert saved.phone == "+5562999998888"


def test_patch_professional_updates_email_and_phone(client, db_session):
    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    prof = make_professional(db_session, company.id)
    db_session.commit()

    resp = client.patch(
        f"/professionals/{prof.id}",
        json={"email": "novo@test.com", "phone": "+5562988887777"},
        headers=auth_header(owner),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "novo@test.com"
    assert data["phone"] == "+5562988887777"


def test_get_professional_includes_email_and_phone(client, db_session):
    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    prof = make_professional(db_session, company.id)
    prof.email = "contato@test.com"
    prof.phone = "+5562900001111"
    db_session.commit()

    resp = client.get(f"/professionals/{prof.id}", headers=auth_header(owner))
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "contato@test.com"
    assert data["phone"] == "+5562900001111"


# ── GET /customers/ filtro por profissional ─────────────────────────────────

def test_customers_filter_by_professional_id(client, db_session):
    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    prof = make_professional(db_session, company.id)
    cust_a = make_customer(db_session, company.id, name="Com Appt")
    cust_b = make_customer(db_session, company.id, name="Sem Appt")
    make_appointment(db_session, company.id, cust_a.id, prof.id)
    db_session.commit()

    resp = client.get(
        f"/customers/?professional_id={prof.id}",
        headers=auth_header(owner),
    )
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert str(cust_a.id) in ids
    assert str(cust_b.id) not in ids


def test_customers_owner_no_filter_returns_all(client, db_session):
    company = make_company(db_session)
    owner = make_user(db_session, company.id, role="OWNER")
    make_customer(db_session, company.id, name="C1")
    make_customer(db_session, company.id, name="C2")
    db_session.commit()

    resp = client.get("/customers/", headers=auth_header(owner))
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_customers_professional_linked_sees_only_own(client, db_session):
    company = make_company(db_session)
    user = make_user(db_session, company.id, role="PROFESSIONAL")
    prof = make_professional(db_session, company.id, user_id=user.id)
    other_prof = make_professional(db_session, company.id, name="Outro")
    cust_mine = make_customer(db_session, company.id, name="Meu")
    cust_other = make_customer(db_session, company.id, name="De outro")
    make_appointment(db_session, company.id, cust_mine.id, prof.id)
    make_appointment(db_session, company.id, cust_other.id, other_prof.id)
    db_session.commit()

    resp = client.get("/customers/", headers=auth_header(user))
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ids == [str(cust_mine.id)]


def test_customers_professional_linked_ignores_query_param(client, db_session):
    """Mesmo passando outro professional_id, o escopo é forçado ao próprio."""
    company = make_company(db_session)
    user = make_user(db_session, company.id, role="PROFESSIONAL")
    prof = make_professional(db_session, company.id, user_id=user.id)
    other_prof = make_professional(db_session, company.id, name="Outro")
    cust_mine = make_customer(db_session, company.id, name="Meu")
    cust_other = make_customer(db_session, company.id, name="De outro")
    make_appointment(db_session, company.id, cust_mine.id, prof.id)
    make_appointment(db_session, company.id, cust_other.id, other_prof.id)
    db_session.commit()

    resp = client.get(
        f"/customers/?professional_id={other_prof.id}",
        headers=auth_header(user),
    )
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ids == [str(cust_mine.id)]


def test_customers_professional_unlinked_returns_empty(client, db_session):
    company = make_company(db_session)
    user = make_user(db_session, company.id, role="PROFESSIONAL")
    make_customer(db_session, company.id, name="Qualquer")
    db_session.commit()

    resp = client.get("/customers/", headers=auth_header(user))
    assert resp.status_code == 200
    assert resp.json() == []
