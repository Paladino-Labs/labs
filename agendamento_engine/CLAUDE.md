**Fase 2 concluída.** Sprint 25 concluído (2026-06-13 — schema-only Estágio 1+ + suite de contrato + wiring DEPOSIT). **Estágio 0 fechado** (suite de contrato verde contra PostgreSQL real). HEAD migration: `e0s25f_product_extras`.

## Estado final — Estágio 0 conforme (2026-06-13, pré-push)
Análise de conformidade plano vs. código: **`docs/conformidade-estagio-0.md`**. Os 15 sprints
(`I → 18 → 17 → 16 → E → B → A → D → C → G → H → 2.0 → 2.6 → 2.7 → 25`) estão implementados e
verificados em código: migration + módulo + router em `main.py` (44 routers) + handlers no
lifespan (12 grupos, incl. `register_deposit_handlers`) + workers no beat_schedule. Cadeia
Alembic **linear, head único `e0s25f_product_extras`** (sem multi-head). Suite: **951 passed,
6 skipped, 1 xfailed** (zero regressões). `tests/contract/` (7 contratos) verde.
- **Veredicto: pronto para push com ressalvas operacionais** (não são bug de código):
  1. Vars Railway — `SECRET_KEY` ainda é `"troque-em-producao"` (TROCAR); configurar
     `CREDENTIAL_ENCRYPTION_KEY`, `EMAIL_PROVIDER`+chave real, `LLM_API_KEY` (vazio → sem LLM,
     só regex), `FRONTEND_BASE_URL`, `ASAAS_API_URL` de produção. Checklist na Seção 8 do relatório.
  2. `scripts/backfill_identity.py` pronto mas **NÃO executado** (janela de manutenção, antes de crescer a base).
  3. Templates `appointment.completed` (Sprint I) + 5 do Sprint G via SQL para tenants antigos.
  4. PagSeguro Point continua bloqueado (stubs não confirmados).
- **Único DoD não cumprido (não bloqueador, Estágio 1+):** eixos CUSTOM de comissão
  (`professional_share`/`prior_commission_share`/`use_net_of_discount`) não existem no schema.
- Nenhum desvio não documentado de impacto; nenhum bloqueador de segurança/dados/contrato de API.

## Sprint 25 — Schema-only Estágio 1+ + suite de contrato + DEPOSIT (2026-06-13)
- **6 migrations schema-only em cadeia** (← e0s27a), SEM endpoint/service/tela —
  apenas estruturas para o Estágio 1+, RLS canônico `app.current_company_id`:
  `e0s25a_locations` (multi-unidade) → `e0s25b_stock_batches` (FEFO/lotes) →
  `e0s25c_encomenda` (encomenda_orders + encomenda_items, FSM em VARCHAR) →
  `e0s25d_operation_professionals` (multi-profissional, UNIQUE appt+prof) →
  `e0s25e_service_input_checklists` (insumos por serviço) →
  `e0s25f_product_extras` (products.barcode + products.location_id FK locations
  ON DELETE SET NULL; índice parcial idx_products_barcode).
  **HEAD migration: e0s25f_product_extras** (próxima down_revision).
- **Wiring DEPOSIT** (`modules/payments/deposit_service.py`) — conecta primitivas
  que existiam isoladas, SEM nova coluna de schema:
  - `resolve_deposit_policy` (service-specific → global) + `compute_deposit_amount`
    (FIXED_AMOUNT | PERCENTAGE, nunca > total).
  - `create_deposit_payment`: Payment PENDING (provider=manual) vinculado ao
    appointment; no-op sem DepositPolicy.
  - `payment.confirmed` → `deposit_handler` promove Reservation **SOFT→FIRME**
    (vínculo pelo slot: professional + start/end, pois Payment não referencia
    Reservation). Registrado no lifespan (`register_deposit_handlers`).
  - `complete_appointment` → `recognize_balance_on_completion`: saldo restante
    (total − sinal confirmado) → `financial_core.handle_deposit_balance_recognized`
    (Movement INFLOW + Entry RECEITA/SERVICOS). No-op sem pagamento parcial.
  - `mark_no_show` (nova função em appointments/service) → `handle_no_show_deposit`:
    retém se `retain_on_no_show` (default True); estorna se False. Sinal retido
    **NÃO gera comissão** salvo `commission_on_retained_deposit` (default False).
  - `cancel_appointment` → `handle_cancellation_deposit`: refund dentro da janela
    (`is_within_refund_window`: now ≤ start − refundable_until_hours_before),
    retenção fora dela. Todas as chamadas no lifecycle são **best-effort
    pós-commit** (try/except logado) — no-op sem DepositPolicy → zero regressão.
