# S-operador-FRONT — a tela do balcão

**Branch:** `feat/operador-frontend` (a partir de `main` = `393b369`) · **sem
push**, `CLAUDE.md` intocado. **Data:** 2026-08-02.

Sprint de frontend. Consome o contrato de
[`s-operador-backend.md`](s-operador-backend.md); nenhuma linha de backend foi
tocada.

---

## 1. O que mudou, tela por tela

| # | Arquivo | Mudança |
|---|---|---|
| 1 | `painel/app/(dashboard)/dashboard/page.tsx` | `OperatorDashboard` sem `GET /payments` e sem agregado de valor |
| 2 | `painel/app/(dashboard)/caixa/page.tsx` | OPERATOR vê só a conferência de gaveta |
| 3 | `painel/app/(dashboard)/recebimentos/page.tsx` | **tela nova** — `GET /payments/today` |
| 4 | `painel/components/Sidebar.tsx` | "Pagamentos" volta a ser OWNER/ADMIN; "Recebimentos" entra para OPERATOR |
| 5 | `painel/app/(dashboard)/settings/usuarios/page.tsx` | Select de papel restaurado no `InviteDialog` |
| 6 | `painel/app/(dashboard)/layout.tsx` | guard de OPERATOR nas rotas de resultado |
| 6b | `painel/components/FeeWarningBanner.tsx` + `PaymentOnCompleteDialog.tsx` | CTA de taxa só para quem pode abrir a tela |
| — | `painel/lib/constants.ts` | `ROLE_INVITE_HINTS` (glossário novo) |
| 7 | `painel/components/Sidebar.tsx` + `app/(dashboard)/configuracoes/page.tsx` | **ajuste pós-relato**: OPERATOR alcança a própria conta |

### 1. Dashboard do OPERATOR

Saiu: o fetch de `GET /payments` (403 para o papel), o KPI **"Caixa do dia"**
(soma dos `Payment` CONFIRMED do dia) e o painel **"Cobranças pendentes"**
(lista PENDING com valores). Com eles saíram `caixaDia`, `todayConfirmed` e
`pendingPayments`.

Entrou, tudo por **contagem**:

| KPI | Fonte | Cálculo |
|---|---|---|
| **Atendimentos hoje** | `GET /appointments/?start_after=…&start_before=…` | `length` |
| **A concluir** | mesma resposta | `status === "SCHEDULED"` **e** `start_at < agora` |
| **Na fila** | `GET /waitlist/entries` | `length` |

Painéis mantidos: Agenda do dia, Fila de espera, Atendimento humano. Na Agenda
do dia, os atendimentos vencidos ganharam um selo **"a concluir"** — o KPI dá o
número, a lista diz quais. Nenhum valor monetário sobrou na tela.

⚠️ **O recorte de "A concluir" é o dia corrente, não o passivo histórico.**
`GET /appointments/` não tem filtro de status (`router.py:38`: página, janela de
data, cliente, profissional — nada de status). Contar os 596 `SCHEDULED`
passados exigiria varrer o histórico inteiro no cliente, com teto de 200 por
página, ou uma rota nova — backend, fora de escopo. O KPI faz o passivo **parar
de crescer**; drená-lo continua sendo o sprint próprio já previsto.

### 2. `/caixa`

Para OPERATOR a página renderiza **só** `CashCountTab`, sem as abas. A faixa
Entradas/Saídas/Saldo saiu junto com a aba que a hospedava: aquela faixa é
derivada de `GET /financial/movements`, que é **403 para o papel** — mantê-la
sem a fonte seria uma aba permanentemente em erro. Subtítulo por papel:
"Conferência da gaveta." × "Movimentações e contagem do dia."

OWNER/ADMIN continuam com as duas abas, idênticas. A tela **não** chamava
`GET /financial/accounts/{id}/balance` (o único consumidor é
`financeiro/contas`), então o estreitamento #6 do backend não a afeta.

### 3. Pagamentos do dia — **tela própria** (`/recebimentos`)

**A decisão: tela própria, não adaptação por papel.** Três razões, em ordem de
peso:

1. **É o mesmo argumento que decidiu a Parte 1 do backend.** Adaptar
   `financeiro/pagamentos` faria uma tela com **dois contratos** conforme quem
   olha: `GET /payments` (lista completa, com filtro de data livre) para o dono,
   `GET /payments/today` (janela fixa, sem parâmetro) para o balcão. O backend
   recusou exatamente isso e escolheu a rota separada — a tela seguir por outro
   caminho desfaria a contenção no lugar onde ela é visível.
