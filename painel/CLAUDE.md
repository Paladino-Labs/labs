# painel — contexto operacional

**Sprint atual:** Sprint de Backend BookingFlow em andamento (pré-G13)
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

### O que NÃO fazer (acréscimos ao design)

- Não alterar `BookingFlow.tsx` — sprint G13 separado
- Não hardcodar cores (`text-white`, `#25D366`, `bg-green-*`, etc.)
- Não usar emojis como ícones — sempre Lucide
- Não usar inline styles para hover/focus — sempre classes Tailwind