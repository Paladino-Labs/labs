# PALADINO — BRIEF DA FASE 0 (LOVABLE)

**Objetivo:** especificar a *fundação de navegação* do Painel do Tenant — o shell role-aware que precede todo o restante do frontend. Derivado de `painel/docs/inventario-funcional.md` (§2, §4, §6, §9 Fase 0).

> **Escopo rígido:** apenas o shell. Nenhum CRUD, formulário, lógica de negócio ou chamada de API além de `auth/me` e `tenant/branding`. Ver §9.

---

## 1. Contexto do produto

Paladino é uma plataforma **SaaS multi-tenant** para gestão de negócios de serviço pessoal (barbearias no piloto — a vertical-âncora do Estágio 0). A stack é **Next.js 15 (App Router) · TypeScript · shadcn/ui · TailwindCSS · Lucide icons**, com **Cormorant Garamond** (display) e **Inter** (corpo). O código existente já tem `AuthContext` (JWT decodificado client-side), `lib/api.ts` com `BASE` apontando para produção, `ThemeProvider` (claro/escuro via `localStorage`), e um `Sidebar` colapsável funcional **porém sem filtro por role**. A Fase 0 transforma esse sidebar em role-aware, torna o dashboard role-aware com widgets mockados, cria os shells básicos das áreas Owner e Portal, e injeta o branding do tenant como CSS vars.

---

## 2. Design Tokens

Tokens semânticos já definidos em `painel/app/globals.css`. **Nunca hardcodar cores** — sempre os tokens.

### Paleta

| Token | Valor | Uso |
|---|---|---|
| Background principal | `#faf9f5` | fundo de página (`bg-background`) |
| Primária / brand | `#16242c` (petrol escuro) | sidebar, botões primários (`bg-primary`, `bg-sidebar`) |
| Accent | `#c79a5a` (brass/ouro antigo) | destaques, item ativo, ícones de marca (`text-sidebar-primary`) |
| Sidebar | fundo `#16242c`, texto/ícones claros (`text-sidebar-foreground`) | navegação |

### Tipografia

| Papel | Fonte | Como aplicar |
|---|---|---|
| Marca / títulos | **Cormorant Garamond** / serif (`--font-display`) | "PALADINO", `h1/h2/h3`, labels do sidebar |
| Corpo | **Inter** / sans-serif | texto corrido |

- `h1/h2/h3` herdam Cormorant Garamond automaticamente via `@layer base`.
- Em `span`/`div`, aplicar display type com `[font-family:var(--font-display)]` (ou classe `font-display`).

### Convenções

- Tokens semânticos sempre: `bg-card`, `border-border`, `text-muted-foreground`, `bg-primary` — nunca `bg-white` / `text-gray-*`.
- **Ícones:** Lucide, `size={16}` `strokeWidth={1.5}` — nunca emojis.
- **Item de nav ativo:** `italic` + sufixo `◆` em accent.
- **Moeda:** `formatBRL()` de `lib/utils.ts`. **Datas:** `formatDateTime()` com `timeZone` explícito.
- Identidade por tenant via **tokens** (logo, cores, fonte, favicon) — UI única, nunca layouts paralelos por tenant.

---

## 3. Estrutura de rotas — Fase 0 apenas

Apenas os grupos/rotas que a Fase 0 toca. O resto pertence às fases seguintes (§9 do inventário) e **não deve ser criado agora**.

```
app/
  (auth)/                          ← já existem (login na raiz page.tsx)
    page.tsx        → login
    activate/       → ativação de convite
    forgot-password/
    reset-password/

  (dashboard)/
    layout.tsx      ← ALVO PRINCIPAL (shell do tenant: sidebar + header + branding + guards)
    dashboard/
      page.tsx      ← dashboard role-aware (widgets mockados)

  (owner)/
    layout.tsx      ← shell básico (vazio, guard PLATFORM_OWNER)

  (portal)/
    layout.tsx      ← shell básico (vazio, sem sidebar do tenant)
```

> O `(dashboard)/layout.tsx` atual já faz o guard de autenticação e monta `<Sidebar />` + `<main>`. A Fase 0 estende isso com header, branding e breadcrumbs — **sem quebrar** o guard de hidratação existente.

---

## 4. Sidebar — especificação completa

O `Sidebar.tsx` atual tem 8 links **sem filtro por role** (`roles: null`) e já é colapsável (desktop `w-60 ↔ w-16`, persistido em `localStorage`) + drawer mobile com hamburguer. **Manter** esse comportamento; adicionar grupos/submenus e filtro por role.

### Origem do role

Vem do JWT via `useAuth()`. Tipo: `"OWNER" | "ADMIN" | "OPERATOR" | "PROFESSIONAL"`.

```tsx
const { role } = useAuth()
const isOwnerOrAdmin = ["OWNER", "ADMIN"].includes(role ?? "")
```

> RBAC do frontend **espelha** as regras de negócio mas não é a verdade — a verdade é o backend (403 → ocultar item). Itens marcados "opt-in por config" só aparecem se a config do tenant habilitar.

### OWNER / ADMIN (visão completa, agrupada)

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

### Ícones sugeridos (Lucide)

