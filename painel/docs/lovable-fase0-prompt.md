# PALADINO — PROMPT FASE 0 (colar no Lovable)

> Prompt pronto para colar. Spec completa em `painel/docs/lovable-fase0-brief.md`.

---

```
Você é arquiteto de frontend sênior construindo o Paladino —
plataforma SaaS multi-tenant para gestão de negócios de serviço
(barbearias no piloto).

Stack: Next.js 15 (App Router) · TypeScript · shadcn/ui · Tailwind
· Lucide icons · Cormorant Garamond (display) · Inter (corpo)

━━━ ESCOPO DESTA SESSÃO: FASE 0 ━━━
Implementar apenas o SHELL da aplicação.
NÃO implementar CRUDs, formulários ou lógica de negócio.
NÃO chamar API além de tenant/branding e auth/me.

━━━ DESIGN TOKENS ━━━
Tokens semânticos já existem em globals.css. Nunca hardcodar cores.

Paleta:
  bg-background  #faf9f5  (fundo de página)
  bg-primary / bg-sidebar  #16242c  (petrol escuro — sidebar, botões primários)
  text-sidebar-primary (accent)  #c79a5a  (brass/ouro — destaques, item ativo)
  bg-sidebar  #16242c, text-sidebar-foreground claro

Tipografia:
  Títulos/marca: Cormorant Garamond via --font-display
    (h1/h2/h3 herdam via @layer base; em span/div use font-display)
  Corpo: Inter (sans)

Convenções:
  - Tokens semânticos sempre (bg-card, border-border, text-muted-foreground,
    bg-primary) — nunca bg-white / text-gray-*
  - Ícones: Lucide size={16} strokeWidth={1.5} — nunca emojis
  - Item de nav ativo: italic + sufixo ◆ em accent
  - Moeda: formatBRL() ; datas: formatDateTime() com timeZone explícito

━━━ SIDEBAR ROLE-AWARE ━━━
Role vem de useAuth().role: "OWNER"|"ADMIN"|"OPERATOR"|"PROFESSIONAL"
Guard de exemplo:
  const isOwnerOrAdmin = ["OWNER","ADMIN"].includes(role ?? "")

Manter o que já existe: colapsável no desktop (w-60 ↔ w-16, transition,
persistido em localStorage) + drawer/hamburguer no mobile.
Adicionar grupos/submenus + filtro por role.

OWNER/ADMIN (completo, agrupado):
  Operação: Dashboard · Agenda · Operações · Fila · Atendimento humano (Inbox)
  Relacionamento: Clientes/CRM · Comunicação
  Comercial: Catálogo (Serviços·Produtos·Categorias) · Pacotes/Assinaturas · Promoções/Cupons
  Financeiro: Pagamentos · Gestão Financeira (DRE·Contas·Conciliação) · Despesas
              · Estoque/Fornecedores · Payables · Comissões · Extrato · Taxas
  Administração: Profissionais · Usuários/Acessos · Configurações (Branding·Módulos·Canais)
              · Relatórios · Audit
  (ADMIN = igual, sem ações OWNER-exclusivas)

OPERATOR:
  Dashboard · Agenda · Operações · Fila · Atendimento humano
  Clientes · Catálogo (view) · Pagamentos (cobranças) · Caixa (CashCount)
  (oculto: DRE, Contas, Comissões payout, Audit, Usuários, Branding/Módulos)

PROFESSIONAL:
  Dashboard (meus atendimentos) · Agenda própria · Operações próprias
  Clientes atendidos (view) · Extrato de comissões próprias (se ativado)

Ícones Lucide sugeridos: LayoutDashboard, Calendar, ClipboardList, ListOrdered,
  MessageSquare, Users, Scissors, Package, Tags, Boxes, Wallet, BarChart3,
  Landmark, Receipt, Warehouse, Truck, HandCoins, FileSpreadsheet, Percent,
  UserCircle, Settings, ShieldCheck.
Header de grupo: text-[10px] uppercase tracking-[0.25em] text-muted-foreground
  (esconder quando colapsado).

━━━ DASHBOARD (dados MOCKADOS, sem endpoints) ━━━
Render condicionado ao role.
OWNER/ADMIN: KPI strip (agendamentos/faturamento/ocupação) · Receita×Despesa×Margem
  (gráfico) · alertas (pagamentos a confirmar, estoque baixo, cotas/promoções
  expirando) · pendências (payables vencendo, conciliação/caixa) · CRM clientes em risco
OPERATOR: agenda do dia · fila · atendimento humano · cobranças pendentes · caixa
PROFESSIONAL: próximos atendimentos próprios · ações rápidas · extrato de comissões próprias

━━━ HEADER ━━━
Logo Paladino (Cormorant, brass) · toggle sidebar (desktop) + hamburguer (mobile)
· nome do tenant (GET /companies/me) · nome do usuário + role (useAuth, ROLE_LABELS)
· tema claro/escuro (useTheme) · botão sair (useAuth().logout)

━━━ TENANT BRANDING ━━━
Ao montar (dashboard)/layout.tsx: GET /tenant/branding (público)
  → { logo_url, primary_color, accent_color, font_display, favicon_url }
Injetar como CSS vars em :root. Não bloquear o render esperando.
Fallback se ausente/erro: #16242c (primary), #c79a5a (accent)

━━━ GUARDS ━━━
Não autenticado → / (preservar guard de hydrated p/ não dar loop login↔dashboard)
PROFESSIONAL em /financeiro/* → /dashboard
Acesso a /owner/* exige PLATFORM_OWNER → guard verifica useAuth().companyId == null
  (NÃO uma string de role; PLATFORM_OWNER = company_id null no JWT). Senão → /dashboard
Breadcrumbs automáticos derivados do pathname.

━━━ ESTRUTURA DE ROTAS ━━━
(dashboard)/layout.tsx ← principal (sidebar + header + branding + guards)
(dashboard)/dashboard/page.tsx ← dashboard role-aware (mockado)
(owner)/layout.tsx ← shell básico vazio (guard PLATFORM_OWNER)
(portal)/layout.tsx ← shell básico vazio (sem sidebar do tenant)
(auth) já existe (login, activate, forgot, reset)

━━━ REGRAS ABSOLUTAS ━━━
- Tokens semânticos nunca hardcoded (bg-primary, não #16242c)
- h1/h2/h3: Cormorant Garamond via font-display
- Ícones: Lucide 16px strokeWidth=1.5 — nunca emojis
- Item de nav ativo: italic + ◆ accent
- Sidebar colapsável no desktop (w-60 ↔ w-16 com transição)
- Mobile: drawer/hamburguer preservado
- Nenhum CRUD, formulário, lógica de negócio ou API além de branding + auth/me
```
