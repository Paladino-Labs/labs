# Análise: Planejado vs. Executado — Estágio 0
**Gerado em:** 2026-06-09 · **Sessão:** análise exclusiva — nenhum arquivo de código foi modificado  
**Fonte:** CLAUDE.md, SPRINT-LOG.md, roadmap-estagio-0.md, plano-execucao-fase3.md, plano-sprint-frontend.md, plano-ajustes-pos-sprint.md + inventário direto do código

---

## 1. Resumo Executivo

O projeto concluiu **15 dos 25 sprints de backend** do Estágio 0 e todos os sprints de infraestrutura/fundação. O backend está sólido até o Sprint 15 (Assinaturas), com 66 migrations em cadeia linear, 400+ testes passando e sem drift de schema. O frontend executou os sprints de design, o Sprint Frontend principal (Blocos A–F, 14 REQs) e o Sprint Frontend Comissões. Estão ausentes os 3 últimos sprints de módulos de negócio (Promoções, Estoque, Despesas), o Sprint 25 de schema-only, e todos os sprints de UI avançada (19–24). O bot WhatsApp tem FSM completa com 16 estados e suporte a escalonamento humano via state HUMANO, mas sem IntentClassifier, sem inbox de atendimento humano no painel e sem handlers para COMPRAR_PRODUTO / COMPRAR_PACOTE. As divergências principais são: PagSeguro com stubs não confirmados; dívida Asaas birthDate em produção; e Sprint 4 (Workers Celery) com flip asyncio→Celery formalmente pendente mas operacionalmente resolvido.

---

## 2. Tabela de Status por Sprint — Backend

### Fase 1 — Fundação Técnica

| Sprint | Nome | Status | Migrations | Testes | Observações |
|--------|------|--------|-----------|--------|-------------|
| Sprint 1 | Hardening crítico | ✅ COMPLETO | `a9b1c2d3e4f5` (overlap exclusion) + bcrypt, slowapi, security headers, uploads Supabase | ✅ | EXCLUDE CONSTRAINT ativa; slowapi 10 req/min/IP em `/auth/login` |
| Sprint 2 | RBAC v1 + Auth completa | ✅ COMPLETO | `b1c2d3e4f5a6`, `b2c3d4e5f6a7`, `b3c4d5e6f7a8` + `f1g2h3i4j5k6` (password_reset), `j1k2l3m4n5o6` | ✅ | PLATFORM_OWNER, forgot/reset/change-password, must_change_password, anti-escalonamento |
| Sprint 3 | TenantConfig, módulos, branding | ✅ COMPLETO | `c1d2e3f4a5b6`, `c2d3e4f5a6b7` | ✅ | TenantConfig, ModuleActivation (10 por tenant), TenantBranding, 16 categories default |
| Sprint 4 | Workers Celery + Redis | ⚠️ PARCIAL | `d1e2f3a4b5c6` (idempotency keys) | ✅ | Celery+Redis ativos; flip asyncio→Celery formalmente "pendente de 24h em produção" (Sprint 4 status: Aberto). Na prática Celery Beat está em uso. `asyncio.create_task` removido do lifespan conforme CLAUDE.md |
| Sprint 5 | Event bus + Comunicação | ✅ COMPLETO | `e1f5g2h3i4j5`, `e2f6h3i4j5k6`, `g1h2i3j4k5l6` (seed template) | ✅ | EventBus in-process, CommunicationService, CommunicationTemplate/Log/Setting, IntegrationCredential com Fernet |
| Sprint RLS | Row Level Security | ✅ COMPLETO | `h1i2j3k4l5m6`, `22bfd8bf16b3`, `i1j2k3l4m5n6` | ✅ | RLS em 26 tabelas; 2 testes de trigger validados contra Supabase em 2026-06-08 |
| Sprint Fechamento | Testes + polish | ✅ COMPLETO | — | ✅ | Password reset, tests sprint3/5, template seed |

