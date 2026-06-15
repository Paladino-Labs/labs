# PALADINO — INVENTÁRIO FUNCIONAL COMPLETO (FRONTEND)

**Documento mestre para guiar toda a implementação do frontend do Painel do Tenant, Portal do Cliente, Painel Owner e telas públicas.**

- **Derivado de:** `visao-estagio-0.md`, `agendamento_engine/openapi.json` (224 endpoints, 43 tags), `painel/` atual, `docs/plano-estagio-0-completo.md`, `docs/conformidade-estagio-0.md`.
- **Backend:** Estágio 0 completo — 15 sprints, head único `e0s25f_product_extras`, 951 testes verdes. **Todos os módulos abaixo têm backend pronto** salvo onde marcado `[SCHEMA APENAS]`.
- **Regra de escopo:** o que não está aqui pertence ao Estágio 1+ e não deve ser construído agora (ver `visao-estagio-0.md` Parte 13).
- **Natureza:** sessão de análise/planejamento. Nenhum arquivo de código foi modificado.

---

## 1. RESUMO EXECUTIVO

### Números

| Métrica | Valor |
|---|---|
| Tags (módulos) no OpenAPI | 43 |
| Endpoints totais | 224 |
| Endpoints públicos (sem auth) | 34 |
| Endpoints paginados | 6 (`appointments`, `audit/logs`, `audit/impersonation-accesses`, `communication/logs`, `portal/history`, `platform/audit`) |
| Endpoints multipart/upload | 2 (`POST /uploads/`, `POST /financial/statement/import`) |
| **Telas mapeadas (total)** | **~96** |
| Telas já implementadas no painel | ~32 page.tsx |
| Telas pendentes | ~64 |

### Estado por superfície

| Superfície | Estado |
|---|---|
| **Painel do Tenant** | Núcleo operacional + financeiro básico + comissões implementados. ~18 módulos com backend pronto **sem UI**. |
| **Portal do Cliente** | **0% implementado.** 18 endpoints `/portal/*` prontos. App separado, sem sidebar do painel. |
| **Painel Owner** | **0% implementado.** 13 endpoints `/platform/*` prontos. App/área separada, acesso `PLATFORM_OWNER`. |
| **Telas públicas** | Link público (`book/[slug]`) implementado. Faltam `/manage/{token}` (gestão sem login) e `/nps/respond/{survey_id}`. |

### Módulos com backend pronto esperando UI (alta prioridade)

CRM · CustomerCredits (cotas) · Estoque · Fornecedores · Payables · Despesas · Promoções/Cupons · Pacotes · Assinaturas · NPS · Fila de Espera · Inbox de atendimento humano · DRE · Extrato bancário (statement) · Contas/Movimentos/Conciliação (Financial Core completo) · Cash Count · Deposit Policies · Módulos do tenant (ativar/desativar) · Branding · Audit · WhatsApp (conexão/QR) · Portal do Cliente · Painel Owner.

---

## 2. DESIGN TOKENS (referência para TODAS as telas)

Tokens semânticos já definidos em `painel/app/globals.css`. **Nunca hardcodar cores** — sempre os tokens abaixo.

| Token | Valor | Uso |
|---|---|---|
| Background principal | `#faf9f5` | fundo de página (`bg-background`) |
| Primária / brand | `#16242c` (petrol escuro) | sidebar, botões primários (`bg-primary`, `bg-sidebar`) |
| Accent | `#c79a5a` (brass/ouro antigo) | destaques, item ativo, ícones de marca (`text-sidebar-primary`) |
| Tipografia marca | Cormorant Garamond / serif (`--font-display`) | "PALADINO", títulos `h1/h2/h3`, labels do sidebar |
| Tipografia corpo | Inter / sans-serif | texto corrido |
| Sidebar | fundo `#16242c`, texto/ícones claros (`text-sidebar-foreground`) | navegação |

### Convenções herdadas (de `painel/CLAUDE.md`)

- Tokens semânticos: `bg-card`, `border-border`, `text-muted-foreground`, `bg-primary` — nunca `bg-white`/`text-gray-*`.
- `h1/h2/h3` herdam Cormorant Garamond via `@layer base`; em `span/div` use `[font-family:var(--font-display)]`.
- Ícones: **Lucide** 16px / `strokeWidth 1.5` — nunca emojis.
- Item de nav ativo: `italic` + `◆` accent.
- Moeda: `formatBRL()` de `lib/utils.ts`. Datas: `formatDateTime()` com `timeZone` explícito.
- Identidade por tenant via **tokens** (logo, cores, fonte, favicon) — UI única, nunca layouts paralelos por tenant. Customização via `GET/PUT /tenant/branding`.
- **Nomenclatura Estágio 0:** `professionals` → "Barbeiros"; campos de cliente/serviço com fallback `"Em breve"` quando ausentes.

