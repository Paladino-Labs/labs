# Plano de execução — Estágio 0
**Gerado em:** 2026-05-22
**Baseado em:** `visao-estagio-0.md` v1 (derivado de `visao-produto-paladino.md` v23.0) · Relatório de varredura 2026-05-21

---

## Resumo executivo

O backend tem fundação operacional para **agendamento** (BookingEngine FSM, multi-tenant em 442 ocorrências/50 arquivos, snapshots imutáveis, estados terminais protegidos), **bot WhatsApp** (13 handlers, FSM soberano sobre input), **link público** (FSM via slug), **observabilidade** (Sentry + JSON logs) e **CORS restrito**. O frontend (Next.js 16) tem 8 áreas básicas no painel e o Link Público responsivo.

Tudo que toca **dinheiro real, contratos comerciais e contabilidade interna** está ausente: Financial Core (Account/Movement/Entry/Transfer), Pagamentos (Asaas), Estoque, Despesas, Comissões com dois eixos, CustomerCredit, Pacotes, Assinaturas, Promoções/Cupons, Reconciliação, CashCount. Também não existem: sistema de eventos com idempotência, Comunicação como handler+dispatch, RBAC granular por ação+escopo, Identidade Paladino de 3 níveis, ConsentRecord, Portal do Cliente, Painel Owner Paladino, FSM expandida de Operações (DRAFT/REQUESTED/soft↔firme), Catálogo com opt-ins (preço/duração por profissional, variantes), e workers com garantia de entrega.

**Estimativa:** 25 sprints de 2 semanas (~50 semanas / ~12 meses), com 4 sprints críticos de hardening + fundação antes de qualquer construção de módulo de valor.

---

## Tabela de GAP

### Parte 4 — RBAC: papéis e permissões

| Item | Estado | O que falta | Dependências |
|------|--------|-------------|--------------|
| Roles do tenant (OWNER, ADMIN, OPERATOR, PROFESSIONAL, CLIENT) | ⚠️ Parcial | Hoje só `ADMIN`, `PROFESSIONAL`, `CLIENT` no enum (string solto em `User.role`). Faltam `OWNER` (do tenant) e `OPERATOR`. Criar enum tipado em `app/domain/enums/user_role.py` | Migration: `User.role` enum + `User.company_id` nullable |
| Roles de plataforma (PLATFORM_OWNER) | ❌ Ausente | Sem `PLATFORM_OWNER`. `User.company_id` é `nullable=False` (`user.py:13`) e precisa virar `nullable=True`. Script `create_owner.py` apenas cria User comum | Migration `User.company_id` nullable + `require_platform_owner` dep |
| Roles `[SCHEMA APENAS]` (PLATFORM_SUPPORT/BILLING/READONLY) | ❌ Ausente | Criar valores no enum, sem rota nem service | Enum UserRole |
| Anti-escalonamento (OWNER único, ADMIN não eleva, etc.) | ❌ Ausente | Endpoint `users/router.py` aplica `require_admin` binário. Faltam regras de quem-pode-atribuir-quem, "último OWNER ativo", convite por e-mail | RBAC v2 |
| RBAC camada 2 — ação + escopo (ex: PROFESSIONAL = ações amplas em escopo próprio) | ❌ Ausente | Apenas `require_admin` em `core/deps.py:43`. Sem `require_action(action, scope)`. Sem `Permission`, sem matrix de permissões | Modelo `Permission`/`RoleBinding` + dependency `require_action` |
| `apply_manual_discount_override` (ação sensível com audit) | ❌ Ausente | Sem desconto, sem audit, sem `sensitive_audit_context` | Promoções/Cupons + Audit append-only |
| `create_manual_adjustment` (Financial) | ❌ Ausente | Sem Financial Core | Financial Core |
| `IntegrationCredential` write-only/masked (RBAC-3) | ❌ Ausente | `WhatsAppConnection` armazena dados não-cifrados. Sem rotate/revoke API | Refactor de credentials + KMS/encryption |
| Audit append-only (RBAC-4) | ⚠️ Parcial | `AppointmentStatusLog` existe e é insert-only. Sem tabela genérica de Audit para outros domínios; sem `view_audit`/`export_audit` | Tabela `audit_log` genérica |

### Parte 5 — Sistema de eventos

| Item | Estado | O que falta | Dependências |
|------|--------|-------------|--------------|
| Event bus in-process | ❌ Ausente | Grep `event_bus\|EventBus\|publish_event` em `app/`: zero matches. Tudo é chamada síncrona direta (`notifications.py` → `evolution_client.send_text`) | Decisão de implementação (in-process registry + sync dispatch) |
| Envelope canônico (event_id, event_type, occurred_at, company_id, idempotency_key, actor, payload) | ❌ Ausente | Sem modelo | Event bus |
| `ProcessedIdempotencyKey` (UNIQUE key+consumer+company_id, TTL 90d) | ❌ Ausente | Sem tabela | Event bus + worker de cleanup |
| Catálogo de eventos PaymentsEngine (`payment.confirmed`, `.failed`, `.refunded`, etc.) | ❌ Ausente | Sem Pagamentos | Pagamentos |
| Catálogo de eventos CommissionEngine (`commission.calculated/due/paid/reverted/recovery_recorded`) | ❌ Ausente | Sem Comissões | Comissões |
| Catálogo de eventos StockEngine | ❌ Ausente | Sem Estoque | Estoque |
| Catálogo de eventos ExpensesService/PayablesService | ❌ Ausente | Sem Despesas | Despesas |
| Catálogo de eventos CashCount, FinancialCore | ❌ Ausente | Sem Financial Core | Financial Core |
| Catálogo de eventos Agenda (soft_reservation.created/expired, reservation.confirmed/released/no_show, etc.) | ❌ Ausente | Hoje agenda é síncrona com BookingEngine; sem soft reservation com TTL nem promoção SOFT→FIRME | Agenda expandida + Operations FSM |
| Replay forçado proibido em consumers financeiros | ❌ Ausente | Sem replay nem trava | Painel Owner + Financial Core |

### Parte 6 — Módulos detalhados

| Item | Estado | O que falta | Dependências |
|------|--------|-------------|--------------|
| **Catálogo — Serviços (cadastro básico)** | ✅ Implementado | `Service(name, price, duration, description, image_url, active)` + `ProfessionalService(commission_percentage)`. Modos operacionais Agendamento já cobertos | — |
| **Catálogo — Serviços (opt-ins)** | ❌ Ausente | Sem preço por profissional, sem duração por profissional, sem variantes simples, sem tempo de preparação/descanso. Sem `commission_base_value` por serviço | Migration `ServicePricingOverride`/`ServiceVariant` + service expansion |
| **Catálogo — Produtos (cadastro)** | ⚠️ Parcial | `Product(name, description, price, image_url, active)` existe. Faltam: código de barras `[SCHEMA APENAS]`, categorização opt-in, variações opt-in, múltiplas imagens (até 5), modos operacionais (Venda direta, Encomenda) | Migration + service expansion |
| **Agenda — WorkingHour + ScheduleBlock** | ✅ Implementado | `WorkingHour(weekday, opening_time, closing_time)` + `ScheduleBlock(start_at, end_at, reason)`. Cálculo de slots em `availability/service.py` | — |
| **Agenda — Jornada × Exceção × Bloqueio (ordem de cálculo)** | ⚠️ Parcial | Hoje há jornada (WorkingHour) e bloqueio (ScheduleBlock). **Falta:** modelo `ScheduleException` (substitutiva ou aditiva); ordem formal de 8 passos do cálculo (incluindo soft/firme/ocupação direta); ainda não calcula com soft reservation | Agenda expandida |
| **Agenda — Reserva soft + firme (FSM com TTL)** | ❌ Ausente | Apenas `BookingSession` com TTL de 15min (web), 30min (whatsapp), 2h (admin). Não há `Reservation` model com soft↔firme separado. Promoção SOFT→FIRME hoje é implícita no `confirm_booking` | Agenda + Operations FSM |
| **Agenda — Ocupação direta (DIRECT mode)** | ❌ Ausente | Não existe | Operations FSM |
| **Agenda — Overbooking manual com motivo+audit** | ❌ Ausente | Engine rejeita sobreposição sem caminho de override | Audit + Operations |
| **Agenda — `EXCLUDE CONSTRAINT` no banco (btree_gist + tsrange)** | ❌ Ausente 🔴 | Proteção só na aplicação (`_assert_slot_available` + `SELECT FOR UPDATE NOWAIT`). Grep `btree_gist\|EXCLUDE\|tsrange` zero matches em código | Migration |
| **Operações — FSM (DRAFT → REQUESTED → CONFIRMED → IN_PROGRESS → COMPLETED/CANCELLED/NO_SHOW/FAILED)** | ⚠️ Parcial | `AppointmentStatus` tem apenas `SCHEDULED → IN_PROGRESS → COMPLETED/CANCELLED/NO_SHOW`. Faltam: `DRAFT`, `REQUESTED`, `FAILED`; transições com timeouts (`draft_expiration_minutes`, `requested_expiration_hours`, `no_show_threshold_minutes`); `auto_confirm_rules` | Refactor de Appointment model → Operation + migration |
| **Operações — Tipos (SERVICE×SCHEDULED, SERVICE×DIRECT, PRODUCT×SALE)** | ❌ Ausente | Hoje só `SERVICE×SCHEDULED` implícito. Sem `operation_type` no model | Refactor de Appointment → Operation |
| **Pagamentos — Asaas adapter** | ❌ Ausente | Grep `asaas\|payment_order\|PaymentProvider`: zero matches | SDK Asaas + provider abstraction |
| **Pagamentos — PaymentSources (Cartão, Pix, Boleto, Dinheiro, Maquininha)** | ❌ Ausente | Sem nenhum | Asaas adapter + Manual entry |
| **Pagamentos — Modelos de cobrança (POST_DELIVERY, DEPOSIT, PREPAID, PREPAID_REFUNDABLE)** | ❌ Ausente | Flag `require_payment_upfront` em `CompanySettings:22` sem implementação | Pagamentos base |
| **Pagamentos — Sinal/depósito (DEPOSIT)** | ❌ Ausente | Sem `deposit_policy` por serviço, sem fluxo de sinal | Pagamentos + Agenda soft/firme |
| **Pagamentos — Webhook idempotente** | ❌ Ausente | Sem endpoint webhook | Event bus + ProcessedIdempotencyKey |
| **Pagamentos — Token de cartão vinculado ao cliente** | ❌ Ausente | Sem tokenização nem autorização por tenant | Identidade Paladino + ConsentRecord |
| **Pagamentos — TenantFeeRoutingPolicy** | ❌ Ausente | Sem modelo | Financial Core |
| **Estoque — Cadastro, entradas, saídas (VENDA/USO/PERDA/AJUSTE), custo médio** | ❌ Ausente | Grep `stock\|inventory\|estoque`: zero matches em `app/` | Financial Core (gera Entry CUSTO) |
| **Estoque — Fornecedores + Payables** | ❌ Ausente | Sem `Supplier`, sem `Payable` | Estoque |
| **Estoque — Custos como Entry sem Movement** | ❌ Ausente | Sem Financial Core | Financial Core |
| **Comissões — Dois eixos (commission_base × commission_fee_policy)** | ⚠️ Parcial | Só `commission_percentage` por `ProfessionalService` + `default_commission_percentage` em `CompanySettings`. Função `calculate_commission(price, %)` em `domain/services/financial.py` (8 linhas). **Faltam:** eixos BASE (`SERVICE_REFERENCE_PRICE`/`ALLOCATED_COTA_VALUE`) e TRATAMENTO (`GROSS_OF_FEES`/`NET_OF_FEES`/`CUSTOM`); beneficiários (SERVICE_PROVIDER/SELLER/RECURRING_SELLER) | Pagamentos + CustomerCredit + Pacotes/Assinaturas |
| **Comissões — Lifecycle (CALCULATED → DUE → PAID, com REVERTED antes de PAID)** | ❌ Ausente | Sem lifecycle, sem `Commission` model | Event bus + Financial Core |
| **Comissões — Payout mensal configurável** | ❌ Ausente | Sem janela de payout | Comissões base |
| **CustomerCredit — Cota como direito de uso (não saldo)** | ❌ Ausente | Sem modelo. Princípio Credit-1 ainda não materializado | Pacotes/Assinaturas/grant_cota |
| **CustomerCredit — FEFO (First Expiry, First Out)** | ❌ Ausente | Sem algoritmo de consumo prioritário | CustomerCredit base |
| **CustomerCredit — Lifecycle (ACTIVE → EXHAUSTED/EXPIRED/REVOKED)** | ❌ Ausente | Sem lifecycle | CustomerCredit + worker de expiração |
| **Pacotes — PackagePurchase → grant CustomerCredit** | ❌ Ausente | Sem `Package` model | CustomerCredit + Pagamentos |
| **Pacotes — Vendedor (SELLER) vs Prestador (SERVICE_PROVIDER) como comissões distintas** | ❌ Ausente | Sem distinção; só `professional_id` em appointment | Comissões |
| **Assinaturas — Recorrência via Asaas** | ❌ Ausente | Sem `Subscription` model | Pagamentos Asaas |
| **Assinaturas — Lifecycle (ACTIVE/PAUSED/OVERDUE/SUSPENDED/CANCELLED)** | ❌ Ausente | Sem lifecycle | Assinaturas base |
| **Assinaturas — Renovação emite `subscription.renewed` (não `operation.completed`)** | ❌ Ausente | Sem evento | Event bus + Assinaturas |
| **Promoções/Cupons — Estrutura completa (Promotion, Coupon, CouponRedemption, DiscountApplication)** | ❌ Ausente | Sem nenhum modelo | Pagamentos + Operations |
| **Promoções/Cupons — Algoritmo (cumulative vs exclusive, CUSTOMER_FAVORABLE, preview ≠ efetivação)** | ❌ Ausente | Sem algoritmo | Promoções base |
| **Promoções/Cupons — Manual_discount_override** | ❌ Ausente | Sem ação | Promoções base + Audit |
| **Financial Core — Account (CAIXA/ACQUIRER/BANK)** | ❌ Ausente | Sem modelo | — |
| **Financial Core — Movement (INFLOW/OUTFLOW/TRANSFER_IN/TRANSFER_OUT)** | ❌ Ausente | Sem modelo. Campos `total_amount`/`financial_status` em `appointment.py:29-38` são insuficientes para Financial Core | Account |
| **Financial Core — Entry (RECEITA/CUSTO/DESPESA/TAXA/COMISSAO/ESTORNO/AJUSTE) com direção (ADDS/SUBTRACTS) e category** | ❌ Ausente | Sem modelo | Account |
| **Financial Core — Transfer (cria 2 Movements atômicos)** | ❌ Ausente | Sem modelo | Account |
| **Financial Core — Categorias defaults de RECEITA/DESPESA** | ❌ Ausente | Sem enums | Financial Core |
| **Financial Core — Imutabilidade após criação (Movement/Entry)** | ❌ Ausente | N/A | RBAC-2 |
| **Gestão Financeira — Dashboard (receitas/despesas/margem/lucro)** | ❌ Ausente | Sem página `painel/app/(dashboard)/financial/` | Financial Core |
| **Gestão Financeira — Reconciliação manual Level 1** | ❌ Ausente | Sem `ReconciliationRecord` | Financial Core |
| **Despesas — Lançamentos com categoria, recorrência, fornecedor** | ❌ Ausente | Sem `Expense` model | Financial Core |
| **Despesas — Lifecycle (PENDENTE → PAGA/CANCELLED)** | ❌ Ausente | Sem lifecycle | Despesas base |
| **Despesas — Eventos (created/due_soon/overdue/paid/cancelled)** | ❌ Ausente | Sem worker `expense.due_soon/overdue` | Event bus + Workers |
| **CashCount — Registro de contagem + resolução de divergência** | ❌ Ausente | Sem modelo | Financial Core |