### Fase 2 — Módulos Financeiros Fundacionais

| Sprint | Nome | Status | Migrations | Testes | Observações |
|--------|------|--------|-----------|--------|-------------|
| Sprint 6 | Financial Core (Account + Movement + Entry) | ✅ COMPLETO | `k1l2m3n4o5p6`, `l1m2n3o4p5q6`, `m1n2o3p4q5r6`, `n1o2p3q4r5s6`, `o1p2q3r4s5t6` | ✅ | Imutabilidade por trigger+ORM; TenantFeeRoutingPolicy; hook create_company cria Account CAIXA + 7 políticas |
| Sprint 7 | Financial Core (Transfer + Reconciliation + CashCount) | ✅ COMPLETO | `p1q2r3s4t5u6`, `q1r2s3t4u5v6`, `r1s2t3u4v5w6`, `s1t2u3v4w5x6` | ✅ | Transfer atômico; ReconciliationRecord; CashCount ADJUSTED com entry_id vinculado |
| Sprint 8 | Asaas adapter + Subcontas | ✅ COMPLETO | `t1u2v3w4x5y6`, `u1v2w3x4y5z6`, `v1w2x3y4z5a6` | ✅ | AsaasProvider; lazy ensure_customer(); CPF/CNPJ com dígito verificador; dívida birthDate registrada |
| Sprint 9 | PaymentsEngine FSM + webhook | ✅ COMPLETO | `w1x2y3z4a5b6`, `x1y2z3a4b5c6`, `y1z2a3b4c5d6` | ✅ | Payment FSM PENDING→CONFIRMED→REFUNDED; webhook idempotente; DepositPolicy; confirm_manual; fee MDR |
| Sprint 10 | Operations FSM + Agenda granular | ✅ COMPLETO | `z1a2b3c4d5e6`, `a3b4c5d6e7f8`, `b2c3d4e5f6g7`, `c2d3e4f5g6h7` | ✅ | DRAFT/FAILED, ScheduleException, Reservation SOFT/FIRME, DirectOccupancy; expire_soft via Celery |

### Sprint de Integrações (pós-Fase 2)

| Sprint | Nome | Status | Migrations | Testes | Observações |
|--------|------|--------|-----------|--------|-------------|
| Sprint Integrações | Email + Asaas fixes + PagSeguro + CASH manual + MDR | ✅ COMPLETO | `d1e2f3g4h5i6`, `e1f2g3h4i5j6`, `psg1a2b3c4d5`, `f2g3h4i5j6k7`, `g3h4i5j6k7l8`, `h2i3j4k5l6m7`, `i3j4k5l6m7n8`, `j2k3l4m5n6o7` | ✅ 338/338 | PagSeguroProvider com stubs (create_charge, refund não confirmados pelo PagBank); Mailtrap HTTP API; confirm-manual; MDR 8 fontes |

### Fase 3 — Módulos de Negócio (Sprints 11–15)

| Sprint | Nome | Status | Migration | Testes | Observações |
|--------|------|--------|----------|--------|-------------|
| Sprint 11 | Catálogo opt-ins | ✅ COMPLETO | `e2f3g4h5i6j7` | 26 | ServicePricingOverride, ServiceVariant, preparation_minutes, business_hours_structured |
| Sprint 12 | CommissionEngine (2 eixos) | ✅ COMPLETO | `f3g4h5i6j7k8` + `k3l4m5n6o7p8` | 25 | Commission + CommissionPayout; lifecycle CALCULATED→DUE→PAID; commission_fee_policy_v2 |
| Sprint 13 | CustomerCredit + FEFO | ✅ COMPLETO | `g4h5i6j7k8l9` | 25 | CustomerCredit, CustomerCreditConsumption; FEFO por expires_at; expiry_worker |
| Sprint 14 | Pacotes | ✅ COMPLETO | `h3i4j5k6l7m8` | 26 | Package, PackagePurchase; grant CustomerCredit; comissão SELLER |
| Sprint 15 | Assinaturas (recorrência Asaas) | ✅ COMPLETO | `i4j5k6l7m8n9` | 28 | SubscriptionPlan, CustomerSubscription; renewal_worker; inadimplência → SUSPENDED |

