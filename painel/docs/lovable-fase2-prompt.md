# PALADINO — PROMPT FASE 2 (colar no Lovable)

> Prompt pronto para colar. Spec completa em `painel/docs/lovable-fase2-brief.md`.

---

```
Você é arquiteto de frontend sênior construindo o Paladino —
plataforma SaaS multi-tenant para gestão de negócios de serviço
(barbearias no piloto).

Stack: Next.js 15 (App Router) · TypeScript · shadcn/ui · Tailwind
· Lucide icons · Cormorant Garamond (display) · Inter (corpo)

━━━ ESCOPO DESTA SESSÃO: FASE 2 (Comercial) ━━━
Prototipar 10 telas do COMERCIAL. Foco em LAYOUT, ESTADOS,
INTERAÇÕES e FLUXOS. DADOS MOCKADOS — ainda SEM integração real.
O SHELL DA FASE 0 e os COMPONENTES DA FASE 1 JÁ EXISTEM: NÃO
reimplementar sidebar, header, layout, providers, branding, tokens,
FsmBadge, CustomerAutocomplete, formatBRLFromDecimal nem sonner/toast.
Produzir apenas o conteúdo das páginas (dentro de <main>).

━━━ TOKENS E CONVENÇÕES (já em globals.css) ━━━
Nunca hardcodar cores. Tokens semânticos sempre:
  bg-background #faf9f5 · bg-primary/bg-sidebar #16242c (petrol)
  accent (text-sidebar-primary) #c79a5a (brass)
  bg-card · border-border · text-muted-foreground — nunca bg-white/text-gray-*
Tipografia: h1/h2/h3 = Cormorant Garamond; título de página
  font-display text-3xl tracking-wide. Corpo: Inter.
Ícones: Lucide size=16 strokeWidth=1.5 — nunca emojis.
Moeda: formatBRLFromDecimal() — TODO valor monetário da API é
  STRING DECIMAL ("38.50","120.00"); nunca calcular à mão.
Datas: formatDateTime() com timeZone BR.
Campo ausente (só vem id, não nome) → compor via lista ou fallback
  "Em breve" (text-xs text-muted-foreground opacity-50). Nunca mockar no real.

━━━ FSMs NOVOS DESTA FASE (adicionar a components/FsmBadge.tsx) ━━━
NÃO confundir com Appointment/Payment (Fase 1).
PackagePurchase: PENDING_PAYMENT(âmbar) → ACTIVE(verde) → REVOKED(vermelho).
Subscription: ACTIVE(verde) ⇄ PAUSED(âmbar) · OVERDUE(âmbar/verm) ·
  SUSPENDED(verm) · CANCELLED(neutro).
Promotion: DRAFT(neutro) → ACTIVE(verde) ⇄ PAUSED(âmbar) ·
  EXPIRED(neutro) · CANCELLED(vermelho).
Coupon: ACTIVE(verde) · EXHAUSTED(neutro) · CANCELLED(vermelho).
Glossários novos em lib/constants.ts:
  DISCOUNT_TYPE: PERCENTAGE=Percentual · FIXED_AMOUNT=Valor fixo ·
    OVERRIDE_PRICE=Preço fixo · FREE_ITEM=Item grátis
  APPLICATION_MODE: AUTOMATIC=Automática · COUPON_REQUIRED=Requer cupom
  GENERATION_TYPE: BULK=Em lote · SINGLE_USE=Uso único · PER_CUSTOMER=Por cliente
  COUPON_REOPEN: NEVER_REOPEN=Não reabrir · REOPEN_ON_REFUND=Reabrir no estorno

━━━ AS 10 TELAS ━━━

BLOCO E — CATÁLOGO COMPLETO
1) /catalogo/categorias — CRUD de categorias (OWNER/ADMIN; OPERATOR view)
   Lista AGRUPADA por entity_type (serviço/produto/despesa — valores vêm
   da API), ordenada por sort_order. Colunas: Nome · Tipo · Ordem ·
   Status(Switch) · Padrão(badge se is_default) · ações.
   Form (Dialog): nome(1–255) · entity_type · sort_order · Switch is_active.
   is_default: excluir e editar nome/tipo/ordem DISABLED + Tooltip
   "Categoria padrão" (só is_active muda).

2) Variantes de serviço — Sheet "Gerenciar variantes" em /services
   (NÃO criar rota nova). Cada linha de serviço ganha ação "Variantes" que
   abre Sheet lateral c/ nome do serviço + lista + form inline.
   Itens: Nome · Preço(formatBRLFromDecimal) · Duração(duration_min min) ·
   Ordem · Status · editar/excluir. Form: nome · preço · duração · ordem.

3) /professionals/[id] — nova aba "Preços por serviço" (OWNER/ADMIN)
   ESTENDER a ficha existente (já tem horários/serviços/bloqueios).
   Table: Serviço · Preço base · Preço override · Duração override(ou "—")
   · Status · ações. Form criar: Select service_id · preço · duração(opc).
   Editar só price/duration/is_active.

4) /products — galeria de imagens no form (OWNER/ADMIN)
   ESTENDER os diálogos criar/editar de produto com uploader de galeria:
   até 5 slots em grid, drag-and-drop opc, preview por slot, remover.
   SLOT 1 = primária (única que persiste em image_url).
   SLOTS 2–5: visuais + DISABLED + badge "Em breve" (backend só guarda 1
   imagem hoje; não simular persistência múltipla). Upload multipart:
   POST /uploads/ campo file → {url}; spinner no slot; erro→toast.

BLOCO F — PACOTES
5) /pacotes — Planos de pacote (CRUD) (OWNER/ADMIN)
   Table/cards. Colunas: Nome · Serviço(nome ou "Genérico" se null) ·
   Cotas(total_cotas) · Preço · Validade(validity_days dias ou "Sem
   validade") · Status · ações Editar·Excluir·VENDER.
   Form: nome · cotas(int>0) · preço · Select serviço(+ "Genérico") ·
   validade(dias,opc) · Switch is_active(editar).
   (Modelo real: 1 service_id nullable; SEM services[] nem
    commission_on_sale_enabled.)
6) Venda de pacote — modal guiado (lançado de /pacotes) (OWNER/ADMIN/OPERATOR)
   Dialog com stepper 4 passos:
     1 Selecionar cliente (CustomerAutocomplete — já existe)
     2 Confirmar plano (resumo: nome, cotas, preço, validade)
     3 Método de pagamento (usar PAYMENT_METHOD_OPTIONS, agrupado
       Dinheiro/Pix · Crédito · Débito)
     4 Confirmar.
   Ação: POST /sell {customer_id, payment_method}.
   IMPORTANTE: a venda cria compra PENDING_PAYMENT + pagamento PENDING
   (NÃO confirma sozinha, nem CASH) → toast "Pacote vendido — pagamento
   pendente de confirmação" + link opc ao pagamento. NÃO marcar pago aqui.
7) /pacotes/compras — Histórico (read-only) (OWNER/ADMIN)
   Table. Colunas: Data · Cliente · Pacote · Valor(total_price) ·
   Status(PackagePurchaseBadge) · Pagamento(link) · "Ver cotas".
   Filtros client-side: status, cliente. Linha→detalhe (Dialog).
   "Ver cotas" → /customers/[id] (aba Cotas, Fase 1).
   SEM cancelar/estornar (não há endpoint). Cotas (saldo/validade) NÃO
   estão na compra — vivem em /customer-credits (ficha do cliente).

BLOCO G — ASSINATURAS
8) /assinaturas/planos — Planos (CRUD) (OWNER/ADMIN)
   Table/cards. Colunas: Nome · Serviço(ou "Genérico") · Cotas/ciclo ·
   Preço · Ciclo(cycle_days dias) · Rollover(badge sim/não) · Status · ações.
   Form: nome · cotas_per_cycle · preço · ciclo(dias,default 30) ·
   Switch rollover_enabled · Select serviço(opc) · Switch is_active.
   SEM DELETE → ação "Desativar" = PATCH is_active=false.
9) /assinaturas — Instâncias (OWNER/ADMIN)
   Table. Colunas: Cliente · Plano · Status(SubscriptionBadge) ·
   Próx. cobrança(next_billing_at) · Em atraso desde(overdue_since) · ações.
   Filtros client-side: status, cliente.
   Nova assinatura (Dialog): CustomerAutocomplete + Select plano +
     DateTimePicker first_billing_at(opc) → POST /subscriptions.
   Ações por status (esconder inválidas): Pausar(se ACTIVE)→PATCH /pause ·
     Retomar(se PAUSED)→PATCH /resume · Cancelar(ACTIVE/PAUSED/OVERDUE)→
     Dialog confirmação→PATCH /cancel. SEM reason (endpoints sem body).

BLOCO H — PROMOÇÕES E CUPONS
10a) /promocoes — Lista + criar + ativar/pausar/cancelar (OWNER/ADMIN)
   Table. Colunas: Nome · Tipo(discount_type) · Valor(% se PERCENTAGE;
   formatBRLFromDecimal se FIXED_AMOUNT; "—" senão) · Modo(application_mode)
   · Status(PromotionBadge) · Vigência(valid_from–valid_until) ·
   Usos(uses_count/max_uses) · ações.
   Form criar (Dialog): nome · Textarea descrição · Select discount_type ·
     discount_value(condicional ao tipo; PERCENTAGE ≤100) · Select
     application_mode · Switch cumulative · priority · DateTimePicker
     valid_from/until · max_uses · max_uses_per_customer.
     conditions = READ-ONLY (sem editor de regras).
   Ações por status (esconder inválidas): Ativar(DRAFT/PAUSED)→/activate ·
     Pausar(ACTIVE)→/pause · Cancelar(DRAFT/ACTIVE/PAUSED)→Dialog→/cancel ·
     "Cupons"→tela 10b. SEM editar/excluir (não há endpoint) → não renderizar.
10b) /promocoes/[id]/cupons — Geração em lote + lista (OWNER/ADMIN)
   Header: nome/status da promoção + "Gerar cupons" + Table.
   Colunas: Código(+copiar) · Tipo(generation_type) · Usos(uses_count/
   max_uses) · Cliente(se PER_CUSTOMER) · Validade(expires_at) ·
   Reabertura(coupon_reopen_policy) · Status(CouponBadge).
   Form gerar (Dialog) — Select generation_type → campos condicionais:
     BULK: quantity · prefix(opc) · max_uses
     SINGLE_USE: code(opc)/prefix; max_uses FIXO 1 (disabled)
     PER_CUSTOMER: CustomerAutocomplete OBRIGATÓRIO · max_uses
     comuns: DateTimePicker expires_at · Select coupon_reopen_policy
   Ação: POST /coupons → adiciona N linhas + toast "N cupons gerados".

━━━ PREVIEW DE DESCONTO (apoio, não é tela) ━━━
POST /promotions/preview alimenta o checkout (Fase 1). Sempre vem da API
(final_amount, discount_total = string decimal; coupon_valid bool).
Nunca calcular desconto no cliente. Opcional: mini-card de preview na
venda de pacote/assinatura se houver cupom.

━━━ PADRÕES DE UX (todas as telas) ━━━
- Ações destrutivas/de mudança de estado sempre em Dialog de confirmação.
- Toast (sonner) success/error após toda ação; erro do detail da API.
- Transições renderizadas CONFORME o status atual — esconder ações inválidas.
- SEM campo reason em assinatura/promoção (a API não recebe) — não inventar.
- Monetário sempre formatBRLFromDecimal(); datas sempre formatDateTime() BR.
- Sem paginação no servidor nesta fase → filtrar/paginar CLIENT-SIDE.
- Ação sem endpoint (editar/excluir promoção, cancelar compra de pacote,
  slots 2–5 de imagem, DELETE de plano) → não renderizar OU disabled +
  Tooltip "Em breve". Nunca prometer wiring inexistente.
- RBAC visível: OPERATOR só vende pacote (tela 6) e vê catálogo; escrita é
  OWNER/ADMIN. A verdade é o 403 do backend.
- Estados obrigatórios por tela: vazio · loading(Skeleton) · erro(retry) · dados.

━━━ REGRAS ABSOLUTAS ━━━
- NÃO reimplementar sidebar/header/layout/branding/tokens/FsmBadge/
  CustomerAutocomplete (Fase 0/1 já existem).
- Tokens semânticos nunca hardcoded; ícones Lucide 16/1.5; nunca emojis.
- Dados mockados; sem chamadas reais de API.
- NÃO incluir telas fora do escopo (financeiro profundo, estoque,
  fornecedores, payables, despesas, NPS, comunicação, inbox, owner, portal).
- Pacote/Plano usam 1 service_id nullable (null=genérico), nunca services[].
- Produto persiste 1 imagem (image_url); multi-imagem é "Em breve".
- Promoção é imutável após criada (só activate/pause/cancel).
- Componentes shadcn: Table, Tabs, Sheet, Dialog, Card, Badge, Select,
  Input, Textarea, Switch, RadioGroup, Tooltip, Skeleton, Pagination,
  DateTimePicker (ou Input datetime-local).
```

━━━ NOTA DE IMPLEMENTAÇÃO ━━━
Este protótipo está em TanStack Start.
O Claude Code traduzirá para Next.js App Router (painel/).
Consultar: https://github.com/Silva-fin/barberflow-system.git