- **Suite de contrato `tests/contract/`** (7 contratos, 54 testes SQLite/FakeDB +
  2 gated → **56 verdes contra PostgreSQL real**). `conftest.py`: FakeDB que
  avalia critérios reais do SQLAlchemy (eq/ne/is/ge/le/gt/lt/in_/notin_), `options`
  passthrough, e `execute` mínimo replicando `processed_idempotency_keys`.
  `requires_postgres` = skipif sem DATABASE_URL.
  - C1 FSM (estados REAIS — não DRAFT/REQUESTED/CONFIRMED do enunciado);
    C2 conflito (`_assert_slot_available` + EXCLUDE constraint real);
    C3 DEPOSIT (deposit_service ponta a ponta); C4 comissão dois eixos
    (BARBERSHOP_PAYS=40,00 / SPLIT_50_50=38,50 / BARBER_PAYS=37,00);
    C5 idempotência (mecanismo is_processed/mark_processed + guarda de domínio
    do commission_handler via SessionLocal monkeypatched); C6 DRE; C7 multi-tenant
    (+ RLS real gated).
- **GAP documentado (Estágio 1+, não bloqueador):** eixos CUSTOM de comissão
  (`professional_share`, `prior_commission_share`, `use_net_of_discount`) **não
  existem** no modelo `commission_policies`. O modelo tem `commission_base`
  (GROSS_SERVICE|NET_SERVICE|GROSS_OPERATION|CUSTOM_AMOUNT) e
  `commission_fee_policy` (BARBERSHOP_PAYS|SPLIT_50_50|BARBER_PAYS; legado
  BEFORE_FEES|AFTER_FEES). Implementar os eixos CUSTOM é trabalho de Estágio 1+.
- Sem migração de dados (apenas wiring de lógica). Suite completa: 951 passed,
  6 skipped, 1 xfailed (zero regressões).

**HEAD migration:** e0s25f_product_extras

## Sprint 2.7 — Inbox de atendimento humano + estado RESOLVIDA (2026-06-13)
- Migration `e0s27a_conversation_messages` (HEAD ← e0s20a): tabela
  `conversation_messages` (RLS canônico) — id, company_id FK, session_id FK
  bot_sessions, direction (INBOUND|OUTBOUND), content, content_type, sender_type
  (CLIENT|BOT|AGENT), agent_user_id FK users nullable, whatsapp_message_id,
  created_at. Índices (session_id, created_at ASC) e (company_id, created_at DESC).
  A migration também faz **seed idempotente** do template conversation.escalated
  (WHATSAPP+EMAIL, OWNER) para tenants existentes (padrão g1h2i3j4k5l6).
- **STATE_RESOLVIDA** (bot_service.py): marcador terminal. `resolve` seta RESOLVIDA;
  o dispatcher consome RESOLVIDA na próxima mensagem → reset_session(keep_customer)
  + MENU_PRINCIPAL + show_menu_principal (**bot reassume, não silencia**). Permite
  `GET /conversations?status=resolved` listar conversas resolvidas por estado.
- bot_service: `_persist_message` (best-effort, db.add+flush), `_escalate_to_human`
  centraliza os 2 gatilhos de escalada (comando universal "humano"/"atendente"/
  "ajuda"/"suporte" + intenção FALAR_COM_HUMANO): persiste INBOUND do gatilho →
  state=HUMANO → envia+persiste HUMANO_CHAMADO (OUTBOUND BOT) → publica
  conversation.escalated. Branch STATE_HUMANO **agora persiste INBOUND CLIENT** e
  silencia (antes era `pass`). BotSession **não tem coluna customer_id** — vem de
  `session.context["customer_id"]`.
- `conversation.escalated` (trigger=INTENT|MENU) → handler
  `workers/handlers/conversation_handler.py` notifica OWNER via
  CommunicationService (template conversation.escalated). Registrado no lifespan.
  `conversation.resolved` publicado no resolve (best-effort).
- `modules/conversations/` — service + router `/conversations` (RBAC
  OWNER/ADMIN/OPERATOR em TODOS): GET / (status=escalated|resolved), GET /{id},
  GET /{id}/messages (asc), POST /{id}/reply (422 se != HUMANO; envia via
  sender.send_text resolvendo instance via WhatsAppConnection.company_id; persiste
  OUTBOUND AGENT), PATCH /{id}/resolve. Isolamento cross-tenant: sessão precisa
  pertencer ao company_id → 404.
- Template conversation.escalated (WHATSAPP+EMAIL, OWNER) em _DEFAULT_TEMPLATES.
  ⚠ Tenants pré-2.7: já cobertos pelo seed da migration (não precisa SQL manual).
- messages.ATENDIMENTO_ENCERRADO nova.
- Testes: tests/test_sprint27_inbox.py (12 testes, FakeDB com filtros reais +
  order_by funcional; dispatcher via handle_inbound_message async).

**HEAD migration:** e0s27a_conversation_messages


## Sprint 2.6 — ChainClassifier integrado ao FSM + compras (2026-06-13)
- **Sem migration** — estados novos usam a coluna `bot_sessions.state` existente.
  HEAD permanece `e0s20a_intent_classifications`.
- `bot_service._classify_and_route()`: texto livre em **INICIO/MENU_PRINCIPAL**
  (cliente já identificado + input que não casa com opção do menu) → ChainClassifier
  sugere; o FSM decide (invariante 1). Bloco roda APÓS comandos universais e só
  para esses dois estados; `resolve_input(...) is None` garante que cliques de
  botão não acionam o classificador (B6 — estados guiados por menu preservados).
  Erro do classificador é capturado e cai no menu (não quebra o bot).