**HEAD migration atual:** `k3l4m5n6o7p8` (commission_fee_policy_v2)  
**Total migrations:** 66  
**Total testes estimados:** ~460+ (338 pós-Integrações + 26+25+25+26+28 Fase 3 + Sprint Comissões)

### Backend AUSENTE (Sprints 16–18 + 25)

| Sprint | Nome | Status | Confirmação de ausência |
|--------|------|--------|------------------------|
| Sprint 16 | Promoções/Cupons | ❌ AUSENTE | `app/modules/promotions/` não existe; nenhuma migration `add_promotions*` |
| Sprint 17 | Estoque + Fornecedores + Payables | ❌ AUSENTE | `app/modules/stock/` não existe; `app/modules/suppliers/` não existe |
| Sprint 18 | Despesas + recorrência | ❌ AUSENTE | `app/modules/expenses/` não existe; nenhuma migration `add_expenses*` |
| Sprint 25 | Schema-only + testes de contrato | ❌ AUSENTE | Sem migrations de Location, StockBatch, EncomendaOrder; cobertura FSM/conflito/depósito/comissão-2-eixos não implementada como suite isolada |

---

## 3. Tabela de Status por Sprint — Frontend

### Sprints de Design e Fundação (pré-Sprint Frontend)

| Sprint | Nome | Status | Observações |
|--------|------|--------|-------------|
| Sprint Design (Polish Visual) | Design system Paladino | ✅ COMPLETO | globals.css petrol blue + antique brass; paleta semântica; Cormorant Garamond |
| Sprint Design (Navalha→Paladino) | Transposição visual | ✅ COMPLETO | paladino-wordmark.png; ThemeProvider; dark/light toggle |
| Sprints A–F | Espelhamento barberflow-system | ✅ COMPLETO | BookingFlow G13 (4 steps); Link Público; Vitrine; Agenda; Login 2 colunas |
| Sprint Correção Frontend | Pós-testes de produção | ✅ COMPLETO | 10 bugs corrigidos; NEXT_PUBLIC_API_URL produção; working_hours multi-período |

### Sprint Frontend Principal (Blocos A–F, 14 REQs)

| Bloco | REQs | Status | Observações |
|-------|------|--------|-------------|
| Bloco A | Sidebar, Auth name, Logo | ✅ COMPLETO | MENU; User.name no header; logo maior |
| Bloco B | Painel + Agenda | ✅ COMPLETO | `/agenda` como rota canônica; calendário default; `/appointments` redireciona |
| Bloco C | CPF profissional | ✅ COMPLETO | Campo CPF removido do formulário |
| Bloco D | Módulo Financeiro | ✅ COMPLETO | `/financeiro`, `/financeiro/pagamentos`, `/financeiro/pagamentos/novo`, `/financeiro/movimentacoes`; CustomerAutocomplete; FeeWarningBanner |
| Bloco E | Configurações expandidas | ✅ COMPLETO | `/settings/taxas`, `/settings/integracoes`, `/settings/comunicacao`, `/settings/usuarios`; redirects `/users` e `/integrations` |
| Bloco F | Convite + ativação | ✅ COMPLETO | `/activate?token=` com nome opcional; login automático pós-ativação |
| Ajustes 1–8 | Pós-sprint | ✅ COMPLETO | guard hydrated; parseDetailMessage; taxas em `/financeiro/taxas`; PagSeguro escondido; link agendamento em perfil; `/settings/perfil`; PaymentOnCompleteDialog; dashboard KPIs+Recharts |
| Ajuste 9 | Subconta Asaas (backend + frontend) | ⚠️ PARCIAL | **Backend concluído** (migration `i3j4k5l6m7n8`, 8 colunas owner_* em companies, AsaasProvider aceita todos os campos). **Frontend pendente**: formulário expandido em settings/integracoes aba Asaas (5 campos: mobilePhone, incomeValue, address, addressNumber, province, postalCode) |