2. **O guard fica absoluto.** Com a tela do balcão fora de `/financeiro`, o
   guard do item 6 bloqueia `/financeiro/*` **inteiro** para OPERATOR, sem
   exceção a manter. Exceção em guard é dívida: a de `/financeiro/taxas` para
   PROFESSIONAL já custou um bug documentado no `painel/CLAUDE.md`.
3. **Metade da tela atual não faz sentido em um dia.** Filtro "De/Até",
   paginação de 20 e contagem de "registro(s)" existem porque a lista completa é
   grande. Numa janela de um dia civil são controles mortos.

A tela nova: lista `created_at DESC` como o backend entrega, colunas
Hora · Cliente · Método · Valor · Situação · Ações, filtro de situação
client-side e **nenhum totalizador**. O valor por transação fica — é como o
operador cobra. Ações: "Ver detalhes" (`/payments/{id}`, aberto ao papel) e
**Confirmar** para os `PENDING` de `provider=manual`, que o backend destravou
(`confirm-manual` agora aceita OPERATOR).

`financeiro/pagamentos` **não foi tocada**.

### 4. Menu

`Pagamentos` (`/financeiro/pagamentos`) voltou a ser `["OWNER","ADMIN"]`;
`Recebimentos` (`/recebimentos`) entrou como `["OPERATOR"]`.

Varredura do que o OPERATOR alcança hoje (medida no browser, papel real):
Dashboard, Agenda, Operações, Fila, Atendimento humano, Clientes, Catálogo
(Serviços/Produtos/Categorias), Recebimentos, Caixa, Despesas, Estoque,
Fornecedores, Contas a pagar. Nenhuma leva a tela de resultado.

Confirmado que **Despesas, Contas a pagar e Fornecedores não têm totalizador**:
o único `reduce` da área (`estoque/page.tsx:66`) soma os itens de **uma** ordem
de compra em digitação, e a coluna "Total" de `payables` é o valor **daquela**
conta. Ambos são transação, não acumulado. `payables` também chama
`GET /financial/accounts` — que este ciclo abriu ao papel, então deixou de ser
um 403 silencioso.

### 5. `InviteDialog`

Select de papel restaurado, alimentado por `ASSIGNABLE_ROLES_BY_ACTOR`
(OWNER convida os 4; ADMIN convida OPERATOR/PROFESSIONAL). Prop `actorRole` de
volta; título genérico "Convidar usuário"; o vínculo com profissional continua
opcional e volta a aparecer **só** quando o papel escolhido é PROFESSIONAL.

Dois cuidados:

- **O default não é `allowed[0]`.** Para OWNER isso seria "Proprietário", e um
  convite de proprietário por descuido é caro de desfazer. O default é
  PROFESSIONAL quando disponível — o convite mais comum e o menos poderoso da
  lista.
- **Cada papel explica o que alcança** (`ROLE_INVITE_HINTS`), porque a diferença
  entre Operador e Profissional não é óbvia para quem convida.

Com isso a assimetria da aba Membros (dava para **promover** a Operador, não
para **convidar**) desaparece.

### 6. Guard por papel

Efeito novo no `(dashboard)/layout.tsx`: OPERATOR em `/financeiro/*`,
`/relatorios` ou `/comissoes/*` → `router.replace("/dashboard")`. Sem exceções —
as superfícies do balcão vivem fora desses prefixos por construção. O guard de
PROFESSIONAL ficou intacto, com a exceção de `/financeiro/taxas` preservada.

É defesa em profundidade: quem responde 403 é o backend. O ganho é redirect
limpo em vez de tela de erro.

### 6b. `fee_warning`

`onConfigureClick` virou **opcional** no `FeeWarningBanner`. Quando ausente, o
banner troca o CTA "Configurar agora →" por orientação: o pagamento foi
registrado, o líquido saiu sem desconto de taxa, avise a gerência. O
`PaymentOnCompleteDialog` só passa o CTA para quem pode abrir `/financeiro/taxas`
(OWNER/ADMIN/PROFESSIONAL). `financeiro/pagamentos/novo` — o outro consumidor do
banner — é tela OWNER/ADMIN e não muda.

### 7. A própria conta do OPERATOR (ajuste pós-relato)