- `INTENT_TO_STATE` (7 intenções). Roteamento real:
  AGENDAR→ESCOLHENDO_SERVICO · CONSULTAR→VER_AGENDAMENTOS ·
  FALAR_COM_HUMANO→HUMANO · COMPRAR_PRODUTO/PACOTE→fluxo de compra.
  **CANCELAR** (`_route_cancelar`): 0 agendamentos→menu; **1→auto-seleciona e entra
  em CANCELANDO**; >1→VER_AGENDAMENTOS. **REMARCAR** (`_route_remarcar`)→sempre
  VER_AGENDAMENTOS (cliente escolhe e gerencia — REAGENDANDO exige agendamento).
- **`is_universal_command` não trata mais "cancelar" como menu** — virou intenção
  CANCELAR. Abortar fluxo continua via `0/menu/início/voltar/sair`.
- Módulo inativo: ChainClassifier converte intenção fora do catálogo em FALLBACK
  (sem mensagem). `_inactive_module_intent()` faz regex SEM filtro sobre ALL_INTENTS
  e, se o texto pede produto/pacote com módulo desligado, envia `RECURSO_INDISPONIVEL`
  em vez de só reexibir o menu.
- **PRODUCT×SALE NÃO criado como Operation/Appointment** — `Appointment` exige
  profissional+horário; o plano prevê "sem migration". A venda via bot é
  representada pela primitiva real: **Payment (manual/CASH) + StockMovement VENDA**
  (Sprint 17). `StockMovement.created_by` é NOT NULL → bot resolve o **OWNER** do
  tenant como ator; sem owner, registra o Payment e pula a baixa (best-effort logado).
  Checa estoque antes de cobrar (mensagem amigável se insuficiente).
- `handlers/comprando_produto.py`: ESCOLHENDO_PRODUTO (stock>0, list se >3 / botões
  se ≤3, máx 10) → CONFIRMANDO_QUANTIDADE_PRODUTO (parse de inteiro) →
  CONFIRMANDO_PRODUTO ([Confirmar]/[Cancelar]) → `_finalize` (Payment + StockMovement).
- `handlers/comprando_pacote.py`: ESCOLHENDO_PACOTE (is_active) → CONFIRMANDO_PACOTE
  → `_finalize` reutiliza `packages.purchase(seller_user_id=None, payment_method=CASH)`
  → PackagePurchase PENDING_PAYMENT + Payment PENDING.
- Testes: tests/test_sprint26_bot_integration.py (12 testes, FakeDB + serviços
  monkeypatched — não exercita webhook async nem Postgres).

**HEAD migration:** e0s20a_intent_classifications

## Sprint 2.0 — IntentClassifier isolado (2026-06-13)
- Migration `e0s20a_intent_classifications`: tabela append-only
  `intent_classifications` (RLS canônico) — toda classificação (REGEX | LLM |
  FALLBACK) é persistida, sem dedup. Colunas: confidence NUMERIC(4,3),
  entities JSONB, llm_provider/llm_model/llm_latency_ms (NULL fora de LLM)
