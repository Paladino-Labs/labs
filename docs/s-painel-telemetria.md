# S-painel-telemetria — Ler as conversas do bot

Branch `feat/painel-telemetria`, a partir de `main` em `17cc475`
(inclui os três sprints de 12/08). **Sem push. `CLAUDE.md` não foi tocado.**

O Silva lê as conversas dos dias de coleta e, lendo, rotula o que o bot
deveria ter entendido. O resultado é o insumo do redesenho do catálogo de
intenções.

---

## 1. O que saiu do menu e continua alcançável por URL

O menu do painel de plataforma foi reduzido a **um item: Telemetria**. As
cinco telas abaixo **continuam existindo e funcionando** — só perderam o
caminho de navegação:

| Tela | URL | Verificada |
|---|---|---|
| Tenants | `/owner/tenants` | ✅ renderiza |
| Detalhe do tenant | `/owner/tenants/[id]` | rota preservada |
| Flags do tenant | `/owner/tenants/[id]/flags` | rota preservada |
| Impersonation | `/owner/impersonation` | ✅ renderiza |
| Sistema | `/owner/sistema` | ✅ renderiza |
| Configurações da plataforma | `/owner/settings` | ✅ renderiza |
| Auditoria | `/owner/audit` | ✅ renderiza |

**Nada de backend foi removido.** As rotas `/platform/*`, os serviços, a
impersonation e a gestão de tenant estão intactos — inclusive o middleware de
impersonation, que é o caminho de dar suporte a um tenant.

Único efeito colateral de navegação: o **destino do login** do perfil de
plataforma passou de `/owner/tenants` para `/owner/telemetria`
(`painel/app/page.tsx`, dois pontos).

### ⚠️ Isto cria de propósito o padrão "tela existe, caminho não existe"

Este repo já tem **três ocorrências acidentais** desse padrão (o hub
`/settings` órfão, `reset-password` e `settings/comunicacao` antes do
S-onboarding). **A quarta é deliberada e temporária.** Está registrada em
comentário no topo do `NAV` de `components/owner/OwnerSidebar.tsx`, com a
instrução explícita de não "consertar" restaurando os itens sem decisão do
Silva.

Quando o painel definitivo for desenhado, o critério é o que o Silva sentir
falta usando só a telemetria.

---

## 2. A migration, aplicada no dev

`e0s36_bot_message_labels` ← `e0s35_user_phone`.

**Cadeia conferida: head único** (`alembic heads` → `e0s36_bot_message_labels`).
O dev estava em `e0s33`; o `upgrade head` aplicou `e0s34`, `e0s35` e `e0s36`.

O Supabase de dev **não estava pausado** — não foi preciso despausar.

### Confirmação no banco de dev (`tvguwtdfayhrctlpollf`)

Estrutura conferida via `information_schema` / `pg_constraint`:

```
bot_message_labels_pkey                PRIMARY KEY (id)
bot_message_labels_trace_id_key        UNIQUE (trace_id)
bot_message_labels_trace_id_fkey       FK → bot_message_traces(id) ON DELETE CASCADE
bot_message_labels_labeled_by_fkey     FK → users(id) ON DELETE SET NULL
chk_bot_message_labels_understood      CHECK (understood IN ('YES','NO','WRONG'))
chk_bot_message_labels_not_empty       CHECK (pelo menos um dos três campos preenchido)
idx_bot_message_labels_trace           (trace_id)
idx_bot_message_labels_intent          (expected_intent) WHERE expected_intent IS NOT NULL
relrowsecurity = False                 (tabela de plataforma — mesmo idioma de e0sC2/e0sC3)
```

**Comportamento exercitado contra PostgreSQL real (5/5):**

1. rótulo grava e relê ✅
2. `UNIQUE(trace_id)` rejeita duplicata ✅ (é o que faz a gravação da tela ser upsert idempotente)
3. `CHECK understood` rejeita valor fora do domínio ✅
4. `CHECK not_empty` rejeita linha-fantasma ✅
5. **CASCADE**: apagar o trace apaga o rótulo ✅

**Ciclo `upgrade → downgrade → upgrade` limpo**, head único ao final.

### Duas decisões de schema que merecem leitura

**`expected_intent` é VARCHAR livre, validado só na API.** O catálogo de
intenções é *exatamente* o que este trabalho vai redesenhar; prendê-lo num
enum ou num CHECK faria toda ideia nova do Silva exigir migration. O
vocabulário vive em `telemetry_service.EXPECTED_INTENTS` e é servido por
`GET /platform/telemetry/catalog` — a tela não repete a lista, então
acrescentar um rótulo é editar uma tupla em Python. `understood` tem CHECK
porque seus 3 valores *são a pergunta*, não o vocabulário em revisão.

**⚠️ O rótulo tem a mesma vida útil de 30 dias do trace (CASCADE).**
`bot_message_traces` tem retenção de 30 dias com expurgo oportunista. É
deliberado: rótulo órfão não é analisável — some o texto, o estado e a
classificação que o justificavam. **Quem precisar do resultado além da janela
extrai o resumo (seção 3), não preserva a tabela.** A primeira linha da coleta
atinge a retenção por volta de **2026-09-07**.

