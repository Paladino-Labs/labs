"""Telemetria ponta a ponta do bot — S-bot-1.

Registra a TRAJETÓRIA de cada mensagem que entra pelo webhook da Evolution:
webhook → classificador → dispatcher → saída. Uma linha por evento inbound em
`bot_message_traces`.

Por que existe
--------------
Hoje só se vê "cliente disse X, bot respondeu menu". Isso não distingue três
falhas diferentes com três correções diferentes: o regex não casou, casou
errado, ou casou certo e o handler não soube tratar. A trajetória distingue.

⚠️ Instrumento DESCARTÁVEL. O pipeline vai ser redesenhado; isto existe para
que o redesenho seja feito com dados, não com intuição. Não construa em cima.

Três decisões que sustentam o resto
-----------------------------------
1. **ContextVar, não parâmetro.** O trace não viaja pela assinatura de nenhuma
   função. Instrumentar não é refatorar — passar um objeto por ~40 handlers
   mudaria estrutura, que é exatamente o que este sprint não pode fazer. O
   webhook é sequencial por request; o ContextVar acompanha isso por construção.

2. **Sessão de banco PRÓPRIA.** A gravação usa `SessionLocal()` novo, nunca a
   sessão do bot. Se o bot levantar e sofrer rollback, o trace daquela falha —
   justamente o mais interessante — sobrevive. E um erro na gravação do trace
   nunca contamina a transação do agendamento.

3. **Toda função pública é best-effort.** Nenhuma levanta. Instrumento que
   quebra o instrumentado é pior que nenhum instrumento.

Retenção: `BOT_TRACE_RETENTION_DAYS` (30). O expurgo NÃO depende do beat (que
não existe em produção) nem do worker Celery (fazer o webhook depender dele foi
o incidente de 22/07): roda oportunisticamente, no próprio processo, a cada
`_PURGE_EVERY` gravações e no máximo uma vez por hora por processo.
"""
import hashlib
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Desfechos do trace (coluna `outcome`) ────────────────────────────────────
# O que aconteceu com a mensagem — a primeira coisa que se olha na análise.
OUTCOME_PROCESSED         = "PROCESSED"           # chegou ao dispatcher
OUTCOME_REACTION          = "IGNORED_REACTION"    # reação a emoji (S-bot-1 parte 2)
OUTCOME_DUPLICATE         = "IGNORED_DUPLICATE"   # re-entrega da Evolution
OUTCOME_FROM_ME           = "IGNORED_FROM_ME"     # eco da própria instância
OUTCOME_GROUP             = "IGNORED_GROUP"       # mensagem de grupo
OUTCOME_NO_JID            = "IGNORED_NO_JID"      # payload sem remoteJid
OUTCOME_EMPTY_BATCH       = "IGNORED_EMPTY_BATCH"
OUTCOME_UNKNOWN_INSTANCE  = "IGNORED_UNKNOWN_INSTANCE"
OUTCOME_BOT_DISABLED      = "IGNORED_BOT_DISABLED"
OUTCOME_NO_SETTINGS       = "IGNORED_NO_SETTINGS"
OUTCOME_SESSION_LOCKED    = "IGNORED_SESSION_LOCKED"
OUTCOME_EVENT_IGNORED     = "IGNORED_EVENT"       # evento fora dos 4 tratados
OUTCOME_INVALID_JSON      = "IGNORED_INVALID_JSON"
OUTCOME_UNAUTHORIZED      = "REJECTED_UNAUTHORIZED"
OUTCOME_ERROR             = "ERROR"               # exceção no processamento

