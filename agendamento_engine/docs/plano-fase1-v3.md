# Plano de execução — Fase 1 (v3)
**Gerado em:** 2026-05-25
**Baseado em:** `brief-fase1-fundacao.md` v2 · `visao-estagio-0.md` · `protocolo-claudemd.md` v1.0
**Varredura de código:** 2026-05-25
**Produto em produção:** SIM — Bot WhatsApp (13 handlers FSM), BookingEngine, Link Público.

---

## Divergências encontradas

Varredura comparou o brief com o código real. Cada divergência classificada como:
- **(a)** invalida tarefa do brief
- **(b)** adiciona pré-requisito
- **(c)** cosmética / sem impacto funcional

| Item | O que o brief afirma | O que o código tem | Impacto | Resolução |
|------|----------------------|--------------------|---------|-----------|
| Localização das migrations | (implícito) `alembic/versions/` | `migrations/versions/` (definido em `alembic.ini`: `script_location = %(here)s/migrations`); existe `alembic/` separado, mas não contém versões | (c) | Em todas as instruções deste plano, paths apontam para `migrations/versions/`. |
| Localização dos modelos SQLAlchemy | (implícito) `app/models/` | `app/infrastructure/db/models/` (estrutura DDD) | (c) | Caminhos corrigidos em todas as referências. |
| `cryptography` no `requirements.txt` (Sprint 5) | "Adicionar `cryptography>=42.0`" | Já presente: `cryptography==46.0.7` | (a) | **Tarefa removida do Sprint 5.** Manter apenas a configuração de `Fernet` em `app/core/encryption.py`. |
| `whatsapp_connection.token` / `whatsapp_connection.server_url` (Sprint 5) | Brief instrui migrar esses campos para `integration_credentials` | Modelo real (`infrastructure/db/models/whatsapp_connection.py`) **não tem** `token` nem `server_url`. Campos reais: `id, company_id, instance_name (UNIQUE), status, phone_number, qr_code, qr_generated_at, connected_at, disconnect_reason, created_at, updated_at`. Credenciais reais em `settings.EVOLUTION_API_URL` e `settings.EVOLUTION_API_KEY` (globais, lidas em `app/modules/whatsapp/evolution_client.py:13,18,26`) | (b) | **Decisão já registrada (Opção A) ativa:** não executar migração no Estágio 0. `WHATSAPP_EVOLUTION` no enum `integration_credentials.provider` permanece schema-only. Bot continua lendo de `settings` global. |
| Uploads — escopo do refactor (Sprint 1) | "Remover `os.makedirs("static/uploads")` de `main.py`" | Confirmado em `app/main.py:113-114`. **Adicional:** `app/modules/uploads/router.py` também tem `UPLOAD_DIR = Path("static/uploads")` e gera URLs com `f"{settings.WEBHOOK_BASE_URL}/static/uploads/{filename}"` | (b) | Sprint 1 deve refatorar **dois arquivos**, não apenas `main.py`: `app/main.py` + `app/modules/uploads/router.py`. |
| `bcrypt__rounds=12` (Sprint 1) | "Fixar explicitamente" | `app/core/security.py:7`: `CryptContext(schemes=["bcrypt"], deprecated="auto")` — sem rounds explícito. `bcrypt==4.0.1` (default da biblioteca = 12) | (c) | Tarefa permanece como blindagem futura. Sem efeito funcional imediato; nenhum hash precisa ser regenerado. |
| `tailwind` versão | Não mencionado no brief | `painel/package.json`: `tailwindcss: ^4` (Tailwind v4) | (c) | Refletir no estado base do `painel/CLAUDE.md`. |
| `next` / `react` versão | Não mencionado no brief | `next: 16.2.2`, `react: 19.2.4`, `shadcn: ^4.2.0` (pacote shadcn como dep direta) | (c) | Refletir no estado base do `painel/CLAUDE.md`. |
| Diretório aninhado `painel/painel/` | Não mencionado | Confirmado em varreduras anteriores: skeleton stranded com `package.json` próprio, `node_modules/` próprio, apenas `layout.tsx`/`page.tsx`/`globals.css` | (b) | Adicionar como tarefa de limpeza no Sprint 1 (não-bloqueante para outras tarefas). |
| Workers atuais | "asyncio loop em main.py lifespan" | Confirmado: `app/main.py:62-66` registra `session_cleanup_worker` + `reminder_worker` via `asyncio.create_task` no lifespan. `app/workers/reminder_worker.py` e `app/workers/session_cleanup_worker.py` rodam `while True + asyncio.sleep`. | (c) | Brief alinhado. |
| `User.role` / `User.company_id` | "String(20)" / "NOT NULL" | Confirmado em `app/infrastructure/db/models/user.py:13,16` | (c) | Brief alinhado. |

**Resumo de impacto na Fase 1:**
- 1 tarefa do Sprint 5 removida (cryptography já está)
- 2 pré-requisitos adicionados ao Sprint 1 (refactor de `uploads/router.py`; limpeza de `painel/painel/`)
- Decisão Opção A (WhatsApp) confirmada por código
- Demais divergências são cosméticas (paths) e não alteram escopo

---

## Decisões já registradas (NÃO reabrir)

Estas decisões estão fechadas. Qualquer geração de código que questione uma delas deve ser recusada:

1. **`whatsapp_connection → integration_credentials`:** **NÃO executar no Estágio 0.** Evolution API permanece global (`EVOLUTION_API_URL` e `EVOLUTION_API_KEY` em variáveis de ambiente). `WHATSAPP_EVOLUTION` em `integration_credentials.provider` enum é schema-only — nenhum registro criado, código do bot continua lendo de `settings`. Quando vier Evolution dedicada por tenant (Estágio 1+), o caminho está pronto.

2. **`PLATFORM_OWNER` vs `OWNER`:** são papéis distintos no enum `userrole`.
   - `PLATFORM_OWNER` → operador da PLATAFORMA Paladino. `company_id=NULL`.
   - `OWNER` (sem prefixo) → dono de UM tenant. `company_id` preenchido.
   Não confundir em nenhuma geração de código, teste ou seed.

3. **Pagamentos:** provider escolhido é **Asaas** (split nativo, subcontas sem KYC separado). Mercado Pago descartado.

4. **Verificação prévia de overlaps em `appointments`:** ✅ executada em **2026-05-22** — resultado **0 linhas**. `EXCLUDE CONSTRAINT no_overlap_per_professional` pode ser aplicada sem remediação prévia de dados.

5. **`cryptography==46.0.7`:** já presente em `requirements.txt`. Sprint 5 **não precisa** adicionar a biblioteca — apenas implementar `app/core/encryption.py` com `Fernet`.

---

## Pré-requisitos antes do Sprint 1

| # | Item | Status |
|---|------|--------|
| 1 | Query de overlaps em `appointments` em produção retornando 0 linhas | ✅ Executado 2026-05-22 |
| 2 | Extensão `btree_gist` ativa no Postgres (`SELECT * FROM pg_extension WHERE extname = 'btree_gist'`) | 🔵 Validar antes da migration do Sprint 1 |
| 3 | Conta Supabase Storage com bucket público `uploads` criado | 🔵 Configurar antes da Tarefa 5 do Sprint 1 |
| 4 | `CREDENTIAL_ENCRYPTION_KEY` gerada e armazenada em vault Railway (gerada com `Fernet.generate_key()`) | 🔵 Pode esperar até o Sprint 5; gerar nesta semana |
| 5 | Acesso ao Railway com plano que suporte Redis + Celery worker + Celery beat como serviços separados | 🔵 Validar antes do Sprint 4 |
| 6 | Grep no `painel/` para verificar se `POST /users` (com senha no body) é chamado pelo frontend | 🔵 Verificar antes do Sprint 2 |