O item **Configurações** da Sidebar passou a incluir OPERATOR. Quem filtra o que
ele vê **não é o item pai — é `roleVisible` por subitem**: "Meu Perfil" e
"Segurança" são `"ALL"`; Taxas é `["OWNER","ADMIN","PROFESSIONAL"]`; Financeiro,
Integrações, Módulos e Branding são `["OWNER","ADMIN"]`. O submenu do operador
tem, portanto, exatamente duas entradas. As três rotas que ele usa —
`GET /auth/me`, `PATCH /auth/profile`, `POST /auth/change-password` — dependem só
de `get_current_user`, sem guard de papel.

**O hub `/configuracoes` precisou vir junto**, e essa é a parte não-óbvia: quando
a Sidebar está **recolhida**, `NavItemRow` renderiza o item pai como link para
`item.url` em vez do submenu. Sem tratar o hub, incluir o papel abriria uma porta
para 10 cards, 8 deles para telas que o guard bloqueia — exatamente o "menu que
leva a erro" que o sprint veio remover. O hub virou client component e filtra os
cards com as **mesmas roles do submenu**.

⚠️ **Efeito colateral deliberado no PROFESSIONAL:** ele via os 10 cards e agora vê
3 (Meu Perfil, Segurança, Taxas). Os 7 que sumiram levavam a telas que já lhe
respondiam 403 ou o redirecionavam — buraco pré-existente, fechado de passagem
porque a correção do OPERATOR o atravessa. OWNER/ADMIN continuam com os 10.

### O item 2 do relato — **não existia**

O achado 2 da versão anterior deste relatório (`/payments/{id}` não deixaria o
OPERATOR confirmar) estava **errado**, e nada foi alterado por causa dele.

O gate de papel na tela de detalhe é `canManage = isOwner || isAdmin`, mas ele
cobre **apenas** `DiscountDialog` e `RefundDialog`. O `ConfirmDialog` está sob
`{isPending && ...}`, sem papel nenhum — a tela sempre permitiu a confirmação.
O erro veio de ler o arquivo por `grep` de `isOwner`/`isAdmin` e generalizar o
gate para as três ações, em vez de conferir a linha de cada uma.

Verificado em execução (banco de dev, papel real): o botão "Confirmar
manualmente" aparece, `POST /payments/{id}/confirm-manual` responde 200 e o
pagamento passa a CONFIRMED. Depois disso o card "Ações" fica vazio para o papel
— desconto e estorno seguem fechados, como devem.

**Dívida pré-existente registrada de passagem** (não corrigida, vale para
OWNER/ADMIN também): a tela de detalhe oferece "Confirmar manualmente" para
**qualquer** `PENDING`, sem checar `provider == "manual"` — a lista faz esse
filtro. Numa cobrança digital pendente, o clique leva ao 422 do backend. O 422 é
a proteção correta; o que falta é a UI não oferecer o caminho.

---

## 2. Rótulos criados ou trocados

| Antes | Agora | Por quê |
|---|---|---|
| KPI "Agendamentos hoje" (operador) | **"Atendimentos hoje"** | o que acontece no balcão é atendimento; "agendamento" é o registro |
| KPI "Caixa do dia" | **"A concluir"** · legenda "horário já passou" | nomeia o que a pessoa controla, não o mecanismo (`SCHEDULED` vencido) |
| — | selo **"a concluir"** na Agenda do dia | liga o número à linha |
| — | título **"Recebimentos do dia"** · menu **"Recebimentos"** | "do dia" trunca no menu; o título da tela carrega o recorte |
| coluna "Status" | **"Situação"** (tela nova) | mesma palavra do filtro ao lado |
| "Confirmar pagamento" | **"Confirmar recebimento"** → toast "Recebimento confirmado" | a ação mantém o nome no fluxo inteiro |
| "Convidar profissional" | **"Convidar usuário"** | o diálogo voltou a ser genérico |
| — | `ROLE_INVITE_HINTS` (4 papéis) | quem convida precisa saber o que está dando |
| "Nenhum pagamento" | **"Nenhum recebimento hoje"** + "Cada pagamento registrado na conclusão de um atendimento aparece aqui." | estado vazio explica de onde vem a linha |
| CTA "Configurar agora →" (operador) | orientação sem link | não mandar a pessoa para onde ela não entra |

---

## 3. Verificação