# ─── Privacidade — ver a análise no relatório do sprint ───────────────────────
# Chaves do payload cru que NUNCA são gravadas: identificam a pessoa ou o
# aparelho sem acrescentar nada ao diagnóstico do pipeline.
_DROP_KEYS = frozenset({
    "pushname", "profilepicurl", "verifiedname", "vname",
    "jpegthumbnail", "thumbnail", "thumbnailurl", "base64", "media", "buffer",
    "mediakey", "mediakeytimestamp", "fileencsha256", "filesha256", "filelength",
    "streamingsidecar", "url", "directpath",
    "devicelistmetadata", "messagesecret", "contextinfo",
})
# Acima deste tamanho, o valor é substituído por um marcador com o comprimento:
# preserva "havia um blob aqui, deste tamanho" sem copiar o blob.
_MAX_STR = 400
_MAX_DEPTH = 6
_MAX_ITEMS = 40
# Teto do texto do usuário guardado em `user_input`.
_MAX_INPUT = 1000

_JID_SUFFIXES = ("@s.whatsapp.net", "@lid", "@g.us", "@c.us", "@broadcast")


def mask_jid(jid: Optional[str]) -> str:
    """Mascara o miolo do número, preservando DDI+DDD e os 2 últimos dígitos.

    "5511987654321@s.whatsapp.net" → "5511*******21@s.whatsapp.net"
    O suficiente para reconhecer o mesmo interlocutor de olho numa listagem,
    sem gravar mais uma cópia legível do telefone do cliente final.
    """
    if not jid:
        return ""
    raw = str(jid)
    suffix = ""
    for s in _JID_SUFFIXES:
        if raw.endswith(s):
            raw, suffix = raw[: -len(s)], s
            break
    head = raw.split(":")[0]
    if len(head) <= 6:
        return "*" * len(head) + suffix
    return f"{head[:4]}{'*' * (len(head) - 6)}{head[-2:]}{suffix}"


def hash_jid(jid: Optional[str]) -> str:
    """Pseudônimo estável para AGRUPAR os eventos de um mesmo interlocutor.

    Agrupar por `whatsapp_masked` seria ambíguo; agrupar por telefone exigiria
    gravá-lo. O hash resolve os dois — e não reidentifica ninguém sozinho.
    """
    if not jid:
        return ""
    return hashlib.sha256(str(jid).encode("utf-8")).hexdigest()[:24]


def sanitize(value: Any, _depth: int = 0) -> Any:
    """Poda o payload cru: remove PII e blobs, preserva a ESTRUTURA.

    A estrutura é o que responde "como este tipo de evento chega de fato" —
    que é a pergunta do parser de reações e de qualquer tipo ainda não tratado.
    """
    if _depth > _MAX_DEPTH:
        return "<depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > _MAX_STR:
            return f"<str len={len(value)}>"
        for s in _JID_SUFFIXES:
            if value.endswith(s):
                return mask_jid(value)
        return value
    if isinstance(value, list):
        out = [sanitize(v, _depth + 1) for v in value[:_MAX_ITEMS]]
        if len(value) > _MAX_ITEMS:
            out.append(f"<+{len(value) - _MAX_ITEMS} itens>")
        return out
    if isinstance(value, dict):
        out: dict = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= _MAX_ITEMS:
                out["<truncado>"] = True
                break
            if str(k).lower() in _DROP_KEYS:
                out[str(k)] = "<removido>"
                continue
            out[str(k)] = sanitize(v, _depth + 1)
        return out
    return f"<{type(value).__name__}>"


# ─── O trace ──────────────────────────────────────────────────────────────────

class MessageTrace:
    """Acumulador da trajetória de UMA mensagem. Sem lógica de negócio."""

    __slots__ = (
        "id", "started_at", "t0", "event", "instance_name", "payload",
        "company_id", "session_id", "whatsapp_id", "message_id", "message_type",
        "fsm_state", "fsm_state_after", "user_input", "outcome",
        "classifier", "dispatch", "outbound",
    )

    def __init__(self, event: str, instance_name: str, payload: Any):
        self.id = uuid.uuid4()
        self.started_at = datetime.now(timezone.utc)
        self.t0 = time.monotonic()
        self.event = (event or "")[:40]
        self.instance_name = (instance_name or "")[:200]
        self.payload = payload
        self.company_id = None
        self.session_id = None
        self.whatsapp_id = None
        self.message_id = None
        self.message_type = None
        self.fsm_state = None
        self.fsm_state_after = None
        self.user_input = None
        self.outcome = None
        self.classifier: dict = {}
        self.dispatch: dict = {}
        self.outbound: list = []


