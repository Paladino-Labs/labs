from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app = FastAPI(
    title="Paladino Labs API",
    version="0.2.0",
    description="Sistema de gestão para barbearias — Sprint 2 (WhatsApp Bot)",
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


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
