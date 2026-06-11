# Gaps: Visão Estágio 0 vs. Código Atual do Backend
**Gerado em:** 2026-06-10 · Sessão exclusiva de análise — nenhum arquivo de código modificado
**Fonte de verdade:** `visao-estagio-0.md` (derivado de visao-produto-paladino.md v23.0)
**Evidências:** `app/modules/` (28 módulos), `migrations/versions/` (68 migrations), `app/workers/`, CLAUDE.md, SPRINT-LOG.md, `docs/plano-execucao-fase3.md`, `docs/analise-planejado-vs-executado.md`

---

## 1. Resumo Executivo

O backend cobre com solidez o eixo **agendamento → operação → pagamento → financial core → comissão → cotas → pacotes → assinaturas** (Sprints 1–15), incluindo FSM de operações com soft/firme reservation, Payment FSM com webhook Asaas idempotente, Movement/Entry imutáveis com triggers, comissão de dois eixos (`commission_fee_policy_v2`), FEFO de cotas e multi-tenancy com RLS em 26 tabelas. Dos 21 domínios que a visão exige para o Estágio 0, **8 estão completamente ausentes no código**: Estoque, Despesas, Promoções/Cupons, NPS, Fila de espera, CRM, Painel Owner Paladino (backend) e Portal do Cliente (backend). A **Identidade Paladino** (PaladinoIdentity 3 níveis, PhoneIdentityResolver E.164, ConsentRecord) também não existe — o `Customer` atual é por tenant, não Paladino-wide. Três gaps são de **planejamento** (não aparecem em nenhum sprint do plano de execução): endpoints backend do Painel Owner, `ExternalStatementEntry` e o roteamento 3-vias de taxas (`client/tenant/professional_share`). As tabelas `[SCHEMA APENAS]` exigidas pela visão (locations, lotes/expiry, encomenda, multi-profissional) estavam no Sprint 25, que foi pulado. Recomendação: fechar Sprints 16–18 + 25 antes de qualquer módulo de relacionamento, e formalizar plano para Painel Owner backend e Identidade Paladino, que hoje só existem como sprints de frontend (20/24) sem contraparte backend planejada.

---

## 2. Tabela por Área: item da visão × status no código

Legenda: ✅ implementado · ⚠️ PARCIAL · ❌ CRÍTICO (ausente) · 🔮 FORA_ESCOPO_0 · ❔ não verificado em detalhe

### 2.1 Identidade e autenticação

| Item da visão | Status no código | Classificação |
|---|---|---|
| Identidade 3 níveis Paladino-wide (logado/leve/migração) | ❌ `Customer` é por tenant (`customers` com company_id); sem PaladinoIdentity | **CRÍTICO** |
| PhoneIdentityResolver (E.164, aliases, customer_id estável) | ❌ não existe; telefone tratado ad-hoc no bot/booking | **CRÍTICO** |
| ConsentRecord (COMMUNICATION/DATA_PROCESSING/PAYMENT_STORAGE/MARKETING) | ❌ nenhum modelo; grep encontra apenas menção textual em communication/service.py | **CRÍTICO** |
| Token de cartão vinculado ao cliente (autorização por tenant) | ❌ sem tokenização de cartão; `Customer.asaas_customer_id` é por tenant | **CRÍTICO** |
| Auth tenant (login, reset, convite, ativação) | ✅ completo (JWT com iat, rate limit, convite por email, ativação por token) | — |

### 2.2 RBAC e multi-tenancy

| Item | Status | Classificação |
|---|---|---|
| 5 papéis tenant + PLATFORM_OWNER (company_id nullable) | ✅ enum `userrole` com 9 valores; PLATFORM_SUPPORT/BILLING/READONLY schema-only conforme visão | — |
| Anti-escalonamento (ADMIN não eleva, último OWNER protegido) | ✅ Sprint 2 (declarado aprovado; não re-verificado linha a linha) | — |
| Autorização por ação + escopo (`require_action` + permission_overrides) | ⚠️ `require_role`/`require_action` existem; matriz granular completa da Parte 4 (ex.: OPERATOR opt-in com limite de valor, PROFESSIONAL scope próprio em todos os domínios) não auditada módulo a módulo | PARCIAL |
| Imutabilidade financeira (RBAC-2) | ✅ triggers no banco + @validates ORM em Movement/Entry; audit_logs append-only | — |
| Credenciais write-only/masked (RBAC-3) | ✅ Fernet + masked_preview; secret nunca retornado | — |
| Audit append-only + export (RBAC-4) | ✅ `modules/audit` + triggers | — |
| Multi-tenant: company_id em queries + RLS | ✅ RLS em 26 tabelas; `set_rls_context()` em get_db e workers | — |
| EXCLUDE CONSTRAINT conflito de agenda (btree_gist) | ✅ ativa em appointments e reservations | — |