---

## Classificação de risco por sprint

Legenda: 🟢 Adição pura · 🟡 Extensão controlada · 🔴 Mudança de risco · ⛔ Requer decisão

### Sprint 1 — Segurança e infraestrutura crítica

| Tarefa | Class. | Estratégia |
|--------|--------|-----------|
| Migration `add_appointments_overlap_exclusion_constraint` (`btree_gist` + `tsrange`, com `company_id` e `professional_id`, filtrada por `status NOT IN ('CANCELLED', 'FAILED', 'EXPIRED')` — **NO_SHOW e COMPLETED permanecem bloqueando**: slot historicamente ocupado; excluir NO_SHOW permitiria backdating administrativo no mesmo slot) | 🔴 | Pré-requisito ✅ atendido. Migration aplicada em transação única; lock breve. Sem dados a remediar. Rollback: `DROP CONSTRAINT no_overlap_per_professional`. |
| `slowapi` no `requirements.txt` + rate limit `POST /auth/login` (10 req/min/IP) + `Retry-After` em 429. **Key function deve extrair IP real via `X-Forwarded-For`:** `get_real_ip(request)` lê primeiro IP de `X-Forwarded-For` (split por `,`, strip) com fallback para `get_remote_address(request)`. `Limiter(key_func=get_real_ip)`. Sem isso, todo tráfego via Railway chega do mesmo IP do load balancer e o rate limit bloqueia todos os usuários simultaneamente. | 🟢 | Adição pura. Middleware novo. Validar em staging com loop de `curl` confirmando que Railway injeta `X-Forwarded-For` antes de habilitar em produção. |
| Middleware de security headers: sempre `X-Content-Type-Options: nosniff` e `X-Frame-Options: DENY`. **HSTS env-gated:** `if settings.PUBLIC_HTTPS: headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"`. Default `PUBLIC_HTTPS=False`; ativar **apenas com `PUBLIC_HTTPS=true`** na env do Railway de produção. Em staging e local sem TLS, HSTS pode travar o browser por um ano — não habilitar fora de produção HTTPS. | 🟢 | Adição pura. Validar com `curl -I` em staging primeiro (sem HSTS). Habilitar HSTS apenas após confirmar HTTPS estável na URL pública de produção. |
| Fixar `bcrypt__rounds=12` explicitamente em `core/security.py:7` | 🟡 | Sem efeito funcional — `bcrypt==4.0.1` já usa 12 como default. Apenas blinda contra futuro upgrade. Hashes existentes (`$2b$12$...`) continuam válidos. |
| Migrar uploads para Supabase Storage — **refactor de `app/main.py` + `app/modules/uploads/router.py`** | 🔴 | **Estratégia dual-write em 4 etapas:** (a) adicionar SDK Supabase e função de upload paralela em `uploads/service.py`; (b) endpoint `POST /uploads/` grava em ambos (Supabase + local) e retorna URL Supabase; (c) script `scripts/migrate_uploads_to_supabase.py` copia arquivos existentes e atualiza URLs nas tabelas (`professionals.image_url`, `services.image_url`, `products.image_url`, `company_profiles.logo_url`/`cover_url`/`gallery_urls`); (d) remover `os.makedirs("static/uploads")` de `main.py:113`, `app.mount("/static", ...)` de `main.py:114`, e `UPLOAD_DIR = Path("static/uploads")` de `uploads/router.py`. Script de rollback `scripts/rollback_uploads_to_volume.py` **escrito e testado em staging ANTES do go-live**. **Matriz de falha durante dual-write:** Supabase ok → retorna URL Supabase (fonte de verdade); Supabase falha → request falha com 500; local falha durante dual-write → warning em log + request continua; ambos falham → 500. |
| Limpar diretório aninhado `/painel/painel/` (skeleton stranded) | 🟢 | Adição pura. `diff -rq painel/app painel/painel/app` mostrou que `painel/painel/` só tem `layout.tsx`/`page.tsx`/`globals.css`/`favicon.ico` — não é referenciado pelo `painel/` real. Antes de remover: confirmar via `git log` que nenhum commit recente toca lá. |

### Sprint 2 — RBAC: papéis, convite e auditoria

| Tarefa | Class. | Estratégia |
|--------|--------|-----------|
| `ALTER COLUMN users.company_id DROP NOT NULL` | 🟡 | Sem impacto em dados. **Cuidado de código:** `get_current_company_id` em `core/deps.py:38-40` retorna `user.company_id` direto — quebra se NULL. Refactor da dep deve estar no **mesmo PR** da migration. |
| Criar enum PostgreSQL `userrole` com **9 valores**: `OWNER, ADMIN, OPERATOR, PROFESSIONAL, CLIENT, PLATFORM_OWNER` (ativos) + `PLATFORM_SUPPORT, PLATFORM_BILLING, PLATFORM_READONLY` (schema-only) | 🟢 | Adição pura. Criar tipo em migration separada antes do `ALTER COLUMN`. |
| `ALTER COLUMN users.role TYPE userrole USING role::userrole` | 🔴 | **Pré-validação obrigatória:** `SELECT DISTINCT role FROM users` deve retornar apenas `ADMIN`, `PROFESSIONAL`, `CLIENT` (subset do enum novo). Caso contrário, migration falha. Lock `AccessExclusiveLock` breve (< 5s no banco atual). Janela de manutenção planejada se atendimento real estiver em horário comercial. |
| Criar `user_invitations` (invitation_id, company_id [nullable], email, role, token UUID UNIQUE, expires_at default 48h, status enum, invited_by_user_id, created_at) | 🟢 | Adição pura. |
| Criar `audit_logs` (audit_id, company_id [nullable], actor_id, actor_role, action, resource_type, resource_id, amount, account_id, reason, correlation_id, before_snapshot, after_snapshot, occurred_at, ip_address, user_agent). **Sem FK** para outras tabelas (audit nunca bloqueia cascade delete). **Append-only enforced no banco via trigger** (restrição na aplicação não basta para garantir RBAC-4): criar `prevent_audit_modification()` que faz `RAISE EXCEPTION 'audit_logs é append-only: % não é permitido', TG_OP`; criar `audit_no_update` (BEFORE UPDATE) e `audit_no_delete` (BEFORE DELETE). | 🟢 | Adição pura. |
| Criar `app/core/audit/sensitive_context.py` com `ActionScope` enum + `SensitiveAuditContext` dataclass + `REASON_REQUIRED` set + `record_sensitive_action()` | 🟢 | Adição pura. **Criar ANTES dos services que consomem** (passos posteriores deste sprint). |
| Criar `app/domain/enums/action_scope.py` com mesmo enum de `ActionScope` (re-export) | 🟢 | Adição pura. |
| Refactor `core/deps.py`: adicionar `require_role(*roles)` e `require_action(action, scope)`; refatorar `get_current_company_id` para tratar PLATFORM_OWNER (retorna `None`); **manter `require_admin` em paralelo** | 🟡 | Sem regressão se mantiver `require_admin` ativo. `require_action` deve ter fallback gracioso para `tenant_configs` ausente (Sprint 3 cria a tabela). |
| `POST /users/invite` (novo) + `POST /auth/activate` (novo, público) | 🟢 | Adição pura. `/auth/activate` **sem** `Depends(get_current_user)` (público). |
| `POST /users` (legado, aceita senha no body) | 🔴 | **Manter funcionando** durante este sprint. Adicionar header `Deprecation: true` na resposta + log de uso (`logger.warning("legacy_create_user_called", ...)`). Remover só no Sprint 3 se logs confirmarem zero chamadas. |
| Anti-escalonamento enforced em código: OWNER pode convidar qualquer role; ADMIN apenas OPERATOR/PROFESSIONAL; nenhum role eleva o próprio; OWNER não remove o último OWNER | 🟢 | Lógica nova em `users/service.py`. |
| Validação no `invite` + `assign_role` de papéis schema-only (PLATFORM_SUPPORT/BILLING/READONLY) → 422 | 🟢 | Adição pura. |
| Validação no `invite` + `assign_role` de PLATFORM_OWNER → 403 se actor não é PLATFORM_OWNER | 🟢 | Adição pura. |
| `PATCH /users/{id}/role`, `DELETE /users/{id}` (desativa), `GET /invitations`, `DELETE /invitations/{id}`, `POST /users/transfer-ownership` | 🟢 | Adição pura. Todos com `record_sensitive_action`. |
| `GET /audit/logs` (paginado) + `GET /audit/logs/export` (CSV via StreamingResponse, `record_sensitive_action(action="export_audit")` ANTES do stream) | 🟢 | Adição pura. |

