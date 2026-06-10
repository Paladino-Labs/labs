**Fase 2 concluída.** Sprint 12 concluído (2026-06-07 — CommissionEngine). Próximo: Sprint 13.

## Canal EMAIL — CommunicationService (Sprint 11)
- `_send_email()` em `modules/communication/service.py` via smtplib nativo (síncrono)
- `dispatch()` tenta EMAIL primeiro (se email_enabled=True), fallback WHATSAPP
  Usa `is True` para checar bool (seguro com MagicMock nos testes)
- Credencial SMTP: IntegrationCredential provider=SMTP (decrypt_secret para senha);
  config JSONB: {"host", "port", "from_email", "use_tls"} — fallback para SMTP_* de settings
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL, SMTP_USE_TLS em config.py
- Template auth.password_reset_requested channel=EMAIL audience=CLIENT adicionado em _DEFAULT_TEMPLATES
- forgot_password(): recipient_type="CLIENT", context inclui recipient_email + token
- recipient_email obrigatório no context para envio EMAIL
- Testes: tests/test_smtp_email.py (14 testes — todos passando)

## Operations FSM + Agenda granular (Sprint 10 concluído)
- Reservation SOFT/FIRME: EXCLUDE tstzrange WHERE status='ACTIVE'
- promote_to_firme: PROMOTED + db.flush() + INSERT FIRME (atômico)
- expire_soft_reservation: Celery (crítico); handler idempotente registrado
- Celery Beat: expire_soft_reservations_scan (*/5 min)
- ScheduleException: SUBSTITUTIVE | ADDITIVE por data
- DirectOccupancy com overbooking auditado
- Appointment: DRAFT, FAILED, operation_type

**HEAD migration:** l4m5n6o7p8q9 (expand_fee_sources_bandeiras)
**Total migrations Fase 2 + alinhamento + Sprint Integrações + pré-req frontend + Ajuste 9 + correções:** 27 (k1→d1→e1→psg→f2→g3→h2→i3→j2)
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

## Sprint de Integrações (pós-Fase 2)

### Email / CommunicationService
- Canal EMAIL em `dispatch()` via Mailtrap HTTP API (fallback: smtplib se SMTP_HOST configurado)
- `_send_email()` em `modules/communication/service.py`
- `forgot_password()` e `send_invite()` passam `recipient_email` no context
- MAILTRAP_API_TOKEN + MAILTRAP_SANDBOX_INBOX_ID em config.py
- Nota: Railway bloqueia SMTP (25/465/587/2525); usar Mailtrap HTTP API ou SendGrid em produção
- Templates `auth.password_reset_requested` e `user.invitation_sent` channel=EMAIL em `_DEFAULT_TEMPLATES`

### Asaas — correções críticas
- `create_payment()` chama `provider.create_charge()` antes do commit → `payment.external_charge_id` preenchido
- `confirm()` extrai value/fee do payload aninhado: `webhook_data.get("payment", {}).get("value")`
- Lazy registration de customer Asaas: `ensure_customer()` na primeira cobrança → `Customer.asaas_customer_id`
- `validate_and_clean_cpf_cnpj()` em `payments/service.py` — valida dígitos verificadores antes do Asaas
- **Dívida**: `create_subaccount()` sem `birthDate` — bloqueia produção Asaas com CPF

### PagSeguro (novo provider)
- `providers/pagseguro.py` — PagSeguroProvider(PaymentProvider) para terminais físicos
- OAuth2 client_credentials via `_authenticate()` — token descartado após uso
- `create_charge()`, `handle_webhook()`, `get_status()` implementados para terminal físico
- `refund()` — **STUB, endpoint `/charges/{id}/cancel` NÃO confirmado pela documentação PagBank (2026-06-03)**
- `list_terminals()` — **STUB, endpoint REST de listagem não encontrado na documentação pública**
- Decisão arquitetural: PagSeguro Point não tem REST API pública para push de cobranças
  → SmartPOS/PlugPag usam SDK Android; TEF usa middleware de parceiros — sem REST direto
- Migration `psg1a2b3c4d5`: `credentialprovider` enum recebeu valor 'PAGSEGURO'
- Factory em `provider_factory.py`: PAGSEGURO credential → PagSeguroProvider; fallback → AsaasProvider

