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
    # Registro explícito de tasks no worker/beat (S2.1). `conf.imports` é honrado
    # só na inicialização do worker/beat (import_default_modules) — não dispara em
    # import comum do módulo (web/testes). Garante que as tasks enfileiradas por
    # .delay() estejam registradas independentemente do alvo `-A` do worker, que
    # hoje (app.infrastructure.celery_app) não importa nenhum módulo de task.
    imports=(
        "app.workers.communication_worker",       # send_appointment_communication (S2.1) + drain
        "app.workers.handlers.waitlist_handler",   # notify_waitlist_slot_available (S2.1)
        "app.workers.bot_inbound_worker",          # drain_bot_inbound + sweeper (S2.1)
    ),
)

# beat_schedule importado via autodiscover — não importar aqui para evitar ciclo.
# Passar schedule via: celery -A app.infrastructure.celery_app beat --schedule=...
# ou configurar via celery_app.config_from_object após todos os workers carregados.
# Ver app/workers/beat_schedule.py para a definição.
