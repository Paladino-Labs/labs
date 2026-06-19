# PALADINO — BRIEF DA FASE 5C (LOVABLE)

**Objetivo:** especificar o **Painel Owner** — a área exclusiva do
`PLATFORM_OWNER` para operar a plataforma Paladino: tenants, saúde, feature
flags, impersonation, audit cross-tenant, configurações globais e reenvio de
comunicação. É o **quarto shell** do produto, **completamente separado** do
painel do tenant, das superfícies públicas e do portal do cliente. Derivado de
`painel/docs/inventario-funcional.md` (§5 "Painel Owner" · §3 estrutura
`(owner)/`) e de `agendamento_engine/openapi.json` (tag `platform`, 12 rotas;
head `e0s25f_product_extras`). **Contratos conferidos diretamente no backend**
(`modules/platform/router.py` + `service.py`) — as respostas estão **`schema: {}`
(não tipadas)** no OpenAPI, então os shapes abaixo vêm do código, não de inferência.

> **Continuação das Fases 0–5B.** O painel do tenant (`(dashboard)/`), as públicas
> (`(public)/`) e o portal (`(portal)/portal/`) já existem. Esta fase **não toca**
> em nenhum deles. **Dados mockados** no protótipo Lovable; a integração real é
> feita depois pelo Claude Code.

> **⚠️ Já existe — não recriar do zero:**
> - **`app/(owner)/layout.tsx`** já existe (entregue na Fase 0): guard que exige
>   `PLATFORM_OWNER` (`role === "PLATFORM_OWNER" || (token && companyId == null)`),
>   tela de "Carregando…" e `min-h-screen bg-background`. A Fase 5C **estende** esse
>   grupo — ver §2 (a chrome do owner, sidebar própria, entra num layout aninhado
>   `(owner)/owner/layout.tsx`, **não** no guard externo).
> - **Não há rota de login própria do owner.** O `PLATFORM_OWNER` autentica pelo
>   **mesmo `/` (login do painel)** — é um `User` normal com `role=PLATFORM_OWNER` e
>   `company_id=NULL`. Logo, **reusa o JWT e o `apiFetch` do tenant** (ver §2.2).

> **Escopo rígido:** apenas as **7 telas** do Painel Owner abaixo. **NÃO** entra
> nenhuma tela do painel do tenant, do portal ou das públicas.

---

## 1. Objetivo e contexto

O **Painel Owner** é **Paladino-wide**: o `PLATFORM_OWNER` enxerga **todos os
tenants** da plataforma e opera acima deles. É o único role que acessa estas
telas — nenhum `OWNER`/`ADMIN`/`OPERATOR`/`PROFESSIONAL` de tenant entra aqui, e o
owner **nunca** vê o chrome do operador (sidebar do tenant, header, branding por
tenant).

`PLATFORM_OWNER` é um `User` com `company_id = NULL`. O backend usa exatamente esse
sinal para distinguir o owner do operador de tenant (o JWT de tenant **sempre**
carrega `company_id`). Todas as rotas de plataforma vivem sob `/platform/*` e
exigem `require_role("PLATFORM_OWNER")` — qualquer outro role recebe `403`.

Três princípios não-negociáveis derivados da visão (PARTE RBAC):

- **RBAC-3 — credenciais nunca expostas na íntegra.** O painel mostra **status de
  conexão** das integrações, não segredos. O backend de Estágio 0 **não devolve
  nem os últimos 4 caracteres** de nenhuma credencial pelas rotas de plataforma
  (`/health` só traz `asaas_connected`/`whatsapp_connected` booleanos) — ver §3 O2.
- **RBAC-2 — replay financeiro bloqueado.** Replay/reprocessamento de eventos de
  `PaymentsEngine`, `CommissionEngine` e `FinancialCore` é proibido. ⚠️ **Não existe
  endpoint de replay/dead-letter no backend** (ver §3 Q1) — o princípio é
  documentado como spec futura; o botão de replay nasce desabilitado para esses
  módulos.
- **Audit append-only.** A trilha cross-tenant é **somente leitura** — sem editar,
  excluir ou criar registros pela UI.

O Painel Owner é **desktop-first** (ferramenta operacional interna), ao contrário
do portal (mobile-first). Como qualquer área autenticada, redireciona ao login em
`401`.

