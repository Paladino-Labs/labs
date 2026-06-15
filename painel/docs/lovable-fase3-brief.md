# PALADINO — BRIEF DA FASE 3 (LOVABLE)

**Objetivo:** especificar as telas do **Financeiro profundo** do Painel do Tenant — **Despesas** (lançar/pagar/cancelar, recorrência), a **cadeia Estoque → Fornecedores → Payables** (saldo + custo médio, movimentos, receber pedido de fornecedor, CRUD de fornecedores, contas a pagar com parcelas) e a **Gestão Financeira** (DRE por período, Contas + saldos + transferências, Conciliação com cash count, Extrato bancário via import de CSV com sugestões de match). Derivado de `painel/docs/inventario-funcional.md` (§5 tabela mestre — Financeiro/Estoque; §7 fluxos 4 e 5; §9 Fase 3) e de `agendamento_engine/openapi.json` (head `e0s25f_product_extras`, 951 testes verdes). FSMs e schemas **conferidos diretamente no backend** (não inferidos).

> **Continuação das Fases 0, 1 e 2.** O *shell* (sidebar role-aware, header, branding, guards, tokens) e os componentes/utilitários já existem — ver §2. Esta fase preenche o grupo **Financeiro** da sidebar com as 13 telas/superfícies abaixo. **Dados mockados** no protótipo Lovable; a integração real é feita depois pelo Claude Code.

> **Escopo rígido:** apenas o Financeiro profundo (Blocos I–K). Nada de NPS, comunicação, WhatsApp, usuários, módulos, branding, audit (Fase 4), portal/owner/públicas (Fase 5). **Zero cálculo financeiro no cliente** — saldo, discrepância, total do DRE, custo médio: tudo vem da API (ver §6).

---

## 1. Contexto do produto (herdado das Fases 0/1/2)

Paladino é uma plataforma **SaaS multi-tenant** para gestão de negócios de serviço pessoal (barbearias no piloto — vertical-âncora do Estágio 0). Stack: **Next.js 15 (App Router) · TypeScript · shadcn/ui · TailwindCSS · Lucide icons**, **Cormorant Garamond** (display) e **Inter** (corpo). RBAC do frontend **espelha** as regras de negócio mas não é a verdade — a verdade é o backend (403 → ocultar/desabilitar). Toda **moeda** chega como **string decimal** (`"38.50"`) e é renderizada com `formatBRLFromDecimal()` — nunca `Number(x).toFixed`. Nesta fase isso é crítico: somatórios, saldos e discrepâncias **não** são recalculados no cliente; o backend já entrega `balance`, `discrepancy`, `*_total`, `paid_amount`, `avg_cost` prontos.

---

## 2. Shell e componentes existentes — **NÃO reimplementar**

Entregues nas Fases 0–2 e reaproveitados aqui:

- **Sidebar role-aware** (`components/Sidebar.tsx`) — o grupo **Financeiro** já existe (Pagamentos · Gestão Financeira · Despesas · Estoque/Fornecedores · Payables · Comissões · Extrato · Taxas). Esta fase **adiciona os submenus/rotas** desta lista que ainda apontam para "Em breve": Despesas, Estoque, Fornecedores, Payables, DRE, Contas, Conciliação, Extrato.
- **Header**, **`(dashboard)/layout.tsx`** (guard de auth + branding via CSS vars + breadcrumbs), **`useAuth()`** (`role`, `companyId`, `name`, `userId`), **design tokens** em `globals.css`.
- **`components/FsmBadge.tsx`** — já exporta `AppointmentBadge`, `PaymentBadge`, `CrmBadge` (Fase 1) e `PackagePurchaseBadge`, `SubscriptionBadge`, `PromotionBadge`, `CouponBadge` (Fase 2). **Esta fase adiciona** `ExpenseBadge`, `PayableBadge`, `InstallmentBadge`, `ReconciliationBadge`, `StatementBadge`, `TransferBadge` no mesmo arquivo e mesmo padrão (`<Badge variant="outline" className={cn("font-normal", CLASS[status])}>`). Ver §5.
- **`components/ActiveBadge.tsx`** (ativo/inativo) — reaproveitar para `Account.status=ACTIVE`, `Supplier.active`, `StockProduct.active`.
- **`components/PageHeader.tsx`**, **`components/empty-state.tsx`** (`EmptyState`), **`components/ErrorState.tsx`** — usar para os estados vazio/erro de toda tela.
- **`components/CustomerAutocomplete.tsx`** e **`components/DateTimePicker.tsx`** — reaproveitar (nesta fase há vários campos de data: `due_date`, `date_from/to`, filtros).
- **Glossários** (`lib/constants.ts`) — `ROLE_LABELS`, `PAYMENT_METHOD_LABELS`, `PAYMENT_METHOD_OPTIONS`, `FEE_SOURCE_LABELS`. **Esta fase adiciona** os glossários de enum desta fase (ver §5) — `constants.ts` é a fonte única.
- **Utils** — **`formatBRLFromDecimal()`** (string decimal → BRL, trata null/undefined) e `formatDateTime()` em `lib/utils.ts`. `formatBRL(number)` também existe para somatórios já numéricos vindos de gráficos.
- **Upload existente** — `services/page.tsx` / `products/page.tsx` têm o padrão `api.postForm<{ url }>("/uploads/", fd)` com `<input type="file" hidden>`, spinner e toast. O **import de extrato (K4)** é o **segundo** endpoint multipart do sistema e reaproveita esse padrão (campo binário + campos de texto). Ver §3 K4 e §5.
- **Recharts já instalado** — `financeiro/page.tsx` já usa `AreaChart`/`BarChart` com tokens `var(--chart-1..5)`. O **DRE (K1)** reaproveita o mesmo estilo de gráfico/tooltip.

**O protótipo Lovable produz apenas o conteúdo das páginas** (dentro de `<main>`). Não recriar sidebar, header, layout, providers ou tokens.

### Tokens e convenções (relembrete)

- Tokens semânticos sempre (`bg-card`, `border-border`, `text-muted-foreground`, `bg-primary`, `bg-sidebar`, `text-sidebar-primary`, `text-success`, `text-destructive`) — **nunca** `bg-white`/`text-gray-*` nem cores hardcoded.
- Ícones **Lucide** `size={16}` `strokeWidth={1.5}` — nunca emojis. Sugestões: `Receipt` (despesas), `Package`/`Boxes` (estoque), `Truck` (fornecedores), `FileText`/`ClipboardList` (payables), `BarChart3` (DRE), `Wallet`/`Landmark` (contas), `ArrowLeftRight` (transferências), `Scale`/`CheckCheck` (conciliação), `Calculator` (cash count), `FileSpreadsheet`/`Upload` (extrato).
- `h1/h2/h3` herdam Cormorant Garamond; título de página: `font-display text-3xl tracking-wide`. Em `span/div`: `[font-family:var(--font-display)]`.
- **Moeda:** `formatBRLFromDecimal()` (string decimal). **Datas:** `formatDateTime()` (timezone do tenant, fallback `America/Sao_Paulo`); para `due_date`/`occurred_at` que vêm como **date pura** (`"2026-06-15"`), formatar como data curta sem hora.
- Nomenclatura Estágio 0: `professionals` → "Barbeiros/Profissional"; campos ausentes → fallback `"Em breve"` (`text-xs text-muted-foreground opacity-50`), **não** mockar no código real.