### Sprint Frontend Comissões

| Bloco | Status | Rotas criadas | Observações |
|-------|--------|--------------|-------------|
| Comissões | ✅ COMPLETO (planejamento 2026-06-08; execução confirmada) | `/comissoes`, `/comissoes/pagamentos`, `/comissoes/historico`, `/comissoes/politicas` | 4 rotas novas; migration k3l4m5n6o7p8 (commission_fee_policy_v2) no backend |

### Sprints de Frontend AUSENTES (roadmap original Sprints 19–24)

| Sprint | Nome | Status | O que falta |
|--------|------|--------|-------------|
| Sprint 19 | Gestão Financeira UI completa + Dashboard role-aware | ❌ AUSENTE | DRE mensal; `/financial/dre`; dashboard por papel (OWNER/ADMIN/OPERATOR/PROFESSIONAL); reconciliação UI; cash-counts UI. Básico de pagamentos/movimentações existe mas não é a UI completa do Sprint 19 |
| Sprint 20 | Identidade Paladino 3 níveis | ❌ AUSENTE | PaladinoIdentity; PhoneIdentityResolver E.164; ConsentRecord — nenhuma UI nem backend deste sprint |
| Sprint 21 | Portal do Cliente | ❌ AUSENTE | `/customer/*` — nenhuma rota existe |
| Sprint 22 | NPS + Fila de Espera | ❌ AUSENTE | NpsConfig, NpsSurvey, WaitlistEntry — nenhum modelo nem UI |
| Sprint 23 | CRM (classificações + insights) | ❌ AUSENTE | Ficha expandida `/customers/[id]` existe mas sem agregações; sem CustomerClassification; sem CrmConfig |
| Sprint 24 | Painel Owner Paladino | ❌ AUSENTE | `/owner/*` — nenhuma rota existe; sem endpoints `/owner/*` no backend |

---

## 4. Estado do Bot WhatsApp

### Handlers FSM existentes (16 estados)

| Estado FSM | Arquivo handler | Intenção coberta |
|-----------|----------------|-----------------|
| `INICIO` | `handlers/inicio.py` | Início da conversa; coleta de nome se cliente novo |
| `AGUARDANDO_NOME` | `handlers/aguardando_nome.py` | Coleta nome do novo cliente |
| `CONFIRMAR_NOME` | (inline em `inicio.py`) | Confirmação do nome digitado |
| `OFERTA_RECORRENTE` | `handlers/oferta_recorrente.py` | Oferta de reagendamento recorrente |
| `MENU_PRINCIPAL` | `handlers/menu_principal.py` | Menu: Agendar / Ver agendamentos / Falar com atendente |
| `ESCOLHENDO_SERVICO` | `handlers/escolhendo_servico.py` | Seleção de serviço do catálogo |
| `ESCOLHENDO_PROFISSIONAL` | `handlers/escolhendo_profissional.py` | Seleção de profissional |
| `ESCOLHENDO_DATA` | `handlers/escolhendo_data.py` | Seleção de data via calendário |
| `ESCOLHENDO_TURNO` | `handlers/escolhendo_turno.py` | **Mantido no código** apesar de AWAITING_SHIFT ter sido removido do fluxo principal; step não é mais enviado pelo FSM |
| `ESCOLHENDO_HORARIO` | `handlers/escolhendo_horario.py` | Seleção de horário |
| `CONFIRMANDO` | `handlers/confirmando.py` | Confirmação final do agendamento |
| `VER_AGENDAMENTOS` | `handlers/ver_agendamentos.py` | Listagem de agendamentos ativos |
| `GERENCIANDO_AGENDAMENTO` | `handlers/gerenciando_agendamento.py` | Ações sobre um agendamento existente |
| `CANCELANDO` | `handlers/cancelando.py` | Cancelamento com confirmação |
| `REAGENDANDO` | `handlers/reagendando.py` | Remarcação de agendamento |
| `HUMANO` | (inline em `bot_service.py`) | Bot silencia; atendente assume a conversa |

