PALADINO — FASE 5C · PAINEL OWNER (PLATFORM_OWNER)

Prompt paste-ready para o Lovable. Protótipo com **dados mockados
determinísticos**. O wiring real (`apiFetch`) é feito depois pelo Claude Code.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTO — O QUARTO SHELL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

O produto Paladino tem QUATRO shells de produto independentes. Você vai construir
o quarto — o **Painel Owner** — sem tocar nos outros três:

  1. Painel do Tenant  — operador da barbearia (sidebar petrol + header)
  2. Superfícies públicas — sem login (link de agendamento, NPS)
  3. Portal do Cliente — cliente final (nav própria, mobile-first)
  4. **Painel Owner**  ← VOCÊ ESTÁ AQUI

O **Painel Owner** é a área exclusiva do **PLATFORM_OWNER** — o operador da
plataforma Paladino, que enxerga TODOS os tenants e opera acima deles. É
**completamente separado** dos outros três shells:
  • SEM sidebar/header/branding do tenant. Sidebar PRÓPRIA ("Plataforma").
  • PLATFORM_OWNER é o ÚNICO role que acessa. Qualquer outro → redireciona/403.
  • Desktop-first (ferramenta interna), tabelas densas.

São **7 telas**. Nada além delas.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGRAS DE OURO (NÃO QUEBRAR)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. PLATFORM_OWNER é o único role. Shell isolado do tenant/portal/públicas.

2. BANNER DE IMPERSONATION — persistente, NUNCA dismissável. Enquanto houver uma
   sessão de impersonation ativa, uma faixa fixa aparece no TOPO DE QUALQUER TELA
   do owner:
     "Acessando como PLATFORM_OWNER em [tenant] · Modo leitura · Expira em HH:MM · [Encerrar]"
   NÃO existe botão "X"/fechar. Some só ao Encerrar (revoga) ou expirar (countdown→0).

3. CREDENCIAIS MASCARADAS — integrações exibidas APENAS como status de conexão
   (Conectado / Não conectado). NUNCA mostrar segredos. (O backend só devolve um
   booleano por integração — ver O2.)

4. REPLAY — sempre com campo de MOTIVO obrigatório. E o botão de replay nasce
   DESABILITADO para os módulos financeiros: PaymentsEngine, CommissionEngine,
   FinancialCore (com tooltip explicando). (Recurso mockado — ver Q1.)

5. AUDIT — paginado, APPEND-ONLY, somente leitura. Sem editar/excluir/criar. Sem
   export. company_id sempre visível em cada linha.

6. Dados MOCKADOS e DETERMINÍSTICOS. Para CADA tela, prover mocks que cubram os 4
   estados: carregando · vazio · erro · com dados.

7. Ações destrutivas usam Dialog (o projeto NÃO tem AlertDialog). NÃO existem
   RadioGroup nem Progress no projeto.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AS 7 TELAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