### Pagamento manual / MAQUININHA
- `POST /payments/{id}/confirm-manual` — OWNER/ADMIN; CASH e provider=manual
- `confirm_manual()` retorna `tuple[Payment, Optional[dict]]` — segundo elemento é `fee_warning`
- `_calc_manual_fee()` consulta `TenantFeeRoutingPolicy` pelo `fee_source` do payment_method
- `fee_percentage=NULL` → fee=0 + `fee_warning` no response (taxa não configurada)
- `fee_percentage=0` → fee=0 sem warning (zero configurado explicitamente)
- `event_id` sintético determinístico: `f"manual-{payment.payment_id}"` — garante idempotência
- `MAQUININHA` (genérico) + `payment_submethod`: DEBIT → MAQUININHA_DEBIT; CREDIT/None → MAQUININHA_CREDIT

### Taxa MDR — fee-policies
- `GET  /financial/fee-policies` — OWNER/ADMIN; lista 8 políticas por tenant
- `PATCH /financial/fee-policies/{fee_source}` — OWNER/ADMIN; atualiza fee_percentage / fee_flat
- `fee_source` válidos agora incluem: `MAQUININHA_PIX` (adicionado neste sprint)
- Novos tenants: MAQUININHA_PIX criado com fee_percentage=NULL; demais com fee_percentage=0
- Migration `f2g3h4i5j6k7`: ADD COLUMN fee_percentage (nullable), fee_flat, is_active
- Migration `g3h4i5j6k7l8`: DROP NOT NULL fee_percentage + seed MAQUININHA_PIX para tenants existentes

### Evolution API — hardening
- Webhook `POST /whatsapp/webhook` valida `EVOLUTION_WEBHOOK_SECRET` se configurado
- Header validado: `x-evolution-global-apikey`; sem segredo configurado → sem validação
- `EVOLUTION_WEBHOOK_SECRET: str = ""` em config.py (default = sem validação)

## Sprint Frontend (pós-Sprint de Integrações)

### Arquitetura de navegação (painel/)
- Sidebar: MENU (não "Navegação"); itens: Painel, Clientes, Serviços,
  Barbeiros, Produtos, Financeiro, Configurações
- /agenda: rota canônica para agendamentos (calendário por padrão)
- /appointments: redirect para /agenda
- /users: redirect para /settings/usuarios
- /integrations: redirect para /settings/integracoes

### Módulo Financeiro (/financeiro)
- Hub: dashboard com KPIs + gráfico de área (Recharts)
- /financeiro/pagamentos: lista com confirm-manual e FeeWarningBanner
- /financeiro/pagamentos/novo: formulário 4 métodos (CASH/PIX/MAQUININHA)
- /financeiro/movimentacoes: extrato com filtros
- /financeiro/taxas: políticas MDR por método (movido de /settings/taxas)

### Configurações (/settings)
- /settings/perfil: Meu Perfil (nome editável via PATCH /auth/profile)
- /settings/profile: Perfil da empresa (inclui Agendamento Online)
- /settings/integracoes: WhatsApp + Asaas (PagSeguro escondido até sandbox)
- /settings/comunicacao: toggles email/WhatsApp via PUT (não PATCH)
- /settings/usuarios: lista e convite de usuários (com campo name)
- /settings/taxas: redirect para /financeiro/taxas

### Componentes novos
- CustomerAutocomplete: autocomplete client-side de clientes
- FeeWarningBanner: aviso de taxa não configurada com link para /financeiro/taxas
- PaymentOnCompleteDialog: popup de pagamento ao concluir agendamento
  → fluxo: POST /payments → confirm-manual → PATCH /complete
  → "Concluir sem registrar": apenas PATCH /complete

### Decisões arquiteturais
- PagSeguro escondido da UI: componente TabPagSeguro comentado em
  settings/integracoes/page.tsx — reativar após sandbox PagBank validado
- Link de agendamento online: settings/profile (não settings/integracoes)
- Taxas MDR: módulo Financeiro (não Configurações)
- api.ts: parseDetailMessage() trata detail como array (FastAPI 422)
- AuthContext expõe setName para atualização do header sem reload

### Dívidas frontend
- Ajuste 9 (subconta Asaas): 5 campos obrigatórios ausentes no payload
  mobilePhone, incomeValue, address, addressNumber, province, postalCode
  Ver: painel/docs/plano-ajustes-pos-sprint.md seção Ajuste 9
- Visual das novas seções: genérico, não compatível com projeto de referência
  Deferido para após implementações prioritárias
- settings/financial/page.tsx: orphan (sem link no hub) — manter ou redirect
- Campo phone em User: não existe no modelo — requer migration separada

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

## Ambiente de testes

### Executar SEMPRE com o venv
```powershell
cd agendamento_engine
.\venv\Scripts\python.exe -m pytest tests/ -v
```

