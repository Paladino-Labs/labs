# PALADINO — BRIEF DO SPRINT VISUAL GAP (LOVABLE)

**Objetivo:** trazer ao padrão visual das Fases 1–4 as telas que **já existem no código** com vocabulário **pré-Lovable** (status "Feito"/"Ajustar" no inventário, nunca prototipadas no Lovable). É um sprint de **consistência visual, não de lógica**: nenhuma chamada de API, regra de negócio ou fluxo muda. Só o "casco" visual de cada tela é atualizado para a mesma régua das telas das Fases 1–4 (`PageHeader`, `Table`/lista padrão, `EmptyState`/`ErrorState`/`Skeleton`, `FsmBadge`, `ActiveBadge`, `sonner/toast`, tokens semânticos). Inclui **uma tela nova** (`/relatorios`) — um hub de acesso rápido a relatórios existentes. Derivado de `painel/docs/inventario-funcional.md` (§5, telas "Ajustar"/"Feito" sem prototipagem) e da leitura direta dos `page.tsx` atuais.

> **Continuação das Fases 0–4.** O *shell* (sidebar role-aware, header, branding, guards, tokens) e todos os componentes/utilitários **já existem** — ver §2. Este sprint **não cria telas novas de domínio**, exceto `/relatorios`. **Dados mockados** no protótipo Lovable; o Claude Code aplica o visual sobre as telas reais existentes **sem tocar na lógica**.

> **⚠️ Regra de ouro deste sprint:** **NÃO reimplementar lógica, chamadas de API, FSM, validações nem fluxos.** O protótipo Lovable só define o *visual*. Onde a tela atual já está correta visualmente (ex.: `settings` hub, `comissoes` hub), a mudança é mínima (apenas `PageHeader`). Onde usa `alert()`/`confirm()`, `<table>` cru, cores hardcoded ou erros inline, troca-se pelo componente padrão.

---

## 1. Contexto do produto (herdado das Fases 0–4)

Paladino é uma plataforma **SaaS multi-tenant** para gestão de negócios de serviço pessoal (barbearias no piloto — vertical-âncora do Estágio 0). Stack: **Next.js 16 (App Router) · TypeScript · shadcn/ui · TailwindCSS v4 · Lucide icons**, **Cormorant Garamond** (display) e **Inter** (corpo). As Fases 1–4 consolidaram um vocabulário visual (PageHeader + Table + estados + FsmBadge + toast). As telas deste sprint foram construídas **antes** desse vocabulário (Sprints A–F / Fase 1) e ficaram com padrões antigos: `alert()`/`confirm()` nativos, `<table>` cru com classes ad-hoc, badges com cores hex hardcoded (`bg-green-100 text-green-800`), feedback inline "Salvo ✓", blocos "Acesso restrito" custom, loading/erro como `<p>` solto. Este sprint **só** alinha o visual; a verdade continua sendo o backend.

---

## 2. Shell e padrão visual existente — **NÃO reimplementar**

Entregues nas Fases 0–4 e reaproveitados aqui:

- **Sidebar role-aware** (`components/Sidebar.tsx`) — grupos já existem. Este sprint **ativa** a rota nova `/relatorios` no grupo **Administração** (hoje "Em breve").
- **Header**, **`(dashboard)/layout.tsx`** (guard de auth + branding via CSS vars + breadcrumbs), **`useAuth()`** (`role`, `companyId`, `name`, `userId`), **design tokens** em `globals.css`.
- **`components/PageHeader.tsx`** — `title` + `description?` + `eyebrow?` + slot de ações (`children`). É o cabeçalho-padrão de **toda** tela (`font-display text-3xl tracking-wide` + borda inferior).
- **`components/empty-state.tsx`** (`EmptyState`) — modo card (`title`/`description`/`icon`/`action`) ou modo legado (`message`). Substitui blocos "Acesso restrito" custom e `<p>` "Nenhum X".
- **`components/ErrorState.tsx`** (`ErrorState`) — card de erro com botão "Tentar novamente" (`onRetry`). Substitui `<p className="text-destructive">{error}</p>`.
- **`components/ui/skeleton.tsx`** (`Skeleton`) — placeholder de loading. Substitui `<p>Carregando…</p>`.
- **`components/FsmBadge.tsx`** — badges das Fases 1–4 (`AppointmentBadge`, `PaymentBadge`, `ExpenseBadge`, …). **Este sprint adiciona** `CommissionBadge` e `CommissionPayoutBadge` no mesmo padrão (`<Badge variant="outline" className={cn("font-normal", CLASS[status])}>` com as constantes `EMERALD/AMBER/DESTRUCTIVE/NEUTRAL/SKY`). Ver §4.
- **`components/ActiveBadge.tsx`** (ativo/inativo) — reaproveitar para `Professional.active` e linhas de status.
- **`components/CustomerAutocomplete.tsx`**, **`components/DateTimePicker.tsx`**, **`components/MoneyInput.tsx`** — reaproveitar quando já estiverem em uso.
- **Tabela padrão** — duas formas equivalentes já em uso nas Fases 1–4: o componente `components/ui/table.tsx` (`Table`/`TableHeader`/`TableRow`/…) **ou** o `<table className="w-full text-sm">` dentro de `rounded-lg border border-border` com `thead className="bg-muted/50 text-muted-foreground"`. Ambos são "padrão"; o que **não** é padrão é `<table>` com classes ad-hoc e sem moldura.
- **Glossários** (`lib/constants.ts`) — `ROLE_LABELS`, `FEE_SOURCE_LABELS`, `APPOINTMENT_STATUS_LABELS`, etc. já existem. **Este sprint adiciona** `COMMISSION_STATUS_LABELS` e `COMMISSION_PAYOUT_STATUS_LABELS` (ver §4). `constants.ts` é a fonte única.
- **Utils** — `formatBRL()`, `formatDateTime()` (timezone do tenant, fallback `America/Sao_Paulo`), `formatDateShort()` em `lib/utils.ts`.
- **`sonner/toast`** — após toda ação de escrita (success/error). Erro deriva do `detail` da API (já tratado em `lib/api.ts`).

### Tokens e convenções (relembrete)

- Tokens semânticos sempre (`bg-card`, `border-border`, `text-muted-foreground`, `bg-primary`, `text-destructive`, `text-success`) — **nunca** `bg-white`/`text-gray-*` nem cores hardcoded (`bg-green-100`, `text-green-600`, `#25D366`).
- Ícones **Lucide** `size={16}` `strokeWidth={1.5}` — nunca emojis.
- `h1/h2/h3` herdam Cormorant Garamond; cabeçalho de página **sempre** via `PageHeader` (ou, se inviável por toolbar custom, `font-display text-3xl tracking-wide`).
- **Datas:** `formatDateTime()` / `formatDateShort()`. Moeda: `formatBRL()`.

**O protótipo Lovable produz apenas o conteúdo das páginas** (dentro de `<main>`). O shell não é reproduzido.

---

## 2b. Referências visuais

Para cada tela, **consultar a pasta de screenshots das Fases 1–4 compartilhada na sessão**. Se houver screenshot aprovada de uma tela equivalente (ex.: Despesas, Pagáveis, Comunicação — Logs), ela é o contrato visual de referência para tabela, filtros, estados e badges.

> **Status real:** estas telas **não têm** screenshots próprias (nunca passaram pelo Lovable) e **não existem no barberflow-system**. O alvo visual é o **vocabulário já consolidado nas Fases 1–3**: a tela de **Despesas** é o melhor molde de "lista + filtros + estados + badge + ações em Dialog"; o hub de **Comissões** e o hub de **Configurações** são o molde de "grid de cards de acesso rápido" (reaproveitado em `/relatorios`).

---

## 3. O que cada tela faz hoje (leitura dos `page.tsx` atuais)

São **9 superfícies existentes** + **1 nova** (`/relatorios`, §5) = **10 telas** no sprint. Para cada superfície: endpoints/dados, componentes atuais, e o desvio visual a corrigir.