_current: ContextVar[Optional[MessageTrace]] = ContextVar("bot_message_trace", default=None)


def current() -> Optional[MessageTrace]:
    return _current.get()


def _safe(fn):
    """Nenhuma função de telemetria levanta. Ponto."""
    def _wrapper(*args, **kwargs):
        if not settings.BOT_TRACE_ENABLED:
            return None
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception("bot trace: %s falhou", fn.__name__)
            return None
    _wrapper.__name__ = fn.__name__
    return _wrapper


@_safe
def start(event: str, instance_name: str, payload: Any) -> None:
    """Abre o trace no webhook, antes de qualquer decisão."""
    _current.set(MessageTrace(event, instance_name, payload))


@_safe
def note_envelope(
    *, message_id=None, message_type=None, whatsapp_id=None, payload=None,
) -> None:
    """Identificação do evento — o que chegou, de quem, de que tipo."""
    t = current()
    if t is None:
        return
    if message_id is not None:
        t.message_id = str(message_id)[:255]
    if message_type is not None:
        t.message_type = str(message_type)[:60]
    if whatsapp_id is not None:
        t.whatsapp_id = str(whatsapp_id)
    if payload is not None:
        t.payload = payload


@_safe
def note_context(*, company_id=None, session_id=None, fsm_state=None, user_input=None) -> None:
    """Contexto resolvido: tenant, sessão, estado da FSM NA CHEGADA."""
    t = current()
    if t is None:
        return
    if company_id is not None:
        t.company_id = company_id
    if session_id is not None:
        t.session_id = session_id
    if fsm_state is not None:
        t.fsm_state = str(fsm_state)[:40]
    if user_input is not None:
        t.user_input = str(user_input)[:_MAX_INPUT]


@_safe
def note_regex(intent: str, confidence: float, active_intents=None) -> None:
    """Camada 1: o regex casou ou passou direto? Com que confiança?

    Confiança 0.0 com intent de fallback = NENHUM padrão casou — este é o
    "o que impediu" no caso mais comum.
    """
    t = current()
    if t is None:
        return
    t.classifier["regex"] = {
        "intent": intent,
        "confidence": float(confidence),
        "matched": float(confidence) > 0.0,
        "active_intents": list(active_intents) if active_intents is not None else None,
    }


@_safe
def note_llm(intent: str, confidence: float, latency_ms=None, source=None) -> None:
    """Camada 2: só é consultada quando o regex fica abaixo do threshold."""
    t = current()
    if t is None:
        return
    t.classifier["llm"] = {
        "intent": intent,
        "confidence": float(confidence),
        "latency_ms": latency_ms,
        "source": source,
    }


@_safe
def note_classification(result, threshold=None) -> None:
    """Resultado final do ChainClassifier, com o id da linha em
    intent_classifications — a costura entre esta telemetria e a do F5a."""
    t = current()
    if t is None:
        return
    cid = getattr(result, "classification_id", None)
    t.classifier["final"] = {
        "intent": getattr(result, "intent", None),
        "confidence": float(getattr(result, "confidence", 0.0) or 0.0),
        "source": getattr(result, "source", None),
        "entities": getattr(result, "entities", None) or {},
        "classification_id": str(cid) if cid else None,
        "threshold": threshold,
    }


@_safe
def note_routing(decision: str, routed: bool, reason: str = None) -> None:
    """A decisão de roteamento: ROUTED | MENU_FALLBACK | SHADOW_NOT_ROUTED |
    INACTIVE_MODULE_MSG (mesmos valores de intent/telemetry.py)."""
    t = current()
    if t is None:
        return
    t.classifier["routing"] = {"decision": decision, "routed": bool(routed), "reason": reason}