### Parte 7 — Identidade e canais cliente-facing

| Item | Estado | O que falta | Dependências |
|------|--------|-------------|--------------|
| Identidade Paladino — 3 níveis (logado / não-logado / migração) | ❌ Ausente | Hoje há `Customer` por tenant + `User` separado. Sem `PaladinoIdentity` cross-tenant; cliente final não tem login | Refactor de Customer + introdução de `PaladinoIdentity` model |
| PhoneIdentityResolver (normalização E.164 + customer_id estável) | ⚠️ Parcial | `customers/service.py:get_or_create_by_phone` faz upsert por telefone. **Falta:** normalização E.164 explícita, `possible_aliases`, distinção `phone_e164` vs `phone_national_normalized` | Refactor `customers/service.py` + lib `phonenumbers` |
| ConsentRecord (COMMUNICATION/DATA_PROCESSING/PAYMENT_STORAGE/MARKETING) | ❌ Ausente | Grep `ConsentRecord\|consent_record\|lgpd`: zero matches | Identidade Paladino |
| Token de cartão vinculado ao CLIENTE (não tenant) — exige PAYMENT_STORAGE consent | ❌ Ausente | Sem implementação | Pagamentos + Identidade + ConsentRecord |
| Link Público — Vitrine completa (logo, fotos, avaliação, botão Agendar, formas de pagamento) | ⚠️ Parcial | `painel/app/book/[slug]/page.tsx` + `BookingFlow.tsx` cobrem vitrine, agendar, confirmação. **Faltam:** abas Produtos, Pacotes, Assinaturas, Avaliações (NPS); aceite simplificado de Termos como passo dedicado; OG tags | Pagamentos + Pacotes + Assinaturas + NPS |
| Link Público — Cronômetro TTL no checkout | ⚠️ Parcial | Existe TTL na BookingSession mas não é exibido como cronômetro visível ao cliente | Frontend |
| Link Público — Link de gestão (remarcação/cancelamento com token único, sem login) | ❌ Ausente | Sem rota `/manage/[token]` no link público | Frontend + token de gestão |
| Bot WhatsApp — Invariantes (FSM soberano, IA apenas classificação) | ✅ Implementado | FSM via 13 handlers em `whatsapp/handlers/`. Sem IA — comportamento correto para Estágio 0 | — |
| Bot WhatsApp — Intenções AGENDAR/COMPRAR_PRODUTO/COMPRAR_PACOTE/CONSULTAR/REMARCAR/CANCELAR/FALAR_COM_HUMANO | ⚠️ Parcial | Cobre AGENDAR, REMARCAR, CANCELAR, CONSULTAR via menu_principal. **Faltam:** COMPRAR_PRODUTO, COMPRAR_PACOTE, FALAR_COM_HUMANO com escalonamento real | Pacotes + handler de escalonamento humano |
| Bot WhatsApp — Estado da conversa (BOT_ATIVO / EM_ATENDIMENTO_HUMANO / RESOLVIDA) | ❌ Ausente | Sem suporte a "EM_ATENDIMENTO_HUMANO" (humano por conversa) | Inbox de atendimento no painel + estado adicional em `BotSession` |
| Bot WhatsApp — Catálogo dinâmico de intenções por tenant | ❌ Ausente | Intenções hardcoded nos handlers | Refactor `whatsapp/input_parser.py` |
| Bot WhatsApp — Formato (botões max 3, list até 10, paginação) | ✅ Implementado | `response_formatter.py` + `sender.py` cobrem | — |
| Portal do Cliente — Autenticação (e-mail+senha, magic link, Google, Apple) | ❌ Ausente | Sem `/customer/login` nem rota dedicada | Identidade Paladino |
| Portal do Cliente — Dashboard, Histórico, Cotas, Remarcação, Consentimentos, Métodos de pagamento, Perfil | ❌ Ausente | Sem nenhuma rota | Identidade + CustomerCredit + Pagamentos |

### Parte 8 — Painéis

| Item | Estado | O que falta | Dependências |
|------|--------|-------------|--------------|
| Painel do Tenant — Bloco Operação (Home, Agenda, Operações, Fila, Atendimento humano) | ⚠️ Parcial | Home/Dashboard, Agenda (via lista de appointments), Operações (lista) existem. **Faltam:** Fila de espera, Atendimento humano (inbox) | Fila + Bot WhatsApp escalonamento |
| Painel do Tenant — Bloco Relacionamento (Clientes/CRM, Comunicação) | ⚠️ Parcial | Customers existe com lista + ficha básica. **Faltam:** CRM com classificações automáticas e insights; Comunicação (templates, canais, envios) | CRM + Comunicação |
| Painel do Tenant — Bloco Comercial (Catálogo, Pacotes/Assinaturas, Promoções/Cupons) | ⚠️ Parcial | Catálogo (services, products) existe. **Faltam:** Pacotes/Assinaturas, Promoções/Cupons | Pacotes + Assinaturas + Promoções |
| Painel do Tenant — Bloco Financeiro (Pagamentos/Cobranças, Gestão Financeira, Despesas, Estoque, Comissões) | ❌ Ausente | Nenhum dos 5 módulos tem UI | Backend Financial Core + Pagamentos + Despesas + Estoque + Comissões |
| Painel do Tenant — Bloco Administração (Profissionais, Usuários, Configurações, Relatórios, Audit) | ⚠️ Parcial | Profissionais e Configurações (settings/profile) existem. **Faltam:** Usuários/Acessos com RBAC (anti-escalonamento), Relatórios, Audit | RBAC v2 + Audit |
| Painel — Role-aware (conteúdo varia por papel) | ❌ Ausente | `Sidebar.tsx` lista todos os links sem filtro por role. `useAuth.ts` apenas guarda token | Refactor Sidebar + JWT com role completo |
| Painel — Dashboard por papel (OWNER/ADMIN/OPERATOR/PROFESSIONAL) | ❌ Ausente | `dashboard/page.tsx` único para todos | Frontend role-aware |
| Painel — Panel-1 (zero lógica de negócio no frontend) | ✅ Implementado | Verificado por grep — nenhum cálculo financeiro no painel | — |
| Painel Owner — Lista de tenants com status (TRIAL/ACTIVE/SUSPENDED/CHURNED) | ❌ Ausente | Sem rota `/owner` no painel; sem endpoint `/owner/tenants` no backend | RBAC v2 + PLATFORM_OWNER role |
| Painel Owner — Saúde operacional (métricas por tenant) | ❌ Ausente | — | Painel Owner base + observabilidade ampliada |
| Painel Owner — Integrações (status Asaas, WhatsApp API) | ❌ Ausente | — | Pagamentos + WhatsApp |
| Painel Owner — Impersonation controlada (time-boxed, audit, read-only default, escalation com motivo) | ❌ Ausente | Sem JWT especial de impersonation; sem audit cross-tenant | RBAC v2 + Audit |
| Painel Owner — Replay controlado (replay normal, replay forçado proibido em financeiros) | ❌ Ausente | Sem replay | Event bus |
| Painel Owner — Feature flags / Módulos por tenant | ❌ Ausente | Não há `ModuleActivation` model | RBAC v2 |

### Parte 9 — Módulos de relacionamento

| Item | Estado | O que falta | Dependências |
|------|--------|-------------|--------------|
| CRM — Dados rastreados automaticamente (histórico, frequência, último atendimento, profissional preferido, ticket médio) | ❌ Ausente | Ficha de cliente em `customers/[id]/page.tsx` mostra dados básicos. Sem agregações | Endpoint `customers/{id}/summary` + frontend |
| CRM — Dados curados (anotações, classificação manual, campos custom) | ⚠️ Parcial | `Customer.notes` existe. Sem classificação manual nem campos custom | Migration + service |
| CRM — Classificações automáticas (novo/frequente/VIP/em risco/recuperado) | ❌ Ausente | Sem cálculo | CRM agregações |
| CRM — Insights (em risco de churn, janela de retorno, sugestão de remarcação/pacote/produto) | ❌ Ausente | Heurísticas não existem | CRM + Pacotes |
| CRM — Pontos de aparição no painel (badge na agenda, sugestões ao criar agendamento, sugestões pós-COMPLETED, ficha do cliente, dashboard agregado) | ❌ Ausente | Painel não exibe nada disso | Frontend |
| NPS — Trigger após `operation.completed` | ❌ Ausente | Sem evento `operation.completed` (FSM atual usa SCHEDULED→COMPLETED sem evento) | Operations FSM + Event bus |
| NPS — Configurações (canal, delay, visibilidade, alertas) | ❌ Ausente | Sem `NpsConfig` | NPS base |
| Fila de espera — Eventos que ativam (cancelamento/remarcação libera slot; produto reabastecido) | ❌ Ausente | Sem `Waitlist` | Event bus + Operations + Estoque |
| Fila de espera — Lógica de prioridade, canais, comportamento, escopo | ❌ Ausente | — | Fila base |
| Fila de espera — Verificação de operação ativa equivalente antes de notificar | ❌ Ausente | — | Fila + Operations |
| Comunicação — Capacidade fundacional (handler + dispatch) | ⚠️ Parcial | `notifications.py` é placeholder; mensagens hardcoded em `whatsapp/messages.py` e handlers. **Faltam:** sistema de templates, canais configuráveis, audiências, horários permitidos (não enviar 22h-8h) | Refactor `notifications.py` → `CommunicationService` |