---

## 3. ESTRUTURA DE ROTAS NEXT.JS (App Router)

Quatro grupos de rota por superfície de produto. Os grupos `(portal)` e `(owner)` são **shells distintos** (sem o sidebar do tenant).

```
app/
  page.tsx                         ← login do tenant (já existe)
  activate/                        ← ativação de convite (já existe)
  forgot-password/                 ← (já existe)
  reset-password/                  ← (já existe)

  (dashboard)/                     ← Painel do Tenant (sidebar petrol)
    dashboard/                     ← home role-aware (já existe)
    agenda/                        ← (já existe)
    appointments/                  ← operações/atendimentos (já existe)
      new/                         ← (já existe)
    customers/                     ← clientes/CRM (já existe)
      [id]/                        ← ficha (já existe)
    crm/                           ← PENDENTE — alertas, classificações, config
    catalogo/
      servicos/                    ← migrar de /services
      produtos/                    ← migrar de /products + estoque/imagens
      categorias/                  ← PENDENTE
    profissionais/                 ← /professionals (já existe) + jornada/overrides
    pacotes/                       ← PENDENTE (planos + compras)
    assinaturas/                   ← PENDENTE (planos + instâncias)
    promocoes/                     ← PENDENTE (promoções + cupons)
    financeiro/
      page.tsx                     ← gestão financeira (já existe)
      pagamentos/                  ← (já existe) + novo/ + [id]
      movimentacoes/               ← (já existe)
      extrato/                     ← PENDENTE (import CSV, match, dismiss)
      dre/                         ← PENDENTE
      contas/                      ← PENDENTE (accounts + saldos + transfers)
      conciliacao/                 ← PENDENTE (reconciliation + cash-count)
      taxas/                       ← fee-policies (já existe)
    comissoes/                     ← (já existe: page, historico, pagamentos, politicas)
    estoque/                       ← PENDENTE (stock + movements + orders)
    fornecedores/                  ← PENDENTE
    payables/                      ← PENDENTE (contas a pagar + parcelas)
    despesas/                      ← PENDENTE
    nps/                           ← PENDENTE (config + surveys)
    fila/                          ← PENDENTE (config + entries)
    inbox/                         ← PENDENTE (conversas escaladas)
    comunicacao/                   ← PENDENTE (templates + logs); hoje só em settings/comunicacao
    audit/                         ← PENDENTE
    settings/                      ← hub (já existe)
      perfil/  profile/  security/  comunicacao/  financial/  taxas/  usuarios/
      integracoes/                 ← (já existe) + whatsapp/QR
      modulos/                     ← PENDENTE (ativar/desativar módulos)
      branding/                    ← PENDENTE

  (owner)/                         ← Painel Owner (PLATFORM_OWNER) — PENDENTE 100%
    tenants/  [company_id]/
    saude/  integracoes/  sistema/  impersonation/  flags/  audit/  settings/

  (portal)/                        ← Portal do Cliente — PENDENTE 100%
    login/  register/  magic-link/
    dashboard/  historico/  cotas/  assinaturas/  consentimentos/
    pagamentos/  perfil/

  (public)/                        ← sem auth, sem sidebar
    book/[slug]/                   ← Link público (já existe)
    gestao/[token]/                ← PENDENTE — link de gestão de agendamento
    nps/[survey_id]/               ← PENDENTE — resposta NPS pública
```

> **Nota de migração:** rotas atuais usam nomes em inglês (`/services`, `/products`, `/payments`, `/users`) e duplicam pagamentos em `/payments` e `/financeiro/pagamentos`. Consolidar na implementação (ver §5).

---

## 4. SIDEBAR POR ROLE

Sidebar atual (`components/Sidebar.tsx`) tem 8 links **sem filtro por role** (`roles: null`). O Estágio 0 (Fase 3) exige sidebar role-aware. Estrutura-alvo com submenus:

### OWNER / ADMIN (visão completa)

```
Operação
  Dashboard · Agenda · Operações · Fila de espera · Atendimento humano (Inbox)
Relacionamento
  Clientes / CRM · Comunicação
Comercial
  Catálogo (Serviços · Produtos · Categorias) · Pacotes/Assinaturas · Promoções/Cupons
Financeiro
  Pagamentos · Gestão Financeira (DRE · Contas · Conciliação) · Despesas
  Estoque/Fornecedores · Payables · Comissões · Extrato · Taxas
Administração
  Profissionais · Usuários/Acessos · Configurações (Branding · Módulos · Canais) · Relatórios · Audit
```
ADMIN: idêntico, exceto ações OWNER-exclusivas (atribuir ADMIN/OWNER, transfer-ownership, export audit) ocultas/desabilitadas.

