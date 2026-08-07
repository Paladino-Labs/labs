"""Testes S-bot-1 — telemetria ponta a ponta + parser de reações.

Os cinco requisitos do sprint, na ordem do enunciado:

  1. Nada regride — mensagem normal é processada exatamente como hoje.
  2. A telemetria registra a trajetória completa, com os campos de cada etapa
     (webhook, classificador, dispatcher, saída).
  3. Reação não é tratada como mensagem — o bot não reinicia.
  4. Reação é registrada.
  5. ⚠️ Falha ao registrar telemetria NÃO derruba o processamento — o mais
     importante: instrumento que quebra o instrumentado é pior que nenhum.

Estratégia: FakeDB in-memory com avaliação real de filtros (padrão Sprint 2.7)
+ webhook real (o `finally` que grava o trace é do router, e é ele que precisa
ser exercitado). A gravação usa SessionLocal PRÓPRIA — capturada por
monkeypatch, não por FakeDB.
"""
import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import app.infrastructure.db.session as db_session_mod
from app.core.config import settings
from app.infrastructure.db.models import (
    BotSession,
    CompanySettings,
    WhatsAppConnection,
)
from app.modules.whatsapp import bot_service, sender, trace
from app.modules.whatsapp import router as wa_router
from app.modules.whatsapp.helpers import extract_message_type, extract_reaction


# ─── FakeDB (padrão test_sprint27_inbox) ──────────────────────────────────────