- Novo pacote `modules/whatsapp/intent/` — **ZERO integração com
  bot_service.py ou handlers/** (deferido ao Sprint 2.6)
  - `schemas.py`: `IntentResult` (intent, confidence, entities, source,
    raw_input), `FALLBACK_INTENT="MENU_PRINCIPAL"`, `CONFIDENCE_THRESHOLD=0.7`
  - `catalog.py`: `ALL_INTENTS` (7 intenções), `INTENT_MODULE_REQUIREMENTS`
    (COMPRAR_PRODUTO→ESTOQUE, COMPRAR_PACOTE→PACOTES — valores reais do enum
    `modulename`, não placeholders em inglês), `get_active_intents()` —
    catálogo dinâmico por tenant (FALAR_COM_HUMANO sempre ativo)
  - `regex_classifier.py`: `RegexClassifier` — confidence 0.9 (padrão
    específico) / 0.75 (genérico) / 0.0+MENU_PRINCIPAL (sem match); filtra
    por `active_intents`; ordem CANCELAR > REMARCAR > CONSULTAR >
    COMPRAR_PRODUTO > COMPRAR_PACOTE > FALAR_COM_HUMANO > AGENDAR
  - `llm_classifier.py`: `LLMClassifier` (Anthropic Claude Haiku 4.5, tool use
    forçado — nunca texto livre; timeout 5s; qualquer falha → FALLBACK) +
    `NullLLMClassifier` (test double, `NULL_LLM_OUTCOME=fallback|agendar|
    falar_com_humano`, nunca chama API externa)
  - `classifier.py`: `ChainClassifier` — regex primeiro; LLM só se
    confidence < 0.7; resultado fora do catálogo ativo → MENU_PRINCIPAL;
    persiste 100% das classificações; `known_intents` property
- Modelo ORM `IntentClassification` em
  `infrastructure/db/models/intent_classification.py`
- `LLM_PROVIDER`/`LLM_MODEL`/`LLM_API_KEY`/`LLM_TIMEOUT_SECONDS` em config.py
  (defaults: anthropic / claude-haiku-4-5 / "" / 5.0)
- `anthropic==0.69.0` adicionado ao requirements.txt
- Testes: tests/test_sprint20_intent_classifier.py (9 testes, FakeDB
  in-memory) — cobre os 7 casos do DoD + invariantes 1/2/3/5
- Ver decisão de provider LLM no commit "docs: escolha de provider LLM para
  Sprint 2.0"

**HEAD migration:** e0s20a_intent_classifications

## Sprint H — CRM básico (2026-06-12)
- Migration `e0sH1_crm`: crm_configs (thresholds 1:1 por tenant),
  customer_classifications (APPEND por recomputação — histórico preservado;
  atual = linha mais recente via idx_customer_classifications_current),
  customers.custom_fields JSONB (notes já existia — IF NOT EXISTS). RLS canônico.
- `modules/crm/service.py`: compute_customer_metrics (dinâmico, ZERO persistência
  — visita = Appointment COMPLETED; gasto = Payment CONFIRMED net_charged_amount;
  FK é client_id), classify_customer (puro/determinístico, prioridade
  VIP > RECUPERADO > EM_RISCO > FREQUENTE > NOVO > REGULAR; EM_RISCO usa
  max(risk_min_days, avg_freq × risk_multiplier); RECUPERADO = previous EM_RISCO
  e não está mais em risco), recompute_all_classifications (insere se mudou OU
  última > 24h; commit em lote a cada 100), get_customer_insights (heurísticas
  SEM ML: churn_risk HIGH=EM_RISCO / MEDIUM=days>avg×1.5; RESCHEDULE = cancel
  < 7d sem SCHEDULED; PACKAGE = mesmo serviço 3×/60d sem purchase ACTIVE que
  cubra — pacote sem service_id é genérico e cobre qualquer um; PRODUCT = mais
  vendido em VENDA com source_id nos appointments do serviço preferido),
  get_crm_alerts (dedupe pela linha mais recente por customer)
- Filtros de status/escopo aplicados em Python sobre a query company+customer
  (compatível com FakeDB; volumes por cliente são pequenos)
- Rotas: /crm/alerts (OWNER/ADMIN), /crm/classifications (filtros
  classification+date_from), /crm/config GET (OPERATOR ok) / PUT (só OWNER);
  /customers/{id}/insights e /customers/{id}/classification (última + 5)
  com require_role — PATCH /customers/{id} pré-existente ganhou custom_fields
- Worker beat: crm-recompute-classifications (03:00) —
  workers/tasks/crm_recompute.py aceita company_id opcional p/ forçar 1 tenant
- SEM ML/IA; SEM sugestão automática ao cliente (deferidos pela visão)
- Testes: tests/test_sprint_h_crm.py (30 testes + 1 skip celery-ausente-no-venv,
  FakeDB in-memory)

**HEAD migration:** e0sH1_crm

## Sprint G — NPS + Fila de espera (2026-06-12)
- 2 migrations: `e0sG1_nps` (nps_configs 1:1 por tenant; nps_surveys
  PENDING|SENT|RESPONDED|EXPIRED com UNIQUE(appointment_id) — idempotência;
  nps_responses UNIQUE(survey_id), CHECK score 0–10) → `e0sG2_waitlist`
  (waitlist_configs 1:1; waitlist_entries com CHECK check_waitlist_scope —
  exatamente 1 de service_id/professional_id/product_id conforme scope_type).
  RLS canônico em todas.
- **NPS dispara APENAS após operation.completed** — handler
  `workers/handlers/nps_handler.py` (idempotência dupla:
  processed_idempotency_keys "nps.schedule:{appointment_id}" + UNIQUE no banco)
- payload de operation.completed ganhou `customer_id` (transitions.py);
  handler tem fallback que resolve via Appointment.client_id p/ eventos antigos
- `modules/nps/service.py`: schedule (delay + min_interval_days por cliente),
  send_pending (worker — dispatch trata consent/quiet hours; SCHEDULED conta
  como sucesso; SKIPPED_CONSENT_REVOKED → survey EXPIRED; FAILED → retry),
  expire (48h), record_response (público — survey_id é o token; só SENT → 422
  caso contrário), add_tenant_response (nunca edita score — só adiciona)
- Nota baixa (score <= low_score_threshold): publica nps.low_score_alert +
  dispatch best-effort ao OWNER (User role=OWNER ativo; sem phone em User →
  template EMAIL audience OWNER cobre; WHATSAPP existe mas falha sem phone)
- **Slot liberado é implícito no domínio** — Sprint G adicionou
  `_publish_slot_released` em appointments/service.py: cancel_appointment →
  appointment.cancelled, reschedule_appointment → appointment.rescheduled
  (best-effort, pós-commit, payload com service_ids[] + professional_id)
- stock.entry_recorded payload ganhou `product_ids[]` (stock/service.py)
- `modules/waitlist/service.py`: join (dup mesmo escopo → 409; operação ativa
  equivalente → 422), notify_waitlist (priority DESC + created_at ASC;
  PULA cliente com operação ativa e consent revogado; notifica APENAS o 1º
  elegível — não reserva slot), expire (NOTIFIED vencida → EXPIRED + notifica
  próximo). "Operação ativa" = Appointment SCHEDULED|IN_PROGRESS (não existe
  CONFIRMED no enum); escopo PRODUCT nunca tem operação equivalente
- Handlers em `workers/handlers/waitlist_handler.py`: appointment.cancelled,
  appointment.rescheduled, stock.entry_recorded — registrados no lifespan
- Workers beat: nps-send-pending (*/15), nps-expire-surveys (01:00),
  waitlist-expire-entries (*/30)