### 3.1 — Agenda (`/agenda`)
- **Faz hoje:** navegação por semana + day picker com contagem por dia; toggle Lista/Calendário (`AgendaCalendar`); filtros (barbeiro, status); `Dialog` de detalhe e de remarcar; conclusão via `PaymentOnCompleteDialog`. Endpoints: `GET /appointments/?start_after&start_before&page_size`, `GET /professionals/`, `PATCH /appointments/{id}/cancel`, `PATCH /appointments/{id}/reschedule`.
- **Padrão atual:** `<p>Carregando…</p>` e `<p className="text-destructive">` para loading/erro; badge de status via `Badge variant={APPOINTMENT_STATUS_VARIANT[...]}` (abordagem antiga por *variant*); `confirm()` para cancelar; `alert()` para erros de cancel/reschedule; `<p>` central "Nenhum agendamento para este dia".
- **Mudar (visual):** loading → `Skeleton`; erro → `ErrorState` (retry = recarregar a semana); badge → **`AppointmentBadge`** de `FsmBadge` (lista **e** dialog de detalhe); `confirm()` → `AlertDialog`/`Dialog` de confirmação; `alert()` → `toast.error`; toast de sucesso após cancelar/remarcar; "Nenhum agendamento" → `EmptyState`. **Manter** toda a navegação de semana, o toggle e o `AgendaCalendar` como estão (a toolbar custom permanece; só os estados e o badge mudam).

### 3.2 — Novo agendamento (`/appointments/new`)
- **Faz hoje:** formulário (barbeiro → serviço → data → slots disponíveis → cliente buscar/cadastrar inline). Endpoints: `GET /professionals/`, `GET /services/`, `GET /customers/`, `GET /availability/slots`, `POST /customers/`, `POST /appointments/`.
- **Padrão atual:** `<h1 className="font-display text-2xl">` (tamanho fora do padrão); erro de carga inicial e de submit como `<p className="text-destructive">`; sem toast.
- **Mudar (visual):** cabeçalho → `PageHeader` (ou `font-display text-3xl tracking-wide`) com link "Voltar"; erro de carga inicial → `ErrorState`; erros de submit/cadastro de cliente → `toast.error`; `toast.success` ao agendar (hoje só redireciona). **Manter** o fluxo de slots e o sub-form de cliente inline (erros de validação de campo podem continuar inline, são de formulário).

### 3.3 — Barbeiros (`/professionals`)
- **Faz hoje:** grid de cards (avatar, especialidades, dias da semana, comissão); `Dialog` "Novo Barbeiro"; toggle ativar/desativar. Endpoints: `GET /professionals/`, `POST /professionals/`, `PATCH /professionals/{id}`.
- **Padrão atual:** `<p>Carregando…</p>`; `<p>` central "Nenhum barbeiro cadastrado"; `alert()` no toggle; `setError` da carga **nunca é renderizado** (bug visual — em erro a tela fica vazia); sem toast.
- **Mudar (visual):** cabeçalho → `PageHeader` com botão "Novo Barbeiro" no slot de ações; loading → `Skeleton` (grid de cards); erro de carga → `ErrorState` (retry); vazio → `EmptyState` (com ação "Novo Barbeiro"); `alert()` → `toast.error`; `toast.success` ao criar e ao ativar/desativar; opcional: `ActiveBadge` no card. **Manter** o layout de cards e os campos condicionais "Em breve".

### 3.4 — Comissões (superfície com 4 telas)
**3.4a Hub (`/comissoes`)** — KPIs (a pagar / pago 30d / profissionais com pendência) + 3 cards de acesso rápido. Endpoint: `GET /commissions`.
- **Atual:** loading "…" e erro `<p>` inline. **Mudar:** cabeçalho → `PageHeader`; erro → `ErrorState`; KPIs em `Skeleton` no loading. Cards de acesso rápido já estão no padrão (molde para `/relatorios`).

