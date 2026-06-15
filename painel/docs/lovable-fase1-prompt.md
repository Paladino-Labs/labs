# PALADINO — PROMPT FASE 1 (colar no Lovable)

> Prompt pronto para colar. Spec completa em `painel/docs/lovable-fase1-brief.md`.

---

```
Você é arquiteto de frontend sênior construindo o Paladino —
plataforma SaaS multi-tenant para gestão de negócios de serviço
(barbearias no piloto).

Stack: Next.js 15 (App Router) · TypeScript · shadcn/ui · Tailwind
· Lucide icons · Cormorant Garamond (display) · Inter (corpo)

━━━ ESCOPO DESTA SESSÃO: FASE 1 (operação diária) ━━━
Prototipar 9 telas. Foco em LAYOUT, ESTADOS, INTERAÇÕES e FLUXOS.
DADOS MOCKADOS — ainda SEM integração real de API.
O SHELL DA FASE 0 JÁ EXISTE: NÃO reimplementar sidebar, header,
layout, providers, branding nem tokens. Produzir apenas o conteúdo
das páginas (o que vai dentro de <main>).

━━━ TOKENS E CONVENÇÕES (já em globals.css) ━━━
Nunca hardcodar cores. Tokens semânticos sempre:
  bg-background #faf9f5 · bg-primary/bg-sidebar #16242c (petrol)
  accent (text-sidebar-primary) #c79a5a (brass)
  bg-card · border-border · text-muted-foreground — nunca bg-white/text-gray-*
Tipografia: h1/h2/h3 = Cormorant Garamond; títulos de página
  font-display text-3xl tracking-wide. Corpo: Inter.
Ícones: Lucide size=16 strokeWidth=1.5 — nunca emojis.
Moeda: formatBRL() (a API devolve string decimal "38.50" → converter p/ número).
Datas: formatDateTime() com timeZone BR.
Campo ausente na resposta → fallback "Em breve"
  (text-xs text-muted-foreground opacity-50), nunca mockar no código real.

━━━ DOIS FSMs — NÃO CONFUNDIR ━━━
Appointment: SCHEDULED(verde) · IN_PROGRESS(âmbar) · COMPLETED(neutro)
  · CANCELLED/NO_SHOW/FAILED(vermelho) · DRAFT(neutro).
  NÃO existe CONFIRMED em agendamento (estado ativo = SCHEDULED).
Payment: PENDING(âmbar) → CONFIRMED(verde) → REFUNDED(cinza).
Classificação CRM (badge): NOVO · FREQUENTE · VIP(brass) · EM_RISCO(âmbar)
  · RECUPERADO(verde) · REGULAR(neutro).

━━━ AS 9 TELAS ━━━

BLOCO A — OPERAÇÕES
1) /appointments/[id] — Detalhe de operação (OWNER/ADMIN/OPERATOR; PROF scope)
   Layout 2 colunas. Principal: Badge FSM + cliente + horário; cards
   Serviço(s) (Table: nome, duração, preço), Profissional, Valores
   (subtotal/desconto/total). Aside: card Sinal/Depósito + histórico de
   transições.
   DEPOSIT: se houver sinal → "Sinal pago R$X" (badge status) + "Saldo
   pendente R$ (total − sinal)". Sem sinal → ocultar card.
   Ações (Dialog de confirmação + toast):
     Concluir · Cancelar (campo reason opcional) · Remarcar (novo horário).
     Iniciar e Marcar NO_SHOW → botões DISABLED + Tooltip "Em breve"
     (sem endpoint no Estágio 0 — não prometer wiring).

BLOCO B — CLIENTES / CRM
2) /customers — Lista (OWNER/ADMIN/OPERATOR/PROF view)
   Table paginada. Colunas: Nome · Telefone · Última visita("Em breve")
   · Classificação(Badge) · Ticket médio("Em breve") · Cotas ativas(badge)
   · ação(abrir ficha). Filtros: classificação, sem visita há X dias.
   Estados: vazio/loading(skeleton)/erro/dados.
3) /customers/[id] — Ficha (Tabs) (scope)
   Header: avatar(iniciais) + nome + telefone + Badge classificação.
   Aba Resumo: dados + classificação + insights heurísticos (churn risk,
     sugestões remarcar/pacote/produto — ocultar card de insight ausente).
   Aba Histórico: Table de appointments passados (status badge), paginado.
   Aba Cotas: cards (tipo, remaining/total, validade ou "sem validade",
     status) + botão "Conceder cota" (modal) + "Revogar" por cota.
     Modal conceder: total_cotas(>0) · validade(opcional) · reason(OBRIGATÓRIO).
   Aba Consentimentos: lista de tipos (COMMUNICATION/MARKETING/
     DATA_PROCESSING) com estado GRANTED/REVOKED + ações grant/revoke.
4) /crm — Dashboard CRM (OWNER/ADMIN)
   4 cards KPI: Em risco · Novos no mês · VIP · Recuperados na semana.
   Lista Top 10 em risco (dias sem visita desc, link p/ ficha).
   Lista Sugestões de ação (remarcar / enviar pacote).
   Vazio → "Tudo em dia".

BLOCO C — INBOX E FILA
5) /inbox — Conversas escaladas (OWNER/ADMIN/OPERATOR)
   Master-detail. Lista: cliente/telefone · última msg truncada · tempo
   esperando (de escalated_at) · Badge "Em atendimento". Tabs
   Escaladas | Resolvidas (Badge "Resolvida").
   Detalhe: thread de bolhas por sender_type (CLIENT esquerda; BOT/AGENT
   direita c/ rótulo) + campo reply (Textarea + enviar).
   Ações: Enviar resposta (toast; erro se conversa não está em atendimento
   humano → "Conversa não está em atendimento humano"); Resolver conversa
   (Dialog → toast "Bot reassumiu o atendimento", move p/ Resolvidas).
   Vazio → "Nenhuma conversa em atendimento".
6) /fila — Fila de espera (Entradas OWNER/ADMIN/OPERATOR; Config OWNER/ADMIN)
   Tabs Entradas | Configuração.
   Entradas: Table — cliente · escopo (badge SERVICE/PROFESSIONAL/PRODUCT
   + alvo) · prioridade · tempo na fila · status · ações. Filtros status/escopo.
     Ação Remover (Dialog → toast). Notificar manualmente → DISABLED +
     Tooltip "Em breve" (sem endpoint).
   Configuração: Switch enabled · Select priority_mode (FIFO/prioridade)
   · Input notification_window_hours · Salvar (toast).
   Vazio → "Fila vazia".

BLOCO D — PAGAMENTOS
7) /financeiro/pagamentos — Lista (OWNER/ADMIN/OPERATOR)
   (consolida /payments — só existe /financeiro/pagamentos)
   Table. Colunas: Data · Cliente · Valor(formatBRL net) · Método(label
   do glossário) · Status(Badge Payment) · ação. Filtros client-side:
   status, método, período (date range). Paginação client-side.
   Ação rápida Confirmar (só PENDING) → Dialog → toast (+ banner de aviso
   de taxa não configurada, se houver). Linha → detalhe.
8) /financeiro/pagamentos/[id] — Detalhe (OWNER/ADMIN ações; OPERATOR view)
   Cards: Valores (bruto/desconto/líquido/taxa) · Origem (método/submétodo,
   provider, appointment vinculado→link, cupom) · Datas (criado/pago/estornado).
   Ações (Dialog + toast):
     Confirmar (se PENDING).
     Estornar (se CONFIRMED): Select RefundReason
       (SERVICE_FAILURE/REGISTRATION_ERROR/DEADLINE_POLICY/OTHER, OBRIGATÓRIO)
       + checkbox force_local SÓ p/ OWNER.
     Aplicar desconto manual (OWNER/ADMIN, só PENDING): valor(>0) +
       reason(OBRIGATÓRIO).
9) /settings/financial — aba Deposit Policies (OWNER/ADMIN)
   Table de políticas: Serviço (nome ou "Global") · Tipo
   (FIXED_AMOUNT/PERCENTAGE) · Valor (R$ ou %) · Janela cancelamento (h)
   · Reter em NO_SHOW (badge sim/não). Botão "Nova política".
   Form (Dialog): serviço(ou Global) · tipo · valor · h janela ·
   Switch refund_on_tenant_fault · Switch retain_on_no_show ·
   Switch commission_on_retained_deposit.
   Criar/editar/excluir(Dialog) → toast. Vazio → "Nenhuma política".

━━━ PADRÕES DE UX (todas as telas) ━━━
- Ações destrutivas/sensíveis sempre em Dialog de confirmação.
- Toast success/error após toda ação.
- Reason obrigatório: manual-discount, grant-cota, refund.
- Tabelas com paginação (server só em /appointments; resto client-side).
- Monetário sempre formatBRL(); datas sempre formatDateTime() BR.
- Ação sem endpoint no Estágio 0 (Iniciar, NO_SHOW, Notificar manual) →
  botão disabled + Tooltip "Em breve".
- RBAC visível: ações OWNER-only ocultas/desabilitadas p/ ADMIN/OPERATOR.
- Estados obrigatórios por tela: vazio · loading(Skeleton) · erro(retry) · dados.

━━━ REGRAS ABSOLUTAS ━━━
- NÃO reimplementar sidebar/header/layout/branding/tokens (Fase 0 já existe).
- Tokens semânticos nunca hardcoded; ícones Lucide 16/1.5; nunca emojis.
- Dados mockados; sem chamadas reais de API.
- NÃO incluir telas fora do escopo (catálogo, financeiro profundo, estoque,
  promoções, pacotes, NPS, owner, portal).
- Componentes shadcn: Table, Tabs, Badge, Dialog, Card, Select, Input,
  Textarea, Switch, Tooltip, Avatar, ScrollArea, Pagination, Skeleton.
```

━━━ NOTA DE IMPLEMENTAÇÃO ━━━
Este protótipo está em TanStack Start.
O Claude Code traduzirá para Next.js App Router (painel/).
Consultar: https://github.com/Silva-fin/barberflow-system.git