- Rotas: /nps/config (GET/PUT), /nps/surveys (lista/detalhe/respond tenant),
  POST /nps/respond/{survey_id} PÚBLICO rate limit 3/min;
  /waitlist/config (GET/PUT), /waitlist/entries (GET/POST/DELETE)
- nps.survey_request e waitlist.slot_available adicionados a
  _QUIET_HOURS_SCHEDULED_EVENTS (quiet hours → SCHEDULED, drain envia depois)
- 5 templates novos em _DEFAULT_TEMPLATES. ⚠ Tenants pré-Sprint G não os têm —
  inserir via SQL (mesmo caveat do Sprint I)
- Testes: tests/test_sprint_g_nps_waitlist.py (35 testes, FakeDB in-memory)

**HEAD migration:** e0sG2_waitlist

## Sprint C — Painel Owner Paladino (2026-06-12)
- 3 migrations: `e0sC1_tenant_status` (companies.status TRIAL|ACTIVE|SUSPENDED|
  CHURNED, default ACTIVE) → `e0sC2_impersonation_grants` (tabela de PLATAFORMA
  sem RLS; quase-append-only: trigger bloqueia DELETE e qualquer UPDATE que não
  seja revogação revoked_at NULL→valor) → `e0sC3_platform_settings` (key/value
  JSONB global, sem RLS, acesso só via service layer)
- **Suspensão bloqueia login**: check em `auth/service.py::authenticate` após
  credenciais — company.status==SUSPENDED → 403; PLATFORM_OWNER
  (company_id=None) nunca passa pelo check
- `app/middleware/impersonation.py` — ImpersonationMiddleware (header
  `X-Impersonate-Grant: {grant_id}`): valida JWT PLATFORM_OWNER + grant ativo +
  dono do grant; injeta request.state.{impersonating, impersonation_grant,
  effective_company_id}; audita CADA request impersonada em audit_logs com
  action="impersonated_request", resource_type="ImpersonationGrant",
  resource_id=grant_id, company_id=tenant (audit_logs NÃO ganhou coluna nova).
  READ_ONLY bloqueia métodos != GET/HEAD/OPTIONS já no middleware (defesa
  dupla com a dependency `require_not_read_only`)
- `modules/platform/` — service + router `/platform/*` (TODOS exigem
  require_role("PLATFORM_OWNER")): tenants (list/get/health/PATCH status),
  impersonation grants (POST/DELETE/GET — ELEVATED exige reason ≥20 chars,
  default 30min), flags por tenant (permission_overrides — reatribuição, não
  mutação in-place do JSONB), platform settings (upsert), GET /platform/audit
  (acesso auditado com action="platform_audit_access" ANTES de retornar —
  RBAC-4), redispatch
- **Redispatch (D7)**: só logs FAILED; CommunicationLog NÃO persiste context →
  re-renderizar via dispatch() é impossível — re-envia rendered_body direto
  pelo canal (padrão drain_scheduled); cria NOVO log (original intocado)
- `GET /audit/impersonation-accesses` (audit/router.py): tenant vê acessos
  impersonados do próprio company_id; PLATFORM_OWNER → 403 (usa /platform/audit)
- Notificação de suspensão ao OWNER do tenant: email DIRETO
  (`modules/platform/emails.py`, padrão _send_reset_email_direct) — evento de
  plataforma não passa pelo CommunicationService do tenant; best-effort
- Testes: tests/test_sprint_c_platform.py (33 testes, FakeDB in-memory)

**HEAD migration:** e0sC3_platform_settings

## Sprint D — Portal do Cliente (2026-06-12)
- 2 migrations: `e0sD1_portal_auth` (portal_credentials UNIQUE por identity e
  por email, password_hash NULLABLE — magic-link-only; portal_magic_tokens
  com SHA-256 do token, cru NUNCA persiste — padrão Sprint B) →
  `e0sD2_payment_source_authorizations` (UNIQUE identity+company+token,
  mode ALWAYS|ONCE). Tabelas GLOBAIS sem company_id — RLS HABILITADO SEM
  POLICY (padrão e0sA1); acesso só via service layer
- **JWT portal** (`modules/portal/auth_service.py`): claims
  `{sub: identity_id, type: "portal", iat, exp 24h}` — SEM company_id.
  `verify_portal_token` rejeita type != "portal" → 401.
  `get_current_user` (deps.py) rejeita EXPLICITAMENTE payload com claim
  `type` (JWT portal nunca autentica em endpoint tenant — antes do lookup)