### Estado de conversa vs. planejado

| Estado planejado | Implementado? | Observação |
|-----------------|--------------|-----------|
| `BOT_ATIVO` (implícito — todos os estados acima exceto HUMANO) | ✅ SIM | Comportamento default |
| `EM_ATENDIMENTO_HUMANO` → `STATE_HUMANO` | ⚠️ PARCIAL | Estado existe no banco e no FSM; bot silencia quando HUMANO. **Gap: sem inbox de atendimento humano no painel**; atendente não tem onde ver/responder as conversas |
| `RESOLVIDA` | ❌ AUSENTE | Sem transição explícita de HUMANO → RESOLVIDA; sessão expira por TTL |

### IntentClassifier e intenções

| Item | Status |
|------|--------|
| Diretório `whatsapp/intent/` | ❌ NÃO EXISTE |
| `IntentClassifier` | ❌ NÃO EXISTE |
| Classificação de intenção | ⚠️ HARDCODED — `helpers.py:is_universal_command()` faz matching textual simples por string literal |
| Intenção AGENDAR | ✅ via menu + handlers FSM |
| Intenção REMARCAR | ✅ via `REAGENDANDO` |
| Intenção CANCELAR | ✅ via `CANCELANDO` |
| Intenção CONSULTAR (ver agendamentos) | ✅ via `VER_AGENDAMENTOS` |
| Intenção FALAR_COM_HUMANO | ⚠️ PARCIAL — state HUMANO existe, sem inbox no painel |
| Intenção COMPRAR_PRODUTO | ❌ AUSENTE — sem handler |
| Intenção COMPRAR_PACOTE | ❌ AUSENTE — sem handler |
| Catálogo dinâmico de intenções por tenant | ❌ AUSENTE — intenções hardcoded |

---

## 5. Backend Pendente para Fechar o Estágio 0

Os seguintes sprints do plano original não foram executados. Confirmação de ausência via código:

### Sprint 16 — Promoções e Cupons
- `app/modules/promotions/` **não existe**
- Sem migrations `add_promotions`, `add_coupons`, `add_coupon_redemptions`, `add_discount_applications`
- Sem Promotion, Coupon, CouponRedemption, DiscountApplication
- Sem algoritmo cumulative/exclusive
- Sem `apply_manual_discount_override`
- Sem worker `promotions.expiry_scanner`
- **Dependências satisfeitas:** Sprint 9 (Pagamentos) ✅ e Sprint 10 (Operations) ✅

### Sprint 17 — Estoque + Fornecedores + Payables
- `app/modules/stock/` **não existe**
- Sem migrations `add_suppliers`, `add_stock_items`, `add_stock_entries`, `add_stock_movements`, `add_payables`, `add_payable_installments`
- `products.stock` já existe (adicionado em `d1e2f3g4h5i6`) — sprint deve usar `ADD COLUMN IF NOT EXISTS` para `stock_min_alert` e `unit`
- Sem custo médio ponderado, sem worker `payable.due_soon/overdue`
- **Dependências satisfeitas:** Sprint 6 ✅ e Sprint 9 ✅

### Sprint 18 — Despesas + recorrência
- `app/modules/expenses/` **não existe**
- Sem migration `add_expenses`
- Sem Expense model, sem recurrence_rule JSONB, sem workers `expense.due_soon`, `expense.overdue`, `expense.recurrence_generator`
- **Dependências satisfeitas:** Sprint 6 ✅

