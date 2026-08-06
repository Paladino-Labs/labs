# S-heartbeat — enxergar o worker e a fila

Branch `feat/heartbeat-health-deep`, base `main` = `9024f8b`.
Migration nova: **`e0s33_worker_heartbeats`** (← `e0s32_bot_conversation_leases`, head único).

O que o sprint entrega: um endpoint que responde *"o sistema está saudável de
verdade?"* — não *"o processo web respondeu"*. Durante o incidente de 22/07 os
três monitores do Uptime Kuma (API, painel, vitrine) ficariam **verdes**: o web
estava de pé; faltava o consumidor da fila.

---

## 1. Parte 3 — como o batimento roda sem o beat

**Escolha: (a), com a estrutura de (b) pronta e desligada.**

O worker se auto-despacha. No sinal `worker_ready` sobe uma thread daemon que, a
cada 60 s, **enfileira** a task `app.workers.heartbeat.worker_heartbeat`. O
worker a consome e grava a linha.

Fundamento:

- **(c) está descartado por definição** — implementar tudo e deixar inerte até o
  beat subir entrega um monitor que não monitora.
- **(b) exigiria decisão do Silva agora.** Não a decisão de *código* (separar o
  schedule é trivial e está feito), mas a de *infraestrutura*: criar um processo
  de beat em produção, que hoje não existe. Isso adiantaria uma decisão que foi
  deliberadamente adiada. O sprint manda parar e reportar nesse caso — então não
  se pediu.
- **(a) não pede nada a ninguém.** O batimento passa a existir no mesmo deploy
  do worker, sem processo novo, sem env var nova, sem nenhuma das 18 tasks
  represadas se aproximar da fila.

### A thread despacha; ela nunca escreve

Esta é a parte que dá honestidade ao sinal, e é onde a armadilha do sprint quase
se repete numa forma nova.

Uma thread que **gravasse direto** a linha seria o mesmo erro do beat com outro
nome: continuaria batendo com o pool de execução travado, ou com o broker fora.
Diria "estou vivo" exatamente no incidente.

Como ela apenas **enfileira**, o caminho medido é `broker → fila → pool de
execução` — o mesmo caminho de qualquer task real. A linha só aparece se alguém
de fato consumiu.

`dispatched_at` viaja como argumento da task, então a própria linha registra
`queue_lag_ms = executed_at − dispatched_at`. É esse número que detecta "worker
vivo mas travado", que a frescura do batimento sozinha não pegaria.

A entrada `worker-heartbeat` existe no `beat_schedule`, isolada no dicionário
`heartbeat_schedule` (as outras 18 continuam intocadas). Quando o beat subir, ele
despacha o mesmo batimento; o upsert absorve os dois escritores sem conflito.
Um teste trava que `heartbeat_schedule` tem **exatamente uma** entrada.

---

## 2. Frequência e limiar

| | valor | por quê |
|---|---|---|
| Escrita | **60 s** | 1 UPSERT/min numa tabela de N linhas (N = nº de workers). Custo irrelevante; granularidade suficiente para "minutos". |
| Alarme de worker | **180 s** | Três janelas. Duas perdas isoladas (deploy, restart, blip de rede) não acordam ninguém; ausência real de consumidor acende em ≤3 min. |
| Alarme de fila | **300 s de lag** | Acima disso há consumidor vivo e a fila não anda. Folgado de propósito: com `concurrency=2` um pico legítimo pode segurar o batimento por alguns minutos, e um falso vermelho custa mais caro que 5 min de atraso na detecção de um caso que o alarme de worker não cobre. |
| Deadline do broker | **2 s** | O check é de alcançabilidade. |

Os dois knobs (escrita/leitura) são **independentes por construção**: o leitor
(`app/modules/health/service.py`) não importa o módulo do worker — o que também
evita arrastar o Celery para dentro do processo web. Um teste afirma a relação
entre eles (`limiar ≥ 2 × intervalo`), que é o que precisa valer.

---

## 3. Tabela, não Redis

`worker_heartbeats` — chave `worker_name` (`celery@<host>`), `last_seen_at`,
`dispatched_at`, `queue_lag_ms`, `pid`, `beat_count`. Tabela de **plataforma**:
sem `company_id`, sem RLS (padrão de `platform_settings`) — o batimento descreve
o processo, não um tenant.

Duas razões, ambas do enunciado e ambas verificadas no repo:

1. **O Redis é o que cai.** Medir a saúde da fila por um estado que mora no
   componente sob suspeita é ficar cego no momento errado.
2. **Nada aqui pode depender de estado de sessão do Postgres** — o pooler em
   transaction-mode não o preserva (provado no S2.1 com advisory lock). Uma
   linha é pooler-agnóstica por construção.