- `get_current_portal_identity` em core/deps.py → PaladinoIdentity
- Auth: register (resolver por telefone — 422 sem DDD; identity existente →
  has_existing_history=true = adoção de histórico), login email+senha,
  magic link (15min, single-use, endpoint sempre 200 — não revela email).
  Email enviado DIRETO (Mailtrap HTTP/SMTP, padrão _send_reset_email_direct)
  — identity é global, CommunicationService.dispatch exige company_id
- Rotas `/portal/*`: dashboard/history/credits/subscriptions cross-tenant
  (identity → customers.identity_id → dados tenant-scoped); pause/cancel de
  assinatura com config do tenant; consents (source=PORTAL); payment-sources
  exigem consent PAYMENT_STORAGE (422); PATCH profile (phone re-resolve —
  E.164 de outra identity → 409; email novo → email_verified=false +
  verificação); GET /portal/identity/me e /identity/me (501 do Sprint A
  resolvido — ambos usam o dependency portal)
- B5: `allows_subscription_pause` (default False) /
  `allows_subscription_cancel` (default True) em modules/tenant/service.py
  via permission_overrides — SEM migration de coluna
- Asaas NÃO tem tokenização de cartão no adapter — POST /portal/payment-sources
  recebe source_token já tokenizado; tokenização no provider fica p/ sprint futura
- Tabela legada payment_sources (tenant-scoped) NÃO foi tocada
- Testes: tests/test_sprint_d_portal.py (48 testes, FakeDB in-memory)

**HEAD migration:** e0sD2_payment_source_authorizations

## Sprint A — Identidade Paladino (2026-06-12)
- 3 migrations em cadeia: `e0sA1_paladino_identities` (tabela GLOBAL sem
  company_id — RLS HABILITADO SEM POLICY, intencional; acesso só via service
  layer) → `e0sA2_consent_records` (append-only, trigger
  consent_records_no_update no banco; company_id NULL = consent global) →
  `e0sA3_customers_identity_link` (customers.identity_id nullable + índice
  parcial; backfill via script, NÃO na migration)
- `modules/identity/resolver.py` — PhoneIdentityResolver:
  normalize_phone_e164 ESTRITA (DDD obrigatório → 422; insere 9º dígito como
  customers/service.normalize_phone — decisão: SEM phonenumbers, a lib não
  insere o 9 e duplicaria identidades); resolve() create-if-new idempotente;
  resolve_for_tenant() → (customer, is_new) com lazy-link de identity_id NULL
- phone_e164 com '+' na identity; customers.phone continua SEM '+' (convenção)
- `modules/identity/consent_service.py` — append-only; check_consent:
  COMMUNICATION default True (opt-out), MARKETING/demais default False;
  channel NULL vale p/ todos os canais; company_id NULL = global
- Integrações: create_customer (PAINEL, não-fatal se telefone sem DDD),
  bot aguardando_nome (BOT) e public_book (LINK) usam resolver + consent
  GRANTED na criação; inicio.py faz lazy backfill no primeiro contato
- dispatch() passo 4: consent verificado p/ CLIENT no canal escolhido →
  SKIPPED_CONSENT_REVOKED; sem identity_id (UUID real) → envia (fallback
  transacional); event_type `marketing.*` → ConsentType.MARKETING e
  BLOQUEIA sem identity
- Rotas: GET/POST /customers/{id}/consents[/grant|/revoke] (writes
  OWNER/ADMIN, source=PAINEL); GET /identity/me → 501 até Sprint D
- `scripts/backfill_identity.py` (--dry-run): agrupa por E.164, colisões de
  nome → mais recente + backfill_collision_report.csv; idempotente;
  **NÃO executado — operação de produção com janela de manutenção**
- Testes: tests/test_sprint_a_identity.py (32 testes, FakeDB in-memory)

**HEAD migration:** e0sA3_customers_identity_link

## Sprint B — Link de gestão com token único (2026-06-11)
- `appointments.manage_token_hash` (SHA-256; cru NUNCA persiste) +
  `manage_token_expires_at` (= start_at) + índice único parcial —
  migration `e0sB1_appointment_manage_tokens`
- `modules/appointments/manage_tokens.py`: issue_manage_token (gera UUID4 cru,
  persiste hash), hash_token, invalidate_manage_token, build_manage_url
  (FRONTEND_BASE_URL, vazio → fallback FRONTEND_URL)
- Token gerado em create_appointment E reschedule_appointment (novo token
  invalida o anterior); cru vai só na mensagem via context {{manage_url}}
  (template appointment.confirmed CLIENT ganhou "Para remarcar ou cancelar: …")
- `modules/public/manage_router.py` + `manage_service.py` — público, sem JWT:
  GET /manage/{token} (10/min) · POST cancel (5/min) · POST reschedule (5/min)