### OPERATOR (operação diária, sem financeiro sensível salvo config)

```
Dashboard · Agenda · Operações · Fila · Atendimento humano
Clientes · Catálogo (view) · Pagamentos (cobranças) · Caixa (CashCount)
```
Oculto por default: DRE, Contas, Comissões payout, Audit, Usuários, Branding/Módulos. Itens "opt-in por config" (manual-adjustment, transfer, statement) aparecem só se a config do tenant habilitar.

### PROFESSIONAL (escopo próprio)

```
Dashboard (meus atendimentos) · Agenda (própria) · Operações próprias (iniciar/concluir/remarcar/cancelar)
Clientes atendidos (view) · Extrato de comissões próprias (se visibilidade ativada)
```
Sem: catálogo (edição), financeiro global, usuários, configurações, audit.

> Implementação: estender `NAV_LINKS` com `roles: string[]` real e mapa de grupos/submenus. RBAC do frontend espelha PARTE 4 da visão; a verdade é o backend (403 → ocultar).

---

## 5. TABELA MESTRE DE TELAS

Legenda Backend: ✅ pronto · ⚠️ parcial · 🔲 `[SCHEMA APENAS]` (não construir).
Status: **Feito** · **Ajustar** (existe mas desalinhada/incompleta) · **Pendente**.
Prioridade: **P0** bloqueante de negócio · **P1** valor alto · **P2** secundária.

### Núcleo / Auth / Identidade

| Módulo | Tela | Rota | Role | Backend | Status | Prio |
|---|---|---|---|---|---|---|
| Auth | Login | `/` | público | ✅ `/auth/login` | Feito | — |
| Auth | Ativação de convite | `/activate` | público | ✅ `/auth/activate` | Feito | — |
| Auth | Esqueci a senha | `/forgot-password` | público | ✅ `/auth/forgot-password` | Feito | — |
| Auth | Reset de senha | `/reset-password` | público | ✅ `/auth/reset-password` | Feito | — |
| Auth | Perfil do usuário / trocar senha | `/settings/perfil`,`/security` | todos | ✅ `/auth/me`,`/auth/profile`,`/auth/change-password` | Feito | — |

### Dashboard

| Módulo | Tela | Rota | Role | Backend | Status | Prio |
|---|---|---|---|---|---|---|
| Dashboard | Home role-aware | `/dashboard` | todos | ⚠️ composto (sem endpoint dedicado) | Ajustar (tornar role-aware + alertas) | P0 |

### Agenda / Operações

| Módulo | Tela | Rota | Role | Backend | Status | Prio |
|---|---|---|---|---|---|---|
| Agenda | Calendário (dia/semana) | `/agenda` | OWNER/ADMIN/OPERATOR/PROF | ✅ `availability/slots`, `agenda/*` | Feito | — |
| Operações | Lista de atendimentos (FSM) | `/appointments` | todos (scope) | ✅ `/appointments/` (paginado) | Feito | — |
| Operações | Novo agendamento | `/appointments/new` | OWNER/ADMIN/OPERATOR | ✅ `POST /appointments/` | Feito | — |
| Operações | Detalhe / transições (cancel/complete/reschedule) | `/appointments/[id]` | scope | ✅ `PATCH .../cancel|complete|reschedule` | Ajustar (detalhe + DEPOSIT/saldo) | P1 |
| Agenda | Jornada/Exceções/Bloqueios | `/profissionais/[id]` (aba) | OWNER/ADMIN | ✅ `schedule/working-hours|exceptions|blocks` | Ajustar (verificar UI completa) | P1 |
| Fila | Configuração | `/fila` (config) | OWNER/ADMIN | ✅ `waitlist/config` | Pendente | P1 |
| Fila | Entradas | `/fila` | OWNER/ADMIN/OPERATOR | ✅ `waitlist/entries` | Pendente | P1 |
| Inbox | Conversas escaladas | `/inbox` | OWNER/ADMIN/OPERATOR | ✅ `/conversations`, `.../messages`, `/reply`, `/resolve` | Pendente | P1 |

### Clientes / CRM / Identidade

