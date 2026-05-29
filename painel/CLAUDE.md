# painel — contexto operacional

**Sprint atual:** Sprint 6 em andamento (Fase 2 — Financial Core)
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
- Formatação monetária: `formatBRL()` de `lib/utils.ts`
- Formatação de data: `formatDateTime()` de `lib/utils.ts` com `timeZone` explícito
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