### 2.3 Catálogo

| Item | Status | Classificação |
|---|---|---|
| Serviços: preço, duração, commission_base_value | ✅ | — |
| Opt-ins: preço/duração por profissional, variantes, preparo antes/depois | ✅ Sprint 11 (ServicePricingOverride, ServiceVariant, preparation_minutes) | — |
| Produtos: cadastro, imagens (Supabase), estoque básico | ⚠️ Product existe com `stock` simples; sem categorização opt-in/variações; limite de 5 imagens/5MB não verificado | PARCIAL |
| Modo Encomenda (serviços e produtos) | ❌ `[SCHEMA APENAS]` na visão — migrations não criadas (Sprint 25 pulado) | PARCIAL (schema exigido) |
| Múltiplos profissionais simultâneos `[SCHEMA APENAS]` | ❌ migration não criada | PARCIAL (schema exigido) |

### 2.4 Agendamento (Agenda + BookingEngine)

| Item | Status | Classificação |
|---|---|---|
| Jornada semanal + exceções + bloqueios | ✅ working_hours, ScheduleException (SUBSTITUTIVE/ADDITIVE), schedule_blocks | — |
| Reserva soft com TTL + promoção para firme | ✅ Reservation SOFT/FIRME, EXCLUDE tstzrange, expire via Celery | — |
| Ocupação direta + overbooking auditado | ✅ DirectOccupancy | — |
| Disponibilidade em runtime (8 passos) | ✅ availability/service.py (com preparo do Sprint 11) | — |
| Link de gestão com token único (remarcar/cancelar sem login) | ❌ grep por manage_token/management_link/cancel_token: zero ocorrências | **CRÍTICO** |
| Fluxo Link Público de agendamento (vitrine + booking) | ⚠️ módulos `public` + `booking` (web_booking_sessions) existem; confirmação via WhatsApp com link de gestão ausente | PARCIAL |

### 2.5 Operações (FSM)

| Item | Status | Classificação |
|---|---|---|
| Estados DRAFT→REQUESTED→CONFIRMED→IN_PROGRESS→COMPLETED/CANCELLED/NO_SHOW/FAILED | ✅ Sprint 10 (Appointment estendido + transitions.py) | — |
| `operation.completed` emitido → consumidores assíncronos | ✅ publicado em transitions; consumido por commission_handler | — |
| Tipos SERVICE×SCHEDULED e SERVICE×DIRECT | ✅ operation_type em Appointment | — |
| PRODUCT×SALE (venda de produto como operação) | ❔ não verificado se venda direta de produto passa pela FSM de operações | PARCIAL (provável) |
| Parâmetros configuráveis (draft_expiration, requested_expiration, no_show_threshold, auto_confirm_rules) | ❔ DRAFT existe; presença dos 4 parâmetros no TenantConfig não verificada | PARCIAL (provável) |

### 2.6 Pagamentos

| Item | Status | Classificação |
|---|---|---|
| Asaas (Pix/cartão/boleto) + webhook idempotente | ✅ Sprint 9 + correções (external_charge_id, ensure_customer, CPF/CNPJ) | — |
| Dinheiro + Maquininha (confirm-manual com MDR e submethod) | ✅ confirm-manual, TenantFeeRoutingPolicy, payment_submethod (m5n6o7p8q9r0) | — |
| Modelos de cobrança (POST_DELIVERY/DEPOSIT/PREPAID/PREPAID_REFUNDABLE) | ⚠️ DepositPolicy por serviço/global existe; fluxo DEPOSIT ponta a ponta (sinal → FIRME → saldo no COMPLETED → retenção em NO_SHOW) sem teste dedicado (Sprint 25 pulado); PREPAID_REFUNDABLE não verificado | PARCIAL |
| Estorno com refund_reason classificado | ⚠️ refund_reason existe em payments/schemas; **provider.refund() não é chamado** — estorno apenas contábil (dívida registrada no CLAUDE.md) | PARCIAL |
| TenantFeeRoutingPolicy com routing 3-vias (client/tenant/professional_share, soma=100%) | ⚠️ **[ERRATA 2026-06-10]** colunas client/tenant/professional_share + CHECK soma=100 + `PUT /tenant/fee-routing` EXISTEM (migration k1l2m3n4o5p6, ORM, schemas); o gap real é o COMPORTAMENTO (client_share como acréscimo de preço no checkout) — deferido formalmente em plano-estagio-0-completo.md (Decisão D2) | PARCIAL (schema pronto; comportamento deferido) |
| Subcontas Asaas (split) | ⚠️ create_subaccount implementado; tenants pré-Ajuste 9 sem external_account_id; frontend do Ajuste 9 pendente | PARCIAL |