### O ambiente — duas rodadas

**Rodada 2 (ajustes 7 e 2) — banco de dev reativado, verificação REAL.** Com o
Supabase de dev de volta, subi o backend da branch `feat/operador-backend`
apontado para ele e criei um OPERATOR **pelo fluxo real**: login do OWNER →
`POST /users/invite {role: OPERATOR}` → token lido da tabela `user_invitations`
→ `POST /auth/activate`. Isso revalidou o item 5 do lado do backend, de ponta a
ponta. Login no painel com `balcao@dev.paladino.app`, papel vindo do JWT real.

**Rodada 1 (itens 1–6b) — o dev estava fora do ar.** O pooler respondia
`FATAL: (ENOTFOUND) tenant/user postgres.tvguwtdfayhrctlpollf not found`, e o
`.env` local aponta para **produção**, onde semear operador e criar pagamentos de
teste seria ato de produção — não fiz, e não recomendo.

Aquela rodada correu contra um **mock do contrato** (`scratchpad/mock_api.py`,
não versionado): um servidor stdlib que devolve os payloads das rotas abertas e
**403 nas fechadas** (a lista de §2 do relatório de backend), registrando cada
requisição com papel, método, rota e status. Ele não é um backend — mas responde
a pergunta que é do frontend: *quais rotas o painel chama em cada papel, e em
que ordem*. A semântica do backend (a janela do dia civil, o 422 do
`confirm-manual`, os guards reais) já tem os 24 testes do sprint anterior.

O mock, aliás, pegou um erro **meu**, não do painel: fechei `/payments` para
qualquer método e o diálogo de conclusão quebrou com "Permissão insuficiente".
`GET /payments` é fechado; **`POST /payments` é aberto**. Corrigido no mock, o
fluxo passou.

Papel simulado por JWT não assinado no `localStorage` — o `AuthContext` lê o
papel do payload do token e o mock aceita qualquer assinatura.

**O que a rodada 2 confirmou do que a rodada 1 só havia mockado:** o dashboard do
OPERATOR carrega sem tocar em `/payments`; `/recebimentos` lista o dia real
(`GET /payments/today` → 1 transação, R$ 55,00, Confirmado, sem totalizador);
`POST /payments` é aceito para o papel (a cobrança de teste foi criada pelo
próprio operador).

### Os 6 pontos (rodada 1, contra o mock)

| # | Ponto | Resultado |
|---|---|---|
| 1 | OPERATOR vê o dashboard novo com as três contagens | ✅ Com 4 atendimentos no dia (2 vencidos SCHEDULED, 1 COMPLETED, 1 futuro) e 1 na fila: **4 · 2 · 1**. Log do mock sem nenhuma chamada a `/payments` |
| 2 | Conclui um atendimento com pagamento, ponta a ponta | ✅ Agenda → card → Concluir → Dinheiro → "Confirmar pagamento e concluir". Sequência exata do contrato: `POST /payments` (201) → `POST /payments/{id}/confirm-manual` (200) → `PATCH /appointments/{id}/complete` (200); tela final "Pagamento confirmado" |
| 3 | `/caixa` sem a faixa de agregados, e registra conferência | ✅ Sem abas e sem Entradas/Saídas/Saldo. Conferência registrada: `POST /financial/cash-counts` → 201 + recarga da lista. Zero chamadas a `/financial/movements` e a `/accounts/{id}/balance` |
| 4 | Não alcança `/financeiro/dre`, `/relatorios`, `/comissoes` | ✅ Os três + `/financeiro/pagamentos` → `location.pathname === "/dashboard"` |
| 5 | OWNER convida alguém como Operador | ✅ Diálogo com os 4 papéis e a legenda de cada um; `POST /users/invite` com body `{"email":"balcao2@leduc.com","role":"OPERATOR"}` → 201 |
| 6 | Nada regrediu para OWNER e PROFESSIONAL | ✅ Dashboard do OWNER com os 3 KPIs, gráfico, alertas, pendências e CRM; `/caixa` do OWNER com as 2 abas e a faixa; PROFESSIONAL sem vínculo cai no EmptyState de sempre e segue **entrando** em `/financeiro/taxas` e **sendo barrado** em `/financeiro/contas` |

### Os 2 ajustes pós-relato (banco de dev real, papel real)

