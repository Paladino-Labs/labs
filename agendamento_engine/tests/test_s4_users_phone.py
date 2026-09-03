"""
S4 — `users.phone` editável.

Antes deste sprint o telefone era write-once no convite: nada no sistema o
alterava depois. Medido em produção: `owners_ativos = 1`, `owners_com_telefone
= 0` nos dois tenants, com `whatsapp_enabled = true` — o canal ligado e sem
destino, e a escalada caindo no e-mail (`communication/service.py:172-179` só
coloca WHATSAPP na preferência se `recipient_phone` estiver preenchido).

Dois caminhos:
  * `PATCH /auth/profile`  — o próprio usuário (o schema já previa a expansão).
  * `PATCH /users/{id}/phone` — OWNER/ADMIN corrigindo terceiro do PRÓPRIO
    tenant.

O que os testes protegem:
  1. Formato — a normalização é a MESMA função do convite; um telefone gravado
     pela rota nova é byte-a-byte igual ao gravado pelo convite. É o único
     risco real deste sprint: dois formatos para o mesmo usuário quebrariam
     quem lê o campo (`conversation_handler`, `auth/service`) em silêncio.
  2. Cross-tenant — OWNER de A não alcança usuário de B. É o teste que impede
     este sprint de reintroduzir o defeito que a S0.2 fechou em assign_role.
  3. Hierarquia — INVITE_PERMISSION, o mesmo gate de assign_role.
  4. Validação — DDD fora da whitelist ANATEL e comprimento errado → 422.
  5. Regressão do convite depois da extração da função compartilhada.

⚠️ Persistência real (o valor sobrevive ao reload) NÃO é provada aqui: o
FakeDB abaixo não é um banco, e um teste de persistência sobre ele é vazio
(lição registrada no S2). O que se afirma aqui é que o service ATRIBUI e chama
commit; a persistência de verdade foi verificada em dev, pela tela.
"""
import uuid

import pytest
from fastapi import HTTPException

from app.infrastructure.db.models.user import User
from app.modules.users.service import _normalize_invite_phone, update_user_phone


# ── FakeDB (padrão de tests/test_s02_cross_tenant_users.py) ──────────────────

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
        self.commits = 0

    def _store(self, model):
        return self.stores.setdefault(model, [])

    def query(self, model, *rest):
        return FakeQuery(self._store(model))

    def add(self, obj):
        self._store(type(obj)).append(obj)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass


TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())


def _user(company_id, role, phone=None):
    return User(
        id=str(uuid.uuid4()),
        company_id=company_id,
        email=f"{uuid.uuid4().hex[:8]}@ex.com",
        password_hash="x",
        role=role,
        active=True,
        phone=phone,
    )


@pytest.fixture(autouse=True)
def _no_audit_table(monkeypatch):
    """audit_logs não existe no FakeDB — o objeto deste arquivo não é a auditoria."""
    monkeypatch.setattr(
        "app.modules.users.service.record_sensitive_action",
        lambda ctx, db: None,
    )


def _db_with(*users):
    db = FakeDB()
    for u in users:
        db.add(u)
    return db


# ── 1. Formato: idêntico ao do convite ───────────────────────────────────────

CASES = [
    ("62985657312",     "5562985657312"),  # celular, 11 dígitos
    ("(62) 98565-7312", "5562985657312"),  # com máscara
    ("062985657312",    "5562985657312"),  # zero de interurbano
    ("6285657312",      "5562985657312"),  # celular sem o 9º → insere
    ("6232251234",      "556232251234"),   # FIXO (local em 2/3/4) → não insere
    ("11999998888",     "5511999998888"),
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_terceiro_grava_no_mesmo_formato_do_convite(raw, expected):
    """A rota nova e o convite produzem a MESMA string para a mesma entrada.

    Não basta "parecer E.164": se a rota nova divergisse, o mesmo usuário teria
    dois formatos conforme o caminho, e o `evolution_client` receberia um
    número que não é o dele.
    """
    owner = _user(TENANT_A, "OWNER")
    alvo = _user(TENANT_A, "PROFESSIONAL")
    db = _db_with(owner, alvo)

    update_user_phone(db, owner, alvo.id, raw)

    assert alvo.phone == expected
    # O lado do convite, pela função que ele próprio usa:
    assert alvo.phone == _normalize_invite_phone(raw)


def test_formato_nao_leva_o_mais_e_cabe_na_coluna():
    """users.phone é String(20) e a convenção é E.164 SEM o '+'."""
    owner = _user(TENANT_A, "OWNER")
    alvo = _user(TENANT_A, "OPERATOR")
    db = _db_with(owner, alvo)

    update_user_phone(db, owner, alvo.id, "(11) 99999-8888")

    assert not alvo.phone.startswith("+")
    assert alvo.phone.isdigit()
    assert len(alvo.phone) <= 20


# ── 2. Validação ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "9999",             # curto demais
    "123456789012345",  # comprimento inválido / DDI
    "abcdefghij",       # sem dígitos
])
def test_telefone_invalido_e_422(raw):
    owner = _user(TENANT_A, "OWNER")
    alvo = _user(TENANT_A, "PROFESSIONAL")
    db = _db_with(owner, alvo)

    with pytest.raises(HTTPException) as exc:
        update_user_phone(db, owner, alvo.id, raw)
    assert exc.value.status_code == 422
    assert alvo.phone is None
    assert db.commits == 0