- **404 genérico SEMPRE** p/ token inválido/expirado/terminal (nunca 401/403)
- **Janela decide CONSEQUÊNCIA, não permissão**: cancel via link usa
  skip_policy=True; DepositPolicy (service-specific → global) + Payment
  CONFIRMED no appointment → fora da janela cancela E deposit_retained=true
  (retenção é informativa — refund continua manual/OWNER)
- transitions.py: transição p/ estado terminal zera manage_token_hash/expires
- Reschedule: 409 de conflito → 422 no contrato público
- Tenants pré-Sprint B: appointments existentes sem token (manage_url vazio
  na mensagem) — só novos agendamentos ganham link
- Testes: tests/test_sprint_b_manage_token.py (21 testes)

**HEAD migration:** e0sB1_appointment_manage_tokens

## Sprint E — ExternalStatementEntry (2026-06-11)
- Tabela `external_statement_entries` (RLS canônico) — migration
  `e0sE1_external_statement_entries`; UNIQUE (company_id, line_hash)
  garante idempotência de re-upload (line_hash = SHA-256 da linha crua)
- `modules/financial_core/statement_service.py`: import_csv, suggest_match,
  confirm_match, dismiss_entry, list_statement_entries, list_batches
- `modules/financial_core/statement_router.py` (prefixo /financial/statement,
  registrado em main.py): POST /import (multipart: file + account_id +
  column_mapping JSON), GET /, GET /batches, GET /{id}/suggestions,
  POST /{id}/match, POST /{id}/dismiss
- **Movement NUNCA é alterado** — vínculo unidirecional em
  entry.matched_movement_id (append-only preservado)
- `auto_matched` no import = entries com candidato encontrado; é APENAS
  sugestão — nada persiste como MATCHED (confirmação manual via /match)
- Match: mesmo account, |amount| ±0.01, occurred_at ±2 dias, direção
  compatível (INFLOW→INFLOW/TRANSFER_IN), movement não casado; critérios
  revalidados em Python (defesa em profundidade + testável com mocks)
- direction inferido pelo sinal do valor (negativo → OUTFLOW) ou coluna
  explícita (D/DEBIT/SAIDA → OUTFLOW); amount armazenado sempre positivo
- dismiss: reason obrigatório (422); só entries PENDING (422); audit completo
- **Primeiro uso real de `require_action()`** (deps.py): writes exigem
  OWNER/ADMIN; OPERATOR só com permission_overrides["OPERATOR"]["statement_*"]
  (actions: statement_import, statement_match, statement_dismiss)
- Eventos: statement.batch_imported / entry_matched / entry_dismissed
- Testes: tests/test_sprint_e_statement.py (30 testes)

**HEAD migration:** e0sE1_external_statement_entries

## Sprint 16 — Promoções e Cupons (2026-06-11)
- Tabelas `promotions`, `coupons`, `coupon_redemptions`, `discount_applications`
  (RLS canônico) + `payments.coupon_code` — migration `e0s16a_promotions_coupons`
  ⚠ `discount_applications.promotion_id` é NULLABLE (manual-discount usa NULL)
  ⚠ `manual_override_count` já existia desde w1x2y3z4a5b6 — não recriado
- `modules/promotions/service.py`:
  `compute_preview()` ZERO efeito colateral; `effectuate()` revalida tudo com
  SELECT FOR UPDATE em coupons.uses_count; `revert_for_refund()` no refund
- Seleção: exclusivas (cumulative=false) → a de maior desconto
  (CUSTOMER_FAVORABLE); cumulativas em priority DESC sobre o residual
- Revalidação falhou (modo STRICT) → publica `promotion.effectuation_failed`,
  NÃO bloqueia o pagamento (decisão de produto — supersede "refund automático"
  do DoD original do plano)
- `promotion_payment_handler`: 5º listener de payment.confirmed
  (+ payment.refunded para reverter redenções); registrado no lifespan
- payload de payment.confirmed agora inclui `coupon_code`
- `create_payment(coupon_code=...)`: aplica preview na criação —
  net_charged_amount nasce com desconto → Entry RECEITA reflete o líquido
  (desconto reduz receita no DRE; NÃO existe categoria DESCONTO)
- `POST /payments/{id}/manual-discount` (OWNER/ADMIN): reason obrigatório,
  só PENDING, audit `manual_discount_override`, manual_override_count++
- Rotas `/promotions` (CRUD + activate/pause/cancel + /preview + /coupons)
- Worker `promotions_expiry_scanner` (00:05): Promotion ACTIVE vencida →
  EXPIRED; Coupon ACTIVE vencido → CANCELLED
- `coupon_reopen_policy`: NEVER_REOPEN (default) | REOPEN_ON_REFUND
- Testes: tests/test_sprint16_promotions.py (27 + 1 skip PostgreSQL)
  ⚠ NÃO importar app.main em arquivos de teste que rodem antes de
  test_sprint2_rbac (quebra o monkey-patch de modelos daquele arquivo)

**HEAD migration:** e0s16a_promotions_coupons

## Sprint 18 — Despesas + recorrência (2026-06-11)
- Modelo `Expense` (tabela `expenses`, RLS padrão `app.current_company_id`):
  lifecycle PENDENTE → PAGA | CANCELLED; categoria validada contra
  `DESPESA_CATEGORIES` (derivado de entry_category.py — CUSTO → 422)
