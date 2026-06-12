"""
Testes Sprint D — Portal do Cliente (backend).

Usa FakeDB in-memory (avalia BinaryExpressions do SQLAlchemy contra
objetos Python) — sem banco PostgreSQL real (padrão do projeto).

Casos obrigatórios:
  1.  JWT portal (type=portal) rejeitado em endpoints de tenant
  2.  JWT tenant rejeitado em endpoints de portal
  3.  Login com senha correta → JWT portal válido
  4.  Login com senha errada → 401
  5.  Magic link: token expirado → 401
  6.  Magic link: token usado duas vezes → 401
  7.  Magic link: nunca revela existência do email (silencioso p/ desconhecido)
  8.  Dashboard cross-tenant: cliente com 2 tenants vê dados de ambos
  9.  Pause de assinatura quando tenant não permite → 403
  10. PAYMENT_STORAGE sem consent → 422 ao adicionar fonte
  11. Revogar fonte de pagamento → revoked_at preenchido
  12. PATCH /portal/profile com phone: identity re-resolvida
  13. GET /portal/identity/me: retorna dados corretos (resolve o 501)
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

from app.core.config import settings
from app.core.deps import get_current_portal_identity, get_current_user
from app.core.security import create_access_token, hash_password
from app.infrastructure.db.models import (
    Appointment,
    ConsentRecord,
    Customer,
    CustomerCredit,
    PaladinoIdentity,
    PaymentSourceAuthorization,
    PortalCredential,
    PortalMagicToken,
    TenantConfig,
)
from app.infrastructure.db.models.subscription import CustomerSubscription
from app.modules.portal import auth_service, service as portal_service
from app.modules.portal.auth_service import (
    create_portal_token,
    hash_magic_token,
    verify_portal_token,
)


# ─── FakeDB (padrão Sprint A, estendido: in_, comparações, count/offset/limit) ─

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
    """Session fake com stores in-memory roteados por classe de modelo."""

    def __init__(self):
        self.stores = {}
        self.commits = 0

    def _store(self, model):
        return self.stores.setdefault(model, [])

    def query(self, model):
        return FakeQuery(self._store(model))

    def add(self, obj):
        if getattr(obj, "id", None) is None and hasattr(obj, "id"):
            obj.id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        # Defaults de coluna não se aplicam a instâncias transient
        if isinstance(obj, ConsentRecord) and obj.occurred_at is None:
            obj.occurred_at = now
        if isinstance(obj, PaladinoIdentity) and obj.possible_aliases is None:
            obj.possible_aliases = []
        if isinstance(obj, Customer) and obj.active is None:
            obj.active = True
        if isinstance(obj, PortalCredential) and obj.email_verified is None:
            obj.email_verified = False
        if isinstance(obj, PaymentSourceAuthorization) and obj.granted_at is None:
            obj.granted_at = now
        self._store(type(obj)).append(obj)

    def commit(self):
        self.commits += 1

    def flush(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_identity(db, phone="5562988887777", **kwargs) -> PaladinoIdentity:
    identity = PaladinoIdentity(
        phone_e164=f"+{phone}",
        phone_national_normalized=phone[2:],
        possible_aliases=[],
        **kwargs,
    )
    db.add(identity)
    return identity


def _make_credential(db, identity, email="cliente@example.com", password=None):
    cred = PortalCredential(
        identity_id=identity.id,
        email=email,
        password_hash=hash_password(password) if password else None,
        email_verified=False,
    )
    db.add(cred)
    return cred


def _make_customer(db, identity, company_id=None):
    customer = Customer(
        company_id=company_id or uuid.uuid4(),
        name="Cliente Teste",
        phone=identity.phone_e164.lstrip("+"),
        identity_id=identity.id,
        active=True,
    )
    db.add(customer)
    return customer


def _make_appointment(db, customer, hours_from_now=48, status="SCHEDULED"):
    start = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
    a = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=customer.company_id,
        client_id=customer.id,
        start_at=start,
        end_at=start + timedelta(minutes=30),
        status=status,
        services=[SimpleNamespace(service_name="Corte")],
        professional=SimpleNamespace(name="João Barbeiro"),
        total_amount=Decimal("50.00"),
    )
    db._store(Appointment).append(a)
    return a


def _make_subscription(db, customer, status="ACTIVE"):
    s = SimpleNamespace(
        subscription_id=uuid.uuid4(),
        company_id=customer.company_id,
        customer_id=customer.id,
        plan=SimpleNamespace(name="Plano Mensal"),
        status=status,
        next_billing_at=datetime.now(timezone.utc) + timedelta(days=15),
        paused_at=None,
        cancelled_at=None,
    )
    db._store(CustomerSubscription).append(s)
    return s


def _make_credit(db, customer, expires_in_days=None, status="ACTIVE"):
    c = SimpleNamespace(
        credit_id=uuid.uuid4(),
        company_id=customer.company_id,
        customer_id=customer.id,
        entitlement_type="PACKAGE",
        total_cotas=4,
        remaining_cotas=2,
        status=status,
        granted_at=datetime.now(timezone.utc),
        expires_at=(
            datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            if expires_in_days is not None else None
        ),
    )
    db._store(CustomerCredit).append(c)
    return c


def _make_tenant_config(db, company_id, overrides=None):
    cfg = SimpleNamespace(
        company_id=company_id,
        permission_overrides=overrides or {},
    )
    db._store(TenantConfig).append(cfg)
    return cfg


def _grant_payment_storage(db, identity, company_id):
    record = ConsentRecord(
        identity_id=identity.id,
        company_id=company_id,
        consent_type="PAYMENT_STORAGE",
        channel=None,
        status="GRANTED",
        source_channel="PORTAL",
    )
    db.add(record)
    return record


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _tenant_token(user_id=None, company_id=None) -> str:
    return create_access_token({
        "sub": str(user_id or uuid.uuid4()),
        "email": "owner@tenant.com",
        "company_id": str(company_id or uuid.uuid4()),
        "role": "OWNER",
    })


# ─── 1–2. Separação JWT portal × JWT tenant ──────────────────────────────────

class TestTokenSeparation:
    def test_portal_token_has_portal_claims(self):
        identity_id = uuid.uuid4()
        token = create_portal_token(identity_id)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["type"] == "portal"
        assert payload["sub"] == str(identity_id)
        assert "company_id" not in payload
        assert "iat" in payload and "exp" in payload

    def test_portal_token_rejected_on_tenant_endpoints(self):
        """JWT portal NUNCA autentica em get_current_user (endpoints tenant)."""
        token = create_portal_token(uuid.uuid4())
        db = MagicMock()
        with pytest.raises(HTTPException) as exc:
            get_current_user(credentials=_bearer(token), db=db)
        assert exc.value.status_code == 401
        db.query.assert_not_called()  # rejeição explícita, antes do lookup

    def test_tenant_token_rejected_on_portal_endpoints(self):
        """JWT tenant (sem type=portal) → 401 no verify_portal_token."""
        token = _tenant_token()
        with pytest.raises(HTTPException) as exc:
            verify_portal_token(token)
        assert exc.value.status_code == 401

    def test_tenant_token_rejected_by_portal_dependency(self):
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            get_current_portal_identity(credentials=_bearer(_tenant_token()), db=db)
        assert exc.value.status_code == 401

    def test_garbage_token_rejected(self):
        with pytest.raises(HTTPException) as exc:
            verify_portal_token("nao-e-um-jwt")
        assert exc.value.status_code == 401

    def test_portal_dependency_returns_identity(self):
        db = FakeDB()
        identity = _make_identity(db)
        token = create_portal_token(identity.id)
        result = get_current_portal_identity(credentials=_bearer(token), db=db)
        assert result is identity

    def test_portal_token_for_unknown_identity_401(self):
        db = FakeDB()
        token = create_portal_token(uuid.uuid4())
        with pytest.raises(HTTPException) as exc:
            get_current_portal_identity(credentials=_bearer(token), db=db)
        assert exc.value.status_code == 401


# ─── 3–4. Login com senha ─────────────────────────────────────────────────────

class TestPasswordLogin:
    def test_login_correct_password_returns_valid_portal_jwt(self):
        db = FakeDB()
        identity = _make_identity(db)
        cred = _make_credential(db, identity, password="Senha123")

        token = auth_service.login_with_password(db, "cliente@example.com", "Senha123")

        assert verify_portal_token(token) == identity.id
        assert cred.last_login_at is not None

    def test_login_wrong_password_401(self):
        db = FakeDB()
        identity = _make_identity(db)
        _make_credential(db, identity, password="Senha123")

        with pytest.raises(HTTPException) as exc:
            auth_service.login_with_password(db, "cliente@example.com", "errada")
        assert exc.value.status_code == 401

    def test_login_unknown_email_401(self):
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            auth_service.login_with_password(db, "ninguem@example.com", "Senha123")
        assert exc.value.status_code == 401

    def test_login_magic_link_only_account_401_with_password(self):
        """Credencial sem password_hash (só magic link) não loga com senha."""
        db = FakeDB()
        identity = _make_identity(db)
        _make_credential(db, identity, password=None)

        with pytest.raises(HTTPException) as exc:
            auth_service.login_with_password(db, "cliente@example.com", "qualquer")
        assert exc.value.status_code == 401


# ─── 5–7. Magic link ──────────────────────────────────────────────────────────

class TestMagicLink:
    def _issue(self, db, identity, minutes=15):
        raw = str(uuid.uuid4())
        magic = PortalMagicToken(
            identity_id=identity.id,
            token_hash=hash_magic_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        )
        db.add(magic)
        return raw, magic

    def test_verify_valid_token_returns_portal_jwt_and_marks_used(self):
        db = FakeDB()
        identity = _make_identity(db)
        cred = _make_credential(db, identity)
        raw, magic = self._issue(db, identity)

        token = auth_service.verify_magic_link(db, raw)

        assert verify_portal_token(token) == identity.id
        assert magic.used_at is not None
        assert cred.email_verified is True

    def test_expired_token_401(self):
        db = FakeDB()
        identity = _make_identity(db)
        raw, _ = self._issue(db, identity, minutes=-1)  # já expirado

        with pytest.raises(HTTPException) as exc:
            auth_service.verify_magic_link(db, raw)
        assert exc.value.status_code == 401

    def test_token_used_twice_401(self):
        db = FakeDB()
        identity = _make_identity(db)
        _make_credential(db, identity)
        raw, _ = self._issue(db, identity)

        auth_service.verify_magic_link(db, raw)  # primeiro uso OK
        with pytest.raises(HTTPException) as exc:
            auth_service.verify_magic_link(db, raw)  # segundo uso
        assert exc.value.status_code == 401

    def test_unknown_token_401(self):
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            auth_service.verify_magic_link(db, str(uuid.uuid4()))
        assert exc.value.status_code == 401

    def test_send_magic_link_unknown_email_silent_no_token_created(self):
        """Nunca revela existência: email desconhecido → sem erro, sem token."""
        db = FakeDB()
        with patch.object(auth_service, "_send_portal_email") as send:
            auth_service.send_magic_link(db, "desconhecido@example.com")
        send.assert_not_called()
        assert db._store(PortalMagicToken) == []

    def test_send_magic_link_known_email_creates_hashed_token(self):
        db = FakeDB()
        identity = _make_identity(db)
        _make_credential(db, identity)

        with patch.object(auth_service, "_send_portal_email") as send:
            auth_service.send_magic_link(db, "cliente@example.com")

        send.assert_called_once()
        tokens = db._store(PortalMagicToken)
        assert len(tokens) == 1
        assert len(tokens[0].token_hash) == 64  # SHA-256 hex — cru nunca persiste
        body = send.call_args[0][2]
        assert tokens[0].token_hash == hash_magic_token(body.split("/portal/magic/")[1].split("\n")[0])

    def test_send_failure_does_not_raise(self):
        """Falha de envio não vaza erro (router responde 200 sempre)."""
        db = FakeDB()
        identity = _make_identity(db)
        _make_credential(db, identity)
        with patch.object(auth_service, "_send_portal_email", side_effect=RuntimeError("smtp down")):
            auth_service.send_magic_link(db, "cliente@example.com")  # não levanta


# ─── Registro ─────────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_new_identity(self):
        db = FakeDB()
        with patch.object(auth_service, "_send_portal_email"):
            result = auth_service.register(
                db, email="novo@example.com", name="Novo Cliente",
                phone="62 98888-7777", password="Senha123",
            )
        assert result["has_existing_history"] is False
        creds = db._store(PortalCredential)
        assert len(creds) == 1
        assert creds[0].email == "novo@example.com"
        assert creds[0].password_hash is not None
        assert creds[0].email_verified is False

    def test_register_existing_identity_offers_history(self):
        """Identity já existente pelo telefone → has_existing_history=True."""
        db = FakeDB()
        _make_identity(db, phone="5562988887777")
        with patch.object(auth_service, "_send_portal_email"):
            result = auth_service.register(
                db, email="novo@example.com", name="Cliente",
                phone="62 98888-7777",
            )
        assert result["has_existing_history"] is True

    def test_register_duplicate_email_409(self):
        db = FakeDB()
        identity = _make_identity(db)
        _make_credential(db, identity, email="dup@example.com")
        with pytest.raises(HTTPException) as exc:
            auth_service.register(
                db, email="dup@example.com", name="X", phone="62 97777-6666",
            )
        assert exc.value.status_code == 409

    def test_register_phone_without_ddd_422(self):
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            auth_service.register(
                db, email="x@example.com", name="X", phone="98888-7777",
            )
        assert exc.value.status_code == 422


# ─── 8. Dashboard cross-tenant ────────────────────────────────────────────────

class TestDashboard:
    def test_cross_tenant_dashboard_shows_both_tenants(self):
        """Cliente com 2 tenants vê appointments/credits/subscriptions de ambos."""
        db = FakeDB()
        identity = _make_identity(db)
        company_a, company_b = uuid.uuid4(), uuid.uuid4()
        cust_a = _make_customer(db, identity, company_a)
        cust_b = _make_customer(db, identity, company_b)
        _make_appointment(db, cust_a, hours_from_now=24)
        _make_appointment(db, cust_b, hours_from_now=48)
        _make_credit(db, cust_a)
        _make_subscription(db, cust_b)

        dash = portal_service.get_dashboard(db, identity.id)

        companies_seen = {a["company_id"] for a in dash["upcoming_appointments"]}
        assert companies_seen == {str(company_a), str(company_b)}
        assert len(dash["active_credits"]) == 1
        assert dash["active_credits"][0]["company_id"] == str(company_a)
        assert len(dash["active_subscriptions"]) == 1
        assert dash["active_subscriptions"][0]["company_id"] == str(company_b)

    def test_dashboard_excludes_past_and_terminal(self):
        db = FakeDB()
        identity = _make_identity(db)
        cust = _make_customer(db, identity)
        _make_appointment(db, cust, hours_from_now=-2)                      # passado
        _make_appointment(db, cust, hours_from_now=24, status="CANCELLED")  # terminal
        upcoming = _make_appointment(db, cust, hours_from_now=24)

        dash = portal_service.get_dashboard(db, identity.id)
        assert [a["id"] for a in dash["upcoming_appointments"]] == [str(upcoming.id)]

    def test_dashboard_other_identity_sees_nothing(self):
        """Isolamento: outra identity não vê dados que não são dela."""
        db = FakeDB()
        identity = _make_identity(db)
        cust = _make_customer(db, identity)
        _make_appointment(db, cust)
        other = _make_identity(db, phone="5511977776666")

        dash = portal_service.get_dashboard(db, other.id)
        assert dash["upcoming_appointments"] == []
        assert dash["active_credits"] == []
        assert dash["active_subscriptions"] == []


# ─── History / Credits ────────────────────────────────────────────────────────

class TestHistoryAndCredits:
    def test_history_only_terminal_statuses_paginated(self):
        db = FakeDB()
        identity = _make_identity(db)
        cust = _make_customer(db, identity)
        _make_appointment(db, cust, hours_from_now=-100, status="COMPLETED")
        _make_appointment(db, cust, hours_from_now=-50, status="NO_SHOW")
        _make_appointment(db, cust, hours_from_now=24, status="SCHEDULED")  # fora

        result = portal_service.get_history(db, identity.id, page=1, page_size=1)
        assert result["total"] == 2
        assert len(result["items"]) == 1

    def test_history_company_filter(self):
        db = FakeDB()
        identity = _make_identity(db)
        company_a = uuid.uuid4()
        cust_a = _make_customer(db, identity, company_a)
        cust_b = _make_customer(db, identity)
        _make_appointment(db, cust_a, hours_from_now=-10, status="COMPLETED")
        _make_appointment(db, cust_b, hours_from_now=-10, status="COMPLETED")

        result = portal_service.get_history(db, identity.id, company_id=company_a)
        assert result["total"] == 1
        assert result["items"][0]["company_id"] == str(company_a)

    def test_credits_fefo_order(self):
        """Ordenados por expires_at asc; sem expiração por último (FEFO)."""
        db = FakeDB()
        identity = _make_identity(db)
        cust = _make_customer(db, identity)
        no_expiry = _make_credit(db, cust, expires_in_days=None)
        late = _make_credit(db, cust, expires_in_days=30)
        soon = _make_credit(db, cust, expires_in_days=5)

        credits = portal_service.get_credits(db, identity.id)
        assert [c["credit_id"] for c in credits] == [
            str(soon.credit_id), str(late.credit_id), str(no_expiry.credit_id),
        ]


# ─── 9. Subscriptions pause/cancel ───────────────────────────────────────────

class TestSubscriptions:
    def test_pause_blocked_when_tenant_does_not_allow(self):
        """Default allow_subscription_pause=False → 403."""
        db = FakeDB()
        identity = _make_identity(db)
        cust = _make_customer(db, identity)
        sub = _make_subscription(db, cust)
        _make_tenant_config(db, cust.company_id)  # sem override → pause negado

        with pytest.raises(HTTPException) as exc:
            portal_service.pause_subscription(db, identity.id, sub.subscription_id)
        assert exc.value.status_code == 403
        assert sub.status == "ACTIVE"

    def test_pause_allowed_when_tenant_permits(self):
        db = FakeDB()
        identity = _make_identity(db)
        cust = _make_customer(db, identity)
        sub = _make_subscription(db, cust)
        _make_tenant_config(db, cust.company_id, {"allow_subscription_pause": True})

        result = portal_service.pause_subscription(db, identity.id, sub.subscription_id)
        assert sub.status == "PAUSED"
        assert result["status"] == "PAUSED"

    def test_cancel_allowed_by_default(self):
        """allow_subscription_cancel default True (opt-out)."""
        db = FakeDB()
        identity = _make_identity(db)
        cust = _make_customer(db, identity)
        sub = _make_subscription(db, cust)
        _make_tenant_config(db, cust.company_id)

        result = portal_service.cancel_subscription(db, identity.id, sub.subscription_id)
        assert sub.status == "CANCELLED"
        assert result["status"] == "CANCELLED"

    def test_cancel_blocked_when_tenant_opts_out(self):
        db = FakeDB()
        identity = _make_identity(db)
        cust = _make_customer(db, identity)
        sub = _make_subscription(db, cust)
        _make_tenant_config(db, cust.company_id, {"allow_subscription_cancel": False})

        with pytest.raises(HTTPException) as exc:
            portal_service.cancel_subscription(db, identity.id, sub.subscription_id)
        assert exc.value.status_code == 403

    def test_subscription_of_other_identity_404(self):
        """Ownership: assinatura de outro cliente → 404 (não 403)."""
        db = FakeDB()
        identity = _make_identity(db)
        cust = _make_customer(db, identity)
        sub = _make_subscription(db, cust)
        intruder = _make_identity(db, phone="5511977776666")

        with pytest.raises(HTTPException) as exc:
            portal_service.cancel_subscription(db, intruder.id, sub.subscription_id)
        assert exc.value.status_code == 404


# ─── 10–11. Payment sources ───────────────────────────────────────────────────

class TestPaymentSources:
    def test_add_without_payment_storage_consent_422(self):
        db = FakeDB()
        identity = _make_identity(db)
        company_id = uuid.uuid4()

        with pytest.raises(HTTPException) as exc:
            portal_service.add_payment_source(
                db, identity.id, company_id, "tok_abc", "ALWAYS",
            )
        assert exc.value.status_code == 422
        assert db._store(PaymentSourceAuthorization) == []

    def test_add_with_consent_succeeds(self):
        db = FakeDB()
        identity = _make_identity(db)
        company_id = uuid.uuid4()
        _grant_payment_storage(db, identity, company_id)

        result = portal_service.add_payment_source(
            db, identity.id, company_id, "tok_abc", "always",
            last_four="4242", brand="VISA",
        )
        assert result["mode"] == "ALWAYS"
        assert result["last_four"] == "4242"
        assert result["revoked_at"] is None
        assert len(db._store(PaymentSourceAuthorization)) == 1

    def test_add_invalid_mode_422(self):
        db = FakeDB()
        identity = _make_identity(db)
        company_id = uuid.uuid4()
        _grant_payment_storage(db, identity, company_id)

        with pytest.raises(HTTPException) as exc:
            portal_service.add_payment_source(
                db, identity.id, company_id, "tok_abc", "FOREVER",
            )
        assert exc.value.status_code == 422

    def test_revoke_sets_revoked_at(self):
        db = FakeDB()
        identity = _make_identity(db)
        company_id = uuid.uuid4()
        _grant_payment_storage(db, identity, company_id)
        created = portal_service.add_payment_source(
            db, identity.id, company_id, "tok_abc", "ALWAYS",
        )
        auth_id = uuid.UUID(created["id"])

        result = portal_service.revoke_payment_source(db, identity.id, auth_id)

        assert result["revoked_at"] is not None
        stored = db._store(PaymentSourceAuthorization)[0]
        assert stored.revoked_at is not None
        # Lista de fontes ativas não inclui revogadas
        assert portal_service.list_payment_sources(db, identity.id) == []

    def test_revoke_other_identity_source_404(self):
        db = FakeDB()
        identity = _make_identity(db)
        company_id = uuid.uuid4()
        _grant_payment_storage(db, identity, company_id)
        created = portal_service.add_payment_source(
            db, identity.id, company_id, "tok_abc", "ALWAYS",
        )
        intruder = _make_identity(db, phone="5511977776666")

        with pytest.raises(HTTPException) as exc:
            portal_service.revoke_payment_source(
                db, intruder.id, uuid.UUID(created["id"]),
            )
        assert exc.value.status_code == 404


# ─── Consents via Portal ──────────────────────────────────────────────────────

class TestPortalConsents:
    def test_grant_and_revoke_with_portal_source(self):
        db = FakeDB()
        identity = _make_identity(db)
        company_id = uuid.uuid4()

        granted = portal_service.grant_consent(
            db, identity.id, "MARKETING", "WHATSAPP", company_id=company_id,
        )
        assert granted.source_channel == "PORTAL"
        assert granted.status == "GRANTED"

        revoked = portal_service.revoke_consent(
            db, identity.id, "MARKETING", "WHATSAPP", company_id=company_id,
        )
        assert revoked.status == "REVOKED"
        # Append-only: ambos os registros persistem
        assert len(db._store(ConsentRecord)) == 2

    def test_list_consents_returns_current_state(self):
        db = FakeDB()
        identity = _make_identity(db)
        portal_service.grant_consent(db, identity.id, "MARKETING", None)
        current = portal_service.list_consents(db, identity.id)
        assert len(current) == 1
        assert current[0].status == "GRANTED"


# ─── 12. PATCH /portal/profile ────────────────────────────────────────────────

class TestProfile:
    def test_update_phone_re_resolves_identity(self):
        db = FakeDB()
        identity = _make_identity(db, phone="5562988887777")
        _make_credential(db, identity)

        result = portal_service.update_profile(db, identity, phone="11 97777-6666")

        assert identity.phone_e164 == "+5511977776666"
        assert identity.phone_national_normalized == "11977776666"
        assert result["phone_e164"] == "+5511977776666"

    def test_update_phone_of_other_identity_409(self):
        db = FakeDB()
        identity = _make_identity(db, phone="5562988887777")
        _make_identity(db, phone="5511977776666")  # telefone já em uso

        with pytest.raises(HTTPException) as exc:
            portal_service.update_profile(db, identity, phone="11 97777-6666")
        assert exc.value.status_code == 409

    def test_update_phone_without_ddd_422(self):
        db = FakeDB()
        identity = _make_identity(db)
        with pytest.raises(HTTPException) as exc:
            portal_service.update_profile(db, identity, phone="97777-6666")
        assert exc.value.status_code == 422

    def test_update_name(self):
        db = FakeDB()
        identity = _make_identity(db)
        result = portal_service.update_profile(db, identity, name="Novo Nome")
        assert identity.name == "Novo Nome"
        assert result["name"] == "Novo Nome"

    def test_update_email_requires_verification(self):
        """Email novo → email_verified=False + envio de verificação."""
        db = FakeDB()
        identity = _make_identity(db)
        cred = _make_credential(db, identity, email="velho@example.com")
        cred.email_verified = True

        with patch.object(auth_service, "_send_portal_email") as send:
            result = portal_service.update_profile(db, identity, email="novo@example.com")

        assert cred.email == "novo@example.com"
        assert cred.email_verified is False
        assert result["email_verification_sent"] is True
        send.assert_called_once()

    def test_update_email_already_taken_409(self):
        db = FakeDB()
        identity = _make_identity(db)
        _make_credential(db, identity, email="meu@example.com")
        other = _make_identity(db, phone="5511977776666")
        _make_credential(db, other, email="ocupado@example.com")

        with pytest.raises(HTTPException) as exc:
            portal_service.update_profile(db, identity, email="ocupado@example.com")
        assert exc.value.status_code == 409


# ─── 13. GET /portal/identity/me (resolve o 501 do Sprint A) ─────────────────

class TestIdentityMe:
    def test_identity_me_returns_identity_data(self):
        db = FakeDB()
        identity = _make_identity(db, name="Cliente Final", email="c@example.com")
        token = create_portal_token(identity.id)

        resolved = get_current_portal_identity(credentials=_bearer(token), db=db)

        from app.modules.identity.schemas import IdentityResponse
        response = IdentityResponse.model_validate(resolved)
        assert response.id == identity.id
        assert response.phone_e164 == identity.phone_e164
        assert response.name == "Cliente Final"
        assert response.cpf_masked is None  # CPF nunca sai em claro

    def test_identity_me_router_no_longer_501(self):
        """O endpoint /identity/me agora usa o dependency portal (sem 501)."""
        from app.modules.identity.router import get_my_identity
        identity = SimpleNamespace(id=uuid.uuid4())
        assert get_my_identity(identity=identity) is identity
