from celery import Celery

from app.core.config import settings

celery_app = Celery("paladino")
celery_app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)

# beat_schedule importado via autodiscover — não importar aqui para evitar ciclo.
# Passar schedule via: celery -A app.infrastructure.celery_app beat --schedule=...
# ou configurar via celery_app.config_from_object após todos os workers carregados.
# Ver app/workers/beat_schedule.py para a definição.