### Parte 10 — Infraestrutura

| Item | Estado | O que falta | Dependências |
|------|--------|-------------|--------------|
| Event bus in-process + handlers por event type | ❌ Ausente 🔴 | — | — |
| `ProcessedIdempotencyKey` (UNIQUE key+consumer+company_id, TTL 90d) | ❌ Ausente 🔴 | — | Event bus |
| Worker `reminder_worker` — retry com backoff exponencial | ⚠️ Parcial | Existe em `workers/reminder_worker.py:71-76` mas é loop `while True + asyncio.sleep`, sem retry exponencial, sem DLQ | Celery+Redis ou equivalente |
| Worker `session_cleanup_worker` — expira reservas soft | ⚠️ Parcial | Existe em `workers/session_cleanup_worker.py`. Hoje só limpa `bot_sessions` expiradas. **Falta:** expirar reservas soft de Agenda + BookingSessions | Agenda soft/firme |
| Worker `subscription_renewal_worker` — cobrança recorrente | ❌ Ausente | — | Assinaturas + Asaas |
| Worker `promotions.expiry_scanner` — move Promotion/Coupon para EXPIRED | ❌ Ausente | — | Promoções |
| Worker `expense.due_soon/overdue` — alertas de vencimento | ❌ Ausente | — | Despesas |
| Worker `payable.due_soon/overdue` — alertas de vencimento de payables | ❌ Ausente | — | Estoque + Payables |
| Worker `customer_credit.expiry_worker` — expira cotas | ❌ Ausente | — | CustomerCredit |
| Worker `processed_idempotency_key.cleanup_worker` — TTL 90 dias | ❌ Ausente | — | ProcessedIdempotencyKey |
| Multi-tenant — `company_id` em todas as queries | ✅ Implementado | 442 ocorrências em 50 arquivos. Toda query inspecionada filtra | — |
| Multi-tenant — `get_current_company_id` tratando `PLATFORM_OWNER` (`company_id=NULL`) | ❌ Ausente | `core/deps.py:38` retorna `user.company_id` direto; quebra para PLATFORM_OWNER | RBAC v2 |
| Multi-tenant — `EXCLUDE CONSTRAINT` no banco (btree_gist) | ❌ Ausente 🔴 | Grep zero matches | Migration |
| Observabilidade — Sentry SDK + logs JSON com `request_id`/`company_id`/`user_id` | ✅ Implementado | `main.py:21-30` + `core/logging.py` + `middleware/request_context.py` | — |
| Storage — Uploads em Supabase Storage (não volume Docker) | ❌ Ausente 🔴 | `main.py:113-114` monta `static/uploads/` local. Sem SDK Supabase no `requirements.txt` | Refactor `uploads/router.py` |
| Segurança — Rate limiting em `/auth/login` | ❌ Ausente 🔴 | `slowapi` ausente do `requirements.txt`. Grep `slowapi\|rate_limit\|limiter` zero matches em `app/` | Lib slowapi |
| Segurança — Security headers (X-Content-Type-Options, X-Frame-Options, HSTS) | ❌ Ausente 🔴 | Apenas RequestContextMiddleware + CORSMiddleware | Middleware novo |
| Segurança — `bcrypt__rounds=12` explícito | ❌ Ausente 🔴 | `core/security.py:7` é `CryptContext(schemes=["bcrypt"], deprecated="auto")` sem rounds explícito | Refactor security.py |
| Testes — Cobertura crítica (BookingEngine FSM, conflitos, sinal/depósito, comissão dois eixos, idempotência) | ❌ Ausente | Apenas 3 arquivos: `test_conflito.py`, `test_cors.py`, `test_logging.py`. Sem cobertura para `transitions.py`, `policies.py`, `snapshots.py`, handlers do bot, FSM completa | pytest + testcontainers (já no plano-v3) |
| Migrations Alembic — sem drift | ✅ Implementado | 18 migrations lineares (HEAD: `f1e2d3c4b5a6`) | — |

---

## Desvios arquiteturais pendentes

Retomada dos 15 desvios do relatório de varredura, com status atual.

| # | Descrição | Status | Prioridade | Sprint planejado |
|---|-----------|--------|-----------|-------------------|
| 1 | `/painel/painel/` diretório aninhado duplicado (skeleton stranded) | ⚠️ Não resolvido | Limpeza simples — pode entrar como item de Sprint 1 | Sprint 1 |
| 2 | Workers asyncio in-process sem retry/DLQ | ⚠️ Não resolvido 🔴 | Bloqueante para Fila de espera e lembretes confiáveis | Sprint 4 |
| 3 | `require_admin` binário (sem RBAC granular) | ⚠️ Não resolvido 🔴 | Bloqueante para introdução de OPERATOR/PROFESSIONAL com escopo restrito | Sprint 2 + 3 |
| 4 | bcrypt sem `rounds=12` explícito | ⚠️ Não resolvido | Hardening | Sprint 1 |
| 5 | Sem rate limiting nem security headers | ⚠️ Não resolvido 🔴 | Bloqueante para abrir novos perfis na Fase de RBAC | Sprint 1 |
| 6 | Sem `EXCLUDE CONSTRAINT` em appointments | ⚠️ Não resolvido 🔴 | Crítico operacional — bug silencioso possível | Sprint 1 |
| 7 | Camada de eventos inexistente (integrações síncronas) | ⚠️ Não resolvido 🔴 | Bloqueante para todos os módulos com lifecycle | Sprint 5 |
| 8 | Auth tem único endpoint (login + me) | ⚠️ Não resolvido | Bloqueante para criação de OPERATOR/PROFESSIONAL via Admin | Sprint 2 |
| 9 | `User.company_id` é `nullable=False` (bloqueia PLATFORM_OWNER) | ⚠️ Não resolvido 🔴 | Bloqueante para Painel Owner | Sprint 2 |
| 10 | Filtro `status.notin_(["CANCELLED", "NO_SHOW"])` com string literal | ⚠️ Não resolvido | Baixo risco — limpeza | Sprint 10 (junto com Operations FSM) |
| 11 | `AppointmentService.service_id` nullable sem `ondelete='SET NULL'` | ⚠️ Não resolvido | Baixo risco | Sprint 11 (junto com Catálogo opt-ins) |
| 12 | `get_current_company_id` quebra para PLATFORM_OWNER | ⚠️ Não resolvido | Bloqueante para Painel Owner | Sprint 2 |
| 13 | `users/router.py` sem suporte a senha temporária / `must_change_password` | ⚠️ Não resolvido | Bloqueante para convite de novos usuários | Sprint 2 |
| 14 | Cobertura de testes mínima (3 arquivos) | ⚠️ Não resolvido | Crescente ao longo do plano | Sprints 1+ (todos) |
| 15 | Uploads em volume Docker (não persiste entre deploys) | ⚠️ Não resolvido 🔴 | Crítico para profissionalização do produto | Sprint 1 |

Nenhum desvio foi resolvido entre a varredura e este plano (sessão de planejamento, sem implementação).

---

## Plano de sprints

**Convenções:**
- Cada sprint = até 2 semanas
- Backend = modelos + service + router + migration + testes
- Frontend = páginas + componentes + integração com API
- `[SCHEMA APENAS]` = migration sem endpoint nem tela
- 🔴 = bloqueante de receita ou produção | 🟠 = pré-requisito de outro sprint | 🟡 = fundação | 🟢 = valor | 🔵 = canal/UI

---

### Sprint 1 — Hardening crítico + limpeza 🔴
**Objetivo:** Fechar todos os vetores de segurança e perda de dados antes de qualquer construção nova.
**Critério de conclusão:** Banco protege overlap por constraint; `/auth/login` resistente a brute force; uploads persistem entre deploys; `/painel/painel/` removido.

#### Backend
- [ ] Migration de `EXCLUDE CONSTRAINT` em `appointments` (btree_gist + tsrange) — `(company_id, professional_id, tsrange(start_at, end_at, '[)') WITH &&) WHERE status NOT IN ('CANCELLED', 'NO_SHOW')`
- [ ] Verificar extensão `btree_gist` ativa em Supabase antes da migration
- [ ] `slowapi` no `requirements.txt` + rate limit em `/auth/login` (5 tentativas/min/IP; lockout 15min)
- [ ] Middleware de security headers (`app/middleware/security_headers.py`): X-Content-Type-Options, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy, CSP `default-src 'self'`
- [ ] Refactor `core/security.py`: `CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)`
- [ ] Refactor `modules/uploads/router.py` + `service.py`: usar Supabase Storage (SDK `supabase`); URL pública retornada
- [ ] Script `scripts/migrate_uploads_to_supabase.py` para mover arquivos existentes + atualizar URLs no banco
- [ ] Script `scripts/rollback_uploads_to_volume.py` testado **antes** do deploy

#### Frontend
- [ ] Remover `/painel/painel/` (skeleton stranded com `package.json`, `node_modules/`, `app/` próprios — confirmar não-uso antes)

#### Migrations
- [ ] `add_appointments_overlap_exclusion_constraint`

#### Testes
- [ ] Postgres real (testcontainers): insert sobreposto direto → falha com `ExclusionViolationError`
- [ ] Postgres: mesmo slot, profissionais diferentes → ambos aceitos
- [ ] `/auth/login` 6ª tentativa em 1 min → 429 com `Retry-After`
- [ ] `curl -I /health` retorna todos os security headers

---

### Sprint 2 — RBAC v1 + Auth completa 🔴
**Objetivo:** 5 papéis do tenant + PLATFORM_OWNER funcionando + auth com troca/recuperação de senha.
**Critério de conclusão:** Admin cria OPERATOR/PROFESSIONAL via convite; PLATFORM_OWNER autentica com `company_id=NULL`; usuário recupera senha via WhatsApp/email.

#### Backend
- [ ] `app/domain/enums/user_role.py`: enum `UserRole` (OWNER, ADMIN, OPERATOR, PROFESSIONAL, CLIENT, PLATFORM_OWNER, + valores `[SCHEMA APENAS]` para PLATFORM_SUPPORT/BILLING/READONLY)
- [ ] Migration: `User.company_id` → `nullable=True`
- [ ] Migration: `User.role` → enum tipado (substituir `String(20)`)
- [ ] Migration: novos campos em `User` — `must_change_password (bool default False)`, `email_verified_at (timestamp nullable)`, `last_password_change_at`
- [ ] `core/deps.py`: `get_current_company_id` trata PLATFORM_OWNER (retorna `None` em vez de quebrar)
- [ ] `core/deps.py`: `require_role(*roles)` e `require_platform_owner()`
- [ ] `modules/auth/router.py` novos endpoints:
  - `POST /auth/change-password` (autenticado, valida senha atual)
  - `POST /auth/forgot-password` (gera token de 6 dígitos, envia via Comunicação)
  - `POST /auth/reset-password` (consome token)
- [ ] `app/infrastructure/db/models/password_reset_token.py`: `(user_id, token_hash, expires_at, used, created_at)`
- [ ] `modules/users/router.py`: `POST /users/invite` (Admin convida; gera senha temporária com `must_change_password=True`)
- [ ] Regras de anti-escalonamento em `users/service.py`:
  - ADMIN não atribui ADMIN/OWNER
  - ADMIN não revoga OWNER/ADMIN
  - OWNER não remove o último OWNER ativo
  - Nenhum papel eleva o próprio role

#### Frontend
- [ ] Página `/dashboard/settings/security/page.tsx`: troca de senha
- [ ] Página `/forgot-password/page.tsx`: solicita reset
- [ ] Página `/reset-password/[token]/page.tsx`: consome token
- [ ] Redirect obrigatório para `/dashboard/settings/security` quando JWT contém `must_change_password=True`
- [ ] Validação de senha forte (≥8 chars, 1 maiúscula, 1 número) no frontend
- [ ] Página `/dashboard/users/page.tsx`: lista de usuários do tenant + convite

