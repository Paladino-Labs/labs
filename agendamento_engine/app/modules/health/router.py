"""`GET /health/deep` — readiness do sistema (S-heartbeat).

⚠️ **ANÔNIMO, e isso é requisito.** O Uptime Kuma não faz login; um endpoint de
monitoramento autenticado não é monitorado. Mesma exposição do `/health`, que já
é público.

O que o anonimato custa, e como o custo é pago:
  • O corpo devolve nomes de sub-check, estado e idades em segundos. Não devolve
    hostname de worker, PID, DSN, texto de exceção nem número de negócio.
    `queue_depth` é profundidade de fila interna de tasks — não revela volume
    comercial.
  • Rate limit por IP (30/min): o endpoint toca banco e broker, e sem teto seria
    amplificação barata. O Kuma pergunta 1×/min.

⚠️ **Não mexa no `/health`** (`app/main.py`): ele é o healthcheck de DEPLOY do
Railway. Se ele reprovasse por Redis instável, um deploy legítimo falharia por
dependência secundária. `/health` = liveness do processo; `/health/deep` =
readiness do sistema.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.rate_limit import limiter
from app.infrastructure.db.session import SessionLocal
from app.modules.health import service as svc

router = APIRouter(tags=["health"])


@router.get("/health/deep")
@limiter.limit("30/minute")
def health_deep(request: Request) -> JSONResponse:
    """200 se tudo passa; 503 com o sub-check culpado discriminado no corpo.

    Função síncrona de propósito: o FastAPI a roda no threadpool, então nem a
    leitura do banco nem o PING no broker tocam o event loop.
    """
    body, status_code = svc.run_deep_health(SessionLocal, settings.REDIS_URL)
    return JSONResponse(content=body, status_code=status_code)
