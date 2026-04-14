"""
Worker de limpeza de sessões de bot expiradas.

Executa a cada 15 minutos e deleta registros de bot_sessions cujo
expires_at já passou. Usa batching para evitar locks longos em tabelas
grandes.

Segurança de concorrência:
    O SELECT FOR UPDATE NOWAIT em _get_session_locked() bloqueia a linha
    enquanto uma sessão está sendo processada. Como o worker só deleta
    WHERE expires_at < NOW(), linhas ativas (com TTL resetado após
    processamento) nunca correspondem ao critério → sem conflito real.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.infrastructure.db.session import SessionLocal
from app.core.config import settings

logger = logging.getLogger(__name__)

_INTERVAL_SECONDS = 15 * 60  # 15 minutos


async def run_session_cleanup_worker() -> None:
    """Loop infinito. Registrado no startup do FastAPI."""
    logger.info("session_cleanup_worker: iniciado (intervalo=%ds)", _INTERVAL_SECONDS)
    while True:
        try:
            await _cleanup_once()
        except Exception:
            logger.exception("session_cleanup_worker: erro inesperado")
        await asyncio.sleep(_INTERVAL_SECONDS)


async def _cleanup_once() -> None:
    """Deleta sessões expiradas em batches. Roda no executor para não bloquear o event loop."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _cleanup_sync)


def _cleanup_sync() -> None:
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
                # Batch não estava cheio → não há mais registros para deletar
                break
            # Batch cheio → pode haver mais; itera imediatamente

        if total_deleted > 0:
            logger.info("session_cleanup_worker: %d sessões expiradas removidas", total_deleted)
        else:
            logger.debug("session_cleanup_worker: nenhuma sessão expirada encontrada")

    except Exception:
        db.rollback()
        logger.exception("session_cleanup_worker: erro ao executar cleanup")
    finally:
        db.close()
