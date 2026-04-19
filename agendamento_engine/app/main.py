import asyncio
import logging
import os
from contextlib import asynccontextmanager


logging.basicConfig(
    level=logging.getLevelName(os.getenv("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.modules.auth.router import router as auth_router
from app.modules.companies.router import router as companies_router
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restringir em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(companies_router)
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

# Static files (uploaded images)
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.3.0"}