### 2.7 Comissões

| Item | Status | Classificação |
|---|---|---|
| Dois eixos: commission_base × commission_fee_policy (incl. CUSTOM) | ✅ Sprint 12 + migration `k3l4m5n6o7p8` (fee_policy_v2) | — |
| Lifecycle CALCULATED→DUE→PAID / REVERTED + payout (Movement+Entry) | ✅ | — |
| Beneficiary roles SELLER (pacote) / SERVICE_PROVIDER | ✅ comissão SELLER no Sprint 14 | — |
| RECURRING_SELLER (assinaturas) | ❔ não verificado no código do Sprint 15 | PARCIAL (provável) |
| commission.recovery_recorded (recuperação) | ❔ não verificado | não verificado |

### 2.8 CustomerCredit, Pacotes e Assinaturas

| Item | Status | Classificação |
|---|---|---|
| CustomerCredit (cota ≠ saldo), FEFO, lifecycle, expiry worker | ✅ Sprint 13 (FOR UPDATE SKIP LOCKED, ORDER BY expires_at) | — |
| grant_cota com audit, sem receita | ✅ | — |
| Pacotes (compra → payment.confirmed → activate → crédito + comissão SELLER) | ✅ Sprint 14 (package_handler) | — |
| Assinaturas (renewal/overdue workers, OVERDUE→SUSPENDED, rollover) | ✅ Sprint 15 | — |
| Recorrência via Asaas (cobrança no gateway) | ⚠️ renewal_worker cria Payment interno; integração de recorrência nativa Asaas não verificada | PARCIAL |

### 2.9 Financial Core e Gestão Financeira

| Item | Status | Classificação |
|---|---|---|
| Account / Movement / Entry imutáveis + Transfer | ✅ Sprints 6–7 | — |
| ReconciliationRecord + CashCount (ADJUSTED → Entry AJUSTE) | ✅ Sprint 7 | — |
| ExternalStatementEntry (import/match/dismiss) | ❌ não existe e **não aparece em nenhum sprint do plano** | **CRÍTICO** + gap de planejamento |
| Dashboard Gestão Financeira / DRE por categoria | ⚠️ **[ERRATA 2026-06-10]** `aggregate_dre()` + `GET /financial/dre` EXISTEM desde o Sprint 6 (financial_core/service.py:430, router.py:156); o DRE só fica completo (CUSTO/DESPESA reais) após Sprints 17/18 | PARCIAL (não é gap de planejamento) |
| create_manual_adjustment com sensitive_audit_context | ✅ | — |

### 2.10 Estoque, Despesas, Payables

| Item | Status | Classificação |
|---|---|---|
| StockEngine (entradas, saídas VENDA/USO_INTERNO/PERDA/AJUSTE, custo médio ponderado) | ❌ `app/modules/stock/` não existe | **CRÍTICO** (Sprint 17 planejado, não executado) |
| Fornecedores + SupplierOrder | ❌ não existe | **CRÍTICO** |
| Payables (lifecycle OPEN→PARTIALLY_PAID→PAID, installments, workers due_soon/overdue) | ❌ não existe | **CRÍTICO** |
| ExpensesService (PENDENTE→PAGA, recorrência, workers) | ❌ `app/modules/expenses/` não existe | **CRÍTICO** (Sprint 18) |
| Eventos stock.* / expense.* / payable.* | ❌ nenhum emissor/consumidor | **CRÍTICO** |
| FEFO de estoque com lote/expiry `[SCHEMA APENAS]` | ❌ migration não criada (Sprint 25) | PARCIAL (schema exigido) |

### 2.11 Promoções e Cupons

| Item | Status | Classificação |
|---|---|---|
| Promotion/Coupon/CouponRedemption/DiscountApplication | ❌ grep case-insensitive por promotion/coupon em app/: zero arquivos | **CRÍTICO** (Sprint 16 planejado, não executado) |
| Preview no checkout ≠ efetivação no payment.confirmed | ❌ | **CRÍTICO** |
| apply_manual_discount_override (ação sensível) | ❌ | **CRÍTICO** |
| promotions.expiry_scanner worker | ❌ | **CRÍTICO** |

