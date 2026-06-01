# Financial Core — Domínio Financeiro

## Responsabilidade

O Financial Core registra a economia interna do tenant.
É a fundação sobre a qual Gestão Financeira, Despesas, Pagamentos,
Comissões e Estoque operam.

```
Financial Core DEFINE
  Contas (Account): onde o dinheiro fica
  Saldos por conta (derivados de Movements)
  Movimentações de dinheiro (Movement)
  Lançamentos econômicos (Entry)
  Vínculos entre movimentações e fatos operacionais
  TenantFeeRoutingPolicy
  Reconciliação manual (Level 1)

Financial Core NÃO DEFINE
  Como cobrar o cliente          → PaymentsEngine
  Como reservar tempo            → AgendaEngine
  Como calcular comissão         → CommissionEngine (Fase 3)
  Como gerenciar estoque         → StockEngine (Fase 3)
  Apresentação do dashboard      → Gestão Financeira UI (Fase 5)
```

---

## Entidades

### Account (Conta)
```
account_id          UUID PK
company_id          UUID FK → companies [RLS]
name                VARCHAR NOT NULL
type                VARCHAR NOT NULL
  -- CAIXA | ACQUIRER | BANK | ESCROW
provider            VARCHAR nullable
  -- ex: "asaas" (para conta ACQUIRER do Asaas)
external_ref        VARCHAR nullable
currency            CHAR(3) DEFAULT 'BRL'
status              VARCHAR DEFAULT 'ACTIVE'
is_default_inflow   BOOLEAN DEFAULT false
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
```

**Constraint:**
```sql
CREATE UNIQUE INDEX uq_default_inflow_provider
  ON accounts(company_id, COALESCE(provider, '__none__'))
  WHERE is_default_inflow = true;
```
Garante um único `is_default_inflow=true` por `(company_id, provider)`.
`COALESCE(provider, '__none__')` evita problema de NULL na unicidade.

**Setup automático:** ao criar um tenant (`create_company`), uma
Account CAIXA é criada automaticamente com `is_default_inflow=true`.

**Saldo:** nunca armazenado. Sempre derivado de `SUM(movements)`.
`compute_balance(account_id, as_of=None)` retorna o saldo atual ou
em uma data específica.

---

### Movement (Movimentação)

```
movement_id     UUID PK
company_id      UUID FK → companies [RLS]
account_id      UUID FK → accounts
type            VARCHAR NOT NULL
  -- INFLOW | OUTFLOW | TRANSFER_IN | TRANSFER_OUT
amount          NUMERIC(15,2) NOT NULL CHECK (amount > 0)
occurred_at     TIMESTAMPTZ DEFAULT now()
source_type     VARCHAR NOT NULL    # qual entidade originou
source_id       UUID NOT NULL       # ID da entidade originadora
transfer_id     UUID nullable FK → transfers
created_at      TIMESTAMPTZ DEFAULT now()
```

**⚡ Invariante de imutabilidade (CRÍTICA):**
- Trigger de banco (`movement_no_update`, `movement_no_delete`) rejeita
  UPDATE e DELETE com RAISE EXCEPTION
- `@validates` no ORM rejeita mutação após persistência (segunda camada)
- Correções são feitas por novos Movements de sinal oposto (NUNCA editando)

**Cardinalidade com Entry:** 1 Movement pode ter 0 ou 1 Entries.
Transfers criam 2 Movements e 0 Entries.

---

### Entry (Lançamento)

```
entry_id        UUID PK
company_id      UUID FK → companies [RLS]
type            VARCHAR NOT NULL
  -- RECEITA | CUSTO | DESPESA | TAXA | COMISSAO | ESTORNO | AJUSTE
direction       VARCHAR NOT NULL     # ADDS | SUBTRACTS
amount          NUMERIC(15,2) NOT NULL CHECK (amount > 0)
occurred_at     TIMESTAMPTZ DEFAULT now()
category        VARCHAR NOT NULL     # subcategoria do tipo (ver abaixo)
source_type     VARCHAR NOT NULL
source_id       UUID NOT NULL
movement_id     UUID nullable FK → movements
created_at      TIMESTAMPTZ DEFAULT now()
```

**⚡ Invariante de imutabilidade (CRÍTICA):**
Mesmos triggers e @validates do Movement.

