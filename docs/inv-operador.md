# INV-operador — religar o perfil de balcão

**Sessão READ-ONLY** — investigação, não correção. Nenhum código, migration ou
commit.
**Data da medição:** 2026-08-01 (queries de leitura contra o Supabase de
produção, ref `uhhygdqioqcgcfqfbmif`).

> **Proveniência.** Este relatório foi redigido na sessão de investigação de
> 2026-08-01, mas o modo de planejamento daquela sessão só permitia escrever no
> arquivo de plano — o documento não chegou a `docs/`. Foi reconstruído a partir
> do transcript em 2026-08-01, **sem re-investigar**: os números e as referências
> `arquivo:linha` são os do momento da medição. Se algo divergir do estado atual,
> é movimento da base, não erro do levantamento.

---

## Contexto

Produção acusa **577 `SCHEDULED`** contra **111 `COMPLETED`** no Le Duc — a
barbearia não fecha atendimento no painel. A causa foi confirmada com o cliente e
**não é técnica**: o papel OPERATOR saiu de uso, e sem ele quem trabalha no balcão
passou a evitar o painel inteiro, porque o painel do dono expõe informação
financeira que aquela pessoa não deveria ver.

As consequências encadeadas: o NPS nunca dispara (a pesquisa nasce em
`operation.completed`), o ciclo financeiro não fecha, e — o mais caro — **a
comissão desenhada na FD-1 nunca seria calculada**, porque ela também nasce em
`operation.completed`. Isso torna o perfil pré-requisito do trio
DEPOSIT/SOFT/FSM.

---

## 1. O que OPERATOR pode e vê hoje

### RBAC — dois mecanismos convivem

- **`require_role(...)`** — lista explícita de papéis. Cerca de 30 endpoints
  incluem OPERATOR: agenda/reservas, clientes, catálogo, estoque, fornecedores,
  despesas, contas a pagar, fila, inbox, CRM (leitura), NPS, cash-counts.
- **`require_action(...)`** (`core/deps.py:140-197`) — OPERATOR cai num
  `raise 403` **incondicional** (`deps.py:181-186`), a menos que
  `TenantConfig.permission_overrides` libere a ação nominalmente. É usado hoje
  **só** no `statement_router` (5 pontos).

⚠️ Em produção o `permission_overrides` do Le Duc é `{}` — a "config de OPERATOR"
prevista na matriz da visão **nunca foi usada**. (Paladino Labs tem apenas
`{"use_communication_service": true}`.)

### O caminho do balcão — o que já funciona

| Endpoint | Guarda | OPERATOR |
|---|---|---|
| `GET /appointments/` | `get_current_user` (`appointments/router.py:45`) | ✅ vê **todos** |
| `POST /appointments/` · `cancel` · `reschedule` | `get_current_user` | ✅ |
| `PATCH /appointments/{id}/complete` | `get_current_user` (`:268`) | ✅ **conclui** |
| `GET .../available-credit` (`:200`) · `.../pending-products` (`:235`) | `get_current_company_id` | ✅ |
| `GET /professionals/` · `GET /services/` | `get_current_company_id` | ✅ |
| `POST /payments` | `get_current_user` (`payments/router.py:125`) | ✅ |
| **`POST /payments/{id}/confirm-manual`** | `_owner_admin` (`:170`) | 🔴 **403** |
| `GET /payments` (lista) | `_owner_admin` (`:147`) | 🔴 403 |
| `GET /payments/{id}` | `get_current_user` (`:156`) | ✅ |

### Menu (`Sidebar.tsx`)

OPERATOR vê: Dashboard, Agenda, Operações, Fila (`:81`), Atendimento humano
(`:82`), Clientes, Catálogo (`:110`), **Pagamentos** (`:137`), **Caixa** (`:138`),
Despesas (`:148`), Estoque (`:150`), Fornecedores (`:156`), Contas a pagar
(`:157`).

Não vê: DRE/Gestão Financeira, Comissões, Relatórios, CRM, Auditoria,
Configurações, Profissionais, Usuários.

⚠️ **"Pagamentos" e "Caixa" estão no menu mas dão 403 no backend** — são telas
mortas.

### Guards de rota (frontend)

`app/(dashboard)/layout.tsx:26-35` tem guard **apenas para PROFESSIONAL** em
`/financeiro/*` (com exceção de `/financeiro/taxas`). **Não existe nenhum guard
por papel para OPERATOR** — nem no layout nem nas páginas de resultado.

---

## 2. O que foi desativado, e onde

A desativação foi **uma linha**, não uma remoção:

- **`settings/usuarios/page.tsx:93`** — o `InviteDialog` envia
  `role: "PROFESSIONAL"` fixo. Commit **`121921e`** (2026-06-23), *"fix: convite
  restrito a PROFESSIONAL; simplifica InviteDialog"*, que removeu o Select de
  papel, o estado `role` e a lógica de `allowed`/`actorRole`. **Não há como
  convidar um OPERATOR pela UI.**

Tudo o mais **continua no código**: o enum `UserRole.OPERATOR`
(`models/user.py:14`), o `INVITE_PERMISSION` (`:34-35` — OWNER e ADMIN podem
convidar OPERATOR), o `ASSIGNABLE_ROLES_BY_ACTOR` (`constants.ts:456`), o
`ROLE_LABELS` ("Operador"), a Sidebar, um dashboard dedicado e ~30 endpoints.

**Brecha residual:** a aba Membros ainda oferece OPERATOR no Select de papel
(`usuarios/page.tsx:360`, alimentado por `ASSIGNABLE_ROLES_BY_ACTOR`) — dá para
**promover** um usuário existente, só não para **criar** um.

### Produção — usuários por papel

| Tenant | Papel | Ativo | N |
|---|---|---|---|
| — (plataforma) | PLATFORM_OWNER | sim | 1 |
| **Le Duc** | **OWNER** | sim | **1** |
| **Le Duc** | **ADMIN** | **não** | **1** |
| Paladino Labs | OWNER | sim | 1 |
| Paladino Labs | ADMIN | sim | 2 |
| Paladino Labs | **OPERATOR** | sim | **1** |
| Paladino Labs | PROFESSIONAL | sim | 3 |

🔴 **O Le Duc não tem — e nunca teve — um OPERATOR.** O único do banco inteiro
está no tenant de laboratório (Paladino Labs).

### Produção — convites por papel

| Papel | Status | N |
|---|---|---|
| ADMIN | PENDING / ACCEPTED | 1 / 1 |
| PROFESSIONAL | PENDING / ACCEPTED / CANCELLED | 5 / 2 / 1 |
| **OPERATOR** | — | **0** |

**Zero convites com o papel em toda a história.** "Desativado por falta de uso" é
literal: o papel nunca chegou ao cliente.

### Produção — quem conclui atendimento

Agregando `appointment_status_log` por ator, para `to_status = 'COMPLETED'`:

| Tenant | Ator | Papel | Conclusões |
|---|---|---|---|
| Le Duc | usuário único | **OWNER** | **111 de 111** |
| Paladino Labs | usuário único | **OWNER** | **30 de 30** |

🔴 **Nenhum outro papel jamais concluiu um atendimento em produção.** O dono é o
único operador que existe. *(Os e-mails dos atores foram omitidos deste
documento — a identidade não acrescenta nada ao achado.)*

### Produção — appointments por status

| Tenant | CANCELLED | COMPLETED | SCHEDULED |
|---|---|---|---|
| Le Duc | 34 | 111 | **577** |
| Paladino Labs | 13 | 30 | 33 |

> Nota: a medição de 2026-07-31 registrada no `CLAUDE.md` fala em 596 `SCHEDULED`
> / 138 `COMPLETED` **somando os dois tenants**. Os números acima são de
> 2026-08-01 e refletem a base andando. Não é contradição.

---

## 3. O dashboard de OPERATOR exibe resultado agregado?

**Sim — por desenho.** `dashboard/page.tsx:514-692` (`OperatorDashboard`,
roteado em `:806`):

- **KPI "Caixa do dia"** (`:602-608`) = soma de `net_charged_amount` de **todos**
  os `Payment` CONFIRMED do dia (`:567-570`). É **resultado do negócio**, não
  valor de transação.
- **Painel "Cobranças pendentes"** (`:672-687`) — lista de PENDING com valores de
  outros atendimentos.

Ambos vêm de `GET /payments` (`:534`), que **dá 403 para OPERATOR**. O
`makeGuard` (`:254-265`) engole o erro, então **hoje** o KPI mostra "—" e o painel
mostra "Não foi possível carregar".

⚠️ **A intenção é vazamento; o efeito é painel quebrado.** Precisa ser refeito de
qualquer forma — e, principalmente: **consertar a cobrança revela o vazamento**,
se `GET /payments` for aberto junto.

Não exibe comissão. ✅

### Superfícies de transação — corretas, sem ajuste

- **`PaymentOnCompleteDialog`** mostra só o valor daquele atendimento e o método
  de pagamento → comportamento esperado pela distinção do cliente.
- **`appointments/[id]/page.tsx:138-193`** mostra subtotal, desconto, total e
  sinal **daquele** agendamento. A chamada a `GET /payments` (`:57`) está em
  `try/catch` aninhado (`:62-64`), então o 403 do OPERATOR degrada em silêncio —
  a tela funciona, só não mostra o sinal.

