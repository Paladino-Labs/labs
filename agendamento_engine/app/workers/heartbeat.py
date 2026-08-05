"""Batimento do worker Celery — S-heartbeat.

O QUE ESTE MÓDULO PROVA
-----------------------
Que existe um processo worker **consumindo a fila**. Não que o web respondeu,
não que o beat está de pé: que alguém tirou uma mensagem da fila e executou.

Em 22/07 o web estava verde, o beat estava vivo e o bot ficou 22 horas mudo
porque não havia consumidor. Um batimento escrito pelo BEAT teria dito "estou
vivo" durante o incidente inteiro. Por isso quem escreve aqui é sempre quem
EXECUTA a task — o worker.

POR QUE O BATIMENTO NÃO DEPENDE DO BEAT
---------------------------------------
O beat não existe em produção, e ligá-lo dispara tasks represadas (decisão do
Silva, ver CLAUDE.md "O beat nunca rodou em produção"). Um monitor que só
funciona depois daquela decisão não monitora nada.

Então o próprio worker se auto-despacha: no sinal `worker_ready` sobe uma thread
daemon que, a cada `HEARTBEAT_INTERVAL_SECONDS`, **enfileira** a task de
batimento. O worker a consome e grava a linha.

A thread apenas DESPACHA; ela nunca escreve. A distinção é o que dá honestidade
ao sinal — o caminho medido é broker → fila → pool de execução, o mesmo caminho
de qualquer task real. Uma thread que gravasse direto continuaria batendo com o
pool travado ou o broker fora.

`dispatched_at` viaja como argumento da task, então a própria linha registra a
latência da fila (`queue_lag_ms`) — é ela que detecta "worker vivo mas travado",
que a frescura do batimento sozinha não pegaria.

A entrada correspondente no `beat_schedule` existe e é redundante de propósito:
quando o beat subir, ele despacha o mesmo batimento e o upsert absorve os dois
escritores sem conflito.
"""
import logging
import os
import socket
import threading
from datetime import datetime, timezone

from celery.signals import worker_ready, worker_shutdown
from sqlalchemy import text

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)

# Frequência de escrita. Curta o bastante para detectar em minutos, longa o
# bastante para o custo ser irrelevante (1 UPSERT/min numa tabela de N linhas).
# O limiar de alarme vive no leitor (app/modules/health/service.py) e é
# deliberadamente ~3× este valor, para tolerar duas perdas isoladas.
HEARTBEAT_INTERVAL_SECONDS = 60

# Batimento que passou desta idade na fila não interessa mais: o próximo já
# saiu. Evita que uma pilha de batimentos velhos seja drenada de uma vez quando
# o broker volta, fabricando um "tudo bem" retroativo.
_HEARTBEAT_EXPIRES_SECONDS = HEARTBEAT_INTERVAL_SECONDS * 2

_UPSERT_SQL = text("""
    INSERT INTO worker_heartbeats
        (worker_name, last_seen_at, dispatched_at, queue_lag_ms, pid, beat_count, detail)
    VALUES
        (:worker_name, :last_seen_at, :dispatched_at, :queue_lag_ms, :pid, 1, '{}')
    ON CONFLICT (worker_name) DO UPDATE SET
        last_seen_at  = EXCLUDED.last_seen_at,
        dispatched_at = EXCLUDED.dispatched_at,
        queue_lag_ms  = EXCLUDED.queue_lag_ms,
        pid           = EXCLUDED.pid,
        beat_count    = worker_heartbeats.beat_count + 1
""")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dispatched_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@celery_app.task(
    bind=True,
    name="app.workers.heartbeat.worker_heartbeat",
    ignore_result=True,
)
def worker_heartbeat(self, dispatched_at: str | None = None) -> str:
    """Grava o batimento deste worker. Idempotente por `worker_name`.

    Um único `INSERT ... ON CONFLICT DO UPDATE`: uma transação por escrita,
    sem leitura prévia, sem estado de sessão — seguro sob o pooler.

    Sem retry: um batimento perdido é irrelevante (o próximo vem em 1 min) e
    retentar empilharia batimentos velhos, que é justamente o que se quer evitar.
    """
    executed_at = _now_utc()
    dispatched = _parse_dispatched_at(dispatched_at)
    lag_ms = (
        max(0, int((executed_at - dispatched).total_seconds() * 1000))
        if dispatched is not None
        else None
    )

    request = getattr(self, "request", None)
    worker_name = getattr(request, "hostname", None) or f"celery@{socket.gethostname()}"

    db = SessionLocal()
    try:
        db.execute(
            _UPSERT_SQL,
            {
                "worker_name": str(worker_name)[:200],
                "last_seen_at": executed_at,
                "dispatched_at": dispatched,
                "queue_lag_ms": lag_ms,
                "pid": os.getpid(),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("worker_heartbeat: falha ao gravar batimento worker=%s", worker_name)
        raise
    finally:
        db.close()

    logger.debug("worker_heartbeat: worker=%s lag_ms=%s", worker_name, lag_ms)
    return str(worker_name)


# ── Auto-despacho: o worker se agenda sozinho, sem depender do beat ──────────

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def dispatch_heartbeat() -> None:
    """Enfileira UM batimento. Nunca levanta — falha de broker só se registra.

    A falha aqui é informação, não erro a tratar: se o broker está fora, o
    batimento não é gravado e o `/health/deep` fica vermelho. É o comportamento
    desejado — foi o broker que caiu em 22/07.
    """
    try:
        worker_heartbeat.apply_async(
            kwargs={"dispatched_at": _now_utc().isoformat()},
            expires=_HEARTBEAT_EXPIRES_SECONDS,
        )
    except Exception:
        logger.exception("heartbeat: falha ao despachar batimento (broker inacessível?)")


def _heartbeat_loop() -> None:
    while not _stop_event.is_set():
        dispatch_heartbeat()
        _stop_event.wait(HEARTBEAT_INTERVAL_SECONDS)


def start_heartbeat_loop() -> threading.Thread | None:
    """Sobe a thread de auto-despacho (idempotente)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return _thread
    _stop_event.clear()
    _thread = threading.Thread(
        target=_heartbeat_loop,
        name="worker-heartbeat",
        daemon=True,
    )
    _thread.start()
    logger.info(
        "heartbeat: auto-despacho ativo (intervalo=%ss)", HEARTBEAT_INTERVAL_SECONDS
    )
    return _thread


def stop_heartbeat_loop() -> None:
    _stop_event.set()


@worker_ready.connect
def _on_worker_ready(**_kwargs) -> None:
    """Só o worker dispara este sinal — o beat e a API nunca."""
    start_heartbeat_loop()


@worker_shutdown.connect
def _on_worker_shutdown(**_kwargs) -> None:
    stop_heartbeat_loop()