### Sprint 3 — TenantConfig, módulos e branding

| Tarefa | Class. | Estratégia |
|--------|--------|-----------|
| Criar `tenant_configs` (todos os campos do brief; `accounting_mode` Enum default `CASH`; `permission_overrides` JSONB; `fee_routing_policy_id` FK nullable placeholder) + trigger `block_accrual_mode` | 🟢 | Adição pura. FK para `tenant_fee_routing_policies` permanece NULL até Sprint 6 (Fase 2). |
| Criar `module_activations` (UNIQUE `company_id, module_name`; enum com 10 módulos) | 🟢 | Adição pura. |
| Criar `tenant_brandings` (UNIQUE `company_id`) | 🟢 | Adição pura. |
| Criar `categories` (entity_type enum: SERVICE/PRODUCT/EXPENSE; UNIQUE `company_id, name, entity_type`) | 🟢 | Adição pura. |
| Hook em `companies/service.create_company`: inserir TenantConfig + 10 ModuleActivation + TenantBranding + 16 Category default (5 SERVICE + 4 PRODUCT + 7 EXPENSE) na **mesma transação** | 🟡 | Estendendo função existente. Test de integração obrigatório validando atomicidade. |
| Data migration idempotente (`ON CONFLICT (company_id) DO NOTHING`) para tenants existentes — roda no `alembic upgrade head` | 🔴 | Validar em staging com dump da produção primeiro. Confirmar contagens pós-migração: cada company com 1 tenant_config, 10 module_activations, 1 tenant_branding, 16 categories. |
| Endpoints `/tenant/config` (GET/PUT), `/tenant/modules` (GET, POST activate/deactivate), `/tenant/branding` (GET público, PUT), `/categories` (GET/POST/PATCH/DELETE) | 🟢 | Adição pura. PUT `/tenant/config` rejeita `accounting_mode=ACCRUAL` (redundante com trigger, fail-fast no service). |
| Validação Category `is_default=true`: bloquear `PATCH name/entity_type/sort_order` (→ 422); permitir `PATCH is_active`; `DELETE` bloqueado | 🟢 | Adição pura. |
| **Migrar 15 routers existentes de `require_admin` → `require_role("ADMIN")`** (refactor mecânico, comportamento idêntico) | 🟡 | Sem essa migração, RBAC granular do Sprint 2/3 só vale para endpoints novos. Endpoints atingidos: `appointments`, `auth/me`, `availability`, `booking`, `companies`, `company_profile`, `customers`, `products`, `professionals`, `public`, `schedule`, `services`, `uploads`, `users`, `whatsapp`. |
| Refinar `require_role("ADMIN")` → `require_action(action, scope)` em endpoints onde OPERATOR/PROFESSIONAL devem ter acesso parcial | 🟢 | Opcional — só onde fizer diferença real (ex: `/appointments` para PROFESSIONAL com scope OWN). |
| Remover `require_admin` de `core/deps.py` | 🟡 | Critério: `grep -r "require_admin" app/modules/` retorna 0 matches. |
| Remover `POST /users` legado | 🔴 | Verificar logs do Sprint 2 (header `Deprecation: true` logado a cada chamada). Se zero chamadas em 2 semanas → remover. Senão → reportar quem chama e estender prazo. **Confirmar também via grep no `painel/`.** |

### Sprint 4 — Sistema de eventos e workers com garantia de entrega

| Tarefa | Class. | Estratégia |
|--------|--------|-----------|
| Adicionar `celery[redis]`, `redis`, `kombu` ao `requirements.txt` | 🟢 | Adição pura. |
| Criar `app/infrastructure/celery_app.py` com config do brief (acks_late, reject_on_worker_lost, prefetch_multiplier=1) | 🟢 | Adição pura. |
| Criar `app/infrastructure/event_bus.py` com `DomainEvent` dataclass + `EventBus.register()` + `EventBus.publish()` | 🟢 | Adição pura. In-process no Estágio 0, **best-effort** — não usar para fluxos críticos. **FLUXOS CRÍTICOS → não passam pelo EventBus**: são enfileirados diretamente em Celery com retry, backoff, logs de falha e idempotência no handler. Garantia operacional via broker + retry + idempotência (não "entrega garantida" em absoluto — depende de broker, ack e idempotência). Críticos: `appointment.confirmed`, `appointment.cancelled`, `appointment.reminder_due`, `appointment.no_show` → Celery task direta. **FLUXOS TOLERANTES → EventBus in-process**, perda em crash do processo aceitável no Estágio 0: `booking_session.expired`; [Fase 4+] NPS, CRM classification. |
| Criar migration `processed_idempotency_keys`: `PRIMARY KEY (key, consumer)`; `company_id UUID` como **coluna de auditoria que NÃO participa da unicidade** (NULL para eventos de plataforma); índice em `processed_at` para cleanup. **Convenção obrigatória:** `idempotency_key` deve ser globalmente única por fato. Incluir `event_type` no prefixo é **obrigatório**. Formato: `"{event_type}:{uuid}[:{discriminador}]"`. | 🟢 | Adição pura. |
| Criar `app/core/idempotency.py` com `is_processed` e `mark_processed` (em transação atômica com o processamento do evento) | 🟢 | Adição pura. |
| Refactor `reminder_worker` → `@celery_app.task` com `max_retries=5`, `autoretry_for=(Exception,)`, `retry_backoff=True`, `retry_backoff_max=3600`, `retry_jitter=True`. Após max_retries: log ERROR + push para Redis list `dead_letter:{task_name}`. **Manter campos `reminder_24h_sent`/`reminder_2h_sent` como guardas de idempotência.** | 🔴 | **Coexistência → flip:** (1) Sprint 4 sobe Celery worker+beat em paralelo aos workers asyncio. (2) Validar 1 semana em staging com tráfego sintético. (3) Em produção: rodar ambos por 24h — flags idempotentes garantem zero duplicatas (quem chegar primeiro marca o flag). (4) Após 24h sem erros no Sentry: remover registros de workers do `lifespan` em `main.py:59-77`. **Rollback:** reativar `asyncio.create_task` no lifespan; Celery worker para de processar. |
| Refactor `session_cleanup_worker` → `@celery_app.task` com `max_retries=3`, retry backoff 5min. **Mantém escopo atual: apenas `bot_sessions`.** | 🔴 | Mesma estratégia coexistência → flip. Worker menos crítico (atraso na limpeza não afeta cliente final). |
| Remover `asyncio.create_task` do `lifespan` em `main.py` | 🔴 | **Última tarefa do Sprint 4.** Só executar após 24h de coexistência sem erros. |
| Criar `app/workers/beat_schedule.py` com 3 tasks: `reminder-check` (a cada 10min), `session-cleanup` (a cada 5min), `idempotency-key-cleanup` (diário às 03:00) | 🟢 | Adição pura. |
| Atualizar `docker-compose.yml` adicionando serviços `redis`, `celery_worker`, `celery_beat` | 🟡 | Apenas dev local. Railway: serviços adicionais configurados separadamente. |
| Handler `booking_session.expired` — Padrão A: `booking_session.expired:{booking_session_id}`. **Cobre `booking_sessions` (checkout web), não `bot_sessions`.** Disparador: task Celery Beat a cada 5min escaneia `SELECT id FROM booking_sessions WHERE expires_at < now() AND state NOT IN ('CONFIRMED','EXPIRED')` e publica 1 evento por sessão. Handler marca `EXPIRED` e libera reservas associadas. **Por que é tolerante sem outbox:** se o processo cair após publicar e antes do handler executar, o próximo scan republica o evento porque a sessão continua vencida e não-`EXPIRED` — idempotência vem do scan periódico, não da persistência do evento. | 🟢 | Adição pura. **Não confundir `bot_sessions` (escopo do `session_cleanup_worker`) com `booking_sessions` (escopo deste handler).** Se geração de código propor unificação, recusar. |
| Handler `appointment.reminder_due` — Padrão B: `appointment.reminder_due:{appointment_id}:{interval}` (interval ∈ {`24h`, `2h`}). Despacha para `CommunicationService` (criado no Sprint 5). | 🟡 | Coexistência durante a transição: handler publica o evento; até o Sprint 5 substituir, `reminder_worker` Celery ainda chama `evolution_client` direto. |

