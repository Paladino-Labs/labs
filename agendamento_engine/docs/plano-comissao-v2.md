# Plano: Novo Modelo de Comissão v2 (3 opções de taxa)

**Data:** 2026-06-08
**Sessão:** análise pré-sprint — nenhum arquivo de código modificado
**Classificação:** MODERADO — requer cuidado com migração de dados; executável em uma sessão

---

## 1. Valores exatos dos enums no banco

### Descoberta crítica: NÃO são PostgreSQL enums

A migration `f3g4h5i6j7k8` criou as tabelas com colunas **VARCHAR NOT NULL**,
não com tipos `CREATE TYPE ... AS ENUM`. Isso é confirmado pela DDL:

```sql
commission_base       VARCHAR NOT NULL,
commission_fee_policy VARCHAR NOT NULL,
```

**Consequência direta:** nenhum `ALTER TYPE ... ADD VALUE` é necessário.
Os novos valores (`BARBERSHOP_PAYS`, `SPLIT_50_50`, `BARBER_PAYS`) podem ser
gravados assim que o código Python for atualizado. A migration precisa apenas
fazer `UPDATE` nas linhas existentes.

### Valores atuais em uso no banco

| Campo | Valores ativos | Comentário no ORM |
|---|---|---|
| `commission_base` | `GROSS_SERVICE` \| `NET_SERVICE` \| `GROSS_OPERATION` \| `CUSTOM_AMOUNT` | ver models/commission.py linha 19 |
| `commission_fee_policy` | `BEFORE_FEES` \| `AFTER_FEES` | ver models/commission.py linha 21 |

---

## 2. Lógica atual de calculate_commission() com exemplo

**Parâmetros:** gross=100, fee=3, rate=40%

```
base = gross_amount  # ponto de partida

GROSS_SERVICE  → base = 100  (bruto)
NET_SERVICE    → base = 100  (FALLBACK para bruto; desconto indisponível — linha 83)
GROSS_OPERATION → base = 100 (bruto)
CUSTOM_AMOUNT  → retorna fixed_amount diretamente (ignora rate e fee)

Se AFTER_FEES: base = base − fee

Se base < 0: base = 0

commission = base × (rate / 100)
```

| commission_base | commission_fee_policy | base | commission |
|---|---|---|---|
| GROSS_SERVICE | BEFORE_FEES | 100 | **40.00** |
| GROSS_SERVICE | AFTER_FEES | 97 | **38.80** |
| NET_SERVICE | BEFORE_FEES | 100 | **40.00** (fallback para gross) |
| NET_SERVICE | AFTER_FEES | 97 | **38.80** (fallback para gross − fee) |
| GROSS_OPERATION | BEFORE_FEES | 100 | **40.00** |
| GROSS_OPERATION | AFTER_FEES | 97 | **38.80** |
| CUSTOM_AMOUNT | — | — | **25.00** (fixed_amount, ignora fee/rate) |

---

## 3. Diagnóstico do problema de labels em inglês no frontend

### Situação atual no código

