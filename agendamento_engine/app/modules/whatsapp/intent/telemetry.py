"""Telemetria do volante de intenção — Bot F5a.

Grava (1) a decisão de roteamento na própria classificação e (2) o DESFECHO
em intent_outcomes (tabela-irmã 1:1 — preserva o append-only de
intent_classifications entre requests).

Correlação classificação→desfecho:
  session_id NÃO delimita conversa — a linha de bot_sessions é reutilizada
  entre conversas do mesmo whatsapp_id. Por isso a correlação NUNCA consulta
  "última classificação da session": o id da classificação viaja no
  session.context (marker MARKER_KEY), que morre junto com a conversa
  (reset_session/expiração limpa o context) e é substituído — com desfecho
  ABANDONED — a cada nova classificação. CORRELATION_WINDOW_MINUTES é a defesa
  extra contra sessões longas com TTL renovado: marker mais velho que a janela
  é descartado SEM gravar (telemetria ambígua → não adivinhar; classificação
  sem linha em intent_outcomes = PENDING).

Todas as funções são best-effort: telemetria nunca derruba o bot.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.infrastructure.db.models.intent_classification import (
    IntentClassification,
    IntentOutcome,
)

logger = logging.getLogger(__name__)

# Chave do marker de correlação em BotSession.context
MARKER_KEY = "intent_track"

# Alinhado ao BOT_SESSION_TTL_MINUTES: desfecho além disso é ambíguo demais
CORRELATION_WINDOW_MINUTES = 30

# ── routing_decision (intent_classifications) ─────────────────────────────────
ROUTING_ROUTED = "ROUTED"                        # intent roteou o usuário
ROUTING_MENU = "MENU_FALLBACK"                   # fallback/baixa confiança → menu
ROUTING_SHADOW = "SHADOW_NOT_ROUTED"             # LLM >= threshold contida (shadow)
ROUTING_INACTIVE_MODULE = "INACTIVE_MODULE_MSG"  # RECURSO_INDISPONIVEL enviado

# ── outcome (intent_outcomes) ─────────────────────────────────────────────────
OUTCOME_MENU_CLICK_AFTER_FALLBACK = "MENU_CLICK_AFTER_FALLBACK"
OUTCOME_FLOW_CONFIRMED = "FLOW_CONFIRMED"
OUTCOME_FLOW_CANCELLED = "FLOW_CANCELLED"
OUTCOME_ABANDONED = "ABANDONED"
# PENDING não é gravado: classificação sem linha em intent_outcomes = pendente.

# Valores de track em record_routing
TRACK_FALLBACK = "fallback"   # menu exibido — próximo clique é ground truth (3a)
TRACK_ROUTED = "routed"       # fluxo iniciado — desfecho vem da confirmação (3b)


def record_routing(db, session, company_id, result, decision, track=None) -> None:
    """Grava routing_decision na classificação e arma o marker de correlação.

    track=None não arma correlação (ex.: INACTIVE_MODULE — a resposta já foi
    dada). Um marker anterior ainda pendente é fechado como ABANDONED
    (superseded) antes de ser substituído.
    """
    try:
        cid = getattr(result, "classification_id", None)
        if cid is None:
            return

        row = (
            db.query(IntentClassification)
            .filter(IntentClassification.id == cid)
            .first()
        )
        if row is not None:
            row.routing_decision = decision

        if track is None:
            return

        ctx = dict(session.context or {})
        _abandon(db, company_id, ctx.pop(MARKER_KEY, None), reason="superseded")
        ctx[MARKER_KEY] = {
            "cid": str(cid),
            "intent": result.intent,
            "routed": track == TRACK_ROUTED,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        session.context = ctx
    except Exception:
        logger.exception("intent telemetry: record_routing falhou")


def consume_menu_click(db, session, company_id, option_payload) -> None:
    """Write-back 3a: clique de menu após fallback/shadow = rótulo real da intenção."""
    try:
        marker = (session.context or {}).get(MARKER_KEY)
        if not marker or marker.get("routed"):
            return
        _pop_marker(session)
        if _stale(marker):
            return
        _insert_outcome(
            db, company_id, marker.get("cid"),
            OUTCOME_MENU_CLICK_AFTER_FALLBACK,
            {"menu_option": option_payload, "suggested_intent": marker.get("intent")},
        )
    except Exception:
        logger.exception("intent telemetry: consume_menu_click falhou")


def record_flow_outcome(db, session, company_id, intents, outcome, detail=None) -> None:
    """Write-back 3b: desfecho de fluxo iniciado por classificação roteada.

    Consome o marker apenas se a intenção que iniciou o fluxo casa com o ponto
    de materialização (intents) — marker de outra intenção fica intacto
    (não adivinhar).
    """
    try:
        marker = (session.context or {}).get(MARKER_KEY)
        if not marker or not marker.get("routed"):
            return
        if marker.get("intent") not in intents:
            return
        _pop_marker(session)
        if _stale(marker):
            return
        _insert_outcome(db, company_id, marker.get("cid"), outcome, detail or {})
    except Exception:
        logger.exception("intent telemetry: record_flow_outcome falhou")


# ─── internos ─────────────────────────────────────────────────────────────────

def _abandon(db, company_id, marker, reason: str) -> None:
    """Fecha um marker pendente como ABANDONED (nunca sobrescreve desfecho)."""
    if not marker:
        return
    _insert_outcome(
        db, company_id, marker.get("cid"), OUTCOME_ABANDONED, {"reason": reason},
    )


def _pop_marker(session) -> None:
    ctx = dict(session.context or {})
    ctx.pop(MARKER_KEY, None)
    session.context = ctx


def _stale(marker) -> bool:
    try:
        at = datetime.fromisoformat(marker["at"])
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - at > timedelta(
            minutes=CORRELATION_WINDOW_MINUTES
        )
    except Exception:
        return True   # marker malformado → descarta sem gravar


def _insert_outcome(db, company_id, classification_id, outcome, detail) -> None:
    try:
        cid = uuid.UUID(str(classification_id))
    except (ValueError, TypeError, AttributeError):
        return
    try:
        existing = (
            db.query(IntentOutcome)
            .filter(IntentOutcome.classification_id == cid)
            .first()
        )
        if existing is not None:
            return   # 1 desfecho por classificação (UNIQUE) — primeiro vence
        db.add(IntentOutcome(
            id=uuid.uuid4(),
            company_id=company_id,
            classification_id=cid,
            outcome=outcome,
            outcome_detail=detail,
        ))
        db.flush()
    except Exception:
        logger.exception("intent telemetry: insert de outcome falhou cid=%s", cid)
