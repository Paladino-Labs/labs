# S-operador-BACK — rotas e guards do perfil de balcão

**Branch:** `feat/operador-backend` (a partir de `main` = `a7d8dc8`) · **sem
migration**.
O sprint foi executado sem tocar o `CLAUDE.md`; a seção "RBAC — papéis" foi
acrescentada depois, no passo de auditoria, com o diff do auditor.
**Data:** 2026-08-01.

Sprint de backend. Define o contrato que o sprint de frontend vai consumir.

> ⚠️ **Nota de registro — leia primeiro.**
> Este relatório sucede `docs/inv-operador.md` e `docs/s-operador-proposta.md`,
> mas **nenhum dos dois existe no disco**. As duas investigações foram feitas e
> aprovadas em sessões anteriores, porém o modo de planejamento daquelas sessões
> só permitia escrever no arquivo de plano — os documentos nunca chegaram a
> `docs/`. O conteúdo está no transcript das sessões; posso reconstruí-lo a
> pedido. O essencial para executar este sprint está reproduzido abaixo.

---

## 1. A decisão da Parte 1: **(b) endpoint separado, escopado por construção**

O enunciado deixou a escolha entre (a) reaproveitar os endpoints existentes com
filtro de data forçado por papel, e (b) endpoints já escopados. Com o código à
vista, **(a) não é contido**:

- **`GET /payments` não tem parâmetro nenhum.** `list_payments(company_id, db)`
  (`payments/service.py:315`) filtra só por tenant — sem data, sem paginação.
  Para fazer (a) eu teria que **primeiro criar** a superfície de data e **depois**
  forçá-la por papel: inventar o parâmetro só para restringi-lo. O mesmo endpoint
  passaria a ter dois contratos conforme quem chama, e o frontend não teria como
  saber qual recebeu.
- **Em `/financial/movements` seria pior.** Ele já aceita `date_from`/`date_to`
  do cliente (`financial_core/router.py:121`). Forçar a janela para OPERATOR
  significa **sobrescrever em silêncio** o que o caller pediu e responder 2xx —
  exatamente o modo de falha que o S0.1 documentou no webhook Asaas.
- **O teste #2 do enunciado decide.** "OPERATOR não consegue obter pagamento de
  outro dia, nem manipulando parâmetros" é **demonstrável de uma vez** em (b): a
  rota não tem parâmetro de data. Em (a) só se prova filtro a filtro, e cada
  filtro novo reabre a pergunta.

Mesmo racional do lease sobre o advisory lock no S2.1: **restrição por construção
vale mais que restrição por disciplina.**

**Verificado empiricamente** (smoke test contra o app real): parâmetros espúrios
não deslocam a janela, e o contrato OpenAPI de `/payments/today` declara **zero
parâmetros**.

```
GET /payments/today                                           → 200
  janela: 2026-08-01T03:00Z → 2026-08-02T03:00Z  (= 1 dia)
GET /payments/today?date_from=2020-01-01&day=…&as_of=…        → 200, janela IDÊNTICA
openapi paths./payments/today.get.parameters                  → []
```

### A exceção deliberada — onde (b) não se aplica

`GET /financial/accounts` devolve o **cadastro** de contas e nenhum valor
(`AccountResponse`: name/type/currency/status — `financial_core/schemas.py:89`).
Roster de conta é configuração, não dado temporal: **não há "dia" a escopar.** Ali
a ampliação do guard é a resposta certa, e o princípio continua satisfeito. Um
teste trava isso (`test_cadastro_de_conta_nao_expoe_valor`): se algum campo
monetário aparecer no schema, a decisão precisa ser revista.

---

## 2. Contrato de rotas do OPERATOR — insumo do sprint de frontend

### Pode chamar