### Sprint 5 — Comunicação e credenciais

| Tarefa | Class. | Estratégia |
|--------|--------|-----------|
| ~~Adicionar `cryptography>=42.0` ao `requirements.txt`~~ | — | **Removido.** Já presente: `cryptography==46.0.7`. |
| Definir `CREDENTIAL_ENCRYPTION_KEY` em vault Railway (`Fernet.generate_key()`); backup em local seguro (perda = todas as credenciais inutilizáveis) | 🔴 | **Decisão de operações.** Validação obrigatória no startup: ausente → `KeyError: CREDENTIAL_ENCRYPTION_KEY ausente` (fail-fast). Nunca commitar no repositório. |
| Criar `app/core/encryption.py` com `encrypt_secret()`, `decrypt_secret()`, `make_masked_preview()` usando Fernet | 🟢 | Adição pura. `decrypt_secret` usado APENAS internamente em `test_connection` — nunca em resposta de API. |
| Criar migration `integration_credentials` (provider enum `WHATSAPP_EVOLUTION, WHATSAPP_META, SMTP, ASAAS`; label, secret_encrypted, masked_preview, config JSONB, status, audit fields) | 🟢 | Adição pura. **`SUPABASE_STORAGE` NÃO entra no enum** — é credencial de plataforma (env var), não de tenant. **`ASAAS` preparado aqui** para Sprint 8 (Fase 2) não exigir `ALTER TYPE`. |
| Criar migration `communication_settings` (UNIQUE `company_id`; whatsapp/email enabled flags; credential FKs; whatsapp_api_type enum; quiet_hours fields) | 🟢 | Adição pura. |
| Criar migration `communication_templates` (UNIQUE `company_id, event_type, channel, audience`) | 🟢 | Adição pura. |
| Criar migration `communication_logs` (status enum inclui `SCHEDULED`; campo `scheduled_send_at`) | 🟢 | Adição pura. |
| Criar `app/modules/communication/service.py` com `CommunicationService.dispatch()` (passos 1-7 do brief — settings → quiet_hours → template → consent skip → render → send → log) e `drain_scheduled()`. **Quiet hours — distinção por tipo de evento:** **Transacionais** (`appointment.confirmed`, `appointment.cancelled`) → **bypass quiet hours** (cliente acabou de agir; bloquear até 8h é experiência ruim) → status `SENT` imediato mesmo às 23h. **Automáticos** (`appointment.reminder_due`, `appointment.no_show`) → **respeitam quiet hours** → status `SCHEDULED` com `scheduled_send_at` no fim do período silencioso. | 🟢 | Adição pura. |
| Adicionar `communication-drain` ao `beat_schedule` (a cada 5min) | 🟢 | Adição pura. |
| Registrar handlers — **todos os 4 fluxos de appointment são críticos** (Celery task direta, **não EventBus**): `appointment.confirmed` (CLIENT + PROFESSIONAL — transacional, bypass quiet hours); `appointment.cancelled` (CLIENT — transacional, bypass quiet hours); `appointment.reminder_due` (CLIENT — automático, respeita quiet hours → SCHEDULED); `appointment.no_show` (PROFESSIONAL + OWNER — automático, respeita quiet hours → SCHEDULED). Idempotency key do reminder: `appointment.reminder_due:{appointment_id}:{interval}`. Payload: `{ interval: "24h" \| "2h" }`. O handler deriva o nome do template antes de buscar: `event_type_template = f"appointment.reminder_{payload['interval']}"` → `appointment.reminder_24h` ou `appointment.reminder_2h`. **Razão para no_show ser crítico:** notificação importante para profissional+owner; perda em crash do processo não é aceitável. **Tolerantes via EventBus no Estágio 0:** apenas `booking_session.expired` (Sprint 4); eventos novos virão na Fase 4+ (NPS, CRM classification). | 🟡 | **Cuidado:** `appointments/service.py` atualmente NÃO publica esses eventos — chama `send_booking_confirmation()` direto. Nesta tarefa: **disparar fluxo paralelo E manter chamada direta** (coexistência). Para **todos os 4 fluxos** (`appointment.confirmed`, `appointment.cancelled`, `appointment.reminder_due`, `appointment.no_show`): **enfileirar task Celery** (`send_appointment_communication.delay(...)`) — **não publicar via EventBus**. Remoção da chamada direta é tarefa separada (vira item de SPRINT-LOG ao fim do Sprint 5, não tarefa interna). **Templates mantêm nomes distintos** (`reminder_24h`, `reminder_2h`) — o **evento publicado é único** (`reminder_due`); a derivação do nome do template acontece dentro do handler antes do dispatch. |
| Seeds de templates default **+ `CommunicationSettings` default** no hook `create_company` (`whatsapp_enabled=False, email_enabled=False, quiet_hours_enabled=True, quiet_hours_start='22:00', quiet_hours_end='08:00'`) | 🟢 | Adição pura. Sem `CommunicationSettings`, `dispatch` falha no passo 1 (busca de settings). 7 templates obrigatórios (lista do brief): `appointment.confirmed` (CLIENT, PROFESSIONAL), `appointment.cancelled` (CLIENT), `appointment.reminder_24h` (CLIENT), `appointment.reminder_2h` (CLIENT), `appointment.no_show` (PROFESSIONAL, OWNER). |
| Data migration de templates + `CommunicationSettings` para tenants existentes (`ON CONFLICT (company_id) DO NOTHING`) | 🟢 | Idempotente. |
| Substituir chamadas a `evolution_client.send_text()` em `notifications.py` e handlers do bot por `CommunicationService.dispatch()` | 🔴 | **Estratégia gradual com feature flag por tenant.** (1) Adicionar `dispatch` ao lado da chamada direta. (2) Validar em staging que `CommunicationLog` é criado e mensagem chega. (3) Em produção: flag em `TenantConfig.permission_overrides["use_communication_service"] = true` (JSONB já existe desde Sprint 3 — sem nova migration). `notifications.py` consulta a flag e decide entre chamada direta (default `False`) ou `CommunicationService.dispatch`. (4) Após 1 semana ativo no cliente atual sem regressão: remover chamadas diretas + chave do JSONB. |
| **Migração `whatsapp_connection` → `integration_credentials`** | ✅ Decidido (Opção A) | **Não executar no Estágio 0.** `WHATSAPP_EVOLUTION` no enum `provider` permanece schema-only (sem registros, sem uso ativo). Bot continua lendo `EVOLUTION_API_URL`/`EVOLUTION_API_KEY` de `settings` global como hoje. Critério "whatsapp_connection migrada" do brief é considerado **não aplicável no Estágio 0** e não bloqueia conclusão do sprint. |
| Endpoints `/integrations/credentials` (POST/GET/POST rotate/POST revoke/POST test) — todos OWNER/ADMIN, `record_sensitive_action`, retornam `masked_preview` nunca `secret_encrypted` | 🟢 | Adição pura. |
| Endpoints `/communication/settings` (GET/PUT), `/communication/templates` (GET/POST/PUT/DELETE com regra `is_default=true` desativável mas não deletável; OPERATOR via `permission_overrides["OPERATOR"]["update_operational_templates"]` para templates não-default), `/communication/logs` (GET com filtros) | 🟢 | Adição pura. |