As rotas abaixo mapeiam para /owner/* (ver nota de tradução no fim).

──────────────────────────────────────────────────────────────────────
O1 · Tenants — lista                                  rota: /owner/tenants
──────────────────────────────────────────────────────────────────────
PageHeader "Tenants". Filtro de status (Select: Todos · Período de teste · Ativo ·
Suspenso · Cancelado) + busca por nome (Input).

Table, colunas: Nome · Slug · Status (Badge colorido) · Criado em · Ativo (sim/não).
Linha clicável → O2.

Status enum (4) e cores (via tokens semânticos, nunca hardcoded):
  TRIAL → "Período de teste" (âmbar/secondary)
  ACTIVE → "Ativo" (verde/primary)
  SUSPENDED → "Suspenso" (vermelho/destructive)
  CHURNED → "Cancelado" (cinza/muted)

Ações por linha:
  • Suspender (quando ACTIVE/TRIAL): Dialog com Textarea MOTIVO OBRIGATÓRIO.
  • Reativar (quando SUSPENDED): Dialog de confirmação.
Resultado inline (a linha reflete o novo status). NÃO incluir "Criar tenant".

NÃO incluir colunas "último acesso" nem "volume" aqui (não vêm da lista).
Estados: Skeleton de linhas · EmptyState (com/sem filtro) · ErrorState com retry.

──────────────────────────────────────────────────────────────────────
O2 · Tenant — detalhe + saúde                    rota: /owner/tenants/[id]
──────────────────────────────────────────────────────────────────────
PageHeader com nome + Badge de status + ações Suspender/Reativar (mesmo Dialog).
Duas seções:

  DADOS: nome, slug, status, ativo, criado em.

  SAÚDE (KPIs em cards): usuários · clientes · Agendamentos (30d) · Último acesso ·
  Falhas de comunicação (7d). E INTEGRAÇÕES como STATUS DE CONEXÃO:
    Asaas:    Badge "Conectado"/"Não conectado"
    WhatsApp: Badge "Conectado"/"Não conectado"
  ⚠️ NUNCA mostrar credenciais. O backend só devolve um booleano por integração.
  (Se quiser ILUSTRAR o padrão de mascaramento, pode mostrar "•••• 4242 · Conectado"
   como MOCK, mas deixe claro que é mock e que o real só traz o status.)

  Sinais de churn = leitura visual de (agendamentos 30d baixos + último acesso antigo
  + falhas de comunicação altas). Sem score numérico.

  Link "Feature flags →" leva a P1.
Estados: Skeleton por seção · ErrorState na seção de saúde (dados básicos podem
carregar mesmo se a saúde falhar).

──────────────────────────────────────────────────────────────────────
P1 · Feature flags por tenant            rota: /owner/tenants/[id]/flags
──────────────────────────────────────────────────────────────────────
PageHeader "Feature flags — [tenant]".

⚠️ Flags NÃO são um catálogo fixo. É um DICIONÁRIO LIVRE chave→valor. Renderize
GENERICAMENTE iterando sobre as chaves do mock:
  • valor booleano → Switch (toggle).
  • valor objeto/string/número → mostra o valor (code/Badge) + botão "Editar" →
    Dialog com Textarea JSON.
Ao alterar, reflita o dicionário completo.

Mock de exemplo (chaves reais do backend):
  { "use_communication_service": true, "allows_subscription_pause": false,
    "allows_subscription_cancel": true }
Estados: Skeleton · EmptyState "Nenhuma flag configurada" · ErrorState
"Config não encontrada" (404). Erro de toggle → reverte + mensagem inline.

──────────────────────────────────────────────────────────────────────
P2 · Impersonation                              rota: /owner/impersonation
──────────────────────────────────────────────────────────────────────
Duas partes.

CRIAR GRANT (Card):
  • Select de tenant (lista de tenants).
  • Textarea MOTIVO OBRIGATÓRIO.
  • Select de MODO: "Somente leitura" (READ_ONLY, default) · "Elevado" (ELEVATED).
  • Input numérico DURAÇÃO em minutos (default 30; faixa 1–480).
  • Validação na UI: ELEVATED exige motivo ≥ 20 caracteres (mostre erro inline).
  • Botão "Criar acesso" → ao sucesso, INICIA a sessão de impersonation:
    grava um estado mock de "grant ativo" → DISPARA O BANNER (regra de ouro 2).

GRANTS ATIVOS (Table): tenant · modo · motivo · expira em · criado em ·
  ação "Encerrar" (Dialog de confirmação → revoga + limpa o banner).

BANNER (regra de ouro 2): renderizado no layout do owner, no topo de TODAS as telas
enquanto houver grant ativo. Texto:
  "Acessando como PLATFORM_OWNER em [tenant] · Modo leitura · Expira em HH:MM · [Encerrar]"
Countdown a partir de expires_at. Sem botão de fechar. Cor de destaque, alto contraste.
Estados: Skeleton (tabela) · EmptyState "Nenhum acesso ativo" · ErrorState. Erro de
criação (ELEVATED/duração) → inline no form.

──────────────────────────────────────────────────────────────────────
Q1 · Sistema — reenvio + dead-letter            rota: /owner/sistema
──────────────────────────────────────────────────────────────────────
PARTE REAL — Reenviar comunicação (Card):
  Input log_id (UUID) + Textarea MOTIVO OBRIGATÓRIO + botão "Reenviar".
  Resultado inline (novo log + status). NÃO há listagem de logs — cola-se o log_id.

PARTE MOCKADA — Monitor de dead-letter / workers (apenas layout; SEM backend):
  Renderize como EmptyState "Em breve" OU, para validar layout, uma Table mock:
    colunas: módulo · evento · erro · ação Replay.
  REGRAS no Replay (regra de ouro 4):
    • Botão Replay DESABILITADO (com Tooltip) para módulos:
      PaymentsEngine, CommissionEngine, FinancialCore.
    • Nos demais módulos, Replay abre Dialog com Textarea MOTIVO OBRIGATÓRIO.
  Marque visualmente esta seção como "Em breve / mock" (não é endpoint real).

──────────────────────────────────────────────────────────────────────
Q2 · Configurações globais da plataforma        rota: /owner/settings
──────────────────────────────────────────────────────────────────────
PageHeader "Configurações da plataforma".
⚠️ Settings é um DICIONÁRIO LIVRE chave→valor (igual às flags). Renderize
genericamente: Table/lista chave→valor; "Editar" → Dialog com Textarea JSON.
Resultado inline. (Sem catálogo fixo.)
Mock de exemplo:
  { "default_trial_days": 14, "support_email": "suporte@paladino.com",
    "maintenance_mode": false }
Estados: Skeleton · EmptyState "Nenhuma configuração" · ErrorState.

──────────────────────────────────────────────────────────────────────
R1 · Audit cross-tenant                          rota: /owner/audit
──────────────────────────────────────────────────────────────────────
PageHeader "Auditoria". Tabs: "Tudo" · "Impersonation" (a 2ª é só um preset de
filtro — registros de ação impersonated_request).

Filtros: tenant (company_id) · ator (actor_id) · ação (action) · período (de/até).
Table, colunas: company_id (SEMPRE visível) · ator (actor_id + actor_role) · ação ·
resource_type · resource_id · motivo · ocorrido em. Linha → expandir/Dialog com
before_snapshot/after_snapshot (JSON).

Paginação com envelope { total, page, limit, items } — controles de página + limite.

⚠️ APPEND-ONLY: nenhuma ação de editar/excluir/criar. SEM botão de export.
SEM coluna IP (o backend não devolve). Apenas ler, filtrar, paginar, expandir.
Estados: Skeleton de linhas · EmptyState · ErrorState.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTRATOS DE API (para shape dos mocks — NÃO chamar no protótipo)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Todos sob /platform/*, exigem PLATFORM_OWNER.

GET  /platform/tenants?status=&created_after=&search_name=
     → { items: [{ id, name, slug, status, active, created_at }], total }   (sem paginação)
GET  /platform/tenants/{id}
     → { id, name, slug, status, active, created_at }
GET  /platform/tenants/{id}/health
     → { company_id, status, total_users, total_customers, appointments_30d,
         last_activity_at, communication_failures_7d,
         asaas_connected: bool, whatsapp_connected: bool }
PATCH /platform/tenants/{id}/status   body { status, reason? }
     → company row.  status ∈ TRIAL|ACTIVE|SUSPENDED|CHURNED.  reason obrigatório p/ SUSPENDED.

GET  /platform/impersonation/grants
     → { items: [{ grant_id, company_id, mode, reason, expires_at, revoked_at, created_at }], total }
POST /platform/impersonation/grants   body { company_id, mode="READ_ONLY", reason, duration_minutes=30 }
     → 201 { grant_id, expires_at, mode }.  mode ∈ READ_ONLY|ELEVATED; ELEVATED reason ≥ 20 chars; duração 1–480.
DELETE /platform/impersonation/grants/{grant_id}   → grant row (revoked_at setado)
     ⚠️ NÃO existem /impersonation/start nem /end. Impersonation = grant + header X-Impersonate-Grant.

GET  /platform/tenants/{id}/flags     → { flags: { …dict livre… } }
PUT  /platform/tenants/{id}/flags/{key}   body { value }   → { flags: { …completo… } }

GET  /platform/settings               → { settings: { key: value, … } }
PUT  /platform/settings/{key}         body { value }   → { key, value }

GET  /platform/audit?company_id=&actor_id=&action=&date_from=&date_to=&page=1&limit=50
     → { total, page, limit, items: [{ audit_id, company_id, actor_id, actor_role,
          action, resource_type, resource_id, reason, before_snapshot, after_snapshot, occurred_at }] }
     ⚠️ sem campo ip; sem endpoint de export; impersonation = filtro action=impersonated_request.

POST /platform/communications/{log_id}/redispatch   body { reason }
     → { new_log_id, status, original_log_id }.  Só logs FAILED. Sem GET de listagem.

⚠️ NÃO existem: POST /platform/tenants (criar tenant), /platform/system,
   /platform/workers, /platform/dead-letter, replay de eventos, export de audit.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PADRÕES VISUAIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Reaproveitar o sistema visual do painel: tokens semânticos (bg-card, border-border,
  text-muted-foreground, bg-primary — NUNCA cores hardcoded tipo bg-white/text-gray),
  font-display (Cormorant) em títulos e wordmark, ícones Lucide (16px, strokeWidth 1.5).
• Componentes shadcn existentes: Card, Table, Badge, Dialog, Select, Switch, Tabs,
  Tooltip, Input, Label, Textarea, Button, Skeleton + EmptyState/ErrorState/PageHeader.
  NÃO existem: AlertDialog, RadioGroup, Progress.
• Sidebar própria do owner ("Plataforma"): Tenants · Impersonation · Sistema ·
  Configurações · Auditoria. Footer com identidade "Paladino" + sair.
• Dialog (não AlertDialog) para confirmações destrutivas.
• Motivo obrigatório: suspender, redispatch, criar grant (ELEVATED ≥ 20 chars), replay.
• Resultado inline (não toast) para consequências permanentes.
• Glossários: TENANT_STATUS_LABELS, IMPERSONATION_MODE_LABELS.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REFERÊNCIA VISUAL — barberflow-system
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

O projeto de referência (barberflow-system) tem rotas owner.tsx/owner.index.tsx,
porém são apenas um STUB "Em construção" (guard + placeholder) — NÃO há telas reais
de owner para espelhar. Desenhe o Painel Owner DO ZERO, herdando o vocabulário
visual do painel (cards densos, font-display, tokens). Sem screenshots aprovadas.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTA DE TRADUÇÃO — TanStack (protótipo) → Next.js (Claude Code)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

O protótipo é agnóstico de path. No projeto real (Next.js App Router), as telas
serão traduzidas assim:

  • SEGMENTO LITERAL: route groups "(...)" SOMEM da URL no Next.js. Para as URLs
    ficarem em /owner/*, as páginas vivem sob um segmento LITERAL "owner" dentro do
    grupo (owner):  app/(owner)/owner/tenants/page.tsx → /owner/tenants  (etc).
    (Mesma regra que o Portal usou: app/(portal)/portal/...)

  • SHELL: app/(owner)/layout.tsx JÁ EXISTE (guard PLATFORM_OWNER). A sidebar do
    owner + o ImpersonationBanner entram num layout aninhado
    app/(owner)/owner/layout.tsx (não no guard externo).

  • API: NÃO criar helper novo. O PLATFORM_OWNER autentica pelo mesmo /auth/login e
    usa o JWT de tenant (company_id=null) → reusa apiFetch / api.* (lib/api.ts).
    NÃO importar Sidebar/Header/BrandingProvider do tenant.

  • IMPERSONATION header: no real, entrar em impersonation injeta
    X-Impersonate-Grant: {grant_id} nas chamadas (wiring futuro). No protótipo o
    banner é só visual/mock.

Tudo no protótipo é mockado; estas notas são para o Claude Code, não para você.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENTREGÁVEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

7 telas (O1, O2, P1, P2, Q1, Q2, R1) + sidebar do owner + banner de impersonation
persistente, todas com mocks determinísticos para carregando/vazio/erro/dados.
Shell completamente separado dos outros três. PLATFORM_OWNER como único acesso.