---

## 2b. Referências visuais

Para cada tela desta fase, **consultar a pasta de screenshots compartilhada na sessão**. Se houver screenshot aprovada, ela é o contrato visual; o código em `/tmp/barberflow` é a referência de **estrutura**.

> **⚠️ Status real desta fase (reportar ao Lovable):** **não há screenshots aprovadas** para nenhuma das telas da Fase 3 (a pasta cobre apenas Fases 0–2: agenda, clientes, catálogo, pacotes, assinaturas, promoções, pagamentos, inbox, fila). E o protótipo **barberflow-system não tem rotas de financeiro profundo** — só `_authenticated.app.financeiro.tsx` (um dashboard) e `_authenticated.configuracoes.financeiro.tsx` (settings). Nenhuma rota `despesa / estoque / fornecedor / payable / dre / conciliacao / extrato / conta` existe no protótipo.
>
> **Consequência:** estas 13 telas são **desenhadas do zero**, herdando o **vocabulário visual já consolidado nas Fases 1 e 2** (mesma régua de `PageHeader`, `Table`, `Dialog`/`Sheet`, `FsmBadge`, filtros client-side, KPIs em `Card`, gráficos Recharts com tokens `--chart-*`). O `financeiro/page.tsx` atual (KPI strip + AreaChart + cards de acesso rápido) é o **molde de layout** a seguir para o DRE e a Conciliação.

---

## 3. Endpoints por tela

Todos exigem JWT (`HTTPBearer`). **Valores monetários = string decimal.** Métodos, campos, defaults e roles **confirmados contra `openapi.json` e os routers/models do backend**. `*` = obrigatório.

### Bloco I — Despesas (`/expenses`) · roles: GET OWNER/ADMIN/OPERATOR · POST/pay/cancel **OWNER/ADMIN**

| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /expenses/?status=&category=&due_date_from=&due_date_to=&supplier_id=` | `ExpenseResponse[]` |
| Detalhe | `GET /expenses/{expense_id}` | `ExpenseResponse` |
| Criar | `POST /expenses/` | `ExpenseCreate` |
| Pagar | `PATCH /expenses/{expense_id}/pay` | `ExpensePayRequest{paid_amount?(num/str/null)}` → `ExpenseResponse` |
| Cancelar | `PATCH /expenses/{expense_id}/cancel` | `ExpenseCancelRequest{reason*}` → `ExpenseResponse` |

`ExpenseCreate`: `description*, amount*(number|string), category*(string — categoria DESPESA, ver §5), due_date*(date), supplier_id?, recurrence_rule?{frequency*, day_of_month*(int), end_date?(date)}`.
`ExpenseResponse`: `id, company_id, description, amount(str), category, supplier_id?, due_date(date), status(PENDENTE|PAGA|CANCELLED), paid_at?(date-time), paid_amount?(str), recurrence_rule?(obj), parent_expense_id?(uuid), created_by, created_at`.
> ⚠️ **`pay` aceita `paid_amount` opcional** (default = `amount`); útil para pagamento de valor divergente. **Só despesa `PENDENTE` pode ser paga/cancelada.** `recurrence_rule` gera despesas-filhas via worker; no protótipo o form oferece um toggle "Recorrente" + frequência + dia do mês (read/write), mas a **série** (despesas-filhas com `parent_expense_id`) é só leitura. `supplier_id` → nome via `/suppliers/` (J4).

### Bloco J — Estoque, Fornecedores e Payables (cadeia)

**J1 — Estoque** (`/stock/`) · roles: OWNER/ADMIN/OPERATOR (leitura).
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /stock/?active_only=true` | `StockProductResponse[]` |

`StockProductResponse`: `id, name, active, stock?(int), stock_min_alert?(str), unit?(str), avg_cost?(str)`.
> ⚠️ É a **visão de estoque do produto** (não o CRUD de produto da Fase 2). `avg_cost` = **custo médio ponderado** já calculado no backend (string decimal) — exibir com `formatBRLFromDecimal`. **Alerta de estoque baixo:** comparar `stock` com `stock_min_alert` é exibição visual (badge "Baixo") permitida — não é regra de negócio, ambos vêm da API. Sem `stock` → "Em breve".

**J2 — Movimentações** (`/stock/movements/`) · roles: GET OWNER/ADMIN/OPERATOR · POST **OWNER/ADMIN**.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /stock/movements/?product_id=&movement_type=&date_from=&date_to=` | `StockMovementResponse[]` |
| Registrar saída/ajuste | `POST /stock/movements/` | `RecordMovementRequest` → `201 StockMovementResponse` |

`RecordMovementRequest`: `product_id*, movement_type*(**VENDA|USO_INTERNO|PERDA|AJUSTE**), quantity*(number|string), source_type?, source_id?, notes?`.
`StockMovementResponse`: `id, company_id, product_id, movement_type(ENTRADA|VENDA|USO_INTERNO|PERDA|AJUSTE), quantity(str), unit_cost?(str), source_type?, source_id?, notes?, occurred_at, created_by`.
> ⚠️ **`ENTRADA` NÃO é registrável por aqui** — entrada de estoque só ocorre via **receber pedido (J3)**. O `Select` de `movement_type` no form oferece apenas `VENDA / USO_INTERNO / PERDA / AJUSTE`. **`AJUSTE` exige `notes`** (validação do backend; refletir como required no form quando o tipo for AJUSTE). `product_id` → nome via `/stock/` ou `/products/`.

**J3 — Receber pedido de fornecedor** (`/stock/orders/`) · roles: **OWNER/ADMIN**. (modal lançado de J1)
| Ação | Método + Path | Campos |
|---|---|---|
| Receber | `POST /stock/orders/` | `ReceiveOrderRequest` → `201 ReceiveOrderResponse` |

`ReceiveOrderRequest`: `supplier_id?, items*[{product_id*, quantity*(num|str), unit_cost*(num|str)}], closing_method(CASH_AT_CREATION|INSTALLMENTS)=CASH_AT_CREATION, installments?[{amount*, due_date?(date)}], due_date?(date), notes?`.
`ReceiveOrderResponse`: `order{id, company_id, supplier_id?, status(RECEIVED), ordered_at, received_at?, notes?}, payable_id(uuid), total_amount(str)`.
> ⚠️ **Esta é a cadeia Estoque → Payable.** Receber um pedido (1) dá **entrada** de estoque (`StockMovement ENTRADA` por item, recalculando `avg_cost`) **e** (2) cria automaticamente um **Payable** (`payable_id` retornado). A UI deve, no sucesso, exibir toast "Pedido recebido — conta a pagar criada" + **link para `/payables`** (filtrar por aquele `payable_id`). `closing_method=INSTALLMENTS` exige `installments[]`. Apoio: `GET /products/` (Select de produto) e `GET /suppliers/` (Select de fornecedor opcional).

**J4 — Fornecedores** (`/suppliers/`) · roles: GET OWNER/ADMIN/OPERATOR · POST/PATCH/DELETE **OWNER/ADMIN**.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /suppliers/?active=true` | `SupplierResponse[]` |
| Criar | `POST /suppliers/` | `SupplierCreate{name*, contact?, document?}` → `201` |
| Editar | `PATCH /suppliers/{supplier_id}` | `SupplierUpdate{name?, contact?, document?, active?}` |
| Excluir | `DELETE /suppliers/{supplier_id}` | → `200 SupplierResponse` |

