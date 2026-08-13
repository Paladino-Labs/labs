"""
Testes S-painel-telemetria — leitura e rotulagem das conversas do bot.

Usa FakeDB in-memory (padrão Sprints A/C/D) — sem PostgreSQL real.
NÃO importa app.main (quebra o monkey-patch de test_sprint2_rbac).

Casos cobertos:
  1.  Lista agrupa por whatsapp_hash, mais recente primeiro
  2.  Contador de não-entendidas conta MENU_FALLBACK e SHADOW_NOT_ROUTED
  3.  INACTIVE_MODULE_MSG NÃO conta como não-entendida (o bot entendeu)
  4.  Tipo ilegível (áudio) conta como não-entendida
  5.  Filtro de data recorta a lista
  6.  Eventos sem mensagem (connection.update) ficam fora
  7.  A conversa vem em ordem cronológica ASCENDENTE
  8.  O expansível traz o diagnóstico da mensagem
  9.  Conversa inexistente → 404
  10. Rótulo novo é criado (upsert)
  11. Rótulo existente é corrigido, não duplicado
  12. Rótulo com os três campos vazios APAGA a linha
  13. understood inválido → 422
  14. expected_intent inválido → 422
  15. Rótulo sobre trace inexistente → 404
  16. O rótulo gravado volta na leitura da conversa
  17. O catálogo de rotulagem é servido pela API
  18. Usuário de tenant não alcança /platform (require_role)
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.deps import require_role
from app.infrastructure.db.models import Company
from app.infrastructure.db.models.bot_message_label import BotMessageLabel
from app.infrastructure.db.models.bot_message_trace import BotMessageTrace
from app.modules.platform import telemetry_service as svc


# ─── FakeDB (padrão Sprint A/C/D) ─────────────────────────────────────────────

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
    if op_name in ("ne", "is_not", "isnot", "is_not_op"):
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

    def order_by(self, *args):
        """Ordena de verdade por received_at — a ordem É o comportamento
        testado aqui (lista DESC, transcrição ASC)."""
        items = list(self.items)
        for clause in args:
            text = str(clause)
            if "received_at" in text:
                items.sort(
                    key=lambda i: (
                        i.received_at is not None,
                        i.received_at or datetime.min.replace(tzinfo=timezone.utc),
                    ),
                    reverse="DESC" in text.upper(),
                )
        return FakeQuery(items)

    def limit(self, n):
        return FakeQuery(self.items[:n])

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
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self._store(type(obj)).append(obj)

    def delete(self, obj):
        store = self._store(type(obj))
        if obj in store:
            store.remove(obj)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

BASE = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


def _trace(
    db,
    *,
    wa_hash="hash-a",
    masked="+55 62 *****-7777",
    minutes=0,
    text="oi",
    decision=None,
    intent=None,
    confidence=0.0,
    message_type="conversation",
    company_id=None,
    fsm_state="MENU_PRINCIPAL",
    handler=None,
    outbound=None,
    message_id="MSG",
    outcome="PROCESSED",
):
    classifier = {}
    if intent is not None or decision is not None:
        classifier["regex"] = {
            "intent": intent, "confidence": confidence,
            "matched": confidence > 0.0, "active_intents": None,
        }
        classifier["final"] = {
            "intent": intent, "confidence": confidence,
            "source": "REGEX", "entities": {},
            "classification_id": str(uuid.uuid4()), "threshold": 0.7,
        }
    if decision is not None:
        classifier["routing"] = {
            "decision": decision, "routed": decision == "ROUTED", "reason": None,
        }

    t = BotMessageTrace(
        id=uuid.uuid4(),
        company_id=company_id,
        received_at=BASE + timedelta(minutes=minutes),
        instance_name="paladino",
        event="messages.upsert",
        whatsapp_hash=wa_hash,
        whatsapp_masked=masked,
        message_id=f"{message_id}-{minutes}",
        message_type=message_type,
        session_id=uuid.uuid4(),
        fsm_state=fsm_state,
        fsm_state_after=fsm_state,
        outcome=outcome,
        user_input=text,
        webhook={},
        classifier=classifier,
        dispatch={"handler": handler, "path": [handler] if handler else []},
        outbound=outbound if outbound is not None else [],
        duration_ms=42,
    )
    db._store(BotMessageTrace).append(t)
    return t


def _actor_id():
    return uuid.uuid4()


# ─── 1–6: a lista de conversas ────────────────────────────────────────────────

def test_lista_agrupa_por_hash_mais_recente_primeiro():
    db = FakeDB()
    _trace(db, wa_hash="ana", minutes=0)
    _trace(db, wa_hash="ana", minutes=5)
    _trace(db, wa_hash="bruno", minutes=30)

    rows = svc.list_conversations(db)

    assert [r["whatsapp_hash"] for r in rows] == ["bruno", "ana"]
    assert rows[1]["message_count"] == 2
    assert rows[0]["message_count"] == 1


def test_contador_conta_menu_fallback_e_shadow():
    db = FakeDB()
    _trace(db, minutes=0, decision="ROUTED", intent="AGENDAR", confidence=0.9)
    _trace(db, minutes=1, decision="MENU_FALLBACK", intent="MENU_PRINCIPAL")
    _trace(db, minutes=2, decision="SHADOW_NOT_ROUTED", intent="AGENDAR", confidence=0.8)

    rows = svc.list_conversations(db)

    assert rows[0]["message_count"] == 3
    assert rows[0]["not_understood_count"] == 2


def test_inactive_module_nao_conta_como_nao_entendida():
    """O bot ENTENDEU e respondeu que o recurso está desligado — é outra
    conversa, não falta de entendimento."""
    db = FakeDB()
    _trace(
        db, minutes=0, decision="INACTIVE_MODULE_MSG",
        intent="COMPRAR_PRODUTO", confidence=0.9,
    )

    rows = svc.list_conversations(db)

    assert rows[0]["not_understood_count"] == 0


def test_tipo_ilegivel_conta_como_nao_entendida():
    """Áudio/imagem/sticker chegam com texto vazio e reexibem o menu — o
    cliente falou e o bot não ouviu (classe catalogada no S-bot-1)."""
    db = FakeDB()
    _trace(db, minutes=0, message_type="audioMessage", text=None)

    rows = svc.list_conversations(db)

    assert rows[0]["not_understood_count"] == 1


def test_filtro_de_data_recorta_a_lista():
    db = FakeDB()
    _trace(db, wa_hash="antigo", minutes=0)
    _trace(db, wa_hash="novo", minutes=60 * 24 * 3)

    rows = svc.list_conversations(db, date_from=BASE + timedelta(days=1))

    assert [r["whatsapp_hash"] for r in rows] == ["novo"]


def test_evento_sem_mensagem_fica_fora():
    """connection.update também vira trace (o ponto do S-bot-1 é que nada
    some), mas não é mensagem — não entra na transcrição nem na contagem."""
    db = FakeDB()
    _trace(db, wa_hash="ana", minutes=0)
    ruido = _trace(db, wa_hash="ana", minutes=1)
    ruido.message_id = None
    ruido.user_input = None
    ruido.message_type = None

    rows = svc.list_conversations(db)

    assert rows[0]["message_count"] == 1


# ─── 7–9: a conversa ──────────────────────────────────────────────────────────

def test_conversa_vem_em_ordem_cronologica():
    db = FakeDB()
    _trace(db, minutes=10, text="a terceira")
    _trace(db, minutes=0, text="a primeira")
    _trace(db, minutes=5, text="a segunda")

    convo = svc.get_conversation(db, "hash-a")

    assert [m["text"] for m in convo["messages"]] == [
        "a primeira", "a segunda", "a terceira",
    ]
    assert convo["message_count"] == 3


def test_expansivel_traz_o_diagnostico():
    db = FakeDB()
    _trace(
        db, minutes=0, text="quero cortar o cabelo",
        decision="MENU_FALLBACK", intent="MENU_PRINCIPAL",
        fsm_state="MENU_PRINCIPAL", handler="show_menu_principal",
        outbound=[{"kind": "menu", "text": "Escolha uma opção", "ok": True}],
    )

    m = svc.get_conversation(db, "hash-a")["messages"][0]

    assert m["diagnosis"]["generic_menu"] is True
    assert m["diagnosis"]["not_understood"] is True
    assert m["diagnosis"]["reason"] == "MENU_FALLBACK"
    assert m["detail"]["fsm_state"] == "MENU_PRINCIPAL"
    assert m["detail"]["handler"] == "show_menu_principal"
    assert m["detail"]["message_type"] == "conversation"
    assert m["detail"]["outcome"] == "PROCESSED"
    assert m["detail"]["regex"]["matched"] is False
    assert m["outbound"][0]["text"] == "Escolha uma opção"


def test_conversa_inexistente_404():
    db = FakeDB()
    with pytest.raises(HTTPException) as e:
        svc.get_conversation(db, "nao-existe")
    assert e.value.status_code == 404


# ─── 10–16: a marcação ────────────────────────────────────────────────────────

def test_rotulo_novo_e_criado():
    db = FakeDB()
    t = _trace(db, minutes=0)

    out = svc.upsert_label(db, t.id, "NO", "agendar", "pediu corte", _actor_id())

    assert out["label"]["understood"] == "NO"
    assert out["label"]["expected_intent"] == "agendar"
    assert len(db._store(BotMessageLabel)) == 1


def test_rotulo_existente_e_corrigido_nao_duplicado():
    db = FakeDB()
    t = _trace(db, minutes=0)
    actor = _actor_id()

    svc.upsert_label(db, t.id, "NO", "agendar", None, actor)
    out = svc.upsert_label(db, t.id, "WRONG", "preco", None, actor)

    assert len(db._store(BotMessageLabel)) == 1
    assert out["label"]["understood"] == "WRONG"
    assert out["label"]["expected_intent"] == "preco"


def test_rotulo_vazio_apaga_a_linha():
    """É como a tela desfaz uma marcação — e o CHECK do banco protege contra
    a linha-fantasma que um caminho futuro poderia reintroduzir."""
    db = FakeDB()
    t = _trace(db, minutes=0)
    actor = _actor_id()
    svc.upsert_label(db, t.id, "NO", "agendar", None, actor)

    out = svc.upsert_label(db, t.id, None, None, "   ", actor)

    assert out["label"] is None
    assert db._store(BotMessageLabel) == []


def test_understood_invalido_422():
    db = FakeDB()
    t = _trace(db, minutes=0)
    with pytest.raises(HTTPException) as e:
        svc.upsert_label(db, t.id, "TALVEZ", None, None, _actor_id())
    assert e.value.status_code == 422


def test_expected_intent_invalido_422():
    db = FakeDB()
    t = _trace(db, minutes=0)
    with pytest.raises(HTTPException) as e:
        svc.upsert_label(db, t.id, None, "fazer_cafe", None, _actor_id())
    assert e.value.status_code == 422


def test_rotulo_sobre_trace_inexistente_404():
    db = FakeDB()
    with pytest.raises(HTTPException) as e:
        svc.upsert_label(db, uuid.uuid4(), "NO", None, None, _actor_id())
    assert e.value.status_code == 404


def test_rotulo_gravado_volta_na_leitura():
    """O critério real do Silva: marcar persiste e continua lá ao recarregar."""
    db = FakeDB()
    t1 = _trace(db, minutes=0, text="oi")
    _trace(db, minutes=1, text="quero agendar")
    svc.upsert_label(db, t1.id, "NO", "saudacao", "só cumprimentou", _actor_id())

    msgs = svc.get_conversation(db, "hash-a")["messages"]

    assert msgs[0]["label"]["understood"] == "NO"
    assert msgs[0]["label"]["expected_intent"] == "saudacao"
    assert msgs[0]["label"]["note"] == "só cumprimentou"
    # Marcar é OPCIONAL por mensagem: o que está certo fica em branco.
    assert msgs[1]["label"] is None


# ─── 17–18: catálogo e acesso ─────────────────────────────────────────────────

def test_catalogo_de_rotulagem_e_servido_pela_api():
    """A tela não repete a lista — acrescentar rótulo é editar o service."""
    assert "agendar" in svc.EXPECTED_INTENTS
    assert "saudacao" in svc.EXPECTED_INTENTS
    assert "agradecimento" in svc.EXPECTED_INTENTS
    assert set(svc.UNDERSTOOD_VALUES) == {"YES", "NO", "WRONG"}


@pytest.mark.parametrize("role", ["OWNER", "ADMIN", "OPERATOR", "PROFESSIONAL"])
def test_usuario_de_tenant_nao_alcanca_platform(role):
    """A tela vive sob a dependency PLATFORM_OWNER do router /platform —
    nenhum papel novo foi criado neste sprint."""
    guard = require_role("PLATFORM_OWNER")
    user = SimpleNamespace(
        id=uuid.uuid4(), role=role, company_id=uuid.uuid4(), active=True,
    )
    with pytest.raises(HTTPException) as e:
        guard(user=user)
    assert e.value.status_code == 403


def test_platform_owner_passa_no_guard():
    guard = require_role("PLATFORM_OWNER")
    user = SimpleNamespace(
        id=uuid.uuid4(), role="PLATFORM_OWNER", company_id=None, active=True,
    )
    assert guard(user=user) is user