**Categorias por tipo:**
```
RECEITA:   SERVICOS, PRODUTOS, PACOTE, ASSINATURA_ADESAO,
           ASSINATURA_RENOVACAO, SINAL_SERVICO, OUTROS

CUSTO:     INSUMOS_USO_INTERNO, PRODUTO_VENDIDO, MATERIAL_DESCARTAVEL,
           PERDA_ESTOQUE, PERDA_OPERACIONAL, OUTROS

DESPESA:   ALUGUEL, UTILITIES, MARKETING, SOFTWARE, CONTABILIDADE,
           LIMPEZA, MANUTENCAO, SALARIO, SERVICOS_PJ, ALIMENTACAO_COPA,
           EQUIPAMENTOS, TAXAS_BANCARIAS, TREINAMENTO, OUTROS

TAXA:      ACQUIRER_FEE, WITHDRAW_FEE, ANTECIPATION_FEE, OUTROS

COMISSAO:  COMISSAO_SERVICO, COMISSAO_VENDA, COMISSAO_RENOVACAO,
           COMISSAO_PERSONALIZADA

ESTORNO:   REEMBOLSO_CLIENTE, CHARGEBACK, REVERSAO_TAXA

AJUSTE:    CONTAGEM_CAIXA, CONTAGEM_ESTOQUE, CORRECAO_LANCAMENTO,
           CORRECAO_COMISSAO, OUTROS
```

---

### Transfer (Transferência entre Contas)

```
transfer_id     UUID PK
company_id      UUID FK → companies [RLS]
from_account_id UUID FK → accounts
to_account_id   UUID FK → accounts
amount          NUMERIC(15,2) NOT NULL CHECK (amount > 0)
status          VARCHAR DEFAULT 'REQUESTED'
  -- REQUESTED | COMPLETED | FAILED
requested_at    TIMESTAMPTZ DEFAULT now()
completed_at    TIMESTAMPTZ nullable
failed_at       TIMESTAMPTZ nullable
failure_reason  VARCHAR nullable
notes           TEXT nullable
```

**Invariante:** Transfer COMPLETED cria exatamente 2 Movements:
- Movement TRANSFER_OUT em `from_account`
- Movement TRANSFER_IN em `to_account`
Criados atomicamente. Sem Entry (Transfer é movimentação, não fato econômico).

---

### ReconciliationRecord

```
reconciliation_id   UUID PK
company_id          UUID FK → companies [RLS]
account_id          UUID FK → accounts
status              VARCHAR DEFAULT 'OPEN'  -- OPEN | CLOSED
opened_at           TIMESTAMPTZ DEFAULT now()
closed_at           TIMESTAMPTZ nullable
opened_by           UUID FK → users
closed_by           UUID nullable FK → users
notes               TEXT nullable
```

---

### MovementReconciliation

```
id                  UUID PK
company_id          UUID FK → companies [RLS]  # desnormalizado para RLS
movement_id         UUID FK → movements
reconciliation_id   UUID FK → reconciliation_records
reconciled_at       TIMESTAMPTZ DEFAULT now()
reconciled_by       UUID FK → users
UNIQUE(movement_id, reconciliation_id)
```

**Design:** Movement é 100% append-only. A reconciliação é registrada
numa tabela de vínculo separada. O Movement nunca é alterado.

---

### CashCount (Contagem de Caixa)

```
cash_count_id       UUID PK
company_id          UUID FK → companies [RLS]
account_id          UUID FK → accounts
expected_amount     NUMERIC(15,2)   # compute_balance() no momento
counted_amount      NUMERIC(15,2)   # valor físico contado
discrepancy         NUMERIC(15,2)   # counted - expected
resolution          VARCHAR         # ADJUSTED | NO_ADJUSTMENT
notes               TEXT nullable   # OBRIGATÓRIO se discrepancy != 0
entry_id            UUID nullable FK → entries  # Entry AJUSTE se ADJUSTED
created_by          UUID FK → users
created_at          TIMESTAMPTZ DEFAULT now()
```

**Lógica:** se `resolution=ADJUSTED` e `discrepancy != 0`:
- `notes` obrigatório (HTTP 422 se ausente)
- Chama `create_manual_adjustment` no FinancialCoreEngine
- Movement INFLOW (se discrepancy > 0) ou OUTFLOW (se < 0)
- Entry AJUSTE, category=CONTAGEM_CAIXA
- `cash_count.entry_id` vinculado à Entry criada

---

### TenantFeeRoutingPolicy

```
policy_id           UUID PK
company_id          UUID FK → companies [RLS]
fee_source          VARCHAR NOT NULL
  -- ASAAS_PIX | ASAAS_CARD | MAQUININHA_DEBIT | MAQUININHA_CREDIT
  -- | ANTECIPACAO | ESTORNO | RECORRENTE_FEE
client_share        NUMERIC(5,2) DEFAULT 0
tenant_share        NUMERIC(5,2) DEFAULT 100
professional_share  NUMERIC(5,2) DEFAULT 0
CONSTRAINT shares_sum_100 CHECK (client_share + tenant_share + professional_share = 100)
UNIQUE(company_id, fee_source)
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
```