def test_ddd_fora_da_whitelist_anatel_e_422():
    """23 não é DDD atribuído — a whitelist de identity/valid_ddds pega."""
    owner = _user(TENANT_A, "OWNER")
    alvo = _user(TENANT_A, "PROFESSIONAL")
    db = _db_with(owner, alvo)

    with pytest.raises(HTTPException) as exc:
        update_user_phone(db, owner, alvo.id, "23987654321")
    assert exc.value.status_code == 422
    assert "23" in str(exc.value.detail)
    assert alvo.phone is None


def test_vazio_limpa_o_campo():
    owner = _user(TENANT_A, "OWNER")
    alvo = _user(TENANT_A, "OPERATOR", phone="5562985657312")
    db = _db_with(owner, alvo)

    update_user_phone(db, owner, alvo.id, "")

    assert alvo.phone is None


def test_atribui_e_faz_commit():
    """Não é prova de persistência (FakeDB não é banco) — é prova de que o
    service não esquece o commit, que é o defeito que faria a tela "aceitar e
    não salvar"."""
    owner = _user(TENANT_A, "OWNER")
    alvo = _user(TENANT_A, "OPERATOR")
    db = _db_with(owner, alvo)

    update_user_phone(db, owner, alvo.id, "62985657312")

    assert alvo.phone == "5562985657312"
    assert db.commits == 1


# ── 3. Cross-tenant ──────────────────────────────────────────────────────────

def test_owner_do_tenant_a_nao_edita_usuario_do_tenant_b():
    """🔴 O teste que impede este sprint de repetir o defeito do assign_role."""
    owner_a = _user(TENANT_A, "OWNER")
    alvo_b = _user(TENANT_B, "PROFESSIONAL", phone="5511999998888")
    db = _db_with(owner_a, alvo_b)

    with pytest.raises(HTTPException) as exc:
        update_user_phone(db, owner_a, alvo_b.id, "62985657312")

    assert exc.value.status_code == 404
    assert alvo_b.phone == "5511999998888"  # intacto
    assert db.commits == 0


def test_alvo_de_outro_tenant_responde_como_inexistente():
    """Indistinguibilidade: mesmo status e mesmo detail — não revelar que o
    usuário existe em outro tenant."""
    owner_a = _user(TENANT_A, "OWNER")
    alvo_b = _user(TENANT_B, "PROFESSIONAL")
    db = _db_with(owner_a, alvo_b)

    with pytest.raises(HTTPException) as outro:
        update_user_phone(db, owner_a, alvo_b.id, "62985657312")
    with pytest.raises(HTTPException) as inexistente:
        update_user_phone(db, owner_a, str(uuid.uuid4()), "62985657312")

    assert outro.value.status_code == inexistente.value.status_code
    assert outro.value.detail == inexistente.value.detail


def test_usuario_inativo_nao_e_alcancado():
    owner = _user(TENANT_A, "OWNER")
    alvo = _user(TENANT_A, "PROFESSIONAL")
    alvo.active = False
    db = _db_with(owner, alvo)

    with pytest.raises(HTTPException) as exc:
        update_user_phone(db, owner, alvo.id, "62985657312")
    assert exc.value.status_code == 404


# ── 4. Hierarquia (INVITE_PERMISSION) ────────────────────────────────────────

def test_owner_edita_terceiro():
    owner = _user(TENANT_A, "OWNER")
    alvo = _user(TENANT_A, "ADMIN")
    db = _db_with(owner, alvo)

    update_user_phone(db, owner, alvo.id, "62985657312")
    assert alvo.phone == "5562985657312"


def test_owner_edita_o_proprio_telefone_pela_rota_de_terceiro():
    """O caso que motiva o sprint: o OWNER sem telefone se conserta."""
    owner = _user(TENANT_A, "OWNER")
    db = _db_with(owner)

    update_user_phone(db, owner, owner.id, "62985657312")
    assert owner.phone == "5562985657312"