**3.4b Regras (`/comissoes/politicas`)** — regra global + tabela de regras específicas; `Dialog` criar/editar; desativar. Endpoints: `GET /commission-policies`, `/professionals`, `/services`; `POST/PATCH/DELETE /commission-policies`.
- **Atual:** "Acesso restrito" como `<p>`; loading/erro `<p>`; `<h1 className="text-3xl">` **sem `font-display`**; `<table>` cru; `<input type="number">` cru; feedback "Salvo ✓" em `text-green-600` (hardcoded); `alert()` no erro de delete; confirmação de delete inline ("Desativar? Sim/Não").
- **Mudar:** "Acesso restrito" → `EmptyState`; loading → `Skeleton`; erro → `ErrorState`; cabeçalho → `PageHeader`; `<table>` cru → tabela padrão (moldura + `thead` muted); `<input>` cru → `Input`; feedback inline + `alert()` → `toast.success/error`; confirmação de delete → `AlertDialog`. **Manter** toda a lógica de regra global vs. específica e o mapeamento de labels Stage 0/legado.

**3.4c Histórico (`/comissoes/historico`)** — filtros (barbeiro, status, período) + tabela + total pendente. Endpoint: `GET /commissions?...`.
- **Atual:** `StatusBadge` custom com cores hardcoded (`bg-yellow-100`, `bg-green-100`, `bg-red-100`); `<table>` cru; loading/erro `<p>`. (Já usa `EmptyState` — bom.)
- **Mudar:** `StatusBadge` custom → **`CommissionBadge`** novo (§4); `<table>` cru → tabela padrão; loading → `Skeleton`; erro → `ErrorState`; cabeçalho → `PageHeader`. **Manter** filtros e cálculo de total.

**3.4d Pagamentos (`/comissoes/pagamentos`)** — seleciona barbeiro → lista comissões pendentes → registra payout; histórico de payouts. Endpoints: `GET /professionals`, `/commission-payouts`, `/financial/accounts`, `GET /commissions?professional_id`, `POST /commission-payouts`.
- **Atual:** "Acesso restrito" `<p>`; card de confirmação inline com cores verdes hardcoded + auto-dismiss 3s; badge "Pago" hardcoded `bg-green-600`; `<table>` cru; `bootError`/`postError` inline.
- **Mudar:** "Acesso restrito" → `EmptyState`; confirmação inline → `toast.success`; badge "Pago" → **`CommissionPayoutBadge`** novo (§4); `<table>` cru → tabela padrão; `bootError` → `ErrorState`; `postError` → `toast.error`; cabeçalho → `PageHeader`. **Manter** seleção de conta e o fluxo de criação de payout.

### 3.5 — Taxas de maquininha (`/financeiro/taxas`)
- **Faz hoje:** tabela editável de taxas por método (% + fixa), salvar por linha. Endpoints: `GET /financial/fee-policies`, `PATCH /financial/fee-policies/{source}`.
- **Padrão atual:** componente `AccessRestricted` custom; loading/erro `<p>`; cabeçalho `[font-family:var(--font-display)]`; `<table>` + `<input>` crus; feedback "Salvo ✓" `text-green-600` e "Não configurado" `text-amber-600` (hardcoded); sem toast.
- **Mudar (visual):** `AccessRestricted` → `EmptyState`; loading → `Skeleton`; erro → `ErrorState`; cabeçalho → `PageHeader`; `<table>` cru → tabela padrão; `<input>` cru → `Input`; "Salvo ✓" → `toast.success`; hint "Não configurado" → `text-muted-foreground` (ou badge âmbar via token). **Manter** a edição por linha e a regra de `CASH` não-editável.

### 3.6 — Registrar pagamento (`/financeiro/pagamentos/novo`)
- **Faz hoje:** form (cliente → agendamento opcional → valor → método) com fases form/loading/success; `FeeWarningBanner`. Endpoints: `GET /appointments?customer_id`, `POST /payments`, `POST /payments/{id}/confirm-manual`.
- **Padrão atual:** bloco "Acesso restrito" custom; título de sucesso `text-green-700` hardcoded; erro de submit inline `<p>`.
- **Mudar (visual):** "Acesso restrito" → `EmptyState`; cabeçalho → `PageHeader` (mantendo link "Voltar"); cor de sucesso `text-green-700` → `text-success`; erro de submit → `toast.error` (além do card de sucesso já existente). **Manter** as 3 fases (form/loading/success), o seletor de métodos e o `FeeWarningBanner`.