---

## 3. O que a marcação persiste — e como será lida depois

Por mensagem do cliente (`bot_message_labels`, 1:1 com o trace):

| Campo | Conteúdo |
|---|---|
| `understood` | `YES` · `NO` · `WRONG` — "o bot entendeu?" |
| `expected_intent` | agendar · cancelar · remarcar · consultar · saudação · agradecimento · preço · disponibilidade · produto · pacote · humano · outro |
| `note` | observação livre — o que não cabe em rótulo |
| `labeled_by`, `created_at`, `updated_at` | procedência |

Marcar é **opcional por mensagem**: o que está certo fica em branco. Limpar os
três campos **apaga** a linha (é como a tela desfaz uma marcação).

### As queries que transformam marcação em resumo

⚠️ **As três foram executadas contra o dev e devolvem o resultado esperado.**
Sem elas o dado fica parado — são entregável, não ilustração.

**A frase que o Silva quer no fim:** *"das 25 conversas, 14 mensagens não
entendidas: 9 eram agendamento, 3 saudação, 2 preço"*

```sql
-- (a) O título: quanto foi lido e quanto falhou
SELECT count(DISTINCT t.whatsapp_hash)                        AS conversas_marcadas,
       count(*)                                               AS mensagens_marcadas,
       count(*) FILTER (WHERE l.understood IN ('NO','WRONG')) AS nao_entendidas,
       count(*) FILTER (WHERE l.note IS NOT NULL)             AS com_observacao
FROM bot_message_labels l
JOIN bot_message_traces t ON t.id = l.trace_id;
```

```sql
-- (b) O detalhamento: "9 eram agendamento, 3 saudação, 2 preço"
SELECT l.expected_intent,
       count(*)                                        AS mensagens,
       count(DISTINCT t.whatsapp_hash)                 AS conversas,
       count(*) FILTER (WHERE l.understood = 'NO')     AS nao_entendeu,
       count(*) FILTER (WHERE l.understood = 'WRONG')  AS entendeu_errado,
       count(*) FILTER (WHERE l.understood = 'YES')    AS entendeu
FROM bot_message_labels l
JOIN bot_message_traces t ON t.id = l.trace_id
WHERE l.expected_intent IS NOT NULL
GROUP BY l.expected_intent
ORDER BY mensagens DESC, l.expected_intent;
```

```sql
-- (c) O material bruto do redesenho: as falas REAIS por rótulo, ao lado do
--     que o bot achou que era. É esta lista que vira padrão de regex.
SELECT l.expected_intent,
       t.user_input,
       t.fsm_state,
       t.classifier->'final'->>'intent'     AS intent_do_bot,
       t.classifier->'routing'->>'decision' AS decisao,
       l.note
FROM bot_message_labels l
JOIN bot_message_traces t ON t.id = l.trace_id
WHERE l.expected_intent IS NOT NULL
ORDER BY l.expected_intent, t.received_at;
```

⚠️ **Rode a (c) e guarde o CSV antes dos 30 dias.** É o único artefato que
sobrevive ao expurgo do trace.

---

## 4. Como a tela define "mensagem não entendida"

É o número pelo qual o Silva escolhe o que ler, então a definição está num
lugar só (`telemetry_service._diagnose`) e vale para a lista e para o detalhe:

| Conta | Por quê |
|---|---|
| `routing.decision = MENU_FALLBACK` | nada casou → menu genérico |
| `routing.decision = SHADOW_NOT_ROUTED` | a LLM entendeu, o shadow conteve — **o cliente vê o mesmo menu** |
| `message_type` fora dos legíveis | áudio/imagem/sticker/`protocolMessage` — o cliente falou e o bot não ouviu (classe catalogada no S-bot-1 e não corrigida) |

**Não conta:** `INACTIVE_MODULE_MSG` — ali o bot **entendeu** e respondeu que o
recurso está desligado. É outra conversa, não falta de entendimento.

### Uma decisão de agrupamento que muda a leitura

**A conversa é agrupada por `whatsapp_hash`, não por sessão.**
`bot_sessions.id` é reutilizada entre conversas do mesmo interlocutor (aviso
do F5a), então agrupar por sessão cortaria e misturaria conversas de forma
arbitrária. Consequência aceita: quem falou com o bot na segunda e na quinta
aparece como **uma** conversa — com ~25 conversas em 4 dias isso ajuda a
leitura em vez de atrapalhar.

A agregação acontece **em Python**, não em SQL: o volume é de dezenas de
conversas num instrumento descartável, e a definição acima fica legível num
lugar só. `MAX_TRACES = 5000` é o teto que faz essa escolha falhar barulhenta
se o volume mudar.

---

## 5. Verificação manual

Ambiente: API contra o **Supabase de dev** (`scripts/run_dev_api.py`, novo) +
painel em `localhost:3000`, com 3 conversas semeadas por
`scripts/seed_dev_bot_traces.py` (novo) reproduzindo as assinaturas que
importam: regex não casou, roteou certo, e tipo ilegível (áudio).