NUNCA usar `pytest` direto — o Python global (pyenv) não tem `slowapi`, causando 9 ModuleNotFoundError em `test_user_name.py`. Esses erros são **ambientais**, não bugs de código. Não investigar.

#### test_user_name.py — 9 ModuleNotFoundError
Causa: importa `app.main` → carrega `slowapi` ausente no Python global.
Solução: sempre usar `.\venv\Scripts\python.exe -m pytest`. Não confundir com regressão — ignorar quando usando venv.

### Testes skipados sem DATABASE_URL (PostgreSQL real) — validados 2026-06-08

Usam `@pytest.mark.skipif(not DATABASE_URL)` — pulam automaticamente sem banco real; passam contra Supabase. Implementados com SAVEPOINT + rollback: zero resíduo no banco, usam registros reais para satisfazer FKs.

| Teste | Arquivo | Trigger que valida | Validado |
|---|---|---|---|
| `TestTenantConfigAccrual::test_trigger_blocks_accrual_at_db_level` | `tests/test_sprint3_config.py` | `enforce_cash_mode` (fn `block_accrual_mode`) | ✓ 2026-06-08 |
| `TestImmutabilityTriggers::test_movement_update_rejected_by_trigger` | `tests/test_sprint6_financial_core.py` | `movement_no_update` (fn `prevent_movement_modification`) | ✓ 2026-06-08 |
| `TestImmutabilityTriggers::test_entry_delete_rejected_by_trigger` | `tests/test_sprint6_financial_core.py` | `entry_no_delete` (fn `prevent_entry_modification`) | ✓ 2026-06-08 |

Rodar contra Supabase:
```powershell
$env:DATABASE_URL="postgresql://postgres:<senha>@<host>:5432/postgres"
.\venv\Scripts\python.exe -m pytest tests/test_sprint3_config.py::TestTenantConfigAccrual::test_trigger_blocks_accrual_at_db_level tests/test_sprint6_financial_core.py::TestImmutabilityTriggers::test_movement_update_rejected_by_trigger tests/test_sprint6_financial_core.py::TestImmutabilityTriggers::test_entry_delete_rejected_by_trigger -v
```

### 1 xfail esperado (permanente)
`tests/test_asaas_integration.py::test_sandbox_create_subaccount`
Asaas sandbox rejeita criação de subconta sem todos os campos obrigatórios. Marcado `xfail(strict=False)` — comportamento esperado, não investigar.

## Stack e infraestrutura

- FastAPI 0.115 · SQLAlchemy 2.0 · Alembic
- slowapi ativo — rate limit 10 req/min/IP em POST /auth/login (X-Forwarded-For)
- Uploads: Supabase Storage (dual-write ativo; migração de URLs executada)
- EXCLUDE CONSTRAINT ativa em appointments (btree_gist + tsrange, company_id + professional_id)
- Tabelas criadas: `user_invitations`, `audit_logs` (append-only via triggers no banco)
- Tabelas: `tenant_configs`, `module_activations`, `tenant_brandings`, `categories`
- Onboarding: `create_company` cria TenantConfig + 10 ModuleActivations +
  TenantBranding + 16 categories default na mesma transação
- Workers: Celery + Redis (session_cleanup e reminder exclusivamente via Celery Beat)
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
- Não chamar `provider.refund()` para PagSeguro em produção — endpoint não confirmado (stub retorna 500)
- Não usar revision ID `e1f2g3h4i5j6` para Sprint 11 — já em uso por add_asaas_customer_id

## Decisões registradas

- `ACCRUAL` bloqueado no Estágio 0 via trigger `block_accrual_mode` em `tenant_configs`
- Evolution API permanece global no Estágio 0 (Opção A — confirmada no Sprint 5):
  WHATSAPP_EVOLUTION no enum provider é schema-only; migração whatsapp_connection
  não aplicável no Estágio 0
- PagSeguro Point: documentação pública não expõe REST API para push de cobranças a terminais físicos.
  Soluções físicas (SmartPOS, PlugPag, TEF, Tap On) usam SDK Android, Bluetooth ou Intent local.
  PagSeguroProvider.create_charge() usa endpoint /orders como proxy — não confirmado para Point.
  Decisão: não ativar PagSeguro Point em produção até confirmar endpoint com time comercial PagBank.

- fee_percentage NULL vs. zero: NULL = "não configurado" → dispara fee_warning em confirm_manual.
  Zero = "0% configurado" → sem aviso, sem taxa. Semântica intencional para MAQUININHA_PIX.
  Tenants pré-sprint têm MAQUININHA_CREDIT/DEBIT com fee_percentage=0 (DEFAULT da migration) — sem warning.

