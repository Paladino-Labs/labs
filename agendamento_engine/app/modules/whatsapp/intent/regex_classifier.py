"""Classificador baseado em regex — primeira camada do ChainClassifier (D8).

Rápido, sem custo, sem dependência externa. Cobre os padrões de mensagem
mais comuns; casos ambíguos ficam com confidence < CONFIDENCE_THRESHOLD e
são escalados para o LLMClassifier pelo ChainClassifier.

Ordem de avaliação importa: intenções mais específicas (CANCELAR, REMARCAR)
são checadas antes de intenções mais genéricas (AGENDAR) para evitar que
"quero cancelar meu agendamento" caia em AGENDAR por conter "agendamento".
"""
import re

from app.modules.whatsapp.intent.schemas import FALLBACK_INTENT, IntentResult

# Ordem de avaliação — específico antes de genérico
_INTENT_ORDER = [
    "CANCELAR",
    "REMARCAR",
    "CONSULTAR",
    "COMPRAR_PRODUTO",
    "COMPRAR_PACOTE",
    "FALAR_COM_HUMANO",
    "AGENDAR",
]

# Cada intenção tem padrões "specific" (confidence 0.9) e "generic" (0.75)
PATTERNS: dict[str, dict[str, list[str]]] = {
    "CANCELAR": {
        "specific": [
            r"\bcancelar?\s+(o\s+|meu\s+|minha\s+)?(agendamento|hor[áa]rio|consulta|reserva)",
            r"\bquero\s+cancelar\b",
            r"\bn[ãa]o\s+(vou|posso)\s+(ir|comparecer)\b",
            r"\bdesmarcar\b",
        ],
        "generic": [
            r"\bcancela(r)?\b",
        ],
    },
    "REMARCAR": {
        "specific": [
            r"\bremarcar?\s+(o\s+|meu\s+|minha\s+)?(agendamento|hor[áa]rio|consulta)",
            r"\bquero\s+remarcar\b",
            r"\b(mudar|trocar|alterar)\s+(o\s+|meu\s+|minha\s+)?(hor[áa]rio|data|agendamento)\b",
        ],
        "generic": [
            r"\bremarcar\b",
            r"\boutro\s+hor[áa]rio\b",
        ],
    },
    "CONSULTAR": {
        "specific": [
            r"\b(quais?|que)\s+(s[ãa]o\s+)?(os\s+)?(meus\s+)?(agendamentos|hor[áa]rios)\b",
            r"\bquando\s+[ée]\s+(meu|o)\s+(agendamento|hor[áa]rio|consulta)\b",
            r"\bver\s+(meus\s+)?agendamentos\b",
            r"\bconsultar\s+(meu\s+|minha\s+)?(agendamento|hor[áa]rio)\b",
        ],
        "generic": [
            r"\bconsultar\b",
            r"\bmeus\s+agendamentos\b",
        ],
    },
    "COMPRAR_PRODUTO": {
        "specific": [
            r"\bcomprar\s+(um\s+|uma\s+)?produto\b",
            r"\bquero\s+comprar\b",
            r"\b(tem|t[êe]m|vende[m]?)\s+.*\b(produto|shampoo|creme|loção|cosm[ée]tico)\b",
        ],
        "generic": [
            r"\bproduto[s]?\b",
            r"\bcomprar\b",
        ],
    },
    "COMPRAR_PACOTE": {
        "specific": [
            r"\bcomprar\s+(um\s+|o\s+)?pacote\b",
            r"\bquero\s+(um\s+|o\s+)?pacote\b",
            r"\bplano\s+de\s+(sess[õo]es|servi[çc]os)\b",
        ],
        "generic": [
            r"\bpacote[s]?\b",
        ],
    },
    "FALAR_COM_HUMANO": {
        "specific": [
            r"\bfalar\s+com\s+(um\s+)?(atendente|humano|pessoa|funcion[áa]rio)\b",
            r"\bquero\s+(falar|ser\s+atendido)\s+com\s+(algu[ée]m|atendente|humano)\b",
            r"\batendimento\s+humano\b",
        ],
        "generic": [
            r"\batendente\b",
            r"\bhumano\b",
        ],
    },
    "AGENDAR": {
        "specific": [
            r"\b(quero|gostaria\s+de)\s+(agendar|marcar)\b",
            r"\bagendar\s+(um\s+|uma\s+)?(hor[áa]rio|consulta|servi[çc]o|atendimento)\b",
            r"\bmarcar\s+(um\s+|uma\s+)?(hor[áa]rio|consulta|servi[çc]o)\b",
        ],
        "generic": [
            r"\bagendar\b",
            r"\bagendamento\b",
            r"\bmarcar\b",
        ],
    },
}


class RegexClassifier:
    """Classifica mensagens por padrões de regex (D8 — primeira camada)."""

    def classify(self, text: str, active_intents: list[str]) -> IntentResult:
        normalized = (text or "").strip().lower()

        for intent in _INTENT_ORDER:
            if intent not in active_intents:
                continue

            patterns = PATTERNS.get(intent, {})
            for pattern in patterns.get("specific", []):
                if re.search(pattern, normalized):
                    return IntentResult(
                        intent=intent,
                        confidence=0.9,
                        source="REGEX",
                        raw_input=text,
                    )

        for intent in _INTENT_ORDER:
            if intent not in active_intents:
                continue

            patterns = PATTERNS.get(intent, {})
            for pattern in patterns.get("generic", []):
                if re.search(pattern, normalized):
                    return IntentResult(
                        intent=intent,
                        confidence=0.75,
                        source="REGEX",
                        raw_input=text,
                    )

        return IntentResult(
            intent=FALLBACK_INTENT,
            confidence=0.0,
            source="REGEX",
            raw_input=text,
        )
