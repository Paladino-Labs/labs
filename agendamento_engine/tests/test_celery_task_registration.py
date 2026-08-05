"""Registro de tasks do Celery — S-registro.

INVARIANTE PROTEGIDO
--------------------
Toda task que o `beat_schedule` despacha precisa estar registrada quando o worker
sobe com o comando de produção (`docker-compose.yml`):

    celery -A app.infrastructure.celery_app:celery_app worker

O beat despacha por NOME — não precisa do código da task. Se o worker não
registrar o módulo, o despacho vira `NotRegistered` e a task nunca roda: falha
silenciosa em produção, invisível na suíte. Antes deste sprint o alvo de produção
registrava ZERO tasks.

⚠️ POR QUE TUDO RODA EM SUBPROCESSO — E POR QUE ESTE ARQUIVO NÃO IMPORTA CELERY
-------------------------------------------------------------------------------
Dez e poucos arquivos desta suíte injetam `sys.modules["celery"] = MagicMock()`,
sob o guard `if "celery" not in sys.modules`. Isso cria contaminação nas DUAS
direções:

  → se eles rodarem antes, um teste in-process aqui leria um registro falso
    (MagicMock) e passaria ou falharia por ordenação de arquivos;
  → se ESTE arquivo importar o celery real na coleção, o guard deles não dispara,
    o mock nunca é instalado e 10 testes de worker quebram (medido: sprint13,
    sprint15 e sprint17 falharam exatamente assim numa versão anterior deste
    arquivo).

Por isso o escopo do módulo importa apenas stdlib e pytest. Toda inspeção do
Celery acontece num interpretador limpo, que é também a forma mais fiel de
verificar o invariante: é literalmente o boot do worker de produção.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Alvo -A do worker de produção (docker-compose.yml, serviço celery_worker).
_PROD_TARGET_MODULE = "app.infrastructure.celery_app"
_PROD_TARGET_ATTR = "celery_app"

# Executado num interpretador limpo — é o que o worker Celery faz no boot.
_BOOT_PROBE = f"""
import json, os, sys
sys.path.insert(0, os.getcwd())
from importlib import import_module

from {_PROD_TARGET_MODULE} import {_PROD_TARGET_ATTR} as celery_app
celery_app.loader.import_default_modules()   # importa conf.imports / conf.include

from app.workers.beat_schedule import beat_schedule

declared = list(celery_app.conf.imports or ())
beat_tasks = sorted({{entry["task"] for entry in beat_schedule.values()}})

# Módulos de tasks do beat que NÃO foram declarados em conf.imports (ou seja,
# registrados por importação acidental de terceiros, não pela configuração).
undeclared = sorted(
    {{
        celery_app.tasks[name].__module__
        for name in beat_tasks
        if name in celery_app.tasks
    }}
    - set(declared)
)

# Entradas de conf.imports que não importam.
dead = []
for module_path in declared:
    try:
        import_module(module_path)
    except Exception as exc:
        dead.append(module_path + ": " + type(exc).__name__ + ": " + str(exc))

print(json.dumps({{
    "registered": sorted(n for n in celery_app.tasks if not n.startswith("celery.")),
    "beat_entries": len(beat_schedule),
    "beat_tasks": beat_tasks,
    "missing": [t for t in beat_tasks if t not in celery_app.tasks],
    "declared_imports": declared,
    "undeclared_modules": undeclared,
    "dead_imports": dead,
}}))
"""


@pytest.fixture(scope="module")
def worker_registry() -> dict:
    """Sobe o alvo de produção num interpretador limpo e devolve o registro."""
    proc = subprocess.run(
        [sys.executable, "-c", _BOOT_PROBE],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        if "No module named 'celery'" in proc.stderr:
            pytest.skip("celery não instalado no ambiente")
        pytest.fail(
            "boot do alvo de produção falhou "
            f"({_PROD_TARGET_MODULE}:{_PROD_TARGET_ATTR}):\n{proc.stderr}"
        )
    return json.loads(proc.stdout.strip().splitlines()[-1])


class TestBeatTasksRegisteredOnProductionTarget:
    """O teste que impede a regressão."""

    def test_every_beat_task_is_registered_by_the_production_worker(self, worker_registry):
        assert worker_registry["missing"] == [], (
            "Tasks do beat_schedule que o worker de produção NÃO registra:\n"
            + "\n".join(f"  - {name}" for name in worker_registry["missing"])
            + "\n\nCorreção: inclua o módulo de cada uma em `imports`, no "
            "celery_app.conf.update() de app/infrastructure/celery_app.py."
        )

    def test_production_target_registers_at_least_the_beat_tasks(self, worker_registry):
        registered = worker_registry["registered"]
        assert len(registered) >= worker_registry["beat_entries"], (
            f"worker registrou {len(registered)} tasks para "
            f"{worker_registry['beat_entries']} entradas de beat"
        )


class TestImportsIsTheRegistrationSource:
    """As tasks estão registradas PORQUE `imports` as lista — não por acaso.

    Sem isto, o teste acima poderia passar só porque outro módulo importou a task
    por efeito colateral, mascarando um `imports` incompleto.
    """

    def test_every_beat_task_module_is_declared_in_conf_imports(self, worker_registry):
        assert worker_registry["undeclared_modules"] == [], (
            "Módulos de task do beat ausentes de conf.imports (registrados por "
            f"importação acidental): {worker_registry['undeclared_modules']}"
        )

    def test_conf_imports_has_no_dead_entries(self, worker_registry):
        assert worker_registry["dead_imports"] == [], (
            f"entradas inválidas em conf.imports: {worker_registry['dead_imports']}"
        )


class TestTasksDispatchedOutsideTheBeat:
    """Três tasks não têm entrada no beat — são chamadas por `.delay()`.

    Rodam no MESMO worker, então precisam do mesmo registro. Ficam de fora da
    verificação por beat_schedule e por isso são afirmadas em separado.
    """

    @pytest.mark.parametrize(
        "task_name",
        [
            "app.workers.communication_worker.send_appointment_communication",
            "app.workers.tasks.expire_reservations.dispatch_soft_reservation_expired",
            # S2.1-A: enfileirada pelo waitlist_handler no cancel/reschedule.
            "app.workers.handlers.waitlist_handler.notify_waitlist_slot_available",
        ],
    )
    def test_delay_dispatched_task_is_registered(self, worker_registry, task_name):
        assert task_name in worker_registry["registered"]
