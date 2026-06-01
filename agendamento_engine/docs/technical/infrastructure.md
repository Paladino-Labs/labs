# Infraestrutura — Paladino

## Row-Level Security (RLS)

### Como funciona

PostgreSQL RLS enforça que cada query retorna apenas linhas do tenant correto.

**Política padrão (em 30+ tabelas):**
```sql
CREATE POLICY tenant_isolation ON [tabela]
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE [tabela] ENABLE ROW LEVEL SECURITY;
```

**Tabelas sem `company_id`:** movementreconciliations usa `company_id`
desnormalizado para RLS eficiente sem JOIN.

### Onde o contexto é setado

`app/core/db_rls.py → set_rls_context(db, company_id)`

```python
db.execute(text("SET LOCAL app.company_id = :cid"), {"cid": str(company_id)})
```

Chamado pelo SQLAlchemy event listener (`configure_rls_events`) antes
de cada query dentro da sessão.

**Fluxo:**
```
RequestContextMiddleware
  → Extrai company_id do JWT → seta company_id_ctx (ContextVar)

get_db() (FastAPI Depends)
  → Abre sessão → configure_rls_events registrado
  → Antes de cada query: lê company_id_ctx → SET LOCAL app.company_id
```

**Invariante:** `company_id_ctx` é setado pelo middleware ANTES de
`get_db()` ser chamado. O FastAPI chama os Depends dentro do handler,
após os middlewares terem executado.

### Superuser bypass

Queries que precisam ignorar RLS (seeds, migrations, PLATFORM_OWNER)
usam conexão de superuser ou `SET LOCAL row_security = off`.

### RLS em workers Celery

`app/core/celery_db_context.py`:

```python
@contextmanager
def celery_db_context(company_id):
    with SessionLocal() as db:
        set_rls_context(db, company_id)
        try:
            yield db
            db.commit()
        except:
            db.rollback()
            raise
```

Cada task Celery recebe `company_id` como parâmetro e usa este context manager.

---

## EventBus (In-Process, Best-Effort)

`app/infrastructure/event_bus.py`

### Características
- Síncrono e in-process (sem serialização, sem rede)
- Best-effort: se o processo morrer, evento perdido
- Handler executa na mesma thread que o publicador
- Falha no handler é capturada e logada (não propaga para o caller)

### API
```python
event_bus.register(event_name, handler_fn)
event_bus.publish(event_name, **kwargs)

# Decorator
@event_bus.on(event_name)
def handle(event_name, **kwargs): ...
```

### Quando usar EventBus vs. Celery

| Critério | EventBus | Celery |
|---------|---------|--------|
| Tolerância a falha | Alta (notificações) | Baixa (expiração de reserva) |
| Persistência necessária | Não | Sim |
| Execução assíncrona real | Não (mesma thread) | Sim |
| Retry automático | Não | Sim |

**Regra:** domínios críticos (reservas, lembretes) usam Celery task direta.
Notificações e logs secundários usam EventBus.

### Handlers registrados

| Evento | Handler | Tipo |
|--------|---------|------|
| `payment.confirmed` | CommunicationHandler | EventBus |
| `payment.refunded` | CommunicationHandler | EventBus |
| `agenda.soft_reservation.expired` | SoftReservationHandler | EventBus |

---

## Celery

`app/infrastructure/celery_app.py`

### Configuração
- Broker: Redis (`REDIS_URL`)
- Backend: Redis (para resultado das tasks)
- Serializer: JSON

### Workers

| Worker / Task | Tipo | Schedule |
|--------------|------|----------|
| `communication_worker` | Task | Sob demanda |
| `booking_session_worker` | Task | Sob demanda |
| `reminder_worker` | Beat | */30 min |
| `expire_soft_reservations_scan` | Beat | */5 min |
| `idempotency_cleanup` | Beat | Diário |
| `session_cleanup_worker` | Beat | Diário |

### Celery Beat Schedule (`beat_schedule.py`)
```python
CELERY_BEAT_SCHEDULE = {
    "reminder-check":          {"task": "reminder_worker", "schedule": crontab(minute="*/30")},
    "soft-reservation-expiry": {"task": "expire_soft_reservations_scan", "schedule": crontab(minute="*/5")},
    "idempotency-cleanup":     {"task": "idempotency_cleanup", "schedule": crontab(hour=3, minute=0)},
    "session-cleanup":         {"task": "session_cleanup_worker", "schedule": crontab(hour=2, minute=0)},
}
```

### Retry e Dead-Letter
Tasks críticas têm `max_retries=3`, `countdown=exponential_backoff`.
Tasks que excedem `max_retries` são movidas para a fila dead-letter
(implementação a definir — atualmente apenas logadas).

---

## Idempotência (ProcessedIdempotencyKey)

`app/core/idempotency.py`

Tabela `processed_idempotency_keys`:
```
key         VARCHAR NOT NULL
consumer    VARCHAR NOT NULL     # quem consumiu (ex: "payment_confirmed")
company_id  UUID nullable        # auditoria; não usado em RLS
processed_at TIMESTAMPTZ DEFAULT now()
PRIMARY KEY (key, consumer)
```

API:
```python
is_processed(key, consumer, db) → bool
mark_processed(key, consumer, company_id, db) → None
```

**Invariante:** `mark_processed` deve ser chamado na **mesma transação**
que o processamento. Se a transação fizer rollback, a chave de
idempotência também é revertida — garantindo que o evento pode ser
reprocessado.

---

## Alembic — Migrations

### Cadeia atual
33 migrations (Fase 1) + 19 migrations (Fase 2) = 52 total.
HEAD: `c2d3e4f5g6h7` (add_direct_occupancies)

Cadeia linear (sem branches abertas desde o merge em `906df50dc028`).

### Convenções
- Revision IDs: gerados manualmente no formato `k1l2m3n4o5p6` (não auto-gerado)
- Docstring com `Revises:` deve corresponder ao `down_revision` da variável Python
- Toda nova tabela inclui `CREATE POLICY tenant_isolation` + `ENABLE ROW LEVEL SECURITY`
- Migrations de Sprint financeiro incluem triggers de imutabilidade inline

### Comandos
```bash
# Aplicar todas as migrations pendentes
alembic upgrade head

# Verificar head
alembic current

# Verificar conflitos
alembic heads   # deve retornar exatamente 1 linha
```

---

## Supabase Storage

Uploads de imagem (logo, galeria, avatar de profissional) são
armazenados no Supabase Storage.

`app/modules/uploads/router.py → POST /uploads/`

Retorna URL pública permanente. O frontend armazena apenas a URL;
o arquivo fica no Supabase.

---

## Dívidas de Infraestrutura

| Dívida | Status |
|--------|--------|
| asyncio.create_task coexistindo com Celery Beat | Remover após 24h sem erros em produção |
| 2 testes de trigger (movements/entries) | Validar em staging com PostgreSQL real |
| Dead-letter queue não implementada | Fase 3 ou hotfix |
| CORS permissivo | Configurar antes de produção com múltiplos tenants |
| Separação de chaves PII | Antes do Estágio 1 |