def _criterion_matches(obj, c) -> bool:
    key = c.left.key
    actual = getattr(obj, key, None)
    right = c.right
    right_cls = right.__class__.__name__
    if right_cls == "True_":
        val = True
    elif right_cls == "False_":
        val = False
    elif right_cls == "Null":
        val = None
    else:
        val = getattr(right, "value", None)
    op_name = getattr(c.operator, "__name__", "")
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

    def with_for_update(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

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

    def query(self, model, *rest):
        return FakeQuery(self._store(model))

    def add(self, obj):
        if getattr(obj, "id", None) is None and hasattr(obj, "id"):
            obj.id = uuid.uuid4()
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


# ─── Fixtures ─────────────────────────────────────────────────────────────────

JID = "5511987654321@s.whatsapp.net"
INSTANCE = "inst-x"


@pytest.fixture
def sent(monkeypatch):
    """Captura tudo que o bot envia (o sender real chamaria a Evolution)."""
    out = []
    monkeypatch.setattr(
        wa_router.connection_service, "handle_connection_update",
        lambda *a, **k: None, raising=False,
    )
    import app.modules.whatsapp.evolution_client as ec
    monkeypatch.setattr(ec, "send_text",
                        lambda inst, to, text: out.append(("text", text)))
    monkeypatch.setattr(ec, "send_poll",
                        lambda inst, to, name, values: out.append(("poll", name)))
    monkeypatch.setattr(ec, "send_list",
                        lambda *a, **k: out.append(("list", a[2] if len(a) > 2 else "")))
    monkeypatch.setattr(ec, "send_buttons",
                        lambda *a, **k: out.append(("buttons", "")))
    return out


class _TraceSink:
    """Substitui a SessionLocal própria do trace e guarda as linhas gravadas."""

    def __init__(self):
        self.rows = []
        self.raise_on_commit = False

    def __call__(self):
        sink = self

        class _S:
            def add(self, obj):
                sink.rows.append(obj)

            def commit(self):
                if sink.raise_on_commit:
                    raise RuntimeError("banco de telemetria indisponível")

            def execute(self, *a, **k):
                return SimpleNamespace(rowcount=0)

            def rollback(self):
                pass

            def close(self):
                pass

        return _S()


@pytest.fixture
def traces(monkeypatch):
    sink = _TraceSink()
    monkeypatch.setattr(db_session_mod, "SessionLocal", sink)
    monkeypatch.setattr(settings, "BOT_TRACE_ENABLED", True)
    return sink


@pytest.fixture(autouse=True)
def _clear_trace_context():
    yield
    try:
        trace.finish()
    except Exception:
        pass


def make_db(state="MENU_PRINCIPAL", customer_id=None, last_message_id=None):
    db = FakeDB()
    cid = uuid.uuid4()
    db._store(WhatsAppConnection).append(
        SimpleNamespace(id=uuid.uuid4(), company_id=cid, instance_name=INSTANCE)
    )
    db._store(CompanySettings).append(
        SimpleNamespace(company_id=cid, bot_enabled=True)
    )
    db._store(bot_service.Company).append(
        SimpleNamespace(id=cid, name="Barbearia", timezone="America/Sao_Paulo")
    )
    session = SimpleNamespace(
        id=uuid.uuid4(), company_id=cid, whatsapp_id=JID, state=state,
        context={"customer_name": "Maria", **({"customer_id": str(customer_id)}
                                              if customer_id else {})},
        last_message_id=last_message_id, expires_at=None,
    )
    db._store(BotSession).append(session)
    return db, cid, session


def upsert(message: dict, msg_id="MSG-1", push_name="Maria Silva"):
    return {
        "event": "messages.upsert",
        "instance": INSTANCE,
        "data": {
            "key": {"id": msg_id, "fromMe": False, "remoteJid": JID},
            "pushName": push_name,
            "message": message,
        },
    }


REACTION = {"reactionMessage": {"key": {"id": "MSG-CONFIRMACAO"}, "text": "👍"}}


class FakeRequest:
    def __init__(self, payload):
        self.headers = {}
        self._payload = payload

    async def json(self):
        return self._payload


def drive(db, payload):
    """Exercita o webhook REAL — é dele o `finally` que grava o trace."""
    return asyncio.run(wa_router.webhook(FakeRequest(payload), db))


# ══ Parte 2 — o parser de reações (unitário) ═════════════════════════════════

def test_extract_reaction_reconhece_reacao():
    r = extract_reaction(upsert(REACTION)["data"])
    assert r == {"emoji": "👍", "target_message_id": "MSG-CONFIRMACAO", "removed": False}


def test_extract_reaction_reacao_removida():
    """Tirar a reação usa o MESMO formato, com text vazio — também é reação."""
    data = upsert({"reactionMessage": {"key": {"id": "M"}, "text": ""}})["data"]
    r = extract_reaction(data)
    assert r["removed"] is True and r["emoji"] == ""


@pytest.mark.parametrize("message", [
    {"conversation": "quero cortar o cabelo"},
    {"extendedTextMessage": {"text": "oi"}},
    {"listResponseMessage": {"singleSelectReply": {"selectedRowId": "opt_agendar"}}},
])
def test_extract_reaction_nao_confunde_mensagem_normal(message):
    assert extract_reaction(upsert(message)["data"]) is None


def test_extract_message_type_discrimina_o_que_chegou():
    assert extract_message_type(upsert(REACTION)["data"]) == "reactionMessage"
    assert extract_message_type(upsert({"conversation": "oi"})["data"]) == "conversation"
    assert extract_message_type(upsert({"audioMessage": {}})["data"]) == "audioMessage"
    assert extract_message_type({"messageType": "imageMessage"}) == "imageMessage"


# ══ Requisito 3 — reação não é tratada como mensagem ═════════════════════════

def test_reacao_nao_reinicia_o_bot(sent, traces):
    """O sintoma relatado pelo cliente: reagir à confirmação reexibia o menu."""
    db, cid, session = make_db(state="MENU_PRINCIPAL", customer_id=uuid.uuid4())

    drive(db, upsert(REACTION, msg_id="MSG-REACAO"))

    assert sent == [], "reação não pode gerar NENHUMA resposta"
    assert session.state == "MENU_PRINCIPAL", "estado não pode mudar"


def test_reacao_nao_tem_efeito_colateral_na_sessao(sent, traces):
    """Ignorar é ANTES do lock: não consome last_message_id nem renova TTL.

    Se consumisse, a mensagem seguinte poderia parecer duplicata.
    """
    db, cid, session = make_db(customer_id=uuid.uuid4(), last_message_id="ANTERIOR")

    drive(db, upsert(REACTION, msg_id="MSG-REACAO"))

    assert session.last_message_id == "ANTERIOR"
    assert session.expires_at is None
    assert db.commits == 0


def test_reacao_ignorada_em_qualquer_estado(sent, traces):
    """Decidido: ignorar SEMPRE. Reagir 👍 a "qual horário?" não confirma nada."""
    for state in ("INICIO", "MENU_PRINCIPAL", "AWAITING_TIME", "CONFIRMANDO", "HUMANO"):
        db, cid, session = make_db(state=state, customer_id=uuid.uuid4())
        drive(db, upsert(REACTION))
        assert session.state == state, f"estado {state} foi alterado por uma reação"
    assert sent == []


# ══ Requisito 4 — a reação é registrada ══════════════════════════════════════

def test_reacao_entra_na_telemetria_com_o_emoji(sent, traces):
    db, cid, session = make_db(customer_id=uuid.uuid4())

    drive(db, upsert(REACTION, msg_id="MSG-REACAO"))

    assert len(traces.rows) == 1
    row = traces.rows[0]
    assert row.outcome == trace.OUTCOME_REACTION
    assert row.message_type == "reactionMessage"
    assert row.dispatch["handler"] == "ignored_reaction"
    # O emoji é guardado para que a decisão de ignorar possa ser revista com dados.
    assert row.dispatch["detail"]["emoji"] == "👍"
    assert row.dispatch["detail"]["target_message_id"] == "MSG-CONFIRMACAO"


# ══ Requisito 1 — nada regride ═══════════════════════════════════════════════

def test_mensagem_normal_continua_sendo_processada(sent, traces):
    db, cid, session = make_db(state="MENU_PRINCIPAL")

    drive(db, upsert({"conversation": "1"}, msg_id="MSG-NORMAL"))

    assert sent, "mensagem normal deve continuar produzindo resposta"
    assert session.last_message_id == "MSG-NORMAL"
    assert session.expires_at is not None


def test_bot_funciona_identicamente_com_telemetria_desligada(sent, monkeypatch, traces):
    """BOT_TRACE_ENABLED=false é kill-switch: processamento byte-idêntico."""
    monkeypatch.setattr(settings, "BOT_TRACE_ENABLED", False)
    db, cid, session = make_db(state="MENU_PRINCIPAL")

    drive(db, upsert({"conversation": "1"}, msg_id="MSG-OFF"))

    assert sent, "o bot deve responder normalmente com a telemetria desligada"
    assert traces.rows == [], "nada pode ser gravado com o kill-switch acionado"


# ══ Requisito 2 — trajetória completa, com os campos de cada etapa ═══════════

def test_trace_registra_a_trajetoria_completa(sent, traces):
    db, cid, session = make_db(state="MENU_PRINCIPAL")

    drive(db, upsert({"conversation": "1"}, msg_id="MSG-TRAJ"))

    row = traces.rows[0]
    # webhook
    assert row.event == "messages.upsert"
    assert row.instance_name == INSTANCE
    assert row.message_id == "MSG-TRAJ"
    assert row.message_type == "conversation"
    assert row.received_at is not None and row.duration_ms is not None
    # contexto
    assert row.company_id == cid
    assert row.session_id == session.id
    assert row.fsm_state == "MENU_PRINCIPAL"     # estado NA CHEGADA
    assert row.fsm_state_after is not None       # estado ao final
    assert row.user_input == "1"
    # dispatcher
    assert row.dispatch["handler"] == "menu_principal.handle"
    assert "menu_principal.handle" in row.dispatch["path"]
    # saída
    assert row.outbound and row.outbound[0]["text"]
    assert row.outcome == trace.OUTCOME_PROCESSED


def test_trace_registra_as_camadas_do_classificador(sent, traces, monkeypatch):
    """Distingue "o regex não casou" de "casou e o handler não soube tratar"."""
    db, cid, session = make_db(state="MENU_PRINCIPAL", customer_id=uuid.uuid4())

    drive(db, upsert({"conversation": "quero marcar um corte"}, msg_id="MSG-CLS"))

    clf = traces.rows[0].classifier
    assert "regex" in clf
    assert clf["regex"]["intent"] and "matched" in clf["regex"]
    assert clf["regex"]["active_intents"] is not None
    assert clf["final"]["source"] in ("REGEX", "LLM", "FALLBACK")
    assert clf["final"]["threshold"] is not None
    # routing_decision espelhada da telemetria do F5a
    assert clf["routing"]["decision"] in (
        "ROUTED", "MENU_FALLBACK", "SHADOW_NOT_ROUTED", "INACTIVE_MODULE_MSG",
    )


def test_trace_registra_por_que_o_classificador_nao_rodou(sent, traces):
    """"bot mostrou o menu" ≠ "o classificador nem foi chamado"."""
    db, cid, session = make_db(state="MENU_PRINCIPAL")   # sem customer_id

    drive(db, upsert({"conversation": "quero marcar"}, msg_id="MSG-SKIP"))

    detail = traces.rows[0].dispatch.get("detail", {})
    assert detail.get("reason") == "no_customer_id"
    assert "classifier_skipped" in traces.rows[0].dispatch["path"]


def test_trace_registra_eventos_descartados_antes_do_tenant(sent, traces):
    """Instância desconhecida hoje some sem rastro — é o que se quer enxergar."""
    db = FakeDB()

    drive(db, upsert({"conversation": "oi"}, msg_id="MSG-ORFA"))

    row = traces.rows[0]
    assert row.outcome == trace.OUTCOME_UNKNOWN_INSTANCE
    assert row.company_id is None       # NULLABLE existe para este caso


def test_trace_registra_duplicata_e_grupo(sent, traces):
    db, cid, session = make_db(last_message_id="MSG-DUP")
    drive(db, upsert({"conversation": "oi"}, msg_id="MSG-DUP"))
    assert traces.rows[0].outcome == trace.OUTCOME_DUPLICATE

    grupo = upsert({"conversation": "oi"}, msg_id="MSG-G")
    grupo["data"]["key"]["remoteJid"] = "123-456@g.us"
    drive(db, grupo)
    assert traces.rows[1].outcome == trace.OUTCOME_GROUP


# ══ Privacidade ══════════════════════════════════════════════════════════════

def test_telefone_nunca_e_gravado_em_claro(sent, traces):
    db, cid, session = make_db()

    drive(db, upsert({"conversation": "oi"}, msg_id="MSG-PII"))

    row = traces.rows[0]
    blob = repr(row.webhook) + repr(row.whatsapp_masked) + repr(row.whatsapp_hash)
    assert "5511987654321" not in blob
    assert row.whatsapp_masked == "5511*******21@s.whatsapp.net"
    assert row.whatsapp_hash and len(row.whatsapp_hash) == 24


def test_pushname_e_blobs_sao_podados_do_payload(sent, traces):
    db, cid, session = make_db()
    payload = upsert({"conversation": "oi"}, msg_id="MSG-BLOB", push_name="Maria Silva")
    payload["data"]["message"]["imageMessage"] = {
        "jpegThumbnail": "A" * 5000, "mimetype": "image/jpeg",
    }

    drive(db, payload)

    blob = repr(traces.rows[0].webhook)
    assert "Maria Silva" not in blob
    assert "AAAA" not in blob
    # A ESTRUTURA sobrevive à poda — é ela que responde "como este tipo chega"
    assert "imageMessage" in blob and "mimetype" in blob


def test_hash_agrupa_o_mesmo_interlocutor():
    assert trace.hash_jid(JID) == trace.hash_jid(JID)
    assert trace.hash_jid(JID) != trace.hash_jid("5511900000000@s.whatsapp.net")


# ══ Requisito 5 — o instrumento NUNCA derruba o instrumentado ════════════════

def test_falha_ao_gravar_o_trace_nao_derruba_o_bot(sent, traces):
    """O mais importante do sprint."""
    traces.raise_on_commit = True
    db, cid, session = make_db(state="MENU_PRINCIPAL")

    resp = drive(db, upsert({"conversation": "1"}, msg_id="MSG-FAIL"))

    assert resp == {"status": "ok"}
    assert sent, "o cliente deve receber a resposta mesmo com a telemetria quebrada"
    assert session.last_message_id == "MSG-FAIL"


def test_sessao_de_telemetria_indisponivel_nao_derruba_o_bot(sent, monkeypatch):
    """Nem sequer abrir a sessão de gravação — o bot segue."""
    def _explode():
        raise RuntimeError("pool esgotado")
    monkeypatch.setattr(db_session_mod, "SessionLocal", _explode)
    db, cid, session = make_db(state="MENU_PRINCIPAL")

    resp = drive(db, upsert({"conversation": "1"}, msg_id="MSG-NOSESS"))

    assert resp == {"status": "ok"}
    assert sent


@pytest.mark.parametrize("call", [
    lambda: trace.note_envelope(message_id="m", message_type="t", whatsapp_id=JID),
    lambda: trace.note_context(company_id=uuid.uuid4(), fsm_state="X", user_input="oi"),
    lambda: trace.note_regex("AGENDAR", 0.9, ["AGENDAR"]),
    lambda: trace.note_llm("AGENDAR", 0.8, latency_ms=12, source="LLM"),
    lambda: trace.note_classification(SimpleNamespace(intent="AGENDAR", confidence=0.9,
                                                      source="REGEX", entities={})),
    lambda: trace.note_routing("ROUTED", True),
    lambda: trace.note_dispatch("h", k="v"),
    lambda: trace.note_outbound("text", "oi"),
    lambda: trace.note_state_after("X"),
    lambda: trace.set_outcome(trace.OUTCOME_PROCESSED),
    lambda: trace.finish(),
])
def test_funcoes_de_trace_nunca_levantam_sem_contexto(call):
    """Chamadas fora de um request (workers, testes, código futuro) são no-op.

    Sem isto, instrumentar um caminho que roda fora do webhook derrubaria esse
    caminho — exatamente o que o instrumento não pode fazer.
    """
    assert trace.current() is None
    call()   # não pode levantar nem gravar


def test_payload_maluco_nao_derruba_a_gravacao(traces):
    """`sanitize` enfrenta o payload cru da Evolution, que não é contrato nosso."""
    class Hostil:
        def __repr__(self):
            raise RuntimeError("nem repr")

    trace.start("messages.upsert", INSTANCE, {"a": Hostil(), "b": [Hostil()] * 100})
    trace.set_outcome(trace.OUTCOME_PROCESSED)
    trace.finish()   # não pode levantar

    assert len(traces.rows) == 1


def test_sanitize_limita_profundidade_e_tamanho():
    fundo = {"n": 0}
    cur = fundo
    for i in range(20):
        cur["filho"] = {"n": i}
        cur = cur["filho"]
    assert "<depth>" in repr(trace.sanitize(fundo))
    assert trace.sanitize("x" * 5000).startswith("<str len=5000")
    assert "<+" in repr(trace.sanitize(list(range(200))))


# ══ Retenção ═════════════════════════════════════════════════════════════════

def test_expurgo_usa_a_retencao_configurada(monkeypatch):
    """O expurgo não depende do beat nem do worker — roda no próprio processo."""
    captured = {}

    class _DB:
        def execute(self, stmt, params):
            captured["sql"] = str(stmt)
            captured["cutoff"] = params["cutoff"]
            return SimpleNamespace(rowcount=3)

        def commit(self):
            pass

        def rollback(self):
            pass

    monkeypatch.setattr(trace, "_write_count", trace._PURGE_EVERY - 1)
    monkeypatch.setattr(trace, "_last_purge_at", 0.0)
    monkeypatch.setattr(settings, "BOT_TRACE_RETENTION_DAYS", 30)

    trace._maybe_purge(_DB())

    assert "DELETE FROM bot_message_traces" in captured["sql"]
    idade = datetime.now(timezone.utc) - captured["cutoff"]
    assert 29 <= idade.days <= 30