| Rota | Método | Guard | Escopo | Não devolve |
|---|---|---|---|---|
| `/appointments/` | GET | autenticado | tenant; filtros de data livres | — (o papel vê todos) |
| `/appointments/` · `/{id}/cancel` · `/{id}/reschedule` | POST · PATCH | autenticado | unitário | — |
| `/appointments/{id}` · `/{id}/available-credit` · `/{id}/pending-products` | GET | autenticado | unitário | — |
| `/appointments/{id}/complete` | PATCH | autenticado | unitário | — |
| `/professionals/` · `/services/` · `/products/` · `/customers/` | GET | autenticado | tenant | — |
| `/payments` | POST | autenticado | unitário | — |
| `/payments/{id}` | GET | autenticado | unitário | — |
| **`/payments/{id}/confirm-manual`** | POST | **OWNER/ADMIN/OPERATOR** ⬅ novo | unitário | 422 se não for CASH/manual |
| **`/payments/today`** | GET | **OWNER/ADMIN/OPERATOR** ⬅ **rota nova** | **dia civil do tenant** | sem parâmetro de data; **sem totais**; não alcança outro dia |
| **`/financial/accounts`** | GET | **OWNER/ADMIN/OPERATOR** ⬅ novo p/ o papel | tenant (cadastro) | **sem saldo** |
| `/financial/cash-counts` | GET · POST | OWNER/ADMIN/OPERATOR | tenant (histórico) | pré-existente (Sprint 7) — ver achado 1 |
| `/waitlist/*` · `/conversations/*` · `/nps/*` · `/crm/config` (GET) | — | inalterado | — | — |

**`GET /payments/today`** — resposta `list[PaymentResponse]`, ordenada por
`created_at DESC`. Casa por **`created_at` OU `paid_at`** dentro da janela: a
cobrança criada ontem e recebida hoje é recebimento de hoje, e sem isso o
operador não encontraria o próprio caixa. Inclui PENDING e CONFIRMED — o balcão
precisa dos dois para saber se o cliente pagou.

### Continua fechado (403)

`GET /payments` (lista completa) · `/payments/{id}/manual-discount` ·
`/payments/{id}/refund` · `/financial/dre` · `/financial/movements` ·
`/financial/entries` · `/financial/transfers` · `/financial/reconciliation` ·
**`/financial/accounts/{id}/balance`** · `/financial/fee-policies` ·
`/commissions` · `/commission-policies` · `/financial/statement/*`.

---

## 3. Mudanças, e por quê

| # | Onde | Mudança |
|---|---|---|
| 1 | `payments/router.py:206` | `confirm_manual_payment`: `_owner_admin` → `_owner_admin_operator`. **O bloqueador.** |
| 2 | `payments/router.py:160` | **`GET /payments/today`** — rota nova, declarada **antes** de `/payments/{payment_id}` |
| 3 | `payments/service.py:325` | `list_payments_for_day(company_id, day_start, day_end, db)` — irmão escopado de `list_payments` |
| 4 | `tenant/service.py:26,49` | `get_tenant_timezone` + `current_day_bounds_utc` |
| 5 | `financial_core/router.py:71` | `list_accounts`: `_owner_admin` → `_owner_admin_operator` |
| 6 | `financial_core/router.py:112` | ⚠️ `get_account_balance`: `_owner_admin_operator` → `_owner_admin` (**estreitamento**) |

**O 422 permaneceu intocado.** A proteção real do `confirm-manual` — não
confirmar cobrança digital sem passar pelo webhook (`service.py:576`) — é o
`422 CASH/manual`, não o papel. É a única com racional escrito
(`docs/plano-sprint-integracoes.md:689`); o `(OWNER/ADMIN)` original apareceu na
especificação **sem justificativa**, reflexo do "escrita financeira = OWNER/ADMIN"
do resto do módulo. Um teste garante que o 422 sobrevive para o papel novo.

**⚠️ A ordem de declaração da rota é funcional, não estética.** O FastAPI casa na
ordem de declaração: `/payments/today` depois de `/payments/{payment_id}` cairia
no path param e viraria 422 de UUID inválido. Há teste travando a ordem.

**O "dia" é o do tenant, não o do servidor.** Railway roda em UTC; entre 21h e
meia-noite em Brasília o dia UTC já virou — e é justamente o fim do expediente do
balcão. `current_day_bounds_utc` calcula o dia civil no fuso do tenant e converte
para UTC, somando no horário de parede (correto sob DST, ainda que o Brasil não o
use hoje).

### O estreitamento (#6) — sinalizado

`GET /financial/accounts/{id}/balance` estava aberto ao OPERATOR por herança do
Sprint 7. `compute_balance` (`service.py:410`) soma o histórico inteiro da conta:
é **saldo consolidado**, que o enunciado nomeia explicitamente como o que não
entra. Fechei.

Não afeta a conferência de gaveta: `record_count` calcula o esperado no servidor
(`cash_count_service.py:49`); o body manda só
`account_id`/`counted_amount`/`resolution`/`notes`. Único consumidor da rota é
`financeiro/contas`, tela de gestão.

**É uma linha isolada** — trivial de reverter se o Silva preferir manter.

---

## 4. Suíte