---

## 2. Shell do Painel Owner — separação dos quatro contextos

O projeto passa a ter **quatro shells de produto independentes**:

| Shell | Grupo de rota | Role / Auth | Helper de API | Chrome |
|---|---|---|---|---|
| **Painel do Tenant** | `(dashboard)/` | OWNER/ADMIN/OPERATOR/PROF · JWT tenant (`localStorage["token"]`) | `apiFetch` / `api.*` | Sidebar petrol + Header do operador + branding por tenant |
| **Públicas** | `(public)/` + `book/[slug]/` | **nenhuma** | `publicFetch` | Wordmark PALADINO, sem nav |
| **Portal do Cliente** | `(portal)/portal/` | cliente · **JWT portal** (`localStorage["portal_token"]`) | `portalFetch` | Nav própria do cliente (lateral/bottom) |
| **Painel Owner** | `(owner)/owner/` | **`PLATFORM_OWNER`** · JWT tenant (`localStorage["token"]`, `company_id=null`) | **`apiFetch` / `api.*`** (reaproveitado) | **Sidebar própria do owner** (Plataforma), sem header/branding de tenant |

> **Princípio inviolável:** o Owner **não importa** o `Sidebar`, o `Header` nem o
> `BrandingProvider` do painel do tenant. Nada de tenant (agenda, financeiro do
> tenant, "Barbeiros") aparece. O owner vê **a plataforma**, não a administração de
> nenhum tenant — exceto durante uma sessão de **impersonation explícita** (P2),
> sempre sinalizada por um **banner persistente**.

### 2.1 `ownerFetch` — **NÃO criar; reusar `apiFetch` / `api.*`**

**Decisão (conferida em `context/AuthContext.tsx` + `lib/api.ts`):** o
`PLATFORM_OWNER` autentica pelo **mesmo `POST /auth/login`** e recebe um **JWT de
tenant comum** — com `role` e **sem** a claim `type` (que define o JWT do portal),
e com `company_id = null`. O `get_current_user` do backend aceita esse token
normalmente. Como `apiFetch` já anexa `Authorization: Bearer <localStorage["token"]>`,
**o Painel Owner usa `apiFetch` / `api.*` sem nenhum helper novo**.

- **Diferente do Portal** (Fase 5B), que exigiu `portalFetch` por causa do
  `type="portal"` + chave de storage própria. O Owner **não** tem isso.
- **Guard:** `companyId == null` (ou `role === "PLATFORM_OWNER"`). Já implementado no
  `(owner)/layout.tsx` existente. `ROLE_LABELS["PLATFORM_OWNER"] = "Paladino"`.
- **Wiring de login (nota p/ Claude Code, não para o protótipo):** após o login, se
  `companyId == null`, redirecionar para `/owner/tenants` em vez de `/dashboard`.
- **Única exceção — header de impersonation.** Entrar em impersonation significa
  enviar `X-Impersonate-Grant: {grant_id}` nas chamadas subsequentes (o
  `ImpersonationMiddleware` valida e audita cada request; `READ_ONLY` bloqueia
  métodos != GET). `apiFetch` não injeta esse header hoje. ⚠️ **Isso é wiring
  futuro** (um wrapper fino que lê o grant ativo de um contexto e o injeta); no
  **protótipo Lovable o banner é puramente visual / mockado**.

### 2.2 Estrutura de rotas — segmento **literal** `/owner/`

⚠️ **Mesmo problema do Portal:** route groups `(...)` **somem da URL** no Next.js.
Para as telas ficarem em `/owner/*`, as páginas vivem sob um **segmento literal
`owner`** dentro do grupo `(owner)`:

```
app/(owner)/
  layout.tsx                       ← guard PLATFORM_OWNER (JÁ EXISTE — não recriar)
  owner/
    layout.tsx                     ← NOVO: chrome do owner (sidebar Plataforma) + ImpersonationBanner
    tenants/page.tsx               ← /owner/tenants            (O1)
    tenants/[id]/page.tsx          ← /owner/tenants/[id]       (O2)
    tenants/[id]/flags/page.tsx    ← /owner/tenants/[id]/flags (P1)
    impersonation/page.tsx         ← /owner/impersonation      (P2)
    sistema/page.tsx               ← /owner/sistema            (Q1)
    settings/page.tsx              ← /owner/settings           (Q2)
    audit/page.tsx                 ← /owner/audit              (R1)
```

