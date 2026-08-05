"""S-heartbeat — batimento do worker + GET /health/deep.

⚠️ ESTE ARQUIVO NÃO IMPORTA CELERY NEM `app.main` NO PROCESSO DO PYTEST.
Dez e poucos arquivos da suíte instalam `sys.modules["celery"] = MagicMock()`
sob o guard `if "celery" not in sys.modules`. Importar o celery real aqui (via
`app.workers.heartbeat`) desarmaria o guard e quebraria 10 testes de worker —
o mesmo mecanismo documentado em test_celery_task_registration.py.

Por isso tudo que toca o worker roda em SUBPROCESSO, num interpretador limpo,
que é também a forma mais fiel de verificar quem escreve o batimento: é
literalmente o boot do worker de produção.

Os testes do endpoint são in-process: `app/modules/health/` não importa celery.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter
from app.modules.health import service as svc
from app.modules.health.router import router as health_router

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────── dublês de banco ────────────────────────────────

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar(self):
        return 1

    def fetchall(self):
        return self._rows


class _FakeSession:
    """Sessão mínima: devolve linhas fixas de worker_heartbeats."""

    def __init__(self, rows=None):
        self._rows = rows or []
        self.closed = False

    def execute(self, statement, params=None):
        return _FakeResult(self._rows)

    def close(self):
        self.closed = True


def _session_factory(rows=None, fail_on=None):
    """`fail_on="connect"` = Postgres fora: nenhuma sessão abre."""
    if fail_on == "connect":
        def _boom():
            raise RuntimeError("could not connect to server")
        return _boom
    return lambda: _FakeSession(rows=rows)


def _heartbeat_row(age_seconds: float, lag_ms: int = 120, name="celery@w1"):
    return (name, datetime.now(timezone.utc) - timedelta(seconds=age_seconds), lag_ms)


class _FakeRedis:
    def __init__(self, depth=0):
        self._depth = depth

    def ping(self):
        return True

    def llen(self, _queue):
        return self._depth


def _redis_factory(depth=0):
    return lambda url, timeout: _FakeRedis(depth)


# ───────────────────────────── o endpoint ───────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    """App mínimo com o router de health — sem importar `app.main`."""

    def _build(rows=None, fail_on=None, redis_factory=None):
        monkeypatch.setattr(
            "app.modules.health.router.SessionLocal",
            _session_factory(rows=rows, fail_on=fail_on),
        )
        monkeypatch.setattr(
            "app.modules.health.service._default_redis_client",
            redis_factory or _redis_factory(),
        )
        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.include_router(health_router)
        return TestClient(app)

    return _build


class TestHealthDeepHappyPath:
    def test_200_when_everything_is_healthy(self, client):
        resp = client(rows=[_heartbeat_row(age_seconds=10)]).get("/health/deep")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["failed"] == []
        assert set(body["checks"]) == {"database", "worker", "queue", "broker"}
        assert all(c["status"] == "ok" for c in body["checks"].values())

    def test_endpoint_is_anonymous_and_leaks_no_internals(self, client):
        """Sem header de auth, e sem hostname/PID/DSN no corpo."""
        resp = client(rows=[_heartbeat_row(age_seconds=10)]).get("/health/deep")

        assert resp.status_code == 200
        raw = resp.text
        for leaked in ("celery@w1", "postgres", "redis://", "password", "Traceback"):
            assert leaked not in raw


class TestHealthDeepDiscriminatesTheFailure:
    """Os dois que importam: 503 dizendo O QUE falhou."""

    def test_503_and_body_blames_the_database(self, client):
        resp = client(fail_on="connect").get("/health/deep")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "fail"
        assert body["failed"] == ["database"]
        assert body["checks"]["database"]["status"] == "fail"
        # Banco fora não acusa worker/fila: a causa é uma só.
        assert body["checks"]["worker"]["status"] == "unknown"
        assert body["checks"]["queue"]["status"] == "unknown"

    def test_503_and_body_blames_the_worker_when_heartbeat_is_stale(self, client):
        stale = svc.WORKER_STALE_AFTER_SECONDS + 60
        resp = client(rows=[_heartbeat_row(age_seconds=stale)]).get("/health/deep")

        assert resp.status_code == 503
        body = resp.json()
        assert body["failed"] == ["worker"]
        assert body["checks"]["worker"]["error"] == "heartbeat_stale"
        assert body["checks"]["worker"]["workers_alive"] == 0
        assert body["checks"]["worker"]["last_seen_age_seconds"] >= stale
        assert body["checks"]["database"]["status"] == "ok"

    def test_503_when_the_heartbeat_table_is_unreadable(self, monkeypatch, client):
        """Migration não aplicada = vermelho, nunca verde.

        Banco de pé + tabela ausente devolveria 200 se a leitura virasse
        `unknown` — o monitor nasceria mentindo no primeiro deploy.
        """
        real = svc.check_worker_and_queue

        def _explode(session_factory, now=None, database_ok=True):
            def _boom():
                raise RuntimeError('relation "worker_heartbeats" does not exist')
            return real(_boom, now=now, database_ok=database_ok)

        monkeypatch.setattr(svc, "check_worker_and_queue", _explode)
        resp = client(rows=[]).get("/health/deep")

        assert resp.status_code == 503
        body = resp.json()
        assert body["failed"] == ["worker"]
        assert body["checks"]["database"]["status"] == "ok"
        assert body["checks"]["worker"]["error"] == "heartbeat_unreadable"

    def test_503_when_no_worker_ever_wrote_a_heartbeat(self, client):
        resp = client(rows=[]).get("/health/deep")

        assert resp.status_code == 503
        assert resp.json()["checks"]["worker"]["error"] == "no_heartbeat"

    def test_503_and_body_blames_the_broker(self, client):
        def _refused(url, timeout):
            raise ConnectionError("Error 111 connecting to redis")

        resp = client(
            rows=[_heartbeat_row(age_seconds=5)], redis_factory=_refused
        ).get("/health/deep")

        assert resp.status_code == 503
        body = resp.json()
        assert body["failed"] == ["broker"]
        assert body["checks"]["broker"]["error"] == "unreachable"
        assert "111" not in resp.text  # erro do cliente não vaza


class TestBrokerCheckNeverHangs:
    def test_broker_timeout_is_bounded_and_reported(self):
        """Cliente que nunca responde não pendura o endpoint."""
        import time

        class _HangingRedis:
            def ping(self):
                time.sleep(30)

        started = time.monotonic()
        result = svc.check_broker(
            "redis://localhost:6379/0",
            timeout=0.3,
            client_factory=lambda url, timeout: _HangingRedis(),
        )
        elapsed = time.monotonic() - started

        assert result == {"status": "fail", "error": "timeout"}
        assert elapsed < 5, f"check do broker levou {elapsed:.1f}s — deveria ser limitado"

    def test_queue_depth_is_informative_and_never_fails_alone(self):
        result = svc.check_broker(
            "redis://localhost:6379/0",
            client_factory=_redis_factory(depth=4200),
        )
        assert result["status"] == "ok"
        assert result["queue_depth"] == 4200


class TestQueueLagDetectsAStuckWorker:
    def test_fresh_heartbeat_with_huge_lag_fails_the_queue_check(self, client):
        lag_ms = (svc.QUEUE_LAG_FAIL_SECONDS + 60) * 1000
        resp = client(rows=[_heartbeat_row(age_seconds=5, lag_ms=lag_ms)]).get("/health/deep")

        assert resp.status_code == 503
        body = resp.json()
        assert body["failed"] == ["queue"]
        assert body["checks"]["worker"]["status"] == "ok"
        assert body["checks"]["queue"]["error"] == "queue_lagging"


# ────────────────── o batimento (subprocesso: worker real) ──────────────────

_WORKER_PROBE = """
import json, os, sys
sys.path.insert(0, os.getcwd())