---

## Checklist de fechamento por sprint

Cada sprint só está concluído quando **todos os itens passam** + commit obrigatório de atualização do `CLAUDE.md`.

### Sprint 1

**Verificações de código:**
- [ ] `EXCLUDE CONSTRAINT no_overlap_per_professional` aplicada e testada (INSERT sobreposto via SQL direto retorna `ExclusionViolationError`)
- [ ] CANCELLED, FAILED e EXPIRED não ativam a constraint; **NO_SHOW e COMPLETED ativam** (slot historicamente ocupado — verificado por teste)
- [ ] `slowapi` configurado; `POST /auth/login` retorna 429 após 10 req/min/IP com header `Retry-After`
- [ ] Security headers presentes em toda resposta da API: sempre `X-Content-Type-Options: nosniff` e `X-Frame-Options: DENY`; `Strict-Transport-Security: max-age=31536000; includeSubDomains` **apenas quando `settings.PUBLIC_HTTPS=True`** (default `False`; verificar com `curl -I` em produção que o header aparece e em staging que NÃO aparece)
- [ ] `bcrypt__rounds=12` explícito em `app/core/security.py:7`
- [ ] 100% das URLs de upload em banco apontam para Supabase Storage (zero URLs com `/static/uploads/` em `professionals.image_url`, `services.image_url`, `products.image_url`, `company_profiles.{logo_url,cover_url,gallery_urls}`)
- [ ] `os.makedirs("static/uploads")` removido de `app/main.py`
- [ ] `app.mount("/static", ...)` removido de `app/main.py`
- [ ] `UPLOAD_DIR = Path("static/uploads")` removido de `app/modules/uploads/router.py`
- [ ] Script `scripts/rollback_uploads_to_volume.py` existe e foi testado em staging
- [ ] Diretório `/painel/painel/` removido (skeleton stranded)

**Validação em produção (não apenas testes):**
- [ ] Cliente atual consegue agendar via Link Público (fluxo completo)
- [ ] Cliente atual consegue agendar via Bot WhatsApp
- [ ] Upload de foto de profissional grava em Supabase e exibe corretamente
- [ ] Sentry sem novos erros nas 24h pós-deploy

**Atualização do `agendamento_engine/CLAUDE.md`:**
- [ ] Seção **Sprint atual** → "Sprint 2 em andamento"
- [ ] Seção **Stack e infraestrutura** → adicionar: `slowapi` ativo, rate limit 10 req/min em `/auth/login`; uploads em Supabase Storage (não mais volume local)
- [ ] Seção **Convenções críticas** → adicionar: `EXCLUDE CONSTRAINT` ativa com `btree_gist`; endpoint de upload retorna URL Supabase
- [ ] Seção **O que NÃO fazer** → adicionar: não reintroduzir `os.makedirs("static/uploads")`; não usar URLs de volume local

**Commit obrigatório:**
```
docs: atualiza CLAUDE.md pós-Sprint 1

- stack: slowapi, supabase storage, security headers
- remove referências a volume local de uploads
- sprint atual: 2
```

### Sprint 2

**Verificações de código:**
- [ ] `SELECT DISTINCT role FROM users` (pré-migration) retorna apenas `ADMIN`, `PROFESSIONAL`, `CLIENT`
- [ ] `User.role` é tipo `userrole` Enum com 9 valores (6 ativos + 3 schema-only)
- [ ] `User.company_id` é nullable; `get_current_company_id` trata `None` sem 500
- [ ] `POST /users/invite` e `POST /auth/activate` funcionando end-to-end
- [ ] `POST /users` (legado) marcado com `Deprecation: true` e logando uso
- [ ] `user_invitations` e `audit_logs` criados; `audit_logs` sem UPDATE/DELETE (testar via SQL direto)
- [ ] `require_role` e `require_action` disponíveis em `core/deps.py`; `require_admin` ainda presente (será removido no Sprint 3)
- [ ] Anti-escalonamento funcionando: ADMIN não promove a OWNER (403); ADMIN não revoga OWNER (403); último OWNER não removível (422)
- [ ] `POST /users/transfer-ownership` funcionando; audit gravado com `before_snapshot` e `after_snapshot`
- [ ] OWNER do tenant tentando convidar PLATFORM_OWNER → 403
- [ ] `POST /users/invite` com `role=PLATFORM_SUPPORT` (ou BILLING/READONLY) → 422
- [ ] `SensitiveAuditContext` gravado em `audit_logs` para `invite_user` e `assign_role`
- [ ] `record_sensitive_action` sem `reason` para `export_audit` → `ValueError`

**Validação em produção:**
- [ ] Login do ADMIN existente funciona normalmente
- [ ] `GET /auth/me` retorna `role=ADMIN` (string) — compat de contrato preservada
- [ ] Bot WhatsApp e Link Público continuam funcionando (não autenticam via JWT)
- [ ] `SELECT COUNT(*) FROM users` antes/depois da migration confere

**Atualização do `agendamento_engine/CLAUDE.md`:**
- [ ] Seção **Sprint atual** → "Sprint 3 em andamento"
- [ ] Seção **Stack e infraestrutura** → adicionar tabelas `user_invitations`, `audit_logs`
- [ ] Seção **Convenções críticas** → atualizar: `User.role` é Enum `userrole` (não String); `User.company_id` é nullable (PLATFORM_OWNER tem NULL); usar `require_role()` e `require_action()` em código novo — não mais `require_admin`
- [ ] Seção **Onde está o quê** → adicionar: `core/audit/sensitive_context.py`, `domain/enums/action_scope.py`, novos endpoints em `core/deps.py`
- [ ] Seção **O que NÃO fazer** → adicionar: `POST /users` legado está deprecado (será removido no Sprint 3); não criar endpoints novos com `require_admin`

**Atualização do `painel/CLAUDE.md`:**
- [ ] Seção **Convenções de frontend** → adicionar: criação de usuário via `POST /users/invite` + `POST /auth/activate`; `POST /users` legado removido no Sprint 3

**Commit obrigatório:**
```
docs: atualiza CLAUDE.md pós-Sprint 2

- role: User.role agora é Enum userrole
- deps: require_role/require_action substituem require_admin
- company_id: nullable para PLATFORM_OWNER
- sprint atual: 3
```

### Sprint 3

