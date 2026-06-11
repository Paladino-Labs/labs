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
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.rate_limit import limiter
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

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
from app.modules.audit.router import router as audit_router
from app.modules.tenant.router import router as tenant_router
from app.modules.categories.router import router as categories_router
from app.modules.integrations.router import router as integrations_router
from app.modules.communication.router import router as communication_router
from app.modules.financial_core.router import router as financial_router
from app.modules.payments.router import router as payments_router
from app.modules.payments.router import financial_router as payments_financial_router
from app.modules.agenda.router import router as agenda_router
from app.modules.schedule_exceptions.router import router as schedule_exceptions_router
from app.modules.professionals.overrides_router import router as overrides_router
from app.modules.commission.router import router as commission_router
from app.modules.customer_credit.router import router as customer_credit_router
from app.modules.packages.router import router as packages_router
from app.modules.subscriptions.router import router as subscriptions_router
from app.modules.expenses.router import router as expenses_router

from app.infrastructure.db.session import engine
from app.core.db_rls import configure_rls_events
configure_rls_events(engine)

logger = logging.getLogger(__name__)


def _validate_encryption_key() -> None:
    """Fail-fast na ausência de CREDENTIAL_ENCRYPTION_KEY em ambiente não-dev."""
    if not settings.CREDENTIAL_ENCRYPTION_KEY.strip():
        import os
        env = os.getenv("ENVIRONMENT", "development").lower()
        if env not in ("development", "dev", "test", "testing"):
            raise KeyError(
                "CREDENTIAL_ENCRYPTION_KEY ausente. "
                "Gerar com: from cryptography.fernet import Fernet; Fernet.generate_key(). "
                "Nunca commitar no repositório. Armazenar no vault Railway."
            )
        logger.warning(
            "CREDENTIAL_ENCRYPTION_KEY não configurada — endpoints de credenciais "
            "falharão. Aceitável apenas em desenvolvimento."
        )


_validate_encryption_key()


def _validate_pii_keys() -> None:
    """Fail-fast se nenhuma chave PII estiver disponível em produção."""
    has_pii = bool(settings.PII_ENCRYPTION_KEY.strip())
    has_cred = bool(settings.CREDENTIAL_ENCRYPTION_KEY.strip())
    if not has_pii and not has_cred:
        import os
        env = os.getenv("ENVIRONMENT", "development").lower()
        if env not in ("development", "dev", "test", "testing"):
            raise KeyError(
                "PII_ENCRYPTION_KEY ausente e CREDENTIAL_ENCRYPTION_KEY não pode servir de fallback. "
                "Configure PII_ENCRYPTION_KEY no vault Railway antes de subir em produção."
            )
        logger.warning(
            "PII_ENCRYPTION_KEY não configurada — operações de PII (CPF/CNPJ) falharão. "
            "Aceitável apenas em desenvolvimento."
        )


_validate_pii_keys()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação (substitui @on_event deprecated)."""
    # Registrar handlers do EventBus
    from app.workers.booking_session_handlers import register_handlers as register_booking_handlers
    from app.workers.appointment_reminder_handler import register_handlers as register_reminder_handlers
    from app.modules.communication.handlers import register_handlers as register_communication_handlers
    from app.workers.handlers.soft_reservation_handler import register_handlers as register_soft_reservation_handlers
    from app.workers.handlers.commission_handler import register_handlers as register_commission_handlers
    from app.workers.handlers.package_handler import register_handlers as register_package_handlers
    from app.workers.handlers.subscription_payment_handler import register_handlers as register_subscription_handlers
    register_booking_handlers()
    register_reminder_handlers()
    register_communication_handlers()
    register_soft_reservation_handlers()
    register_commission_handlers()
    register_package_handlers()
    register_subscription_handlers()

    yield  # aplicação em execução


app = FastAPI(
    title="Paladino Labs API",
    version="2.0.0",
    description="Paladino — Fase 2 concluída (Financial Core + Pagamentos)",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Lê X-Forwarded-Proto do Railway para que redirects de trailing slash usem https://.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

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
app.include_router(audit_router)
app.include_router(tenant_router)
app.include_router(categories_router)
app.include_router(integrations_router)
app.include_router(communication_router)
app.include_router(financial_router)
app.include_router(payments_router)
app.include_router(payments_financial_router)
app.include_router(agenda_router)
app.include_router(schedule_exceptions_router)
app.include_router(overrides_router)
app.include_router(commission_router)
app.include_router(customer_credit_router)
app.include_router(packages_router)
app.include_router(subscriptions_router)
app.include_router(expenses_router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}