#### Migrations
- [ ] `user_role_enum_and_company_nullable`
- [ ] `add_password_reset_tokens`
- [ ] `add_must_change_password_to_users`

#### Testes
- [ ] PLATFORM_OWNER autentica com sucesso (sem company_id)
- [ ] Token de reset inválido após 1 uso
- [ ] Token de reset expirado após 15 min
- [ ] ADMIN tentando atribuir OWNER → 403
- [ ] OWNER tentando remover último OWNER → 422 com motivo claro
- [ ] Usuário com `must_change_password=True` bloqueado de todas as rotas exceto `/auth/change-password`

---

### Sprint 3 — RBAC v2 (permissões granulares por ação+escopo) 🟠
**Objetivo:** Camada 2 do RBAC implementada — autorização por ação + escopo (não apenas papel binário).
**Critério de conclusão:** PROFESSIONAL acessa apenas suas operações; OPERATOR opt-in para `create_manual_adjustment`; matriz de permissões em código declarativo.

#### Backend
- [ ] `app/domain/permissions.py`: registro declarativo de permissões por ação
- [ ] `core/deps.py`: `require_action(action: str, scope: ActionScope)` — dependency que checa `(role, action, scope)`
- [ ] Aplicar `require_action` em todos os routers existentes (replace de `require_admin`)
- [ ] `app/domain/enums/action_scope.py`: `OWN | OWN_CUSTOMERS | TENANT | CROSS_TENANT`
- [ ] Tabela `permission_overrides` (opt-in/opt-out por tenant para ações sensíveis: `OPERATOR.create_manual_adjustment`, `PROFESSIONAL.apply_manual_discount_override` etc.)
- [ ] `modules/tenant_config/`: novo módulo para `TenantConfig` (permission_overrides, sensitive_action_limits)

#### Frontend
- [ ] `hooks/useAuth.ts` expõe `user.role` e `user.permissions` (do JWT)
- [ ] `components/Sidebar.tsx`: renderização condicional por role/permissões
- [ ] Página `/dashboard/forbidden/page.tsx`
- [ ] Middleware Next.js: redirect rota bloqueada → `/dashboard/forbidden`
- [ ] `/dashboard/settings/permissions/page.tsx`: Admin configura opt-ins (com avisos sobre risco)

#### Migrations
- [ ] `add_permission_overrides`
- [ ] `add_tenant_config_table`

#### Testes
- [ ] PROFESSIONAL tenta listar appointments de outro profissional → 403
- [ ] OPERATOR tenta `create_manual_adjustment` sem opt-in → 403
- [ ] OPERATOR com opt-in dentro do `max_amount` → 200
- [ ] OPERATOR com opt-in acima do `max_amount` → 422 com motivo

---

### Sprint 4 — Workers Celery + Redis 🔴
**Objetivo:** Substituir workers asyncio in-process por jobs Celery com Redis broker — garantia de entrega para lembretes e base para futuros workers (Fila, Despesas, Subscriptions).
**Critério de conclusão:** Lembrete entregue com retry automático em caso de falha temporária da Evolution API; Celery beat rodando como serviço separado.

#### Backend
- [ ] `requirements.txt`: `celery[redis]`, `redis`
- [ ] `agendamento_engine/app/celery_app.py`: app Celery + beat scheduler com `REDIS_URL` do env
- [ ] `app/workers/reminder_worker.py`: refactor para Celery Beat (task periódica a cada 10min que despacha tasks individuais `send_reminder.delay(appointment_id, kind)`)
- [ ] `app/workers/tasks/send_reminder.py`: task individual com retry (3x, backoff 5min) + DLQ
- [ ] `app/workers/session_cleanup_worker.py`: refactor para Celery Beat
- [ ] Remover registro de workers do `app/main.py:lifespan`
- [ ] Configuração Railway: serviço Redis + serviço Celery worker + serviço Celery beat

#### Frontend
- [ ] Nenhuma alteração

#### Migrations
- [ ] Nenhuma (Celery armazena estado em Redis, não em Postgres)

#### Testes
- [ ] Smoke: criar appointment com 25h antecedência → simular falha temporária Evolution API (mock) → confirmar retry e entrega no próximo ciclo
- [ ] Verificar que `reminder_24h_sent`/`reminder_2h_sent` só são setados após confirmação real

---

### Sprint 5 — Event bus + ProcessedIdempotencyKey + Comunicação handler/dispatch 🟠
**Objetivo:** Infraestrutura de eventos com idempotência + CommunicationService como handler real (substituindo `notifications.py` placeholder).
**Critério de conclusão:** Domínios emitem eventos via envelope canônico; consumers registrados por type processam idempotentemente; lembretes do bot/email usam templates configuráveis.

#### Backend
- [ ] `app/core/events/__init__.py`: registry in-process de handlers por `event_type`
- [ ] `app/core/events/envelope.py`: `DomainEvent` dataclass com (event_id, event_type, occurred_at, company_id, idempotency_key, actor, payload)
- [ ] `app/core/events/dispatcher.py`: `publish(event)` que despacha para handlers + registra `ProcessedIdempotencyKey`
- [ ] Modelo `ProcessedIdempotencyKey`: `(key, consumer, company_id, processed_at, event_id, result_summary)` com `UNIQUE(key, consumer, company_id)`
- [ ] Worker `processed_idempotency_key.cleanup_worker` (TTL 90 dias)
- [ ] `app/modules/communication/`: novo módulo
  - `CommunicationService.dispatch(event: NotificationRequest)` com canal (WhatsApp/email), template, audiência, horários permitidos
  - Modelo `CommunicationTemplate`: `(id, company_id, code, channel, body, variables, created_at)`
  - Modelo `CommunicationLog`: `(id, company_id, recipient, channel, template_code, sent_at, status, error?)`
  - Refactor `notifications.py`: chama `CommunicationService` em vez de `evolution_client` diretamente
  - Refactor `whatsapp/messages.py`: extrai mensagens para `CommunicationTemplate` (com seed inicial)
- [ ] Handler de eventos `agenda.reservation.confirmed` → dispara notificação via Comunicação (substitui `send_booking_confirmation` direto)

#### Frontend
- [ ] `/dashboard/settings/communication/page.tsx`: templates editáveis, canais ativos, horários permitidos

#### Migrations
- [ ] `add_processed_idempotency_keys`
- [ ] `add_communication_templates`
- [ ] `add_communication_logs`

#### Testes
- [ ] Mesmo evento publicado 2x → consumer processa 1x; segunda chamada audit como duplicata
- [ ] Notificação fora do horário permitido (22h-8h) → enfileira para horário válido
- [ ] Template com variável faltante → falha controlada com log, não exceção propagada

---

### Sprint 6 — Financial Core (Account + Movement + Entry) 🟠
**Objetivo:** Modelos base do Financial Core — Account, Movement, Entry — com imutabilidade após criação.
**Critério de conclusão:** Tenant tem `Account` default (CAIXA); Movements e Entries criados via API privada (sem endpoint público); tentativa de UPDATE/DELETE retorna erro.

#### Backend
- [ ] `app/infrastructure/db/models/account.py`: `Account(id, company_id, name, type [CAIXA|ACQUIRER|BANK], provider?, external_ref?, currency BRL, status, is_default_inflow)` + `UNIQUE(company_id, provider) WHERE is_default_inflow=true`
- [ ] `app/infrastructure/db/models/movement.py`: `Movement(id, company_id, account_id, type [INFLOW|OUTFLOW|TRANSFER_IN|TRANSFER_OUT], amount, occurred_at, source_type, source_id, transfer_id?, reconciled_at?, reconciliation_id?)`
- [ ] `app/infrastructure/db/models/entry.py`: `Entry(id, company_id, type [RECEITA|CUSTO|DESPESA|TAXA|COMISSAO|ESTORNO|AJUSTE], direction [ADDS|SUBTRACTS], amount, occurred_at, category, source_type, source_id, movement_id NULLABLE)`
- [ ] Trigger no banco: `BEFORE UPDATE OR DELETE ON movements/entries → RAISE EXCEPTION` (imutáveis)
- [ ] SQLAlchemy `@validates` para reforçar imutabilidade no ORM
- [ ] `modules/financial_core/service.py`: `create_movement_with_entry(...)` (transação atômica), `compute_balance(account_id, as_of?)`, `list_movements(filters)`, `list_entries(filters)`
- [ ] Enum de categorias defaults: `RECEITA.{SERVICOS|PRODUTOS|PACOTE|ASSINATURA_ADESAO|ASSINATURA_RENOVACAO|SINAL_SERVICO|OUTROS}`, `DESPESA.{ALUGUEL|UTILITIES|MARKETING|SOFTWARE|CONTABILIDADE|LIMPEZA|OUTROS}`
- [ ] Hook ao criar empresa: cria Account default CAIXA `is_default_inflow=true`
- [ ] Eventos: `financial_core.movement_created`, `financial_core.entry_created`

#### Frontend
- [ ] Nenhuma (módulos consomem Financial Core, não exibem direto neste sprint)

#### Migrations
- [ ] `add_accounts`
- [ ] `add_movements_with_immutability_trigger`
- [ ] `add_entries_with_immutability_trigger`

#### Testes
- [ ] UPDATE direto em Movement → erro do trigger
- [ ] DELETE direto em Entry → erro do trigger
- [ ] `create_movement_with_entry` rollback completo em falha parcial
- [ ] `compute_balance` com 100 movements aleatórios

---

### Sprint 7 — Financial Core (Transfer + Reconciliation + CashCount) 🟠
**Objetivo:** Completar Financial Core com Transfer, ReconciliationRecord e CashCount.
**Critério de conclusão:** Transfer cria 2 Movements atômicos; reconciliação manual Level 1 funciona; CashCount registra divergência e gera Entry AJUSTE.

#### Backend
- [ ] `app/infrastructure/db/models/transfer.py`: `Transfer(id, company_id, from_account_id, to_account_id, amount, status [REQUESTED|COMPLETED|FAILED], requested_at, completed_at?)`
- [ ] `app/infrastructure/db/models/reconciliation_record.py`: `ReconciliationRecord(id, company_id, account_id, opened_at, closed_at?, opened_by, closed_by?, status)`
- [ ] `app/infrastructure/db/models/cash_count.py`: `CashCount(id, company_id, account_id, expected_amount, counted_amount, discrepancy, resolution [ADJUSTED|NO_ADJUSTMENT], created_by, created_at, notes)`
- [ ] `modules/financial_core/transfer_service.py`: `create_transfer(...)` cria Movements OUTFLOW + INFLOW atomicamente (sem Entry)
- [ ] `modules/financial_core/reconciliation_service.py`: open/close, marcar movement reconciliado
- [ ] `modules/financial_core/cash_count_service.py`: registrar contagem; se `resolution=ADJUSTED` dispara `cash_count.adjustment_created` → Entry AJUSTE category=CAIXA_DIVERGENCIA
- [ ] Eventos: `financial_core.transfer_completed`, `cash_count.recorded`, `cash_count.adjustment_created`, `financial_core.reconciliation_opened/closed`

#### Frontend
- [ ] Nenhuma (Gestão Financeira UI é Sprint 19)

#### Migrations
- [ ] `add_transfers`
- [ ] `add_reconciliation_records`
- [ ] `add_cash_counts`

#### Testes
- [ ] Transfer COMPLETED cria exatamente 2 Movements (OUTFLOW + INFLOW) na mesma transação
- [ ] Falha no 2º Movement → rollback do 1º
- [ ] CashCount com divergência → Entry AJUSTE com `notes` obrigatório

---

### Sprint 8 — Asaas adapter + Subcontas + PaymentSource 🟠
**Objetivo:** Conexão com Asaas + criação de subcontas Asaas para o tenant + PaymentSources cadastradas.
**Critério de conclusão:** Tenant criado tem subconta Asaas em `pending_verification`; webhook de ativação atualiza para `active`; PaymentSource cadastrada com tokenização Asaas.