### Sprint 25 — Schema-only + testes de contrato
- Sem migrations de: `Location`, `StockBatch`, `OperationProfessional`, `EncomendaOrder`, `EncomendaItem`, `ServiceInputChecklist`
- `TenantConfig.accounting_mode` com trigger `block_accrual_mode` **já existe** (Sprint 3) — parcialmente satisfeito
- UserRole com `PLATFORM_SUPPORT/BILLING/READONLY` **já existe no enum** (Sprint 2) — parcialmente satisfeito
- Testes de cobertura mínima do Estágio 0 (BookingEngine FSM completo, conflito soft+firme, sinal/depósito ponta-a-ponta, comissão 2 eixos, idempotência, multi-tenant, RBAC v2 scope) **não existem como suite dedicada**

### Sprint 2.0 — IntentClassifier WhatsApp
- `whatsapp/intent/` **não existe**
- Sem classificador de intenções por ML/regras
- Pré-requisito do Estágio 0 conforme roadmap; depende dos módulos de produtos/pacotes existirem para as intenções COMPRAR_PRODUTO / COMPRAR_PACOTE fazerem sentido

### Sprint 2.6 — Integração do classificador com FSM
- Bloqueado pelo Sprint 2.0

---

## 6. Frontend Pendente para Fechar o Estágio 0

### Módulos com backend pronto mas sem UI

| Módulo | Backend | Frontend | O que falta |
|--------|---------|----------|-------------|
| Pacotes | ✅ Sprint 14 | ❌ AUSENTE | `/dashboard/packages/page.tsx`; fluxo de venda; CRUD de pacotes |
| Assinaturas | ✅ Sprint 15 | ❌ AUSENTE | `/dashboard/subscriptions/plans/page.tsx`; `/dashboard/subscriptions/page.tsx` |
| CustomerCredit | ✅ Sprint 13 | ❌ AUSENTE | Ficha do cliente com cotas ativas (validade + saldo); `/customers/[id]/grant-cota` |
| Ajuste 9 subconta Asaas | ✅ Backend | ⚠️ Frontend parcial | Formulário expandido na aba Asaas (5 campos faltantes) |

### Sprints 19–24 completos

| Sprint | Backend necessário | Frontend | O que falta |
|--------|------------------|----------|-------------|
| Sprint 19 — Gestão Financeira UI + role-aware | Sprint 6–9 ✅ + Sprint 12 ✅ + Sprints 17–18 ❌ | ❌ | DRE; alertas; OWNER/ADMIN/OPERATOR/PROFESSIONAL dashboards distintos; reconciliação UI; cash-counts UI |
| Sprint 20 — Identidade Paladino | ❌ (Sprint 20 não executado) | ❌ | PaladinoIdentity; ConsentRecord — tudo |
| Sprint 21 — Portal do Cliente | ❌ (Sprint 21 não executado) | ❌ | `/customer/*` — tudo |
| Sprint 22 — NPS + Fila de Espera | ❌ (Sprint 22 não executado) | ❌ | NPS, waitlist — tudo |
| Sprint 23 — CRM | ❌ (Sprint 23 não executado) | ❌ | Classificações automáticas, insights, ficha expandida |
| Sprint 24 — Painel Owner | ❌ (Sprint 24 não executado) | ❌ | `/owner/*` — tudo |

### Dívidas de UI remanescentes (pré-Sprint 19)

| Item | Arquivo | Status |
|------|---------|--------|
| Sidebar sem filtro por role | `Sidebar.tsx` | Dívida registrada — RBAC visível no frontend é Fase 3 |
| Dashboard único para todos os papéis | `dashboard/page.tsx` | Dívida registrada — Sprint 19 |
| settings/financial/page.tsx orphan (sem link no hub) | `settings/financial/page.tsx` | Orphan documentado — manter ou adicionar redirect |
| Múltiplos períodos/dia no formulário de profissional | `professionals/[id]/page.tsx` | Dívida registrada — UI ainda envia período único |
| Campo specialty no formulário de profissional | `professionals/[id]/page.tsx` | Dívida registrada |
| Campo stock no formulário de produto | `products/page.tsx` | Dívida registrada |
| G13 BookingFlow: TTL de soft reservation visível | `BookingFlow.tsx` | Dívida registrada — aguarda Sprint 10 features expostas |