@_safe
def note_dispatch(handler: str, **detail) -> None:
    """Para qual handler o dispatcher roteou. `handler` é o nome do branch —
    o "fallback / menu genérico" aparece como o handler que o produziu."""
    t = current()
    if t is None:
        return
    # `path` preserva a ORDEM das decisões (ex.: classificador pulado → handler
    # do estado); `handler` é a última — a que efetivamente respondeu.
    path = t.dispatch.setdefault("path", [])
    if len(path) < 8:
        path.append(handler)
    t.dispatch["handler"] = handler
    if detail:
        t.dispatch.setdefault("detail", {}).update(
            {k: (str(v)[:200] if v is not None else None) for k, v in detail.items()}
        )


@_safe
def note_state_after(state) -> None:
    t = current()
    if t is None:
        return
    t.fsm_state_after = str(state)[:40] if state is not None else None


@_safe
def note_outbound(kind: str, text: str, ok: bool = True) -> None:
    """O que o bot respondeu. Também é o sinal de abandono: a última resposta
    antes de o cliente parar de responder."""
    t = current()
    if t is None or len(t.outbound) >= 12:
        return
    t.outbound.append({
        "kind": kind,
        "text": (text or "")[:_MAX_STR],
        "ok": bool(ok),
    })


@_safe
def set_outcome(outcome: str) -> None:
    t = current()
    if t is None:
        return
    t.outcome = outcome


# ─── Gravação ─────────────────────────────────────────────────────────────────

_write_count = 0
_last_purge_at = 0.0
_PURGE_EVERY = 50
_PURGE_MIN_INTERVAL_S = 3600


@_safe
def finish() -> None:
    """Persiste o trace e fecha o contexto. Chamado no `finally` do webhook."""
    t = current()
    _current.set(None)
    if t is None:
        return

    from app.infrastructure.db.models.bot_message_trace import BotMessageTrace
    from app.infrastructure.db.session import SessionLocal

    row = BotMessageTrace(
        id=t.id,
        company_id=t.company_id,
        received_at=t.started_at,
        instance_name=t.instance_name,
        event=t.event,
        whatsapp_hash=hash_jid(t.whatsapp_id),
        whatsapp_masked=mask_jid(t.whatsapp_id)[:60],
        message_id=t.message_id,
        message_type=t.message_type,
        session_id=t.session_id,
        fsm_state=t.fsm_state,
        fsm_state_after=t.fsm_state_after,
        outcome=t.outcome or OUTCOME_PROCESSED,
        user_input=t.user_input,
        webhook=sanitize(t.payload),
        classifier=t.classifier or {},
        dispatch=t.dispatch or {},
        outbound=t.outbound or [],
        duration_ms=int((time.monotonic() - t.t0) * 1000),
    )

    # Sessão própria: o trace de uma falha precisa sobreviver ao rollback dela.
    db = SessionLocal()
    try:
        db.add(row)
        db.commit()
        _maybe_purge(db)
    except Exception:
        logger.exception("bot trace: gravação falhou trace_id=%s", t.id)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def _maybe_purge(db) -> None:
    """Expurgo oportunista da retenção — sem beat, sem worker, sem cron.

    A cada `_PURGE_EVERY` gravações e no máximo 1×/hora por processo. Com 1–4
    sessões por dia o volume é irrisório; o índice em received_at torna o DELETE
    barato. Falha é logada e ignorada.
    """
    global _write_count, _last_purge_at
    _write_count += 1
    now = time.monotonic()
    if _write_count % _PURGE_EVERY != 0 or (now - _last_purge_at) < _PURGE_MIN_INTERVAL_S:
        return
    _last_purge_at = now
    try:
        from sqlalchemy import text as _text
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.BOT_TRACE_RETENTION_DAYS)
        res = db.execute(
            _text("DELETE FROM bot_message_traces WHERE received_at < :cutoff"),
            {"cutoff": cutoff},
        )
        db.commit()
        logger.info("bot trace: expurgo removeu %s linhas anteriores a %s",
                    getattr(res, "rowcount", "?"), cutoff.isoformat())
    except Exception:
        logger.exception("bot trace: expurgo falhou")
        try:
            db.rollback()
        except Exception:
            pass