- `handle_expense_paid` em financial_core/service.py: Movement OUTFLOW +
  Entry DESPESA atômicos (flush sem commit, padrão handle_payment_confirmed);
  resolve conta `is_default_inflow` se account_id não informado
- Recorrência MONTHLY em JSONB (`recurrence_rule`) com clamp de fim de mês
  (`next_occurrence` usa dateutil.relativedelta); instâncias encadeadas via
  `parent_expense_id`; geração FORA da transação de pagamento (falha não
  desfaz o pagamento); `generate_next_instance` idempotente
- `supplier_id` UUID SEM FK — Sprint 17 adiciona a FK via ALTER TABLE
- Rotas `/expenses/` (POST, GET, GET/{id}, PATCH/{id}/pay, PATCH/{id}/cancel)
- Workers: `expense_due_soon` (07:30, janela 3 dias, também publica
  expense.overdue; dedup via processed_idempotency_keys) e
  `expense_recurrence` (06:00) no beat_schedule
- Eventos: expense.created/due_soon/overdue/paid/cancelled com keys canônicos
- ⚠ Categorias da visão FOLHA_PAGAMENTO/IMPOSTOS/OUTROS_DESPESAS não existem
  no enum — usar SALARIO/DESPESA_OUTROS (entry_category.py é fonte de verdade)
- python-dateutil==2.9.0.post0 explicitado no requirements.txt
- Testes: tests/test_sprint18_expenses.py (28 testes)

**HEAD migration:** e0s18a_expenses

## Sprint I — Dívidas críticas (2026-06-11)
- `refund()`: gateway ANTES da contabilidade; falha do provider → HTTP 502, nenhum Movement/Entry
- `force_local=true` no POST /payments/{id}/refund: apenas OWNER (403 p/ ADMIN);
  reason obrigatório (422); audit action `refund_payment_forced_local`
  com after_snapshot {"force_local": true, "note": "estorno forçado sem gateway"}
- NullProvider.refund(): env var `NULLPROVIDER_REFUND_OUTCOME=success|error` (default success)
- Chamadas diretas `evolution_client.send_text` de NOTIFICAÇÃO removidas:
  notifications.py, reminder_worker.py, appointments/router.py (pós-atendimento)
  → tudo via CommunicationService.dispatch; CommunicationLog captura 100% dos envios
  Bot conversacional (whatsapp/sender.py + handlers) fora do escopo — é diálogo FSM, trilha 2.6/2.7
- Flag `use_communication_service`: agora kill-switch — ausente → **True**
  (`overrides.get("use_communication_service", True)` em todos os pontos)
- Template novo `appointment.completed` (WHATSAPP/CLIENT) em _DEFAULT_TEMPLATES.
  ⚠ Tenants criados ANTES do Sprint I não têm esse template — inserir via SQL
  para manter a mensagem de pós-atendimento (sem template → SKIPPED_NO_TEMPLATE)
- Email plugável: `EMAIL_PROVIDER=mailtrap|sendgrid|smtp` (default mailtrap);
  `modules/communication/email_adapters.py` (EmailAdapter ABC + Mailtrap + SendGrid);
  credencial ausente → fallback SMTP (credencial tenant → SMTP_* global)
- reminder_worker: flags reminder_*_sent só marcados quando dispatch != FAILED
  (FAILED → retry no próximo scan da janela)

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

**HEAD migration:** m5n6o7p8q9r0 (add_payment_submethod)
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
  é kill-switch do dispatch (Sprint I: ausente → True; False = opt-out explícito)
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
  → usar CommunicationService.dispatch (chamadas diretas de notificação removidas no Sprint I;
  exceção: bot conversacional via whatsapp/sender.py)
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
- [RESOLVIDO — Sprint I] Asaas refund: payment_service.refund() chama provider.refund()
  ANTES da contabilidade; falha do gateway → 502 sem Movement/Entry; force_local p/ OWNER
- [RESOLVIDO — Sprint I] Email em produção: adapter plugável via EMAIL_PROVIDER
  (mailtrap|sendgrid|smtp). Railway bloqueia SMTP → configurar EMAIL_PROVIDER=sendgrid
  + SENDGRID_API_KEY, ou mailtrap com token de produção (MAILTRAP_SANDBOX_INBOX_ID=0),
  no vault do Railway. Mailtrap sandbox permanece para dev.
- PagSeguro Point: REST API para push de cobranças não documentada publicamente;
  create_charge() e list_terminals() são stubs aguardando confirmação do time comercial PagBank
- Ajuste 9 Asaas: backend completo (migration i3j4k5l6m7n8, 8 colunas owner_* em
  companies; AsaasProvider.create_subaccount aceita todos os campos; service.py
  persiste e envia — inclui birthDate). Frontend pendente (5 campos no formulário
  de settings/integracoes). Tenants criados antes do Ajuste 9 sem external_account_id
  — subconta Asaas inexistente para esses tenants.

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