A escrita é um único `INSERT … ON CONFLICT (worker_name) DO UPDATE`: uma
transação, sem leitura prévia, idempotente. Sem `retry` — batimento perdido é
irrelevante (o próximo vem em 1 min) e retentar empilharia batimentos velhos.
Pelo mesmo motivo o despacho leva `expires=120s`: quando o broker volta, uma
pilha de batimentos represados não pode ser drenada de uma vez fabricando um
"tudo bem" retroativo.

---

## 4. `GET /health/deep`

`/health` **não foi alterado** (só ganhou docstring dizendo por que não deve
ser). Ele é o healthcheck de **deploy** do Railway: se passasse a reprovar
porque o Redis oscilou, um deploy legítimo falharia por dependência secundária.
`/health` = liveness do processo; `/health/deep` = readiness do sistema.

```
200  {"status":"ok","failed":[],"checks":{...}}
503  {"status":"fail","failed":["worker"],"checks":{
        "database":{"status":"ok"},
        "worker":{"status":"fail","error":"heartbeat_stale",
                  "workers_alive":0,"last_seen_age_seconds":912,
                  "stale_after_seconds":180},
        "queue":{"status":"unknown","error":"heartbeat_stale"},
        "broker":{"status":"ok","queue_depth":37}}}
```

### O que cada sub-check mede

1. **database** — `SELECT 1`. Hoje o `/health` mente se o Postgres cair.
2. **worker** — `max(last_seen_at)` dentro da janela.
3. **queue** — `queue_lag_ms` do batimento mais recente (ver §5).
4. **broker** — PING com deadline curto.

### Três regras de discriminação

- **Banco fora → worker e queue viram `unknown`, não `fail`.** A causa é uma só;
  acusar três coisas ao mesmo tempo é o mesmo que não dizer nada.
- **Banco de pé e leitura falhando → `fail`.** Tabela ausente (migration não
  aplicada), permissão, schema fora do lugar. Sem essa distinção o endpoint
  devolveria **200 no primeiro deploy sem a `e0s33`** — falso verde, pior que
  vermelho. Tem teste.
- **`unknown` nunca reprova sozinho.** Ele sempre acompanha o `fail` de outro
  sub-check, que é quem carrega o alarme.

### Nenhum check pendura o endpoint

O broker roda com deadline em **duas camadas**: `socket_connect_timeout` /
`socket_timeout` no cliente, e `future.result(timeout=2s)` por fora. A segunda
existe porque a primeira depende do cliente se comportar — e um endpoint de
saúde que pendura é pior que não ter endpoint. O teste usa um cliente que dorme
30 s e afirma que a resposta sai em menos de 5.

O handler é `def`, não `async def`: o FastAPI o roda no threadpool, então nem a
leitura do banco nem o PING tocam o event loop (relevante dado o achado da A7
sobre o loop único do bot).

---

## 5. O que o check de fila mede hoje — e o que não mede

**Mede:** a **latência** da fila, ponta a ponta, pelo `queue_lag_ms` que o
próprio batimento carrega. É o detector de "worker vivo mas travado".

**Mede como informação, sem reprovar:** a **profundidade** da fila padrão do
Redis (`LLEN celery`), colhida no mesmo PING. Ela aparece no corpo (`queue_depth`)
mas nunca sozinha derruba o endpoint: não há limiar calibrado, e um pico legítimo
não é incidente. Quando houver histórico, vira alarme.

**Não mede:** backlog da fila **durável em tabela**. A `bot_inbound_messages` só
existe com a Entrega B do S2.1, que está revertida — reentregá-la está fora do
escopo deste sprint. Enquanto isso, o backlog observável é o do Redis, com a
limitação óbvia: se o Redis cair, ele some junto (e é o check de broker que
acende).

---

## 6. Exposição anônima — a decisão

**O endpoint é anônimo, e isso é requisito**: o Uptime Kuma não faz login. Um
endpoint de monitoramento autenticado não é monitorado. Mesma exposição do
`/health`, que já é público.

O que o corpo devolve: **nomes de sub-check, estado, idades em segundos e os
limiares**. O que ele **não** devolve:

- hostname do worker, PID, quantidade de workers por nome — nada de topologia;
- DSN, URL do broker, credencial;
- texto de exceção (as exceções vão para o log, com `logger.exception`; a
  resposta traz só `unreachable` / `timeout`);
- nenhum número de negócio — nem faturamento, nem contagem de clientes, nem
  volume de agendamentos.

`queue_depth` é profundidade de fila **interna de tasks**. Não é proxy de volume
comercial (o beat não roda; o que passa ali é infraestrutura). Fica exposto
porque é justamente o número que quem abre o alarme precisa.

Um teste afirma a ausência de vazamento no corpo (hostname, `redis://`,
`postgres`, `Traceback`).

**Rate limit 30/min por IP** (slowapi, mesmo mecanismo do `/manage` e do NPS
público). O endpoint toca banco e broker; sem teto seria amplificação barata.
O Kuma pergunta 1×/min.

---

## 7. Validação do desenho — 22/07

