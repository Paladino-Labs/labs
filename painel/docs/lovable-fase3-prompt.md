# PALADINO — PROMPT FASE 3 (colar no Lovable)

> Prompt pronto para colar. Spec completa em `painel/docs/lovable-fase3-brief.md`.

---

```
Você é arquiteto de frontend sênior construindo o Paladino —
plataforma SaaS multi-tenant para gestão de negócios de serviço
(barbearias no piloto).

Stack: Next.js 15 (App Router) · TypeScript · shadcn/ui · Tailwind
· Lucide icons · Cormorant Garamond (display) · Inter (corpo) · Recharts

━━━ ESCOPO DESTA SESSÃO: FASE 3 (Financeiro profundo) ━━━
Prototipar 13 telas/superfícies do FINANCEIRO PROFUNDO. Foco em LAYOUT,
ESTADOS, INTERAÇÕES e FLUXOS. DADOS MOCKADOS — ainda SEM integração real.
O SHELL DA FASE 0 e os COMPONENTES DAS FASES 1/2 JÁ EXISTEM: NÃO
reimplementar sidebar, header, layout, providers, branding, tokens,
FsmBadge, ActiveBadge, PageHeader, EmptyState, ErrorState,
CustomerAutocomplete, DateTimePicker, formatBRLFromDecimal nem sonner/toast.
Produzir apenas o conteúdo das páginas (dentro de <main>).
O grupo FINANCEIRO da sidebar já existe — estas rotas preenchem os
submenus hoje marcados "Em breve".

━━━ REGRA DE OURO: ZERO CÁLCULO FINANCEIRO NO CLIENTE ━━━
Saldo (balance), divergência (discrepancy), custo médio (avg_cost),
totais do DRE (*_total, resultado_bruto, resultado_liquido), paid_amount
do payable, total_amount do pedido — TUDO vem PRONTO da API. O cliente
só FORMATA e EXIBE. Nunca somar, subtrair ou recalcular valor monetário.
TODO valor monetário da API é STRING DECIMAL ("38.50") → formatBRLFromDecimal().

━━━ TOKENS E CONVENÇÕES (já em globals.css) ━━━
Nunca hardcodar cores. Tokens semânticos sempre:
  bg-background #faf9f5 · bg-primary/bg-sidebar #16242c (petrol)
  accent (text-sidebar-primary) #c79a5a (brass)
  bg-card · border-border · text-muted-foreground · text-success ·
  text-destructive — nunca bg-white/text-gray-*
Tipografia: h1/h2/h3 = Cormorant Garamond; título de página
  font-display text-3xl tracking-wide. Corpo: Inter.
Ícones: Lucide size=16 strokeWidth=1.5 — nunca emojis. Sugestões:
  Receipt(despesas) Package/Boxes(estoque) Truck(fornecedores)
  ClipboardList(payables) BarChart3(DRE) Wallet/Landmark(contas)
  ArrowLeftRight(transferências) Scale(conciliação) Calculator(caixa)
  FileSpreadsheet/Upload(extrato).
Datas: formatDateTime() BR; campos date puros (due_date, occurred_at do
  extrato) = data curta sem hora.
Campo ausente (só vem id, não nome) → compor via lista ou fallback
  "Em breve" (text-xs text-muted-foreground opacity-50). Nunca mockar no real.

━━━ REFERÊNCIAS VISUAIS ━━━
NÃO há screenshots aprovadas para esta fase (a pasta cobre só Fases 0–2),
e o protótipo barberflow-system NÃO tem rotas de financeiro profundo.
Logo: desenhar do ZERO herdando o vocabulário visual JÁ consolidado nas
Fases 1/2 (mesma régua de PageHeader, Table, Dialog/Sheet, FsmBadge,
filtros client-side, KPIs em Card, gráficos Recharts com tokens --chart-*).
O financeiro/page.tsx atual (KPI strip + AreaChart + cards) é o molde de
layout para o DRE e a Conciliação.

━━━ FSMs NOVOS DESTA FASE (adicionar a components/FsmBadge.tsx) ━━━
Valores EXATOS do backend — não inventar estados. Reusar EMERALD/AMBER/
DESTRUCTIVE/NEUTRAL já no arquivo (+SKY se quiser).
Expense (ExpenseBadge): PENDENTE=Pendente(âmbar) · PAGA=Paga(verde) ·
  CANCELLED=Cancelada(neutro)  ⚠️ a chave é CANCELLED (inglês), não CANCELADA.
Payable (PayableBadge): OPEN=Em aberto(âmbar) · PARTIALLY_PAID=Parcial(sky)
  · PAID=Paga(verde) · CANCELLED=Cancelada(neutro).
Installment (InstallmentBadge): OPEN=Em aberto(âmbar) · PAID=Paga(verde) ·
  CANCELLED=Cancelada(neutro).
Reconciliation (ReconciliationBadge): OPEN=Aberta(âmbar) · CLOSED=Fechada(verde).
Statement (StatementBadge): PENDING=Pendente(âmbar) · MATCHED=Conciliado(verde)
  · DISMISSED=Dispensado(neutro).
Transfer (TransferBadge): REQUESTED=Solicitada(âmbar) · COMPLETED=Concluída(verde)
  · FAILED=Falhou(vermelho).
SupplierOrder = sempre RECEIVED (badge verde "Recebido", sem FSM).
Account.status=ACTIVE / Supplier.active / StockProduct.active → ActiveBadge existente.

Glossários novos em lib/constants.ts (fonte única):
  EXPENSE_STATUS · PAYABLE_STATUS · INSTALLMENT_STATUS · RECONCILIATION_STATUS
  · STATEMENT_STATUS · TRANSFER_STATUS (labels acima)
  STOCK_MOVEMENT_TYPE: ENTRADA=Entrada · VENDA=Venda · USO_INTERNO=Uso interno
    · PERDA=Perda · AJUSTE=Ajuste
  ACCOUNT_TYPE: CAIXA=Caixa · ACQUIRER=Adquirente · BANK=Banco · ESCROW=Conta garantia
  MOVEMENT_TYPE: INFLOW=Entrada · OUTFLOW=Saída · TRANSFER_IN=Transf. recebida
    · TRANSFER_OUT=Transf. enviada
  ENTRY_TYPE: RECEITA · CUSTO · DESPESA · TAXA · COMISSAO=Comissão · ESTORNO · AJUSTE
  CLOSING_METHOD: CASH_AT_CREATION=À vista · INSTALLMENTS=Parcelado
  CASH_COUNT_RESOLUTION: ADJUSTED=Com ajuste · NO_ADJUSTMENT=Sem ajuste
  ENTRY_CATEGORY: mapa categoria→label (ver brief §5; ex.: ALUGUEL=Aluguel,
    SALARIO=Salário, PRODUTO_VENDIDO=Produto vendido, ...). Categorias DESPESA
    (ALUGUEL/UTILITIES/MARKETING/SOFTWARE/CONTABILIDADE/LIMPEZA/MANUTENCAO/
    SALARIO/SERVICOS_PJ/ALIMENTACAO_COPA/EQUIPAMENTOS/TAXAS_BANCARIAS/
    TREINAMENTO/DESPESA_OUTROS) alimentam o Select de categoria de Despesa.

━━━ AS 13 TELAS ━━━

BLOCO I — DESPESAS
1) /despesas — Lista + lançar + pagar/cancelar (OWNER/ADMIN; OPERATOR view)
   Filtros: status · category(Select DESPESA) · due_date_from/to · supplier_id.
   Colunas: Descrição · Categoria(ENTRY_CATEGORY) · Valor(amount) ·
   Vencimento(due_date) · Status(ExpenseBadge) · Fornecedor(→nome ou —) ·
   Pago(paid_at/paid_amount se PAGA) · ações.
   Form criar (Dialog): descrição · valor · Select categoria(DESPESA) ·
   DateTimePicker vencimento · Select fornecedor(opcional) · Switch
   "Recorrente" → frequência + dia do mês + fim(opcional).
   Pagar (só PENDENTE): Dialog c/ Input opcional "Valor pago"
     (default=amount) → PATCH /expenses/{id}/pay.
   Cancelar (só PENDENTE): Dialog c/ Textarea motivo OBRIGATÓRIO →
     PATCH /expenses/{id}/cancel.
   Despesa-filha (parent_expense_id) = ícone recorrente, read-only.
   GET/POST /expenses/ · GET /expenses/{id}.

BLOCO J — ESTOQUE → FORNECEDORES → PAYABLES (cadeia)
2) /estoque — Lista qtd + custo médio (OWNER/ADMIN; OPERATOR view)
   GET /stock/?active_only=true → {id,name,active,stock?,stock_min_alert?,
   unit?,avg_cost?}. Colunas: Produto · Qtd(stock+unit ou "Em breve") ·
   Alerta mín · Custo médio(avg_cost) · Status(ActiveBadge) · ações.
   Badge "Estoque baixo" se stock≤stock_min_alert (só visual, ambos da API).
   Botões: "Receber pedido"(tela 3) · "Movimentações"(tela 4, filtra product_id).
3) Receber pedido (MODAL guiado, lançado de /estoque) (OWNER/ADMIN)
   Dialog: Select fornecedor(opcional) + lista editável de itens
   (Select produto + Input quantidade + Input custo unit + "Adicionar item")
   + Select fechamento(CLOSING_METHOD) → INSTALLMENTS: editor parcelas
   (amount+due_date); CASH_AT_CREATION: DateTimePicker vencimento + notas.
   POST /stock/orders/ {supplier_id?, items[{product_id,quantity,unit_cost}],
   closing_method, installments?, due_date?, notes?} → resp {order(status
   RECEIVED), payable_id, total_amount}.
   ⚠️ CADEIA: receber pedido dá ENTRADA de estoque E cria um PAYABLE
   automático. Sucesso → toast "Pedido recebido — entrada registrada e
   conta a pagar criada" + botão "Ver conta a pagar" → /payables (destaca
   payable_id). Exibir total_amount DA RESPOSTA (não somar itens).
4) /estoque/movimentacoes — Histórico (OWNER/ADMIN; OPERATOR view)
   Filtros: product_id · movement_type · date_from/to. Colunas: Data
   (occurred_at) · Produto · Tipo(STOCK_MOVEMENT_TYPE, cor por tipo) ·
   Quantidade(sinal visual) · Custo unit · Origem(source_type) · Notas.
   Form registrar (Dialog): Select produto · Select tipo
   (APENAS VENDA/USO_INTERNO/PERDA/AJUSTE — ENTRADA fora, nota "só via
   Receber pedido") · Input quantidade · Textarea notas
   (OBRIGATÓRIO quando tipo=AJUSTE).
   GET/POST /stock/movements/.
5) /fornecedores — CRUD (OWNER/ADMIN; OPERATOR view)
   GET /suppliers/?active=true. Colunas: Nome · Contato · Documento(CNPJ/CPF)
   · Status(ActiveBadge) · Criado · ações.
   Form (Dialog): name* · contact? · document?.
   POST /suppliers/ · PATCH /suppliers/{id} · DELETE /suppliers/{id}
   (retorna SupplierResponse = DESATIVAÇÃO lógica → "Desativar", reflete
   active=false, NÃO remove a linha; Dialog de confirmação).
6) /payables — Contas a pagar + parcelas + pagar (OWNER/ADMIN; OPERATOR view)
   Filtros: status · supplier_id · due_date_from/to. Colunas: Descrição ·
   Fornecedor(→nome) · Total(total_amount) · Pago(paid_amount) ·
   Status(PayableBadge) · Vencimento · Fechamento(CLOSING_METHOD) ·
   Origem(ícone se source_type=SUPPLIER_ORDER) · ações.
   Form criar (Dialog): descrição · valor total · Select fornecedor? ·
   DateTimePicker vencimento? · Select fechamento → INSTALLMENTS: editor parcelas.
   Cancelar: Dialog c/ motivo OBRIGATÓRIO → PATCH /payables/{id}/cancel
   (esconder se PAID/CANCELLED).
7) Parcelas (Sheet/Dialog "Parcelas" de uma linha de /payables)
   GET /payables/{id}/installments → Table: Nº(installment_number) · Valor ·
   Vencimento · Status(InstallmentBadge) · Pago em(paid_at) · ação Pagar(só OPEN).
   Pagar parcela (Dialog): Select conta(account_id, opcional, contas da tela 9)
   + payment_id(opcional) → PATCH /payables/{id}/installments/{iid}/pay.
   Pagar última → payable PAID; parcial → PARTIALLY_PAID (status DA RESPOSTA).

BLOCO K — GESTÃO FINANCEIRA
8) /financeiro/dre — DRE por período (OWNER/ADMIN)
   Seletor de período: Mês / Trimestre / Ano / custom(2 DateTimePicker) →
   GET /financial/dre?date_from&date_to (date-TIME obrigatórios; início 00:00,
   fim 23:59). KPI strip (molde do financeiro/page.tsx): Receita total ·
   Custo total · Despesa total · Resultado líquido(verde/vermelho conforme
   sinal da string — ler, não recalcular).
   Gráfico Recharts (BarChart, tokens --chart-*): Receita × (Custo+Despesa+
   Taxa+Comissão+Estorno) × Resultado. Tabela por bucket (receita/custo/
   despesa/taxa/comissao/estorno/ajuste): linhas categoria(ENTRY_CATEGORY)→valor
   + *_total no rodapé (TUDO da API). Linha final resultado_bruto / resultado_liquido.
9) /financeiro/contas — Contas + saldos + transferências (OWNER/ADMIN)
   GET /financial/accounts → cards: Nome · Tipo(ACCOUNT_TYPE) ·
   provider/external_ref? · Saldo(GET /financial/accounts/{id}/balance →
   balance) · badge "Padrão" se is_default_inflow · ActiveBadge.
   Topo (read-only): GET /financial/settings (provedor, accounts_count).
   Form nova conta (Dialog): name · Select tipo(CAIXA/ACQUIRER/BANK/ESCROW) ·
   provider? · external_ref? · Switch is_default_inflow.
   Aba Transferências: GET /financial/transfers → Origem→Destino · Valor ·
   Status(TransferBadge) · Solicitada · Concluída/Falhou · motivo de falha.
   Transferir (tela 10).
   Aba Movimentos (opcional): GET /financial/movements?account_id= →
   Data · Tipo(MOVEMENT_TYPE) · Valor · Origem. (lista geral já existe em
   /financeiro/movimentacoes — não reconstruir).
   Ajuste manual (opcional, SENSÍVEL, Dialog c/ confirmação dupla):
   valor · RadioGroup direção(ADDS=entrada/SUBTRACTS=saída) · Select
   categoria(AJUSTE) · Select conta · Textarea motivo → POST
   /financial/manual-adjustment. SEM editar/excluir conta (não há endpoint).
10) Transferir (MODAL de /financeiro/contas) (OWNER/ADMIN)
   Dialog: Select conta origem · Select conta destino(≠origem) · Input valor
   · Textarea notas → POST /financial/transfers. 422 se contas iguais.
11) /financeiro/conciliacao — abrir/fechar + reconciliar (OWNER/ADMIN)
   Tabs "Conciliação bancária" | "Contagem de caixa".
   FLUXO SEQUENCIAL OBRIGATÓRIO:
   a) Select conta → se SEM conciliação OPEN: botão "Abrir conciliação"
      (POST /financial/reconciliation {account_id,notes?}).
   b) Com OPEN: Table GET /financial/movements/unreconciled?account_id →
      Data · Tipo · Valor · botão "Marcar conciliado"
      (POST /financial/movements/{mid}/reconcile {reconciliation_id}).
   c) "Fechar conciliação" (PUT /financial/reconciliation/{id}/close, sem body)
      — DESABILITADO + Tooltip se não houver conciliação OPEN; Dialog confirmação.
   Badge ReconciliationBadge(OPEN/CLOSED). NÃO conciliar em conciliação
   fechada (422); NÃO fechar sem aberta.
12) Contagem de caixa (Tab de /financeiro/conciliacao) (OWNER/ADMIN/OPERATOR)
   GET /financial/cash-counts → histórico: Data · Conta · Esperado
   (expected_amount) · Contado(counted_amount) · DIVERGÊNCIA(discrepancy:
   verde=0, vermelho<0, âmbar>0) · Resolução(CASH_COUNT_RESOLUTION).
   Registrar (Dialog): Select conta · Input valor contado · RadioGroup
   resolução(ADJUSTED/NO_ADJUSTMENT) · Textarea notas → POST
   /financial/cash-counts. discrepancy = counted−expected vem DA API
   (não calcular). ADJUSTED + discrepancy≠0 EXIGE notes (se 422, orientar).
13) /financeiro/extrato — Import CSV + match + dismiss (OWNER/ADMIN/OPERATOR)
   Cards de lotes: GET /financial/statement/batches → total/matched/pending/
   dismissed por batch_id.
   SEQUÊNCIA OBRIGATÓRIA do import:
   a) UPLOAD: área de drop + <input type=file accept=.csv hidden> (padrão
      /uploads/) · Select conta(account_id) · editor de column_mapping
      (mapear colunas: data* · valor* · descrição? · direção?) → montar
      JSON STRING {"date":idx|nome,"amount":idx|nome,"description"?:...,
      "direction"?:...} (date e amount OBRIGATÓRIAS).
   b) PREVIEW: ler localmente 1ªs N linhas do CSV e mostrar tabela (visual).
   c) IMPORTAR: POST /financial/statement/import (MULTIPART: file binário +
      account_id + column_mapping) com Progress/spinner; toast com
      StatementImportResponse (imported/skipped_duplicates/skipped_invalid/
      auto_matched).
   Tabela GET /financial/statement/?account_id&status&batch_id&date_from&to →
   Data(occurred_at) · Descrição · Valor · Direção(INFLOW/OUTFLOW) ·
   Status(StatementBadge) · ações.
   MATCH (só PENDING): "Ver sugestões" → GET /financial/statement/{id}/
   suggestions (MovementResponse[]) em Dialog → escolher → "Confirmar match"
   (POST /financial/statement/{id}/match {movement_id}) OU "Dispensar"
   (POST /financial/statement/{id}/dismiss {reason} motivo OBRIGATÓRIO).
   Import pode estar atrás de require_action: se 403/require_action, aviso
   "Ação não habilitada para este tenant" — não simular permissão.

━━━ UPLOAD CSV: TRATAMENTO MULTIPART (como /uploads/ da Fase 2) ━━━
É o 2º endpoint multipart do sistema. Usar FormData/api.postForm igual ao
upload de imagem de produto: anexar file(binário) + account_id(string) +
column_mapping(string JSON). Spinner/Progress durante envio; resumo no toast.
NÃO enviar JSON puro — é multipart/form-data.

━━━ CADEIA ESTOQUE → PAYABLE (documentar na UI) ━━━
Receber pedido (tela 3) cria Payable automático (payable_id na resposta).
Sempre dar caminho explícito para a conta criada (toast c/ ação "Ver conta
a pagar" → /payables). Payables com source_type=SUPPLIER_ORDER ganham
ícone "Pedido de estoque". Fluxo: Fornecedor → Receber pedido (Payable +
entrada estoque) → Pagar parcela (Movement OUTFLOW) → consumo gera Entry CUSTO.

━━━ PADRÕES DE UX (todas as telas) ━━━
- Ações destrutivas/de mudança de estado sempre em Dialog de confirmação.
- Toast (sonner) success/error após toda ação; erro do detail da API.
- Transições/ações renderizadas CONFORME o status atual — esconder inválidas.
- Conciliação é sequencial: abrir → marcar → fechar (não fechar sem abrir).
- Cash count: divergência vem da API (verde=0/vermelho<0/âmbar>0).
- Monetário sempre formatBRLFromDecimal(); datas formatDateTime() BR;
  campos date puros = data curta.
- Sem paginação no servidor → filtrar/paginar CLIENT-SIDE; filtros que
  viram query (status/datas/ids) repassados ao GET.
- Ação sem endpoint (editar/excluir conta; reabrir conciliação; editar
  payable; remover parcela; ENTRADA avulsa de estoque) → não renderizar OU
  disabled + Tooltip "Em breve". Nunca prometer wiring inexistente.
- RBAC visível: OPERATOR vê estoque/movimentos/fornecedores/payables e
  REGISTRA contagem de caixa; escrita de despesas/contas/transferências/
  DRE/conciliação é OWNER/ADMIN. A verdade é o 403 do backend.
- Estados obrigatórios por tela: vazio(EmptyState) · loading(Skeleton) ·
  erro(ErrorState retry) · dados.

━━━ REGRAS ABSOLUTAS ━━━
- NÃO reimplementar sidebar/header/layout/branding/tokens/FsmBadge/
  ActiveBadge/PageHeader/EmptyState/ErrorState/CustomerAutocomplete/
  DateTimePicker (Fases 0/1/2 já existem).
- ZERO cálculo financeiro no cliente — balance/discrepancy/avg_cost/
  *_total/resultado_*/paid_amount/total_amount vêm prontos da API.
- Tokens semânticos nunca hardcoded; ícones Lucide 16/1.5; nunca emojis.
- Dados mockados; sem chamadas reais de API.
- FSMs com valores EXATOS (Expense usa CANCELLED, não CANCELADA).
- ENTRADA de estoque só via Receber pedido (nunca em movimento avulso).
- DELETE de fornecedor = desativação (active=false), não remove linha.
- Pagamento de payable é POR PARCELA (não pelo payable inteiro).
- Import de extrato é MULTIPART; column_mapping é string JSON.
- NÃO incluir telas fora do escopo (NPS, comunicação, WhatsApp, usuários,
  módulos, branding, audit — Fase 4; portal, owner, públicas — Fase 5).
- Componentes shadcn: Table, Tabs, Sheet, Dialog, Card, Badge, Select,
  Input, Textarea, Switch, RadioGroup, Checkbox, Tooltip, Skeleton,
  Progress, Pagination, DateTimePicker (ou Input datetime-local/date).
```

━━━ NOTA DE IMPLEMENTAÇÃO ━━━
Este protótipo está em TanStack Start.
O Claude Code traduzirá para Next.js App Router (painel/).
O barberflow-system NÃO tem financeiro profundo — desenhar do zero
herdando o visual das Fases 1/2. Referência de estrutura geral:
https://github.com/Silva-fin/barberflow-system.git