| Módulo | Tela | Rota | Role | Backend | Status | Prio |
|---|---|---|---|---|---|---|
| Clientes | Lista (paginada) | `/customers` | OWNER/ADMIN/OPERATOR/PROF | ✅ `/customers/` | Feito (verificar visit_count/total_spent) | — |
| Clientes | Ficha do cliente | `/customers/[id]` | scope | ✅ `/customers/{id}`, `/appointments`, `/classification`, `/insights` | Ajustar (insights/classificação) | P1 |
| CRM | Alertas (churn, retorno) | `/crm` (dashboard) | OWNER/ADMIN | ✅ `/crm/alerts` | Pendente | P1 |
| CRM | Classificações | `/crm/classificacoes` | OWNER/ADMIN | ✅ `/crm/classifications` | Pendente | P1 |
| CRM | Configuração de classificação | `/crm/config` | OWNER/ADMIN | ✅ `/crm/config` (GET/PUT) | Pendente | P2 |
| CustomerCredit | Cotas/saldo do cliente | `/customers/[id]` (aba) | OWNER/ADMIN/OPERATOR | ✅ `customer-credits`, `/balance`, `/grant-cota`, `/revoke` | Pendente | P1 |
| Identidade | Consentimentos do cliente | `/customers/[id]` (aba) | OWNER/ADMIN | ✅ `customers/{id}/consents` (list/grant/revoke) | Pendente | P2 |

### Catálogo

| Módulo | Tela | Rota | Role | Backend | Status | Prio |
|---|---|---|---|---|---|---|
| Serviços | Lista + CRUD | `/services` → `/catalogo/servicos` | OWNER/ADMIN | ✅ `/services/` | Feito (migrar rota) | — |
| Serviços | Variantes | (modal/aba) | OWNER/ADMIN | ✅ `services/{id}/variants` | Ajustar | P2 |
| Produtos | Lista + CRUD + imagens | `/products` → `/catalogo/produtos` | OWNER/ADMIN | ✅ `/products/`, `POST /uploads/` (multipart) | Ajustar (upload até 5 imgs) | P1 |
| Categorias | CRUD de categorias/tags | `/catalogo/categorias` | OWNER/ADMIN (OPERATOR config) | ✅ `/categories/` | Pendente | P2 |
| Profissionais | Lista + ficha | `/professionals` | OWNER/ADMIN | ✅ `/professionals/` | Feito | — |
| Profissionais | Serviços por profissional | `/professionals/[id]` (aba) | OWNER/ADMIN | ✅ `professionals/{id}/services` | Ajustar | P1 |
| Profissionais | Overrides de preço/duração | `/professionals/[id]` (aba) | OWNER/ADMIN | ✅ `professionals/{id}/pricing-overrides` | Pendente | P2 |

### Comercial

| Módulo | Tela | Rota | Role | Backend | Status | Prio |
|---|---|---|---|---|---|---|
| Pacotes | Planos (CRUD) | `/pacotes` | OWNER/ADMIN | ✅ `/packages` | Pendente | P1 |
| Pacotes | Venda de pacote | `/pacotes` (ação) | OWNER/ADMIN/OPERATOR | ✅ `packages/{id}/sell` | Pendente | P1 |
| Pacotes | Compras (histórico/cotas) | `/pacotes/compras` | OWNER/ADMIN | ✅ `package-purchases`, `/{id}` | Pendente | P1 |
| Assinaturas | Planos (CRUD) | `/assinaturas/planos` | OWNER/ADMIN | ✅ `subscription-plans` | Pendente | P1 |
| Assinaturas | Instâncias (pause/resume/cancel) | `/assinaturas` | OWNER/ADMIN/OPERATOR | ✅ `subscriptions`, `/{id}/pause|resume|cancel` | Pendente | P1 |
| Promoções | Lista + CRUD + ativar/pausar/cancelar | `/promocoes` | OWNER/ADMIN (OPERATOR config) | ✅ `promotions`, `/{id}/activate|pause|cancel` | Pendente | P1 |
| Cupons | Geração em lote + lista | `/promocoes/[id]/cupons` | OWNER/ADMIN | ✅ `promotions/{id}/coupons` | Pendente | P1 |
| Promoções | Preview de desconto | (no checkout) | scope | ✅ `promotions/preview` | Pendente | P2 |

### Financeiro

