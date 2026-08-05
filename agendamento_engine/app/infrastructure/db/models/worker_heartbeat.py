from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP, JSON

from app.infrastructure.db.base import Base


def _now_utc():
    return datetime.now(timezone.utc)


class WorkerHeartbeat(Base):
    """Batimento de um processo worker do Celery (S-heartbeat).

    Tabela de PLATAFORMA — sem company_id e sem RLS (padrão platform_settings):
    descreve o processo, não um tenant.

    ⚠️ Escrita EXCLUSIVAMENTE pela task `app.workers.heartbeat.worker_heartbeat`,
    que roda no worker. O beat pode despachá-la; quem grava é sempre quem
    executa. Se o beat gravasse, o sinal mentiria no modo de falha de 22/07
    (beat vivo, worker morto).

    A escrita real é um `INSERT ... ON CONFLICT DO UPDATE` em SQL (uma
    transação, idempotente por `worker_name`) — este modelo existe para
    registrar o schema no metadata e documentar as colunas.
    """
    __tablename__ = "worker_heartbeats"

    worker_name = Column(String(200), primary_key=True)
    last_seen_at = Column(TIMESTAMP(timezone=True), nullable=False, default=_now_utc)
    dispatched_at = Column(TIMESTAMP(timezone=True), nullable=True)
    queue_lag_ms = Column(Integer, nullable=True)
    pid = Column(Integer, nullable=True)
    beat_count = Column(BigInteger, nullable=False, default=0)
    detail = Column(JSON, nullable=False, default=dict)