from app.infrastructure.celery_app import celery_app as prod_app
prod_app.loader.import_default_modules()

import app.workers.heartbeat as hb
from app.workers.beat_schedule import beat_schedule, heartbeat_schedule

captured = []

class _Sess:
    def execute(self, statement, params=None):
        captured.append((str(statement), dict(params or {})))
    def commit(self): captured.append(("COMMIT", {}))
    def rollback(self): captured.append(("ROLLBACK", {}))
    def close(self): pass

hb.SessionLocal = _Sess

# Executa a task DUAS vezes, como o worker faria.
hb.worker_heartbeat("2026-08-05T12:00:00+00:00")
hb.worker_heartbeat("2026-08-05T12:01:00+00:00")

# Quem está escutando worker_ready? (o mecanismo que dispensa o beat)
from celery.signals import worker_ready
ready_receivers = [getattr(r[1](), "__name__", str(r)) for r in worker_ready.receivers]

dispatched = []
class _FakeAsync:
    @staticmethod
    def apply_async(kwargs=None, expires=None):
        dispatched.append({"kwargs": sorted((kwargs or {}).keys()), "expires": expires})
_real = hb.worker_heartbeat
hb.worker_heartbeat = _FakeAsync
hb.dispatch_heartbeat()
hb.worker_heartbeat = _real

