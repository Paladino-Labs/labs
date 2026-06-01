# Arquitetura — Paladino

## Stack Tecnológico

### Backend
| Componente | Tecnologia | Versão |
|-----------|-----------|--------|
| Runtime | Python | 3.11 |
| Framework | FastAPI | latest |
| ORM | SQLAlchemy | 2.0 |
| Migrations | Alembic | latest |
| Validação | Pydantic | v2 |
| Task queue | Celery | latest |
| Message broker | Redis | latest |
| Banco de dados | PostgreSQL | via Supabase |
| Criptografia | cryptography (Fernet) | latest |
| Autenticação | python-jose (JWT) | latest |

### Frontend
| Componente | Tecnologia | Versão |
|-----------|-----------|--------|
| Framework | Next.js | 16.2.2 |
| UI library | React | 19.2.4 |
| CSS | TailwindCSS | v4 |
| Componentes | shadcn/ui | v4 |
| Ícones | Lucide React | latest |

### Infraestrutura
| Componente | Tecnologia |
|-----------|-----------|
| Banco de dados | Supabase (PostgreSQL + Storage) |
| File storage | Supabase Storage |
| Task queue | Redis + Celery |
| Deploy | A definir (Fase 5) |

---

## Estrutura de Diretórios

### Backend (`agendamento_engine/`)
```
agendamento_engine/
├── app/
│   ├── core/
│   │   ├── config.py          # Settings (env vars, Pydantic BaseSettings)
│   │   ├── deps.py            # FastAPI dependencies (get_current_user, get_db)
│   │   ├── security.py        # JWT: create_access_token, verify_token
│   │   ├── db_rls.py          # RLS: set_rls_context, configure_rls_events
│   │   ├── celery_db_context.py # Context manager DB+RLS para workers Celery
│   │   └── idempotency.py     # is_processed(), mark_processed()
│   │
│   ├── domain/
│   │   ├── enums/
│   │   │   └── entry_category.py  # EntryCategory + CATEGORY_TO_ENTRY_TYPE
│   │   └── services/
│   │       └── financial.py   # calculate_commission(), calculate_net_value()
│   │
│   ├── infrastructure/
│   │   ├── db/
│   │   │   └── models/        # Todos os modelos SQLAlchemy (42+ arquivos)
│   │   ├── celery_app.py      # Instância Celery + configuração
│   │   └── event_bus.py       # EventBus in-process (best-effort)
│   │
│   ├── modules/               # Um diretório por domínio/módulo
│   │   ├── auth/              # router, service, schemas
│   │   ├── agenda/            # reservation_service, schemas, router
│   │   ├── appointments/
│   │   ├── audit/
│   │   ├── availability/
│   │   ├── booking/           # FSM público (BookingFlow)
│   │   ├── categories/
│   │   ├── communication/     # service, handlers, templates
│   │   ├── companies/
│   │   ├── customers/
│   │   ├── financial_core/    # FinancialCoreEngine + sub-services
│   │   ├── integrations/
│   │   ├── payments/          # PaymentsEngine, providers, validators
│   │   ├── products/
│   │   ├── professionals/
│   │   ├── public/            # Endpoints públicos legados (sem FSM)
│   │   ├── schedule_exceptions/
│   │   ├── services/
│   │   ├── tenant/
│   │   ├── uploads/
│   │   ├── users/
│   │   └── whatsapp/
│   │
│   └── workers/
│       ├── handlers/          # Handlers de eventos (EventBus)
│       │   └── soft_reservation_handler.py
│       └── tasks/             # Celery tasks
│           ├── communication_worker.py
│           ├── booking_session_worker.py
│           ├── reminder_worker.py
│           ├── session_cleanup_worker.py
│           ├── idempotency_cleanup.py
│           └── expire_reservations.py
│
├── migrations/
│   └── versions/              # 52 migrations (33 Fase 1 + 19 Fase 2)
│
├── tests/                     # 142 testes unitários (+ 2 skips PostgreSQL)
├── docs/                      # Briefs e documentação técnica
└── main.py                    # FastAPI app, lifespan, routers
```

### Frontend (`painel/`)
```
painel/
├── app/
│   ├── (dashboard)/           # Rotas autenticadas
│   │   ├── appointments/      # Agenda semanal + novo agendamento
│   │   ├── customers/         # Clientes
│   │   ├── dashboard/         # Overview + KPIs
│   │   ├── integrations/      # Configuração de integrações
│   │   ├── payments/          # Pagamentos (lista + detalhe)
│   │   ├── products/          # Produtos
│   │   ├── professionals/     # Profissionais
│   │   ├── services/          # Serviços
│   │   ├── settings/          # Hub de configurações
│   │   │   ├── financial/     # Status subconta Asaas
│   │   │   ├── profile/       # Perfil da empresa
│   │   │   └── security/      # Troca de senha
│   │   └── users/             # Gestão de usuários
│   ├── book/
│   │   └── [slug]/            # Vitrine pública + BookingFlow
│   └── page.tsx               # Login
├── lib/
│   ├── api.ts                 # api.get/post/patch/delete + publicFetch
│   ├── auth.tsx               # AuthContext, useAuth
│   └── constants.ts           # STATUS_OPTIONS, badges, etc.
└── components/                # Componentes compartilhados
```