```
baseline (branch, antes)  → 1324 passed · 12 failed · 6 skipped · 1 xfailed
depois                    → 1348 passed · 12 failed · 6 skipped · 1 xfailed
```

+24 testes novos (`tests/test_operador_backend.py`), **zero regressão**. As 12
falhas são as de `test_sprint2_rbac` que o revert do S2.1 desfez — idênticas
antes e depois, sprint próprio pendente.

⚠️ O enunciado previa 1324 → o baseline **medido** foi 1324, não 1330. Registro o
medido.

Os testes leem o `Depends(...)` **realmente wired** em cada endpoint (via
`inspect.signature`), não uma redeclaração — trocar o guard de uma rota faz o
teste falhar. Cobrem: o caminho do balcão nos 3 guards; ausência de `Payment`
órfão; ausência de parâmetro de data em `/payments/today`; a ordem de declaração;
o recorte do dia civil do tenant (23h30 em SP ainda é o dia anterior); o
fallback de timezone; o que continua fechado; a sobrevivência do 422; e
não-regressão de OWNER/ADMIN/PLATFORM_OWNER e a exclusão de
PROFESSIONAL/CLIENT.

**Lint:** os 2 achados do `ruff` nos arquivos tocados
(`financial_core/router.py`: `Decimal` e `get_current_user` não usados) são
**pré-existentes** — verificado com `git stash`. Não corrigidos: fora de escopo.

---

## 5. Achados fora de escopo (registrados, não corrigidos)

1. **`GET /financial/cash-counts` devolve o histórico inteiro ao OPERATOR**, com
   `expected_amount` (saldo esperado da conta) por linha. Permissão do Sprint 7,
   anterior a este princípio. Cada linha é um evento discreto, então passa na
   regra por pouco — mas o `expected_amount` é acumulado. **Decisão do Silva.**
   Não mexi: estreitar uma permissão pré-existente não estava no enunciado, e o
   #6 já é um estreitamento.
2. **`POST /financial/cash-counts` com `resolution=ADJUSTED` cria Movement +
   Entry** via `create_manual_adjustment` — o OPERATOR já podia lançar ajuste
   contábil desde o Sprint 7, sem que isso tenha sido decidido explicitamente.
   Mesma família do achado 1.
3. **`confirm-manual` não deixa rastro.** `refund` e `manual-discount` chamam
   `record_sensitive_action` (`service.py:718,828`); `confirm_manual` não. Com um
   papel a mais confirmando recebimento, "quem bateu o caixa" passa a importar.
4. **`GET /payments` sem paginação nem teto** (`service.py:315`) — já registrado
   pela A7; mais um motivo para não abri-lo ao papel.
5. **Dois resolvedores de fuso.** `get_tenant_timezone` (novo, em `tenant/`)
   duplica `appointments/service._resolve_tenant_tz:65`. Comportamento idêntico,
   documentado nos dois lados. Não unifiquei porque `_resolve_tenant_tz` está no
   caminho de **gravação** de horário, com histórico de bug no `CLAUDE.md` — risco
   desproporcional para este sprint. Housekeeping: fazer aquele delegar para este.
6. **`fee_warning` → beco sem saída: é frontend, e o backend não precisa mudar.**
   O `PaymentOnCompleteDialog` abre `/financeiro/taxas`, cuja guarda é
   OWNER/ADMIN/PROFESSIONAL — o operador verá "sem acesso". O `fee_warning` já é
   puramente informativo (`code`/`fee_source`/`fee_applied`/`message`) e o texto
   vem de `_fee_warning_message`. A correção é trocar mensagem/CTA por papel na
   tela; **nenhum campo novo é necessário no backend.**

---

## 6. O que o sprint de frontend precisa saber

- O fluxo do dialog de conclusão (`POST /payments` → `confirm-manual` →
  `PATCH /complete`) **funciona para OPERATOR sem nenhuma outra mudança de
  backend**. Ele não lê lista de pagamento nenhuma — usa o `payment_id` da
  resposta do próprio POST.
- Para "houve pagamento hoje?", usar **`GET /payments/today`**. Não usar
  `GET /payments` (403 para o papel).
- A tela `/caixa` pode listar contas e registrar/consultar conferência de gaveta,
  mas **não** pode exibir a faixa Entradas/Saídas/Saldo (`/financial/movements` e
  `/accounts/{id}/balance` são 403) — são agregados, e é o desenho pretendido.
- O dashboard de OPERATOR deve ser refeito **sem** `GET /payments` — hoje ele
  tenta somar o caixa do dia e é o único agregado do perfil.
