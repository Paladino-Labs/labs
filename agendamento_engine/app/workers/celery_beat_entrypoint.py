"""
Ponto de entrada para o Celery Beat.

Importa celery_app e registra o beat_schedule após todos os workers
estarem carregados (evita import circular com celery_app.py).

Uso no docker-compose / Railway:
  celery -A app.workers.celery_beat_entrypoint:celery_app beat --loglevel=info
"""
from app.infrastructure.celery_app import celery_app  # noqa: F401 — exportado para CLI
from app.workers.beat_schedule import beat_schedule

# Sprint 13 — registra task para visibilidade do beat
import app.workers.tasks.customer_credit_expiry  # noqa: F401

celery_app.conf.beat_schedule = beat_schedule