---

## Princípios de Design

### 1. Multi-tenancy por RLS
Todo dado pertence a um tenant (`company_id`). O isolamento é enforçado
no banco de dados via PostgreSQL Row-Level Security. A aplicação define
o contexto do tenant via `set_config('app.company_id', ...)` antes de
cada query. Sem o contexto correto, nenhuma linha é retornada.

Ver [infrastructure.md](infrastructure.md) e [security.md](security.md).

### 2. Imutabilidade de registros financeiros
`movements` e `entries` são append-only. Triggers de banco rejeitam
UPDATE e DELETE. Correções são feitas por novos lançamentos de ajuste.
O ORM adiciona `@validates` como segunda camada de defesa.

Ver [domains/financial-core.md](domains/financial-core.md).

### 3. Idempotência em eventos externos
Webhooks e eventos externos são processados via `ProcessedIdempotencyKey`
(tabela `processed_idempotency_keys`). O registro é feito na mesma
transação que o processamento, garantindo que replay não cause efeito duplo.

Ver [domains/payments.md](domains/payments.md) e [infrastructure.md](infrastructure.md).

### 4. Separação de concerns: domínio vs. notificação
Engines de domínio (PaymentsEngine, FinancialCoreEngine) nunca chamam
CommunicationService diretamente. Publicam eventos via EventBus após
commit. Handlers separados consomem os eventos e disparam notificações.
Falha na notificação não afeta o domínio.

### 5. EventBus best-effort vs. Celery crítico
- **EventBus in-process:** para eventos tolerantes a falha (notificações,
  logs secundários). Não persiste. Se o processo morrer, o evento se perde.
- **Celery task direta:** para fluxos críticos (expiração de reservas,
  lembretes de agendamento). Persiste no Redis até confirmação.

### 6. PII protegido em repouso
CPF/CNPJ nunca em plaintext no banco. Armazenado como:
- `cpf_cnpj_encrypted`: Fernet(PII_ENCRYPTION_KEY)
- `cpf_cnpj_hash`: HMAC-SHA256(PII_HASH_KEY) para deduplicação
- `cpf_cnpj_masked`: preview para UI e logs

### 7. API-first no frontend
O frontend não contém lógica de negócio. Toda validação real
acontece no backend. O frontend valida campos para UX (não para segurança).

---

## Fluxo de Requisição (Backend)

```
HTTP Request
    ↓
FastAPI Router
    ↓
RequestContextMiddleware
  → Extrai company_id do JWT
  → Seta company_id_ctx (ContextVar)
    ↓
Depends(get_current_user)
  → Verifica JWT (exp, iat vs last_password_change_at)
  → Retorna User
    ↓
Depends(get_db)
  → Abre sessão SQLAlchemy
  → SQLAlchemy event listener: antes de query →
    set_config('app.company_id', company_id_ctx.get())
    ↓
Handler (router function)
  → Chama service
  → Service chama FinancialCoreEngine / outros
    ↓
Response
```

**Invariante de ordem:** `company_id_ctx` é setado pelo middleware
ANTES de `get_db()` ser chamado pelo FastAPI. Não há race condition.

---

## Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `DATABASE_URL` | ✅ | URL completa do PostgreSQL |
| `SECRET_KEY` | ✅ | Chave para assinar JWTs |
| `ALGORITHM` | ✅ | Algoritmo JWT (ex: HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ✅ | TTL do token |
| `SUPABASE_URL` | ✅ | URL do projeto Supabase |
| `SUPABASE_SERVICE_KEY` | ✅ | Chave de serviço Supabase |
| `REDIS_URL` | ✅ | URL do Redis (Celery broker) |
| `CREDENTIAL_ENCRYPTION_KEY` | ✅ | Fernet key para IntegrationCredential |
| `PII_ENCRYPTION_KEY` | ✅* | Fernet key para CPF/CNPJ (*fallback: CREDENTIAL_ENCRYPTION_KEY) |
| `PII_HASH_KEY` | ✅* | HMAC key para hash de CPF/CNPJ (*fallback: CREDENTIAL_ENCRYPTION_KEY) |
| `ASAAS_API_KEY` | ⚠️ | API key global Asaas (fallback quando tenant não tem credential) |
| `EVOLUTION_API_URL` | ⚠️ | URL da Evolution API (WhatsApp) |
| `EVOLUTION_API_KEY` | ⚠️ | Chave da Evolution API |

**Nota:** separar `PII_ENCRYPTION_KEY` e `PII_HASH_KEY` de
`CREDENTIAL_ENCRYPTION_KEY` antes do Estágio 1 (múltiplos tenants em produção).