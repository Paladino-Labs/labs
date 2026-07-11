"""Contrato de retorno do IntentClassifier (Sprint 2.0).

IntentResult é o ÚNICO formato de saída do classificador — a IA classifica,
nunca gera resposta (invariante 2 do canal).
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntentResult:
    intent: str
    confidence: float       # 0.0 a 1.0
    entities: dict[str, Any] = field(default_factory=dict)
    source: str = "REGEX"   # REGEX | LLM | FALLBACK
    raw_input: str = ""
    # Preenchido pelo ChainClassifier após persistir (F5a) — permite ao
    # chamador correlacionar roteamento e desfecho à linha gravada.
    classification_id: Any = None


# Intent de degradação: LLM indisponível ou intent fora do catálogo do tenant
FALLBACK_INTENT = "MENU_PRINCIPAL"

# Abaixo deste valor o resultado do regex não é confiável → tenta LLM
CONFIDENCE_THRESHOLD = 0.7