| Ponto | Resultado |
|---|---|
| Sidebar do OPERATOR | ✅ Grupo **Administração → Configurações** com **exatamente** "Meu Perfil" e "Segurança". Nenhuma outra entrada apareceu (nav lida do DOM) |
| Hub `/configuracoes` | ✅ OPERATOR **2 cards**; PROFESSIONAL **3** (+ Taxas); OWNER **10** (inalterado) |
| Meu Perfil funciona | ✅ Tela carrega com os dados do operador; salvar nome → `PATCH /auth/profile` **200** |
| Segurança funciona | ✅ Troca de senha real → `POST /auth/change-password` **200**; o token anterior foi invalidado (`last_password_change_at`) e o painel exigiu novo login — comportamento correto. **Senha revertida** para o padrão do dev |
| `/payments/{id}` como OPERATOR | ✅ "Confirmar manualmente" presente; `POST .../confirm-manual` **200**; badge vira **Confirmado**; card "Ações" fica vazio (desconto/estorno seguem fechados) |

Além disso: **`npx tsc --noEmit` limpo**, **`npx next build` verde**
(`/recebimentos` e `/configuracoes` na lista de rotas) e **lint 52 problemas × 53
no baseline de `main`** — nenhum achado novo; o que sumiu foi um
`eslint-disable` que voltou a ter uso.

Também verificado que o `PaymentOnCompleteDialog` com OPERATOR mostra o banner
de taxa **sem** o CTA, com o texto de orientação (item 6b) — o `fee_warning` foi
forçado pelo mock, que é como ele apareceria com taxa não configurada.

---

## 4. Achados fora de escopo (registrados, não corrigidos)

1. ~~**OPERATOR não alcança "Meu Perfil" nem "Segurança".**~~ **CORRIGIDO** —
   item 7 acima.
2. ~~**`/payments/{id}` não deixa o OPERATOR confirmar.**~~ **ACHADO ERRADO** —
   sempre deixou; ver "O item 2 do relato" acima. No lugar dele fica a dívida
   real que a verificação revelou: **a tela de detalhe oferece "Confirmar
   manualmente" sem checar `provider == "manual"`** (a lista checa), então uma
   cobrança digital pendente leva o clique ao 422. Vale para todos os papéis.
3. **O guard de layout perde para uma página que estoura no primeiro render.**
   O redirect é um `useEffect` do layout: se a página filha lança durante a
   renderização, o efeito não chega a rodar. Vi isso com o DRE recebendo um
   payload malformado do mock. Não é vetor real (o backend responde 403 e o dado
   vem certo), mas confirma que **o guard é conforto, não contenção** — a
   contenção é do backend.
4. **A faixa de agregados de `/caixa` só existe porque a aba existe.** Se algum
   dia `GET /financial/movements` for aberto ao papel com janela escopada, a
   decisão de esconder a faixa precisa ser reafirmada de propósito, não herdada
   do 403.
5. **O `worktree` de `feat/operador-backend`** em `%TEMP%\claude\opback`
   (pré-existente a esta sessão) teve o `.env` sobrescrito por mim com o conteúdo
   de `.env.dev` — é por ele que a rodada 2 rodou o backend contra o dev.
   Inofensivo, mas registrado.
6. **O banco de dev ganhou um usuário e uma cobrança de teste**:
   `balcao@dev.paladino.app` (OPERATOR, senha padrão do dev) e um `Payment` de
   R$ 55,00 CONFIRMED do "Cliente Dois". Criados pelos fluxos reais, no **dev** —
   produção intocada.
7. **O hub `/configuracoes` não tinha filtro de papel nenhum** e é alcançável por
   URL direta por qualquer papel autenticado. Agora filtra, mas continua sendo
   uma **segunda fonte** das mesmas roles do submenu da Sidebar — duas listas que
   precisam ser mantidas em sincronia à mão. Unificar (uma tabela de roles por
   rota, consumida pelos dois) é housekeeping com dono.

## 5. Pendências que este sprint **não** tocou, por escopo

- Os **596 `SCHEDULED` passados** — operação, sprint próprio.
- As dívidas do Sprint 7 (`cash-counts` com histórico e `expected_amount`;
  `resolution=ADJUSTED` lançando ajuste contábil) — decisão do Silva, registradas
  no relatório de backend.
- `confirm-manual` sem `record_sensitive_action` — com um papel a mais
  confirmando recebimento, "quem bateu o caixa" passa a importar (achado 3 do
  backend).