### 2.12 Relacionamento (NPS, Fila, CRM)

| Item | Status | Classificação |
|---|---|---|
| NPS pós-operation.completed (config por tenant) | ❌ nenhum módulo/modelo | **CRÍTICO** |
| Fila de espera (consome eventos de Operações/Estoque) | ❌ nenhum módulo/modelo | **CRÍTICO** |
| CRM: rastreio automático + classificações + insights heurísticos | ❌ `customers` tem ficha básica; sem classificações, sem insights, sem campos custom | **CRÍTICO** |

### 2.13 Comunicação

| Item | Status | Classificação |
|---|---|---|
| CommunicationService (handler + dispatch, templates, canais, quiet hours) | ✅ Sprint 5 + canal EMAIL (Mailtrap/SMTP) | — |
| Audiences (cliente/profissional/owner) por evento | ✅ communicationaudience | — |
| Feature flag use_communication_service default False + chamadas diretas evolution_client | ⚠️ coexistência ainda ativa (dívida registrada); email produção depende de Mailtrap sandbox | PARCIAL |
| Horários permitidos de envio | ✅ quiet hours (transacional bypassa, automático respeita) | — |

### 2.14 Bot WhatsApp

| Item | Status | Classificação |
|---|---|---|
| FSM soberano (16 estados, fluxo de agendamento completo) | ✅ modules/whatsapp + handlers | — |
| IntentClassifier (IA classifica, nunca gera resposta) | ❌ `whatsapp/intent/` não existe; matching textual hardcoded em helpers.py | **CRÍTICO** |
| Intenções COMPRAR_PRODUTO / COMPRAR_PACOTE | ❌ sem handlers | **CRÍTICO** |
| Catálogo dinâmico de intenções por tenant | ❌ hardcoded | **CRÍTICO** |
| Escalonamento humano (EM_ATENDIMENTO_HUMANO → RESOLVIDA) | ⚠️ state HUMANO existe; sem transição RESOLVIDA (expira por TTL); sem inbox no painel (sem endpoint backend de conversas) | PARCIAL |
| API oficial Meta Cloud como opção do tenant | ⚠️ apenas Evolution API (global, Opção A registrada); Meta Cloud ausente | PARCIAL |

### 2.15 Portal do Cliente e Painel Owner

| Item | Status | Classificação |
|---|---|---|
| Portal do Cliente (auth cliente, dashboard, cotas, consentimentos, métodos de pagamento) | ❌ nenhum endpoint `/customer/*`; role CLIENT existe no enum mas sem fluxo | **CRÍTICO** |
| Painel Owner backend (tenants TRIAL/ACTIVE/SUSPENDED/CHURNED, saúde, integrações, impersonation, replay, feature flags) | ❌ nenhum endpoint `/owner/*` ou `/platform/*`; PLATFORM_OWNER autentica mas não tem superfície | **CRÍTICO** + gap de planejamento (backend) |
| Impersonation controlada (time-boxed, auditada) | ❌ | **CRÍTICO** |
| Monetização | 🔮 deferido pela própria visão (Pendência 1) | FORA_ESCOPO_0 |

### 2.16 Infraestrutura

| Item | Status | Classificação |
|---|---|---|
| EventBus in-process + ProcessedIdempotencyKey (TTL 90d + cleanup) | ✅ | — |
| Envelope canônico de evento (event_id, actor, occurred_at) | ❔ eventos publicados com idempotency_key; aderência completa ao envelope da Parte 5 não auditada | PARCIAL (provável) |
| Workers obrigatórios: reminder, session_cleanup, subscription_renewal, customer_credit_expiry, idempotency_cleanup | ✅ todos no beat_schedule | — |
| Workers obrigatórios ausentes: promotions.expiry_scanner, expense due_soon/overdue, payable due_soon/overdue | ❌ dependem dos Sprints 16–18 | **CRÍTICO** |
| Observabilidade (logging estruturado + RequestContextMiddleware) | ✅ middleware/request_context.py + core/logging.py; inicialização Sentry presente em main.py (não inspecionada em detalhe) | — |
| Storage Supabase, rate limiting, security headers, bcrypt 12 | ✅ | — |
| Testes mínimos do Estágio 0 (FSM completo, conflito, DEPOSIT e2e, comissão 2 eixos, idempotência) como suite de contrato | ❌ testes unitários por sprint existem (~460+); suite de contrato dedicada não (Sprint 25 pulado) | PARCIAL |