> O protótipo Lovable é agnóstico de path (TanStack/Vite) — esta árvore é a
> tradução-alvo para o Claude Code. **`barberflow-system`** tem `owner.tsx` +
> `owner.index.tsx`, mas é apenas um **stub "Em construção"** (guard + placeholder),
> sem nenhuma tela real — confirma que o Painel Owner é desenhado **do zero**,
> herdando o vocabulário visual do painel (tokens, `font-display`, cards). Sem
> screenshots aprovadas.

---

## 3. Endpoints por tela

Todas as rotas sob a tag `platform`, prefixo **`/platform`**, **todas** exigem
`PLATFORM_OWNER`. Helper real: **`apiFetch` / `api.*`** (§2.1). As respostas estão
`schema: {}` no OpenAPI — **os shapes abaixo vêm do `router.py`/`service.py`
(conferidos), não do contrato**; ainda assim marcados ✅ porque foram lidos no
código (≠ portal, onde eram inferência).

### Tenants (Bloco O)

| Ação | Método + Path | Query / Body | Resposta (do código) |
|---|---|---|---|
| Listar | `GET /platform/tenants` | `status?`, `created_after?`(date-time), `search_name?` | `{ items: [{ id, name, slug, status, active, created_at }], total }` — **sem paginação** (retorna todos); `search_name` = substring case-insensitive em `name` |
| Detalhe | `GET /platform/tenants/{company_id}` | — | `{ id, name, slug, status, active, created_at }` |
| Saúde | `GET /platform/tenants/{company_id}/health` | — | `{ company_id, status, total_users, total_customers, appointments_30d, last_activity_at(iso\|null), communication_failures_7d, asaas_connected(bool), whatsapp_connected(bool) }` |
| Mudar status | `PATCH /platform/tenants/{company_id}/status` | `{ status*, reason? }` | company row. `status` ∈ **TRIAL/ACTIVE/SUSPENDED/CHURNED** (422 fora disso); `reason` **obrigatório** se `SUSPENDED` (422) |