| Módulo | Tela | Rota | Role | Backend | Status | Prio |
|---|---|---|---|---|---|---|
| Pagamentos | Lista | `/financeiro/pagamentos` (consolidar `/payments`) | OWNER/ADMIN/OPERATOR | ✅ `/payments` | Ajustar (consolidar duplicata) | P1 |
| Pagamentos | Novo pagamento | `.../pagamentos/novo` | OWNER/ADMIN/OPERATOR | ✅ `POST /payments` | Feito | — |
| Pagamentos | Detalhe (confirmar/refund/desconto) | `.../pagamentos/[id]` | OWNER/ADMIN | ✅ `/{id}/confirm-manual|refund|manual-discount` | Ajustar (RefundReason enum) | P1 |
| Pagamentos | Payment sources / terminais | `.../pagamentos/fontes` | OWNER/ADMIN | ✅ `payment-sources`, `payments/terminals` | Pendente | P2 |
| Pagamentos | Deposit policies (sinal) | `/settings/financial` (aba) | OWNER/ADMIN | ✅ `deposit-policies` | Pendente | P1 |
| Financial Core | Contas + saldos | `/financeiro/contas` | OWNER/ADMIN | ✅ `financial/accounts`, `/{id}/balance` | Pendente | P1 |
| Financial Core | Movimentos | `/financeiro/movimentacoes` | OWNER/ADMIN (OPERATOR config) | ✅ `financial/movements` | Feito | — |
| Financial Core | Lançamentos (entries) | `/financeiro` (visão) | OWNER/ADMIN | ✅ `financial/entries` | Pendente | P2 |
| Financial Core | Transferências | `/financeiro/contas` (ação) | OWNER/ADMIN | ✅ `financial/transfers` | Pendente | P2 |
| Financial Core | Ajuste manual | `/financeiro` (ação sensível) | OWNER/ADMIN | ✅ `financial/manual-adjustment` | Pendente | P2 |
| Gestão Financeira | DRE | `/financeiro/dre` | OWNER/ADMIN | ✅ `financial/dre` | Pendente | P1 |
| Conciliação | Abrir/fechar + reconciliar | `/financeiro/conciliacao` | OWNER/ADMIN | ✅ `financial/reconciliation`, `movements/unreconciled`, `/reconcile` | Pendente | P1 |
| Caixa | Cash count + divergência | `/financeiro/conciliacao` (aba) | OWNER/ADMIN/OPERATOR | ✅ `financial/cash-counts` | Pendente | P1 |
| Extrato | Import CSV + match + dismiss | `/financeiro/extrato` | OWNER/ADMIN (OPERATOR config) | ✅ `financial/statement/*` (import multipart) | Pendente | P1 |
| Taxas | Fee policies | `/financeiro/taxas`, `/settings/taxas` | OWNER/ADMIN | ✅ `financial/fee-policies`, `tenant/fee-routing` | Feito | — |
| Despesas | Lançamentos + pagar/cancelar | `/despesas` | OWNER/ADMIN | ✅ `expenses/*` | Pendente | P1 |

### Estoque

| Módulo | Tela | Rota | Role | Backend | Status | Prio |
|---|---|---|---|---|---|---|
| Estoque | Lista (qtd, custo médio) | `/estoque` | OWNER/ADMIN | ✅ `/stock/` | Pendente | P1 |
| Estoque | Movimentações (VENDA/USO/PERDA/AJUSTE) | `/estoque/movimentacoes` | OWNER/ADMIN | ✅ `stock/movements` | Pendente | P1 |
| Estoque | Receber pedido (entrada) | `/estoque` (ação) | OWNER/ADMIN | ✅ `stock/orders` | Pendente | P1 |
| Fornecedores | CRUD | `/fornecedores` | OWNER/ADMIN | ✅ `/suppliers/` | Pendente | P1 |
| Payables | Contas a pagar + parcelas | `/payables` | OWNER/ADMIN | ✅ `payables`, `/installments`, `/pay` | Pendente | P1 |

### Comissões

| Módulo | Tela | Rota | Role | Backend | Status | Prio |
|---|---|---|---|---|---|---|
| Comissões | Histórico (mark-due/reverse) | `/comissoes/historico` | OWNER/ADMIN | ✅ `commissions`, `/{id}/mark-due|reverse` | Feito | — |
| Comissões | Políticas (2 eixos + CUSTOM) | `/comissoes/politicas` | OWNER/ADMIN | ✅ `commission-policies` | Feito | — |
| Comissões | Pagamentos (payout) | `/comissoes/pagamentos` | OWNER/ADMIN | ✅ `commission-payouts` | Feito | — |

### Relacionamento

| Módulo | Tela | Rota | Role | Backend | Status | Prio |
|---|---|---|---|---|---|---|
| NPS | Configuração | `/nps/config` | OWNER/ADMIN | ✅ `nps/config` | Pendente | P1 |
| NPS | Surveys + respostas | `/nps` | OWNER/ADMIN | ✅ `nps/surveys`, `/{id}`, `/respond` | Pendente | P1 |
| Comunicação | Templates (CRUD) | `/comunicacao` (hoje `/settings/comunicacao`) | OWNER/ADMIN | ✅ `communication/templates` | Ajustar (mover/expandir) | P1 |
| Comunicação | Settings de canais | `/settings/comunicacao` | OWNER/ADMIN | ✅ `communication/settings` (GET/PUT) | Feito | — |
| Comunicação | Logs de envio | `/comunicacao/logs` | OWNER/ADMIN | ✅ `communication/logs` (paginado) | Pendente | P2 |

