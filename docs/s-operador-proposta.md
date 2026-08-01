# S-operador — investigação dirigida e proposta de sprint

**Sessão READ-ONLY** — investigar e propor; não implementar.
**Data:** 2026-08-01. Sucede [`inv-operador.md`](inv-operador.md).

> **Proveniência.** Redigido na sessão de investigação dirigida de 2026-08-01,
> que rodava em modo de planejamento — o documento não chegou a `docs/` na época.
> Reconstruído a partir do transcript, **sem re-investigar**. Números e
> referências `arquivo:linha` são os do momento da medição.

---

## O princípio que orienta tudo (decisão do Silva)

> **Quantidade sim, valor somado não.**

O que separa não é a natureza do dado — é a **granularidade**:

| | OPERATOR vê |
|---|---|
| **Transacional / unitário** | ✅ o preço daquele serviço, o valor daquela despesa, o total daquele agendamento |
| **Contagem** | ✅ "12 despesas pendentes", "3 fornecedores", "8 atendimentos hoje" |
| **Valor agregado** | ❌ "Caixa do dia: R$ 1.240", "R$ 4.200 a pagar", faturamento, DRE, margem |

Racional: a recepção lança a conta de luz, cadastra fornecedor, registra compra
de material — isso é dia a dia. O **total** do mês é resultado, e é do dono.

Aplicado como **teste** a cada tela: *um número de dinheiro que soma mais de uma
transação é agregado; um número que descreve uma transação, ou que conta itens,
não é.*

---

## 1. `confirm-manual` — o que faz, quem chama, veredito

### O que é

Wrapper fino de `confirm()` (`payments/service.py:552-628`). **Não tem
discricionariedade:**

- **Não aceita valor.** Cobra `payment.net_charged_amount`, já fixado na criação
  (`:617-620`). O operador não altera nada.
- **Não dá desconto.** Desconto manual é endpoint separado — `/manual-discount`
  (`payments/router.py:185`), OWNER/ADMIN, `reason` obrigatório,
  `record_sensitive_action` e `manual_override_count += 1`
  (`service.py:826-841`).
  🔎 **`confirm_manual` nunca toca `manual_override_count`.** A suspeita do
  enunciado — de que o contador indicaria um caminho de exceção — **não se
  confirma**: o caminho de exceção é o `/manual-discount`, não este.
- **Não alcança pagamento digital.** 422 se não for CASH ou `provider=manual`
  (`:576-587`). O racional está registrado no plano original: *"deve ser
  RESTRITO a CASH/manual para evitar bypass do processo de confirmação por
  webhook"* (`docs/plano-sprint-integracoes.md:689`) — **a proteção real é essa,
  e ela independe de papel.**
- **É idempotente.** `event_id = f"manual-{payment_id}"` (`:589`); re-submit em
  CONFIRMED devolve o mesmo pagamento (`:592-598`).
- Calcula MDR pela `TenantFeeRoutingPolicy`; sem taxa configurada confirma e
  devolve `fee_warning`.

### Quem chama — 4 superfícies, todas do painel

| Chamador | Papel da tela |
|---|---|
| `PaymentOnCompleteDialog.tsx:136` | **balcão** — conclusão do atendimento |
| `financeiro/pagamentos/novo/page.tsx:160` | gestão (tela já com guard OWNER/ADMIN) |
| `financeiro/pagamentos/page.tsx:109` | gestão (botão sob `canConfirm`) |
| `payments/[id]/page.tsx:182` | gestão |

Serve gestão **e** balcão, mas é sempre a mesma operação — "recebi o dinheiro
deste pagamento". Não há poder de gestão embutido nela.

### A assimetria foi acidente, não decisão

`POST /payments` nasceu `get_current_user` no commit original da Fase 2
(`c3bccce`) e nunca mudou. O `(OWNER/ADMIN)` do `confirm-manual` aparece na
especificação **sem justificativa alguma** — foi o reflexo "escrita financeira =
OWNER/ADMIN" do resto do módulo. Nenhum comentário, teste ou decisão registrada
defende o papel; toda a fundamentação escrita trata da restrição CASH/manual.

### 🔎 Veredito: **ampliar o guard**, não criar caminho novo

A propriedade de segurança que importa (não confirmar cobrança digital sem
webhook) mora no 422 e continua intacta. Um endpoint paralelo duplicaria
idempotência, cálculo de MDR e `fee_warning` — e o `inv-operador.md` já registrou
que duplicação de caminho é justamente o que produz o `Payment` órfão. Custo:
uma linha de dependência + teste de RBAC.

⚠️ **Não ampliar junto:** `/manual-discount`, `/refund`, `GET /payments`.