### 3.7 — Configurações — hub (`/settings`)
- **Faz hoje:** grid de cards de seção (Perfil, Empresa, Segurança, Usuários, Integrações, Comunicação). Estático.
- **Padrão atual:** já está no vocabulário (grid de cards igual ao hub de Comissões). Cabeçalho é `<h1 font-display>`.
- **Mudar (visual):** **mínimo** — cabeçalho → `PageHeader`. Opcional: incluir um card "Relatórios" apontando para `/relatorios` (ou deixar só na sidebar). Nenhuma outra mudança.

### 3.8 — Meu Perfil (`/settings/perfil`)
- **Faz hoje:** form nome (editável) + email (read-only) + papel (badge). Endpoints: `GET /auth/me`, `PATCH /auth/profile`.
- **Padrão atual:** `ROLE_LABELS` **duplicado localmente** (já existe em `constants.ts`); feedback "Salvo ✓" inline; erro inline.
- **Mudar (visual):** cabeçalho → `PageHeader`; usar `ROLE_LABELS` de `constants.ts`; "Salvo ✓" → `toast.success`; erro → `toast.error`; opcional `Skeleton` enquanto carrega o `GET`. **Manter** o form e o read-only do email.

### 3.9 — Segurança (`/settings/security`)
- **Faz hoje:** form trocar senha (atual/nova/confirmar) com validação client-side. Endpoint: `POST /auth/change-password`.
- **Padrão atual:** `<h1 className="font-display text-2xl">` (tamanho fora do padrão); box de sucesso inline; erro de submit inline `<p>`.
- **Mudar (visual):** cabeçalho → `PageHeader`; sucesso → `toast.success` (pode manter o box, mas alinhar a tokens `border-success/40 bg-success/15`); erro de submit → `toast.error`. **Manter** a validação de campo inline (é de formulário).

---

## 4. Especificação visual — foco no que muda

Regra geral por tela (aplicar onde o padrão antigo aparecer):

| Padrão antigo | Padrão alvo (Fases 1–4) |
|---|---|
| `<h1>` custom / `text-2xl` / `text-3xl` sem `font-display` | `PageHeader` (`title`, `description?`, slot de ações) |
| `<p>Carregando…</p>` | `Skeleton` (forma da tabela/grid) |
| `<p className="text-destructive">{error}</p>` | `ErrorState` com `onRetry` |
| `<p>` "Nenhum X" / "Acesso restrito" custom / `AccessRestricted` | `EmptyState` (`title`/`description`/`icon`/`action?`) |
| `alert(msg)` / `confirm(msg)` | `toast.error` / `AlertDialog` (ou `Dialog`) |
| Erro inline de ação de escrita | `toast.error` (deriva do `detail`) |
| Feedback inline "Salvo ✓" / `text-green-600` | `toast.success` |
| Badge com cor hex hardcoded (`bg-green-100`…) | `FsmBadge` correspondente / `ActiveBadge` |
| `<table>` cru com classes ad-hoc | tabela padrão (moldura `rounded-lg border` + `thead bg-muted/50`) |
| `<input>` cru | `Input` (e `MoneyInput` onde for moeda) |
| Cor de texto/estado hardcoded (`text-green-700`, `text-amber-600`) | tokens (`text-success`, `text-muted-foreground`, `text-destructive`) |

**Estados obrigatórios** em telas de listagem/carga (Agenda, Barbeiros, Comissões ×4, Taxas): **loading (`Skeleton`) · erro (`ErrorState` + retry) · vazio (`EmptyState`) · dados**.

### Badges e glossários novos — adicionar a `components/FsmBadge.tsx` e `lib/constants.ts`

