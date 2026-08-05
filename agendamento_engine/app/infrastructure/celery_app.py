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
    # ── Registro de tasks ────────────────────────────────────────────────────
    # FONTE ÚNICA. O worker de produção sobe com
    #   celery -A app.infrastructure.celery_app:celery_app worker
    # e só conhece as tasks dos módulos listados aqui — o loader os importa no
    # boot. Sem esta lista o worker registra ZERO tasks e todo despacho do beat
    # (que despacha por NOME, sem precisar do código) vira NotRegistered.
    #
    # ⚠ Ao criar um módulo de task novo, inclua-o abaixo.
    #   tests/test_celery_task_registration.py falha se você esquecer.
    imports=(
        # app/workers/
        "app.workers.booking_session_worker",
        "app.workers.communication_worker",
        "app.workers.idempotency_cleanup",
        "app.workers.reminder_worker",
        "app.workers.session_cleanup_worker",
        # app/workers/handlers/ — handler de EventBus que também hospeda task
        # (notify_waitlist_slot_available, enfileirada por .delay/.apply_async
        #  a partir do próprio handler; S2.1-A)
        "app.workers.handlers.waitlist_handler",
        # app/workers/tasks/
        "app.workers.tasks.crm_recompute",
        "app.workers.tasks.customer_credit_expiry",
        "app.workers.tasks.expense_due_soon",
        "app.workers.tasks.expense_recurrence",
        "app.workers.tasks.expire_reservations",
        "app.workers.tasks.nps_worker",
        "app.workers.tasks.payable_due",
        "app.workers.tasks.promotions_expiry",
        "app.workers.tasks.stock_alert",
        "app.workers.tasks.subscription_overdue",
        "app.workers.tasks.subscription_renewal",
        "app.workers.tasks.waitlist_worker",
    ),
)

# O beat_schedule NÃO é aplicado aqui: quem o registra é
# app/workers/celery_beat_entrypoint.py, o alvo -A do processo de beat.
# Ver app/workers/beat_schedule.py para a definição das entradas.
#
# (Não existe autodiscover_tasks neste repositório. O comentário anterior
#  afirmava o contrário e era falso — as tasks vivem em duas convenções de
#  caminho, app/workers/*.py e app/workers/tasks/*.py, e o registro é o
#  `imports` explícito acima.)