---

## 2. Agregados nas telas que OPERATOR mantém

Varredura completa do menu do OPERATOR, aplicando a regra.

### Nenhum agregado — 13 telas

`despesas`, `payables`, `fornecedores`, `estoque`, `estoque/movimentacoes`,
`customers`, `fila`, `operacoes`, `agenda`, `inbox`, `services`, `products`,
`catalogo/categorias`.

Verificado por ausência de `reduce(`, de faixa de KPI e de rodapé de totalização
em todos eles. **Todo dinheiro exibido é por linha.**

### Parecem agregado e não são — manter

- `estoque/page.tsx:66,220` "Total (prévia)" = soma dos itens **daquele** pedido
  de compra → total da transação sendo montada. ✅
- `estoque/page.tsx:321` `avg_cost` → atributo unitário do produto. ✅
- `payables/page.tsx:396` coluna "Total" → `total_amount` **de cada** conta. ✅
- `agenda/page.tsx:270` "N agend." no seletor de dia → contagem. ✅

### Agregados reais — 5, concentrados em 2 telas

| Onde | O que soma | Troca proposta |
|---|---|---|
| `dashboard/page.tsx:602-608` KPI "Caixa do dia" | `net_charged_amount` de **todos** os Payment CONFIRMED do dia (`:567-570`) | **remover**; no lugar, contagem "a concluir" |
| `dashboard/page.tsx:672-687` "Cobranças pendentes" | lista PENDING com valores de outros atendimentos | contagem "N cobranças pendentes", ou remover |
| `caixa/page.tsx:91` "Entradas" | soma dos movimentos INFLOW do dia | remover do perfil |
| `caixa/page.tsx:99` "Saídas" | soma dos OUTFLOW do dia | remover do perfil |
| `caixa/page.tsx:107` "Saldo" | `inflow − outflow` | remover do perfil |

### Zona cinzenta — não é soma, mas é razão de gestão

- `caixa/page.tsx:280` `expected_amount` da contagem = saldo esperado da gaveta.
  É acumulado, não transação. **Recomendo tratar como agregado.**
- `financeiro/pagamentos` — lista de todos os pagamentos do tenant. Cada linha é
  transação (passa na regra), mas o conjunto é o razão financeiro. **Recomendo
  tirar do menu do OPERATOR** — o balcão não precisa dela (ver §3).

---

## 3. O acoplamento cobrança ↔ dashboard

**A boa notícia: não há acoplamento obrigatório.** O caminho do balcão **não lê
lista de pagamento nenhuma.**

O `PaymentOnCompleteDialog` usa `POST /payments` (✅ aberto) → guarda o
`created.payment_id` **da própria resposta** → `confirm-manual` →
`PATCH /complete` (`:126-140`). As outras duas chamadas da tela,
`available-credit` e `pending-products`, já são abertas
(`appointments/router.py:200,235`). **`GET /payments` nunca entra no fluxo.**

Logo os dois cenários se separam:

| Se ampliar… | Efeito |
|---|---|
| **só `confirm-manual`** | o balcão fecha atendimento com pagamento ponta a ponta; o dashboard continua exibindo "—" (o `makeGuard` engole o 403 de `GET /payments`, `dashboard/page.tsx:254-265`); **nenhum agregado aparece** |
| **também `GET /payments`** | 🔴 o KPI "Caixa do dia" e o painel "Cobranças pendentes" **acendem no mesmo deploy** — o vazamento nasce no dia em que o balcão começa a funcionar. E `/financeiro/pagamentos` (hoje no menu do OPERATOR) vira o razão completo do tenant |

**Consequência para o sprint:** a correção da cobrança **não força** a do
dashboard. Mas o dashboard precisa ser refeito de qualquer forma — hoje ele
mostra "—" e "Não foi possível carregar" para o único papel que deveria usá-lo.
A recomendação é **não abrir `GET /payments`** e reescrever o dashboard sem ele:
assim os dois problemas morrem juntos e o agregado nunca chega a existir.

**Efeito colateral aceito:** `appointments/[id]` continua sem mostrar o sinal
para OPERATOR — o `GET /payments` daquela tela está em `try/catch` aninhado
(`:56-64`) e degrada em silêncio. Se o sinal for necessário no balcão, o caminho
certo é um endpoint por agendamento, não a lista.

---

## 4. Proposta de sprint

Ordem = caminho crítico. **Sem migration em nenhum item.**