def test_operator_nao_edita_terceiro():
    """OPERATOR não tem ninguém em INVITE_PERMISSION → 403.

    Na rota HTTP ele já é barrado antes, por require_role; aqui garante-se que
    o service também não confia só no router.
    """
    operador = _user(TENANT_A, "OPERATOR")
    alvo = _user(TENANT_A, "PROFESSIONAL")
    db = _db_with(operador, alvo)

    with pytest.raises(HTTPException) as exc:
        update_user_phone(db, operador, alvo.id, "62985657312")
    assert exc.value.status_code == 403
    assert alvo.phone is None


def test_admin_nao_edita_telefone_de_owner():
    """ADMIN gerencia OPERATOR/PROFESSIONAL. Trocar o telefone de um OWNER
    redireciona a escalada — tem o peso de assign_role, e o mesmo gate."""
    admin = _user(TENANT_A, "ADMIN")
    owner = _user(TENANT_A, "OWNER", phone="5562985657312")
    db = _db_with(admin, owner)

    with pytest.raises(HTTPException) as exc:
        update_user_phone(db, admin, owner.id, "11999998888")
    assert exc.value.status_code == 403
    assert owner.phone == "5562985657312"


def test_admin_edita_telefone_de_professional():
    admin = _user(TENANT_A, "ADMIN")
    alvo = _user(TENANT_A, "PROFESSIONAL")
    db = _db_with(admin, alvo)

    update_user_phone(db, admin, alvo.id, "62985657312")
    assert alvo.phone == "5562985657312"


# ── 5. Regressão do convite ──────────────────────────────────────────────────

def test_convite_continua_exigindo_telefone():
    """A extração da função compartilhada não podia tornar o convite opcional."""
    with pytest.raises(HTTPException) as exc:
        _normalize_invite_phone("")
    assert exc.value.status_code == 422
    assert "obrigatório" in exc.value.detail


def test_convite_continua_rejeitando_ddd_invalido():
    with pytest.raises(HTTPException) as exc:
        _normalize_invite_phone("23987654321")
    assert exc.value.status_code == 422


def test_convite_continua_gravando_e164_sem_mais():
    assert _normalize_invite_phone("(62) 98565-7312") == "5562985657312"


# ── 6. O próprio usuário (PATCH /auth/profile) ───────────────────────────────

def _profile(body_kwargs):
    """Chama o handler de PATCH /auth/profile com o schema real."""
    from app.modules.auth.router import update_profile
    from app.modules.auth.schemas import UpdateProfileRequest
    return UpdateProfileRequest(**body_kwargs), update_profile


def test_proprio_usuario_edita_o_proprio_telefone():
    """O caminho que o schema já deixava explicitamente aberto."""
    body, handler = _profile({"phone": "(62) 98565-7312"})
    user = _user(TENANT_A, "OWNER")
    db = FakeDB()

    out = handler(body=body, user=user, db=db)

    assert user.phone == "5562985657312"
    assert out["phone"] == "5562985657312"
    assert db.commits == 1


def test_proprio_usuario_com_telefone_invalido_recebe_422():
    body, handler = _profile({"phone": "9999"})
    user = _user(TENANT_A, "PROFESSIONAL")
    db = FakeDB()

    with pytest.raises(HTTPException) as exc:
        handler(body=body, user=user, db=db)
    assert exc.value.status_code == 422
    assert user.phone is None
    assert db.commits == 0


def test_proprio_usuario_ddd_fora_da_whitelist_recebe_422():
    body, handler = _profile({"phone": "23987654321"})
    user = _user(TENANT_A, "OPERATOR")
    db = FakeDB()

    with pytest.raises(HTTPException) as exc:
        handler(body=body, user=user, db=db)
    assert exc.value.status_code == 422


def test_profile_sem_phone_no_corpo_preserva_o_telefone():
    """🔴 A regressão silenciosa: quem só troca o nome não pode perder o
    telefone. É por isso que o handler olha `model_fields_set` em vez de
    `is not None`."""
    body, handler = _profile({"name": "Novo Nome"})
    user = _user(TENANT_A, "OWNER", phone="5562985657312")
    db = FakeDB()

    handler(body=body, user=user, db=db)

    assert user.name == "Novo Nome"
    assert user.phone == "5562985657312"


def test_profile_com_phone_null_limpa():
    body, handler = _profile({"phone": None})
    user = _user(TENANT_A, "OWNER", phone="5562985657312")
    db = FakeDB()

    handler(body=body, user=user, db=db)

    assert user.phone is None


def test_profile_e_convite_produzem_o_mesmo_formato():
    """Os dois lados, lado a lado — o risco nomeado no sprint."""
    body, handler = _profile({"phone": "62 98565-7312"})
    user = _user(TENANT_A, "OWNER")
    handler(body=body, user=user, db=FakeDB())

    assert user.phone == _normalize_invite_phone("62 98565-7312")
