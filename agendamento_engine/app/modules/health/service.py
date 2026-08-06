"""Readiness do SISTEMA — os sub-checks de `GET /health/deep` (S-heartbeat).

`/health` (em `app/main.py`) é **liveness do processo web** e não muda: é o
healthcheck de deploy do Railway. Se ele passasse a devolver 5xx quando o Redis
oscila, um deploy legítimo falharia por dependência secundária.

Este módulo responde a outra pergunta: *o sistema está saudável de verdade?*

Regras que o desenho respeita:
  • Nenhum sub-check pode pendurar o endpoint (todos têm deadline).
  • Nenhum sub-check pode derrubar outro — cada um é isolado por try/except e
    reportado em separado. Quem abrir o alarme precisa saber SE é banco, worker
    ou fila, sem investigar do zero.
  • O corpo é ANÔNIMO: nomes de sub-check, estado e idades em segundos. Nunca
    hostname, DSN, texto de exceção ou contagem de negócio.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

# O worker bate a cada 60s (app/workers/heartbeat.py HEARTBEAT_INTERVAL_SECONDS).
# 180s = três janelas: duas perdas isoladas não acordam ninguém, ausência real de
# consumidor acende em ≤3 min. Os dois números são knobs INDEPENDENTES de
# propósito — o leitor não importa o módulo do worker (e portanto não arrasta
# celery para dentro do processo web).
WORKER_STALE_AFTER_SECONDS = 180

# Latência aceitável entre despachar e executar um batimento. Acima disso há
# consumidor vivo mas a fila não anda ("worker travado"), que a frescura do
# batimento sozinha não detecta.
QUEUE_LAG_FAIL_SECONDS = 300

# Deadline do broker. Curto de propósito: o check é sobre alcançabilidade, e o
# endpoint precisa responder mesmo com o Redis mudo.
BROKER_TIMEOUT_SECONDS = 2.0

# Fila padrão do Celery (celery_app não declara task_default_queue).
BROKER_QUEUE_NAME = "celery"

_OK = "ok"
_FAIL = "fail"
_UNKNOWN = "unknown"


def check_database(session_factory) -> dict:
    """`SELECT 1`. Hoje o `/health` mente se o Postgres cair."""
    db = None
    try:
        db = session_factory()
        db.execute(text("SELECT 1")).scalar()
        return {"status": _OK}
    except Exception:
        logger.exception("health_deep: banco inacessível")
        return {"status": _FAIL, "error": "unreachable"}
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def check_worker_and_queue(session_factory, now: datetime | None = None,
                           database_ok: bool = True) -> tuple[dict, dict]:
    """Frescura do batimento (worker) e latência da fila, de uma só leitura.

    Banco fora → os dois viram `unknown`, não `fail`: o corpo aponta para o
    banco, que é a causa, em vez de acusar três coisas ao mesmo tempo.

    ⚠️ Banco DE PÉ e leitura falhando é outra coisa — tabela ausente (migration
    não aplicada), permissão, schema fora do lugar. Isso REPROVA. Sem esta
    distinção o endpoint devolveria 200 num deploy sem a `e0s33`: falso verde,
    que é pior que vermelho.
    """
    now = now or datetime.now(timezone.utc)
    db = None
    try:
        db = session_factory()
        rows = db.execute(text(
            "SELECT worker_name, last_seen_at, queue_lag_ms FROM worker_heartbeats"
        )).fetchall()
    except Exception:
        logger.exception("health_deep: falha ao ler worker_heartbeats")
        if database_ok:
            failed = {"status": _FAIL, "error": "heartbeat_unreadable"}
            return failed, {"status": _UNKNOWN, "error": "heartbeat_unreadable"}
        unknown = {"status": _UNKNOWN, "error": "database_unavailable"}
        return unknown, dict(unknown)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    if not rows:
        no_beat = {
            "status": _FAIL,
            "error": "no_heartbeat",
            "workers_alive": 0,
        }
        return no_beat, {"status": _UNKNOWN, "error": "no_heartbeat"}

    ages = []
    for row in rows:
        last_seen = _as_aware(row[1])
        if last_seen is None:
            continue
        ages.append((now - last_seen).total_seconds())

    if not ages:
        no_beat = {"status": _FAIL, "error": "no_heartbeat", "workers_alive": 0}
        return no_beat, {"status": _UNKNOWN, "error": "no_heartbeat"}

    freshest = min(ages)
    alive = sum(1 for age in ages if age <= WORKER_STALE_AFTER_SECONDS)
    worker = {
        "status": _OK if alive >= 1 else _FAIL,
        "workers_alive": alive,
        "workers_known": len(ages),
        "last_seen_age_seconds": round(freshest, 1),
        "stale_after_seconds": WORKER_STALE_AFTER_SECONDS,
    }
    if alive < 1:
        worker["error"] = "heartbeat_stale"

    # Latência medida no batimento mais recente que ainda vale.
    lag_ms = None
    for row in rows:
        last_seen = _as_aware(row[1])
        if last_seen is None:
            continue
        if abs((now - last_seen).total_seconds() - freshest) < 1e-6:
            lag_ms = row[2]
            break

    if worker["status"] != _OK:
        # Sem consumidor fresco, a latência do último batimento não diz nada
        # sobre a fila AGORA — não invente um segundo alarme.
        queue = {"status": _UNKNOWN, "error": "heartbeat_stale"}
    elif lag_ms is None:
        queue = {"status": _UNKNOWN, "error": "lag_not_measured"}
    else:
        lag_seconds = round(lag_ms / 1000.0, 1)
        queue = {
            "status": _OK if lag_seconds <= QUEUE_LAG_FAIL_SECONDS else _FAIL,
            "lag_seconds": lag_seconds,
            "lag_fail_after_seconds": QUEUE_LAG_FAIL_SECONDS,
        }
        if queue["status"] != _OK:
            queue["error"] = "queue_lagging"
    return worker, queue


def check_broker(broker_url: str, timeout: float = BROKER_TIMEOUT_SECONDS,
                 client_factory=None) -> dict:
    """PING no broker com deadline duro.

    Deadline em DUAS camadas: socket timeout no cliente e `future.result(timeout)`
    por fora. A segunda existe porque a primeira depende do cliente se comportar
    — e um endpoint de saúde que pendura é pior que nenhum.

    Traz junto a profundidade da fila padrão: é o único backlog observável hoje
    (a fila durável em tabela, `bot_inbound_messages`, veio na Entrega B do S2.1,
    que está revertida). É informativo e NUNCA reprova sozinho — não há limiar
    calibrado, e um pico legítimo não é incidente.
    """
    factory = client_factory or _default_redis_client

    def _probe() -> dict:
        client = factory(broker_url, timeout)
        result = {"status": _OK}
        client.ping()
        try:
            result["queue_depth"] = int(client.llen(BROKER_QUEUE_NAME))
        except Exception:
            logger.debug("health_deep: profundidade da fila indisponível", exc_info=True)
        return result

    executor = ThreadPoolExecutor(max_workers=1)
    try:
        return executor.submit(_probe).result(timeout=timeout)
    except FutureTimeout:
        logger.warning("health_deep: broker não respondeu em %ss", timeout)
        return {"status": _FAIL, "error": "timeout"}
    except Exception:
        logger.exception("health_deep: broker inacessível")
        return {"status": _FAIL, "error": "unreachable"}
    finally:
        # Não espera a thread pendurada: o socket timeout do cliente a encerra.
        executor.shutdown(wait=False)


def _default_redis_client(broker_url: str, timeout: float):
    import redis  # import local: o health não é caminho de boot

    return redis.from_url(
        broker_url,
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
    )


def run_deep_health(session_factory, broker_url: str, **kwargs) -> tuple[dict, int]:
    """Roda os quatro sub-checks e devolve `(corpo, status_http)`.

    200 só quando nada reprova. `unknown` não reprova sozinho — ele sempre
    acompanha um `fail` de outro sub-check, que é quem carrega o alarme.
    """
    checks = {"database": check_database(session_factory)}
    worker, queue = check_worker_and_queue(
        session_factory,
        now=kwargs.get("now"),
        database_ok=checks["database"]["status"] == _OK,
    )
    checks["worker"] = worker
    checks["queue"] = queue
    checks["broker"] = check_broker(
        broker_url,
        timeout=kwargs.get("broker_timeout", BROKER_TIMEOUT_SECONDS),
        client_factory=kwargs.get("broker_client_factory"),
    )

    failed = sorted(name for name, result in checks.items() if result.get("status") == _FAIL)
    body = {
        "status": _OK if not failed else _FAIL,
        "failed": failed,
        "checks": checks,
    }
    return body, (200 if not failed else 503)


def _as_aware(value) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
