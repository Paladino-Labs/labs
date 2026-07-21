"""Processamento assíncrono do webhook do bot WhatsApp — S2.1 (Entrega B).

Produção roda um uvicorn, um event loop, servindo painel/vitrine/portal/bot.
O webhook do bot era async mas processava tudo síncrono dentro (SQLAlchemy +
httpx Evolution 15s + LLM shadow 5s) — enquanto uma mensagem processava, todo
o resto PARAVA. Aqui o processamento sai do event loop para o worker Celery.

Fronteira do corte: o webhook persiste a mensagem em bot_inbound_messages
(RECEIVED) e enfileira drain_bot_inbound; se o worker cair após o 200, a linha
fica RECEIVED e o sweeper a re-enfileira (durabilidade melhor que o síncrono de
antes, que perdia a mensagem num crash).

⚠️ ORDENAÇÃO — por que LEASE em tabela e não advisory lock:
  A serialização por conversa NÃO pode usar advisory lock de sessão. O pooler
  transaction-mode do Supabase (6543) reassina o backend por transação, então o
  advisory lock evapora entre commits/backends — provado empiricamente: dois
  workers adquirem o MESMO lock (exclusão mútua some). Mesmo mecanismo do
  vazamento de set_config da RLS. Regra do sistema: nada depende de estado de
  sessão do Postgres.

  Lease em bot_conversation_leases: claim atômico via INSERT ON CONFLICT DO
  UPDATE ... WHERE locked_until < now() RETURNING. Cada claim/renovação/release
  é UMA transação → pooler-agnóstico. Só o detentor da lease processa a conversa,
  na ordem de chegada (mais antiga RECEIVED primeiro) → ordem preservada por
  construção. Expiração da lease = recuperação de crash embutida.
"""
import asyncio
import logging
import os
import socket

from sqlalchemy import text

from app.core.celery_db_context import celery_db_session
from app.infrastructure.celery_app import celery_app
from app.workers.communication_worker import _push_dead_letter

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5
# TTL da lease. Cobre o pior caso de UMA mensagem (LLM ~5s + httpx Evolution 15s,
# possivelmente 2-3 envios, + queries → ~60s) com folga 2x. A lease é renovada a
# cada mensagem, então cada mensagem tem a janela inteira. Se uma mensagem passar
# de _LEASE_TTL_SECONDS (patológico/hang), o fencing na renovação contém o dano.
_LEASE_TTL_SECONDS = 120


def _worker_id(task) -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{task.request.id}"


_CLAIM_SQL = text("""
    INSERT INTO bot_conversation_leases (company_id, whatsapp_id, locked_by, locked_until)
    VALUES (:c, :w, :by, now() + make_interval(secs => :ttl))
    ON CONFLICT (company_id, whatsapp_id) DO UPDATE
        SET locked_by = EXCLUDED.locked_by, locked_until = EXCLUDED.locked_until
        WHERE bot_conversation_leases.locked_until < now()
    RETURNING locked_by
""")

_RENEW_SQL = text("""
    UPDATE bot_conversation_leases
        SET locked_until = now() + make_interval(secs => :ttl)
        WHERE company_id = :c AND whatsapp_id = :w
          AND locked_by = :by AND locked_until >= now()
""")

_RELEASE_SQL = text("""
    DELETE FROM bot_conversation_leases
        WHERE company_id = :c AND whatsapp_id = :w AND locked_by = :by
""")

_REAP_SQL = text("""
    UPDATE bot_inbound_messages
        SET status = 'FAILED', processed_at = now()
        WHERE company_id = :c AND whatsapp_id = :w AND status = 'PROCESSING'
    RETURNING id, whatsapp_message_id
""")


