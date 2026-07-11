"""Testes Sprint 2.6 — ChainClassifier integrado ao FSM + intenções de compra.

Invariantes verificados:
  1. FSM soberano — o classificador SUGERE, o FSM DECIDE. FALLBACK não transiciona.
  2. LLMClassifier nunca retorna texto livre (coberto no Sprint 2.0; aqui usamos
     NullLLMClassifier como fallback determinístico).
  4. FALAR_COM_HUMANO acessível por texto livre de qualquer estado de entrada.

Estratégia: testa `_classify_and_route` (roteamento) e os handlers de compra
(progressão de estados) de forma isolada — FakeDB in-memory + serviços
monkeypatched. Não exercita o webhook async nem o Postgres real.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.whatsapp import bot_service
from app.modules.whatsapp import sender
from app.modules.whatsapp.handlers import comprando_produto as h_produto
from app.modules.whatsapp.handlers import comprando_pacote as h_pacote
from app.modules.whatsapp.helpers import is_universal_command, resolve_input
from app.modules.whatsapp.intent.classifier import ChainClassifier
from app.modules.whatsapp.intent.llm_classifier import NullLLMClassifier
from app.modules.whatsapp.intent.regex_classifier import RegexClassifier
from app.modules.whatsapp.intent.schemas import FALLBACK_INTENT, IntentResult


# ─── Fakes ────────────────────────────────────────────────────────────────────

class FakeDB:
    def __init__(self, results=None):
        self._results = dict(results or {})
        self.added = []
        self.commits = 0

    def query(self, model, *rest):
        db = self

        class Q:
            def filter(self, *a, **k): return self
            def order_by(self, *a, **k): return self
            def all(self_q): return db._results.get(model, [])
            def first(self_q):
                rows = db._results.get(model, [])
                return rows[0] if rows else None

        return Q()

    def add(self, obj): self.added.append(obj)
    def flush(self): pass
    def commit(self): self.commits += 1
    def refresh(self, obj): pass


def fake_session(state="MENU_PRINCIPAL", **ctx):
    base = {"customer_id": str(uuid.uuid4()), "customer_name": "Maria"}
    base.update(ctx)
    return SimpleNamespace(id=uuid.uuid4(), state=state, context=base)


class StubClassifier:
    """Retorna um IntentResult fixo — controla a sugestão sem LLM/persistência."""

    def __init__(self, intent, confidence, source="REGEX"):
        self._intent = intent
        self._confidence = confidence
        self._source = source

    def classify(self, company_id, text, session_id=None, module_activations=None,
                 fsm_state=None):
        return IntentResult(
            intent=self._intent, confidence=self._confidence,
            source=self._source, raw_input=text,
        )


@pytest.fixture
def captured(monkeypatch):
    """Captura todos os envios do bot."""
    sent = []
    monkeypatch.setattr(sender, "send_text",
                        lambda inst, to, text: sent.append(("text", text)))
    monkeypatch.setattr(sender, "send_buttons",
                        lambda inst, to, text, buttons: sent.append(("buttons", text)))
    monkeypatch.setattr(sender, "send_list",
                        lambda inst, to, title, desc, rows, *a, **k: sent.append(("list", title)))
    return sent


def _route(session, db, text, classifier, company_name="Barbearia"):
    return bot_service._classify_and_route(
        db, session, uuid.uuid4(), "inst", "5511999@s.whatsapp.net",
        text, company_name, classifier=classifier,
    )


# ─── 1. AGENDAR (classificador real) → ESCOLHENDO_SERVICO ────────────────────

def test_agendar_real_chain_routes_to_escolhendo_servico(captured, monkeypatch):
    calls = []
    monkeypatch.setattr(bot_service, "_start_escolhendo_servico",
                        lambda *a, **k: calls.append("servico"))

    db = FakeDB()  # ModuleActivation → [] (AGENDAR sempre ativo)
    chain = ChainClassifier(db, regex_classifier=RegexClassifier(),
                            llm_classifier=NullLLMClassifier())
    session = fake_session(state="INICIO")

    routed = _route(session, db, "quero marcar um corte", classifier=chain)

    assert routed is True
    assert session.state == bot_service.STATE_ESCOLHENDO_SERVICO
    assert calls == ["servico"]


# ─── 2. "cancelar" → CANCELANDO (auto-seleção de 1 agendamento) ──────────────

def test_cancelar_single_appointment_routes_to_cancelando(captured, monkeypatch):
    from app.modules.booking.engine import booking_engine
    appt_id = uuid.uuid4()
    monkeypatch.setattr(booking_engine, "get_customer_appointments",
                        lambda db, cid, custid: [SimpleNamespace(id=appt_id)])
    calls = []
    monkeypatch.setattr(bot_service, "_start_cancelando",
                        lambda *a, **k: calls.append("cancelando"))

    db = FakeDB()
    session = fake_session(state="MENU_PRINCIPAL")
    routed = _route(session, db, "cancelar", StubClassifier("CANCELAR", 0.75))

    assert routed is True
    assert session.state == bot_service.STATE_CANCELANDO
    assert session.context["managing_appointment_id"] == str(appt_id)
    assert calls == ["cancelando"]


def test_cancelar_word_is_not_universal_menu():
    # Sprint 2.6: "cancelar" deixou de ser atalho de menu (agora é CANCELAR).
    assert is_universal_command("cancelar") is None
    assert is_universal_command("menu") == "menu"
    assert is_universal_command("sair") == "menu"


# ─── 3. "quero falar com alguém" → HUMANO (invariante 4) ─────────────────────

def test_falar_com_humano_routes_to_humano(captured, monkeypatch):
    # F5a: resultado de source=LLM só roteia em LLM_MODE="live" (shadow é o
    # default e contém a LLM). O invariante 4 via REGEX/comando universal
    # continua valendo em qualquer modo.
    monkeypatch.setattr(bot_service.settings, "LLM_MODE", "live")
    db = FakeDB()
    session = fake_session(state="MENU_PRINCIPAL")
    routed = _route(session, db, "quero falar com alguém",
                    StubClassifier("FALAR_COM_HUMANO", 0.95, source="LLM"))

    assert routed is True
    assert session.state == bot_service.STATE_HUMANO
    assert any(kind == "text" for kind, _ in captured)


# ─── 4/5. Módulo inativo → indisponibilidade (não entra no fluxo de compra) ──

def test_pacote_module_inactive_returns_unavailable(captured):
    db = FakeDB()  # ModuleActivation → [] (PACOTES inativo)
    session = fake_session(state="MENU_PRINCIPAL")
    # Classificador já converteu para FALLBACK (catálogo do tenant)
    routed = _route(session, db, "quero pacote", StubClassifier(FALLBACK_INTENT, 0.0, "FALLBACK"))

    assert routed is True
    assert session.state == "MENU_PRINCIPAL"  # NÃO entrou em ESCOLHENDO_PACOTE
    assert ("text", h_pacote.messages.RECURSO_INDISPONIVEL) in captured


def test_produto_module_inactive_returns_unavailable(captured):
    db = FakeDB()  # ESTOQUE inativo
    session = fake_session(state="MENU_PRINCIPAL")
    routed = _route(session, db, "quero produto", StubClassifier(FALLBACK_INTENT, 0.0, "FALLBACK"))

    assert routed is True
    assert session.state != bot_service.STATE_ESCOLHENDO_PRODUTO
    assert ("text", h_produto.messages.RECURSO_INDISPONIVEL) in captured


# ─── 6. Compra de produto: fluxo completo → Payment + StockMovement VENDA ────

def test_comprar_produto_flow(captured, monkeypatch):
    company_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    product_id = uuid.uuid4()
    product = SimpleNamespace(id=product_id, name="Pomada", price=Decimal("20.00"), stock=10)

    # start → lista produtos
    monkeypatch.setattr(h_produto.stock_service, "list_stock",
                        lambda db, company_id, active_only=True: [product])

    db = FakeDB()
    session = SimpleNamespace(id=uuid.uuid4(), state="MENU_PRINCIPAL",
                              context={"customer_id": str(customer_id), "customer_name": "Ana"})

    h_produto.start(db, session, company_id, "inst", "to")
    assert session.state == h_produto.STATE_ESCOLHENDO_PRODUTO

    # escolher produto
    monkeypatch.setattr(h_produto.products_service, "get_product_or_404",
                        lambda db, cid, pid: product)
    # WhatsApp devolve o rowId selecionado ("prod_0") → resolve_input → payload
    h_produto.handle_escolhendo_produto(
        db, session, company_id, "to", "inst", "prod_0", resolve_input=resolve_input,
    )
    assert session.state == h_produto.STATE_CONFIRMANDO_QUANTIDADE_PRODUTO
    assert session.context["product_id"] == str(product_id)

    # quantidade
    h_produto.handle_confirmando_quantidade(db, session, company_id, "to", "inst", "2")
    assert session.state == h_produto.STATE_CONFIRMANDO_PRODUTO
    assert session.context["quantity"] == 2

    # confirmar → Payment + StockMovement VENDA
    payments, movements = [], []
    monkeypatch.setattr(h_produto.payment_service, "create_payment",
                        lambda **kw: payments.append(kw) or SimpleNamespace(payment_id=uuid.uuid4()))
    monkeypatch.setattr(h_produto.stock_service, "record_movement",
                        lambda **kw: movements.append(kw))
    monkeypatch.setattr(h_produto, "_allow_negative", lambda db, cid: False)
    monkeypatch.setattr(h_produto, "_resolve_owner_user_id", lambda db, cid: uuid.uuid4())

    h_produto.handle_confirmando_produto(
        db, session, company_id, "to", "inst", "opt_confirmar_produto", resolve_input=resolve_input,
    )

    assert len(payments) == 1
    assert payments[0]["gross_amount"] == Decimal("40.00")
    assert payments[0]["provider"] == "manual"
    assert len(movements) == 1
    assert movements[0]["movement_type"] == "VENDA"
    assert movements[0]["quantity"] == 2
    assert session.state == h_produto.STATE_MENU_PRINCIPAL


def test_comprar_produto_estoque_insuficiente(captured, monkeypatch):
    company_id = uuid.uuid4()
    product_id = uuid.uuid4()
    product = SimpleNamespace(id=product_id, name="Cera", price=Decimal("10.00"), stock=1)
    db = FakeDB()
    session = SimpleNamespace(
        id=uuid.uuid4(), state="CONFIRMANDO_PRODUTO",
        context={
            "customer_id": str(uuid.uuid4()), "product_id": str(product_id),
            "product_name": "Cera", "unit_price": "10.00", "quantity": 5,
            "last_list": [{"row_id": "opt_confirmar_produto", "payload": "confirmar_produto", "title": "✅"}],
        },
    )
    monkeypatch.setattr(h_produto.products_service, "get_product_or_404",
                        lambda db, cid, pid: product)
    monkeypatch.setattr(h_produto, "_allow_negative", lambda db, cid: False)
    created = []
    monkeypatch.setattr(h_produto.payment_service, "create_payment",
                        lambda **kw: created.append(kw))

    h_produto.handle_confirmando_produto(
        db, session, company_id, "to", "inst", "opt_confirmar_produto", resolve_input=resolve_input,
    )

    assert created == []  # não cobra com estoque insuficiente
    assert any(kind == "text" for kind, _ in captured)


# ─── 7. Compra de pacote: fluxo completo → PackagePurchase PENDING_PAYMENT ────

def test_comprar_pacote_flow(captured, monkeypatch):
    company_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    pkg_id = uuid.uuid4()
    pkg = SimpleNamespace(package_id=pkg_id, name="Combo 5", total_cotas=5,
                          validity_days=90, price=Decimal("150.00"), is_active=True)

    monkeypatch.setattr(h_pacote.packages_service, "list_packages",
                        lambda cid, db: [pkg])

    db = FakeDB()
    session = SimpleNamespace(id=uuid.uuid4(), state="MENU_PRINCIPAL",
                              context={"customer_id": str(customer_id), "customer_name": "Ana"})

    h_pacote.start(db, session, company_id, "inst", "to")
    assert session.state == h_pacote.STATE_ESCOLHENDO_PACOTE

    monkeypatch.setattr(h_pacote.packages_service, "_get_package_or_404",
                        lambda pid, cid, db: pkg)
    h_pacote.handle_escolhendo_pacote(
        db, session, company_id, "to", "inst", "pkg_0", resolve_input=resolve_input,
    )
    assert session.state == h_pacote.STATE_CONFIRMANDO_PACOTE

    purchases = []
    monkeypatch.setattr(h_pacote.packages_service, "purchase",
                        lambda **kw: purchases.append(kw) or SimpleNamespace(
                            purchase_id=uuid.uuid4(), status="PENDING_PAYMENT"))

    h_pacote.handle_confirmando_pacote(
        db, session, company_id, "to", "inst", "opt_confirmar_pacote", resolve_input=resolve_input,
    )

    assert len(purchases) == 1
    assert purchases[0]["package_id"] == pkg_id
    assert purchases[0]["customer_id"] == customer_id
    assert purchases[0]["seller_user_id"] is None
    assert session.state == h_pacote.STATE_MENU_PRINCIPAL


# ─── 8. Texto ambíguo (confidence < 0.7 / FALLBACK) → menu (retorna False) ───

def test_ambiguous_text_returns_false_for_menu(captured):
    db = FakeDB()
    session = fake_session(state="MENU_PRINCIPAL")
    routed = _route(session, db, "oi, tudo bem?", StubClassifier(FALLBACK_INTENT, 0.0, "FALLBACK"))

    assert routed is False  # chamador exibe o menu (comportamento atual)


# ─── 9. FSM não transiciona com FALLBACK (invariante 1) ──────────────────────

def test_fallback_does_not_transition_state(captured):
    db = FakeDB()
    session = fake_session(state="MENU_PRINCIPAL")
    before = session.state
    routed = _route(session, db, "blá blá", StubClassifier(FALLBACK_INTENT, 0.0, "FALLBACK"))

    assert routed is False
    assert session.state == before  # FSM soberano — nenhuma transição


def test_low_confidence_does_not_transition(captured):
    # Mesmo com uma intenção válida, confidence < 0.7 não roteia (invariante 1).
    db = FakeDB()
    session = fake_session(state="MENU_PRINCIPAL")
    routed = _route(session, db, "talvez agendar?", StubClassifier("AGENDAR", 0.5))

    assert routed is False
    assert session.state == "MENU_PRINCIPAL"
