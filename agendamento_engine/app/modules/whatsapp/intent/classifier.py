"""ChainClassifier — orquestra regex -> LLM -> fallback (decisão D8).

Invariantes do Sprint 2.0:
  1. FSM soberano — este módulo NUNCA transiciona estado, apenas classifica.
  2. IA nunca gera resposta livre — LLMClassifier retorna só JSON estruturado.
  3. Toda classificação é persistida em intent_classifications (append-only,
     sem dedup — cada chamada gera uma linha).
  5. Catálogo dinâmico por tenant via ModuleActivation (catalog.get_active_intents).

F5a: a linha persistida carrega fsm_state (estado no momento da classificação)
e devolve classification_id no IntentResult — routing_decision e desfecho são
gravados depois pelo chamador (telemetry.py).
"""
import logging
import time
import uuid
from decimal import Decimal

from app.infrastructure.db.models.intent_classification import IntentClassification
from app.infrastructure.db.models.module_activation import ModuleActivation
from app.modules.whatsapp.intent.catalog import ALL_INTENTS, get_active_intents
from app.modules.whatsapp.intent.llm_classifier import LLMClassifier
from app.modules.whatsapp.intent.regex_classifier import RegexClassifier
from app.modules.whatsapp.intent.schemas import (
    CONFIDENCE_THRESHOLD,
    FALLBACK_INTENT,
    IntentResult,
)

logger = logging.getLogger(__name__)


class ChainClassifier:
    """Classifica mensagens: regex primeiro, LLM apenas em baixa confiança."""

    def __init__(self, db, regex_classifier=None, llm_classifier=None):
        self.db = db
        self.regex = regex_classifier or RegexClassifier()
        self.llm = llm_classifier or LLMClassifier()

    @property
    def known_intents(self) -> list[str]:
        return ALL_INTENTS

    def classify(
        self,
        company_id,
        text: str,
        session_id=None,
        module_activations=None,
        fsm_state=None,
    ) -> IntentResult:
        if module_activations is None:
            module_activations = (
                self.db.query(ModuleActivation)
                .filter(ModuleActivation.company_id == company_id)
                .all()
            )
        active_intents = get_active_intents(module_activations)

        result = self.regex.classify(text, active_intents)

        llm_latency_ms = None
        if result.confidence < CONFIDENCE_THRESHOLD:
            start = time.monotonic()
            result = self.llm.classify(text, active_intents)
            llm_latency_ms = int((time.monotonic() - start) * 1000)

        if result.intent != FALLBACK_INTENT and result.intent not in active_intents:
            logger.info(
                "ChainClassifier: intent %s fora do catálogo ativo — convertendo para %s",
                result.intent, FALLBACK_INTENT,
            )
            result = IntentResult(
                intent=FALLBACK_INTENT, confidence=0.0, source="FALLBACK",
                entities=result.entities, raw_input=text,
            )

        result.classification_id = self._persist(
            company_id, session_id, result, llm_latency_ms, fsm_state,
        )
        return result

    def _persist(
        self, company_id, session_id, result: IntentResult, llm_latency_ms, fsm_state=None,
    ):
        llm_provider = None
        llm_model = None
        if llm_latency_ms is not None:
            llm_provider = getattr(self.llm, "provider", None)
            llm_model = getattr(self.llm, "model", None)

        record = IntentClassification(
            id=uuid.uuid4(),
            company_id=company_id,
            session_id=session_id,
            raw_input=result.raw_input,
            classified_intent=result.intent,
            confidence=Decimal(str(result.confidence)),
            source=result.source,
            entities=result.entities,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_latency_ms=llm_latency_ms,
            fsm_state=fsm_state,
        )
        self.db.add(record)
        self.db.commit()
        return record.id