#### Backend
- [ ] `requirements.txt`: SDK Asaas (ou cliente HTTP próprio)
- [ ] `app/modules/payments/providers/base.py`: `PaymentProvider` ABC (`create_payment`, `handle_webhook`, `refund`, `get_status`, `create_subaccount`, `tokenize_card`)
- [ ] `app/modules/payments/providers/asaas.py`: implementação Asaas
- [ ] `app/modules/payments/providers/null_provider.py`: para testes (configurable outcome + spy `self.calls`)
- [ ] Migration: `Company` ganha `payment_provider (str)`, `external_account_id`, `external_account_status [pending_verification|active|suspended]`
- [ ] Migration: `Professional` ganha `cpf_cnpj`, `external_wallet_id`
- [ ] Validação de CPF/CNPJ com dígito verificador (não apenas regex) antes de enviar à API Asaas
- [ ] Hook no cadastro de tenant: cria subconta Asaas via `AsaasProvider.create_subaccount(...)`
- [ ] Webhook `POST /payments/webhook/asaas/account_status` → atualiza `external_account_status`
- [ ] CPF/CNPJ mascarado em logs (`***.456.789-**`)
- [ ] `app/modules/payments/models/payment_source.py`: `PaymentSource(id, company_id, customer_id, type [CARD_CREDIT|CARD_DEBIT|PIX|BOLETO|CASH|MAQUININHA], provider, external_token, last4?, brand?, is_active)`

#### Frontend
- [ ] `/dashboard/settings/financial/page.tsx`: status da subconta Asaas (banner `pending_verification` com próximos passos)
- [ ] `/dashboard/professionals/[id]/page.tsx`: campo CPF/CNPJ + botão "Criar conta financeira"

#### Migrations
- [ ] `add_company_payment_provider_columns`
- [ ] `add_professional_cpf_cnpj_and_wallet`
- [ ] `add_payment_sources`

#### Testes
- [ ] CPF inválido (111.111.111-11) → erro no frontend antes da API
- [ ] CNPJ válido → subconta criada com `pending_verification`
- [ ] Webhook de ativação → status `active`
- [ ] Nenhum CPF em log de produção (grep logs)

---

### Sprint 9 — PaymentsEngine FSM + modelos de cobrança + webhook idempotente 🟠
**Objetivo:** Engine de pagamentos com POST_DELIVERY/DEPOSIT/PREPAID/PREPAID_REFUNDABLE + webhook idempotente + TenantFeeRoutingPolicy.
**Critério de conclusão:** Pix gerado e confirmado via Asaas em produção; webhook idempotente (replay não cria duplicata); `payment.confirmed` gera Movement INFLOW + Entry RECEITA.

#### Backend
- [ ] Modelos: `Payment(id, company_id, customer_id?, operation_id?, subscription_id?, package_id?, currency, amount, payment_source, provider, target_account_id, status [PENDING|CONFIRMED|FAILED|CANCELLED|REFUNDED], created_at, paid_at?, gross_catalog_amount, discount_amount, net_charged_amount, provider_fee, manual_override_count)` — `provider` imutável (`@validates` + trigger)
- [ ] Modelos: `PaymentTransaction(id, payment_id, provider_transaction_id, amount, status, raw_response JSONB, created_at)`
- [ ] Modelos: `DepositPolicy(id, company_id, service_id?, deposit_type [FIXED_AMOUNT|PERCENTAGE], deposit_value, refundable_until_hours_before, refund_on_tenant_fault, retain_on_no_show, commission_on_retained_deposit)`
- [ ] Modelos: `TenantFeeRoutingPolicy(id, company_id, fee_source [ASAAS_PIX|ASAAS_CARD|MAQUININHA_DEBIT|MAQUININHA_CREDIT|ANTECIPACAO|ESTORNO|RECORRENTE_FEE], client_share %, tenant_share %, professional_share %)` com validação `soma=100`
- [ ] `modules/payments/service.py`: cria `Payment`, emite `payment.created`; `confirm(payment_id, webhook_data)` gera Movement INFLOW + Entry RECEITA + (se provider_fee) OUTFLOW + TAXA
- [ ] Webhook `POST /payments/webhook/asaas/transaction`: idempotente via `external_reference` + `ProcessedIdempotencyKey`
- [ ] `refund(payment_id, reason [SERVICE_FAILURE|REGISTRATION_ERROR|DEADLINE_POLICY|OTHER])` gera Movement OUTFLOW + Entry ESTORNO
- [ ] Eventos: `payment.created`, `payment.confirmed`, `payment.failed`, `payment.retried`, `payment.cancelled`, `payment.refunded`

#### Frontend
- [ ] `/dashboard/payments/page.tsx`: lista de PaymentEvents
- [ ] `/dashboard/payments/[id]/page.tsx`: detalhe + ações (refund com motivo classificado)
- [ ] Componente `<QrCodeDisplay />` no `BookingFlow.tsx` quando POST de booking retorna QR Pix

#### Migrations
- [ ] `add_payments`
- [ ] `add_payment_transactions`
- [ ] `add_deposit_policies`
- [ ] `add_tenant_fee_routing_policies`

#### Testes
- [ ] Pix gerado e confirmado em sandbox Asaas → Movement INFLOW + Entry RECEITA `category=SERVICOS`
- [ ] Webhook replay (mesmo `event_id`) → não cria 2ª `PaymentTransaction`
- [ ] `Payment.provider` imutável: tentativa de UPDATE → erro
- [ ] Refund com motivo `SERVICE_FAILURE` → Entry ESTORNO + audit
- [ ] TenantFeeRoutingPolicy com `client + tenant + professional ≠ 100%` → 422

---

### Sprint 10 — Operations FSM expandida + Agenda granular 🟡
**Objetivo:** FSM completa (DRAFT → REQUESTED → CONFIRMED → IN_PROGRESS → COMPLETED/CANCELLED/NO_SHOW/FAILED) + soft↔firme reservation + ocupação direta.
**Critério de conclusão:** Reserva soft criada com TTL configurável → promovida para firme via `payment.confirmed` ou auto_confirm_rules; ocupação direta funciona; overbooking manual exige motivo + audit.

#### Backend
- [ ] Refactor: renomear `Appointment` → `Operation` (mantendo backward compat com view ou migration) **OU** estender Appointment com `operation_type` + estados ampliados
- [ ] Enum `OperationStatus`: DRAFT, REQUESTED, CONFIRMED, IN_PROGRESS, COMPLETED, CANCELLED, NO_SHOW, FAILED
- [ ] `OperationType`: `SERVICE_SCHEDULED | SERVICE_DIRECT | PRODUCT_SALE` + `[SCHEMA APENAS]` `SERVICE_ENCOMENDA | PRODUCT_ENCOMENDA`
- [ ] Modelos de Agenda granular:
  - `WorkingHour` (existe — manter)
  - `ScheduleException`: substitutiva ou aditiva, por data específica
  - `ScheduleBlock` (existe — manter)
  - `Reservation(id, company_id, professional_id, start_at, end_at, type [SOFT|FIRME], operation_id?, expires_at? [só SOFT], created_at)` com `EXCLUDE CONSTRAINT` para tipo FIRME
  - `DirectOccupancy(id, company_id, professional_id, start_at, end_at, operation_id, opened_at, closed_at?)`