---

## 7. Divergências Relevantes

### 7.1 PagSeguro — stubs não confirmados (dívida ativa de integração)
**Planejado:** Sprint 8 previa `create_charge()`, `refund()` e `list_terminals()` para terminais físicos PagSeguro Point.  
**Executado:** `PagSeguroProvider` implementado com OAuth2, mas endpoints REST de PagSeguro Point **não existem na documentação pública**. `create_charge()` usa `/orders` como proxy não confirmado; `refund()` usa `/charges/{id}/cancel` sem confirmação; `list_terminals()` é stub puro.  
**Consequência:** PagSeguro escondido na UI (componente comentado em `settings/integracoes`). Não ativar em produção até confirmação do time comercial PagBank.  
**Ação necessária:** Confirmar endpoints com PagBank ou remover o provider do Sprint 17 MVP.

### 7.2 Asaas birthDate — dívida de produção ativa
**Planejado:** Sprint 8 previa criação de subconta Asaas completa no onboarding.  
**Executado:** `create_subaccount()` enviava apenas name/email/companyType; `birthDate` ausente causava rejeição para CPF.  
**Correção parcial:** Ajuste 9 backend (2026-06-08) adicionou 8 colunas owner_* em companies e o `AsaasProvider` aceita todos os campos. **Frontend ainda pendente** (5 campos de endereço/telefone/renda não estão no formulário da aba Asaas).  
**Consequência:** Tenants criados antes do Ajuste 9 não têm `external_account_id` populado — subconta Asaas inexistente.

### 7.3 Sprint 4 — status formalmente Aberto
**Planejado:** Sprint 4 "Aprovado" após 24h em produção sem erros.  
**Estado atual:** Sprint 4 está marcado como `⚠️ Aberto` no SPRINT-LOG porque o commit final (pós-flip asyncio→Celery) nunca foi feito formalmente.  
**Na prática:** CLAUDE.md confirma que `asyncio.create_task` foi removido do lifespan e Celery Beat é o único mecanismo de workers. O sprint está funcionalmente completo; apenas o registro formal no SPRINT-LOG está pendente.

### 7.4 `evolution_client` direto vs. CommunicationService
**Planejado:** Sprint 5 previa remoção das chamadas diretas `evolution_client.send_text()` após 1 semana com feature flag ativa.  
**Estado atual:** CLAUDE.md ainda lista como dívida "chamadas diretas evolution_client — remover após 1 semana de flag ativa". A feature flag `use_communication_service` existe no TenantConfig (default False). Chamadas diretas coexistem com o CommunicationService.  
**Consequência:** Risco de inconsistência de logs (CommunicationLog não captura envios via evolution_client direto).

### 7.5 Sprints 11–15 executados em sequência acelerada
**Planejado:** Sprints 11–15 estavam no roadmap de Fase 3 como sprints de 2 semanas cada.  
**Executado:** Todos concluídos entre 2026-06-07 e 2026-06-08 (2 dias), num ritmo de sprint/hora.  
**Consequência:** Testes unitários existem (26+25+25+26+28) mas a suite de **testes de contrato** (ponta-a-ponta: DEPOSIT path, comissão 2 eixos, idempotência dupla, multi-tenant) não foi criada. Está planejada para Sprint 25 mas esse sprint foi pulado.