### Administração / Configurações

| Módulo | Tela | Rota | Role | Backend | Status | Prio |
|---|---|---|---|---|---|---|
| Usuários | Lista + convidar + papéis | `/settings/usuarios`, `/users` | OWNER/ADMIN | ✅ `users`, `/invite`, `/{id}/role`, `transfer-ownership`, `invitations` | Ajustar (anti-escalonamento + invitations) | P1 |
| Config | TenantConfig | `/settings` | OWNER/ADMIN | ✅ `tenant/config` (GET/PUT) | Ajustar | P1 |
| Config | Empresa/perfil | `/settings/perfil`,`/profile` | OWNER/ADMIN | ✅ `companies/me`, `company/profile` | Feito | — |
| Config | Módulos (ativar/desativar) | `/settings/modulos` | OWNER/ADMIN | ✅ `tenant/modules`, `/activate|deactivate` | Pendente | P1 |
| Config | Branding | `/settings/branding` | OWNER/ADMIN | ✅ `tenant/branding` (GET/PUT) | Pendente | P2 |
| Integrações | Credenciais (masked) | `/settings/integracoes`,`/integrations` | OWNER/ADMIN | ✅ `integrations/credentials`, `/rotate|revoke|test` | Feito | — |
| Integrações | WhatsApp (conexão/QR) | `/settings/integracoes` (aba) | OWNER/ADMIN | ✅ `whatsapp/connection`, `/qr` | Pendente | P1 |
| Audit | Trilha append-only + export | `/audit` | OWNER/ADMIN | ✅ `audit/logs` (paginado), `/export`, `/impersonation-accesses` | Pendente | P2 |
| Financeiro | Settings financeiros | `/settings/financial` | OWNER/ADMIN | ✅ `financial/settings`, `tenant/config` | Feito | — |

### Portal do Cliente (app separado — `(portal)/`)

| Tela | Rota | Backend | Status | Prio |
|---|---|---|---|---|
| Login / Registro / Magic link | `/portal/login`,`/register`,`/magic-link` | ✅ `portal/auth/*` | Pendente | P1 |
| Dashboard (próx. agend. + cotas) | `/portal/dashboard` | ✅ `portal/dashboard` | Pendente | P1 |
| Histórico (paginado) | `/portal/historico` | ✅ `portal/history` | Pendente | P1 |
| Cotas | `/portal/cotas` | ✅ `portal/credits` | Pendente | P1 |
| Assinaturas (pause/cancel) | `/portal/assinaturas` | ✅ `portal/subscriptions`, `/{id}/pause|cancel` | Pendente | P1 |
| Consentimentos | `/portal/consentimentos` | ✅ `portal/consents` (grant/revoke) | Pendente | P1 |
| Métodos de pagamento (token) | `/portal/pagamentos` | ✅ `portal/payment-sources` | Pendente | P2 |
| Perfil | `/portal/perfil` | ✅ `portal/profile`, `portal/identity/me` | Pendente | P2 |

### Painel Owner (app separado — `(owner)/`, `PLATFORM_OWNER`)

| Tela | Rota | Backend | Status | Prio |
|---|---|---|---|---|
| Tenants (lista + status) | `/owner/tenants` | ✅ `platform/tenants`, `/status` | Pendente | P1 |
| Tenant detalhe + saúde | `/owner/tenants/[id]` | ✅ `platform/tenants/{id}`, `/health` | Pendente | P1 |
| Feature flags por tenant | `/owner/tenants/[id]/flags` | ✅ `platform/tenants/{id}/flags` | Pendente | P2 |
| Impersonation (grants) | `/owner/impersonation` | ✅ `platform/impersonation/grants` | Pendente | P1 |
| Audit cross-tenant | `/owner/audit` | ✅ `platform/audit` (paginado) | Pendente | P2 |
| Comunicações (redispatch) | `/owner/sistema` | ✅ `platform/communications/{id}/redispatch` | Pendente | P2 |
| Configurações globais | `/owner/settings` | ✅ `platform/settings`, `/{key}` | Pendente | P2 |

### Públicas (sem auth, sem sidebar)

| Tela | Rota | Backend | Status | Prio |
|---|---|---|---|---|
| Link público / vitrine / agendar | `/book/[slug]` | ✅ `public/*`, `booking/{slug}/*` | Feito | — |
| Gestão de agendamento por token | `/gestao/[token]` | ✅ `manage/{token}`, `/cancel`, `/reschedule` | Pendente | P1 |
| Resposta NPS pública | `/nps/[survey_id]` | ✅ `nps/respond/{survey_id}` | Pendente | P1 |

---

## 6. DASHBOARDS POR ROLE

