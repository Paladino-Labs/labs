import asyncio
import os
from contextlib import asynccontextmanager

from app.core.config import settings  # noqa: E402 — carregado antes do setup_logging

# Parseia ALLOWED_ORIGINS (CSV) ou deriva de FRONTEND_URL quando não configurado.
# Sempre inclui localhost para facilitar desenvolvimento sem alterar o .env.
if settings.ALLOWED_ORIGINS.strip():
    ALLOWED_ORIGINS: list[str] = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
else:
    # Fallback automático: FRONTEND_URL + localhost dev
    _dev_origins = ["http://localhost:3000", "http://localhost:3001"]
    _prod_origin = settings.FRONTEND_URL.strip()
    ALLOWED_ORIGINS = list(dict.fromkeys(
        ([_prod_origin] if _prod_origin else []) + _dev_origins
    ))

from app.core.logging import setup_logging  # noqa: E402

setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))

import logging  # noqa: E402

_sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
    )

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.middleware.request_context import RequestContextMiddleware

from app.modules.auth.router import router as auth_router
from app.modules.companies.router import router as companies_router
from app.modules.company_profile.router import router as profile_router
from app.modules.users.router import router as users_router
from app.modules.customers.router import router as customers_router
from app.modules.professionals.router import router as professionals_router
from app.modules.services.router import router as services_router
from app.modules.schedule.router import router as schedule_router
from app.modules.appointments.router import router as appointments_router
from app.modules.availability.router import router as availability_router
from app.modules.whatsapp.router import router as whatsapp_router
from app.modules.booking.router import router as booking_router
from app.modules.products.router import router as products_router
from app.modules.uploads.router import router as uploads_router
from app.modules.public.router import router as public_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação (substitui @on_event deprecated)."""
    from app.workers.session_cleanup_worker import run_session_cleanup_worker
    from app.workers.reminder_worker import run_reminder_worker

    tasks = [
        asyncio.create_task(run_session_cleanup_worker(), name="session_cleanup_worker"),
        asyncio.create_task(run_reminder_worker(), name="reminder_worker"),
    ]
    logger.info("Background workers iniciados: session_cleanup, reminder")

    yield  # aplicação em execução

    # Shutdown: cancela os workers ao desligar
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("Background workers encerrados")


app = FastAPI(
    title="Paladino Labs API",
    version="0.3.0",
    description="Sistema de gestão para barbearias — Sprint 4 (Agendamento Online)",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(profile_router)
app.include_router(users_router)
app.include_router(customers_router)
app.include_router(professionals_router)
app.include_router(services_router)
app.include_router(schedule_router)
app.include_router(appointments_router)
app.include_router(availability_router)
app.include_router(whatsapp_router)
app.include_router(booking_router)
app.include_router(products_router)
app.include_router(uploads_router)
app.include_router(public_router)

# Static files (uploaded images)
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.3.0"}