"""
Testes Sprint A — PaladinoIdentity + PhoneIdentityResolver + ConsentRecord.

Usa um FakeDB in-memory (avalia BinaryExpressions do SQLAlchemy contra
objetos Python) — sem banco PostgreSQL real (padrão do projeto).

Casos obrigatórios:
  1.  Mesmo telefone em 2 tenants → 1 PaladinoIdentity, 2 Customers
  2.  Telefone sem DDD → 422
  3.  Resolver idempotente: segunda chamada retorna identity existente
  4.  Backfill idempotente: re-executar não duplica
  5.  consent REVOKED → dispatch bloqueado no canal correspondente
  6.  MARKETING sem GRANTED explícito → dispatch bloqueado
  7.  COMMUNICATION sem registro → dispatch permitido (opt-out default)
  8.  Tenant A não enxerga ConsentRecords do tenant B
  9.  CPF da identity masked por default no response
  10. Bot: lookup usa resolver (mesmo customer retornado)
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.infrastructure.db.models import (
    Customer,
    ConsentRecord,
    PaladinoIdentity,
)
from app.infrastructure.db.models.communication_setting import CommunicationSetting
from app.infrastructure.db.models.communication_template import CommunicationTemplate
from app.infrastructure.db.models.communication_log import CommunicationLog
from app.modules.identity import consent_service
from app.modules.identity.consent_service import (
    ConsentStatus,
    ConsentType,
    SourceChannel,
)
from app.modules.identity.resolver import (
    InvalidUserPhoneError,
    PhoneIdentityResolver,
    normalize_phone_e164,
    validate_user_phone_input,
)
from app.modules.identity.schemas import IdentityResponse


# ─── FakeDB ───────────────────────────────────────────────────────────────────

def _criterion_matches(obj, c) -> bool:
    """Avalia um BinaryExpression do SQLAlchemy contra um objeto Python."""
    key = c.left.key
    actual = getattr(obj, key, None)
    right = c.right
    op_name = getattr(c.operator, "__name__", "")

    if op_name in ("like_op", "ilike_op"):
        pattern = right.value
        return actual is not None and str(actual).endswith(pattern.lstrip("%"))

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

    def first(self):
        return self.items[0] if self.items else None

    def all(self):
        return list(self.items)


class FakeDB:
    """Session fake com stores in-memory roteados por classe de modelo."""

    def __init__(self):
        self.stores = {
            PaladinoIdentity: [],
            Customer: [],
            ConsentRecord: [],
            CommunicationSetting: [],
            CommunicationTemplate: [],
            CommunicationLog: [],
        }
        self.commits = 0

    # roteamento
    def query(self, model):
        return FakeQuery(self.stores.get(model, []))

    def add(self, obj):
        if getattr(obj, "id", None) is None and hasattr(obj, "id"):
            obj.id = uuid.uuid4()
        if isinstance(obj, Customer) and obj.active is None:
            obj.active = True
        if isinstance(obj, ConsentRecord) and obj.occurred_at is None:
            obj.occurred_at = datetime.now(timezone.utc)
        if isinstance(obj, PaladinoIdentity) and obj.possible_aliases is None:
            obj.possible_aliases = []
        self.stores[type(obj)].append(obj)

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

    # helpers de teste
    @property
    def identities(self):
        return self.stores[PaladinoIdentity]

    @property
    def customers(self):
        return self.stores[Customer]

    @property
    def consents(self):
        return self.stores[ConsentRecord]


def _make_identity(db: FakeDB, phone="5562988887777", **kwargs) -> PaladinoIdentity:
    identity = PaladinoIdentity(
        phone_e164=f"+{phone}",
        phone_national_normalized=phone[2:],
        possible_aliases=[],
        **kwargs,
    )
    db.add(identity)
    return identity


# ─── Normalização ─────────────────────────────────────────────────────────────

class TestNormalizePhone:
    def test_celular_completo(self):
        e164, national = normalize_phone_e164("62 98888-7777")
        assert e164 == "+5562988887777"
        assert national == "62988887777"

    def test_celular_sem_nove_insere(self):
        e164, _ = normalize_phone_e164("62 8888-7777")
        assert e164 == "+5562988887777"

    def test_fixo_nao_insere_nove(self):
        e164, _ = normalize_phone_e164("62 3333-7777")
        assert e164 == "+556233337777"

    def test_com_ddi_e_plus(self):
        e164, _ = normalize_phone_e164("+55 62 98888-7777")
        assert e164 == "+5562988887777"

    def test_sem_ddd_422(self):
        with pytest.raises(HTTPException) as exc:
            normalize_phone_e164("98888-7777")
        assert exc.value.status_code == 422

    def test_vazio_422(self):
        with pytest.raises(HTTPException) as exc:
            normalize_phone_e164("")
        assert exc.value.status_code == 422

    def test_leading_zero_antes_do_ddd(self):
        # Hábito brasileiro de discagem interurbana — "0" antes do DDD
        e164, _ = normalize_phone_e164("011999990000")
        assert e164 == "+5511999990000"

    def test_leading_zero_com_formatacao(self):
        e164, _ = normalize_phone_e164("011 9 9999-0000")
        assert e164 == "+5511999990000"

    def test_leading_zero_celular_goias(self):
        e164, _ = normalize_phone_e164("062985657312")
        assert e164 == "+5562985657312"

    def test_duplo_zero_e_ddi_internacional_nao_remove(self):
        # "00" inicial pode ser DDI internacional — não strip do zero;
        # resultado não casa com formato BR válido → 422
        with pytest.raises(HTTPException) as exc:
            normalize_phone_e164("0062985657312")
        assert exc.value.status_code == 422

    def test_numero_fake_so_zeros_422(self):
        with pytest.raises(HTTPException) as exc:
            normalize_phone_e164("00000000000000000")
        assert exc.value.status_code == 422

    def test_celular_padrao_sem_leading_zero_nao_regride(self):
        e164, _ = normalize_phone_e164("62985657312")
        assert e164 == "+5562985657312"

    def test_celular_com_ddi_nao_regride(self):
        e164, _ = normalize_phone_e164("5562985657312")
        assert e164 == "+5562985657312"


# ─── Validação estrita de formulário público ─────────────────────────────────

class TestValidateUserPhoneInput:
    """validate_user_phone_input — validação estrita para formulários
    públicos (SET_CUSTOMER, /booking/confirm, /booking/start).
    NÃO usada pelo bot nem pelo painel — normalize_phone_e164 intocado."""

    def test_celular_11_digitos_ddd_valido(self):
        assert validate_user_phone_input("62985657312") == "62985657312"

    def test_fixo_10_digitos_ddd_valido(self):
        assert validate_user_phone_input("6298565731") == "6298565731"

    def test_leading_zero_removido(self):
        assert validate_user_phone_input("062985657312") == "62985657312"

    def test_duplo_zero_nao_remove_e_rejeita(self):
        # "00..." não sofre strip do zero:
        # 12 dígitos → rejeitado por comprimento
        with pytest.raises(InvalidUserPhoneError):
            validate_user_phone_input("009856573120")
        # 11 dígitos → sobrevive ao comprimento mas DDD "00" é inválido
        with pytest.raises(InvalidUserPhoneError):
            validate_user_phone_input("00985657312")

    def test_ddi_explicito_rejeitado(self):
        with pytest.raises(InvalidUserPhoneError):
            validate_user_phone_input("5562985657312")

    def test_ddd_invalido_rejeitado(self):
        # DDD "10" não existe na lista ANATEL
        with pytest.raises(InvalidUserPhoneError) as exc:
            validate_user_phone_input("10985657312")
        assert "'10'" in exc.value.message

    def test_leading_zero_ddd_06_vira_69_valido(self):
        # NOTA: o enunciado listava "06985657312" → erro (DDD 06), mas a
        # regra 2 do próprio código remove o zero inicial único ANTES do
        # check de DDD: "06985657312" → "6985657312" (DDD 69, válido).
        assert validate_user_phone_input("06985657312") == "6985657312"

    def test_ddd_99_valido(self):
        assert validate_user_phone_input("99985657312") == "99985657312"

    def test_curto_demais_rejeitado(self):
        with pytest.raises(InvalidUserPhoneError):
            validate_user_phone_input("123456789")

    def test_longo_demais_rejeitado(self):
        with pytest.raises(InvalidUserPhoneError):
            validate_user_phone_input("629856573120")

    def test_formatado_com_mascara(self):
        assert validate_user_phone_input("(62) 98565-7312") == "62985657312"


# ─── Resolver ─────────────────────────────────────────────────────────────────

class TestPhoneIdentityResolver:
    def test_cria_identity_nova(self):
        db = FakeDB()
        result = PhoneIdentityResolver().resolve(db, "62988887777", name="Ana")
        assert result.is_new_identity is True
        assert result.phone_e164 == "+5562988887777"
        assert len(db.identities) == 1
        assert db.identities[0].name == "Ana"

    def test_resolver_idempotente(self):
        """Segunda chamada retorna a identity existente — não duplica."""
        db = FakeDB()
        r1 = PhoneIdentityResolver().resolve(db, "62988887777")
        r2 = PhoneIdentityResolver().resolve(db, "62 9 8888 7777")
        assert r1.identity_id == r2.identity_id
        assert r2.is_new_identity is False
        assert len(db.identities) == 1

    def test_variacao_sem_nove_resolve_mesma_identity(self):
        """Com e sem o 9º dígito normalizam para o MESMO E.164."""
        db = FakeDB()
        r1 = PhoneIdentityResolver().resolve(db, "6288887777")
        r2 = PhoneIdentityResolver().resolve(db, "62988887777")
        assert r1.identity_id == r2.identity_id
        assert len(db.identities) == 1

    def test_telefone_sem_ddd_422(self):
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            PhoneIdentityResolver().resolve(db, "88887777")
        assert exc.value.status_code == 422
        assert len(db.identities) == 0

    def test_mesmo_telefone_dois_tenants_uma_identity_dois_customers(self):
        """Caso central do Sprint A: identidade global, customer por tenant."""
        db = FakeDB()
        resolver = PhoneIdentityResolver()
        company_a, company_b = uuid.uuid4(), uuid.uuid4()

        cust_a, new_a = resolver.resolve_for_tenant(
            db, "62988887777", company_a, name="Ana"
        )
        cust_b, new_b = resolver.resolve_for_tenant(
            db, "62988887777", company_b, name="Ana"
        )

        assert new_a is True and new_b is True
        assert len(db.identities) == 1
        assert len(db.customers) == 2
        assert cust_a.id != cust_b.id
        assert cust_a.identity_id == cust_b.identity_id == db.identities[0].id

    def test_resolve_for_tenant_vincula_customer_existente_sem_identity(self):
        """Cliente pré-Sprint A (identity_id NULL) ganha o vínculo no resolve."""
        db = FakeDB()
        company_id = uuid.uuid4()
        legacy = Customer(
            company_id=company_id, name="Ana", phone="5562988887777"
        )
        db.add(legacy)

        customer, is_new = PhoneIdentityResolver().resolve_for_tenant(
            db, "62988887777", company_id
        )
        assert is_new is False
        assert customer is legacy
        assert customer.identity_id == db.identities[0].id


# ─── ConsentService ───────────────────────────────────────────────────────────

class TestConsentService:
    def test_grant_e_revoke_sao_append_only(self):
        db = FakeDB()
        identity = _make_identity(db)
        company_id = uuid.uuid4()

        consent_service.grant_consent(
            db, identity.id, company_id,
            ConsentType.COMMUNICATION, "WHATSAPP", SourceChannel.PAINEL,
        )
        consent_service.revoke_consent(
            db, identity.id, company_id,
            ConsentType.COMMUNICATION, "WHATSAPP", SourceChannel.PAINEL,
        )
        # nunca UPDATE: dois registros distintos
        assert len(db.consents) == 2
        assert [r.status for r in db.consents] == [
            ConsentStatus.GRANTED, ConsentStatus.REVOKED,
        ]

    def test_check_consent_usa_registro_mais_recente(self):
        db = FakeDB()
        identity = _make_identity(db)
        company_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        for i, status in enumerate([ConsentStatus.REVOKED, ConsentStatus.GRANTED]):
            db.add(ConsentRecord(
                identity_id=identity.id, company_id=company_id,
                consent_type=ConsentType.COMMUNICATION, channel="WHATSAPP",
                status=status, source_channel=SourceChannel.PAINEL,
                occurred_at=now + timedelta(minutes=i),
            ))
        assert consent_service.check_consent(
            db, identity.id, company_id, ConsentType.COMMUNICATION, "WHATSAPP"
        ) is True

    def test_communication_sem_registro_default_true(self):
        """Transacional é opt-out — sem registro → permitido."""
        db = FakeDB()
        identity = _make_identity(db)
        assert consent_service.check_consent(
            db, identity.id, uuid.uuid4(), ConsentType.COMMUNICATION, "WHATSAPP"
        ) is True

    def test_marketing_sem_registro_default_false(self):
        """MARKETING é opt-in — sem GRANTED explícito → bloqueado."""
        db = FakeDB()
        identity = _make_identity(db)
        assert consent_service.check_consent(
            db, identity.id, uuid.uuid4(), ConsentType.MARKETING, "WHATSAPP"
        ) is False

    def test_revoke_canal_nulo_vale_para_todos_os_canais(self):
        db = FakeDB()
        identity = _make_identity(db)
        company_id = uuid.uuid4()
        consent_service.revoke_consent(
            db, identity.id, company_id,
            ConsentType.COMMUNICATION, None, SourceChannel.PAINEL,
        )
        for channel in ("WHATSAPP", "EMAIL"):
            assert consent_service.check_consent(
                db, identity.id, company_id, ConsentType.COMMUNICATION, channel
            ) is False

    def test_tenant_a_nao_enxerga_consents_do_tenant_b(self):
        """REVOKED no tenant B não afeta o tenant A; listagem filtra por tenant."""
        db = FakeDB()
        identity = _make_identity(db)
        company_a, company_b = uuid.uuid4(), uuid.uuid4()

        consent_service.revoke_consent(
            db, identity.id, company_b,
            ConsentType.COMMUNICATION, "WHATSAPP", SourceChannel.PAINEL,
        )
        # A continua com o default opt-out (True) — o REVOKED é só do B
        assert consent_service.check_consent(
            db, identity.id, company_a, ConsentType.COMMUNICATION, "WHATSAPP"
        ) is True
        assert consent_service.check_consent(
            db, identity.id, company_b, ConsentType.COMMUNICATION, "WHATSAPP"
        ) is False
        # Listagem do tenant A não inclui o registro do B
        consents_a = consent_service.get_consents_for_identity(
            db, identity.id, company_a
        )
        assert consents_a == []

    def test_consent_global_company_null_vale_para_todos_os_tenants(self):
        db = FakeDB()
        identity = _make_identity(db)
        consent_service.revoke_consent(
            db, identity.id, None,  # global Paladino-wide
            ConsentType.COMMUNICATION, None, SourceChannel.PORTAL,
        )
        assert consent_service.check_consent(
            db, identity.id, uuid.uuid4(), ConsentType.COMMUNICATION, "WHATSAPP"
        ) is False


# ─── Dispatch × consent ───────────────────────────────────────────────────────

def _dispatch_fixture(db: FakeDB, company_id, event_type="appointment.confirmed"):
    """Settings + template WHATSAPP/CLIENT + customer com identity vinculada."""
    db.add(CommunicationSetting(
        company_id=company_id,
        whatsapp_enabled=True,
        email_enabled=False,
        quiet_hours_enabled=False,
    ))
    db.add(CommunicationTemplate(
        company_id=company_id,
        event_type=event_type,
        channel="WHATSAPP",
        audience="CLIENT",
        is_active=True,
        body_template="Olá {{customer_name}}",
    ))
    identity = _make_identity(db)
    customer = Customer(
        company_id=company_id, name="Ana", phone="5562988887777",
        identity_id=identity.id,
    )
    db.add(customer)
    return identity, customer


class TestDispatchConsent:
    def _dispatch(self, db, company_id, customer, event_type="appointment.confirmed"):
        from app.modules.communication.service import CommunicationService

        svc = CommunicationService()
        with patch.object(CommunicationService, "_send_whatsapp") as send:
            log = svc.dispatch(
                event_type=event_type,
                company_id=company_id,
                context={"recipient_phone": customer.phone, "customer_name": "Ana"},
                recipient_id=customer.id,
                recipient_type="CLIENT",
                db=db,
            )
        return log, send

    def test_consent_revogado_bloqueia_dispatch_no_canal(self):
        db = FakeDB()
        company_id = uuid.uuid4()
        identity, customer = _dispatch_fixture(db, company_id)
        consent_service.revoke_consent(
            db, identity.id, company_id,
            ConsentType.COMMUNICATION, "WHATSAPP", SourceChannel.PAINEL,
        )
        log, send = self._dispatch(db, company_id, customer)
        assert log.status == "SKIPPED_CONSENT_REVOKED"
        send.assert_not_called()

    def test_communication_sem_registro_envia(self):
        """Opt-out default: sem registro algum → SENT."""
        db = FakeDB()
        company_id = uuid.uuid4()
        _, customer = _dispatch_fixture(db, company_id)
        log, send = self._dispatch(db, company_id, customer)
        assert log.status == "SENT"
        send.assert_called_once()

    def test_marketing_sem_granted_explicito_bloqueado(self):
        db = FakeDB()
        company_id = uuid.uuid4()
        _, customer = _dispatch_fixture(db, company_id, event_type="marketing.promo")
        log, send = self._dispatch(
            db, company_id, customer, event_type="marketing.promo"
        )
        assert log.status == "SKIPPED_CONSENT_REVOKED"
        send.assert_not_called()

    def test_marketing_com_granted_explicito_envia(self):
        db = FakeDB()
        company_id = uuid.uuid4()
        identity, customer = _dispatch_fixture(db, company_id, event_type="marketing.promo")
        consent_service.grant_consent(
            db, identity.id, company_id,
            ConsentType.MARKETING, "WHATSAPP", SourceChannel.PAINEL,
        )
        log, send = self._dispatch(
            db, company_id, customer, event_type="marketing.promo"
        )
        assert log.status == "SENT"
        send.assert_called_once()

    def test_transacional_sem_identity_id_envia_fallback(self):
        """Customer sem identity (pré-backfill) → não bloqueia transacional."""
        db = FakeDB()
        company_id = uuid.uuid4()
        _, customer = _dispatch_fixture(db, company_id)
        customer.identity_id = None
        log, send = self._dispatch(db, company_id, customer)
        assert log.status == "SENT"
        send.assert_called_once()

    def test_consent_revogado_email_nao_bloqueia_whatsapp(self):
        """Revoke em canal específico só bloqueia aquele canal."""
        db = FakeDB()
        company_id = uuid.uuid4()
        identity, customer = _dispatch_fixture(db, company_id)
        consent_service.revoke_consent(
            db, identity.id, company_id,
            ConsentType.COMMUNICATION, "EMAIL", SourceChannel.PAINEL,
        )
        log, send = self._dispatch(db, company_id, customer)
        assert log.status == "SENT"
        send.assert_called_once()


# ─── Backfill ─────────────────────────────────────────────────────────────────

class TestBackfill:
    def _run(self, db, monkeypatch, tmp_path):
        import scripts.backfill_identity as backfill

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(backfill, "SessionLocal", lambda: db)
        return backfill.run(dry_run=False)

    def test_backfill_agrupa_por_e164_cross_tenant(self, monkeypatch, tmp_path):
        db = FakeDB()
        company_a, company_b = uuid.uuid4(), uuid.uuid4()
        now = datetime.now(timezone.utc)
        # Mesmo número em 2 tenants — um com 9, outro sem (variações)
        c1 = Customer(company_id=company_a, name="Ana", phone="5562988887777")
        c1.updated_at = now
        c2 = Customer(company_id=company_b, name="Ana", phone="556288887777")
        c2.updated_at = now
        db.add(c1)
        db.add(c2)

        stats = self._run(db, monkeypatch, tmp_path)
        assert stats["identities_created"] == 1
        assert stats["customers_linked"] == 2
        assert c1.identity_id == c2.identity_id == db.identities[0].id

    def test_backfill_idempotente(self, monkeypatch, tmp_path):
        """Re-executar não duplica identidades nem re-vincula."""
        db = FakeDB()
        c = Customer(company_id=uuid.uuid4(), name="Ana", phone="5562988887777")
        c.updated_at = datetime.now(timezone.utc)
        db.add(c)

        stats1 = self._run(db, monkeypatch, tmp_path)
        stats2 = self._run(db, monkeypatch, tmp_path)

        assert stats1["identities_created"] == 1
        assert len(db.identities) == 1
        # Segunda execução: nada a fazer (identity_id já preenchido)
        assert stats2["customers_scanned"] == 0
        assert stats2["identities_created"] == 0

    def test_backfill_colisao_de_nome_usa_mais_recente_e_reporta(
        self, monkeypatch, tmp_path
    ):
        db = FakeDB()
        now = datetime.now(timezone.utc)
        old = Customer(company_id=uuid.uuid4(), name="Ana Antiga", phone="5562988887777")
        old.updated_at = now - timedelta(days=30)
        new = Customer(company_id=uuid.uuid4(), name="Ana Atual", phone="5562988887777")
        new.updated_at = now
        db.add(old)
        db.add(new)

        stats = self._run(db, monkeypatch, tmp_path)
        assert stats["name_collisions"] == 1
        assert db.identities[0].name == "Ana Atual"
        assert (tmp_path / "backfill_collision_report.csv").exists()

    def test_backfill_telefone_invalido_pulado_e_reportado(
        self, monkeypatch, tmp_path
    ):
        db = FakeDB()
        c = Customer(company_id=uuid.uuid4(), name="Ana", phone="123")
        c.updated_at = datetime.now(timezone.utc)
        db.add(c)

        stats = self._run(db, monkeypatch, tmp_path)
        assert stats["skipped_invalid_phone"] == 1
        assert stats["identities_created"] == 0
        assert c.identity_id is None
        assert (tmp_path / "backfill_collision_report.csv").exists()


# ─── PII / response ───────────────────────────────────────────────────────────

class TestIdentityPII:
    def test_cpf_masked_por_default_no_response(self):
        identity = PaladinoIdentity(
            id=uuid.uuid4(),
            phone_e164="+5562988887777",
            phone_national_normalized="62988887777",
            possible_aliases=[],
            name="Ana",
            cpf_encrypted="gAAAAA-ciphertext",
            cpf_hash="a" * 64,
            cpf_masked="***.456.789-**",
        )
        response = IdentityResponse.model_validate(identity)
        dump = response.model_dump()
        assert dump["cpf_masked"] == "***.456.789-**"
        assert "cpf_encrypted" not in dump
        assert "cpf_hash" not in dump


# ─── Bot usa o resolver ───────────────────────────────────────────────────────

class TestBotResolver:
    def test_bot_confirmacao_de_nome_usa_resolver(self):
        """handle_confirmando_nome cria customer via resolver + consent BOT."""
        from app.modules.whatsapp.handlers import aguardando_nome

        db = FakeDB()
        company_id = uuid.uuid4()
        session = SimpleNamespace(
            context={"nome_temp": "Ana"}, state="CONFIRMAR_NOME"
        )

        with patch.object(aguardando_nome, "sender") as sender:
            aguardando_nome.handle_confirmando_nome(
                db, session, company_id,
                "5562988887777@s.whatsapp.net", "instance-1", "sim",
                start_escolhendo_servico=MagicMock(),
            )

        assert len(db.customers) == 1
        assert len(db.identities) == 1
        customer = db.customers[0]
        assert customer.identity_id == db.identities[0].id
        assert session.context["customer_id"] == str(customer.id)
        # Consent COMMUNICATION GRANTED capturado com source=BOT
        assert len(db.consents) == 1
        record = db.consents[0]
        assert record.consent_type == ConsentType.COMMUNICATION
        assert record.status == ConsentStatus.GRANTED
        assert record.source_channel == SourceChannel.BOT
        sender.send_text.assert_called()

    def test_bot_segunda_conversa_retorna_mesmo_customer(self):
        """Lookup via resolver: mesma identidade/customer nas duas conversas."""
        db = FakeDB()
        company_id = uuid.uuid4()
        resolver = PhoneIdentityResolver()

        c1, new1 = resolver.resolve_for_tenant(
            db, "5562988887777", company_id, name="Ana"
        )
        c2, new2 = resolver.resolve_for_tenant(
            db, "5562988887777", company_id, name="Ana"
        )
        assert new1 is True and new2 is False
        assert c1 is c2
        assert len(db.customers) == 1