## Bugs conhecidos / corrigidos

- [CORRIGIDO] Timezone na geração de slots: working_hours eram tratados
  como UTC em vez de horário local do tenant.
  Fix em availability/service.py + appointments/service.py.
  Usa TenantConfig.timezone como fonte canônica com fallback
  "America/Sao_Paulo". Requer tzdata==2026.2 (adicionado ao requirements).
- [CORRIGIDO] company_profile router: User object passado em vez de company_id — fix em 9fed210
- [CORRIGIDO] professionals/schemas: specialty ausente de ProfessionalUpdate/Response — fix em bbb5632
- [CORRIGIDO] products/schemas: stock ausente de ProductUpdate/Response — fix em bbb5632
- [CORRIGIDO] schedule/service: upsert_working_hour suportava apenas 1 período/dia — refatorado DELETE→INSERT em bbb5632
- [CORRIGIDO] booking FSM: SELECT_DATE e NAVIGATE_DATES bloqueados em AWAITING_TIME — fix ddb52c9
- [CORRIGIDO] working_hours: upsert suportava apenas 1 período/dia — refatorado DELETE→INSERT em bbb5632
- [CORRIGIDO] professionals: specialty ausente dos schemas — fix bbb5632
- [CORRIGIDO] products: stock ausente dos schemas — fix bbb5632
- [CORRIGIDO] Professional.specialty: ausente do modelo ORM — adicionado em d5c4741
- [CORRIGIDO] Product.stock: ausente do modelo ORM — adicionado com validator >= 0 em d5c4741
- [CORRIGIDO] WorkingHour: UniqueConstraint removido do ORM (nunca existiu no banco) — múltiplos períodos/dia funcionam em d5c4741
- replace_working_hours_for_day: DELETE+INSERT atômico, max 3 períodos, validação de sobreposição

## Segurança

- JWT agora inclui `iat` (issued at) em todos os tokens
- Troca de senha invalida tokens emitidos antes dela via `last_password_change_at`
  em User — tokens sem `iat` (pré-deploy) são aceitos por backward compat
- change_password e reset_password atualizam last_password_change_at

## Dívidas de integração
- Asaas create_subaccount: campo birthDate obrigatório para CPF;
  onboarding atual não coleta o campo; novos tenants ficam sem
  external_account_id até ser corrigido
- Asaas refund: payment_service.refund() não chama provider.refund() — estorno apenas
  contábil local; gateway externo não processa o estorno automaticamente
- PagSeguro Point: REST API para push de cobranças não documentada publicamente;
  create_charge() e list_terminals() são stubs aguardando confirmação do time comercial PagBank
- Email em produção: Railway bloqueia SMTP (portas 25/465/587/2525);
  implementação atual usa Mailtrap HTTP API (sandbox only);
  substituir por SendGrid/Mailgun/Mailtrap Email API antes de ir a produção
- [BACKEND CONCLUÍDO — Ajuste 9] Subconta Asaas: migration i3j4k5l6m7n8 adicionou
  8 colunas owner_* em companies; AsaasProvider.create_subaccount aceita todos os
  campos; service.py persiste e envia. Pendente: frontend (TabAsaas expandido).

## Lições de produção (2026-06-07)
- FeePolicyResponse.fee_percentage: sempre Optional[Decimal] — coluna nullable no banco
- communicationaudience enum PostgreSQL: valores uppercase (CLIENT, PROFESSIONAL, OWNER)
  dispatch() normaliza recipient_type.upper() antes de qualquer query
- _DEFAULT_FEE_SOURCES deve estar sincronizado com _calc_manual_fee e frontend:
  CASH, CHAVE_PIX, MAQUININHA_PIX,
  MAQUININHA_CREDIT_VISA_MASTER, MAQUININHA_CREDIT_ELO,
  MAQUININHA_CREDIT_HIPER_AMEX, MAQUININHA_CREDIT_OUTROS,
  MAQUININHA_DEBIT_VISA_MASTER, MAQUININHA_DEBIT_ELO,
  MAQUININHA_DEBIT_OUTROS (migration l4m5n6o7p8q9).
  PIX/BOLETO/CARD_* removidos — taxa vem do webhook Asaas.
- GET /financial/movements retorna: type (não movement_type), movement_id (não id),
  occurred_at (não created_at), amount como string Decimal
- ConfirmManualResponse é flat — não tem camada payment: { ... }
- target_account_id em PaymentCreate: Optional — backend resolve conta CAIXA
- provider em PaymentCreate: Optional — default "manual"