**Verificações de código:**
- [ ] Tabelas `tenant_configs`, `module_activations`, `tenant_brandings`, `categories` existem
- [ ] Trigger `block_accrual_mode` ativo (testar: UPDATE para `accounting_mode=ACCRUAL` falha)
- [ ] Backfill executado: cada company tem 1 tenant_config, 10 module_activations, 1 tenant_branding, 16 categories (5 SERVICE + 4 PRODUCT + 7 EXPENSE)
- [ ] Hook em `create_company` cria os 4 registros na mesma transação (teste de integração)
- [ ] `require_action` em `core/deps.py` lê `tenant_configs.permission_overrides` (fallback `{}` desligado para tenants existentes pós-backfill)
- [ ] 15 routers migrados: `grep -r "require_admin" app/modules/` retorna 0 matches
- [ ] `require_admin` removido de `core/deps.py`
- [ ] `POST /users` legado removido (logs do Sprint 2 confirmaram zero uso; grep no `painel/` confirmou que frontend não chama)
- [ ] Endpoints `/tenant/config`, `/tenant/modules`, `/tenant/branding`, `/categories` funcionando
- [ ] Category `is_default=true`: `DELETE` retorna 422; `PATCH name=...` retorna 422; `PATCH is_active=false` permitido
- [ ] `PUT /tenant/config` com `accounting_mode=ACCRUAL` → 422 (e trigger também rejeita)
- [ ] `PUT /tenant/config` grava audit com `before_snapshot`/`after_snapshot`

**Validação em produção:**
- [ ] Cliente atual recebeu seu TenantConfig + 10 ModuleActivation (todos inativos) + TenantBranding vazio + 16 categories no backfill
- [ ] `GET /tenant/branding` sem autenticação retorna dados públicos
- [ ] Bot e Link Público continuam funcionando (não consomem TenantConfig ainda)

**Atualização do `agendamento_engine/CLAUDE.md`:**
- [ ] Seção **Sprint atual** → "Sprint 4 em andamento"
- [ ] Seção **Stack e infraestrutura** → adicionar tabelas `tenant_configs`, `module_activations`, `tenant_brandings`, `categories`; onboarding cria 4 registros + 16 categories por company
- [ ] Seção **Convenções críticas** → atualizar: `require_admin` foi removido do codebase — não usar; `require_action` lê `permission_overrides` de `tenant_configs`; `accounting_mode=ACCRUAL` bloqueado por trigger no banco
- [ ] Seção **O que NÃO fazer** → adicionar: `POST /users` legado foi removido; `require_admin` não existe mais
- [ ] Seção **Decisões registradas** → adicionar: `ACCRUAL` bloqueado no Estágio 0 via trigger `block_accrual_mode`

**Atualização do `painel/CLAUDE.md`:**
- [ ] Seção **Rotas e componentes** → adicionar: rotas de `/tenant/config`, `/tenant/modules`, `/tenant/branding` (backend pronto, UI fica para Fase 3)

**Commit obrigatório:**
```
docs: atualiza CLAUDE.md pós-Sprint 3

- tabelas: tenant_configs, module_activations, brandings, categories
- require_admin: removido do codebase
- POST /users legado: removido
- sprint atual: 4
```

### Sprint 4

**Verificações de código:**
- [ ] `app/infrastructure/celery_app.py`, `app/infrastructure/event_bus.py`, `app/core/idempotency.py` criados
- [ ] Tabela `processed_idempotency_keys` criada com PK composta e índice em `processed_at`
- [ ] `reminder_worker` rodando via Celery Beat (não asyncio); retry 5x com backoff exponencial
- [ ] `session_cleanup_worker` rodando via Celery Beat (não asyncio); retry 3x; **cobre apenas `bot_sessions`**
- [ ] Handler `booking_session.expired` registrado; consumer `booking_session_cleanup`; **cobre apenas `booking_sessions`**
- [ ] Handler `appointment.reminder_due` registrado; Padrão B de idempotency key
- [ ] `asyncio.create_task` removido do `lifespan` em `main.py` (verificar via grep)
- [ ] 24h de coexistência sem duplicatas de lembrete nem erros no Sentry **antes** da remoção do asyncio
- [ ] `docker-compose.yml` atualizado com `redis`, `celery_worker`, `celery_beat`
- [ ] **Nenhum handler registrado como `agenda.soft_reservation.expired`** (modelo Reservation não existe; nome errado)

**Validação em produção:**
- [ ] Pelo menos 1 lembrete de 24h entregue via Celery, com `reminder_24h_sent=true` setado pós-entrega
- [ ] Pelo menos 1 lembrete de 2h entregue via Celery, com `reminder_2h_sent=true` setado pós-entrega
- [ ] `bot_sessions` expiradas continuam sendo limpas
- [ ] `booking_sessions` expiradas marcadas como `EXPIRED` via handler; slot volta a aparecer disponível no Link Público

**Atualização do `agendamento_engine/CLAUDE.md`:**
- [ ] Seção **Sprint atual** → "Sprint 5 em andamento"
- [ ] Seção **Stack e infraestrutura** → atualizar: Workers agora são Celery + Redis (não asyncio); `asyncio.create_task` foi removido de `main.py`; EventBus ativo em `infrastructure/event_bus.py`; idempotência via `processed_idempotency_keys`
- [ ] Seção **Onde está o quê** → adicionar: `infrastructure/celery_app.py`, `infrastructure/event_bus.py`, `core/idempotency.py`, `workers/beat_schedule.py`
- [ ] Seção **O que NÃO fazer** → adicionar: não adicionar workers via `asyncio.create_task` no lifespan — usar Celery Beat; não publicar eventos sem `idempotency_key`; não usar nome `agenda.soft_reservation.expired` (modelo só vem na Fase 3)
- [ ] Seção **Convenções críticas** → adicionar: `bot_sessions` e `booking_sessions` são domínios separados — `session_cleanup_worker` cobre apenas `bot_sessions`; handler `booking_session.expired` cobre apenas `booking_sessions`

**Commit obrigatório:**
```
docs: atualiza CLAUDE.md pós-Sprint 4

- workers: asyncio → Celery+Redis
- event_bus e idempotency ativos
- bot_sessions vs booking_sessions: divisão fechada
- sprint atual: 5
```

### Sprint 5

**Verificações de código:**
- [ ] `CREDENTIAL_ENCRYPTION_KEY` em vault Railway; startup falha com erro claro se ausente
- [ ] `app/core/encryption.py` criado com `encrypt_secret`, `decrypt_secret`, `make_masked_preview`
- [ ] Round-trip: `decrypt_secret(encrypt_secret("abc")) == "abc"`
- [ ] `make_masked_preview("abcdef1234")` retorna `"***•••1234"`
- [ ] Tabelas `integration_credentials`, `communication_settings`, `communication_templates`, `communication_logs` criadas
- [ ] `CommunicationService.dispatch` funcionando: SKIPPED_CHANNEL_DISABLED, SKIPPED_QUIET_HOURS (não-lembrete), SCHEDULED (lembrete em quiet), SKIPPED_NO_TEMPLATE, SENT
- [ ] `drain_scheduled` processa logs `SCHEDULED` após fim do quiet_hours
- [ ] Seeds de templates default + `CommunicationSettings` no `create_company`; data migration aplicada para tenants existentes
- [ ] `notifications.py` consulta `TenantConfig.permission_overrides["use_communication_service"]` antes de chamar `evolution_client.send_text` ou `CommunicationService.dispatch`
- [ ] `GET /integrations/credentials` nunca retorna `secret_encrypted`; sempre retorna `masked_preview` + `config`
- [ ] `POST /integrations/credentials/{id}/test` grava `record_sensitive_action(action="test_connection")`
- [ ] Template `is_default=true`: `DELETE` bloqueado (422)
- [ ] OPERATOR com `permission_overrides["OPERATOR"]["update_operational_templates"]=true` → `PUT /communication/templates/{id}` permitido para template não-default
- [ ] **`WHATSAPP_EVOLUTION` em `integration_credentials.provider` é schema-only** (sem registros criados; bot ainda lê `EVOLUTION_API_URL`/`KEY` de `settings`)