Os dicionários em `painel/app/(dashboard)/comissoes/politicas/page.tsx` já estão
**totalmente em português** (commit `aa282d3` — "fix(frontend): traduz labels em inglês
para portugues no painel"):

```typescript
const BASE_LABELS: Record<string, string> = {
  GROSS_SERVICE:   "% sobre valor bruto",
  NET_SERVICE:     "% sobre valor líquido",
  GROSS_OPERATION: "% sobre operação bruta",
  CUSTOM_AMOUNT:   "Valor fixo (R$)",
}

const FEE_POLICY_LABELS: Record<string, string> = {
  BEFORE_FEES: "Antes das taxas",
  AFTER_FEES:  "Após as taxas",
}
```

Os `SelectItem` usam `value={value}` (chave do enum) e renderizam `{label}` (PT).
Na tabela: `{BASE_LABELS[policy.commission_base] ?? policy.commission_base}` —
fallback seguro para o valor bruto se a chave não existir no mapa.

### Causa raiz dos labels em inglês (se ainda visíveis)

**Stale bundle do Vercel.** O commit `aa282d3` foi feito em 2026-06-08 e o fix
está no código-fonte atual. Se o painel em produção ainda mostra inglês, o deploy
ainda não foi ativado. **Ação:** forçar redeploy no Vercel após as mudanças de backend
desta sprint (um deploy resolverá ambos os itens).

Não há bug residual no código — nenhuma linha a corrigir.

---

## 4. Novo modelo aprovado pelo produto

Três opções que **sempre calculam sobre o valor bruto**. A diferença é quem absorve
a taxa do gateway de pagamento.

| Nova opção | Fórmula | gross=100, fee=3, rate=40% |
|---|---|---|
| `BARBERSHOP_PAYS` | `rate × gross` | **R$40,00** (barbearia absorve toda a taxa) |
| `SPLIT_50_50` | `(rate × gross) − (fee / 2)` | **R$38,50** (taxa dividida igualmente) |
| `BARBER_PAYS` | `(rate × gross) − fee` | **R$37,00** (barbeiro absorve toda a taxa) |

**Regra adicional:** `commission_amount` nunca pode ser negativo.
Se `(rate × gross) − fee < 0`: `commission_amount = 0`.

---

## 5. Análise de impacto: commission_base no novo modelo

Com o novo modelo, `commission_base` perde relevância parcial:

| Valor | Status no novo modelo |
|---|---|
| `GROSS_SERVICE` | **Base padrão** — a única base percentual ativa |
| `NET_SERVICE` | Obsoleto (fallback para gross desde a origem) — manter no banco para compatibilidade, **ocultar da UI** |
| `GROSS_OPERATION` | Obsoleto (sem distinção semântica de GROSS_SERVICE no atual codebase) — manter no banco, **ocultar da UI** |
| `CUSTOM_AMOUNT` | **Mantido** — valor fixo em R$, ignora fee policy |

**Proposta:** manter os 4 valores no VARCHAR (sem remoção), mas oferecer apenas
`GROSS_SERVICE` e `CUSTOM_AMOUNT` no frontend. Políticas existentes com
`NET_SERVICE`/`GROSS_OPERATION` continuam funcionando com o fallback de bruto.

---

## 6. SQL da migration

**Revision ID proposto:** `k3l4m5n6o7p8`
**down_revision:** `j2k3l4m5n6o7` (HEAD atual — fix_fee_source_names)
**Nome:** `commission_fee_policy_v2`

```sql
-- Passo 1: migrar dados existentes (BEFORE_FEES → BARBERSHOP_PAYS, AFTER_FEES → SPLIT_50_50)
-- Executar ANTES de qualquer mudança de código que passe novos valores

UPDATE commission_policies
   SET commission_fee_policy = 'BARBERSHOP_PAYS'
 WHERE commission_fee_policy = 'BEFORE_FEES';

UPDATE commission_policies
   SET commission_fee_policy = 'SPLIT_50_50'
 WHERE commission_fee_policy = 'AFTER_FEES';

-- Passo 2: não há DDL — colunas são VARCHAR, não enum PostgreSQL
-- Nenhum ALTER TYPE necessário.

-- Passo 3 (downgrade):
UPDATE commission_policies
   SET commission_fee_policy = 'BEFORE_FEES'
 WHERE commission_fee_policy = 'BARBERSHOP_PAYS';

UPDATE commission_policies
   SET commission_fee_policy = 'AFTER_FEES'
 WHERE commission_fee_policy = 'SPLIT_50_50';
-- BARBER_PAYS não tem equivalente seguro no downgrade; linhas com BARBER_PAYS
-- serão convertidas para BEFORE_FEES como fallback conservador.
UPDATE commission_policies
   SET commission_fee_policy = 'BEFORE_FEES'
 WHERE commission_fee_policy = 'BARBER_PAYS';
```

### Mapeamento semântico da migração de dados

| Valor antigo | Valor novo | Justificativa |
|---|---|---|
| `BEFORE_FEES` | `BARBERSHOP_PAYS` | Semanticamente equivalente: a barbearia não desconta taxa do barbeiro |
| `AFTER_FEES` | `SPLIT_50_50` | Aproximação razoável — o antigo subtraía 100% da taxa; o novo, 50% |

> **Atenção para produção:** verificar no Railway/Supabase quantas linhas existem
> em `commission_policies` antes de aplicar. Se houver políticas AFTER_FEES ativas,
> comunicar ao OWNER que o cálculo muda levemente (de 38.80 para 38.50 no exemplo).
> Para migração zero-risco, criar novas políticas e desativar as antigas manualmente.

---

## 7. Pseudocódigo de calculate_commission() atualizado

```python
def calculate_commission(
    professional_id, service_id, gross_amount,
    provider_fee, operation_type, appointment_id, company_id, db
):
    policy = _find_active_policy(professional_id, service_id, company_id, db)
    if policy is None:
        return None

    # CUSTOM_AMOUNT: valor fixo, ignora fee policy
    if policy.commission_base == "CUSTOM_AMOUNT":
        commission_amount = Decimal(str(policy.fixed_amount or 0))
    else:
        # Sempre base bruta no novo modelo
        gross_commission = gross_amount * (Decimal(str(policy.rate)) / Decimal("100"))

        if policy.commission_fee_policy == "BARBERSHOP_PAYS":
            commission_amount = gross_commission
        elif policy.commission_fee_policy == "SPLIT_50_50":
            commission_amount = gross_commission - (provider_fee / Decimal("2"))
        elif policy.commission_fee_policy == "BARBER_PAYS":
            commission_amount = gross_commission - provider_fee
        else:
            # Fallback seguro: trata BEFORE_FEES/AFTER_FEES legados se houver
            # (dados não migrados ou rollback parcial)
            if policy.commission_fee_policy == "AFTER_FEES":
                commission_amount = gross_commission - provider_fee
            else:  # BEFORE_FEES ou qualquer valor desconhecido
                commission_amount = gross_commission

    # Nunca negativo
    commission_amount = max(Decimal("0"), commission_amount).quantize(Decimal("0.01"))

    commission = Commission(
        company_id=company_id,
        professional_id=professional_id,
        policy_id=policy.policy_id,
        appointment_id=appointment_id,
        operation_type=operation_type,
        gross_amount=gross_amount,
        commission_amount=commission_amount,
        status="CALCULATED",
    )
    db.add(commission)
    db.commit()
    db.refresh(commission)
    return commission
```

### Diferenças em relação ao código atual

| Aspecto | Antes | Depois |
|---|---|---|
| Base para percentual | `base` variável com fallbacks por `commission_base` | Sempre `gross_amount` |
| Lógica de fee | `if AFTER_FEES: base -= fee` antes da multiplicação | Aplicada APÓS multiplicação, com 3 variantes |
| Quantize | aplicado uma vez no final | mantido — `commission_amount.quantize(Decimal("0.01"))` |
| Fallback legado | não existe | bloco `else` preserva compatibilidade com BEFORE_FEES/AFTER_FEES se migration não foi aplicada |

---

## 8. Labels novos para o frontend

### commission_fee_policy (campo "Quando calcular" → renomear para "Quem paga a taxa")

```typescript
const FEE_POLICY_LABELS: Record<string, string> = {
  BARBERSHOP_PAYS: "Barbearia paga a taxa",
  SPLIT_50_50:     "Taxa dividida (50/50)",
  BARBER_PAYS:     "Barbeiro paga a taxa",
  // legados (exibidos apenas se chegarem da API em dados históricos)
  BEFORE_FEES:     "Antes das taxas (legado)",
  AFTER_FEES:      "Após as taxas (legado)",
}
```

### commission_base (campo "Base de cálculo")

```typescript
const BASE_LABELS: Record<string, string> = {
  GROSS_SERVICE: "Percentual sobre valor bruto",
  CUSTOM_AMOUNT: "Valor fixo (R$)",
  // ocultos da UI mas mantidos para exibição de dados históricos
  NET_SERVICE:     "% sobre valor líquido (legado)",
  GROSS_OPERATION: "% sobre operação bruta (legado)",
}

// Apenas estas 2 opções aparecem nos selects de criação/edição
const BASE_OPTIONS_ACTIVE = [
  ["GROSS_SERVICE", "Percentual sobre valor bruto"],
  ["CUSTOM_AMOUNT", "Valor fixo (R$)"],
]
```

### Label do campo "Quando calcular" → renomear para "Taxa do gateway"

O novo modelo torna explícito quem absorve a taxa. Sugerido:
- Label do `<label>` element: **"Taxa do gateway (quem paga)"**
- Tooltip opcional: "Taxa cobrada pelo meio de pagamento (PIX, cartão, etc.)"

---

## 9. Testes a criar/atualizar em test_sprint12_commissions.py

### Testes existentes que precisam ser atualizados

| Teste atual | O que mudar |
|---|---|
| `test_gross_before_fees_40_percent` | Renomear para `test_barbershop_pays_40_percent`; trocar `BEFORE_FEES` → `BARBERSHOP_PAYS`; resultado esperado permanece **40.00** |
| `test_gross_after_fees_40_percent` | Renomear para `test_split_50_50_40_percent`; trocar `AFTER_FEES` → `SPLIT_50_50`; fee=2 → resultado muda de 39.20 para **(100×0.4)−(2/2) = 39.00** |
| `test_after_fees_with_real_fee_differs_from_before_fees` | Trocar `AFTER_FEES` → `SPLIT_50_50`; resultado de 38.80 muda para **38.50** (40.00 − 1.50); atualizar assert |

### Novos testes necessários (bloco `TestCalculateCommissionV2`)

```python
# 1. BARBERSHOP_PAYS — gross=100, fee=3, rate=40% → 40.00
def test_barbershop_pays_ignores_fee():
    ...
    assert commission.commission_amount == Decimal("40.00")

# 2. SPLIT_50_50 — gross=100, fee=3, rate=40% → 38.50
def test_split_50_50_halves_fee():
    ...
    assert commission.commission_amount == Decimal("38.50")

# 3. BARBER_PAYS — gross=100, fee=3, rate=40% → 37.00
def test_barber_pays_full_fee():
    ...
    assert commission.commission_amount == Decimal("37.00")

# 4. Nunca negativo — fee > gross_commission
def test_commission_never_negative():
    # gross=10, fee=50, rate=40% → gross_commission=4.00, 4.00-50=-46 → deve retornar 0.00
    ...
    assert commission.commission_amount == Decimal("0.00")

# 5. SPLIT_50_50 com fee ímpar → quantize correto
def test_split_50_50_odd_fee_quantized():
    # gross=100, fee=3, rate=40% → 40.00 − 1.50 = 38.50 (não 38.5000...)
    ...
    assert commission.commission_amount == Decimal("38.50")

# 6. Fallback legado BEFORE_FEES ainda funciona (dados não migrados)
def test_legacy_before_fees_still_works():
    # Garante compatibilidade se migration não foi aplicada
    ...
    assert commission.commission_amount == Decimal("40.00")
```

### Total de testes após mudanças

| Categoria | Antes | Depois |
|---|---|---|
| TestCalculateCommissionGross | 4 | 4 (3 renomeados/atualizados + 1 mantido) |
| TestCalculateCommissionV2 (novo) | 0 | 6 |
| Demais classes | sem mudança | sem mudança |
| **Total** | **25** | **~31** |

---

## 10. Revision ID da nova migration

```python
revision: str = "k3l4m5n6o7p8"
down_revision: str = "j2k3l4m5n6o7"  # fix_fee_source_names — HEAD atual
```

Arquivo: `agendamento_engine/migrations/versions/k3l4m5n6o7p8_commission_fee_policy_v2.py`

---

## 11. Resumo executivo e classificação

### Classificação: MODERADO

| Critério | Avaliação |
|---|---|
| Complexidade de migration | **Baixa** — apenas UPDATE de VARCHAR; nenhum DDL necessário |
| Risco de dados | **Médio** — migração AFTER_FEES→SPLIT_50_50 altera cálculos futuros levemente |
| Impacto em testes | **Médio** — 3 testes precisam ser atualizados + 6 novos |
| Impacto no frontend | **Baixo** — labels já em PT; apenas novos valores + novo label do campo |
| Sessões necessárias | **1** — backend + frontend + testes em uma única sessão |

### Ordem de execução recomendada

1. **Migration** `k3l4m5n6o7p8`: UPDATE das linhas existentes (sem DDL)
2. **Backend** — atualizar `calculate_commission()` com nova lógica + fallback legado
3. **Schemas** — adicionar comentários dos novos valores em `CommissionPolicyCreate`
4. **Testes** — atualizar 3 existentes + criar 6 novos
5. **Frontend** — atualizar `FEE_POLICY_LABELS`, `BASE_LABELS`, `BASE_OPTIONS`
   e renomear label "Quando calcular" → "Taxa do gateway"
6. **Deploy** — forçar redeploy no Vercel (resolve também os labels em inglês visíveis em produção)

### Pré-condição para execução

Verificar quantas linhas existem em produção com `BEFORE_FEES`/`AFTER_FEES`
antes de aplicar a migration. Se houver políticas ativas com `AFTER_FEES`,
comunicar ao OWNER que as comissões calculadas a partir do deploy serão
ligeiramente maiores (de `gross×rate − fee` para `gross×rate − fee/2`).