Não há endpoint `/dashboard` agregado no Estágio 0 — a home **compõe** widgets a partir de chamadas existentes. Render condicionado ao role do JWT.

### OWNER / ADMIN
| Widget | Endpoint(s) | Tipo |
|---|---|---|
| Resumo do dia (agend., faturamento, ocupação) | `appointments/?date=hoje`, `availability/slots` | KPI strip |
| Receita × Despesa × Margem (mês) | `financial/dre` | gráfico barras/linha |
| Alertas: pagamentos a confirmar | `payments?status=PENDING` | lista de alertas |
| Alertas: estoque baixo | `stock/?low=true` | badge |
| Alertas: cotas expirando | `customer-credits?expiring` | badge |
| Alertas: promoções expirando | `promotions?status=ACTIVE` | badge |
| Pendências: payables vencendo | `payables/?due_soon` | lista |
| Pendências: conciliação aberta / caixa | `financial/reconciliation`, `cash-counts` | card |
| CRM: clientes em risco | `crm/alerts` | lista |

### OPERATOR
| Widget | Endpoint(s) |
|---|---|
| Agenda do dia | `availability/slots`, `appointments/?date=hoje` |
| Fila de espera | `waitlist/entries` |
| Atendimento humano (escaladas) | `conversations?state=EM_ATENDIMENTO_HUMANO` |
| Cobranças pendentes | `payments?status=PENDING` |
| Caixa (CashCount) | `financial/cash-counts` |

Sem widgets de financeiro sensível (DRE, comissões, contas) salvo config.

### PROFESSIONAL
| Widget | Endpoint(s) |
|---|---|
| Próximos atendimentos (próprios) | `appointments/?professional=me` |
| Ações rápidas (iniciar/concluir/remarcar/cancelar) | `appointments/{id}/...` |
| Extrato de comissões próprias | `commissions?professional=me` (se visibilidade ativada) |

### CLIENT (Portal)
| Widget | Endpoint |
|---|---|
| Próximos agendamentos + cotas ativas | `portal/dashboard` |

---

## 7. FLUXOS CRÍTICOS (sequências de telas)

1. **Agendamento no painel (POST_DELIVERY):**
   `Clientes/identificar → Novo agendamento (serviço → profissional → slot) → confirmar → Operações(CONFIRMED) → Concluir(COMPLETED) → cobrança → Pagamento`.

2. **Sinal/Depósito (DEPOSIT — serviço avulso):**
   `deposit_policy configurada (Settings) → Novo agend. soft reservation → Pagamento do sinal → payment.confirmed → Agenda SOFT→FIRME + Operation CONFIRMED → COMPLETED cobra saldo`. UI deve refletir sinal pago vs saldo pendente no detalhe da operação.

3. **Venda de pacote → uso de cota:**
   `Pacotes/vender (SELLER) → package.purchased gera CustomerCredit → cliente aparece com cota na ficha → Operação consome cota (SERVICE_PROVIDER) na conclusão → comissões distintas para vendedor e executor`.

4. **Estoque ponta a ponta:**
   `Fornecedores cadastrar → Estoque/receber pedido (gera Payable) → Payables/pagar (Movement OUTFLOW) → venda/consumo gera Entry CUSTO`.

5. **Conciliação financeira:**
   `Extrato/importar CSV → ver sugestões de match → confirmar match OU dismiss → Conciliação abrir → marcar movements reconciliados → fechar`.

6. **Promoção no checkout:**
   `Promoções criar/ativar → no Novo pagamento: preview de desconto (promotions/preview) → aplicar cupom → payment.confirmed efetiva DiscountApplication`.

7. **Atendimento humano (Inbox):**
   `Bot escala conversa → Inbox lista (state EM_ATENDIMENTO_HUMANO) → operador responde (reply) → resolve → bot reassume (RESOLVIDA → MENU)`.

8. **Cliente público sem login:**
   `Link público agendar → WhatsApp com link de gestão → /gestao/[token] cancela/remarca sem login`.

9. **Owner — impersonation controlada:**
   `Owner/Tenants → detalhe → criar grant de impersonation (motivo, time-boxed, read-only) → acessar contexto do tenant → tenant vê no audit`.

---

## 8. TELAS PÚBLICAS (sem auth) — detalhe

34 endpoints sem `security`. Telas:

- **`/book/[slug]`** (FEITO): vitrine + FSM de agendamento. Endpoints `public/{slug}/*` e `booking/{slug}/*` (start/update/confirm/session). Abas: Serviços · Profissionais · (Produtos · Pacotes · Assinaturas · Avaliações — Estágio 1+ na UI conforme cobertura).
- **`/gestao/[token]`** (PENDENTE): `GET /manage/{token}` mostra detalhe; `POST .../cancel` e `.../reschedule`. Rate-limited. Sem sidebar/login.
- **`/nps/[survey_id]`** (PENDENTE): `POST /nps/respond/{survey_id}`. Tela de uma pergunta (nota + comentário).
- Webhooks (`payments/webhook/asaas/*`, `whatsapp/webhook`) e `health` não têm UI.
- `GET /tenant/branding` é público (para o link servir cores/logo do tenant).

---

## 9. SEQUÊNCIA DE IMPLEMENTAÇÃO RECOMENDADA

Ordenada por desbloqueio de negócio e dependências. Cada fase é alimentável módulo a módulo no Lovable e implementável como spec pelo Claude Code.

**Fase 0 — Fundação de navegação (pré-requisito de tudo)**
1. Sidebar role-aware + grupos/submenus (RBAC visível, Fase 3 da visão).
2. Dashboard role-aware com widgets/alertas (§6).
3. Consolidar rotas duplicadas (`/payments` ↔ `/financeiro/pagamentos`; PT-BR).

**Fase 1 — Operação diária completa (P0/P1)**
4. Detalhe de operação + transições + DEPOSIT/saldo.
5. CRM (alertas, classificações) + CustomerCredit na ficha do cliente.
6. Inbox de atendimento humano · Fila de espera.
7. Pagamentos: consolidar, detalhe (refund/desconto), deposit policies.

**Fase 2 — Comercial (P1)**
8. Pacotes (planos + venda + compras/cotas).
9. Assinaturas (planos + instâncias).
10. Promoções + Cupons.
11. Catálogo: Categorias, variantes, overrides de preço, upload de imagens de produto.

**Fase 3 — Financeiro profundo (P1)**
12. Despesas.
13. Estoque + Fornecedores + Payables (cadeia).
14. Contas/saldos/transfers · DRE · Conciliação + Cash count · Extrato (import/match).

**Fase 4 — Relacionamento e administração (P1/P2)**
15. NPS (config + surveys + tela pública de resposta).
16. Comunicação (templates + logs) · WhatsApp (conexão/QR).
17. Usuários (anti-escalonamento + invitations) · Módulos · Branding · Audit.

**Fase 5 — Superfícies separadas (P1/P2)**
18. Telas públicas: `/gestao/[token]`.
19. **Portal do Cliente** (shell `(portal)/` + 8 telas).
20. **Painel Owner** (shell `(owner)/` + tenants/saúde/impersonation/flags/audit).

> **Regra de generalização:** o protótipo `barberflow-system` (TanStack/Vite, mock) é **referência visual apenas** — domínios, RBAC e eventos desta visão são a fonte de verdade. Usa "barbeiros"; o domínio é "Profissionais" (label configurável). Onde o protótipo divergir do modelo, vence este documento.

---

## ANEXO — Mapa completo Tag → Endpoints

Resumo de cobertura (224 endpoints, 43 tags). Detalhe operacional já incorporado na §5; lista canônica abaixo para conferência rápida.

| Tag | Nº | Observação de UI |
|---|---|---|
| auth (7) · identity (4) | 11 | Auth feito; consents pendentes |
| companies (2) · company-profile (2) · tenant (9) | 13 | Config/branding/módulos/fee-routing |
| agenda (6) · availability (1) · schedule (9) · appointments (6) | 22 | Agenda feita; jornada/detalhe a completar |
| customers (7) · crm (4) · customer-credits (4) | 15 | Lista/ficha feitas; CRM/cotas pendentes |
| services (8) · products (4) · categories (4) · pricing-overrides (4) · professionals (7) · uploads (1) | 28 | Catálogo parcial |
| payments (15) · financial (18) · financial-statement (6) | 39 | Pagamentos/movimentos/taxas feitos; resto pendente |
| commissions (10) | 10 | Feito |
| stock (4) · suppliers (4) · payables (5) · expenses (5) | 18 | Pendentes |
| promotions (9) · packages (7) · subscriptions (9) | 25 | Pendentes |
| nps (6) · waitlist (5) · conversations (5) · communication (7) | 23 | Pendentes (comunicação parcial) |
| users (7) · integrations (5) · audit (3) · whatsapp (5) | 20 | Usuários/integrações feitos; audit/whatsapp pendentes |
| platform (13) | 13 | Painel Owner — pendente |
| portal (18) | 18 | Portal do Cliente — pendente |
| public (5) · booking-public (12) · manage (3) | 20 | Link público feito; gestão pendente |

*Fonte de verdade de comportamento: `visao-estagio-0.md`. Conflitos resolvem-se a favor da visão. Documento de planejamento — nenhuma regra de negócio vive no frontend (Princípios 7 e Panel-1).*