Mesma régua dos badges existentes (constantes `EMERALD/AMBER/DESTRUCTIVE/NEUTRAL/SKY` já no arquivo). Valores **exatos** do backend (lidos das telas atuais).

**`CommissionBadge`** (status da comissão):
| Estado | Label | Cor |
|---|---|---|
| `CALCULATED` | Pendente | âmbar |
| `DUE` | Vence em breve | sky |
| `PAID` | Paga | emerald |
| `REVERSED` | Estornada | destructive |

**`CommissionPayoutBadge`** (status do payout):
| Estado | Label | Cor |
|---|---|---|
| `PAID` | Pago | emerald |
| `PENDING` | Pendente | âmbar |
| `FAILED` | Falhou | destructive |

Glossários em `lib/constants.ts` (fonte única):
- `COMMISSION_STATUS_LABELS`: `CALCULATED`→"Pendente", `DUE`→"Vence em breve", `PAID`→"Paga", `REVERSED`→"Estornada".
- `COMMISSION_PAYOUT_STATUS_LABELS`: `PAID`→"Pago", `PENDING`→"Pendente", `FAILED`→"Falhou".
- `ROLE_LABELS` **já existe** — o Perfil deve consumi-lo (remover a duplicata local).

> **NPS score** e os badges das Fases 1–4 **já existem** — não recriar.

---

## 5. Tela nova: `/relatorios`

Única tela criada do zero neste sprint. **Não tem endpoint próprio** — é um hub de navegação para telas que já existem (cada card é um link).

- **Rota:** `/relatorios` · **Role:** OWNER/ADMIN (sidebar, grupo **Administração**).
- **Layout:** `PageHeader` "Relatórios" (description "Acesso rápido a indicadores e relatórios") + **grid de cards** (mesmo molde do hub de Comissões / Configurações: `Card` com ícone em quadro `bg-primary/15 text-primary` + título `font-display` + descrição + `ChevronRight`).
- **Cards ativos** (link para tela existente):
  | Card | Destino | Ícone (Lucide) |
  |---|---|---|
  | DRE | `/financeiro/dre` | `FileBarChart` |
  | Comissões | `/comissoes` | `BadgeDollarSign` |
  | NPS | `/nps` | `Star` |
  | Estoque | `/estoque` | `Boxes` |
  | Auditoria | `/audit` | `ShieldCheck` |
  | CRM | `/crm` | `Users` |
- **Cards "Em breve"** (desabilitados, visual muted, badge "Em breve"; sem link):
  - Fluxo de caixa
  - Performance por profissional
  - Agendamentos por período
- **Estados:** estático (sem fetch) — só os cards. Cards "Em breve" com `opacity` reduzida, `cursor-default` e `Badge` "Em breve".

> Os destinos podem ainda não existir como rota neste momento (DRE/NPS/Estoque/Audit/CRM são de Fases anteriores ou paralelas). Se um destino não existir, o card pode levar a um "Em breve" — mas a **estrutura** de `/relatorios` é o entregável.

---

## 6. O que NÃO mudar

- **Lógica de negócio** de qualquer tela (FSM, validações, cálculos, idempotência).
- **Chamadas de API** existentes (mesmos paths, métodos, bodies, query params).
- **Fluxos** (fases form/loading/success do pagamento; navegação de semana da Agenda; fluxo de slots do Novo agendamento; regra global vs. específica das comissões).
- **Telas das Fases 0–4** — já estão no padrão; não tocar.
- **Shell** (sidebar, header, layout, branding, guards) — exceto **ativar o link `/relatorios`** na sidebar.
- **Não inventar** colunas, campos ou ações sem endpoint. Ação sem backend → não renderizar.
- **Não recriar** badges/glossários já existentes; só adicionar `CommissionBadge`, `CommissionPayoutBadge` e os dois glossários novos.

---

*Fonte de verdade de comportamento: `painel/docs/inventario-funcional.md` + os `page.tsx` atuais. Nenhuma regra de negócio vive no frontend. Documento de planejamento — nenhum arquivo de código foi modificado nesta sessão.*