@celery_app.task(
    bind=True,
    name="app.workers.bot_inbound_worker.drain_bot_inbound",
    max_retries=20,
)
def drain_bot_inbound(self, company_id: str, whatsapp_id: str):
    """Processa, em ordem de chegada, as mensagens RECEIVED de uma conversa,
    sob lease exclusiva por conversa."""
    from app.infrastructure.db.models import BotInboundMessage
    from app.modules.whatsapp.bot_service import handle_inbound_message

    who = _worker_id(self)
    params = {"c": company_id, "w": whatsapp_id, "by": who, "ttl": _LEASE_TTL_SECONDS}

    with celery_db_session(company_id) as db:
        # 1. Claim atômico da conversa (pooler-agnóstico).
        claimed = db.execute(_CLAIM_SQL, params).fetchone()
        db.commit()
        if claimed is None:
            # Lease válida de outro worker → ele drena esta conversa. Retry
            # defensivo para a janela de término (ele também pega o que chegar).
            logger.debug("drain_bot_inbound: conversa ocupada %s:%s, retry", company_id, whatsapp_id)
            raise self.retry(countdown=5)
        try:
            # 2. Reap de órfãos: como TEMOS a lease, qualquer PROCESSING desta
            # conversa é de um worker anterior que morreu no meio. NÃO reprocessa
            # (handle_inbound_message pode já ter produzido efeito externo — uma
            # resposta, um agendamento — antes do crash; reprocessar duplicaria)
            # e NÃO pula em silêncio: marca FAILED + dead-letter (visível). A
            # conversa segue com as próximas mensagens, em ordem.
            orphans = db.execute(_REAP_SQL, {"c": company_id, "w": whatsapp_id}).fetchall()
            db.commit()
            for _oid, omid in orphans:
                _push_dead_letter(
                    "drain_bot_inbound.orphan", str(self.request.id), -1,
                    RuntimeError(
                        f"msg {omid} ficou em PROCESSING (worker anterior morreu); "
                        f"NÃO reprocessada (efeito externo ambíguo)"
                    ),
                )

            # 3. Processa as RECEIVED em ordem, renovando a lease por mensagem.
            while True:
                renewed = db.execute(_RENEW_SQL, params).rowcount
                db.commit()
                if not renewed:
                    # Perdemos a lease (só se o processamento passou do TTL, que é
                    # folgado). Aborta com segurança — outro worker assumirá.
                    logger.warning("drain_bot_inbound: lease perdida %s:%s, abortando", company_id, whatsapp_id)
                    break

                row = (
                    db.query(BotInboundMessage)
                    .filter(
                        BotInboundMessage.company_id == company_id,
                        BotInboundMessage.whatsapp_id == whatsapp_id,
                        BotInboundMessage.status == "RECEIVED",
                    )
                    .order_by(BotInboundMessage.created_at.asc())
                    .first()
                )
                if row is None:
                    break

                row_id = row.id
                instance_name = row.instance_name
                raw_payload = row.raw_payload
                row.status = "PROCESSING"
                db.commit()

                try:
                    # handle_inbound_message roda intacto (o mesmo de hoje), agora
                    # fora do event loop do uvicorn. asyncio.run dá um loop dedicado.
                    asyncio.run(handle_inbound_message(db, instance_name, raw_payload))
                    row = db.get(BotInboundMessage, row_id)
                    if row is not None:
                        row.status = "DONE"
                        from datetime import datetime, timezone
                        row.processed_at = datetime.now(timezone.utc)
                        db.commit()
                except Exception as exc:
                    db.rollback()
                    row = db.get(BotInboundMessage, row_id)
                    if row is None:
                        break
                    row.attempts = (row.attempts or 0) + 1
                    if row.attempts >= _MAX_ATTEMPTS:
                        row.status = "FAILED"
                        db.commit()
                        _push_dead_letter(
                            "drain_bot_inbound", str(self.request.id), row.attempts, exc,
                        )
                    else:
                        row.status = "RECEIVED"
                        db.commit()
                    logger.exception(
                        "drain_bot_inbound: falha msg=%s conv=%s:%s attempt=%d",
                        row_id, company_id, whatsapp_id, row.attempts if row else -1,
                    )
                    break  # para na falha — preserva a ordem da conversa
        finally:
            # 4. Libera a lease (só se ainda for nossa).
            db.execute(_RELEASE_SQL, {"c": company_id, "w": whatsapp_id, "by": who})
            db.commit()


