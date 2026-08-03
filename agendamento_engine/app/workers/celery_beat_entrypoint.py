"""
Ponto de entrada para o Celery Beat.

Existe por UMA razão: é aqui que o `beat_schedule` é aplicado ao `celery_app`.
(Não é barreira anti-ciclo — o import circular foi verificado e não ocorre.)

O registro das tasks é responsabilidade de `celery_app.conf.imports`, que o
worker e o beat carregam por igual; os 4 `import` avulsos que ficavam aqui eram
redundantes desde o S-registro e foram removidos.

Uso no docker-compose / Railway:
  celery -A app.workers.celery_beat_entrypoint:celery_app beat --loglevel=info
"""
from app.infrastructure.celery_app import celery_app  # noqa: F401 — exportado para CLI
from app.workers.beat_schedule import beat_schedule

celery_app.conf.beat_schedule = beat_schedule
