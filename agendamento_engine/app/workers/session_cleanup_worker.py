"""
Worker de limpeza de sessões de bot expiradas — Celery task.

Migrado de asyncio loop para Celery Beat no Sprint 4.
Agendado via beat_schedule: a cada 5 minutos.

Escopo: APENAS bot_sessions.
booking_sessions são gerenciadas pelo handler booking_session.expired (EventBus).
Não unificar — são domínios distintos.

Coexistência: asyncio worker mantido durante a transição (ver plano-fase1-v3.md).
"""
import logging
import redis as redis_client
from datetime import datetime, timezone

from sqlalchemy import text

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal
from app.core.config import settings

logger = logging.getLogger(__name__)

_DEAD_LETTER_KEY = "dead_letter:session_cleanup"


@celery_app.task(
    bind=True,
    name="app.workers.session_cleanup_worker.cleanup_bot_sessions",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def cleanup_bot_sessions(self):
    """Deleta bot_sessions expiradas em batches."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # limpeza multi-tenant — bypass RLS
        now = datetime.now(timezone.utc)
        batch_size = settings.BOT_SESSION_CLEANUP_BATCH_SIZE
        total_deleted = 0

        while True:
            result = db.execute(
                text(
                    """
                    DELETE FROM bot_sessions
                    WHERE id IN (
                        SELECT id FROM bot_sessions
                        WHERE expires_at < :now
                        LIMIT :limit
                        FOR UPDATE SKIP LOCKED
                    )
                    """
                ),
                {"now": now, "limit": batch_size},
            )
            deleted = result.rowcount
            db.commit()
            total_deleted += deleted

            if deleted < batch_size:
                break

        if total_deleted > 0:
            logger.info("session_cleanup_worker: %d bot_sessions expiradas removidas", total_deleted)
        else:
            logger.debug("session_cleanup_worker: nenhuma bot_session expirada encontrada")

    except Exception as exc:
        db.rollback()
        logger.exception("session_cleanup_worker: erro attempt=%d", self.request.retries)
        if self.request.retries >= self.max_retries:
            _push_dead_letter(self, exc)
        raise
    finally:
        db.close()


def _push_dead_letter(task, exc: Exception) -> None:
    try:
        r = redis_client.from_url(settings.REDIS_URL)
        r.rpush(
            _DEAD_LETTER_KEY,
            f"task_id={task.request.id} retries={task.request.retries} error={exc!r}",
        )
        logger.error(
            "session_cleanup_worker: dead-letter após %d tentativas task_id=%s",
            task.request.retries, task.request.id,
        )
    except Exception:
        logger.exception("session_cleanup_worker: falha ao gravar dead-letter")


# --- Compatibilidade asyncio (mantida durante coexistência, removida ao fim do Sprint 4) ---
import asyncio as _asyncio


async def run_session_cleanup_worker() -> None:
    """Loop asyncio legado. Mantido durante coexistência com Celery. Ver plano-fase1-v3.md."""
    logger.info("session_cleanup_worker: asyncio loop iniciado (coexistência com Celery)")
    while True:
        try:
            loop = _asyncio.get_event_loop()
            await loop.run_in_executor(None, _cleanup_sync_compat)
        except Exception:
            logger.exception("session_cleanup_worker (asyncio): erro inesperado")
        await _asyncio.sleep(15 * 60)


def _cleanup_sync_compat() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        batch_size = settings.BOT_SESSION_CLEANUP_BATCH_SIZE
        total_deleted = 0
        while True:
            result = db.execute(
                text(
                    """
                    DELETE FROM bot_sessions
                    WHERE id IN (
                        SELECT id FROM bot_sessions
                        WHERE expires_at < :now
                        LIMIT :limit
                        FOR UPDATE SKIP LOCKED
                    )
                    """
                ),
                {"now": now, "limit": batch_size},
            )
            deleted = result.rowcount
            db.commit()
            total_deleted += deleted
            if deleted < batch_size:
                break
        if total_deleted > 0:
            logger.info("session_cleanup_worker (asyncio compat): %d removidas", total_deleted)
    except Exception:
        db.rollback()
        logger.exception("session_cleanup_worker (asyncio compat): erro no ciclo")
    finally:
        db.close()