- [ ] Contrato Agenda ↔ Operações: `consultar_disponibilidade`, `criar_reserva_soft`, `promover_para_firme`, `criar_reserva_firme_direta`, `liberar_reserva`, `marcar_no_show`, `marcar_encerrada`, `replace_reservation`, `abrir_ocupacao_direta`, `fechar_ocupacao_direta`
- [ ] Configurações: `draft_expiration_minutes` (60), `requested_expiration_hours` (24), `no_show_threshold_minutes` (30), `auto_confirm_rules`, `soft_reservation_ttl_minutes` (15), `overbooking_alert_enabled` (true)
- [ ] Overbooking manual com motivo obrigatório + audit
- [ ] Limpar string literal de status (desvio #10): usar `OperationStatus.CANCELLED.value`
- [ ] Eventos: `agenda.soft_reservation.created/expired/cancelled`, `agenda.reservation.confirmed`, `agenda.reservation.released/consumed/no_show/replaced`, `agenda.direct_occupancy.opened/closed`, `agenda.overbooking_forced`, `operation.completed`, `operation.cancelled`, `operation.no_show`

#### Frontend
- [ ] Refactor `/dashboard/appointments/` → `/dashboard/operations/` (com redirect)
- [ ] `BookingFlow.tsx`: TTL de soft reservation visível como cronômetro
- [ ] Página de "ocupação direta" para Operator/Owner registrar walk-in

#### Migrations
- [ ] `add_operations_table_or_extend_appointments`
- [ ] `add_schedule_exceptions`
- [ ] `add_reservations`
- [ ] `add_direct_occupancies`

#### Testes
- [ ] Reserva SOFT vence sem promoção → liberada e emite `agenda.soft_reservation.expired`
- [ ] Reserva SOFT + `payment.confirmed` → promovida para FIRME
- [ ] Dois walk-ins simultâneos no mesmo slot → segundo bloqueado por EXCLUDE
- [ ] Overbooking forçado sem motivo → 422

---

### Sprint 11 — Catálogo opt-ins (preço/duração por profissional, variantes, tempo de preparação) 🟡
**Objetivo:** Habilitar opt-ins do catálogo (Princípio 12) — default permanece simples, complexidade aparece só quando tenant ativa.
**Critério de conclusão:** Tenant pode definir preço/duração diferente por profissional, criar variantes simples de serviço, configurar tempo de preparação/descanso.

#### Backend
- [ ] Modelo `ServicePricingOverride(id, company_id, service_id, professional_id, price?, duration?, commission_base_value?)`
- [ ] Modelo `ServiceVariant(id, company_id, service_id, name, price_delta, duration_delta, active)`
- [ ] Migration: `Service` ganha `preparation_minutes_before`, `preparation_minutes_after`, `commission_base_value`
- [ ] Migration: `Service` ganha flag `multiple_professionals_simultaneous (bool default false)` [SCHEMA APENAS — sem lógica]
- [ ] Service expansion: cálculo de preço/duração resolve override → variant → catálogo base
- [ ] FK `AppointmentService.service_id`: revisar `ondelete='SET NULL'` (desvio #11)

#### Frontend
- [ ] `/dashboard/services/[id]/page.tsx`: tabs (Geral, Preço por profissional, Variantes, Tempo de preparação)
- [ ] Opt-in toggles (mostrar apenas se ativado)

#### Migrations
- [ ] `add_service_pricing_overrides`
- [ ] `add_service_variants`
- [ ] `add_service_preparation_and_commission_base`
- [ ] `add_service_multi_professional_flag`

#### Testes
- [ ] Override de preço sobrepõe catálogo na criação de Operation
- [ ] Variante aplicada altera preço e duração corretamente
- [ ] Sem override + sem variante → usa catálogo base (sem regressão)

---

### Sprint 12 — CommissionEngine (2 eixos) + lifecycle 🟢
**Objetivo:** Comissões com `commission_base` × `commission_fee_policy` + lifecycle CALCULATED → DUE → PAID (com REVERTED).
**Critério de conclusão:** Operation COMPLETED gera commission.calculated; payout mensal configurável move DUE → PAID; refund gera commission.reverted.

#### Backend
- [ ] Modelo `Commission(id, company_id, operation_id?, package_purchase_id?, subscription_renewal_id?, professional_id, beneficiary_role [SERVICE_PROVIDER|SELLER|RECURRING_SELLER], commission_base [SERVICE_REFERENCE_PRICE|ALLOCATED_COTA_VALUE], commission_fee_policy [GROSS_OF_FEES|NET_OF_FEES|CUSTOM], custom_params JSONB?, base_amount, percentage, calculated_amount, status [CALCULATED|DUE|PAID|REVERTED], calculated_at, due_at?, paid_at?, reverted_at?)`
- [ ] Modelo `CommissionPayout(id, company_id, professional_id, period_start, period_end, total_amount, status [DRAFT|EXECUTED], executed_at?)`
- [ ] `modules/commissions/service.py`: `calculate_for_operation(operation)`, `mark_due(commission)`, `mark_paid(commission)`, `revert(commission)`
- [ ] Algoritmo de cálculo respeita os 2 eixos + `use_net_of_discount` (opt-in)
- [ ] Listener de `operation.completed` → `commission.calculated`
- [ ] Listener de `payment.refunded` → `commission.reverted` (se commission ainda não PAID); senão `commission.recovery_recorded`
- [ ] Worker `commission_payout_worker` (mensal, configurável via `payout_day_of_month`)
- [ ] Eventos: `commission.calculated`, `commission.calculation_failed`, `commission.due`, `commission.paid`, `commission.reverted`, `commission.recovery_recorded`
- [ ] `commission.paid` → Movement OUTFLOW + Entry COMISSAO
- [ ] `commission.recovery_recorded` → Movement INFLOW + Entry AJUSTE

#### Frontend
- [ ] `/dashboard/commissions/page.tsx`: lista por profissional, período, status
- [ ] `/dashboard/commissions/payouts/page.tsx`: histórico de payouts + botão "Fechar mês"

#### Migrations
- [ ] `add_commissions`
- [ ] `add_commission_payouts`

#### Testes
- [ ] Operation COMPLETED com `GROSS_OF_FEES` → comissão sobre preço de catálogo cheio
- [ ] Operation com `NET_OF_FEES` e provider_fee=10% → comissão sobre 90%
- [ ] Operation com `CUSTOM` (professional_share=50%) → desconta 50% das taxas
- [ ] Refund antes de PAID → status REVERTED, sem Movement
- [ ] Refund depois de PAID → recovery_recorded com Movement INFLOW + Entry AJUSTE

---

### Sprint 13 — CustomerCredit + FEFO + lifecycle 🟢
**Objetivo:** Cotas como direito de uso (não saldo, Princípio Credit-1) com FEFO e lifecycle completo.
**Critério de conclusão:** Cliente com 2 pacotes (validades diferentes) consome cota com expiração mais próxima primeiro; cota expirada vira EXPIRED via worker.

#### Backend
- [ ] Modelo `CustomerCredit(id, company_id, customer_id, entitlement_type [PACKAGE|SUBSCRIPTION|GRANT_COTA], source_id?, total_cotas, remaining_cotas, status [ACTIVE|EXHAUSTED|EXPIRED|REVOKED], granted_at, expires_at?)`
- [ ] Modelo `CustomerCreditConsumption(id, credit_id, company_id, customer_id, operation_id, consumed_at)`
- [ ] `modules/customer_credit/service.py`: `consume_for_operation(operation)` com algoritmo FEFO (ORDER BY expires_at NULLS LAST)
- [ ] Worker `customer_credit.expiry_worker` (diário): `ACTIVE` com `expires_at < now()` → `EXPIRED` + evento
- [ ] Endpoint `POST /customer-credit/grant-cota` (concessão manual, audit obrigatório, sem receita)
- [ ] Eventos: `customer_credit.granted`, `customer_credit.consumed`, `customer_credit.exhausted`, `customer_credit.expired`, `customer_credit.revoked`, `customer_credit.grant_cota_recorded`

#### Frontend
- [ ] Ficha do cliente exibe cotas ativas (saldo + validade) — quando Sprint 23 (CRM) entrar
- [ ] `/dashboard/customers/[id]/grant-cota`: Admin/Operator concede cota com motivo

#### Migrations
- [ ] `add_customer_credits`
- [ ] `add_customer_credit_consumptions`

#### Testes
- [ ] FEFO: cliente com 2 cotas (uma expira em 30d, outra em 60d) → primeira consumida é a de 30d
- [ ] Cota expirada não pode ser consumida
- [ ] grant_cota gera CustomerCredit sem receita (sem Movement/Entry)
- [ ] Refund de pacote → CustomerCredit fica REVOKED

---

### Sprint 14 — Pacotes 🟢
**Objetivo:** Compra de pacote gera CustomerCredit; comissão distinta para vendedor (SELLER) e prestador de cada uso (SERVICE_PROVIDER).
**Critério de conclusão:** Cliente compra pacote de 10 cortes → 10 cotas em CustomerCredit; vendedor recebe comissão na compra; prestador recebe comissão a cada uso.

#### Backend
- [ ] Modelo `Package(id, company_id, name, service_id?, total_cotas, price, validity_days?, active, commission_seller_percentage?)`
- [ ] Modelo `PackagePurchase(id, company_id, customer_id, package_id, seller_user_id?, total_price, paid_at?, status [PENDING_PAYMENT|ACTIVE|REVOKED])`
- [ ] `modules/packages/service.py`: `purchase(customer_id, package_id, seller_user_id)` → cria PackagePurchase + Payment
- [ ] Listener `payment.confirmed` para PackagePurchase → cria CustomerCredit + emite `package.purchased`
- [ ] Listener `package.purchased` → CommissionEngine calcula comissão para SELLER

#### Frontend
- [ ] `/dashboard/packages/page.tsx`: CRUD de pacotes
- [ ] Fluxo de venda no painel (Admin/Operator): selecionar cliente + pacote + vendedor → gera link de pagamento

#### Migrations
- [ ] `add_packages`
- [ ] `add_package_purchases`

#### Testes
- [ ] Pacote de 10 cortes vendido → 10 cotas geradas em CustomerCredit ACTIVE
- [ ] Comissão SELLER calculada na compra (não no uso)
- [ ] Comissão SERVICE_PROVIDER calculada a cada operation que consome cota
- [ ] Refund do PackagePurchase → CustomerCredit REVOKED + commission reverted

---

### Sprint 15 — Assinaturas (recorrência Asaas) 🟢
**Objetivo:** Planos recorrentes com cobrança via Asaas + lifecycle ACTIVE/PAUSED/OVERDUE/SUSPENDED/CANCELLED.
**Critério de conclusão:** Cliente assina plano mensal → cobrança automática; ciclo gera cota; inadimplência move para OVERDUE → SUSPENDED após grace_period.

#### Backend
- [ ] Modelo `SubscriptionPlan(id, company_id, name, service_id?, cotas_per_cycle, price, cycle_days, rollover_enabled, active)`
- [ ] Modelo `CustomerSubscription(id, company_id, customer_id, plan_id, status [ACTIVE|PAUSED|OVERDUE|SUSPENDED|CANCELLED], next_billing_at, cancelled_at?, paused_at?)`
- [ ] Worker `subscription_renewal_worker` (diário): seleciona `ACTIVE AND next_billing_at <= now()` → cria Payment via Asaas
- [ ] Listener `payment.confirmed` (subscription_id != NULL) → gera CustomerCredit; emite `subscription.renewed`
- [ ] Worker de inadimplência: após `grace_period_days` (default 7) sem pagamento → SUSPENDED; após `auto_cancel_threshold_days` (default 30) → CANCELLED
- [ ] Eventos: `subscription.activated`, `subscription.paused`, `subscription.resumed`, `subscription.renewed`, `subscription.cycle_completed`, `subscription.overdue`, `subscription.suspended`, `subscription.cancelled`

#### Frontend
- [ ] `/dashboard/subscriptions/plans/page.tsx`: CRUD de planos
- [ ] `/dashboard/subscriptions/page.tsx`: lista de assinantes + status
- [ ] Cliente assina via Portal do Cliente (Sprint 21) ou Link Público

#### Migrations
- [ ] `add_subscription_plans`
- [ ] `add_customer_subscriptions`

#### Testes
- [ ] Assinatura ativa → cobrança automática gerada no `next_billing_at`
- [ ] Pagamento confirmado → cotas renovadas + Entry RECEITA `category=ASSINATURA_RENOVACAO`
- [ ] Inadimplência por 7 dias → SUSPENDED, cotas bloqueadas
- [ ] CANCELLED preserva cotas até fim do ciclo pago

---

### Sprint 16 — Promoções/Cupons + algoritmo + manual override 🟢
**Objetivo:** Promotion + Coupon com algoritmo cumulative/exclusive + preview vs efetivação + `manual_discount_override`.
**Critério de conclusão:** Cupom aplicado em checkout é apenas preview; efetivação só no `payment.confirmed`; promoção revalidada antes de cobrar; manual_override exige audit.

#### Backend
- [ ] Modelos `Promotion`, `Coupon`, `CouponRedemption`, `DiscountApplication` conforme estrutura na visão (Parte 6)
- [ ] `modules/promotions/service.py`: `find_eligible(...)`, `compute_preview(items, promotions, coupons)`, `effectuate(payment_id)`
- [ ] Algoritmo:
  1. Identifica candidatas elegíveis (conditions, audience)
  2. Separa cumulative vs exclusive
  3. Resolve exclusivas (`CUSTOMER_FAVORABLE` default)
  4. Aplica em sequência sobre `gross_catalog_amount`
  5. Retorna `DiscountPreview[]` (NÃO persiste)
- [ ] Handler de `payment.confirmed` (modo STRICT): revalida + cria `DiscountApplication` + `CouponRedemption`; se inválido → refund automático
- [ ] `apply_manual_discount_override` (ação sensível): audit obrigatório + threshold opt-in para notificação ao OWNER
- [ ] Worker `promotions.expiry_scanner`
- [ ] Eventos: `promotion.created/activated/paused/cancelled/expired`, `promotion.applied`, `promotion.application_reverted`, `coupon.created/exhausted/expired/cancelled`, `coupon.redeemed`, `coupon.redemption_reverted`

#### Frontend
- [ ] `/dashboard/promotions/page.tsx`: CRUD + dashboard de uso (max_uses_count, conversão)
- [ ] `/dashboard/coupons/page.tsx`: geração bulk, single-use, per-customer
- [ ] No checkout (BookingFlow + bot): campo de cupom + preview de desconto
- [ ] No painel de Operation: botão "Aplicar desconto manual" (visível por permissão)

#### Migrations
- [ ] `add_promotions`
- [ ] `add_coupons`
- [ ] `add_coupon_redemptions`
- [ ] `add_discount_applications`

#### Testes
- [ ] Preview de cupom no checkout não persiste
- [ ] Promoção que vence entre checkout e confirmação → refund automático no STRICT
- [ ] Cupom `max_total_uses=1` + 2 requests simultâneos → apenas 1 redemed (atomicidade)
- [ ] Manual override sem motivo → 422; com motivo → audit obrigatório

---

### Sprint 17 — Estoque + Fornecedores + Payables 🟢
**Objetivo:** Estoque único (Estágio 0) com entrada, saída, custo médio, Fornecedores e Payables — sem FEFO no UI (apenas no schema).
**Critério de conclusão:** Entrada de estoque gera Payable; pagamento gera Movement OUTFLOW; consumo de insumo gera Entry CUSTO category=INSUMOS_USO_INTERNO; venda de produto gera Entry CUSTO category=PRODUTO_VENDIDO.

#### Backend
- [ ] Modelos `Supplier(id, company_id, name, contact, document?, active)`
- [ ] Modelos `StockItem(id, company_id, product_id, current_quantity, average_cost, last_entry_at)`
- [ ] Modelos `StockEntry(id, company_id, stock_item_id, quantity, unit_cost, supplier_id?, batch_number?, expiry_date?, entered_at, payable_id?)` — `expiry_date` é `[SCHEMA APENAS]` no Estágio 0
- [ ] Modelos `StockMovement(id, company_id, stock_item_id, type [VENDA|USO_INTERNO|PERDA|AJUSTE], quantity, occurred_at, source_type, source_id, notes?)`
- [ ] Modelos `Payable(id, company_id, supplier_id, total_amount, status [OPEN|PARTIALLY_PAID|PAID|CANCELLED], due_date?, paid_amount, closing_method [CASH_AT_CREATION|INSTALLMENTS], source_type, source_id)`
- [ ] Modelos `PayableInstallment(id, payable_id, amount, due_date, paid_at?, payment_id?)`
- [ ] `modules/stock/service.py`: cálculo de custo médio ponderado na entrada; consumo decrementa quantity
- [ ] Worker `payable.due_soon/overdue` (default 3 dias antes)
- [ ] Eventos: `stock.entry_recorded`, `stock.consumed`, `stock.sold`, `stock.loss_recorded`, `stock.adjusted`, `payable.created`, `payable.installment.created`, `payable.partially_paid`, `payable.installment.paid`, `payable.paid`, `payable.overdue`, `payable.cancelled`

#### Frontend
- [ ] `/dashboard/stock/page.tsx`: lista de produtos com quantidade atual e custo médio
- [ ] `/dashboard/stock/entries/page.tsx`: lançamentos de entrada
- [ ] `/dashboard/suppliers/page.tsx`: CRUD de fornecedores
- [ ] `/dashboard/payables/page.tsx`: lista de payables, due_soon/overdue badges

#### Migrations
- [ ] `add_suppliers`
- [ ] `add_stock_items`
- [ ] `add_stock_entries` (com `expiry_date` e `batch_number` para Estágio 1+)
- [ ] `add_stock_movements`
- [ ] `add_payables`
- [ ] `add_payable_installments`

#### Testes
- [ ] Entrada de estoque (10 un @ R$5 + 5 un @ R$7) → custo médio = R$5,67
- [ ] Venda de produto → StockMovement VENDA + Entry CUSTO + decremento quantity
- [ ] Payable PARTIALLY_PAID → 2 Movements OUTFLOW (sem Entry — origem stock_purchase)
- [ ] Payable due_soon dispara notificação

---

### Sprint 18 — Despesas + categorias + recorrência 🟢
**Objetivo:** Despesas operacionais (aluguel, utilities, marketing, etc.) com lifecycle PENDENTE → PAGA + recorrência.
**Critério de conclusão:** Tenant lança aluguel mensal recorrente; worker `expense.due_soon` notifica 3 dias antes; pagamento gera Movement OUTFLOW + Entry DESPESA.

#### Backend
- [ ] Modelo `Expense(id, company_id, description, amount, category, supplier_id?, due_date, status [PENDENTE|PAGA|CANCELLED], paid_at?, recurrence_rule? [JSONB], parent_expense_id?, created_by)`
- [ ] Worker `expense.due_soon` (default 3 dias antes)
- [ ] Worker `expense.overdue` (snapshot diário)
- [ ] Worker `expense.recurrence_generator`: cria próximas instâncias da recorrência
- [ ] Eventos: `expense.created`, `expense.due_soon`, `expense.overdue`, `expense.paid`, `expense.cancelled`

#### Frontend
- [ ] `/dashboard/expenses/page.tsx`: CRUD + filtro por categoria + status badges
- [ ] `/dashboard/expenses/new/page.tsx`: formulário com toggle de recorrência

#### Migrations
- [ ] `add_expenses`

#### Testes
- [ ] Despesa recorrente mensal → próxima instância gerada automaticamente
- [ ] Despesa PAGA → Movement OUTFLOW + Entry DESPESA `category=ALUGUEL`
- [ ] Despesa não pode ser editada depois de PAGA (RBAC-2 reforçado)

---

### Sprint 19 — Gestão Financeira UI + Dashboard role-aware 🟡
**Objetivo:** UI completa do bloco Financeiro do Painel do Tenant + Dashboard role-aware (OWNER/ADMIN/OPERATOR/PROFESSIONAL).
**Critério de conclusão:** OWNER vê DRE + saldo + alertas; OPERATOR vê apenas operação + caixa; PROFESSIONAL vê apenas suas comissões.

#### Backend
- [ ] Endpoint `/financial/dashboard?period=monthly&start=...&end=...`: agregações de Movements/Entries por categoria + saldos por Account + alertas (UNDER_REVIEW, stock baixo, cotas expirando, promoções expirando, payables vencendo, reconciliação aberta)
- [ ] Endpoint `/financial/dre?month=YYYY-MM`: receitas por categoria + custos + despesas + comissões + lucro estimado
- [ ] Exportação CSV via `StreamingResponse`

#### Frontend
- [ ] `/dashboard/financial/dashboard/page.tsx`: cards (receita, despesa, margem, lucro), gráfico
- [ ] `/dashboard/financial/dre/page.tsx`: DRE mensal + CSV export
- [ ] `/dashboard/financial/reconciliation/page.tsx`: abrir/fechar reconciliação, marcar movement como reconciliado
- [ ] `/dashboard/financial/cash-counts/page.tsx`: registrar contagem + resolver divergência
- [ ] Refactor `/dashboard/dashboard/page.tsx`: conteúdo varia por `user.role`
  - OWNER/ADMIN: resumo do dia, alertas, pendências
  - OPERATOR: agenda, fila, atendimento humano, cobranças pendentes, caixa
  - PROFESSIONAL: próximos atendimentos, ações rápidas, extrato de comissões

#### Migrations
- [ ] Nenhuma (consome Financial Core existente)

#### Testes
- [ ] OWNER acessa DRE → 200
- [ ] OPERATOR acessa DRE → 403
- [ ] PROFESSIONAL acessa próprias comissões → 200; comissões de outro → 403

---

### Sprint 20 — Identidade Paladino 3 níveis + PhoneIdentityResolver + ConsentRecord 🔵
**Objetivo:** Cliente final passa a ter identidade Paladino-wide (não apenas Customer por tenant).
**Critério de conclusão:** Mesmo telefone em 2 tenants → mesma `PaladinoIdentity`, com histórico segregado por tenant; ConsentRecord registra autorizações por tipo + canal + source.

#### Backend
- [ ] Modelo `PaladinoIdentity(id, phone_e164, name, email?, cpf? [opt-in], created_at, login_email? [se conta logada], password_hash? [se conta logada])`
- [ ] Migration: `Customer` ganha `paladino_identity_id` (FK para PaladinoIdentity)
- [ ] `app/modules/identity/service.py`: `resolve_or_create_by_phone(raw_phone, tenant_default_country)` retorna PaladinoIdentity (não Customer)
- [ ] `app/modules/identity/phone_resolver.py`: normalização E.164 via `phonenumbers` lib
- [ ] Modelo `ConsentRecord(id, paladino_identity_id, company_id?, consent_type [COMMUNICATION|DATA_PROCESSING|PAYMENT_STORAGE|MARKETING], channel? [WHATSAPP|EMAIL|SMS], status [GRANTED|REVOKED], source_channel [LINK|BOT|PORTAL|PAINEL], granted_at, revoked_at?)`
- [ ] Upgrade de identidade leve → completa: endpoint `POST /identity/upgrade` (sempre com confirmação explícita do cliente, nunca automático)
- [ ] Migração de dados: Customer existente → vincula a PaladinoIdentity pelo phone

#### Frontend
- [ ] Nenhuma (Portal do Cliente é Sprint 21)

#### Migrations
- [ ] `add_paladino_identities`
- [ ] `add_paladino_identity_id_to_customers`
- [ ] `add_consent_records`
- [ ] Data migration: backfill PaladinoIdentity a partir de Customer existentes

#### Testes
- [ ] Telefone `5511999999999` em 2 tenants → 2 Customers + 1 PaladinoIdentity
- [ ] Tenant A não vê histórico do cliente no Tenant B
- [ ] ConsentRecord MARKETING criada como REVOKED por default
- [ ] Upgrade leve → completa exige confirmação explícita

---

### Sprint 21 — Portal do Cliente 🔵
**Objetivo:** Área logada Paladino-wide para o cliente final — dashboard, histórico, cotas, métodos de pagamento, consentimentos.
**Critério de conclusão:** Cliente faz login via e-mail+senha (e/ou magic link), vê histórico em todos os tenants onde tem operações, gerencia cotas e consentimentos.

#### Backend
- [ ] `app/modules/portal/router.py`: novo módulo cliente-facing
  - `POST /portal/login` (e-mail+senha)
  - `POST /portal/magic-link/request`
  - `POST /portal/magic-link/consume`
  - `GET /portal/me` → PaladinoIdentity
  - `GET /portal/operations` → histórico consolidado
  - `GET /portal/credits` → CustomerCredit ativas
  - `GET /portal/subscriptions` → assinaturas + pausar/cancelar próprio
  - `GET /portal/payment-methods` → PaymentSources tokenizadas
  - `POST /portal/payment-methods/authorize` (cliente autoriza tenant a usar token)
  - `GET /portal/consents` + `PATCH /portal/consents/:id`
  - `PATCH /portal/profile`
- [ ] Token JWT do cliente final (audience separada do tenant user)

#### Frontend
- [ ] `/customer/login/page.tsx`
- [ ] `/customer/dashboard/page.tsx`: próximos agendamentos + cotas ativas
- [ ] `/customer/history/page.tsx`: operações em todos os tenants
- [ ] `/customer/credits/page.tsx`: cotas, validade, histórico de consumo
- [ ] `/customer/subscriptions/page.tsx`: pausar/cancelar
- [ ] `/customer/payment-methods/page.tsx`: tokenização + autorização por tenant
- [ ] `/customer/consents/page.tsx`: granular (por tipo + canal)
- [ ] `/customer/profile/page.tsx`

#### Migrations
- [ ] Nenhuma nova (PaladinoIdentity criada no Sprint 20)

#### Testes
- [ ] Cliente vê histórico em todos os tenants
- [ ] Tentar listar histórico de outro PaladinoIdentity → 403
- [ ] Magic link expira em 15 min
- [ ] Revogar consent MARKETING → bot/email para de enviar marketing

---

### Sprint 22 — NPS + Fila de espera 🟢
**Objetivo:** NPS triggered após `operation.completed` + Fila de espera que reage a `agenda.reservation.released`.
**Critério de conclusão:** Cliente recebe pesquisa após COMPLETED conforme configuração do tenant; cancelamento de operation libera slot que dispara fila.

#### Backend
- [ ] Modelos `NpsConfig(id, company_id, channel, delay_minutes_after_completion, message_template, allow_response_period_hours, min_interval_between_surveys_days)`
- [ ] Modelos `NpsSurvey(id, company_id, customer_id, operation_id, sent_at, response_score?, response_comment?, responded_at?)`
- [ ] Listener `operation.completed` → enfileira NpsSurvey (com delay) via CommunicationService
- [ ] Modelos `WaitlistEntry(id, company_id, customer_id, preferred_service_id, preferred_professional_id?, preferred_period [AM|PM|ANY], status [WAITING|NOTIFIED|CONFIRMED|EXPIRED], notified_at?, expires_at?)`
- [ ] Listener `agenda.reservation.released` → encontra próximo WAITING com match + notifica via CommunicationService + status NOTIFIED
- [ ] Verificação anti-duplicata: antes de notificar fila, checa se cliente já tem operação ativa equivalente
- [ ] Worker `waitlist.expiry`: NOTIFIED com `expires_at` vencido → EXPIRED + libera para próximo

#### Frontend
- [ ] `/dashboard/nps/config/page.tsx`: configurações
- [ ] `/dashboard/nps/responses/page.tsx`: feed de respostas
- [ ] `/dashboard/waitlist/page.tsx`: lista da fila + ações manuais
- [ ] Bot e Link Público: entrada na fila quando sem slots disponíveis

#### Migrations
- [ ] `add_nps_configs`
- [ ] `add_nps_surveys`
- [ ] `add_waitlist_entries`

#### Testes
- [ ] Operation COMPLETED + delay → NpsSurvey enviada
- [ ] Cliente responde nota 10 → registro completo
- [ ] Cancelamento libera slot → primeiro WAITING com match é notificado
- [ ] Segundo cliente na fila não é notificado até o primeiro expirar

---

### Sprint 23 — CRM (classificações automáticas + insights + ficha) 🟢
**Objetivo:** Ficha completa do cliente com classificações automáticas + insights heurísticos.
**Critério de conclusão:** Cliente sem operação há > X dias aparece como "em risco"; sugestão de pacote quando padrão bate.

#### Backend
- [ ] Endpoint `GET /customers/{id}/summary`: agregado em 1 query (histórico, frequência, ticket médio, profissional preferido, serviços preferidos, status calculado)
- [ ] Modelo `CustomerClassification(id, company_id, customer_id, classification_type [NOVO|FREQUENTE|VIP|EM_RISCO|RECUPERADO], computed_at, parameters_snapshot)`
- [ ] Worker `crm.classification_runner` (diário): recalcula classificações conforme `CrmConfig`
- [ ] Modelo `CrmConfig(id, company_id, novo_threshold_days, frequente_min_ops_in_period, frequente_period_months, vip_criteria JSONB, em_risco_multiplier_avg_frequency)`
- [ ] Endpoints de insights: `/crm/insights/at-risk`, `/crm/insights/return-window`, `/crm/insights/package-suggestion`

#### Frontend
- [ ] `/dashboard/customers/[id]/page.tsx` expandida: histórico, classificação, insights, anotações livres, campos custom
- [ ] Badge na agenda: cliente em risco / VIP
- [ ] Pop-up de sugestões ao criar agendamento manual
- [ ] Pop-up de sugestões pós-COMPLETED
- [ ] `/dashboard/dashboard/page.tsx` (Owner/Admin): widget "Clientes em risco"

#### Migrations
- [ ] `add_customer_classifications`
- [ ] `add_crm_configs`

#### Testes
- [ ] Cliente com 5 ops nos últimos 3 meses → classificação FREQUENTE
- [ ] Cliente sem ops há > 2x frequência média → EM_RISCO
- [ ] Insights respeitam scope do PROFESSIONAL (só seus clientes)

---

### Sprint 24 — Painel Owner Paladino 🔵
**Objetivo:** Painel separado para PLATFORM_OWNER operar a plataforma — tenants, saúde, integrações, impersonation controlada, replay.
**Critério de conclusão:** PLATFORM_OWNER vê todos os tenants, status, métricas; impersonation é time-boxed + audit; replay normal funciona, replay forçado bloqueado para consumers financeiros.

#### Backend
- [ ] Endpoints `/owner/*` protegidos por `require_platform_owner()`
- [ ] `/owner/tenants` → lista com status (TRIAL/ACTIVE/SUSPENDED/CHURNED), criar, suspender, reativar
- [ ] `/owner/tenants/{id}/health` → métricas (uso, volume, último acesso, erros, sinais de churn)
- [ ] `/owner/integrations` → status por tenant (Asaas, WhatsApp API)
- [ ] `/owner/system` → falhas, workers, dead-letter, replay controlado
- [ ] `/owner/impersonation/start` (gera JWT time-boxed 30min, read-only default) + `/owner/impersonation/end`
- [ ] `/owner/audit` → audit cross-tenant (meta-audit)
- [ ] `/owner/replay` → POST com `event_id` + motivo obrigatório
- [ ] `/owner/feature-flags` → toggles por tenant ou global
- [ ] Audit cross-tenant: tenant vê o acesso do PLATFORM_OWNER no seu próprio audit
- [ ] Replay forçado bloqueado para consumers de PaymentsEngine, CommissionEngine, FinancialCore (RBAC-2)
- [ ] Credenciais masked (RBAC-3): nunca expõe valor completo, apenas últimos 4 caracteres + status

#### Frontend
- [ ] `/owner/layout.tsx`: layout separado (sem sidebar de tenant)
- [ ] `/owner/page.tsx`: dashboard plataforma
- [ ] `/owner/tenants/page.tsx`: lista
- [ ] `/owner/tenants/[id]/page.tsx`: detalhe + health
- [ ] `/owner/integrations/page.tsx`
- [ ] `/owner/system/page.tsx`: workers + dead-letter
- [ ] `/owner/audit/page.tsx`
- [ ] Banner persistente quando em modo impersonation

#### Migrations
- [ ] `add_audit_log_table` (genérica, append-only)
- [ ] `add_module_activations` (feature flags por tenant)

#### Testes
- [ ] PLATFORM_OWNER lista tenants → 200; tenant ADMIN tenta → 403
- [ ] Impersonation JWT expira em 30 min
- [ ] Replay de `payment.confirmed` → bloqueado
- [ ] Replay de `agenda.soft_reservation.expired` (sem efeito financeiro) → permitido
- [ ] Audit cross-tenant aparece no audit do tenant impersonado

---

### Sprint 25 — Migrations `[SCHEMA APENAS]` + cobertura de testes final 🟡
**Objetivo:** Adicionar todas as estruturas marcadas como `[SCHEMA APENAS]` na visão + elevar cobertura de testes para nível mínimo do Estágio 0.
**Critério de conclusão:** Schemas preparados sem endpoint/UI: locations, múltiplos estoques, encomenda elaborada, FEFO em estoque, variações complexas, insumos checklist, multi-profissional simultâneo, accounting_mode ACCRUAL bloqueado, papéis platform extras; testes cobrindo BookingEngine FSM, conflitos, sinal/depósito, comissões 2 eixos, idempotência.

#### Backend (apenas schema, sem service/router)
- [ ] Migration `Location(id, company_id, name, address, timezone, is_active)` + FK nullable em `appointments`, `professionals`, `stock_items`
- [ ] Migration `StockBatch(id, company_id, stock_item_id, batch_number, quantity, expiry_date)` + algoritmo FEFO em comentário (sem ativar)
- [ ] Migration: `Operation` ganha `requires_multiple_professionals (bool default false)` + tabela `OperationProfessional` (N:N)
- [ ] Migration: `TenantConfig` ganha `accounting_mode (CASH default; ACCRUAL bloqueado por trigger no Estágio 0)`
- [ ] Migration: estender enum `UserRole` com `PLATFORM_SUPPORT`, `PLATFORM_BILLING`, `PLATFORM_READONLY` (sem dependency `require_platform_support` etc. — sem rota)
- [ ] Migration: `EncomendaOrder(...)`, `EncomendaItem(...)` com FSM stub (sem service)
- [ ] Migration: `ServiceInputChecklist(...)` (insumos pós-atendimento)

#### Frontend
- [ ] Nenhuma alteração (são `[SCHEMA APENAS]`)

#### Testes (cobertura mínima Estágio 0)
- [ ] **BookingEngine FSM:** todas as transições (DRAFT → REQUESTED → CONFIRMED → IN_PROGRESS → COMPLETED/CANCELLED/NO_SHOW/FAILED)
- [ ] **Conflito de agenda:** soft + firme, EXCLUDE CONSTRAINT
- [ ] **Sinal/depósito (DEPOSIT):** ponta a ponta (sinal pago → SOFT promove FIRME → COMPLETED cobra saldo)
- [ ] **Comissão (dois eixos):** SERVICE_REFERENCE_PRICE × GROSS_OF_FEES, ALLOCATED_COTA_VALUE × NET_OF_FEES, CUSTOM com `professional_share` + `prior_commission_share`
- [ ] **Idempotência:** `payment.confirmed` 2x, `commission.calculated` 2x, `customer_credit.consumed` 2x
- [ ] **Multi-tenant:** teste cross-tenant para Customer, Operation, Payment, Commission, Movement
- [ ] **RBAC v2:** PROFESSIONAL scope OWN, OPERATOR opt-in `create_manual_adjustment`, ADMIN anti-escalonamento

---

## O que NÃO entra no plano (referência rápida)

Itens explicitamente fora do Estágio 0 (Parte 13 da visão). **Nenhum dos abaixo deve aparecer em nenhuma sprint deste plano**, mesmo que pareça útil:

| Item | Razão |
|------|-------|
| Saldo (moeda interna) / cashback / programa de fidelidade | Estágio 4 (fintech) |
| Conta digital do tenant | Estágio 4 |
| App mobile (cliente ou tenant) | Futuro |
| Bot Tenant (tenant acessa via bot) | Estágio 1+ |
| Gestão Contábil profunda (`accounting_mode=ACCRUAL`) | Estágio 1+ (schema preparado no Sprint 25) |
| API pública para integrações externas | Futuro |
| Múltiplas unidades / multi-estoque na **UI** | Estágio 1+ (schema preparado no Sprint 25) |
| Encomenda elaborada com FSM completa | Estágio 1+ (schema preparado no Sprint 25) |
| Insumos com checklist pós-atendimento na **UI** | Estágio 1+ (schema preparado no Sprint 25) |
| Múltiplos profissionais simultâneos na **UI** | Estágio 1+ (schema preparado no Sprint 25) |
| Escala quinzenal / recorrência customizada de agenda | Estágio 1+ se necessário |
| Sugestões automáticas ao cliente sem trigger manual | Estágio 1+ |
| ML/IA no CRM | Estágio 1+ |
| NFS-e / Nota Fiscal | Estágio 1+ |
| Impressora física conectada | Futuro |
| Cross-tenant (operação de negócio entre tenants) | Futuro |
| Campanhas de marketing | Adiado |
| Onboarding self-service (landing Paladino) | Estágio 0.5 — pós-piloto |
| IA generativa no Bot WhatsApp | Princípio "FSM soberano, IA apenas classificação" — qualquer geração de texto fica para Estágio 1+ |
| FEFO no UI de estoque | Estágio 1+ (schema preparado no Sprint 25) |
| Roles `PLATFORM_SUPPORT/BILLING/READONLY` ativos | Estágio 1+ (schema preparado no Sprint 25) |

---

## Dependências críticas entre sprints

Mapa visual das dependências (ler como "depende de"):

```
Sprint 1  (hardening)              ← raiz
Sprint 2  (RBAC v1 + auth)         ← Sprint 1
Sprint 3  (RBAC v2)                ← Sprint 2
Sprint 4  (Celery+Redis)           ← Sprint 1
Sprint 5  (eventos + comunicação)  ← Sprint 4
Sprint 6  (Financial Core base)    ← Sprint 5
Sprint 7  (Transfer/Reconc/Cash)   ← Sprint 6
Sprint 8  (Asaas adapter)          ← Sprint 5
Sprint 9  (PaymentsEngine)         ← Sprint 6 + Sprint 8
Sprint 10 (Operations FSM)         ← Sprint 5 + Sprint 9
Sprint 11 (Catálogo opt-ins)       ← Sprint 10
Sprint 12 (Comissões)              ← Sprint 6 + Sprint 9 + Sprint 10
Sprint 13 (CustomerCredit)         ← Sprint 5
Sprint 14 (Pacotes)                ← Sprint 13 + Sprint 9 + Sprint 12
Sprint 15 (Assinaturas)            ← Sprint 14 + Sprint 8
Sprint 16 (Promoções)              ← Sprint 9 + Sprint 10
Sprint 17 (Estoque)                ← Sprint 6 + Sprint 9
Sprint 18 (Despesas)               ← Sprint 6
Sprint 19 (Gestão Financeira UI)   ← Sprint 7 + Sprint 9 + Sprint 12 + Sprint 17 + Sprint 18
Sprint 20 (Identidade Paladino)    ← Sprint 5
Sprint 21 (Portal do Cliente)      ← Sprint 20 + Sprint 13 + Sprint 9
Sprint 22 (NPS + Fila)             ← Sprint 5 + Sprint 10
Sprint 23 (CRM)                    ← Sprint 10 + Sprint 13
Sprint 24 (Painel Owner)           ← Sprint 3 + Sprint 5
Sprint 25 (Schema apenas + testes) ← Todos os anteriores
```

**Dependência circular aparente:** Sprint 9 (Pagamentos) e Sprint 10 (Operations) parecem se referenciar mutuamente (DEPOSIT precisa de Agenda soft/firme, e Operations FSM precisa de payment.confirmed para promover SOFT→FIRME). **Solução:** Sprint 9 implementa PaymentsEngine sem o caminho DEPOSIT (apenas POST_DELIVERY e PREPAID). Sprint 10 implementa Operations FSM com soft/firme. Depois, em rebalanço dentro do Sprint 11 (ou em um Sprint 10b dedicado), implementa o caminho DEPOSIT que requer ambos.

---

## Observações finais

1. **`visao-estagio-0.md` é a fonte de verdade.** Qualquer conflito entre este plano e a visão deve ser resolvido **na visão primeiro**, não diretamente em código ou neste plano.

2. **Sprints 1–4 são não-negociáveis** antes de qualquer construção nova. EXCLUDE CONSTRAINT, hardening de segurança, RBAC completo, workers confiáveis e event bus são fundação para todo o resto.

3. **Sprint 9 e Sprint 10 têm interdependência** que justifica atenção especial — sugiro **piloto interno do DEPOSIT** após Sprint 11 antes de expor a clientes.

4. **Sprint 25 não é "limpeza final" descartável** — os schemas `[SCHEMA APENAS]` definem o contrato do Estágio 1+ e devem ser revisados com cuidado. Cobertura de testes nesse sprint é o **piso mínimo** para considerar o Estágio 0 entregue, não o teto.

5. **O `/painel/painel/` aninhado deve sumir no Sprint 1** ou virar issue dedicada. Cada dia que ele continua existindo é um dia de risco de commits no lugar errado.

6. **Painel Owner Paladino (Sprint 24) pode ser antecipado** se piloto com múltiplos tenants exigir antes — porém depende de RBAC v2 (Sprint 3) e Eventos (Sprint 5), então não pode vir antes do Sprint 5.

7. **Identidade Paladino (Sprint 20) é refactor pesado** — migra Customer existente para PaladinoIdentity. Vale considerar feature flag para rollout gradual.

---

*Plano gerado a partir de `visao-estagio-0.md` e relatório de varredura de 2026-05-21. Conflitos devem ser resolvidos na visão antes da implementação.*
