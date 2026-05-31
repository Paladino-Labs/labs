**Fase 2 concluída.** Sprint atual: Sprint 11 em andamento (Fase 3 — Catálogo opt-ins)

## Operations FSM + Agenda granular (Sprint 10 concluído)
- Reservation SOFT/FIRME: EXCLUDE tstzrange WHERE status='ACTIVE'
- promote_to_firme: PROMOTED + db.flush() + INSERT FIRME (atômico)
- expire_soft_reservation: Celery (crítico); handler idempotente registrado
- Celery Beat: expire_soft_reservations_scan (*/5 min)
- ScheduleException: SUBSTITUTIVE | ADDITIVE por data
- DirectOccupancy com overbooking auditado
- Appointment: DRAFT, FAILED, operation_type

**HEAD migration:** c2d3e4f5g6h7 (add_direct_occupancies)
**Total migrations Fase 2:** 19 (k1→c2)
**Total testes:** 142/142 (+ 2 skips PostgreSQL real)

## PaymentsEngine (Sprint 9 concluído)
- Payment FSM: PENDING → CONFIRMED → REFUNDED
- confirm() atômico (5 passos na mesma transação; ver brief v2)
- Idempotência: ProcessedIdempotencyKey + UNIQUE no banco
- payment.confirmed → CommunicationService via EventBus (best-effort, fora da tx)
- handle_payment_refunded em FinancialCoreEngine
- Payment.provider imutável (trigger banco + @validates)
- DepositPolicy por serviço ou global

**HEAD migration:** y1z2a3b4c5d6 (add_deposit_policies)

## Transfer + Reconciliação + CashCount (Sprint 7 concluído)
- Transfer: 2 Movements atômicos; sem Entry
- Movement permanece 100% append-only; reconciliação via movement_reconciliations
- CashCount ADJUSTED: create_manual_adjustment + entry_id vinculado
- notes obrigatório quando discrepancy != 0

**HEAD migration:** s1t2u3v4w5x6 (add_cash_counts)

## Financial Core — fundação (Sprint 6 concluído)
- TenantFeeRoutingPolicy: lookup por (company_id, fee_source); sem FK em tenant_configs
- Account, Movement (append-only), Entry (append-only)
- FinancialCoreEngine: handle_payment_confirmed, create_manual_adjustment, queries
- Hook create_company: Account CAIXA + 7 TenantFeeRoutingPolicies (mesma transação)
- Triggers de imutabilidade no banco + @validates ORM
- 2 testes de trigger pendentes de validação em staging (PostgreSQL real)

**HEAD migration:** o1p2q3r4s5t6 (add_entries_with_immutability_trigger)

## Stack e infraestrutura

- FastAPI 0.115 · SQLAlchemy 2.0 · Alembic
- slowapi ativo — rate limit 10 req/min/IP em POST /auth/login (X-Forwarded-For)
- Uploads: Supabase Storage (dual-write ativo; migração de URLs executada)
- EXCLUDE CONSTRAINT ativa em appointments (btree_gist + tsrange, company_id + professional_id)
- Tabelas criadas: `user_invitations`, `audit_logs` (append-only via triggers no banco)
- Tabelas: `tenant_configs`, `module_activations`, `tenant_brandings`, `categories`
- Onboarding: `create_company` cria TenantConfig + 10 ModuleActivations +
  TenantBranding + 16 categories default na mesma transação
- Workers: Celery + Redis em coexistência com asyncio
  → flip definitivo (remover asyncio.create_task) após 24h sem erros em produção
- EventBus ativo em `app/infrastructure/event_bus.py` (best-effort, fluxos tolerantes)
- Idempotência: `processed_idempotency_keys` (PK composta key+consumer; company_id como auditoria)
- Beat: worker usa `-A app.infrastructure.celery_app:celery_app`
       beat usa `-A app.workers.celery_beat_entrypoint:celery_app` (evita import circular)
- CommunicationService ativo em `modules/communication/service.py`
- Tabelas: integration_credentials, communication_settings,
  communication_templates, communication_logs