**Validação em produção:**
- [ ] Pelo menos 1 lembrete de 24h real entregue via `CommunicationService.dispatch` (após flag ativada para cliente atual); `CommunicationLog` com status `SENT`
- [ ] Pelo menos 1 confirmação de agendamento real entregue via `CommunicationService`; log visível em `GET /communication/logs`
- [ ] Bot WhatsApp continua funcionando (lendo de `settings` global)
- [ ] Simulação às 23h: `appointment.reminder_due` (interval=`2h`) → `CommunicationLog SCHEDULED` com `scheduled_send_at = próximo dia 08:00` (automático respeita quiet hours)
- [ ] Simulação às 23h: `appointment.confirmed` → `CommunicationLog SENT` imediato (transacional **bypass** quiet hours)

**Atualização do `agendamento_engine/CLAUDE.md`:**
- [ ] Seção **Sprint atual** → "Fase 1 concluída · aguardando Fase 2"
- [ ] Seção **Stack e infraestrutura** → adicionar `CommunicationService` ativo; tabelas de credenciais e comunicação criadas; `Fernet` via `core/encryption.py`
- [ ] Seção **Onde está o quê** → adicionar `core/encryption.py`, `modules/communication/`
- [ ] Seção **Convenções críticas** → adicionar: credenciais de integração armazenadas criptografadas via Fernet — nunca em plaintext no banco; toda mensagem ao cliente passa por `CommunicationService.dispatch` — não chamar `evolution_client` diretamente em código novo
- [ ] Seção **O que NÃO fazer** → adicionar: não chamar `evolution_client.send_text()` diretamente; não criar `integration_credentials` com `provider=WHATSAPP_EVOLUTION` no Estágio 0
- [ ] Seção **Decisões registradas** → confirmar: Evolution API permanece global no Estágio 0 (Opção A); critério "whatsapp_connection migrada" do brief não-aplicável

**Commit obrigatório:**
```
docs: atualiza CLAUDE.md pós-Sprint 5

- CommunicationService ativo; flag por tenant em TenantConfig.permission_overrides
- credenciais: Fernet encryption obrigatória
- WHATSAPP_EVOLUTION em integration_credentials é schema-only
- Fase 1 concluída
```

---

## Estado base dos CLAUDE.md (entrada na Fase 1)

Corrigido com a varredura real de 2026-05-25.

### `agendamento_engine/CLAUDE.md`

```markdown
# agendamento_engine — contexto operacional

**Sprint atual:** Sprint 1 em andamento (Fase 1 — Fundação técnica)
**Produto em produção:** SIM — Bot WhatsApp (13 handlers FSM), BookingEngine, Link Público.
**Regra:** não alterar BookingEngine, bot ou Link Público nesta fase, salvo o que o brief permite explicitamente.

---

## Stack e infraestrutura

- FastAPI 0.115 · SQLAlchemy 2.0 · Alembic
- PostgreSQL via Supabase (us-west-2)
- Auth: JWT + bcrypt (`passlib==1.7.4` + `bcrypt==4.0.1`, rounds=12 — default da biblioteca; a fixar explicitamente no Sprint 1)
- Workers: asyncio loop em `app/main.py:lifespan` (`reminder_worker` + `session_cleanup_worker`)
  → migrando para Celery+Redis no Sprint 4
- Observabilidade: Sentry + structlog + `RequestContextMiddleware`
- Uploads: volume Docker local `/app/static/uploads`
  → migrando para Supabase Storage no Sprint 1
- Multi-tenant: `company_id` obrigatório em toda query (442 ocorrências em 50 arquivos — padrão rígido)
- CORS: restrito via `ALLOWED_ORIGINS` em `.env` (sem wildcard)
- Migrations: `migrations/versions/` (HEAD: `f1e2d3c4b5a6`, 18 migrations) — paths em `alembic.ini` apontam para `%(here)s/migrations`
- `cryptography==46.0.7` já presente no `requirements.txt` (Sprint 5 não precisa adicionar)

## Convenções críticas

- Campos de horário em `appointments`: `start_at` / `end_at` — NUNCA `start_time`/`end_time`
- `User.role`: `String(20)` com valores `ADMIN`, `PROFESSIONAL`, `CLIENT` → vira Enum `userrole` (9 valores) no Sprint 2
- `User.company_id`: `NOT NULL` → vira `nullable=True` no Sprint 2 (PLATFORM_OWNER terá NULL)
- Auth: `require_admin` em `core/deps.py:43` — binário (admin/não-admin) → substituído no Sprint 2/3 por `require_role` e `require_action`
- Todo Movement nasce via evento no FinancialCoreEngine (Fase 2) — engines não criam Movement diretamente
- Estados terminais (`COMPLETED`, `CANCELLED`, `NO_SHOW`, `EXPIRED`, `FAILED`) são imutáveis
- `company_id` em toda query sem exceção — vazar `company_id` é bug crítico de segurança
- Localização real dos modelos: `app/infrastructure/db/models/` (estrutura DDD; NÃO usar `app/models/`)
- **Repository Pattern não adotado** — queries via `db.query()` direto nos services. `app/infrastructure/repositories/` é placeholder vazio (apenas `__init__.py`); não criar repositórios novos sem decisão arquitetural explícita.
- **`idempotency_key` tem dois domínios distintos** — não confundir em código, testes ou migrações: `Appointment.idempotency_key` (constraint `uq_idempotency` por `company_id+key`) **evita duplo-INSERT do mesmo agendamento** (enviado pelo cliente no request body); `processed_idempotency_keys.key` (Sprint 4) **evita dupla execução de consumer de evento** (infraestrutura). Tabelas distintas, propósitos distintos.

## Onde está o quê

- FSM do bot WhatsApp: `app/modules/whatsapp/` (13 handlers em `handlers/`)
- BookingEngine FSM: `app/modules/booking/engine.py`
- Auth + deps: `app/core/security.py`, `app/core/deps.py`
- Migrations: `migrations/versions/` (HEAD: `f1e2d3c4b5a6`)
- Workers: `app/workers/reminder_worker.py`, `app/workers/session_cleanup_worker.py`
- Settings: `app/core/config.py` (inclui `EVOLUTION_API_URL` e `EVOLUTION_API_KEY` globais)
- Uploads: `app/modules/uploads/router.py` (`UPLOAD_DIR = Path("static/uploads")` — será refatorado no Sprint 1)
- Static mount: `app/main.py:113-114` (`os.makedirs` + `app.mount("/static", ...)` — será removido no Sprint 1)
- Models (`app/infrastructure/db/models/`): appointment, availability_slot, booking_session, bot_session, company, company_profile, company_settings, customer, product, professional, service, user, web_booking_session, whatsapp_connection

## O que NÃO fazer (Estágio 0)

- Não implementar: locations/unidades, app mobile, API pública, multi-estoque UI, bot tenant, `accounting_mode=ACCRUAL`, NFS-e
- Não ativar PLATFORM_SUPPORT / PLATFORM_BILLING / PLATFORM_READONLY (schema-only)
- Não integrar com Mercado Pago — provider é Asaas
- Não criar endpoints novos sem filtro `company_id`
- Não modificar BookingEngine, bot WhatsApp ou Link Público sem aprovação explícita
- Não usar `app/models/` — modelos vivem em `app/infrastructure/db/models/`
- Não criar migrations em `alembic/versions/` — usar `migrations/versions/`

## Decisões registradas

- **`whatsapp_connection → integration_credentials`:** NÃO executar no Estágio 0. Evolution API permanece global (`EVOLUTION_API_URL`/`KEY` em `settings`). `WHATSAPP_EVOLUTION` no enum `integration_credentials.provider` é schema-only. Modelo `whatsapp_connection` real **não tem** `token` nem `server_url` — apenas gerencia `instance_name` por tenant na Evolution API compartilhada.
- **Pagamentos:** Asaas (split nativo, subcontas sem KYC separado). Mercado Pago descartado.
- **`PLATFORM_OWNER`:** `role=PLATFORM_OWNER` + `company_id=NULL`. Criado via script de seed. `OWNER` (sem prefixo) = dono de UM tenant. São papéis distintos no enum — não confundir.
- **Verificação prévia de overlaps em `appointments`:** ✅ executada em 2026-05-22, 0 linhas retornadas. `EXCLUDE CONSTRAINT` pode ser aplicada sem remediação prévia.
- **`cryptography==46.0.7`:** já presente; Sprint 5 não adiciona a biblioteca, apenas implementa `app/core/encryption.py` com Fernet.
```