| # | Item | Tam. | Depende de |
|---|---|---|---|
| 1 | **Cobrança** — incluir OPERATOR no guard do `confirm-manual` (`payments/router.py:170`). Manter o 422 CASH/manual; manter `/manual-discount` e `/refund` em OWNER/ADMIN. **Não** abrir `GET /payments`. Teste de RBAC + teste do percurso `POST /payments → confirm-manual → PATCH /complete` | **P** | — |
| 2 | **Convite** — restaurar o Select de papel no `InviteDialog` (`settings/usuarios/page.tsx:93`), alimentado por `ASSIGNABLE_ROLES_BY_ACTOR` (`constants.ts:456`, já correto). Reverte o essencial de `121921e`. O vínculo opcional a profissional continua | **P** | — |
| 3 | **Dashboard de OPERATOR** (`dashboard/page.tsx:514-692`) — **remover o fetch de `/payments`** (`:534`) e os dois agregados. KPIs por contagem, das fontes já abertas ao papel: **Atendimentos hoje** (`GET /appointments/?hoje`), **A concluir** (mesma lista, `SCHEDULED` com `start_at` passado — transforma o passivo em fila de trabalho), **Na fila** (`GET /waitlist/entries`). Painéis mantidos: Agenda do dia, Fila, Atendimento humano | **M** | 1 (mesma entrega) |
| 4 | **Telas com agregado** — nada a fazer fora do dashboard e do `/caixa`; a varredura da §2 saiu limpa. Item existe só para registrar o resultado | **—** | — |
| 5 | **Menu × acesso** — tirar **Pagamentos** (`Sidebar.tsx:137`) do OPERATOR. **Caixa** (`:138`) exige decisão (ver achado 1) | **P–M** | decisão |
| 6 | **Guard por papel** (defesa em profundidade) — estender o `useEffect` de `layout.tsx:26-35` para bloquear OPERATOR em `/financeiro/*`, `/relatorios` e `/comissoes/*`, trocando erro de API por redirect limpo | **P** | 5 |

**Não entra:** abrir `GET /payments`; mexer em `/manual-discount` ou `/refund`;
`permission_overrides` (o mecanismo do `require_action` segue sem uso e não é
necessário aqui); mudança de enum ou schema; a limpeza dos `SCHEDULED` passados
(é operação, sprint próprio).

---

## 5. Achados fora de escopo (registrar, não corrigir)

1. 🟠 **`/caixa` foi desenhada para o OPERATOR e está quebrada por um guard.**
   `GET`/`POST /financial/cash-counts` e `GET /financial/accounts/{id}/balance`
   **já permitem OPERATOR** (`financial_core/router.py:60,302,312,101`), mas a
   tela precisa de `GET /financial/accounts` (`:124`, `_owner_admin`) para listar
   as contas → a aba inteira erra. A intenção original do backend contradiz o
   efeito atual.
   **Decisão:** (a) tirar `/caixa` do menu do OPERATOR, ou (b) abrir
   `GET /financial/accounts` ao papel e esconder a faixa Entradas/Saídas/Saldo,
   mantendo só a contagem de gaveta. Recomendo (a) — a aba "Movimentações do dia"
   é substrato de DRE.
2. 🟡 **`fee_warning` manda o balcão para uma tela que ele não abre.**
   `PaymentOnCompleteDialog.tsx:222` abre `/financeiro/taxas`, cuja guarda é
   OWNER/ADMIN/PROFESSIONAL (`taxas/page.tsx:43`) → OPERATOR verá "sem acesso".
   Assim que a cobrança funcionar, o aviso de taxa não configurada vira beco sem
   saída. Trocar por "avise o responsável" quando o papel for OPERATOR.
3. 🟡 **Brecha de promoção.** A aba Membros ainda oferece OPERATOR no Select de
   papel (`settings/usuarios/page.tsx:360`) — dá para **promover** alguém, só não
   para **convidar**. Some com o item 2 do sprint.
4. 🟡 **`confirm-manual` não deixa rastro.** `refund` e `manual-discount` chamam
   `record_sensitive_action` (`service.py:718,828`); `confirm_manual` não. Com
   mais um papel confirmando recebimento, "quem bateu o caixa" passa a importar.
   Não bloqueia o sprint.

---

## Posfácio — o que foi executado

O item 1 (e a decisão sobre o `/caixa`) virou o sprint de backend
**S-operador-BACK**, entregue em `feat/operador-backend`. Ver
[`s-operador-backend.md`](s-operador-backend.md). Lá o princípio foi refinado
para **"o operador vê a operação corrente (o dia); o dono vê o acumulado"**, que
subsume esta regra: a soma do **dia corrente** é operação; a que atravessa dias é
resultado.

Os itens 2, 3, 5 e 6 são o sprint de frontend, ainda pendente.