`LayoutDashboard` Dashboard · `Calendar` Agenda · `ClipboardList` Operações · `ListOrdered` Fila · `MessageSquare` Inbox/Comunicação · `Users` Clientes/CRM · `Scissors` Serviços · `Package` Produtos/Catálogo · `Tags` Categorias/Promoções · `Boxes` Pacotes/Assinaturas · `Wallet` Pagamentos/Financeiro · `BarChart3` DRE/Relatórios · `Landmark` Contas · `Receipt` Despesas/Payables · `Warehouse` Estoque · `Truck` Fornecedores · `HandCoins` Comissões · `FileSpreadsheet` Extrato · `Percent` Taxas · `UserCircle` Profissionais · `Settings` Configurações · `ShieldCheck` Audit.

### Estado / aparência (manter o atual)

- Colapsável no desktop: `w-60 ↔ w-16` com `transition-all duration-200`, estado persistido em `localStorage` (`sidebar_collapsed`).
- Mobile: drawer + overlay + hamburguer já implementados — preservar.
- Labels em `font-display`; **item ativo:** `italic` + `◆` accent.
- Grupos: header de grupo em `text-[10px] uppercase tracking-[0.25em] text-muted-foreground` (segue o estilo do label "MENU" atual). Esconder headers de grupo quando colapsado.

---

## 5. Dashboard — widgets por role (dados mockados)

Não há endpoint `/dashboard` agregado no Estágio 0 — a home **compõe** widgets. Na Fase 0 os dados são **mockados** (não implementar chamadas). Render condicionado ao `role`.

### OWNER / ADMIN — KPIs e widgets

- **KPI strip:** Resumo do dia (agendamentos, faturamento, ocupação).
- Receita × Despesa × Margem do mês (gráfico barras/linha).
- Alertas: pagamentos a confirmar.
- Alertas: estoque baixo (badge).
- Alertas: cotas expirando (badge).
- Alertas: promoções expirando (badge).
- Pendências: payables vencendo (lista).
- Pendências: conciliação aberta / caixa (card).
- CRM: clientes em risco (lista).

### OPERATOR — widgets

- Agenda do dia.
- Fila de espera.
- Atendimento humano (conversas escaladas).
- Cobranças pendentes.
- Caixa (CashCount).

> Sem widgets de financeiro sensível (DRE, comissões, contas) salvo config.

### PROFESSIONAL — widgets

- Próximos atendimentos (próprios).
- Ações rápidas (iniciar / concluir / remarcar / cancelar).
- Extrato de comissões próprias (se visibilidade ativada).

---

## 6. Header

Barra superior do shell `(dashboard)`:

- **Logo Paladino** (Cormorant, brass) à esquerda.
- **Toggle do sidebar** (desktop) + **hamburguer** (mobile) — o toggle de colapso já existe no Sidebar; o header pode reaproveitá-lo.
- **Nome do tenant** (via `GET /companies/me`; `useAuth()` expõe `companyId` mas **não** o nome).
- **Nome do usuário + role** (`useAuth()` → `name`, `role`; usar `ROLE_LABELS` de `lib/constants.ts`).
- **Tema claro/escuro** (`useTheme()` de `lib/theme.tsx`, já existe).
- **Botão sair** (`useAuth().logout`).

---

## 7. Tenant Branding

Ao montar o `(dashboard)/layout.tsx`, buscar `GET /tenant/branding` (endpoint **público**):

```ts
{ logo_url, primary_color, accent_color, font_display, favicon_url }
```

Injetar como CSS vars em `:root` (sobrescrevendo os tokens base). **Se ausente / erro:** usar os defaults do Design System — `#16242c` (primary), `#c79a5a` (accent). Não bloquear a renderização do shell esperando o branding.

---

## 8. Guards e navegação

- **Não autenticado** → redirect para `/` (o layout atual já faz isso após hidratação; preservar o guard de `hydrated` para evitar loop login↔dashboard).
- **PROFESSIONAL** tentando acessar `/financeiro/*` → redirect para `/dashboard`.
- **Não PLATFORM_OWNER** tentando acessar `/owner/*` → redirect para `/dashboard`.
  *(Nota técnica: o JWT de tenant usa `OWNER|ADMIN|OPERATOR|PROFESSIONAL` e sempre carrega `company_id`. `PLATFORM_OWNER` é role de **plataforma** — o indicador real no backend é `company_id == null`. O guard do `(owner)/*` deve verificar `useAuth().companyId == null`, **não** uma string de role.)*
- **Breadcrumbs automáticos** baseados na rota atual (derivar dos segments do pathname).

---

## 9. O que NÃO implementar na Fase 0

- Nenhum CRUD.
- Nenhum formulário.
- Nenhuma chamada de API além de `tenant/branding` (público) e `auth/me` / `companies/me`.
- Nenhuma lógica de negócio.
- Nenhuma tela além de `dashboard/page.tsx` (mockado) e os shells `(owner)`/`(portal)`.
- Não migrar rotas duplicadas ainda (a consolidação `/payments ↔ /financeiro/pagamentos` é item da Fase 0 do *plano de implementação*, mas executada pelo Claude Code, não pelo Lovable).