| # | Critério | Resultado |
|---|---|---|
| 1 | A lista mostra as conversas com o contador de não-entendidas | ✅ 3 conversas, telefone mascarado, data, nº de mensagens e badge vermelho (4/4, 2/3, 1/2) |
| 2 | Abrir uma conversa mostra a sequência completa, em ordem | ✅ formato de chat, cliente à esquerda / bot à direita, cronológico |
| 3 | O expansível mostra o diagnóstico da mensagem | ✅ estado na chegada e após, tipo, desfecho, handler, decisão de roteamento, regex + confiança + "(não casou)", LLM, duração, caminho |
| 4 | Marcar persiste — e continua lá ao recarregar | ✅ **2 cliques = exatamente 2 PUTs, zero refetch** (o painel expandido nem fechou); após F5 a marcação e a observação continuam lá |
| 5 | O perfil de plataforma alcança; um usuário de tenant não | ✅ PLATFORM_OWNER 200; OWNER de tenant **403**; anônimo **401** |
| 6 | Nada regride no painel de tenant | ✅ `/dashboard` com token de tenant: sidebar completa, todos os grupos, sem erro |

O caso do áudio renderiza como projetado: *"(sem texto — audioMessage)"* +
`não classificada` + `Tipo não lido`, com o bot devolvendo o menu — a classe
do S-bot-1 fica visível na tela pela primeira vez.

### Sobre a autenticação usada na verificação

Não digitei senha em formulário. O token de sessão foi **emitido pela própria
biblioteca da aplicação** (`create_access_token`, o mesmo caminho da suíte) e
injetado no `localStorage` — para o PLATFORM_OWNER e, no item 6, para um OWNER
de tenant.

### ⚠️ `scripts/run_dev_api.py` existe por um motivo específico

O `.env` **versionado** tem `DATABASE_URL` de **produção**. Subir
`uvicorn app.main:app` para verificação sobe a API contra produção. O runner
carrega o `.env.dev` antes de importar o app e **aborta** se a URL resultante
for a de produção; se o `.env.dev` não existir, não sobe (fail-closed, não cai
para o `.env`). O `seed_dev_bot_traces.py` tem o mesmo guard.

---

## 6. Suíte

| | Resultado |
|---|---|
| **Baseline** (`main` em `17cc475`, worktree limpo) | **1512 passed**, 6 skipped, 1 xfailed, **0 failed** |
| **Depois** | **1534 passed**, 6 skipped, 1 xfailed, **0 failed** |

+22 testes novos (`tests/test_painel_telemetria.py`), **zero regressões**.
Cobrem: agrupamento e ordenação, as três regras do contador (incluindo
`INACTIVE_MODULE_MSG` **não** contando e o tipo ilegível contando), filtro de
data, ruído de evento sem mensagem, ordem cronológica, o expansível, 404 de
conversa, upsert / correção / apagamento do rótulo, os dois 422 de validação,
404 de trace, releitura do rótulo gravado, e o guard de papel.

Frontend: `tsc --noEmit` exit 0 e `eslint` exit 0 nos arquivos novos e
alterados.

---

## 7. Escopo — o que NÃO foi feito

Conforme as restrições, e nenhuma precisou ser rompida:

- ❌ Backend do painel de plataforma **não** foi removido — só navegação
- ❌ Nada em `whatsapp/` foi tocado — a telemetria segue coletando
- ❌ Sem agregados, gráficos ou métricas na tela — o resumo é a query da seção 3
- ❌ Sem criação de tenant pela tela
- ❌ Uptime Kuma não embutido
- ❌ Nenhum papel ou permissão novo — a tela usa a dependency `PLATFORM_OWNER`
  que já governa o router `/platform` inteiro

## 8. Arquivos

**Backend**
```
migrations/versions/e0s36_bot_message_labels.py        (novo)
app/infrastructure/db/models/bot_message_label.py      (novo)
app/infrastructure/db/models/__init__.py               (registro)
app/modules/platform/telemetry_service.py              (novo)
app/modules/platform/router.py                         (+4 endpoints)
app/modules/platform/schemas.py                        (+MessageLabelUpdate)
tests/test_painel_telemetria.py                        (novo, 22 testes)
scripts/run_dev_api.py                                 (novo, ferramenta)
scripts/seed_dev_bot_traces.py                         (novo, ferramenta)
```

**Frontend**
```
painel/app/(owner)/owner/telemetria/page.tsx           (novo — lista)
painel/app/(owner)/owner/telemetria/[hash]/page.tsx    (novo — conversa + marcação)
painel/lib/telemetry-types.ts                          (novo)
painel/components/owner/OwnerSidebar.tsx               (NAV reduzido + o porquê)
painel/app/page.tsx                                    (destino do login do owner)
.claude/launch.json                                    (config "Backend DEV")
```

**Endpoints** (todos sob a dependency `PLATFORM_OWNER` do router `/platform`)
```
GET /platform/telemetry/conversations?date_from=&date_to=
GET /platform/telemetry/conversations/{whatsapp_hash}
PUT /platform/telemetry/labels/{trace_id}
GET /platform/telemetry/catalog
```
