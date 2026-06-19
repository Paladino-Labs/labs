# painel — contexto operacional

**Sprint atual:** Fase 5C concluída. Painel Owner (`(owner)/owner/*`)
implementado — quarto shell, isolado dos demais. Próxima fase: a definir.

## Painel Owner — `app/(owner)/owner/`

Quarto shell, exclusivo do `PLATFORM_OWNER` (`company_id=null`). Reusa o JWT do
tenant via `owner.*` (`lib/owner-api.ts`, wrapper de `apiFetch`). Guard de PLATFORM_OWNER no
`(owner)/layout.tsx` (Fase 0, não recriar); chrome próprio em
`(owner)/owner/layout.tsx` (`OwnerSidebar` + `ImpersonationBanner`).

⚠️ Segmento **literal `owner`** dentro do grupo `(owner)` (route groups somem da
URL) — telas em `/owner/*`.

| Caminho | URL | Endpoint principal |
|---------|-----|--------------------|
| `owner/tenants/page.tsx` | `/owner/tenants` | `GET /platform/tenants` · `PATCH .../status` |
| `owner/tenants/[id]/page.tsx` | `/owner/tenants/[id]` | `GET .../{id}` + `.../health` |
| `owner/tenants/[id]/flags/page.tsx` | `/owner/tenants/[id]/flags` | `GET/PUT .../flags` (dict livre) |
| `owner/impersonation/page.tsx` | `/owner/impersonation` | `GET/POST/DELETE /platform/impersonation/grants` |
| `owner/sistema/page.tsx` | `/owner/sistema` | `POST /platform/communications/{id}/redispatch` |
| `owner/settings/page.tsx` | `/owner/settings` | `GET/PUT /platform/settings` (dict livre) |
| `owner/audit/page.tsx` | `/owner/audit` | `GET /platform/audit` (envelope paginado) |

- `context/ImpersonationContext.tsx` — grant ativo em **sessionStorage** (morre ao
  fechar a aba); header `X-Impersonate-Grant` injetado automaticamente por
  `owner.*` (`lib/owner-api.ts`) quando há grant ativo não-expirado.
- **`lib/owner-api.ts`** (`owner.get/post/put/patch/delete`) — wrapper de `apiFetch`
  que lê `sessionStorage["impersonation_grant"]` e injeta `X-Impersonate-Grant:
  {grant_id}` (descarta grant expirado). NOTA: a diretriz "sem `ownerFetch`" foi
  **revogada** — a injeção do header de impersonation é necessidade real que
  `api.*` não cobre sem alterar suas assinaturas.
- `components/owner/` — `OwnerSidebar`, `ImpersonationBanner` (persistente, sem
  dismiss, countdown HH:MM), `TenantStatusBadge`, `TenantStatusDialog`.
- glossários em `lib/constants.ts`: `TENANT_STATUS_LABELS`, `TENANT_STATUS_VARIANT`,
  `IMPERSONATION_MODE_LABELS`.
- login (`app/page.tsx`) redireciona `company_id==null` → `/owner/tenants`.

**Gaps de backend conhecidos (Owner — dívidas / Estágio 1+):**
1. Q1 dead-letter/workers/replay **sem backend** → tabela mock "Em breve · mock";
   Replay desabilitado p/ `PaymentsEngine`/`CommissionEngine`/`FinancialCore`
   (RBAC-2). Único real é o `redispatch` de um CommunicationLog FAILED por `log_id`.
2. Sem `GET /platform/communications` (listagem) → reenvio exige `log_id` colado.
3. Sem `POST /platform/tenants` (criar tenant) → sem CTA "Criar".
4. `/health` só expõe booleanos de conexão (RBAC-3) → integrações só como status,
   nunca last4/credenciais.
5. Audit sem coluna `ip` e sem export CSV de plataforma; impersonation = preset
   `action=impersonated_request` sobre `/platform/audit` (não endpoint separado).
6. ~~`X-Impersonate-Grant` não injetado~~ **RESOLVIDO (F1)** — `owner.*`
   (`lib/owner-api.ts`) injeta o header a partir do grant ativo em sessionStorage.
7. Busca de tenants: backend `search_name` filtra **só por nome**; o match por slug
   é client-side (válido enquanto a lista retornar todos os tenants — revisar se
   houver paginação server-side futura).

## Superfícies públicas — `app/(public)/`