**Design:** sem FK em `tenant_configs`. Lookup por `(company_id, fee_source)`.
Chave natural, não sintética.

**Setup automático:** 7 políticas criadas no `create_company` com
`tenant_share=100%` (barbearia absorve todas as taxas por padrão).

**Invariante:** `client_share + tenant_share + professional_share = 100`.
HTTP 422 se violado via API.

---

## FinancialCoreEngine (Service Central)

`app/modules/financial_core/service.py`

### API Pública (chamável por outros módulos)

```python
# Queries
get_account(account_id, company_id, db) → Account
list_accounts(company_id, db) → list[Account]
compute_balance(account_id, as_of=None, company_id=None, db=None) → Decimal
list_movements(company_id, filters, db) → list[Movement]
list_entries(company_id, filters, db) → list[Entry]
aggregate_dre(company_id, date_from, date_to, db) → dict
list_unreconciled_movements(account_id, company_id, db) → list[Movement]

# Handlers (chamados por outros módulos via evento ou diretamente)
handle_payment_confirmed(
    payment_id, gross_amount, provider_fee,
    target_account_id, fee_source, company_id, db
) → dict  # {"inflow": Movement, "revenue_entry": Entry, ...}

handle_payment_refunded(
    payment_id, amount, account_id, company_id, db
) → tuple[Movement, Entry]

create_manual_adjustment(
    amount, direction, category, account_id,
    reason, actor_id, company_id, db
) → tuple[Movement, Entry]
```

### API Privada (apenas interna ao módulo)

```python
_record_movement(...) → Movement   # NÃO expor como endpoint
_record_entry(...) → Entry         # NÃO expor como endpoint
```

### Handlers adiados (Fase 3)
```python
# handle_expense_paid   → Sprint 18 (Expense module)
# handle_commission_paid → Sprint 12 (CommissionEngine)
```

### Fluxo de handle_payment_confirmed

```
INPUT: gross_amount=100, provider_fee=2, fee_source="ASAAS_PIX"

NUMA ÚNICA TRANSAÇÃO:
  _record_movement(INFLOW, 100, account=ACQUIRER, source=payment)
  _record_entry(RECEITA, ADDS, 100, category=SERVICOS, movement=inflow)

  se provider_fee > 0:
    _record_movement(OUTFLOW, 2, account=ACQUIRER, source=payment)
    _record_entry(TAXA, SUBTRACTS, 2, category=ACQUIRER_FEE, movement=fee_outflow)
```

---

## Fluxos Canônicos (13 cenários)

**Fluxo 1 — Pagamento via Asaas (PIX, com taxa)**
```
payment.confirmed
  → Movement INFLOW R$100 (ACQUIRER) + Entry RECEITA R$100
  → Movement OUTFLOW R$2 (ACQUIRER, taxa) + Entry TAXA R$2
```

**Fluxo 3 — Pagamento em dinheiro**
```
payment.confirmed (provider_fee=0, fee_source=None)
  → Movement INFLOW R$100 (CAIXA) + Entry RECEITA R$100
  → SEM taxa
```

**Fluxo 7 — Saque do Asaas para banco**
```
Transfer(ACQUIRER → BANK)
  → Movement TRANSFER_OUT R$98 (ACQUIRER)
  → Movement TRANSFER_IN R$98 (BANK)
  → SEM Entry
Taxa de saque (se houver):
  → Movement OUTFLOW separado + Entry TAXA (WITHDRAW_FEE)
```

**Fluxo 10 — Reembolso ao cliente**
```
payment.refunded
  → Movement OUTFLOW (do account original) + Entry ESTORNO (REEMBOLSO_CLIENTE)
  → Movement original NÃO alterado
```

**Fluxo 11 — Ajuste manual de caixa**
```
manual_adjustment (OWNER/ADMIN + reason obrigatório)
  → Movement INFLOW ou OUTFLOW + Entry AJUSTE
  → record_sensitive_action gravado
```

---

## Invariantes do Financial Core

1. **Movements são imutáveis.** Trigger de banco rejeita UPDATE/DELETE.
2. **Entries são imutáveis.** Idem.
3. **Toda movimentação tem origem rastreável.** `source_type + source_id` obrigatórios.
4. **Saldo é derivado.** Nunca armazenado como dado primário.
5. **Transfer não cria Entry.** Apenas 2 Movements.
6. **`_record_movement` e `_record_entry` são privados.** Nenhum módulo externo os chama diretamente.
7. **`handle_expense_paid` e `handle_commission_paid` não existem ainda.** Adicionados nas Fases 3 respectivas.
8. **`accounting_mode=ACCRUAL` bloqueado.** Trigger de banco em `tenant_configs`.