### Comissão — já está certo

`GET /commissions` e `/commission-policies` são OWNER/ADMIN
(`commission/router.py:29,85`); `/commissions/me` exige `role == "PROFESSIONAL"`
(`:59`). **OPERATOR não alcança comissão nenhuma.** ✅

---

## 4. Telas de resultado alcançáveis

Não há guard de papel para OPERATOR no frontend; a contenção real é o backend.

| Rota | Guard front | Backend | Efeito p/ OPERATOR |
|---|---|---|---|
| `/financeiro/dre` | nenhum | `_owner_admin` | erro, sem dado |
| `/financeiro/contas` · `/movimentacoes` | nenhum | `_owner_admin` | erro |
| `/financeiro/conciliacao` | só `canWrite` | `_owner_admin` | erro |
| `/financeiro/extrato` | `canWrite` **inclui OPERATOR** | `require_action("statement_*")` | 403 (override `{}`) |
| `/financeiro/pagamentos` | só `canConfirm` (`:56-57`) | `GET /payments` `_owner_admin` | **no menu**, erro |
| `/caixa` | nenhum | `movements`+`accounts` `_owner_admin`; `cash-counts` **permite OPERATOR** | **no menu**, erro |
| `/relatorios` | nenhum | hub estático de links | abre; destinos 403 |
| `/comissoes` · `/comissoes/historico` | nenhum | `_owner_admin` | erro |
| `/comissoes/politicas` · `/comissoes/pagamentos` | guard OWNER/ADMIN | — | bloqueado ✅ |

**Conclusão: hoje não há vazamento de resultado para OPERATOR — o backend
segura.** O que há é o inverso: dois itens de menu que levam a telas mortas, e
telas de gestão que respondem com erro em vez de "sem acesso".

---

## 5. OPERATOR × PROFESSIONAL — OPERATOR é o certo

`list_appointments` (`appointments/router.py:49-58`) força o filtro ao próprio
cadastro **só** para PROFESSIONAL. A agenda do painel também se auto-filtra
(`agenda/page.tsx:139`) e `appointments/[id]` esconde as ações para o papel
(`:115`).

PROFESSIONAL enxerga apenas os próprios atendimentos e não teria a agenda da
casa — **não resolve o balcão**. O pedido do cliente ("balcão", vê todos os
agendamentos) é OPERATOR.

---

## 6. Tamanho do trabalho

Não é (a) "só reativar o papel" nem (b) "reativar + guards/menu". É **(c)
reativar + corrigir o caminho de cobrança + ajustar menu/guards + refazer o
dashboard**. Ordenado por criticidade:

1. 🔴 **Destravar a cobrança.** `POST /payments/{id}/confirm-manual` é
   `_owner_admin` (`payments/router.py:170`) → OPERATOR toma **403**. O
   `PaymentOnCompleteDialog` encadeia `POST /payments`
   (`PaymentOnCompleteDialog.tsx:126`) → `confirm-manual` (`:136`) →
   `PATCH /complete` (`:140`): o passo 1 passa, o 2 falha, e o 3 **nunca roda**.
   **Cada tentativa deixa um `Payment` PENDING órfão e o agendamento continua
   `SCHEDULED`.**
   Sem isto, reativar o papel entregaria ao cliente um balcão que **piora** o
   sintoma que ele pediu para resolver. É o bloqueador real; o resto é acabamento.
2. 🔴 **Reativar o convite** — restaurar o Select de papel no `InviteDialog`,
   respeitando `ASSIGNABLE_ROLES_BY_ACTOR`, que já está correto. Reverte o
   essencial de `121921e`. Sem migration.
3. 🟠 **Refazer o dashboard de OPERATOR** — trocar "Caixa do dia" e "Cobranças
   pendentes" por métricas de operação (contagens). Remove o único agregado de
   resultado do perfil.
4. 🟠 **Menu × acesso** — decidir Pagamentos e Caixa (hoje mortos): habilitar como
   superfície de balcão ou tirar do menu. Idem Despesas / Contas a pagar /
   Fornecedores.
5. 🟡 **Guard por papel** — estender o guard de `layout.tsx` para OPERATOR nas
   rotas de resultado, trocando erro de API por bloqueio limpo. Defesa em
   profundidade — o backend já segura.

**Sem migration.** Nada de schema muda: o enum, o `INVITE_PERMISSION` e o
`permission_overrides` já suportam o papel inteiro.

---

## 7. Dívida registrada (não corrigida)

**`POST /payments` aceita qualquer usuário autenticado enquanto `confirm-manual`
exige OWNER/ADMIN.** É essa assimetria que produz o `Payment` órfão; qualquer
papel novo tropeça nela.