| Caminho | Função |
|---------|--------|
| `layout.tsx` | shell público compartilhado (wordmark PALADINO + footer; sem auth, sem redirect) |
| `manage/[token]/` | gestão de agendamento sem login (`ManageDetailsResponse`, 6 campos) |
| `nps/respond/[survey_id]/` | resposta pública de NPS (re-hospedada da Fase 4) |

`/book/[slug]` permanece em `app/book/[slug]/` — **fora** do grupo `(public)`,
com chrome próprio.

## Portal do Cliente — `app/(portal)/portal/`

Terceiro shell, isolado do painel do tenant e das superfícies públicas. JWT
`type="portal"` (sem `company_id`), chave de storage **`portal_token`**.

⚠️ **Route groups `(...)` são removidos da URL pelo Next.js.** Para as rotas
ficarem em `/portal/*`, as páginas vivem sob um segmento **literal `portal`**:

| Caminho | URL |
|---------|-----|
| `(portal)/layout.tsx` | wrapper mínimo externo (simplificado na Fase 5B — sem header/nav) |
| `(portal)/portal/login/` | `/portal/login` (magic link + e-mail/senha) |
| `(portal)/portal/magic/[token]/` | `/portal/magic/[token]` — **token no PATH** (backend gera `{base}/portal/magic/{token}`) |
| `(portal)/portal/(app)/` | guard (`401→/portal/login`) + nav lateral/bottom; rotas autenticadas dentro |

7 telas autenticadas em `(app)/`: dashboard, historico, cotas, assinaturas,
consentimentos, pagamentos, perfil.

**Helper de API** — `lib/portal-api.ts` (`portalFetch`):
- chave `portal_token` (**nunca** `"token"` do tenant)
- `401` → `setPortalAuthErrorHandler` → `/portal/login` (não o login do tenant)
- `.status` exposto no erro (`Object.assign`, mesmo padrão de `apiFetch`)
- `portal.get/post/patch/delete` disponíveis
- ⛔ não importa `apiFetch`/`AuthContext`/`Sidebar`/`Header` do tenant

**Tipos e componentes:**
- `lib/portal-types.ts` — shapes reais dos endpoints não-tipados no OpenAPI
  (conferidos em `modules/portal/service.py`) + helper `establishmentLabel`
- `components/portal/` — `PortalAuthShell`, `PortalStatusBadge`,
  `QuotaProgress` (barra via `div` — não há `Progress`)
- glossários: `SUBSCRIPTION_STATUS_LABELS`, `CONSENT_TYPE_LABELS`,
  `CONSENT_CHANNEL_LABELS` em `lib/constants.ts`

**Gaps de backend (Portal) — dívidas 5A–5B resolvidas no wiring (B1–B5/F2):**
1. ~~Itens só traziam `company_id`~~ **RESOLVIDO (B1)** — backend serializa
   `company_name`; UI usa `establishmentLabel` (fallback "Estabelecimento").
2. ~~`credits` sem nome de serviço~~ **RESOLVIDO (B2)** — `service_name`
   (fallback `entitlement_type`) nos cards de cota/dashboard.
3. ~~Sem histórico de consumo de cota~~ **RESOLVIDO (B3)** — card expansível faz
   fetch lazy de `GET /portal/credits/{id}/consumptions` (Skeleton/lista/vazio).
4. ~~`GET /portal/history` sem filtro de status~~ **RESOLVIDO (B4)** — `status`
   por query param; filtro server-side, `page` reseta ao trocar.
5. ~~Sem `POST /portal/subscriptions/{id}/resume`~~ **RESOLVIDO (B5)** — ação
   "Retomar" ativa com Dialog de confirmação (gate `allow_subscription_pause`).
6. ~~`email_verification_sent` não reforçado na UI~~ **RESOLVIDO (F2)** —
   `perfil/page.tsx` já mostra "Enviamos um link para confirmar seu novo e-mail".
7. `/portal/pagamentos`: wiring ainda bloqueado por Asaas (tokenização de cartão)
   — estrutura visual em mock estático, sem POST real.
## Design — Sprints A–F + Ajustes concluídos ✅
- Todos os desvios resolvidos: ícones semânticos, brand icons → texto,
  tab Barbeiros sem risco de erro em produção
- G13 (BookingFlow 4 steps) aguarda sprint de backend
**Foco do frontend nesta fase:** apenas ajustes mínimos de segurança.
Mudanças de UI (RBAC visível, dashboards role-aware) são Fase 3.

---

## Stack