- Fernet encryption via `core/encryption.py`
  (CREDENTIAL_ENCRYPTION_KEY obrigatório em produção; ausente → KeyError no startup)
- Feature flag: `TenantConfig.permission_overrides["use_communication_service"]`
  ativa o dispatch (default False — coexistência com evolution_client durante rollout)
- RLS ativo em 26 tabelas (políticas por tenant_isolation; superuser bypassa automaticamente)
- `core/db_rls.py` — set_rls_context() chamado em get_db() e workers Celery
- Workers: company_id=None para scans multi-tenant (bypass); específico para tasks por tenant

## Convenções críticas

- EXCLUDE CONSTRAINT no_overlap_per_professional: filtro WHERE status NOT IN
  ('CANCELLED','FAILED','EXPIRED') — NO_SHOW e COMPLETED ativam a constraint
- Upload: endpoint retorna URL Supabase; gravação local foi removida
- `User.role`: Enum `userrole` com 9 valores — OWNER|ADMIN|OPERATOR|PROFESSIONAL|CLIENT|PLATFORM_OWNER
  ativos; PLATFORM_SUPPORT|PLATFORM_BILLING|PLATFORM_READONLY schema-only (Estágio 1+)
- `User.company_id`: nullable — PLATFORM_OWNER tem NULL; demais têm company_id preenchido
- Auth: `require_role()` e `require_action()` — `require_admin` removido do codebase
- `require_action` lê `permission_overrides` de `tenant_configs` (fallback `{}` gracioso)
- `is_admin` property: `role in ("ADMIN", "OWNER", "PLATFORM_OWNER")`
- `accounting_mode=ACCRUAL` bloqueado por trigger `block_accrual_mode` no banco
- `fee_routing_policy_id` em `tenant_configs`: UUID sem FK (tabela criada na Fase 2 Sprint 6)
- Category `is_default=true`: desativável, não deletável, name/entity_type/sort_order imutáveis
- `GET /tenant/branding`: público — usa `company_id` como query param (sem auth)
- Invitations em `/users/invitations` (não `/invitations` independente)
- bot_sessions e booking_sessions são domínios separados:
    session_cleanup_worker → bot_sessions apenas
    handler booking_session.expired → booking_sessions apenas
- Fluxos críticos não passam pelo EventBus — Celery task direta:
    appointment.confirmed, appointment.cancelled, appointment.reminder_due, appointment.no_show
- idempotency_key dois domínios distintos:
    Appointment.idempotency_key → evita duplo-INSERT de agendamento (cliente envia)
    processed_idempotency_keys.key → evita dupla execução de consumer (infra)
- Credenciais armazenadas criptografadas via Fernet — nunca plaintext no banco
- `secret_encrypted` nunca retornado em respostas de API — apenas `masked_preview` + `config`
- Quiet hours: transacionais (appointment.confirmed, appointment.cancelled) → bypass → SENT;
  automáticos (appointment.reminder_due, appointment.no_show) → respeita → SCHEDULED
- Senha de usuário: mínimo 8 chars + 1 maiúscula + 1 número (validado no backend)
- Token de reset: 6 dígitos numéricos, TTL 15min, invalidado imediatamente após uso
- forgot_password requer template "auth.password_reset_requested" cadastrado no tenant

## Onde está o quê

- `core/audit/sensitive_context.py` — `SensitiveAuditContext`, `record_sensitive_action`, `REASON_REQUIRED`
- `domain/enums/action_scope.py` — `ActionScope` enum (re-export)
- `infrastructure/db/models/user_invitation.py`
- `infrastructure/db/models/audit_log.py`
- `modules/audit/router.py` — `GET /audit/logs`, `GET /audit/logs/export`
- `modules/auth/activate_service.py` — ativação de convite por token
- `modules/tenant/` — /tenant/config, /tenant/modules, /tenant/branding
- `modules/categories/` — /categories
- `infrastructure/db/models/{tenant_config,module_activation,tenant_branding,category}.py`
- `infrastructure/celery_app.py` — configuração Celery
- `infrastructure/event_bus.py` — EventBus (tolerantes)
- `core/idempotency.py` — is_processed, mark_processed
- `workers/beat_schedule.py` — reminder/10min, session-cleanup/5min,
    idempotency-cleanup/03:00, booking-session-scan/5min
