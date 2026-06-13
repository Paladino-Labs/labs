"""
Testes Sprint 2.0 — IntentClassifier isolado (decisão D8: regex -> LLM fallback).

Componente ISOLADO: nenhum teste aqui toca bot_service.py ou
whatsapp/handlers/ (integração é Sprint 2.6).

Usa FakeDB in-memory (padrão do projeto) — sem PostgreSQL real.

Casos obrigatórios:
  1. IntentResult tem o formato esperado (intent, confidence, entities,
     source, raw_input)
  2. Regex com confiança alta NÃO chama o LLM
  3. Regex com confiança baixa aciona o LLM
  4. LLM indisponível/fallback degrada para MENU_PRINCIPAL
  5. Intent fora do catálogo ativo do tenant é convertido para MENU_PRINCIPAL
  6. get_active_intents respeita ModuleActivation por tenant
  7. Toda classificação é persistida em intent_classifications
  8. FALAR_COM_HUMANO está sempre ativo, mesmo sem nenhum módulo
  9. Classificação é auditável — sem dedup (2 chamadas = 2 linhas)
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.infrastructure.db.models.intent_classification import IntentClassification
from app.modules.whatsapp.intent.catalog import get_active_intents
from app.modules.whatsapp.intent.classifier import ChainClassifier
from app.modules.whatsapp.intent.llm_classifier import NullLLMClassifier
from app.modules.whatsapp.intent.regex_classifier import RegexClassifier
from app.modules.whatsapp.intent.schemas import FALLBACK_INTENT, IntentResult


# ─── FakeDB ───────────────────────────────────────────────────────────────────

class FakeDB:
    def __init__(self, all_=None):
        self._all = dict(all_ or {})
        self.added = []
        self.commits = 0

    def query(self, model, *rest):
        db = self

        class Q:
            def filter(self, *a, **k): return self
            def order_by(self, *a, **k): return self

            def all(self_q):
                return db._all.get(model, [])

        return Q()

    def add(self, obj): self.added.append(obj)
    def commit(self): self.commits += 1


class _StubClassifier:
    """Retorna sempre o mesmo IntentResult, sem filtrar por active_intents.

    Usado para testar a camada de filtragem do ChainClassifier de forma
    isolada, sem depender do filtro interno do RegexClassifier/LLMClassifier.
    """

    provider = "stub"
    model = "stub"

    def __init__(self, intent: str, confidence: float, source: str = "REGEX"):
        self._result = IntentResult(intent=intent, confidence=confidence, source=source)

    def classify(self, text, active_intents):
        result = self._result
        return IntentResult(
            intent=result.intent, confidence=result.confidence,
            entities=result.entities, source=result.source, raw_input=text,
        )


# ─── 1. IntentResult shape ────────────────────────────────────────────────────

def test_intent_result_shape():
    result = IntentResult(intent="AGENDAR", confidence=0.9)
    assert result.intent == "AGENDAR"
    assert result.confidence == 0.9
    assert result.entities == {}
    assert result.source == "REGEX"
    assert result.raw_input == ""


# ─── 2. Regex confiante não chama LLM ─────────────────────────────────────────

def test_regex_high_confidence_does_not_call_llm():
    db = FakeDB()
    null_llm = NullLLMClassifier(outcome="agendar")
    chain = ChainClassifier(db, regex_classifier=RegexClassifier(), llm_classifier=null_llm)

    result = chain.classify(
        company_id=uuid.uuid4(),
        text="quero cancelar meu agendamento",
        module_activations=[],
    )

    assert result.intent == "CANCELAR"
    assert result.source == "REGEX"
    assert null_llm.calls == []


# ─── 3. Baixa confiança aciona o LLM ──────────────────────────────────────────

def test_low_confidence_triggers_llm():
    db = FakeDB()
    null_llm = NullLLMClassifier(outcome="agendar")
    chain = ChainClassifier(db, regex_classifier=RegexClassifier(), llm_classifier=null_llm)

    result = chain.classify(
        company_id=uuid.uuid4(),
        text="oi, bom dia",
        module_activations=[],
    )

    assert len(null_llm.calls) == 1
    assert result.intent == "AGENDAR"
    assert result.source == "LLM"


# ─── 4. LLM indisponível degrada para MENU_PRINCIPAL ─────────────────────────

def test_llm_unavailable_falls_back_to_menu():
    db = FakeDB()
    null_llm = NullLLMClassifier(outcome="fallback")
    chain = ChainClassifier(db, regex_classifier=RegexClassifier(), llm_classifier=null_llm)

    result = chain.classify(
        company_id=uuid.uuid4(),
        text="oi, bom dia",
        module_activations=[],
    )

    assert result.intent == FALLBACK_INTENT
    assert result.source == "FALLBACK"
    assert result.confidence == 0.0


# ─── 5. Intent fora do catálogo ativo -> MENU_PRINCIPAL ──────────────────────

def test_inactive_module_intent_converted_to_menu():
    db = FakeDB()
    stub = _StubClassifier(intent="COMPRAR_PACOTE", confidence=0.9, source="REGEX")
    chain = ChainClassifier(db, regex_classifier=stub, llm_classifier=NullLLMClassifier())

    # PACOTES não está ativo (module_activations=[]) -> COMPRAR_PACOTE não está
    # no catálogo ativo, mesmo com confiança alta do classificador stub.
    result = chain.classify(
        company_id=uuid.uuid4(),
        text="quero comprar um pacote",
        module_activations=[],
    )

    assert result.intent == FALLBACK_INTENT
    assert result.source == "FALLBACK"


# ─── 6. get_active_intents respeita ModuleActivation ─────────────────────────

def test_active_intents_respect_module_activation():
    no_modules = get_active_intents([])
    assert "COMPRAR_PRODUTO" not in no_modules
    assert "COMPRAR_PACOTE" not in no_modules
    assert "AGENDAR" in no_modules

    activations = [
        SimpleNamespace(module_name="ESTOQUE", is_active=True),
        SimpleNamespace(module_name="PACOTES", is_active=False),
    ]
    with_estoque = get_active_intents(activations)
    assert "COMPRAR_PRODUTO" in with_estoque
    assert "COMPRAR_PACOTE" not in with_estoque


# ─── 7. Classificação persistida em intent_classifications ──────────────────

def test_classification_persisted_in_db():
    db = FakeDB()
    chain = ChainClassifier(db, regex_classifier=RegexClassifier(), llm_classifier=NullLLMClassifier())
    company_id = uuid.uuid4()

    result = chain.classify(
        company_id=company_id,
        text="quero cancelar meu agendamento",
        module_activations=[],
    )

    assert db.commits == 1
    assert len(db.added) == 1
    record = db.added[0]
    assert isinstance(record, IntentClassification)
    assert record.company_id == company_id
    assert record.raw_input == "quero cancelar meu agendamento"
    assert record.classified_intent == result.intent == "CANCELAR"
    assert record.confidence == Decimal("0.9")
    assert record.source == "REGEX"
    assert record.llm_provider is None
    assert record.llm_model is None
    assert record.llm_latency_ms is None


# ─── 8. FALAR_COM_HUMANO sempre ativo ────────────────────────────────────────

def test_falar_com_humano_always_active():
    assert "FALAR_COM_HUMANO" in get_active_intents([])
    assert "FALAR_COM_HUMANO" in get_active_intents(
        [SimpleNamespace(module_name="ESTOQUE", is_active=False)]
    )


# ─── 9. Classificação auditável — sem dedup ──────────────────────────────────

def test_classification_is_auditable_no_dedup():
    db = FakeDB()
    chain = ChainClassifier(db, regex_classifier=RegexClassifier(), llm_classifier=NullLLMClassifier())
    company_id = uuid.uuid4()

    chain.classify(company_id=company_id, text="quero cancelar meu agendamento", module_activations=[])
    chain.classify(company_id=company_id, text="quero cancelar meu agendamento", module_activations=[])

    assert db.commits == 2
    assert len(db.added) == 2
    assert db.added[0] is not db.added[1]
    assert all(r.classified_intent == "CANCELAR" for r in db.added)