### `painel/CLAUDE.md`

```markdown
# painel — contexto operacional

**Sprint atual:** Sprint 1 em andamento (Fase 1 — Fundação técnica)
**Foco do frontend nesta fase:** apenas ajustes mínimos. Mudanças de UI (RBAC visível, dashboards role-aware) são Fase 3.

---

## Stack

- Next.js 16.2.2 · React 19.2.4 · TailwindCSS v4 (`tailwindcss: ^4`)
- `shadcn: ^4.2.0` como dependência direta (componentes em `components/ui/`)
- `@base-ui/react: ^1.3.0`, `class-variance-authority`, `clsx`, `lucide-react`, `tailwind-merge`, `tw-animate-css`
- App Router (estrutura `app/`)
- API-first: zero lógica de negócio no frontend
- Sem SSR de dados sensíveis — chamadas à API sempre autenticadas via JWT

## Convenções de frontend

- Identidade visual por tenant via design tokens (logo, cores, fonte, favicon)
- Estrutura da UI é única; aparência muda por tokens — não criar layouts paralelos por tenant
- Sidebar: sem filtro por role na Fase 1 → RBAC visível no frontend é Fase 3 (fora do escopo desta fase)
- Imports de `lib/api.ts` sempre — nunca `fetch` raw
- Formatação monetária: `formatBRL()` de `lib/utils.ts`
- Formatação de data: `formatDateTime()` de `lib/utils.ts` com `timeZone` explícito

## Rotas e áreas existentes (entrada Fase 1)

8 áreas em `app/(dashboard)/`: appointments · customers · dashboard · integrations · products · professionals · services · settings (apenas `settings/profile/`)

Link Público em `app/book/[slug]/`:
- `page.tsx` — landing + vitrine
- `BookingFlow.tsx` — FSM do checkout

Login em `app/page.tsx`.

## O que NÃO fazer

- Não criar lógica de negócio no frontend (validação de disponibilidade, cálculo financeiro, etc.)
- Não usar o protótipo `barberflow-system` como spec de comportamento (referência visual apenas)
- Não criar layouts distintos por tenant — tokens visuais, não layouts paralelos
- `POST /users` com senha no body está deprecado a partir do Sprint 2 — usar `POST /users/invite` + `POST /auth/activate`
- Não criar UI nova para módulos da Fase 1 (foco é backend)
```

---

## Riscos principais e mitigações

| # | Risco | Mitigação |
|---|-------|-----------|
| 1 | Migration EXCLUDE CONSTRAINT falha em produção por overlap histórico | ✅ Mitigado — query executada em 2026-05-22, 0 linhas. |
| 2 | Frontend chamando `POST /users` legado com senha no body | Expand-contract: manter endpoint deprecated por 1 sprint, log de uso, grep no `painel/`. |
| 3 | Workers asyncio + Celery em paralelo enviando lembretes duplicados | Flags idempotentes `reminder_24h_sent`/`reminder_2h_sent` já protegem — quem chegar primeiro marca o flag e o outro vê `True` e pula. |
| 4 | Migração de URLs de upload em produção (Sprint 1) | Dual-write durante transição + script de rollback testado em staging antes do go-live. **2 arquivos a refatorar:** `main.py` + `uploads/router.py`. |
| 5 | `CREDENTIAL_ENCRYPTION_KEY` perdida = todas as credenciais inutilizáveis (Sprint 5) | Backup em vault separado; rotação documentada; sem chave no repositório. Startup falha-fast se ausente. |
| 6 | `app/modules/uploads/router.py` esquecido na refatoração de Sprint 1 | Adicionado explicitamente ao checklist. Verificação: `grep -rE "static/uploads|UPLOAD_DIR" app/` deve retornar 0 matches ao final do sprint. |
| 7 | Geração de código tenta criar handler `agenda.soft_reservation.expired` (modelo não existe) | Documentado em todos os checklists e no `O que NÃO fazer` do CLAUDE.md. Verificação no Sprint 4: nenhum handler com esse nome registrado. |
| 8 | Geração de código tenta unificar `bot_sessions` com `booking_sessions` (domínios distintos) | Documentado explicitamente em `Convenções críticas` do CLAUDE.md (pós-Sprint 4). Se proposto, recusar. |

---

## Notas para fases seguintes

Reproduzido do brief sem alteração:

- **Fase 2 / Sprint 6:** criar `TenantFeeRoutingPolicy` (modelo próprio do Financial Core) e atualizar FK `tenant_configs.fee_routing_policy_id`.

- **Fase 2 — prefixo de eventos do Financial Core:** padronizado como `financial_core.*` (nunca `financial.*` sem `_core`). Eventos canônicos: `financial_core.movement_created`, `financial_core.entry_created`, `financial_core.transfer_completed`, `financial_core.manual_adjustment_created`, `financial_core.reconciliation_opened/closed`. Prefixo fixado antes da Fase 2 para evitar cascata de renomeação em handlers, testes e logs.

- **Fase 2 / Sprint 7:** adicionar `ExternalStatementEntry` + endpoint `import_statement` + eventos: `statement.imported`, `reconciliation.matched`, `reconciliation.orphan_flagged`, `reconciliation.orphan_dismissed`.

- **Fase 3 / Sprint 10:** registrar handler `agenda.soft_reservation.expired` quando modelo `Reservation` (SOFT/FIRME) for criado.

- **Fase 5 / Sprint 17:** adicionar `SupplierCredit` (modelo + service + 4 eventos); corrigir `Payable.payment_terms` para enum completo: `CASH | CREDIT | INSTALLMENTS | CONSIGNMENT | ADVANCE` (`CONSIGNMENT` e `ADVANCE`: `[SCHEMA APENAS]` no Estágio 0).

---

## Apêndice — Últimas migrations conhecidas

HEAD atual (em `migrations/versions/`): `f1e2d3c4b5a6_fix_customers_phone_unique_constraint.py`

Últimas migrations alfabeticamente (a ordem temporal pode diferir; verificar via `alembic history` antes de aplicar nova):

```
c7b2f4e91a30_align_users_table.py
c9f2e7a14b38_remove_availability_slots_table.py
d1a4f7b92c06_add_sprint4_service_customer_columns.py
d8e3c2b51f70_align_remaining_tables.py
e1f4a2b3c9d7_add_reminder_flags_to_appointments.py
e3c8b5d91a47_create_products_table.py
e3c9a1d84f17_add_company_profiles.py
f1e2d3c4b5a6_fix_customers_phone_unique_constraint.py   ← HEAD
f3a9e1d72b04_sprint1_schema_alignment.py
f5g6h7i8j9k0_create_web_booking_sessions.py
```

Total: 18 migrations (confirmado em sessão anterior).

---

*Plano gerado a partir de varredura real do código em 2026-05-25. Qualquer ambiguidade durante execução deve aparecer como ⛔ aqui — nunca ser resolvida por suposição.*