@celery_app.task(
    bind=True,
    name="app.workers.bot_inbound_worker.sweep_bot_inbound_orphans",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def sweep_bot_inbound_orphans(self):
    """Safety net do beat: re-enfileira conversas com trabalho pendente
    (RECEIVED) ou preso (PROCESSING órfão) que NÃO estão sob lease ativa — o
    drain reassume, faz o reap dos órfãos e processa. A expiração da lease
    substitui o timeout heurístico de PROCESSING (dois mecanismos viram um).
    """
    with celery_db_session(None) as db:  # plataforma — varre todos os tenants
        pending = db.execute(text("""
            SELECT DISTINCT m.company_id, m.whatsapp_id
            FROM bot_inbound_messages m
            LEFT JOIN bot_conversation_leases l
              ON l.company_id = m.company_id
             AND l.whatsapp_id = m.whatsapp_id
             AND l.locked_until >= now()
            WHERE m.status IN ('RECEIVED', 'PROCESSING')
              AND l.company_id IS NULL
        """)).fetchall()

        for company_id, whatsapp_id in pending:
            try:
                drain_bot_inbound.apply_async(
                    args=[str(company_id), str(whatsapp_id)], retry=False,
                )
            except Exception:
                logger.exception("sweep: falha ao enfileirar drain conv=%s:%s", company_id, whatsapp_id)

        # Limpeza de leases órfãs antigas (crash sem release e sem mais trabalho).
        db.execute(text(
            "DELETE FROM bot_conversation_leases WHERE locked_until < now() - make_interval(hours => 1)"
        ))
        db.commit()

    logger.info("sweep_bot_inbound_orphans: %d conversas re-enfileiradas", len(pending))


# ─────────────────────────────────────────────────────────────────────────────
# Self-test de boot — verifica a premissa de concorrência do lease na conexão
# REAL do worker. O claim é pooler-agnóstico por construção, então isto passa em
# qualquer modo de pooler; o valor é pegar uma regressão futura no claim (ex.:
# alguém removendo o WHERE locked_until < now()) e confirmar o banco alcançável.
# ─────────────────────────────────────────────────────────────────────────────

_SELFTEST_WHATSAPP_ID = "__s21_lease_selftest__"


def verify_lease_serialization():
    """True = claim dá exclusão mútua; False = premissa quebrada; None = pulado."""
    from app.infrastructure.db.session import SessionLocal

    s0 = SessionLocal()
    try:
        cid = s0.execute(text("SELECT id FROM companies LIMIT 1")).scalar()
    finally:
        s0.close()
    if cid is None:
        logger.info("bot lease self-test: pulado (sem company no banco)")
        return None

    claim = text("""
        INSERT INTO bot_conversation_leases (company_id, whatsapp_id, locked_by, locked_until)
        VALUES (:c, :w, :by, now() + make_interval(secs => 30))
        ON CONFLICT (company_id, whatsapp_id) DO UPDATE
            SET locked_by = EXCLUDED.locked_by, locked_until = EXCLUDED.locked_until
            WHERE bot_conversation_leases.locked_until < now()
        RETURNING locked_by
    """)
    cleanup = text("DELETE FROM bot_conversation_leases WHERE company_id=:c AND whatsapp_id=:w")
    p = {"c": cid, "w": _SELFTEST_WHATSAPP_ID}

    s1 = SessionLocal()
    s2 = SessionLocal()
    try:
        s1.execute(cleanup, p)  # remove sentinela residual
        s1.commit()
        got1 = s1.execute(claim, {**p, "by": "selftest-1"}).fetchone()
        s1.commit()
        got2 = s2.execute(claim, {**p, "by": "selftest-2"}).fetchone()
        s2.commit()
        ok = (got1 is not None) and (got2 is None)
        s1.execute(cleanup, p)
        s1.commit()
        return ok
    finally:
        s1.close()
        s2.close()


try:
    from celery.signals import worker_ready

    @worker_ready.connect
    def _bot_lease_selftest_on_boot(**_kwargs):  # pragma: no cover (roda no worker)
        try:
            result = verify_lease_serialization()
            if result is False:
                logger.critical(
                    "BOT LEASE SELF-TEST FALHOU: o claim de lease NÃO dá exclusão "
                    "mútua nesta conexão — a ordenação por conversa do bot NÃO está "
                    "garantida. Investigue o DATABASE_URL/pooler do worker."
                )
            elif result is True:
                logger.info("bot lease self-test: OK (exclusão mútua do claim verificada)")
        except Exception:
            logger.exception("bot lease self-test: erro ao executar (não fatal)")
except Exception:  # pragma: no cover — celery ausente (alguns testes mockam)
    pass