---

## 3. Gaps CRÍTICOS para o Estágio 0

Ordenados por impacto (todos previstos pela visão como obrigatórios no Estágio 0 e completamente ausentes):

1. **Promoções e Cupons** — domínio interno obrigatório; bloqueia também `discount_breakdown` no payload de `payment.confirmed`. (Sprint 16 planejado)
2. **Estoque + Fornecedores + Payables** — domínio interno obrigatório; sem ele os 4 fatos econômicos (Financial-1) não existem e o DRE fica sem CUSTO. (Sprint 17 planejado)
3. **Despesas** — módulo default ativo no painel; sem ele a Gestão Financeira não tem OpEx. (Sprint 18 planejado)
4. **Identidade Paladino** (PaladinoIdentity + PhoneIdentityResolver + ConsentRecord + token de cartão por cliente) — fundação dos 3 canais cliente-facing; o modelo atual (Customer por tenant) divergirá da visão quanto mais tarde for migrado.
5. **Painel Owner Paladino — backend** (tenants, saúde, impersonation, replay, feature flags) — núcleo "sempre presente" na visão; hoje a operação da plataforma é manual via banco.
6. **Portal do Cliente — backend** — canal cliente-facing do núcleo.
7. **NPS, Fila de espera, CRM** — módulos ativáveis previstos; nenhum modelo existe.
8. **Bot WhatsApp: IntentClassifier + intenções de compra + catálogo dinâmico** — invariantes 2 e 5 do canal não atendidas.
9. **Link de gestão com token único** (remarcação/cancelamento sem login) — requisito explícito do Link Público; zero ocorrências no código.
10. **ExternalStatementEntry** (import/match/dismiss de extrato) — parte do Grupo Financeiro do RBAC e da reconciliação Level 1.
11. **Workers de vencimento** (expense/payable due_soon+overdue, promotions expiry) — consequência dos itens 1–3.

---

## 4. Gaps PARCIAIS

| Gap | O que existe | O que falta |
|---|---|---|
| Fluxo DEPOSIT (sinal) | DepositPolicy por serviço/global | Validação ponta a ponta (sinal → FIRME → saldo no COMPLETED → retenção em NO_SHOW → `commission_on_retained_deposit`); teste de contrato |
| Estorno | refund contábil + refund_reason | `provider.refund()` nunca chamado — Asaas não processa o estorno (dívida registrada) |
| TenantFeeRoutingPolicy | fee_percentage/fee_flat (10 fontes) + colunas 3-vias com soma=100 **[ERRATA: schema 3-vias já existe]** | Comportamento do client_share (acréscimo no checkout) — deferido (Decisão D2 do plano) |
| RBAC granular | require_role/require_action + permission_overrides | Matriz completa da Parte 4 (limites de valor para OPERATOR, scopes de PROFESSIONAL por domínio) não auditada/garantida |
| Escalonamento humano no bot | state HUMANO (bot silencia) | Transição RESOLVIDA; inbox de atendimento no painel (requer endpoints backend de conversas) |
| Comunicação | CommunicationService completo | Remoção das chamadas diretas evolution_client; email transacional de produção (Mailtrap é sandbox) |
| Gestão Financeira | Movements/Entries/Transfers/Reconciliation/CashCount consultáveis | Endpoint DRE agregado por categoria/período (backend) |
| Subcontas Asaas | create_subaccount + colunas owner_* | Frontend Ajuste 9; backfill de tenants sem external_account_id |
| Schema `[SCHEMA APENAS]` | accounting_mode ACCRUAL bloqueado ✅; roles de plataforma no enum ✅ | Migrations de Location, StockBatch/expiry, Encomenda (FSM), OperationProfessional (multi-prof), variações complexas — Sprint 25 pulado |
| Suite de testes do Estágio 0 | ~460+ testes unitários por sprint | Suite de contrato dedicada (5 metas da Parte 10) |
| Bot: API oficial | Evolution API (não oficial, global) | Opção Meta Cloud por tenant |
| Assinaturas via Asaas | renewal_worker interno cria Payments | Recorrência nativa do gateway não verificada/confirmada |

---

## 5. Itens da visão NÃO cobertos pelo plano de execução (gaps de planejamento)