> ⚠️ **`status` enum confirmado:** `TRIAL · ACTIVE · SUSPENDED · CHURNED`
> (`service.TENANT_STATUSES`). Suspender **bloqueia o login do tenant** e dispara
> email ao OWNER do tenant (best-effort).
> ⚠️ **"Criar tenant" NÃO tem endpoint** — não existe `POST /platform/tenants` (nem
> companies/onboarding/signup). Criação de tenant no Estágio 0 é via hook interno
> `create_company`, não exposto à UI. → **Omitir o CTA "Criar"** (ou marcar "Em
> breve"/backend). Ações reais de O1 = **suspender / reativar** (via PATCH status).
> ⚠️ **Lista não traz "último acesso" nem "volume"** — só `status`/`created_at`/
> `active`. `last_activity_at` e métricas de volume só existem em `/health`
> (por-tenant). → Mostrar volume/último acesso **em O2 (detalhe)**, não na lista.
> ⚠️ **"Razão social" não existe** — o tenant expõe só `name` e `slug`.

### Impersonation (Bloco P)

| Ação | Método + Path | Body | Resposta (do código) |
|---|---|---|---|
| Listar grants ativos | `GET /platform/impersonation/grants` | — | `{ items: [{ grant_id, company_id, mode, reason, expires_at, revoked_at, created_at }], total }` — só grants **ativos** (não expirados, não revogados) **do owner logado** |
| Criar grant | `POST /platform/impersonation/grants` | `{ company_id*, mode="READ_ONLY", reason*, duration_minutes=30 }` | `201 { grant_id, expires_at, mode }` |
| Revogar grant | `DELETE /platform/impersonation/grants/{grant_id}` | — | grant row (com `revoked_at`); `403` se for de outro owner; `422` se já revogado |

> ⚠️ **NÃO existem `/platform/impersonation/start` nem `/end`** (o escopo os citou).
> O fluxo real é: **(1)** criar o grant (POST) → **(2)** enviar
> `X-Impersonate-Grant: {grant_id}` nas chamadas seguintes (middleware valida +
> audita cada request; `READ_ONLY` bloqueia não-GET) → **(3)** "Encerrar" = parar de
> enviar o header e/ou `DELETE` o grant. `mode` ∈ **READ_ONLY | ELEVATED**; `ELEVATED`
> exige `reason` ≥ **20 chars** (422); `duration_minutes` ∈ 1–480 (default 30).

### Feature flags (Bloco P)

| Ação | Método + Path | Body | Resposta (do código) |
|---|---|---|---|
| Ler flags do tenant | `GET /platform/tenants/{company_id}/flags` | — | `{ flags: { …dict livre… } }` (= `TenantConfig.permission_overrides`); `404` se sem config |
| Setar uma flag | `PUT /platform/tenants/{company_id}/flags/{key}` | `{ value }` (qualquer JSON) | `{ flags: { …dict completo após update… } }` |

> ⚠️ **Flags NÃO são um catálogo enumerado** — é um **dict livre** chave→valor
> (`permission_overrides`), ex.: `allows_subscription_pause: false`,
> `use_communication_service: true`, `OPERATOR: {…}`. **Não há endpoint de flags
> globais.** A UI renderiza o dict genericamente (chave + editor de valor; toggle
> quando o valor é booleano).

### Configurações globais (Bloco Q)

| Ação | Método + Path | Body | Resposta (do código) |
|---|---|---|---|
| Ler settings | `GET /platform/settings` | — | `{ settings: { key: value, … } }` (dict global) |
| Setar uma setting | `PUT /platform/settings/{key}` | `{ value }` (qualquer JSON) | `{ key, value }` |

> ⚠️ **Settings é um dict** chave→valor JSONB global — mesmo padrão genérico das
> flags (sem catálogo fixo). `GET` devolve `{ settings: {...} }`; `PUT` devolve só a
> chave alterada.

### Sistema / Reenvio de comunicação (Bloco Q)

| Ação | Método + Path | Body | Resposta (do código) |
|---|---|---|---|
| Reenviar comunicação | `POST /platform/communications/{log_id}/redispatch` | `{ reason* }` | `{ new_log_id, status, original_log_id }` — só logs **FAILED** com `rendered_body`; cria **novo** log |

> ⚠️ **Q1 (workers/dead-letter/replay) NÃO tem backend.** Não existe
> `/platform/system`, `/platform/workers`, `/platform/dead-letter` nem qualquer
> endpoint de **replay**. A **única** operação de sistema real é o `redispatch` de
> **um** CommunicationLog FAILED — e **nem isso tem endpoint de listagem**
> (`GET /platform/communications` não existe), então exige um `log_id` conhecido.
> → A tela `/owner/sistema` entrega o **reenvio por `log_id` + motivo** (real) e
> trata o monitor de dead-letter/workers como **"Em breve" (sem endpoint, Estágio
> 1+)** — mesma classe de bloqueio da aba Produtos (5A) e de `/portal/pagamentos`
> (5B, Asaas).

### Audit cross-tenant (Bloco R)

| Ação | Método + Path | Query | Resposta (do código) |
|---|---|---|---|
| Trilha cross-tenant | `GET /platform/audit` | `company_id?`, `actor_id?`, `action?`, `date_from?`, `date_to?`, `page`(≥1, def 1), `limit`(1–500, def 50) | **envelope** `{ total, page, limit, items: [{ audit_id, company_id(\|null), actor_id, actor_role, action, resource_type, resource_id(\|null), reason, before_snapshot, after_snapshot, occurred_at }] }` |

> ⚠️ **Paginação = envelope `{ total, page, limit, items }`** (confirmado). `page`/
> `limit` por query.
> ⚠️ **Sem campo `ip`** nas linhas (o escopo citou IP — o backend não devolve).
> ⚠️ **Sem endpoint de export CSV** no nível de plataforma (`/audit/logs/export` é
> **tenant-scoped**, não serve ao owner). → **Não** prometer botão de export.
> ⚠️ **Acessos de impersonation** = **mesmo** endpoint com filtro
> `action=impersonated_request` (linhas escritas pelo middleware). A rota
> `/audit/impersonation-accesses` é **tenant-scoped** (PLATFORM_OWNER → `403`,
> deve usar `/platform/audit`). → A "aba de impersonation" de R1 é um **preset de
> filtro** sobre `/platform/audit`, não um endpoint separado.

---

## 4. Especificação das 7 telas

Estados mínimos por tela: **loading (`Skeleton`) · vazio (`EmptyState`) · erro
(`ErrorState`) · dados**. Desktop-first. **Enums inglês → label PT** via
`lib/constants.ts` (adicionar glossários aditivos — §5). Componentes do projeto:
`Card`, `Table`, `Badge`, `Dialog`, `Select`, `Switch`, `Tabs`, `Tooltip`, `Input`,
`Label`, `Button`, `Skeleton`, `EmptyState` (`components/empty-state.tsx`),
`ErrorState`, `PageHeader`. **Não há** `AlertDialog`, `RadioGroup`, `Progress`.

### Bloco O — Tenants

#### O1 — `/owner/tenants`
- **Layout:** `PageHeader` "Tenants" + filtro de **status** (`Select`: Todos/TRIAL/
  ACTIVE/SUSPENDED/CHURNED) e busca por nome (`Input`, alimenta `search_name`).
  **`Table`** com colunas: **Nome** · **Slug** · **Status** (`Badge` colorido) ·
  **Criado em** (`formatDateShort`) · **Ativo** (sim/não). Linha clicável → O2.
- **Ações:** **Suspender** (status `ACTIVE/TRIAL` → abre `Dialog` com `Textarea`
  **motivo obrigatório** → `PATCH .../status {status:"SUSPENDED", reason}`);
  **Reativar** (status `SUSPENDED` → `Dialog` de confirmação →
  `PATCH .../status {status:"ACTIVE"}`). Resultado **inline** (a linha reflete o
  novo status). **Sem "Criar tenant"** (sem endpoint — §3).
- **Estados:** `Skeleton` de linhas; vazio (com/sem filtro) → `EmptyState`; erro →
  `ErrorState` com retry.
- **shadcn:** `Table`, `Select`, `Input`, `Badge`, `Dialog`, `Button`, `Skeleton`.
- ⚠️ **Sem coluna "último acesso"/"volume"** na lista (não vêm do endpoint).

#### O2 — `/owner/tenants/[id]`
- **Layout:** `PageHeader` com nome do tenant + `Badge` de status + ações
  Suspender/Reativar (mesmo `Dialog` do O1). Duas seções:
  - **Dados** (`GET /platform/tenants/{id}`): nome, slug, status, ativo, criado em.
  - **Saúde** (`GET /platform/tenants/{id}/health`): cards/KPIs — usuários, clientes,
    **agendamentos (30d)**, **último acesso** (`last_activity_at`), **falhas de
    comunicação (7d)**, e **Integrações**: **Asaas** e **WhatsApp** como
    **status de conexão** (`Conectado`/`Não conectado`, `Badge`), derivados de
    `asaas_connected`/`whatsapp_connected`. Sinais de churn = combinação de
    `appointments_30d` baixo + `last_activity_at` antigo + `communication_failures_7d`
    alto (heurística visual, sem score do backend).
  - Link "Feature flags →" → P1.
- **⚠️ Credenciais (RBAC-3):** o `/health` **não devolve nenhum caractere de
  credencial** — apenas os booleanos de conexão. → **Exibir só status**; **não**
  inventar "•••• 4242" no wiring real. (No protótipo, pode-se *ilustrar* o padrão
  de mascaramento `last4 + status`, mas marcado como **mock** + nota de que o
  backend só expõe booleano.)
- **Estados:** `Skeleton` por seção; erro de `/health` → `ErrorState` na seção
  (dados básicos podem carregar mesmo se `/health` falhar).
- **shadcn:** `Card`, `Badge`, `Dialog`, `Button`, `Skeleton`, `Separator`.

### Bloco P — Flags e Impersonation

#### P1 — `/owner/tenants/[id]/flags`
- **Layout:** `PageHeader` "Feature flags — [tenant]". **Renderização genérica do
  dict** `permission_overrides`: uma linha por chave. **Toggle (`Switch`)** quando o
  valor é booleano; para valores não-booleanos (objeto/string/número), mostrar o
  valor em `<code>`/`Badge` + botão "Editar" → `Dialog` com `Textarea` JSON →
  `PUT .../flags/{key} {value}`. Setar a flag re-busca e reflete o dict completo
  devolvido.
- **⚠️ Não há catálogo fixo de flags** — não hardcodar uma lista; iterar sobre as
  chaves que vierem. (Se vazio, `EmptyState` "Nenhuma flag configurada".)
- **Estados:** `Skeleton`; `404` (sem TenantConfig) → `ErrorState` "Config não
  encontrada"; erro de toggle → reverte + mensagem inline.
- **shadcn:** `Switch`, `Label`, `Card`, `Dialog`, `Textarea`, `Button`, `Skeleton`.

#### P2 — `/owner/impersonation`
- **Layout:** duas partes:
  - **Criar grant:** `Card` com `Select` de tenant (lista de `GET /platform/tenants`),
    **`Textarea` motivo (obrigatório)**, `Select` de **modo** (READ_ONLY default ·
    ELEVATED), `Input` numérico **duração (min, default 30, 1–480)**. Validação na
    UI: ELEVATED exige motivo ≥ 20 chars (espelha o 422 do backend). Botão "Criar
    acesso" → `POST .../grants` → ao sucesso, **inicia a sessão de impersonation**
    (no protótipo: grava um estado mock de grant ativo → dispara o banner — §5).
  - **Grants ativos:** `Table` (`GET .../grants`): tenant · modo · motivo · expira em
    · criado em · ação **Encerrar** (`Dialog` de confirmação → `DELETE .../grants/{id}`).
- **Banner de impersonation (persistente):** ver §5. Ao entrar em impersonation, o
  **banner aparece no topo de qualquer tela do owner** e **não pode ser
  escondido** — só "Encerrar" (revoga + limpa) ou expiração automática.
- **Estados:** `Skeleton` na tabela; vazio → `EmptyState` "Nenhum acesso ativo";
  erro → `ErrorState`. Erro de criação (422 ELEVATED/duração) → inline no form.
- **shadcn:** `Card`, `Select`, `Textarea`, `Input`, `Table`, `Badge`, `Dialog`,
  `Button`, `Skeleton`.

### Bloco Q — Sistema e Settings

#### Q1 — `/owner/sistema`  ⚠️ dead-letter/workers SEM backend
- **Layout real (a única capacidade existente):** `Card` "Reenviar comunicação" —
  `Input` **`log_id`** (UUID) + `Textarea` **motivo (obrigatório)** + botão
  "Reenviar" → `POST /platform/communications/{log_id}/redispatch {reason}`.
  Resultado **inline** (`new_log_id` + `status`). ⚠️ **Sem listagem** de logs
  (não há `GET`) — o owner cola o `log_id`.
- **Monitor de workers / dead-letter / replay:** **`EmptyState` "Em breve"** com
  **TODO explícito** (sem endpoint no backend — Estágio 1+). No **protótipo Lovable**
  pode-se *mockar* uma tabela de dead-letter para validar o layout, **desde que**:
  - cada linha tenha módulo + evento + erro + botão **Replay** + motivo;
  - **Replay nasce DESABILITADO** (com `Tooltip`) para
    **`PaymentsEngine` · `CommissionEngine` · `FinancialCore`** (RBAC-2) — não só
    reagindo a `403`, mas bloqueado na UI;
  - **Replay exige motivo** (`Dialog` com `Textarea`) nos demais módulos;
  - tudo marcado **mock** + nota de gap de backend.
- **Estados:** form de reenvio (real) · EmptyState "Em breve" (monitor) ou mock
  (protótipo).
- **shadcn:** `Card`, `Input`, `Textarea`, `Button`, `Table` (mock), `Tooltip`,
  `Dialog`, `EmptyState`.

#### Q2 — `/owner/settings`
- **Layout:** `PageHeader` "Configurações da plataforma". **Renderização genérica
  do dict** `settings`: `Table`/lista chave→valor. Editar → `Dialog` com `Textarea`
  JSON → `PUT /platform/settings/{key} {value}`. Resultado **inline**. (Sem catálogo
  fixo — iterar sobre as chaves.) **Sem criação de chave nova no MVP** salvo se o
  protótipo expuser um campo "nova chave" (opcional; o `PUT` faz upsert, então é
  possível — marcar opcional).
- **Estados:** `Skeleton`; vazio → `EmptyState` "Nenhuma configuração"; erro →
  `ErrorState`.
- **shadcn:** `Table`/`Card`, `Dialog`, `Textarea`, `Button`, `Skeleton`.

### Bloco R — Audit cross-tenant

#### R1 — `/owner/audit`
- **Layout:** `PageHeader` "Auditoria". **`Tabs`**: **"Tudo"** e **"Impersonation"**
  (a 2ª = preset de filtro `action=impersonated_request` sobre o **mesmo** endpoint).
  **Filtros:** tenant (`Select`/`Input` `company_id`), ator (`Input` `actor_id`),
  ação (`Input` `action`), período (`date_from`/`date_to`). **`Table`** com:
  **company_id** (sempre visível — cross-tenant), ator (`actor_id` + `actor_role`),
  **action**, resource_type, resource_id, motivo (`reason`), **ocorrido em**
  (`formatDateTime`). `before_snapshot`/`after_snapshot` em detalhe expansível
  (linha → `Dialog`/disclosure com JSON). **Paginação** por `page`/`limit`
  (envelope `{ total, page, limit, items }`).
- **⚠️ Append-only:** **nenhuma** ação de editar/excluir/criar — só leitura,
  filtro, paginação e expandir detalhe. **Sem botão de export** (sem endpoint).
  **Sem coluna IP** (não vem do backend).
- **Estados:** `Skeleton` de linhas; vazio (com/sem filtro) → `EmptyState`; erro →
  `ErrorState`.
- **shadcn:** `Tabs`, `Table`, `Select`, `Input`, `Badge`, `Button` (paginação),
  `Dialog`/disclosure (snapshots), `Skeleton`.

---

## 5. Padrões de UX da Fase 5C

- **Shell completamente separado.** O Owner **não importa** `Sidebar`/`Header`/
  `BrandingProvider` do tenant. Sidebar própria (`components/owner/`), rótulo
  "Plataforma"/"Paladino", itens: Tenants · Impersonation · Sistema · Configurações ·
  Auditoria. Sem nav de operador.
- **Banner de impersonation — persistente, nunca dismissável.** Enquanto houver
  grant ativo: faixa fixa no topo de **qualquer** tela do owner —
  *"Acessando como PLATFORM_OWNER em **[tenant]** · Modo **leitura/elevado** ·
  Expira em **HH:MM** · [Encerrar]"*. **Sem botão "X"/fechar** — só **Encerrar**
  (revoga o grant + limpa o estado) ou **expiração automática** (countdown chega a
  zero → some + aviso). Cor de destaque (`bg-primary`/âmbar via tokens), alto
  contraste. No protótipo: dirigido por um `ImpersonationContext`/flag mock setado
  em P2; renderizado no `(owner)/owner/layout.tsx`.
- **Credenciais mascaradas (RBAC-3).** Integrações exibidas **apenas como status de
  conexão** (`Conectado`/`Não conectado`). O backend de Estágio 0 **não expõe
  last4** pelas rotas de plataforma. Regra de exibição documentada: *se um dia
  houver endpoint de detalhe de credencial, mostrar **só últimos 4 + status**,
  nunca o segredo* — mas em 5C **só status**.
- **Replay bloqueado por módulo financeiro (RBAC-2).** Onde houver botão de replay
  (monitor de dead-letter, mockado), **desabilitar na UI** para `PaymentsEngine`,
  `CommissionEngine`, `FinancialCore` (com `Tooltip` explicando), e **exigir motivo**
  nos demais. ⚠️ Sem endpoint real de replay → princípio documentado, não wired.
- **Motivo obrigatório** em toda ação sensível: suspender tenant (reason),
  redispatch (reason), criar grant (reason; ELEVATED ≥ 20 chars), replay (mock).
- **Tenant status badges** com cores semânticas (tokens, nunca hardcoded):
  `TRIAL` (âmbar/secondary) · `ACTIVE` (verde/primary) · `SUSPENDED` (vermelho/
  destructive) · `CHURNED` (cinza/muted).
- **Audit cross-tenant:** `company_id` **sempre visível** em cada linha (o que
  distingue do audit do tenant). Append-only — sem ações de escrita.
- **`Dialog` (não `AlertDialog`)** para ações destrutivas/confirmações: suspender
  tenant, encerrar impersonation, revogar grant, replay. O projeto **não tem
  `AlertDialog`** → `Dialog` + botões (padrão das Fases 5A/5B).
- **Sem `Progress`, sem `RadioGroup`** — não são necessários aqui; se algum medidor
  for desejado, usar `div` (padrão `QuotaProgress` do portal).
- **Resultado inline (não toast)** para consequências permanentes (status, grant,
  redispatch). Toast só para feedback efêmero leve.
- **Desktop-first**; tabelas densas; `max-w` amplo. Datas: `formatDateTime` /
  `formatDateShort` de `lib/utils.ts`.

### Glossários a adicionar em `lib/constants.ts` (aditivo)
- `TENANT_STATUS_LABELS` (`TRIAL`→"Período de teste", `ACTIVE`→"Ativo",
  `SUSPENDED`→"Suspenso", `CHURNED`→"Cancelado") + mapa de cor por status.
- `IMPERSONATION_MODE_LABELS` (`READ_ONLY`→"Somente leitura", `ELEVATED`→"Elevado").
- (Reusar `ROLE_LABELS` de `AuthContext` para `actor_role` no audit, se útil.)

### Componentes a reaproveitar / criar
Reaproveitar: `Card`, `Table`, `Badge`, `Dialog`, `Select`, `Switch`, `Tabs`,
`Tooltip`, `Input`, `Label`, `Textarea`, `Button`, `Skeleton`, `EmptyState`,
`ErrorState`, `PageHeader`, ícones **Lucide** (16px/`strokeWidth 1.5`), wordmark
`PALADINO`. **A criar:** `components/owner/OwnerSidebar.tsx` (nav própria),
`ImpersonationBanner` + `ImpersonationContext`, `TenantStatusBadge` (aditivo), e os
glossários acima. **Não criar** `ownerFetch` (§2.1).

### Referência visual
- **barberflow-system** tem `owner.tsx`/`owner.index.tsx`, mas é só um **stub "Em
  construção"** (guard + placeholder), **sem telas reais** — não há nada a espelhar.
  O Painel Owner é desenhado **do zero**, herdando o vocabulário do painel (tokens,
  `font-display`, cards densos). **Sem screenshots aprovadas.**

---

## 6. O que NÃO entra na Fase 5C

- **Telas do painel do tenant** (`(dashboard)/*`), **do portal** (`(portal)/*`) e
  **públicas** (`(public)/*`) — quatro shells distintos; 5C é só `(owner)/owner/*`.
- **Criar tenant** — sem endpoint `POST /platform/tenants` (criação é hook interno).
  Omitir o CTA.
- **`/platform/impersonation/start` e `/end`** — não existem; impersonation é
  grant + header `X-Impersonate-Grant` (§3).
- **Monitor de workers / dead-letter / replay de eventos** — **sem backend**
  (`/platform/system|workers|dead-letter`/replay não existem). Q1 entrega só o
  **redispatch** real; o monitor é "Em breve"/mock.
- **Export CSV do audit** — sem endpoint de plataforma (`/audit/logs/export` é do
  tenant). Não prometer.
- **Coluna IP no audit** — o backend não devolve `ip`.
- **last4 de credenciais** — o `/health` só expõe booleanos de conexão; só status.
- **Listagem de comunicações** — não há `GET /platform/communications`; redispatch
  exige `log_id` conhecido.
- **`ownerFetch` / chave de storage própria / login próprio do owner** — o owner
  reusa `/auth/login` + JWT + `apiFetch` do tenant (`company_id=null`).
- **Catálogo fixo de flags/settings** — ambos são dicts livres; renderizar
  genericamente, não hardcodar uma lista.
- **Inventar** campos não devolvidos pelo código (IP, last4, "razão social",
  "volume" na lista, score de churn) como se confirmados.

---

*Fonte de verdade de comportamento: `visao-estagio-0.md` + `openapi.json`
(head `e0s25f_product_extras`, tag `platform`). Shapes conferidos em
`app/modules/platform/router.py` e `service.py` (respostas `schema: {}` no
OpenAPI). `barberflow-system` só tem um stub de owner — referência visual nula
para estas telas. Onde divergir, vence este documento. Documento de planejamento —
nenhuma regra de negócio vive no frontend.*