### 7.6 Sprint Frontend Comissões — status não documentado
**Estado:** As rotas `/comissoes/*` (4 páginas) existem no painel e a migration `k3l4m5n6o7p8` (commission_fee_policy_v2) existe no backend. O memory file registra o plano como "gerado 2026-06-08" com divergências de prefixo de endpoint e status enum.  
**Gap:** SPRINT-LOG não tem entrada para este sprint; CLAUDE.md não menciona as rotas de comissões. Status de convergência entre o frontend e o endpoint `/commissions/*` não auditado.

### 7.7 Dívida de email em produção
**Estado:** Railway bloqueia SMTP (portas 25/465/587/2525). A implementação atual usa Mailtrap HTTP API (sandbox only).  
**Consequência:** Em produção, recuperação de senha e convites de usuário dependem das credenciais Mailtrap configuradas. Para produção real, substituir por SendGrid/Mailgun/Mailtrap Email API transacional.

### 7.8 Asaas refund — estorno apenas contábil
**Planejado:** Sprint 9 previa `refund()` chamando `provider.refund()` no gateway.  
**Estado atual:** `payment_service.refund()` faz o estorno contábil (Movement OUTFLOW + Entry ESTORNO) mas **não chama** `provider.refund()`. O gateway externo não processa o estorno automaticamente.  
**Consequência:** Estornos exibidos no painel não são reembolsados via Asaas automaticamente. Requer processo manual no painel Asaas.

---

## 8. Recomendação de Sequência para os Próximos Sprints

> **Nota:** Esta seção lista apenas a sequência técnica recomendada com base no estado atual, sem definir timelines. Não é um plano de execução.

### Prioridade 1 — Fechar dívidas ativas antes de avançar

| Item | Tipo | Urgência |
|------|------|----------|
| Ajuste 9 frontend (formulário Asaas expandido) | UI | Alta — bloqueia ativação de subcontas em produção |
| Sprint 4 formal close (commit CLAUDE.md + SPRINT-LOG) | Housekeeping | Baixa — funcional, apenas registro |
| Remover chamadas diretas `evolution_client` + ativar feature flag | Código | Média — inconsistência de logs |
| Confirmar ou remover PagSeguroProvider endpoints não documentados | Produto | Alta — stubs em produção são risco |
| Asaas refund → chamar `provider.refund()` | Código | Média — estornos são manuais hoje |

### Prioridade 2 — Completar o backend do Estágio 0

Sequência natural por dependências:
1. **Sprint 18 — Despesas** (depende só do Sprint 6 ✅)
2. **Sprint 17 — Estoque** (depende Sprint 6 ✅ + Sprint 9 ✅; `products.stock` já existe)
3. **Sprint 16 — Promoções** (depende Sprint 9 ✅ + Sprint 10 ✅)
4. **Sprint 25 — Schema-only + testes de contrato** (após todos os anteriores)
5. **Sprint 2.0 — IntentClassifier** (após Sprints 17 para COMPRAR_PRODUTO fazer sentido)
6. **Sprint 2.6 — Integração classificador com FSM** (após Sprint 2.0)

### Prioridade 3 — Frontend dos módulos com backend pronto

1. **UI de Pacotes** (Sprint 14 ✅ backend) — fluxo de venda + CRUD
2. **UI de Assinaturas** (Sprint 15 ✅ backend) — plans + lista de assinantes
3. **UI de CustomerCredit na ficha do cliente** (Sprint 13 ✅ backend)
4. **Gestão Financeira UI parcial** (Sprint 19 — apenas o que tem backend: DRE sem Estoque/Despesas, reconciliação, cash-counts)

### Prioridade 4 — Sprints de relacionamento e canais (Sprint 20+)

Depende de backend ausente; não executar antes de fechar Prioridade 2.

---

*Documento gerado em 2026-06-09. Sessão exclusiva de análise — nenhum arquivo de código foi modificado.*  
*Conflitos entre este diagnóstico e o estado real do código devem ser resolvidos verificando os arquivos fonte, não este documento.*
