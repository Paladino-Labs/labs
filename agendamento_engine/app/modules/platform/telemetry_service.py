"""Leitura das conversas do bot para rotulagem humana — S-painel-telemetria.

Transforma `bot_message_traces` (uma linha por evento do webhook) em algo que
uma pessoa consegue ler por uma hora seguida: conversas em ordem, com o
diagnóstico de cada mensagem à mão, e um rótulo gravável ao lado.

⚠️ **A conversa é agrupada por `whatsapp_hash`, não por sessão.**
`bot_sessions.id` é reutilizada entre conversas do mesmo interlocutor (aviso
registrado no F5a), então agrupar por sessão misturaria e cortaria conversas
de forma arbitrária. O hash é o pseudônimo estável da pessoa — para o uso
real (ler o que cada cliente disse ao bot) ele é o agrupamento certo.
Consequência aceita: alguém que falou com o bot na segunda e na quinta
aparece como UMA conversa. Com ~25 conversas em 4 dias isso ajuda a leitura
em vez de atrapalhar.

⚠️ **A agregação acontece em Python, não em SQL.** É deliberado: o volume é
de dezenas de conversas num instrumento descartável de 30 dias, e a definição
de "mensagem não entendida" — que é o número pelo qual o Silva escolhe o que
ler — fica num lugar só, legível, compartilhado pela lista e pelo detalhe.
`MAX_TRACES` é o teto que impede a decisão de virar dívida se o volume mudar.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Company
from app.infrastructure.db.models.bot_message_label import BotMessageLabel
from app.infrastructure.db.models.bot_message_trace import BotMessageTrace

logger = logging.getLogger(__name__)

# Teto de linhas lidas numa varredura. A coleta são ~25 conversas; isto existe
# para a escolha de agregar em Python falhar barulhenta, não silenciosamente.
MAX_TRACES = 5000

# ── Catálogo de rótulos ("o que era?") ────────────────────────────────────────
# Vive AQUI, não no banco: é exatamente o vocabulário que este trabalho vai
# redesenhar. Acrescentar um rótulo é editar esta tupla — sem migration.
EXPECTED_INTENTS = (
    "agendar", "cancelar", "remarcar", "consultar", "saudacao",
    "agradecimento", "preco", "disponibilidade", "produto", "pacote",
    "humano", "outro",
)

UNDERSTOOD_VALUES = ("YES", "NO", "WRONG")

# ── "não entendida" ───────────────────────────────────────────────────────────
# O classificador rodou e NÃO roteou o cliente: ele recebeu menu genérico.
#   MENU_FALLBACK      — nada casou (ou casou abaixo do threshold)
#   SHADOW_NOT_ROUTED  — a LLM entendeu, mas o shadow conteve o roteamento;
#                        do ponto de vista do cliente o sintoma é o mesmo menu
# INACTIVE_MODULE_MSG fica de FORA: ali o bot entendeu e respondeu que o
# recurso está desligado — é outra conversa, não falta de entendimento.
NOT_ROUTED_DECISIONS = frozenset({"MENU_FALLBACK", "SHADOW_NOT_ROUTED"})

# Tipos que `helpers.extract_user_text` sabe ler. Qualquer outro chega com
# texto vazio e reexibe o menu — a classe maior que o S-bot-1 catalogou e não
# corrigiu. Conta como não entendida: o cliente falou e o bot não ouviu.
READABLE_MESSAGE_TYPES = frozenset({
    "conversation", "extendedTextMessage",
    "listResponseMessage", "buttonsResponseMessage",
    "templateButtonReplyMessage", "interactiveResponseMessage",
})


def _jget(blob, *path):
    """Leitura defensiva de JSONB — o formato do trace é instrumento, não
    contrato: uma etapa ausente é normal, não erro."""
    cur = blob
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _is_client_message(t: BotMessageTrace) -> bool:
    """Linha que representa alguém falando com o bot.

    Eventos de conexão/QR code e lotes vazios também viram trace (é o ponto do
    S-bot-1: nada some), mas não são mensagem — não entram na contagem nem na
    transcrição.
    """
    return bool(t.whatsapp_hash) and bool(t.message_id or t.user_input or t.message_type)


def _unreadable_type(t: BotMessageTrace) -> bool:
    """Áudio, imagem, sticker, protocolMessage… — o bot recebeu e não leu."""
    if t.message_type is None:
        return False
    return t.message_type not in READABLE_MESSAGE_TYPES


def _diagnose(t: BotMessageTrace) -> dict:
    """O que aconteceu com esta mensagem — o essencial que fica INLINE.

    Três perguntas, na ordem em que o Silva as faz ao ler:
      entendeu?  ·  o quê?  ·  devolveu menu genérico?
    """
    decision = _jget(t.classifier, "routing", "decision")
    final_intent = _jget(t.classifier, "final", "intent")
    final_conf = _jget(t.classifier, "final", "confidence")
    classified = _jget(t.classifier, "final") is not None

    unreadable = _unreadable_type(t)
    not_routed = decision in NOT_ROUTED_DECISIONS

    return {
        # O indicador que faz o Silva escolher qual conversa ler.
        "not_understood": bool(unreadable or not_routed),
        # Por que não entendeu — distingue "não casou" de "não sei ler o tipo".
        "reason": (
            "UNREADABLE_TYPE" if unreadable
            else decision if not_routed
            else None
        ),
        "classified": classified,
        "intent": final_intent,
        "confidence": final_conf,
        "routing_decision": decision,
        # O sintoma que interessa, dito com todas as letras.
        "generic_menu": bool(not_routed),
    }


def _detail(t: BotMessageTrace) -> dict:
    """O diagnóstico completo — o que fica atrás do expansível.

    Tudo inline vira ruído; pouco demais não explica. Isto é o "pouco demais"
    resolvido: estado na chegada, o que o regex disse, decisão de roteamento,
    handler que respondeu, tipo da mensagem e desfecho.
    """
    return {
        "fsm_state": t.fsm_state,
        "fsm_state_after": t.fsm_state_after,
        "message_type": t.message_type,
        "outcome": t.outcome,
        "duration_ms": t.duration_ms,
        "event": t.event,
        "regex": _jget(t.classifier, "regex"),
        "llm": _jget(t.classifier, "llm"),
        "final": _jget(t.classifier, "final"),
        "routing": _jget(t.classifier, "routing"),
        "handler": _jget(t.dispatch, "handler"),
        "dispatch_path": _jget(t.dispatch, "path"),
        "dispatch_detail": _jget(t.dispatch, "detail"),
    }


def _label_row(lb: Optional[BotMessageLabel]) -> Optional[dict]:
    if lb is None:
        return None
    return {
        "understood": lb.understood,
        "expected_intent": lb.expected_intent,
        "note": lb.note,
        "updated_at": lb.updated_at.isoformat() if lb.updated_at else None,
    }


def _fetch_traces(db: Session, date_from=None, date_to=None) -> list:
    q = db.query(BotMessageTrace).filter(BotMessageTrace.whatsapp_hash.isnot(None))
    if date_from is not None:
        q = q.filter(BotMessageTrace.received_at >= date_from)
    if date_to is not None:
        q = q.filter(BotMessageTrace.received_at <= date_to)
    return q.order_by(BotMessageTrace.received_at.desc()).limit(MAX_TRACES).all()


def list_conversations(db: Session, date_from=None, date_to=None) -> list[dict]:
    """Uma linha por interlocutor: quando, quantas, quantas sem entendimento.

    Ordenada por mais recente. O único filtro é data — o painel é laboratório,
    e complexidade prematura é o que faz laboratório virar produto mal-acabado.
    """
    traces = [t for t in _fetch_traces(db, date_from, date_to) if _is_client_message(t)]

    groups: dict[str, dict] = {}
    for t in traces:
        g = groups.get(t.whatsapp_hash)
        if g is None:
            g = groups[t.whatsapp_hash] = {
                "whatsapp_hash": t.whatsapp_hash,
                "whatsapp_masked": t.whatsapp_masked,
                "company_id": str(t.company_id) if t.company_id else None,
                "message_count": 0,
                "not_understood_count": 0,
                "last_at": t.received_at,
                "first_at": t.received_at,
            }
        g["message_count"] += 1
        if _diagnose(t)["not_understood"]:
            g["not_understood_count"] += 1
        # A varredura vem em received_at DESC — o primeiro visto é o mais
        # recente; o último, o mais antigo.
        if t.received_at is not None:
            if g["last_at"] is None or t.received_at > g["last_at"]:
                g["last_at"] = t.received_at
            if g["first_at"] is None or t.received_at < g["first_at"]:
                g["first_at"] = t.received_at
        # Um telefone mascarado/tenant só aparece nas linhas que chegaram a
        # resolver o tenant — preserva o primeiro não-nulo encontrado.
        if g["whatsapp_masked"] is None and t.whatsapp_masked:
            g["whatsapp_masked"] = t.whatsapp_masked
        if g["company_id"] is None and t.company_id:
            g["company_id"] = str(t.company_id)

    rows = sorted(
        groups.values(),
        key=lambda g: (g["last_at"] is not None, g["last_at"]),
        reverse=True,
    )
    _attach_company_names(db, rows)
    for r in rows:
        r["last_at"] = r["last_at"].isoformat() if r["last_at"] else None
        r["first_at"] = r["first_at"].isoformat() if r["first_at"] else None
    return rows


def _attach_company_names(db: Session, rows: list[dict]) -> None:
    """Nome do tenant em lote — sem N+1 (o padrão dos serializers do portal)."""
    ids = {r["company_id"] for r in rows if r["company_id"]}
    names: dict[str, str] = {}
    if ids:
        try:
            for c in db.query(Company).filter(Company.id.in_(list(ids))).all():
                names[str(c.id)] = c.name
        except Exception:
            logger.exception("telemetria: lookup de nomes de company falhou")
    for r in rows:
        r["company_name"] = names.get(r["company_id"] or "")


def get_conversation(db: Session, whatsapp_hash: str) -> dict:
    """A conversa inteira, em ordem cronológica, com rótulo e diagnóstico.

    Formato de chat: cada mensagem do cliente vem com o que o bot respondeu
    (`outbound`, do próprio trace daquele evento) — cliente de um lado, bot do
    outro, sem uma segunda consulta por mensagem.
    """
    traces = (
        db.query(BotMessageTrace)
        .filter(BotMessageTrace.whatsapp_hash == whatsapp_hash)
        .order_by(BotMessageTrace.received_at.asc())
        .limit(MAX_TRACES)
        .all()
    )
    traces = [t for t in traces if _is_client_message(t)]
    if not traces:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    labels = _labels_for(db, [t.id for t in traces])

    messages = []
    for t in traces:
        messages.append({
            "trace_id": str(t.id),
            "received_at": t.received_at.isoformat() if t.received_at else None,
            "text": t.user_input,
            "diagnosis": _diagnose(t),
            "detail": _detail(t),
            "outbound": t.outbound if isinstance(t.outbound, list) else [],
            "label": _label_row(labels.get(t.id)),
        })

    head = traces[-1]
    return {
        "whatsapp_hash": whatsapp_hash,
        "whatsapp_masked": next(
            (t.whatsapp_masked for t in traces if t.whatsapp_masked), None,
        ),
        "company_id": str(head.company_id) if head.company_id else None,
        "message_count": len(messages),
        "not_understood_count": sum(
            1 for m in messages if m["diagnosis"]["not_understood"]
        ),
        "messages": messages,
    }


def _labels_for(db: Session, trace_ids: list) -> dict:
    if not trace_ids:
        return {}
    rows = (
        db.query(BotMessageLabel)
        .filter(BotMessageLabel.trace_id.in_(trace_ids))
        .all()
    )
    return {lb.trace_id: lb for lb in rows}


def upsert_label(
    db: Session,
    trace_id: UUID,
    understood: Optional[str],
    expected_intent: Optional[str],
    note: Optional[str],
    actor_id,
) -> dict:
    """Grava (ou corrige, ou apaga) o rótulo de UMA mensagem.

    Marcar é opcional por mensagem: o que está certo fica em branco. Limpar os
    três campos APAGA a linha em vez de gravar uma vazia — é como a tela
    desfaz uma marcação, e é o que o CHECK do banco protege.
    """
    understood = (understood or None)
    expected_intent = (expected_intent or None)
    note = (note or "").strip() or None

    if understood is not None and understood not in UNDERSTOOD_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"understood inválido; use um de {list(UNDERSTOOD_VALUES)}",
        )
    if expected_intent is not None and expected_intent not in EXPECTED_INTENTS:
        raise HTTPException(
            status_code=422,
            detail=f"expected_intent inválido; use um de {list(EXPECTED_INTENTS)}",
        )

    trace = (
        db.query(BotMessageTrace)
        .filter(BotMessageTrace.id == trace_id)
        .first()
    )
    if trace is None:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    existing = (
        db.query(BotMessageLabel)
        .filter(BotMessageLabel.trace_id == trace_id)
        .first()
    )

    is_empty = understood is None and expected_intent is None and note is None
    if is_empty:
        if existing is not None:
            db.delete(existing)
            db.commit()
        return {"trace_id": str(trace_id), "label": None}

    if existing is None:
        existing = BotMessageLabel(trace_id=trace_id)
        db.add(existing)

    existing.understood = understood
    existing.expected_intent = expected_intent
    existing.note = note
    existing.labeled_by = actor_id
    db.commit()
    db.refresh(existing)

    return {"trace_id": str(trace_id), "label": _label_row(existing)}