O plano de execução vigente (`plano-execucao-fase3.md`, Sprints 11–18 + roadmap com Sprints 19–25, 2.0 e 2.6) cobre a maior parte da visão. Os itens abaixo **não aparecem em nenhum sprint**:

1. **Painel Owner Paladino — backend.** O Sprint 24 do roadmap é frontend (`/owner/*` no painel); nenhum sprint backend define endpoints de tenants, saúde operacional, impersonation, replay controlado ou feature flags. A visão trata como núcleo "sempre presente".
2. **ExternalStatementEntry** (import/match/dismiss de extrato externo) — listado no RBAC Grupo 1 e na reconciliação; ausente de todos os briefs e planos.
3. **Roteamento de taxas 3-vias** — **[ERRATA 2026-06-10]** o schema 3-vias EXISTE desde o Sprint 6 (migration k1l2m3n4o5p6, validação soma=100, endpoint PUT). O gap remanescente é só o comportamento do `client_share` (acréscimo no preço do checkout), deferido formalmente para o Estágio 1 na Decisão D2 do plano-estagio-0-completo.md. `professional_share` já é coberto pelo eixo `commission_fee_policy CUSTOM` (não duplicar — Princípio 6).
4. **Link de gestão com token único** — o fluxo do Link Público nos sprints A–F/G13 não inclui o token de gestão sem login; nenhum sprint o prevê explicitamente.
5. **Inbox de atendimento humano no painel** (backend de conversas escaladas) — Sprints 2.0/2.6 cobrem o classificador, mas a superfície "Atendimento humano" do Bloco Operação não tem sprint backend.
6. **Endpoint DRE / dashboard agregado (backend)** — Sprint 19 é UI; assume um backend de agregação que nenhum sprint backend entrega.
7. **Eventos de promoção com `DiscountApplication` + `discount_breakdown` no payment.confirmed** — o Sprint 16 planejado usa `coupon_code` + `applied_promotion_ids` JSONB em payments, modelo mais simples que o da visão (DiscountApplication com sequence e base_amount_at_application). Divergência de fidelidade, não de ausência.
8. **Recorrência nativa Asaas para assinaturas** — Sprint 15 implementou renovação interna; a visão diz "recorrência via Asaas". Nenhum sprint posterior planeja a integração.

Itens corretamente fora do plano por decisão da própria visão (não são gaps): monetização, Saldo/carteira, conta digital, Bot Tenant, ACCRUAL, API pública, multi-unidade na UI.

---

## 6. Recomendação de Priorização

**Onda 1 — Completar domínios internos obrigatórios (plano já existe, só executar):**
1. Sprint 18 — Despesas (dependência mínima: Financial Core ✅)
2. Sprint 17 — Estoque + Fornecedores + Payables
3. Sprint 16 — Promoções e Cupons (considerar elevar fidelidade à visão: DiscountApplication em vez de JSONB)
4. Sprint 25 — Migrations `[SCHEMA APENAS]` + suite de testes de contrato (FSM, conflito, DEPOSIT e2e, comissão 2 eixos, idempotência)

**Onda 2 — Fechar dívidas que corrompem dados/dinheiro em produção:**
5. `provider.refund()` no estorno Asaas; backfill subcontas (Ajuste 9 frontend)
6. Link de gestão com token (pequeno, alto valor para o cliente final)
7. Workers de vencimento (entram naturalmente com 16–18)

**Onda 3 — Planejar o que não tem plano (gaps de planejamento — exigem brief novo):**
8. Painel Owner backend (mínimo: lista/status de tenants, saúde, audit cross-tenant; impersonation pode ser fase 2 da onda)
9. Identidade Paladino (PaladinoIdentity + PhoneIdentityResolver + ConsentRecord) — fazer **antes** do Portal do Cliente e do crescimento da base, pois migra o modelo de Customer
10. ExternalStatementEntry + endpoint DRE backend
11. Decidir: roteamento 3-vias de taxas agora ou registrar formalmente como Estágio 1

**Onda 4 — Relacionamento e canais (após backend completo):**
12. NPS + Fila (Sprint 22), CRM (Sprint 23), IntentClassifier (2.0/2.6), inbox de atendimento humano, Portal do Cliente (Sprint 21)

---

*Baseado em evidências diretas: listagem de `app/modules/`, `migrations/versions/`, greps por entidades (Promotion/Coupon/Payable/Expense/Consent/IntentClassifier/manage_token), `app/workers/`. Itens marcados "não verificado" não foram inspecionados linha a linha e não devem ser assumidos como implementados ou ausentes sem verificação no fonte.*
