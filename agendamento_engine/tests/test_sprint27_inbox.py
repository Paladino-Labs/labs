"""Testes Sprint 2.7 — Inbox de atendimento humano + estado RESOLVIDA.

Cobre:
  - Persistência de mensagens INBOUND em state=HUMANO (bot silencia)
  - conversation.escalated publicado na transição para HUMANO
  - reply: envia via sender + persiste OUTBOUND/AGENT; 422 em RESOLVIDA
  - resolve: state != HUMANO (RESOLVIDA) + bot reassume em MENU_PRINCIPAL
  - get_conversation_messages em ordem crescente
  - Isolamento cross-tenant (404) e filtro por company_id

Estratégia: FakeDB in-memory que avalia filtros reais (padrão Sprint D),
serviços/sender monkeypatched. Os fluxos de dispatcher exercitam
handle_inbound_message de forma assíncrona com FakeDB.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.infrastructure.db.models import (
    BotSession,
    CompanySettings,
    ConversationMessage,
    Customer,
    WhatsAppConnection,
)
from app.modules.conversations import service as conv_service
from app.modules.whatsapp import bot_service, sender
import app.infrastructure.event_bus as event_bus_mod


# ─── FakeDB com avaliação real de filtros (padrão Sprint D) ───────────────────

def _criterion_matches(obj, c) -> bool:
    key = c.left.key
    actual = getattr(obj, key, None)
    right = c.right
    op_name = getattr(c.operator, "__name__", "")

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

    def with_for_update(self, *a, **k):
        return self

    def order_by(self, *args, **k):
        items = list(self.items)
        for arg in reversed(args):
            element = getattr(arg, "element", arg)
            key = getattr(element, "key", None)
            modifier = getattr(arg, "modifier", None)
            descending = "desc" in getattr(modifier, "__name__", "")
            if key:
                items.sort(key=lambda o: getattr(o, key, None), reverse=descending)
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

    def query(self, model, *rest):
        return FakeQuery(self._store(model))

    def add(self, obj):
        if getattr(obj, "id", None) is None and hasattr(obj, "id"):
            obj.id = uuid.uuid4()
        if isinstance(obj, ConversationMessage) and obj.created_at is None:
            obj.created_at = datetime.now(timezone.utc)
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


# ─── Builders ─────────────────────────────────────────────────────────────────

def _make_session(db, company_id, state="HUMANO", customer_id=None, customer_name="Maria",
                  phone="5511999999999@s.whatsapp.net"):
    ctx = {"customer_name": customer_name}
    if customer_id:
        ctx["customer_id"] = str(customer_id)
    session = BotSession(
        id=uuid.uuid4(), company_id=company_id, whatsapp_id=phone,
        state=state, context=ctx,
    )
    session.updated_at = datetime.now(timezone.utc)
    db._store(BotSession).append(session)
    return session


def _make_conn(db, company_id, instance="paladino-test"):
    conn = WhatsAppConnection(id=uuid.uuid4(), company_id=company_id, instance_name=instance)
    db._store(WhatsAppConnection).append(conn)
    return conn


def _make_message(db, session, created_at, direction="INBOUND", content="oi",
                  sender_type="CLIENT"):
    msg = ConversationMessage(
        id=uuid.uuid4(), company_id=session.company_id, session_id=session.id,
        direction=direction, content=content, content_type="TEXT",
        sender_type=sender_type, created_at=created_at,
    )
    db._store(ConversationMessage).append(msg)
    return msg


@pytest.fixture(autouse=True)
def _silence_sender(monkeypatch):
    sent = []
    monkeypatch.setattr(sender, "send_text", lambda inst, to, text: sent.append((inst, to, text)))
    monkeypatch.setattr(sender, "send_buttons", lambda *a, **k: sent.append(("buttons", a)))
    monkeypatch.setattr(sender, "send_list", lambda *a, **k: sent.append(("list", a)))
    return sent


@pytest.fixture
def captured_events(monkeypatch):
    events = []
    monkeypatch.setattr(event_bus_mod.event_bus, "publish", lambda e: events.append(e))
    return events


# ─── reply / resolve (service) ────────────────────────────────────────────────

def test_reply_sends_and_persists_outbound_agent(_silence_sender):
    db = FakeDB()
    cid = uuid.uuid4()
    session = _make_session(db, cid, state="HUMANO")
    _make_conn(db, cid, instance="inst-x")
    agent = uuid.uuid4()

    msg = conv_service.reply_to_conversation(
        db, session.id, cid, agent_user_id=agent, content="Olá, posso ajudar?",
    )

    assert msg.direction == "OUTBOUND"
    assert msg.sender_type == "AGENT"
    assert msg.agent_user_id == agent
    # Enviado ao número do cliente via instância do tenant
    assert ("inst-x", session.whatsapp_id, "Olá, posso ajudar?") in _silence_sender


def test_reply_on_resolved_returns_422(_silence_sender):
    db = FakeDB()
    cid = uuid.uuid4()
    session = _make_session(db, cid, state="RESOLVIDA")
    _make_conn(db, cid)

    with pytest.raises(Exception) as exc:
        conv_service.reply_to_conversation(
            db, session.id, cid, agent_user_id=uuid.uuid4(), content="oi",
        )
    assert getattr(exc.value, "status_code", None) == 422


def test_resolve_sets_resolvida_and_reassumes(_silence_sender, captured_events):
    db = FakeDB()
    cid = uuid.uuid4()
    session = _make_session(db, cid, state="HUMANO")
    _make_conn(db, cid)

    result = conv_service.resolve_conversation(
        db, session.id, cid, agent_user_id=uuid.uuid4(),
    )

    assert result.state == "RESOLVIDA"
    assert result.state != "HUMANO"
    # Mensagem de sistema persistida + enviada ao cliente
    msgs = db._store(ConversationMessage)
    assert any(m.content == bot_service.messages.ATENDIMENTO_ENCERRADO for m in msgs)
    assert any("conversation.resolved" == e.event_type for e in captured_events)


def test_resolve_on_non_humano_returns_422(_silence_sender):
    db = FakeDB()
    cid = uuid.uuid4()
    session = _make_session(db, cid, state="MENU_PRINCIPAL")

    with pytest.raises(Exception) as exc:
        conv_service.resolve_conversation(db, session.id, cid, agent_user_id=uuid.uuid4())
    assert getattr(exc.value, "status_code", None) == 422


# ─── get_conversation_messages ────────────────────────────────────────────────

def test_get_messages_ascending_order(_silence_sender):
    db = FakeDB()
    cid = uuid.uuid4()
    session = _make_session(db, cid, state="HUMANO")
    now = datetime.now(timezone.utc)
    _make_message(db, session, now, content="terceira")
    _make_message(db, session, now - timedelta(minutes=2), content="primeira")
    _make_message(db, session, now - timedelta(minutes=1), content="segunda")

    result = conv_service.get_conversation_messages(db, session.id, cid)
    assert [m.content for m in result] == ["primeira", "segunda", "terceira"]


# ─── Isolamento cross-tenant ──────────────────────────────────────────────────

def test_cross_tenant_messages_404(_silence_sender):
    db = FakeDB()
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    session = _make_session(db, company_a, state="HUMANO")

    with pytest.raises(Exception) as exc:
        conv_service.get_conversation_messages(db, session.id, company_b)
    assert getattr(exc.value, "status_code", None) == 404


def test_cross_tenant_reply_404(_silence_sender):
    db = FakeDB()
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    session = _make_session(db, company_a, state="HUMANO")
    _make_conn(db, company_a)

    with pytest.raises(Exception) as exc:
        conv_service.reply_to_conversation(
            db, session.id, company_b, agent_user_id=uuid.uuid4(), content="x",
        )
    assert getattr(exc.value, "status_code", None) == 404


def test_list_filters_by_company(_silence_sender):
    db = FakeDB()
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    _make_session(db, company_a, state="HUMANO", phone="a@s.whatsapp.net")
    _make_session(db, company_b, state="HUMANO", phone="b@s.whatsapp.net")

    result = conv_service.list_escalated_conversations(db, company_a)
    assert len(result) == 1
    assert result[0]["phone"] == "a@s.whatsapp.net"


def test_list_resolved_status(_silence_sender):
    db = FakeDB()
    cid = uuid.uuid4()
    _make_session(db, cid, state="HUMANO", phone="hum@x")
    _make_session(db, cid, state="RESOLVIDA", phone="res@x")

    escalated = conv_service.list_escalated_conversations(db, cid, status="escalated")
    resolved = conv_service.list_escalated_conversations(db, cid, status="resolved")

    assert [c["phone"] for c in escalated] == ["hum@x"]
    assert [c["phone"] for c in resolved] == ["res@x"]


# ─── Escalada (bot_service) ───────────────────────────────────────────────────

def test_escalate_to_human_publishes_and_persists(_silence_sender, captured_events):
    db = FakeDB()
    cid = uuid.uuid4()
    customer_id = uuid.uuid4()
    session = _make_session(db, cid, state="MENU_PRINCIPAL", customer_id=customer_id)

    bot_service._escalate_to_human(
        db, session, cid, "inst-x", session.whatsapp_id,
        text="quero falar com alguém", trigger="INTENT",
    )

    assert session.state == "HUMANO"
    # HUMANO_CHAMADO enviado ao cliente
    assert any(t[2] == bot_service.messages.HUMANO_CHAMADO for t in _silence_sender
               if isinstance(t, tuple) and len(t) == 3)
    # INBOUND (gatilho) + OUTBOUND (chamado) persistidos
    msgs = db._store(ConversationMessage)
    assert any(m.direction == "INBOUND" and m.sender_type == "CLIENT" for m in msgs)
    assert any(m.direction == "OUTBOUND" and m.sender_type == "BOT" for m in msgs)
    # conversation.escalated publicado com payload correto
    escalated = [e for e in captured_events if e.event_type == "conversation.escalated"]
    assert len(escalated) == 1
    assert escalated[0].payload["customer_id"] == str(customer_id)
    assert escalated[0].payload["trigger"] == "INTENT"


# ─── Dispatcher: silêncio em HUMANO, reassume em RESOLVIDA ─────────────────────

def _inbound_data(text, msg_id="MSG1"):
    return {
        "key": {"id": msg_id, "fromMe": False, "remoteJid": "5511999999999@s.whatsapp.net"},
        "message": {"conversation": text},
    }


def _drive_inbound(db, company_id, session, text, msg_id="MSG1"):
    _make_conn(db, company_id, instance="inst-x")
    db._store(CompanySettings).append(
        SimpleNamespace(company_id=company_id, bot_enabled=True)
    )
    db._store(bot_service.Company).append(
        SimpleNamespace(id=company_id, name="Barbearia", timezone="America/Sao_Paulo")
    )
    asyncio.run(
        bot_service.handle_inbound_message(db, "inst-x", _inbound_data(text, msg_id))
    )


def test_humano_persists_inbound_and_silences(_silence_sender):
    db = FakeDB()
    cid = uuid.uuid4()
    session = _make_session(db, cid, state="HUMANO")

    _drive_inbound(db, cid, session, "ainda preciso de ajuda", msg_id="M-HUM")

    msgs = db._store(ConversationMessage)
    inbound = [m for m in msgs if m.direction == "INBOUND"]
    assert len(inbound) == 1
    assert inbound[0].sender_type == "CLIENT"
    assert inbound[0].whatsapp_message_id == "M-HUM"
    # Bot silencia — nenhum envio ao cliente
    assert _silence_sender == []


def test_resolvida_reassumes_menu(_silence_sender):
    db = FakeDB()
    cid = uuid.uuid4()
    session = _make_session(db, cid, state="RESOLVIDA")

    _drive_inbound(db, cid, session, "oi de novo", msg_id="M-RES")

    # Bot reassume — responde (não silencia) e sai de RESOLVIDA
    assert session.state == "MENU_PRINCIPAL"
    assert _silence_sender != []