print(json.dumps({
    "registered": "app.workers.heartbeat.worker_heartbeat" in prod_app.tasks,
    "declared_in_imports": "app.workers.heartbeat" in list(prod_app.conf.imports or ()),
    "statements": [sql for sql, _ in captured],
    "params": [p for _, p in captured if p],
    "ready_receivers": ready_receivers,
    "dispatched": dispatched,
    "beat_entry": beat_schedule.get("worker-heartbeat", {}).get("task"),
    "heartbeat_schedule_size": len(heartbeat_schedule),
    "interval": hb.HEARTBEAT_INTERVAL_SECONDS,
}, default=str))
"""


@pytest.fixture(scope="module")
def worker_probe() -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _WORKER_PROBE],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        if "No module named 'celery'" in proc.stderr:
            pytest.skip("celery não instalado no ambiente")
        pytest.fail(f"probe do worker falhou:\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


class TestTheWorkerIsTheWriter:
    """⚠️ A armadilha do sprint: se o BEAT escrevesse, o alarme mentiria.

    Beat vivo com worker morto foi o modo de falha de 22/07 — um batimento
    escrito pelo despachante diria "estou vivo" durante o incidente inteiro.
    """

    def test_the_task_is_registered_by_the_production_worker(self, worker_probe):
        assert worker_probe["registered"], (
            "worker de produção não registra app.workers.heartbeat.worker_heartbeat"
        )
        assert worker_probe["declared_in_imports"], (
            "app.workers.heartbeat ausente de celery_app.conf.imports"
        )

    def test_executing_the_task_writes_the_row(self, worker_probe):
        writes = [s for s in worker_probe["statements"] if "worker_heartbeats" in s]
        assert len(writes) == 2, "cada execução da task grava exatamente uma vez"

    def test_the_write_is_an_idempotent_upsert_in_one_transaction(self, worker_probe):
        for sql in worker_probe["statements"]:
            if "worker_heartbeats" not in sql:
                continue
            assert "INSERT INTO worker_heartbeats" in sql
            assert "ON CONFLICT (worker_name) DO UPDATE" in sql
        assert worker_probe["statements"].count("COMMIT") == 2
        assert "ROLLBACK" not in worker_probe["statements"]

        # Mesmo worker → mesma chave nas duas escritas: a segunda ATUALIZA.
        keys = {p["worker_name"] for p in worker_probe["params"] if "worker_name" in p}
        assert len(keys) == 1

    def test_the_dispatcher_never_writes(self, worker_probe):
        """`dispatch_heartbeat` só enfileira; a escrita é do executor."""
        assert worker_probe["dispatched"] == [
            {"kwargs": ["dispatched_at"], "expires": 120}
        ]

    def test_queue_lag_is_recorded_from_the_dispatch_time(self, worker_probe):
        params = [p for p in worker_probe["params"] if "queue_lag_ms" in p]
        assert params, "a escrita precisa carregar queue_lag_ms"
        assert all(p["queue_lag_ms"] is not None and p["queue_lag_ms"] >= 0 for p in params)


class TestTheHeartbeatDoesNotDependOnTheBeat:
    """Parte 3: o beat não existe em produção. O monitor funciona assim mesmo."""

    def test_worker_ready_signal_starts_the_self_dispatch(self, worker_probe):
        assert "_on_worker_ready" in worker_probe["ready_receivers"], (
            "sem receiver de worker_ready o batimento só existiria com beat — "
            "e um monitor que não monitora é o pior resultado possível"
        )

    def test_beat_entry_exists_but_is_redundant(self, worker_probe):
        assert worker_probe["beat_entry"] == "app.workers.heartbeat.worker_heartbeat"
        assert worker_probe["heartbeat_schedule_size"] == 1, (
            "heartbeat_schedule deve conter SÓ o batimento — as demais entradas "
            "despacham trabalho represado e ligá-las é decisão do Silva"
        )

    def test_interval_is_short_enough_to_detect_in_minutes(self, worker_probe):
        assert worker_probe["interval"] <= 60
        assert svc.WORKER_STALE_AFTER_SECONDS <= 5 * 60
        assert svc.WORKER_STALE_AFTER_SECONDS >= 2 * worker_probe["interval"], (
            "limiar precisa tolerar ao menos duas perdas isoladas"
        )


# ────────────────────── /health intocado (subprocesso) ──────────────────────

_APP_PROBE = """
import json, os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
resp = client.get("/health")
paths = sorted(r.path for r in app.routes if getattr(r, "path", "").startswith("/health"))
print(json.dumps({"status": resp.status_code, "body": resp.json(), "paths": paths}))
"""


@pytest.fixture(scope="module")
def app_probe() -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _APP_PROBE],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        pytest.fail(f"boot do app falhou:\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


class TestLivenessIsUntouched:
    def test_health_still_returns_200_and_the_same_body(self, app_probe):
        """O healthcheck de deploy do Railway não pode depender de nada disto."""
        assert app_probe["status"] == 200
        assert app_probe["body"] == {"status": "ok", "version": "2.0.0"}

    def test_both_endpoints_are_mounted(self, app_probe):
        assert app_probe["paths"] == ["/health", "/health/deep"]
