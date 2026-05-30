"""
Ponto de entrada para o Celery Beat.

Importa celery_app e registra o beat_schedule após todos os workers
estarem carregados (evita import circular com celery_app.py).

Uso no docker-compose / Railway:
  celery -A app.workers.celery_beat_entrypoint:celery_app beat --loglevel=info
"""
from app.infrastructure.celery_app import celery_app  # noqa: F401 — exportado para CLI
from app.workers.beat_schedule import beat_schedule

celery_app.conf.beat_schedule = beat_schedule