- `workers/celery_beat_entrypoint.py` — entrypoint exclusivo do beat
- `workers/booking_session_worker.py` + `booking_session_handlers.py`
- `workers/appointment_reminder_handler.py` — stub, Sprint 5 substitui
- `workers/idempotency_cleanup.py`
- `core/encryption.py` — encrypt_secret, decrypt_secret, make_masked_preview
- `modules/communication/` — CommunicationService, routers /communication/*
- `modules/integrations/` — IntegrationCredential service, routers /integrations/credentials/*
- `workers/communication_worker.py` — Celery tasks para fluxos críticos de appointment
- `infrastructure/db/models/{integration_credential,communication_setting,
  communication_template,communication_log}.py`
- `infrastructure/db/models/password_reset_token.py`
- `modules/auth/router.py` — adicionados: POST /auth/forgot-password,
  POST /auth/reset-password, POST /auth/change-password

## O que NÃO fazer

- Não reintroduzir os.makedirs("static/uploads") — removido de main.py
- Não usar URLs de volume local (/static/uploads/) — fonte de verdade é Supabase Storage
- `POST /users` legado foi removido
- Não criar endpoints novos com `require_admin` — usar `require_role()` ou `require_action()`
- `require_admin` não existe mais — não referenciar
- Não criar `TenantFeeRoutingPolicy` — pertence ao Financial Core (Fase 2, Sprint 6)
- Não implementar `accounting_mode=ACCRUAL` — bloqueado por trigger no Estágio 0
- Não adicionar workers via asyncio.create_task no lifespan — usar Celery Beat
- Não publicar eventos sem idempotency_key
- asyncio.create_task ainda ATIVO no lifespan (coexistência) — remover somente
  após 24h sem erros em produção; atualizar CLAUDE.md após o flip
- Não chamar `evolution_client.send_text()` diretamente em código novo
  → usar CommunicationService.dispatch após remoção das chamadas diretas
- Não criar `integration_credentials` com `provider=WHATSAPP_EVOLUTION` no Estágio 0
- `CREDENTIAL_ENCRYPTION_KEY` nunca commitar no repositório — vault Railway apenas
- Não fazer queries fora de get_db() (HTTP) ou celery_db_session() (workers) — RLS context não será setado
- Não modificar migrations existentes para SET LOCAL row_security = off
  — superuser no Supabase bypassa automaticamente
- Não enviar ação SELECT_SHIFT pelo FSM — AWAITING_SHIFT foi removido
  do fluxo principal. O endpoint stateless GET /booking/{slug}/slots?shift=
  ainda funciona; apenas o step do FSM foi eliminado.

## Decisões registradas

- `ACCRUAL` bloqueado no Estágio 0 via trigger `block_accrual_mode` em `tenant_configs`
- Evolution API permanece global no Estágio 0 (Opção A — confirmada no Sprint 5):
  WHATSAPP_EVOLUTION no enum provider é schema-only; migração whatsapp_connection
  não aplicável no Estágio 0

## Bugs conhecidos / corrigidos

- [CORRIGIDO] Timezone na geração de slots: working_hours eram tratados
  como UTC em vez de horário local do tenant.
  Fix em availability/service.py + appointments/service.py.
  Usa TenantConfig.timezone como fonte canônica com fallback
  "America/Sao_Paulo". Requer tzdata==2026.2 (adicionado ao requirements).

## Segurança

- JWT agora inclui `iat` (issued at) em todos os tokens
- Troca de senha invalida tokens emitidos antes dela via `last_password_change_at`
  em User — tokens sem `iat` (pré-deploy) são aceitos por backward compat
- change_password e reset_password atualizam last_password_change_at