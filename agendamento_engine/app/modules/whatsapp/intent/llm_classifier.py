"""Classificador via LLM — segunda camada do ChainClassifier (D8).

Só é chamado quando o RegexClassifier retorna confidence < CONFIDENCE_THRESHOLD.
Invariante 2 do canal: a IA classifica, nunca gera resposta — saída é SEMPRE
JSON estruturado via tool use forçado (tool_choice), nunca texto livre.
Qualquer falha (timeout, erro de API, sem API key) degrada para
IntentResult(FALLBACK_INTENT, confidence=0.0, source="FALLBACK").

Provider: Anthropic Claude Haiku 4.5 (claude-haiku-4-5) — menor custo/latência
da família Claude, adequado para classificação de texto curto (ver commit de
documentação da decisão).
"""
import logging
import os

import anthropic

from app.core.config import settings
from app.modules.whatsapp.intent.catalog import ALL_INTENTS
from app.modules.whatsapp.intent.schemas import FALLBACK_INTENT, IntentResult

logger = logging.getLogger(__name__)

_CLASSIFY_TOOL = {
    "name": "classify_intent",
    "description": (
        "Classifica a intenção de uma mensagem de cliente de WhatsApp em "
        "uma das intenções disponíveis para este tenant."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": ALL_INTENTS},
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Confiança na classificação, de 0 a 1.",
            },
            "entities": {
                "type": "object",
                "description": "Entidades extraídas da mensagem (ex: serviço, data).",
            },
        },
        "required": ["intent", "confidence"],
    },
}

_SYSTEM_PROMPT = (
    "Você classifica mensagens de clientes de um salão/clínica em uma das "
    "intenções disponíveis. Responda SEMPRE chamando a ferramenta "
    "classify_intent — nunca em texto livre."
)


class LLMClassifier:
    """Segunda camada do ChainClassifier — chamada apenas em baixa confiança."""

    def __init__(self) -> None:
        self.provider = settings.LLM_PROVIDER
        self.model = settings.LLM_MODEL
        self.api_key = settings.LLM_API_KEY
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    def classify(self, text: str, active_intents: list[str]) -> IntentResult:
        if not self.api_key:
            logger.warning(
                "LLMClassifier: LLM_API_KEY ausente — fallback para %s",
                FALLBACK_INTENT,
            )
            return IntentResult(
                intent=FALLBACK_INTENT, confidence=0.0, source="FALLBACK", raw_input=text,
            )

        client = anthropic.Anthropic(api_key=self.api_key).with_options(timeout=self.timeout)

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=256,
                system=_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Intenções disponíveis: {', '.join(active_intents)}.\n"
                        f"Mensagem do cliente: {text}"
                    ),
                }],
                tools=[_CLASSIFY_TOOL],
                tool_choice={"type": "tool", "name": "classify_intent"},
            )
        except anthropic.AnthropicError:
            logger.exception(
                "LLMClassifier: falha ao chamar %s/%s — fallback para %s",
                self.provider, self.model, FALLBACK_INTENT,
            )
            return IntentResult(
                intent=FALLBACK_INTENT, confidence=0.0, source="FALLBACK", raw_input=text,
            )

        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_use is None:
            logger.error(
                "LLMClassifier: resposta de %s/%s sem tool_use — fallback para %s",
                self.provider, self.model, FALLBACK_INTENT,
            )
            return IntentResult(
                intent=FALLBACK_INTENT, confidence=0.0, source="FALLBACK", raw_input=text,
            )

        data = tool_use.input
        intent = data.get("intent", FALLBACK_INTENT)
        confidence = float(data.get("confidence", 0.0))
        entities = data.get("entities") or {}

        if intent not in active_intents:
            intent, confidence = FALLBACK_INTENT, 0.0

        return IntentResult(
            intent=intent, confidence=confidence, entities=entities,
            source="LLM", raw_input=text,
        )


class NullLLMClassifier:
    """Test double do LLMClassifier — nunca chama API externa.

    Resultado controlado por NULL_LLM_OUTCOME (env var, padrão self.outcome):
      fallback          -> IntentResult(MENU_PRINCIPAL, confidence=0.0, source="FALLBACK")
      agendar           -> IntentResult(AGENDAR, confidence=0.95, source="LLM")
      falar_com_humano  -> IntentResult(FALAR_COM_HUMANO, confidence=0.95, source="LLM")
    """

    provider = "null"
    model = "null"

    def __init__(self, outcome: str = "fallback") -> None:
        self.outcome = outcome
        self.calls: list[dict] = []

    def classify(self, text: str, active_intents: list[str]) -> IntentResult:
        outcome = os.getenv("NULL_LLM_OUTCOME", self.outcome)
        self.calls.append({
            "text": text, "active_intents": list(active_intents), "outcome": outcome,
        })

        if outcome == "agendar":
            intent, confidence, source = "AGENDAR", 0.95, "LLM"
        elif outcome == "falar_com_humano":
            intent, confidence, source = "FALAR_COM_HUMANO", 0.95, "LLM"
        else:
            intent, confidence, source = FALLBACK_INTENT, 0.0, "FALLBACK"

        if intent not in active_intents:
            intent, confidence, source = FALLBACK_INTENT, 0.0, "FALLBACK"

        return IntentResult(intent=intent, confidence=confidence, source=source, raw_input=text)