`SupplierResponse`: `id, company_id, name, contact?, document?, active, created_at, updated_at`.
> ⚠️ `DELETE` retorna `SupplierResponse` (provável **desativação lógica**, não 204) — tratar como "Desativar" e refletir `active=false` na lista, sem remover a linha. `document` = CNPJ/CPF do fornecedor (texto livre).

**J5 — Payables (contas a pagar)** (`/payables`) · roles: GET/installments OWNER/ADMIN/OPERATOR · POST/cancel/pay **OWNER/ADMIN**.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /payables/?status=&supplier_id=&due_date_from=&due_date_to=` | `PayableResponse[]` |
| Criar | `POST /payables/` | `PayableCreate` → `201` |
| Cancelar | `PATCH /payables/{payable_id}/cancel` | `PayableCancelRequest{reason*}` → `PayableResponse` |
| Parcelas | `GET /payables/{payable_id}/installments` | `PayableInstallmentResponse[]` |
| Pagar parcela | `PATCH /payables/{payable_id}/installments/{installment_id}/pay` | `PayablePayRequest{payment_id?, account_id?}` → `PayableResponse` |

`PayableCreate`: `description*, total_amount*(num|str), supplier_id?, due_date?(date), closing_method(CASH_AT_CREATION|INSTALLMENTS)=CASH_AT_CREATION, installments?[{amount*, due_date?(date)}]`.
`PayableResponse`: `id, company_id, supplier_id?, description, total_amount(str), paid_amount(str), status(**OPEN|PARTIALLY_PAID|PAID|CANCELLED**), due_date?(date), closing_method, source_type, source_id?, created_at, updated_at`.
`PayableInstallmentResponse`: `id, payable_id, amount(str), due_date?(date), paid_at?(date-time), payment_id?, installment_number(int), status(**OPEN|PAID**)`.
> ⚠️ **Pagar é por PARCELA** (não pelo payable inteiro). `PayablePayRequest` opcionalmente liga a parcela a um `payment_id` e/ou debita de um `account_id` (Select de contas de K2). Pagar a última parcela vira o payable para `PAID`; parcial → `PARTIALLY_PAID`. `paid_amount` é **somado pelo backend** — exibir como veio. `source_type=SUPPLIER_ORDER` marca payables nascidos de pedidos (J3) — exibir badge/ícone de origem.

### Bloco K — Gestão Financeira

**K1 — DRE** (`/financial/dre`) · roles: **OWNER/ADMIN**.
| Ação | Método + Path | Campos |
|---|---|---|
| Gerar | `GET /financial/dre?date_from=&date_to=` (**ambos obrigatórios, date-time**) | `DreResponse` |

`DreResponse`: `date_from, date_to, receita(obj cat→valor), receita_total(str), custo(obj), custo_total(str), despesa(obj), despesa_total(str), taxa(obj), taxa_total(str), comissao(obj), comissao_total(str), estorno(obj), estorno_total(str), ajuste(obj), ajuste_total(str), resultado_bruto(str), resultado_liquido(str)`.
> ⚠️ Cada bucket (`receita`, `custo`, `despesa`, `taxa`, `comissao`, `estorno`, `ajuste`) é um **mapa `{categoria: valor_string}`**; o `*_total` correspondente já vem **somado pelo backend**. `resultado_bruto` e `resultado_liquido` também. **Nada de somar no cliente** — render direto. Glossário de categorias em §5 (`ENTRY_CATEGORY_LABELS`).

**K2 — Contas, saldos e transferências** (`/financial/accounts`, `/financial/transfers`) · roles: **OWNER/ADMIN**.
| Ação | Método + Path | Campos |
|---|---|---|
| Listar contas | `GET /financial/accounts` | `AccountResponse[]` |
| Criar conta | `POST /financial/accounts` | `AccountCreate` → `201` |
| Saldo da conta | `GET /financial/accounts/{account_id}/balance?as_of=` | `BalanceResponse{account_id, balance(str), as_of?}` |
| Listar transferências | `GET /financial/transfers` | `TransferResponse[]` |
| Transferir | `POST /financial/transfers` | `TransferCreate` → `201 TransferResponse` |

`AccountCreate`: `name*, type*(**CAIXA|ACQUIRER|BANK|ESCROW**), provider?, external_ref?, currency=BRL, is_default_inflow=false`.
`AccountResponse`: `account_id, company_id, name, type, provider?, external_ref?, currency, status(ACTIVE), is_default_inflow, created_at, updated_at?`.
`TransferCreate`: `from_account_id*, to_account_id*, amount*(num|str), notes?`.
`TransferResponse`: `transfer_id, company_id, from_account_id, to_account_id, amount(str), status(**REQUESTED|COMPLETED|FAILED**), requested_at, completed_at?, failed_at?, failure_reason?, notes?`.
> ⚠️ **Saldo é endpoint separado** (`/balance`) — buscar por conta (em paralelo ou on-demand ao expandir o card). `is_default_inflow` = conta padrão de entrada (badge "Padrão"); só uma por empresa. `from_account_id ≠ to_account_id` (validação no backend → tratar 422). **Sem editar/excluir conta** (não há endpoint) — não renderizar essas ações.

**Movimentos e Lançamentos (apoio, mesma rota K2 ou aba):**
| Ação | Método + Path | Campos |
|---|---|---|
| Movimentos | `GET /financial/movements?account_id=&type=&date_from=&date_to=` | `MovementResponse[]` |
| Lançamentos (entries) | `GET /financial/entries?type=&category=&date_from=&date_to=` | `EntryResponse[]` |
| Ajuste manual | `POST /financial/manual-adjustment` | `ManualAdjustmentCreate` → `201` (sem body) |

`MovementResponse`: `movement_id, company_id, account_id, type(**INFLOW|OUTFLOW|TRANSFER_IN|TRANSFER_OUT**), amount(str), occurred_at, source_type, source_id, transfer_id?, created_at`.
`EntryResponse`: `entry_id, type(**RECEITA|CUSTO|DESPESA|TAXA|COMISSAO|ESTORNO|AJUSTE**), direction(**ADDS|SUBTRACTS**), amount(str), occurred_at, category, source_type, source_id, movement_id?, created_at`.
`ManualAdjustmentCreate`: `amount*(num|str), direction*(**ADDS|SUBTRACTS**), category*(entry_category), account_id*, reason*`.
> ⚠️ **`/financial/movements` (lista geral)** já existe como tela `/financeiro/movimentacoes` (Fase 1, Feito) — **não reconstruir**; aqui o uso é o filtro por `account_id` dentro de Contas. **Ajuste manual é ação sensível** (gera Movement + Entry) — opcional no protótipo, em `Dialog` com confirmação dupla; `direction=ADDS`→entrada, `SUBTRACTS`→saída; `category` é uma categoria de `entry_category` (oferecer as de **AJUSTE**: `CONTAGEM_CAIXA, CONTAGEM_ESTOQUE, CORRECAO_LANCAMENTO, CORRECAO_COMISSAO, AJUSTE_OUTROS`).

**K3 — Conciliação + Cash count** (`/financial/reconciliation`, `/financial/cash-counts`) · roles: reconciliação **OWNER/ADMIN**; cash-counts **OWNER/ADMIN/OPERATOR**.
| Ação | Método + Path | Campos |
|---|---|---|
| Abrir conciliação | `POST /financial/reconciliation` | `ReconciliationCreate{account_id*, notes?}` → `201 ReconciliationResponse` |
| Fechar conciliação | `PUT /financial/reconciliation/{reconciliation_id}/close` | **sem body** → `ReconciliationResponse` |
| Movimentos não conciliados | `GET /financial/movements/unreconciled?account_id=` (**obrigatório**) | `MovementResponse[]` |
| Marcar movimento conciliado | `POST /financial/movements/{movement_id}/reconcile` | `MarkMovementReconciledBody{reconciliation_id*}` → `201` |
| Listar cash counts | `GET /financial/cash-counts` | `CashCountResponse[]` |
| Registrar contagem | `POST /financial/cash-counts` | `CashCountCreate` → `201 CashCountResponse` |

`ReconciliationResponse`: `reconciliation_id, company_id, account_id, status(**OPEN|CLOSED**), opened_at, closed_at?, opened_by, closed_by?, notes?`.
`MovementReconciliationResponse` (resposta do reconcile): `id, company_id, movement_id, reconciliation_id, reconciled_at, reconciled_by`.
`CashCountCreate`: `account_id*, counted_amount*(num|str), resolution*(**ADJUSTED|NO_ADJUSTMENT**), notes?`.
`CashCountResponse`: `cash_count_id, company_id, account_id, expected_amount(str), counted_amount(str), **discrepancy(str)**, resolution, notes?, entry_id?, created_by, created_at`.
> ⚠️ **Sequência obrigatória da conciliação:** abrir (`POST /reconciliation`) → listar `unreconciled` daquela conta → marcar cada movimento (`POST /{id}/reconcile` com o `reconciliation_id`) → fechar (`PUT /close`). **Não é possível fechar sem conciliação aberta**; `reconcile` falha (422) em conciliação `CLOSED`. **`discrepancy` = `counted_amount − expected_amount` é calculada no backend** — exibir como veio (verde se `0`, vermelho se negativo, âmbar se positivo). `expected_amount` (saldo esperado) também vem da resposta — não calcular. `resolution=ADJUSTED` com `discrepancy ≠ 0` **exige `notes`** (validação backend).

**K4 — Extrato bancário (import CSV + match)** (`/financial/statement/*`) · roles: **OWNER/ADMIN/OPERATOR** (import pode exigir grant de ação — ver nota).
| Ação | Método + Path | Campos |
|---|---|---|
| Importar CSV | `POST /financial/statement/import` (**multipart/form-data**) | `file*(binário), account_id*(uuid), column_mapping*(string JSON)` → `201 StatementImportResponse` |
| Listar entradas | `GET /financial/statement/?account_id=&status=&batch_id=&date_from=&date_to=` | `StatementEntryResponse[]` |
| Lotes (batches) | `GET /financial/statement/batches` | `StatementBatchSummary[]` |
| Sugestões de match | `GET /financial/statement/{entry_id}/suggestions` | `MovementResponse[]` |
| Confirmar match | `POST /financial/statement/{entry_id}/match` | `StatementMatchBody{movement_id*}` → `StatementEntryResponse` |
| Dispensar | `POST /financial/statement/{entry_id}/dismiss` | `StatementDismissBody{reason*}` → `StatementEntryResponse` |

`StatementImportResponse`: `imported(int), skipped_duplicates(int), skipped_invalid(int), auto_matched(int), batch_id(uuid)`.
`StatementEntryResponse`: `id, company_id, account_id, occurred_at(date), amount(str), direction(**INFLOW|OUTFLOW**), description?, status(**PENDING|MATCHED|DISMISSED**), matched_movement_id?, dismissed_reason?, dismissed_at?, dismissed_by?, imported_at?, import_batch_id`.
`StatementBatchSummary`: `batch_id, account_id, imported_at?, total(int), matched(int), pending(int), dismissed(int)`.
> ⚠️ **`column_mapping` é uma string JSON** com as chaves `{"date": idx_ou_nome, "amount": idx_ou_nome, "description"?: ..., "direction"?: ...}` — `date` e `amount` **obrigatórias** (422 se faltar). Os valores são o índice (0-based) **ou** o nome do cabeçalho da coluna no CSV. **Sugestões/match só para entries `PENDING`** (422 caso contrário). `import` pode estar atrás de `require_action` (opt-in por config do tenant) — se a API devolver 403/`require_action`, exibir aviso "Ação não habilitada para este tenant" em vez de quebrar. Multipart: ver §4 K4 e §5.

**Apoio transversal:** `GET /financial/settings` → `FinancialSettingsResponse{payment_provider?, external_account_id?, external_account_status?, external_account_created_at?, accounts_count}` — usar no topo de Contas (K2) para mostrar provedor/quantidade de contas; é GET, read-only nesta fase.

---

## 4. Especificação das 13 telas

Para cada tela: **rota · role · layout · componentes shadcn · estados · ações**. Estados obrigatórios em todas: **vazio (`EmptyState`) · loading (`Skeleton`) · erro (`ErrorState` com retry) · dados**.

### I1 — `/despesas` — Lista + lançar + pagar/cancelar
- **Role:** OWNER/ADMIN (OPERATOR vê lista, ações de escrita ocultas/desabilitadas).
- **Layout:** `PageHeader` "Despesas" + botão "Nova despesa"; faixa de filtros (status, categoria, período de vencimento, fornecedor) + `Table`.
- **Colunas:** Descrição · Categoria (`ENTRY_CATEGORY_LABELS`) · Valor (`amount`) · Vencimento (`due_date`, data curta) · **Status** (`ExpenseBadge`) · Fornecedor (`supplier_id`→nome ou "—") · Pago em (`paid_at`/`paid_amount` se PAGA) · ações.
- **Filtros (client+query):** `status` (PENDENTE/PAGA/CANCELLED), `category` (Select de categorias DESPESA), `due_date_from/to` (`DateTimePicker` em modo data), `supplier_id` (Select de `/suppliers/`). Repassar ao `GET` como query.
- **Form criar (`Dialog`):** `Input` descrição, `Input` numérico valor (step 0.01), `Select` categoria (categorias **DESPESA**, ver §5), `DateTimePicker` vencimento, `Select` fornecedor (opcional), `Switch` "Recorrente" → quando ligado: `Select` frequência + `Input` dia do mês + `DateTimePicker` fim (opcional).
- **Ações (por status):** **Pagar** (só `PENDENTE`) → `Dialog` com `Input` opcional "Valor pago" (default = `amount`) → `PATCH /pay`; **Cancelar** (só `PENDENTE`) → `Dialog` com `Textarea` motivo (obrigatório) → `PATCH /cancel`; linha → detalhe (`GET /{id}`). Despesas-filhas (`parent_expense_id`) marcadas com ícone "recorrente" (read-only).

### J1 — `/estoque` — Lista (quantidade + custo médio)
- **Role:** OWNER/ADMIN (OPERATOR vê; ações OWNER/ADMIN).
- **Layout:** `PageHeader` "Estoque" + botões "Receber pedido" (J3) e toggle "Mostrar inativos" (`active_only`); `Table`.
- **Colunas:** Produto (`name`) · Qtd (`stock` + `unit` ou "Em breve") · Alerta mín. (`stock_min_alert` ou "—") · **Custo médio** (`avg_cost`, `formatBRLFromDecimal`) · Status (`ActiveBadge` por `active`) · ações.
- **Badge "Estoque baixo":** se `stock != null && stock_min_alert != null && stock ≤ stock_min_alert` → badge âmbar (apenas visual; ambos vêm da API).
- **Componentes:** `Table`, `Badge`, `Button`, `Switch`, `Skeleton`, `Tooltip`.
- **Ações:** "Movimentações" → link/atalho a J2 (filtrado por `product_id`); "Receber pedido" → abre J3.

### J3 — Receber pedido (modal guiado, lançado de J1)
- **Role:** OWNER/ADMIN.
- **Layout:** `Dialog` "Receber pedido de fornecedor": `Select` fornecedor (opcional, `/suppliers/`) + **lista editável de itens** (linhas com `Select` produto + `Input` quantidade + `Input` custo unitário, botão "Adicionar item") + `Select` forma de fechamento (`CLOSING_METHOD_LABELS`) → se `INSTALLMENTS`: editor de parcelas (`amount` + `due_date` por linha); se `CASH_AT_CREATION`: `DateTimePicker` vencimento único (opcional) + `Textarea` notas.
- **Resumo:** total (somatório dos itens) exibido como **prévia visual** — o `total_amount` **autoritativo** vem da resposta; exibir o da resposta no sucesso.
- **Ação:** `POST /stock/orders/` → no sucesso, toast "Pedido recebido — entrada de estoque registrada e conta a pagar criada" + **botão "Ver conta a pagar"** que leva a `/payables` (destacando `payable_id`). Recarregar lista de estoque.
- **Estados:** validação por item (produto, qty>0, custo≥0); enviar desabilita o botão.

### J2 — `/estoque/movimentacoes` — Histórico de movimentos
- **Role:** OWNER/ADMIN (OPERATOR vê).
- **Layout:** `PageHeader` "Movimentações de estoque" + filtros (produto, tipo, período) + botão "Registrar movimento" + `Table`.
- **Colunas:** Data (`occurred_at`) · Produto (`product_id`→nome) · Tipo (`STOCK_MOVEMENT_TYPE_LABELS` + cor por tipo) · Quantidade (`quantity` + sinal: ENTRADA/AJUSTE+ positivo, demais negativo — visual) · Custo unit. (`unit_cost` ou "—") · Origem (`source_type`) · Notas.
- **Form registrar (`Dialog`):** `Select` produto (`/stock/` ou `/products/`), `Select` tipo (**apenas VENDA/USO_INTERNO/PERDA/AJUSTE** — ENTRADA fica fora, com nota "Entrada só via Receber pedido"), `Input` quantidade, `Textarea` notas (**obrigatório quando tipo=AJUSTE**).
- **Ação:** `POST /stock/movements/` → toast + recarrega. Filtros repassados ao `GET`.

### J4 — `/fornecedores` — CRUD de fornecedores
- **Role:** OWNER/ADMIN (OPERATOR vê).
- **Layout:** `PageHeader` "Fornecedores" + "Novo fornecedor" + toggle ativos/inativos (`active`) + `Table`.
- **Colunas:** Nome · Contato (`contact` ou "—") · Documento (`document` ou "—") · Status (`ActiveBadge`) · Criado em · ações.
- **Form (`Dialog` criar/editar):** `Input` nome*, `Input` contato, `Input` documento (CNPJ/CPF).
- **Ações:** criar (`POST`), editar (`PATCH`), **"Desativar"** (`DELETE` → reflete `active=false`, **não** remove a linha) com `Dialog` de confirmação.

### J5 — `/payables` — Contas a pagar + parcelas + pagar
- **Role:** OWNER/ADMIN (OPERATOR vê lista/parcelas).
- **Layout:** `PageHeader` "Contas a pagar" + "Nova conta a pagar" + filtros (status, fornecedor, período de vencimento) + `Table`.
- **Colunas:** Descrição · Fornecedor (`supplier_id`→nome ou "—") · Total (`total_amount`) · Pago (`paid_amount`) · **Status** (`PayableBadge`) · Vencimento (`due_date`) · Fechamento (`CLOSING_METHOD_LABELS`) · Origem (ícone se `source_type=SUPPLIER_ORDER`) · ações.
- **Form criar (`Dialog`):** `Input` descrição, `Input` valor total, `Select` fornecedor (opcional), `DateTimePicker` vencimento (opcional), `Select` fechamento → se `INSTALLMENTS`: editor de parcelas (`amount`+`due_date`).
- **Detalhe/parcelas (`Sheet` ou `Dialog`, ação "Parcelas"):** header com descrição/status do payable + `Table` de `PayableInstallmentResponse` — Nº (`installment_number`) · Valor · Vencimento · **Status** (`InstallmentBadge`) · Pago em (`paid_at`) · ação **Pagar** (só `OPEN`).
- **Pagar parcela (`Dialog`):** `Select` conta (opcional, `account_id` de K2) + `Select`/Input `payment_id` (opcional) → `PATCH /installments/{id}/pay` → toast + atualiza payable e parcelas.
- **Cancelar payable:** `Dialog` com motivo (obrigatório) → `PATCH /cancel` (esconder se já `PAID`/`CANCELLED`).

### K1 — `/financeiro/dre` — DRE por período
- **Role:** OWNER/ADMIN.
- **Layout:** `PageHeader` "DRE — Demonstrativo de Resultado" + **seletor de período** (mês / trimestre / ano / intervalo custom com dois `DateTimePicker`) → dispara `GET /financial/dre?date_from&date_to`.
- **Topo (KPI strip, mesmo molde de `financeiro/page.tsx`):** Receita total · Custo total · Despesa total · **Resultado líquido** (verde/vermelho conforme sinal — a string já vem com sinal; ler, não recalcular).
- **Gráfico (Recharts):** barras com Receita × (Custo + Despesa + Taxa + Comissão + Estorno) × Resultado, usando tokens `--chart-*` e o `AreaTooltip`/`BarTooltip` já existentes; valores via `formatBRL`.
- **Tabela de categorias:** uma seção por bucket (`receita`, `custo`, `despesa`, `taxa`, `comissao`, `estorno`, `ajuste`) com linhas `categoria (ENTRY_CATEGORY_LABELS) → valor` e o `*_total` no rodapé de cada seção. **Tudo direto da API.** Linha final: `resultado_bruto` e `resultado_liquido`.
- **Componentes:** `Card`, `Tabs` (ou seções), `Table`, Recharts, `Skeleton`, `Button` (período).

### K2 — `/financeiro/contas` — Contas + saldos + transferências
- **Role:** OWNER/ADMIN.
- **Layout:** `PageHeader` "Contas financeiras" + (read-only) faixa de `FinancialSettings` (provedor, `accounts_count`) + "Nova conta" + "Transferir" + grid de **cards de conta**.
- **Card de conta:** Nome · Tipo (`ACCOUNT_TYPE_LABELS`) · `provider`/`external_ref` (se houver) · **Saldo** (`GET /balance` → `balance`, `formatBRLFromDecimal`) · badge "Padrão" se `is_default_inflow` · `ActiveBadge`.
- **Aba/seção "Transferências":** `Table` de `TransferResponse` — Origem→Destino (nomes via contas) · Valor · **Status** (`TransferBadge`) · Solicitada em · Concluída/Falhou · motivo de falha.
- **Aba/seção "Movimentos" (opcional):** `GET /financial/movements?account_id=` filtrado pela conta selecionada — Data · Tipo (`MOVEMENT_TYPE_LABELS`) · Valor · Origem.
- **Form nova conta (`Dialog`):** `Input` nome, `Select` tipo (CAIXA/ACQUIRER/BANK/ESCROW), `Input` provider (opcional), `Input` external_ref (opcional), `Switch` is_default_inflow.
- **Form transferir (`Dialog`):** `Select` conta origem, `Select` conta destino (≠ origem), `Input` valor, `Textarea` notas → `POST /transfers`.
- **Ajuste manual (opcional, ação sensível):** `Dialog` separado com confirmação — `Input` valor, `RadioGroup` direção (ADDS/SUBTRACTS), `Select` categoria (categorias AJUSTE), `Select` conta, `Textarea` motivo → `POST /manual-adjustment`. **Sem editar/excluir conta** (não há endpoint).

### K3 — `/financeiro/conciliacao` — Abertura/fechamento + cash count
- **Role:** conciliação OWNER/ADMIN; cash count OWNER/ADMIN/OPERATOR.
- **Layout:** `PageHeader` "Conciliação" + `Tabs` "Conciliação bancária" | "Contagem de caixa".
- **Tab Conciliação (fluxo sequencial):**
  1. `Select` conta → se **não há conciliação OPEN** para ela, botão "Abrir conciliação" (`POST /reconciliation`).
  2. Com conciliação **OPEN**: `Table` de `GET /movements/unreconciled?account_id` — Data · Tipo · Valor · checkbox/botão **"Marcar conciliado"** (`POST /{movement_id}/reconcile` com `reconciliation_id`).
  3. Botão **"Fechar conciliação"** (`PUT /close`) — **desabilitado se não houver conciliação aberta**; `Dialog` de confirmação.
  - Badge de estado da conciliação (`ReconciliationBadge`: OPEN/CLOSED).
- **Tab Cash count:**
  - `Table`/lista de `CashCountResponse` (histórico) — Data · Conta · Esperado (`expected_amount`) · Contado (`counted_amount`) · **Divergência** (`discrepancy`, cor: **verde=0, vermelho<0, âmbar>0**) · Resolução (`CASH_COUNT_RESOLUTION_LABELS`).
  - Botão "Registrar contagem" (`Dialog`): `Select` conta, `Input` valor contado, `RadioGroup` resolução (ADJUSTED/NO_ADJUSTMENT), `Textarea` notas (**obrigatório se ADJUSTED e divergência ≠ 0** — mas a divergência só é conhecida após o POST; exibir `discrepancy` da resposta e, se o backend retornar 422 pedindo notas, orientar o usuário). → `POST /cash-counts`.
- **Componentes:** `Tabs`, `Select`, `Table`, `Checkbox`/`Button`, `Dialog`, `Badge`, `Skeleton`, `EmptyState`.

### K4 — `/financeiro/extrato` — Import CSV + sugestões de match + dismiss
- **Role:** OWNER/ADMIN/OPERATOR (import pode exigir grant — ver §3 K4).
- **Layout:** `PageHeader` "Extrato bancário" + cards de **lotes** (`StatementBatchSummary`: total/matched/pending/dismissed por `batch_id`) + área de import + `Table` de entradas.
- **Import (sequência obrigatória):**
  1. **Upload** — área de drop + `<input type="file" accept=".csv" hidden>` (padrão de `/uploads/`); `Select` conta de destino (`account_id`); editor de **`column_mapping`** (mapear colunas do CSV: data*, valor*, descrição?, direção?) → montar o **JSON string** exigido.
  2. **Preview** — ler localmente as primeiras N linhas do CSV e mostrar prévia em tabela (apenas visual, antes de enviar).
  3. **Importar** — `POST /financial/statement/import` (multipart) com **spinner/Progress** durante o upload; no sucesso, toast com `StatementImportResponse` ("X importadas, Y duplicadas ignoradas, Z auto-conciliadas").
- **Tabela de entradas (`GET /financial/statement/`):** Data (`occurred_at`) · Descrição · Valor · Direção (`INFLOW`/`OUTFLOW`) · **Status** (`StatementBadge`: PENDING/MATCHED/DISMISSED) · ações.
- **Match (só PENDING):** ação "Ver sugestões" → `GET /{id}/suggestions` (lista de `MovementResponse` candidatos) em `Dialog` → escolher um → **Confirmar match** (`POST /{id}/match {movement_id}`) **ou** **Dispensar** (`POST /{id}/dismiss {reason}` com motivo obrigatório).
- **Filtros:** conta, status, batch, período.
- **Componentes:** área de upload, `Progress`/spinner, `Table`, `Dialog`, `Badge`, `Select`, `Skeleton`, `EmptyState`.

> **Contagem das 13 telas/superfícies:** I1(1) · J1(2) · J3 modal(3) · J2(4) · J4(5) · J5 lista(6) · J5 parcelas(7) · K1 DRE(8) · K2 contas(9) · K2 transferência modal(10) · K3 conciliação(11) · K3 cash count(12) · K4 extrato(13).

---

## 5. Padrões de UX específicos da Fase 3

### Badges de FSM novos — adicionar a `components/FsmBadge.tsx`
Reusar as constantes de cor já definidas no arquivo (`EMERALD`, `AMBER`, `DESTRUCTIVE`, `NEUTRAL`, mais `SKY` se necessário). Valores **exatos do backend** (não inventar estados):

**Expense** (`ExpenseBadge`):
| Estado | Label | Cor |
|---|---|---|
| `PENDENTE` | Pendente | âmbar |
| `PAGA` | Paga | emerald |
| `CANCELLED` | Cancelada | muted |
> ⚠️ O cancelamento grava **`CANCELLED`** (inglês), não "CANCELADA". Usar a chave exata.

**Payable** (`PayableBadge`):
| Estado | Label | Cor |
|---|---|---|
| `OPEN` | Em aberto | âmbar |
| `PARTIALLY_PAID` | Parcial | sky |
| `PAID` | Paga | emerald |
| `CANCELLED` | Cancelada | muted |

**Installment** (`InstallmentBadge`):
| Estado | Label | Cor |
|---|---|---|
| `OPEN` | Em aberto | âmbar |
| `PAID` | Paga | emerald |
| `CANCELLED` | Cancelada | muted |

**Reconciliation** (`ReconciliationBadge`):
| Estado | Label | Cor |
|---|---|---|
| `OPEN` | Aberta | âmbar |
| `CLOSED` | Fechada | emerald |

**Statement** (`StatementBadge`):
| Estado | Label | Cor |
|---|---|---|
| `PENDING` | Pendente | âmbar |
| `MATCHED` | Conciliado | emerald |
| `DISMISSED` | Dispensado | muted |

**Transfer** (`TransferBadge`):
| Estado | Label | Cor |
|---|---|---|
| `REQUESTED` | Solicitada | âmbar |
| `COMPLETED` | Concluída | emerald |
| `FAILED` | Falhou | destructive |

> `SupplierOrder.status` é sempre `RECEIVED` neste fluxo (criado já recebido) — basta um badge emerald "Recebido"; não precisa FSM próprio. `Account.status=ACTIVE` e `Supplier.active`/`StockProduct.active` usam o `ActiveBadge` existente.

### Glossários de enum — adicionar a `lib/constants.ts` (fonte única)
- `EXPENSE_STATUS_LABELS`: `PENDENTE`→"Pendente", `PAGA`→"Paga", `CANCELLED`→"Cancelada".
- `PAYABLE_STATUS_LABELS`: `OPEN`→"Em aberto", `PARTIALLY_PAID`→"Parcial", `PAID`→"Paga", `CANCELLED`→"Cancelada".
- `INSTALLMENT_STATUS_LABELS`: `OPEN`→"Em aberto", `PAID`→"Paga", `CANCELLED`→"Cancelada".
- `RECONCILIATION_STATUS_LABELS`: `OPEN`→"Aberta", `CLOSED`→"Fechada".
- `STATEMENT_STATUS_LABELS`: `PENDING`→"Pendente", `MATCHED`→"Conciliado", `DISMISSED`→"Dispensado".
- `TRANSFER_STATUS_LABELS`: `REQUESTED`→"Solicitada", `COMPLETED`→"Concluída", `FAILED`→"Falhou".
- `STOCK_MOVEMENT_TYPE_LABELS`: `ENTRADA`→"Entrada", `VENDA`→"Venda", `USO_INTERNO`→"Uso interno", `PERDA`→"Perda", `AJUSTE`→"Ajuste".
- `ACCOUNT_TYPE_LABELS`: `CAIXA`→"Caixa", `ACQUIRER`→"Adquirente", `BANK`→"Banco", `ESCROW`→"Conta garantia".
- `MOVEMENT_TYPE_LABELS`: `INFLOW`→"Entrada", `OUTFLOW`→"Saída", `TRANSFER_IN`→"Transf. recebida", `TRANSFER_OUT`→"Transf. enviada".
- `ENTRY_TYPE_LABELS`: `RECEITA`→"Receita", `CUSTO`→"Custo", `DESPESA`→"Despesa", `TAXA`→"Taxa", `COMISSAO`→"Comissão", `ESTORNO`→"Estorno", `AJUSTE`→"Ajuste".
- `CLOSING_METHOD_LABELS`: `CASH_AT_CREATION`→"À vista", `INSTALLMENTS`→"Parcelado".
- `CASH_COUNT_RESOLUTION_LABELS`: `ADJUSTED`→"Com ajuste", `NO_ADJUSTMENT`→"Sem ajuste".
- `ENTRY_CATEGORY_LABELS` (mapa de **categoria → label PT-BR**, usado em Despesas, DRE, Lançamentos, Ajuste). Conjunto completo do backend (`entry_category.py`):
  - **RECEITA:** SERVICOS→"Serviços", PRODUTOS→"Produtos", PACOTE→"Pacote", ASSINATURA_ADESAO→"Assinatura (adesão)", ASSINATURA_RENOVACAO→"Assinatura (renovação)", SINAL_SERVICO→"Sinal de serviço", RECEITA_OUTROS→"Outras receitas".
  - **CUSTO:** INSUMOS_USO_INTERNO→"Insumos (uso interno)", PRODUTO_VENDIDO→"Produto vendido", MATERIAL_DESCARTAVEL→"Material descartável", PERDA_ESTOQUE→"Perda de estoque", PERDA_OPERACIONAL→"Perda operacional", CUSTO_OUTROS→"Outros custos".
  - **DESPESA:** ALUGUEL→"Aluguel", UTILITIES→"Utilidades (água/luz)", MARKETING→"Marketing", SOFTWARE→"Software", CONTABILIDADE→"Contabilidade", LIMPEZA→"Limpeza", MANUTENCAO→"Manutenção", SALARIO→"Salário", SERVICOS_PJ→"Serviços PJ", ALIMENTACAO_COPA→"Alimentação/copa", EQUIPAMENTOS→"Equipamentos", TAXAS_BANCARIAS→"Taxas bancárias", TREINAMENTO→"Treinamento", DESPESA_OUTROS→"Outras despesas".
  - **TAXA:** ACQUIRER_FEE→"Taxa de adquirente", WITHDRAW_FEE→"Taxa de saque", ANTECIPATION_FEE→"Taxa de antecipação", TAXA_OUTROS→"Outras taxas".
  - **COMISSAO:** COMISSAO_SERVICO→"Comissão de serviço", COMISSAO_VENDA→"Comissão de venda", COMISSAO_RENOVACAO→"Comissão de renovação", COMISSAO_PERSONALIZADA→"Comissão personalizada".
  - **ESTORNO:** REEMBOLSO_CLIENTE→"Reembolso ao cliente", CHARGEBACK→"Chargeback", REVERSAO_TAXA→"Reversão de taxa".
  - **AJUSTE:** CONTAGEM_CAIXA→"Contagem de caixa", CONTAGEM_ESTOQUE→"Contagem de estoque", CORRECAO_LANCAMENTO→"Correção de lançamento", CORRECAO_COMISSAO→"Correção de comissão", AJUSTE_OUTROS→"Outros ajustes".
- `EXPENSE_CATEGORY_OPTIONS` — subconjunto **DESPESA** acima, para o `Select` de categoria no form de Despesa (J→I1). `STOCK_COST` e `AJUSTE` ficam para Estoque/Ajuste manual.

### Cadeia Estoque → Payable (documentar na UI)
**Receber pedido de fornecedor (J3) cria um Payable automaticamente.** O `ReceiveOrderResponse` traz `payable_id`. Sempre exibir, após o sucesso, um caminho explícito para a conta a pagar criada (toast com ação "Ver conta a pagar" → `/payables`). Em `/payables`, payables com `source_type=SUPPLIER_ORDER` ganham um ícone/badge de origem "Pedido de estoque". Fluxo completo (inventário §7.4): *Fornecedor → Receber pedido (gera Payable + entrada de estoque) → Pagar parcela (Movement OUTFLOW) → venda/consumo gera Entry CUSTO.*

### DRE — seletor de período
Atalhos **Mês atual / Trimestre / Ano** + **intervalo custom** (dois `DateTimePicker`). Os parâmetros do endpoint são `date_from`/`date_to` em **date-time** (não date) — enviar ISO com hora (início 00:00, fim 23:59 do range). Todos os totais vêm prontos da resposta.

### Extrato CSV — sequência obrigatória
`upload (file + account_id + column_mapping) → preview de linhas → import (multipart, spinner) → ver entradas → para cada PENDING: ver sugestões → confirmar match OU dispensar (com motivo) → acompanhar no resumo do lote`. **Multipart idêntico ao padrão `/uploads/`** (`api.postForm`/`FormData`): anexar `file` (binário), `account_id` (string) e `column_mapping` (string JSON). Mostrar `Progress`/spinner durante o envio e o resumo (`imported/skipped_*/auto_matched`) no toast.

### Conciliação — fluxo sequencial
**Não é possível fechar conciliação sem uma aberta**, e **não é possível conciliar movimento em conciliação fechada** (422). A UI guia: abrir → marcar → fechar. O botão "Fechar" fica desabilitado (com `Tooltip`) enquanto não houver conciliação `OPEN` para a conta.

### Cash count — divergência
`discrepancy = counted_amount − expected_amount` vem **pronta do backend**. Cor: **verde** se `0`, **vermelho** se negativo (falta dinheiro), **âmbar** se positivo (sobra). `resolution=ADJUSTED` com divergência ≠ 0 **exige `notes`**.

### Regras transversais (idênticas às Fases 1/2)
- **Toast** (`sonner`) após toda ação (success/error); erro deriva do `detail` da API (array 422 do FastAPI já tratado em `lib/api.ts`).
- **Monetário** sempre `formatBRLFromDecimal()`; **datas** com `formatDateTime()` (ou data curta para campos `date` puros).
- **Sem paginação no servidor** nestes endpoints → filtrar/paginar **client-side**; filtros que viram query (status, datas, ids) são repassados ao `GET`.
- **Ação sem endpoint** (editar/excluir conta; reabrir conciliação fechada; editar payable; remover parcela; reverter pagamento) → **não renderizar** ou `disabled` + `Tooltip` "Em breve".
- **RBAC visível:** OPERATOR vê estoque/movimentos/fornecedores/payables/cash-count e **registra contagem de caixa**; escrita de despesas/contas/transferências/DRE/conciliação é OWNER/ADMIN; a verdade é o 403 do backend.
- **Campos ausentes** (nome do produto/fornecedor quando só vem o id) → compor via lista correspondente ou `"Em breve"`.

---

## 6. O que NÃO entra na Fase 3

- **NPS, Comunicação (templates/logs), WhatsApp QR, Usuários/Acessos, Módulos do tenant, Branding, Audit** — Fase 4.
- **Telas públicas (`/gestao/[token]`, `/nps/[survey_id]`), Portal do Cliente, Painel Owner** — Fase 5.
- **Nenhum cálculo financeiro no cliente** — saldo (`balance`), discrepância (`discrepancy`), custo médio (`avg_cost`), totais do DRE (`*_total`, `resultado_*`), `paid_amount` do payable: **tudo vem da API**. O cliente só formata e exibe.
- **Editar/excluir conta financeira** e **reabrir conciliação fechada** — não há endpoint.
- **Registrar `ENTRADA` de estoque por movimento avulso** — só via Receber pedido (J3).
- **`/financeiro/movimentacoes` (lista geral) e `/financeiro/taxas`** — já existem (Fase 1 / Fee Sources), não reconstruir; reaproveitar.
- **Editor visual de regras de `column_mapping`** além do mapeamento simples de colunas (data/valor/descrição/direção) — o JSON é montado a partir de inputs diretos.
- **Ajuste manual e import de extrato** podem estar atrás de `require_action`/config do tenant — tratar 403/`require_action` com aviso, não simular permissão.

---

*Fonte de verdade de comportamento: `visao-estagio-0.md` + `openapi.json` (head `e0s25f_product_extras`); FSMs/enums conferidos em `app/domain/enums/`, `app/infrastructure/db/models/` e nos services. O protótipo `barberflow-system` é referência **visual apenas** (e não cobre o financeiro profundo). Onde divergir, vence este documento. Documento de planejamento — nenhuma regra de negócio vive no frontend.*