- Next.js 16.2.2 · React 19.2.4 · TailwindCSS v4 (`tailwindcss: ^4`)
- `shadcn: ^4.2.0` como dependência direta (componentes em `components/ui/`)
- `@base-ui/react: ^1.3.0`, `class-variance-authority`, `clsx`,
  `lucide-react`, `tailwind-merge`, `tw-animate-css`
- App Router (estrutura `app/`)
- API-first: zero lógica de negócio no frontend
- Sem SSR de dados sensíveis — chamadas à API sempre autenticadas via JWT

## Convenções de frontend

- Identidade visual por tenant via design tokens (logo, cores, fonte, favicon)
- Estrutura da UI é única; aparência muda por tokens — não criar layouts paralelos por tenant
- Sidebar: sem filtro por role na Fase 1 → RBAC visível no frontend é Fase 3 (fora do escopo desta fase)
- Imports de `lib/api.ts` sempre — nunca `fetch` raw
- `publicFetch` expõe `.status` no erro lançado (`Object.assign`, mesmo padrão de
  `apiFetch`). Consumidores que só leem `.message` não são afetados.
- Formatação monetária: `formatBRL()` de `lib/utils.ts`
- Formatação de data: `formatDateTime(iso: string, timeZone?: string)` de
  `lib/utils.ts`. 2º parâmetro opcional (backward-compatible); sem arg = locale do
  browser. Passar `"America/Sao_Paulo"` nas superfícies públicas (P2).
- Componentes usam tokens semânticos do design system (bg-card, border-border,
  text-muted-foreground, bg-primary) — nunca valores hardcoded (bg-white, text-gray-*)
- Display type: [font-family:var(--font-display)] apenas em elementos não-heading (span, div)
  h1/h2/h3 herdam Cormorant Garamond automaticamente via @layer base
- globals.css define os tokens; componentes herdam automaticamente
- .book-page segue paleta do sistema por padrão; customizável via TenantBranding

## Rotas e áreas existentes (entrada Fase 1)

8 áreas em `app/(dashboard)/`:
appointments · customers · dashboard · integrations ·
products · professionals · services · settings (apenas `settings/profile/`)

Link Público em `app/book/[slug]/`:
- `page.tsx` — landing + vitrine
- `BookingFlow.tsx` — FSM do checkout

Login em `app/page.tsx`.

## Design system

- Componentes usam tokens semânticos do design system (bg-card, border-border,
  text-muted-foreground, bg-primary) — nunca valores hardcoded (bg-white, text-gray-*)
- Display type: [font-family:var(--font-display)] apenas em elementos não-heading (span, div)
  h1/h2/h3 herdam Cormorant Garamond automaticamente via @layer base
- globals.css define os tokens; componentes herdam automaticamente
- .book-page segue paleta do sistema por padrão; customizável via TenantBranding
- Sidebar: Lucide icons (16px/strokeWidth 1.5), font-display nos labels,
  italic + ◆ para item ativo, footer com avatar + nome + role + logout
- Dashboard: overview KPI strip + Próximos da casa + Top serviços
- Títulos: font-display text-3xl tracking-wide em todas as páginas
- ThemeProvider em lib/theme.tsx (localStorage, .light class no <html>)
- paladino-wordmark.png em painel/public/
- Sidebar: toggle Sun/Moon funcional
- Pendente: grupo Unidade no sidebar (depende de company context no JWT)

## O que NÃO fazer

- Não criar lógica de negócio no frontend (validação de disponibilidade, cálculo financeiro, etc.)
- Não usar o protótipo `barberflow-system` como spec de comportamento (referência visual apenas)
- Não criar layouts distintos por tenant — tokens visuais, não layouts paralelos
- `POST /users` com senha no body está deprecado a partir do Sprint 2
  → usar `POST /users/invite` + `POST /auth/activate`
- Não criar UI nova para módulos da Fase 1 (foco é backend)
- Não referenciar `painel/painel/` — diretório removido (era resíduo de remoção de submódulo)
- Não criar rota `/gestao/[token]` — o backend gera links para `/manage/{token}`
  (`build_manage_url`). Se precisar de alias, usar `next.config` rewrite, nunca como
  rota primária.
- Não chamar `/tenant/branding` nas superfícies públicas — exige `company_id`; P2 e
  P3 não têm esse dado.
- Não usar `api.publicPost` — não existe. Helper público = `publicFetch` (`lib/api.ts`).

## Sprints de design (espelhamento barberflow-system)