O incidente teve duas camadas: o Redis caiu e, depois dele, **não havia
consumidor da fila**; o bot ficou mudo por 22 horas e ninguém soube. Os três
monitores existentes ficaram verdes o tempo todo.

Como cada camada apareceria no `/health/deep`:

| Sintoma de 22/07 | Sub-check que acende | Quando |
|---|---|---|
| Redis fora | `broker: fail (unreachable\|timeout)` | **na primeira consulta** — ≤1 min |
| Sem consumidor da fila | `worker: fail (heartbeat_stale)` | **≤3 min** após o último batimento |
| Worker de pé mas sem consumir | `queue: fail (queue_lagging)` | ≤5 min de lag |
| Postgres fora | `database: fail` | na primeira consulta |

**Resposta concreta à pergunta de validação:** se o incidente acontecesse amanhã,
o `/health/deep` ficaria vermelho em **menos de 1 minuto** pelo broker e, mesmo
que só o worker tivesse morrido (broker intacto), em **no máximo 3 minutos + o
intervalo de polling do Kuma ≈ 4 minutos**. Não 22 horas.

E o corpo diria **qual** dos quatro falhou, sem investigação.

---

## 8. Testes

`tests/test_s_heartbeat.py` — **20 testes**, cobrindo os 6 do enunciado:

| # do enunciado | teste |
|---|---|
| 1. 200 com tudo saudável | `test_200_when_everything_is_healthy` |
| 2. **503 dizendo que foi o banco** | `test_503_and_body_blames_the_database` |
| 3. **503 dizendo que foi o worker** | `test_503_and_body_blames_the_worker_when_heartbeat_is_stale` |
| 4. broker não pendura | `test_broker_timeout_is_bounded_and_reported` (cliente que dorme 30 s) |
| 5. escrito pelo worker, idempotente | classe `TestTheWorkerIsTheWriter` (5 testes) |
| 6. `/health` intocado | `TestLivenessIsUntouched` |

Extras que valem: `heartbeat_unreadable` (falso verde de migration não aplicada),
`queue_lagging` com batimento fresco (worker travado), broker fora, ausência de
vazamento no corpo, e `TestTheHeartbeatDoesNotDependOnTheBeat` — que afirma o
receiver de `worker_ready` e o tamanho 1 do `heartbeat_schedule`.

### ⚠️ Por que metade do arquivo roda em subprocesso

Mesma razão do `test_celery_task_registration.py`: dez e poucos arquivos da suíte
instalam `sys.modules["celery"] = MagicMock()` sob o guard
`if "celery" not in sys.modules`. Importar `app.workers.heartbeat` (que importa
celery de verdade) no processo do pytest desarmaria o guard e quebraria 10 testes
de worker. `app.main` tem o problema espelhado com o monkey-patch de modelos do
`test_sprint2_rbac`.

Então: tudo que toca worker ou `app.main` roda num interpretador limpo — que é
também a verificação mais fiel de "quem escreve o batimento", porque é
literalmente o boot do worker de produção. Os testes do endpoint são in-process:
`app/modules/health/` não importa celery.

---

## 9. Baseline e resultado

Medidos em **worktrees separados** (a árvore de trabalho em edição contamina a
leitura — vários testes importam o service dentro do corpo).

| | passed | failed | skipped | xfailed |
|---|---|---|---|---|
| Baseline `main` (5398656) | 1354 | **12** | 6 | 1 |
| Branch `feat/heartbeat-health-deep` | 1374 | 12 | 6 | 1 |

⚠️ **A baseline esperada de 0 falhas não é alcançável a partir de `main`.**
O S0.4-bis (`348f8b6`) restaurou o RBAC, mas está em `fix/s04-restaurar-rbac` —
**não mesclado**. As 12 falhas são exatamente as classes de `test_sprint2_rbac`
descritas no `CLAUDE.md`; nenhuma tem relação com este sprint. O mesmo vale para
o `chore/housekeeping` (`5a9485d`), também pendente de merge.

Delta: **+20 testes, 0 regressões**. `ruff check` limpo nos arquivos novos;
`alembic heads` devolve head único.

---

## 10. Pendências para o deploy (do Silva)

1. **Aplicar a `e0s33` antes ou junto do deploy do worker.** Sem a tabela, o
   `/health/deep` responde 503 com `worker: heartbeat_unreadable` — vermelho
   correto, mas evitável.
2. **Configurar o monitor no Uptime Kuma** apontando para `/health/deep`
   (fora do escopo deste sprint). Sugestão de intervalo: 60 s.
3. A migration **não foi aplicada em lugar nenhum** — o único banco alcançável
   desta máquina é o de produção, e o dev pode estar pausado. A SQL é DDL
   simples (`CREATE TABLE IF NOT EXISTS` + `COMMENT`), reversível pelo
   `downgrade`.
4. O beat continua **não existindo** em produção, por decisão pendente. Nada
   neste sprint depende disso.
