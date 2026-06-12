"""
Celery Beat schedule — Sprint 4.

Registrado em celery_app.conf.beat_schedule via celery_app.config_from_object
ou passado diretamente como CELERYBEAT_SCHEDULE no worker de beat.
"""
from celery.schedules import crontab

beat_schedule = {
    "reminder-check": {
        "task": "app.workers.reminder_worker.send_reminders",
        "schedule": crontab(minute="*/10"),
    },
    "session-cleanup": {
        "task": "app.workers.session_cleanup_worker.cleanup_bot_sessions",
        "schedule": crontab(minute="*/5"),
    },
    "idempotency-key-cleanup": {
        "task": "app.workers.idempotency_cleanup.cleanup_old_keys",
        "schedule": crontab(hour=3, minute=0),
    },
    "booking-session-expiry-scan": {
        "task": "app.workers.booking_session_worker.scan_expired_booking_sessions",
        "schedule": crontab(minute="*/5"),
    },
    "communication-drain": {
        "task": "app.workers.communication_worker.drain_scheduled_communications",
        "schedule": crontab(minute="*/5"),
    },
    "soft-reservation-expiry-scan": {
        "task": "app.workers.tasks.expire_reservations.expire_soft_reservations_scan",
        "schedule": crontab(minute="*/5"),
    },
    "customer-credit-expiry": {
        "task": "app.workers.tasks.customer_credit_expiry.customer_credit_expiry_worker",
        "schedule": crontab(hour=2, minute=30),
    },
    "subscription-renewal": {
        "task": "app.workers.tasks.subscription_renewal.subscription_renewal_worker",
        "schedule": crontab(hour=6, minute=0),
    },
    "subscription-overdue": {
        "task": "app.workers.tasks.subscription_overdue.subscription_overdue_worker",
        "schedule": crontab(hour=8, minute=0),
    },
    "expense-recurrence": {
        "task": "app.workers.tasks.expense_recurrence.expense_recurrence_worker",
        "schedule": crontab(hour=6, minute=0),
    },
    "expense-due-soon": {
        "task": "app.workers.tasks.expense_due_soon.expense_due_soon_worker",
        "schedule": crontab(hour=7, minute=30),
    },
    "stock-alert": {
        "task": "app.workers.tasks.stock_alert.stock_alert_worker",
        "schedule": crontab(hour=7, minute=0),
    },
    "payable-due": {
        "task": "app.workers.tasks.payable_due.payable_due_worker",
        "schedule": crontab(hour=7, minute=30),
    },
    "promotions-expiry-scan": {
        "task": "app.workers.tasks.promotions_expiry.promotions_expiry_scanner",
        "schedule": crontab(hour=0, minute=5),
    },
    "nps-send-pending": {
        "task": "app.workers.tasks.nps_worker.nps_send_pending_worker",
        "schedule": crontab(minute="*/15"),
    },
    "nps-expire-surveys": {
        "task": "app.workers.tasks.nps_worker.nps_expire_surveys_worker",
        "schedule": crontab(hour=1, minute=0),
    },
    "waitlist-expire-entries": {
        "task": "app.workers.tasks.waitlist_worker.waitlist_expire_entries_worker",
        "schedule": crontab(minute="*/30"),
    },
    "crm-recompute-classifications": {
        "task": "app.workers.tasks.crm_recompute.crm_recompute_worker",
        "schedule": crontab(hour=3, minute=0),
        # 03:00 — fora do horário de pico
    },
}