Consultar `design-sprints/README.md` para o protocolo completo e status de cada sprint.

### Decisões registradas

| Decisão | Justificativa |
|---------|--------------|
| Adotar "Barbeiros" na UI em vez de "Profissionais" | Produto focado em barbearia no Estágio 0; labels serão configuráveis por vertical no Estágio 1 |
| Hub `/settings` com cards para profile e security | Extensível para futuras seções; zero impacto em rotas existentes |
| `publicFetch<T>()` em `lib/api.ts` | Centraliza chamadas sem JWT do link público — exigência do brief |
| BookingFlow G13 em sprint separado | Step `AWAITING_SHIFT` é entidade da API; eliminação requer sprint de backend antes |
| Abordagem B no BookingFlow aprovada condicionalmente | Após sprint de backend que remove `AWAITING_SHIFT` do engine e simplifica para 4 steps |

### Nomenclatura (Estágio 0)

| Entidade (API/código) | Label na UI |
|-----------------------|-------------|
| `professionals` | Barbeiros |
| `settings/profile` | Perfil da empresa |
| `settings` (raiz) | Configurações |

### Campos condicionais à API

Renderizar com fallback `"Em breve"` (`text-xs text-muted-foreground opacity-50`)
se o campo não existir na resposta atual. Não criar dados mockados.

| Campo | Endpoint | Superfície |
|-------|---------|-----------|
| `visit_count` | `GET /customers/` | Clientes — coluna "Visitas" |
| `total_spent` | `GET /customers/` | Clientes — coluna "Total gasto" |
| Profissionais por serviço | `GET /services/` | Serviços — "Realizado por" |
| `working_days` | `GET /professionals/` | Barbeiros — dias da semana |
| `commission_rate` | `GET /professionals/` | Barbeiros — comissão |
| `specialties` | `GET /professionals/` | Barbeiros — especialidades |
| `rating`, `review_count` | `GET /booking/{slug}/profile` | Vitrine — rating no hero |

## Design — Sprints A–F concluídos (2026-05-29)
- Tokens, componentes compartilhados, publicFetch em lib/api
- .font-display sistemático, emojis → Lucide, hardcoded colors → tokens
- Login 2 colunas, dashboard eyebrow+italic, hub de Configurações
- Barbeiros em cards, Agenda com day picker, Vitrine 2 colunas + aside sticky

## Pendências de design (pós-sprints)
- settings/profile: ícone 👤 trocado por <Globe> — verificar semântica
- Vitrine: brand icons (Instagram/Facebook/TikTok) sem substituto semântico
- Vitrine: business_hours como string livre — highlight "Hoje" não implementado
- Vitrine: tab Barbeiros requer service_id — verificar estado atual
- G13 (BookingFlow): aguarda sprint de backend (remoção AWAITING_SHIFT)

## G13 BookingFlow concluído
- 4 steps visuais (Serviço · Barbeiro · Horário · Confirmar)
- BookingStepper com mapeamento FSM → UI
- AWAITING_SHIFT removido do componente
- publicFetch de lib/api em todas as chamadas públicas

### O que NÃO fazer (acréscimos ao design)

- Não alterar `BookingFlow.tsx` — sprint G13 separado
- Não hardcodar cores (`text-white`, `#25D366`, `bg-green-*`, etc.)
- Não usar emojis como ícones — sempre Lucide
- Não usar inline styles para hover/focus — sempre classes Tailwind

## Dívidas conhecidas
- book/[slug]: dias sem horários só são descobertos após seleção
  (business_hours retorna string livre — filtro visual preventivo
  requer backend retornar [{weekday, open, close}])
- [CORRIGIDO] NEXT_PUBLIC_API_URL=localhost em produção — causa raiz de todos os "Failed to fetch"
- [CORRIGIDO] cpf_cnpj_masked ausente do tipo Professional — fix em 6bf4afe
- [CORRIGIDO] working-hours frontend enviava objeto em vez de array — fix em 6bf4afe
- [CORRIGIDO] useSearchParams sem Suspense em 4 páginas (login, reset-password,
  book/[slug], appointments/new) — fix 8af2769 + e4983ee
- [CORRIGIDO] settings/profile: spread { ...EMPTY, ...data } sobrescrevia defaults
  com null da API — normalizeProfile() adicionado em 124a3c9
- [CORRIGIDO] payments/page.tsx: api() chamado sem .get() — fix eeb494d
- [CORRIGIDO] refundReason tipo incompatível com Select — fix e804949