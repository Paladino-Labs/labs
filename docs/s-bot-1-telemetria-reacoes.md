# S-bot-1 — Telemetria ponta a ponta + parser de reações

**Branch:** `feat/bot-telemetria-reacoes` · **Base:** `main` = `7a0cfe1` (inclui a
Entrega A do S2.1) · **Sem push.** `CLAUDE.md` não foi tocado.

**Migration:** `e0s34_bot_message_traces` (← `e0s33_worker_heartbeats`).
`alembic heads` devolve **um head único**. Não aplicada em lugar nenhum.

---

## 1. O que a telemetria registra, e onde

Uma linha em **`bot_message_traces`** por evento recebido no webhook — inclusive
os que hoje somem sem deixar rastro (instância desconhecida, grupo, duplicata,
JSON inválido, evento não tratado).

### A decisão que sustenta o resto: ContextVar, não parâmetro

O trace **não viaja pela assinatura de nenhuma função**. Ele vive num
`ContextVar` aberto no webhook e lido pelos pontos de instrumentação onde quer
que estejam. Passar um objeto por ~40 handlers seria refatorar — e o enunciado
proíbe mudar estrutura para instrumentar. O webhook é sequencial por request; o
`ContextVar` acompanha isso por construção.

**Nenhuma assinatura de função mudou neste sprint.**

### Os pontos, etapa por etapa

| Etapa | Onde | O que fica visível |
|---|---|---|
| **Webhook** | `whatsapp/router.py:82` — `trace.start()` antes de qualquer decisão, `trace.finish()` num `finally` que cobre **todo** caminho de saída | payload cru saneado (`webhook`), `event`, `instance_name`, `received_at`, `duration_ms`; 401 e JSON inválido também geram linha |
| **Envelope** | `bot_service.handle_inbound_message` | `message_id`, `message_type` (`conversation` \| `reactionMessage` \| `audioMessage` \| …), remetente mascarado + hash |
| **Contexto** | idem, após resolver tenant e travar a sessão | `company_id`, `session_id`, **`fsm_state` na CHEGADA**, `user_input` |
| **Classificador — regex** | `intent/classifier.py:61` | `classifier.regex` = `{intent, confidence, matched, active_intents}`. **`matched=false` é o "o que impediu"** no caso mais comum: nenhum padrão casou |
| **Classificador — LLM** | `intent/classifier.py:66` | `classifier.llm` = `{intent, confidence, latency_ms, source}` — gravado **só quando a camada é consultada** (regex abaixo do threshold) |
| **Classificador — final** | `intent/classifier.py:79` | `classifier.final` = `{intent, confidence, source, entities, classification_id, threshold}`. O `classification_id` **costura esta telemetria com a do F5a** (`intent_classifications` / `intent_outcomes`) |
| **Roteamento** | `intent/telemetry.py::record_routing` — ponto único por onde **todas** as decisões passam | `classifier.routing` = `{decision, routed}` com os mesmos valores do F5a: `ROUTED` \| `MENU_FALLBACK` \| `SHADOW_NOT_ROUTED` \| `INACTIVE_MODULE_MSG` |
| **Dispatcher** | `bot_service` — `dispatch.path` (ordem) + `dispatch.handler` (quem respondeu) | qual handler tratou, e **por que o classificador não rodou** quando não rodou (`no_customer_id` \| `empty_input` \| `matched_menu_option`); comando universal, BACK legado, reação ignorada, estado desconhecido |
| **Estado final** | após o dispatch | `fsm_state_after` |
| **Saída** | `whatsapp/sender.py` — ponto único de envio | `outbound[]` = `[{kind, text, ok}]`, cobrindo `text`, `poll`, `list`, `buttons` e as falhas de envio (`ok=false`) |
| **Desfecho** | coluna `outcome` | `PROCESSED` \| `IGNORED_REACTION` \| `IGNORED_DUPLICATE` \| `IGNORED_GROUP` \| `IGNORED_FROM_ME` \| `IGNORED_UNKNOWN_INSTANCE` \| `IGNORED_BOT_DISABLED` \| `IGNORED_SESSION_LOCKED` \| `IGNORED_EVENT` \| `REJECTED_UNAUTHORIZED` \| `ERROR` |

### A pergunta do enunciado, respondida

> Quando o bot erra, onde ele erra?

Os três casos ficam distintos numa linha só:

| Diagnóstico | Assinatura no trace |
|---|---|
| **O regex não casou** | `classifier.regex.matched = false` e `final.source` = `FALLBACK`/`LLM` |
| **Casou errado** | `classifier.regex.matched = true`, `final.intent` ≠ o que o texto pedia, `routing.decision = ROUTED` |
| **Casou certo e o handler não soube tratar** | `routing.decision = ROUTED`, `dispatch.handler` preenchido, e `outbound` com o menu genérico |

### Abandono

Não é gravado como campo — é **derivado**: é a última linha de um
`whatsapp_hash` sem nenhuma outra depois. A query está na §6 (nº 7). Calcular
inline exigiria um segundo write posterior; derivar é exato e não custa nada.

### O que o instrumento NÃO faz

- Não muda a lógica do classificador, do dispatcher ou da FSM.
- Não altera nenhuma assinatura de função.
- Não cria tela nem relatório (a análise é por SQL).
- Não faz o webhook depender do worker Celery (a Entrega B segue adiada).

---

## 2. Como a Evolution entrega a reação — e se está sendo enviada

### ✅ Está sendo enviada. A Parte 2 procede.

**A reação NÃO tem evento próprio.** Ela chega **dentro de `messages.upsert`** —
o mesmo evento das mensagens normais — como:

```json
{
  "event": "messages.upsert",
  "instance": "<instância>",
  "data": {
    "key": { "id": "<id da reação>", "fromMe": false, "remoteJid": "…" },
    "messageType": "reactionMessage",
    "message": {
      "reactionMessage": {
        "key": { "id": "<id da mensagem REAGIDA>", "fromMe": true, "remoteJid": "…" },
        "text": "👍",
        "senderTimestampMs": "…"
      }
    }
  }
}
```

`MESSAGES_UPSERT` **já está assinado** — `evolution_client.py:101-106` registra
`MESSAGES_UPSERT`, `MESSAGES_UPDATE`, `CONNECTION_UPDATE`, `QRCODE_UPDATED`.
Logo a reação chega, e o diagnóstico do cliente não precisa ser refeito.

### Por que ela reiniciava o bot

`helpers.extract_user_text` conhece 6 formatos (texto, texto estendido, lista,
2 formatos de botão, nativeFlow). **Não conhece `reactionMessage`** — e o
`return` final devolve `""`. Texto vazio segue o pipeline inteiro: não casa
comando universal, o classificador é pulado (exige texto não-vazio), e o handler
do estado com input vazio reexibe o menu. É o "o bot reiniciou" do cliente.

### O que foi implementado

`helpers.extract_reaction(data)` — detecção e extração, sem IA e sem chamada de
rede. Em `bot_service.handle_inbound_message`, **antes do lock de sessão**:

```
reação detectada → log + trace(IGNORED_REACTION, emoji, mensagem-alvo) → return
```

Ignorar **sempre**, independentemente do estado — conforme decidido. Reagir 👍
quando o bot pergunta "qual horário?" não confirma nada.

Três consequências de o `return` vir **antes** do lock, todas verificadas por
teste: a reação **não consome `last_message_id`** (se consumisse, a mensagem
seguinte poderia parecer duplicata), **não renova o TTL** e **não toca o
estado**. Efeito colateral zero, por construção.

Retirar a reação usa o **mesmo formato com `text` vazio** — também é reação,
também é ignorada (`removed: true` no trace).

### ⚠️ Sem mapa semântico de emoji — e por quê

O enunciado previa "mapa simples". Com a decisão de **ignorar sempre**, um mapa
emoji→significado não teria nenhum consumidor: seria código morto no dia em que
nascesse (a auditoria A2 catalogou 12 desses). O emoji é **registrado** na
telemetria, que é o que permite rever a decisão depois, com dados. Se a leitura
dos 3 dias mostrar que alguma reação merece resposta, o mapa nasce ali — com
consumidor.

### 🔴 Achado: a reação era um caso de uma classe maior

Todo tipo de mensagem que `extract_user_text` não conhece produz **exatamente o
mesmo sintoma**: áudio, imagem, sticker, vídeo, documento, localização, contato
e `protocolMessage` (mensagem apagada, ajuste de mensagens temporárias) chegam
ao dispatcher com texto vazio e reexibem o menu.

**Não corrigido — está fora do escopo** ("corrigir comportamento do bot além de
ignorar reações"). Mas a coluna `message_type` mede exatamente isso: a query nº 6
da §6 lista quais tipos estão chegando e com que frequência. É o insumo para
decidir se vale um tratamento genérico ("não entendi esse tipo de mensagem") em
vez de um remendo por tipo.

---

## 3. Análise de privacidade

### O que o payload cru contém além do texto

Nome do perfil (`pushName`), o JID completo (telefone), metadados de aparelho
(`deviceListMetadata`), miniaturas em base64 (`jpegThumbnail`), chaves de mídia
(`mediaKey`, `fileEncSha256`), URLs de mídia e `contextInfo` (que carrega a
mensagem citada, isto é, conteúdo de **outra** mensagem).

### O que o `ConsentRecord` cobre — e o que não cobre

`ConsentRecord` tem 4 tipos: `COMMUNICATION`, `DATA_PROCESSING`,
`PAYMENT_STORAGE`, `MARKETING`. O único consumido no caminho do bot é
`COMMUNICATION`, checado em `CommunicationService.dispatch` — ou seja, ele
governa **enviar** mensagem ao cliente, não **guardar** o que ele escreveu.

**`DATA_PROCESSING` existe no enum e não tem nenhum consumidor no código.**
Formalmente, portanto, nada no `ConsentRecord` autoriza nem proíbe esta gravação.

O que **já é gravado hoje**, antes deste sprint:

| Onde | O quê | Desde |
|---|---|---|
| `bot_sessions.whatsapp_id` | telefone **em claro** | sempre |
| `conversation_messages.content` | conteúdo integral da conversa | Sprint 2.7 |
| `intent_classifications.raw_input` | texto cru de toda mensagem livre | Sprint 2.0 |

O trace **não abre uma categoria nova de dado**: o texto do cliente já é
persistido em dois lugares. O que ele acrescentaria, sem tratamento, é o
**payload cru** — e é aí que estava o risco.

### O que foi mascarado

| Dado | Tratamento | Motivo |
|---|---|---|
| Telefone / JID | `whatsapp_masked` = `5511*******21@s.whatsapp.net` + `whatsapp_hash` = sha256 truncado (24 chars) | O mascarado permite reconhecer de olho; o hash permite **agrupar** uma conversa sem gravar outra cópia legível. JIDs encontrados **dentro** do payload também são mascarados, recursivamente |
| `pushName`, `profilePicUrl`, `verifiedName` | **removidos** | Identificam a pessoa e não acrescentam nada ao diagnóstico do pipeline |
| `jpegThumbnail`, `base64`, `mediaKey`, `fileEncSha256`, `url`, `directPath` | **removidos** | Conteúdo de mídia e chaves criptográficas |
| `contextInfo` | **removido** | Carrega o conteúdo de outra mensagem (a citada) |
| `deviceListMetadata`, `messageSecret` | **removidos** | Metadados de aparelho |
| Qualquer string > 400 chars | vira `<str len=N>` | Preserva "havia um blob aqui, deste tamanho" sem copiar o blob |
| Texto do usuário (`user_input`) | **mantido**, teto de 1000 chars | ⚠️ decisão abaixo |
| Emoji da reação | **mantido** | É o objeto de estudo |

A **estrutura** do payload sobrevive à poda (chaves e tipos preservados) — é ela
que responde "como este tipo de evento chega de fato", que é a pergunta do
parser e de todo tipo ainda não tratado.

### ⚠️ Uma decisão que não é minha para tomar

**Manter o texto do cliente (`user_input` e o texto dentro de `webhook`) é o
único ponto em que este sprint escolheu conteúdo sobre privacidade.** A
justificativa: o objetivo declarado é "ver formas de falar", e sem o texto a
telemetria não serve para nada. E o mesmo texto já está em
`intent_classifications.raw_input` e `conversation_messages.content`.

**Mas o alcance é maior do que o dos dois existentes:** `raw_input` só grava
texto livre nos estados de entrada, e `conversation_messages` só grava conversas
escaladas para humano. O trace grava **toda** mensagem, em todo estado.

**Reportando em vez de decidir sozinho:** se isso não for aceitável, a mitigação
é de uma linha — parar de preencher `user_input` e podar os campos de texto no
`sanitize`. A telemetria de *pipeline* (onde quebra) continua inteira; só se
perde a de *linguagem* (como o cliente fala). Diga qual dos dois vale mais.

Não há tela nem rota expondo a tabela: a leitura é por SQL direto.

---

## 4. Como desligar o shadow — é env var, ação do Silva no Railway

### ⚠️ A variável **não** é a `LLM_MODE`

`LLM_MODE` governa o **roteamento**, não a **chamada**. Ela é lida em
`bot_service._classify_and_route:927`, **depois** de a LLM já ter sido chamada e
paga. Mexer nela não economiza um milissegundo — e mudá-la para `live` seria o
oposto do pedido.

A chamada é decidida em `llm_classifier.py:90`:

```python
if not self.api_key:
    return IntentResult(intent=FALLBACK_INTENT, confidence=0.0, source="FALLBACK", …)
```

Sem chave: retorno imediato, **sem rede, sem latência**.

### Valor correto

```
LLM_API_KEY=          ← esvaziar (ou remover a variável)
LLM_MODE=shadow       ← MANTER como está; não mexer
```

Nenhuma mudança de código é necessária — o mecanismo já existe.

### Dois avisos

1. **Os dados do shadow não são apagados.** `intent_classifications` e
   `intent_outcomes` seguem intactos, como pedido. A coleta simplesmente para.
2. **A telemetria de classificador continua funcionando sem a LLM.** O
   `classifier.regex` é gravado sempre, e o `classifier.final` passa a sair como
   `source=FALLBACK`. É exatamente a redundância que o enunciado apontou.

⚠️ **Ressalva de leitura de dados** (já registrada no `CLAUDE.md`, vale repetir):
linhas `FALLBACK` têm `llm_provider` preenchido mesmo sem LLM real — o
curto-circuito acontece depois de `llm_latency_ms` ser medido. **Filtre por
`source`, nunca por `llm_provider`.**

---

## 5. Expurgo dos 30 dias

**Implementado, sem beat e sem worker.** `whatsapp/trace.py::_maybe_purge`:
`DELETE FROM bot_message_traces WHERE received_at < now() - BOT_TRACE_RETENTION_DAYS`,
disparado no **próprio processo do webhook**, a cada 50 gravações e no máximo
uma vez por hora por processo. Best-effort: falha é logada e ignorada.

Por que não as alternativas:

- **Beat:** não existe em produção, e ligá-lo tem passivo próprio medido
  (47 pesquisas NPS de junho). Fora de escopo por decisão explícita do sprint.
- **Task Celery enfileirada pelo webhook:** faria o webhook do bot depender do
  worker — que é exatamente o desenho da Entrega B, adiada porque o worker cair
  deixa **o bot mudo** (incidente de 22/07).

Com 1–4 sessões/dia o volume é irrisório e há índice em `received_at`. Se o
expurgo oportunista se mostrar barulhento na leitura dos logs, o plano B é
manual e trivial:

```sql
DELETE FROM bot_message_traces WHERE received_at < now() - interval '30 days';
```

**Data para revisitar: 2026-09-07** (30 dias após o deploy) — é quando a primeira
linha atinge a retenção e o mecanismo é observável pela primeira vez.

**Kill-switch:** `BOT_TRACE_ENABLED=false` desliga toda a gravação sem tocar em
código. Verificado por teste que o processamento do bot é idêntico nos dois modos.

---

## 6. As queries — para LER OS CASOS, não para tirar percentuais

⚠️ **O bot registra 1 a 4 sessões por dia. Três dias rendem ~20 conversas.**
Isso serve para ver formas de falar e onde o pipeline quebra. **Não** para
estimar frequência. Nenhuma query abaixo devolve percentual, de propósito.

Todas em `America/Sao_Paulo` (o Railway roda em UTC).

### 1. As conversas dos últimos 3 dias — o índice de leitura

```sql
SELECT whatsapp_hash,
       min(whatsapp_masked)                                  AS quem,
       date_trunc('day', received_at AT TIME ZONE 'America/Sao_Paulo') AS dia,
       count(*)                                              AS eventos,
       min(received_at AT TIME ZONE 'America/Sao_Paulo')     AS inicio,
       max(received_at AT TIME ZONE 'America/Sao_Paulo')     AS fim,
       array_agg(DISTINCT outcome)                           AS desfechos
FROM bot_message_traces
WHERE received_at > now() - interval '3 days'
GROUP BY 1, 3
ORDER BY inicio DESC;
```

### 2. Uma conversa inteira, evento a evento — a leitura principal

Cole o `whatsapp_hash` da query 1.

```sql
SELECT received_at AT TIME ZONE 'America/Sao_Paulo' AS quando,
       message_type,
       fsm_state                          AS estado_na_chegada,
       user_input                         AS cliente_disse,
       classifier->'regex'->>'matched'    AS regex_casou,
       classifier->'regex'->>'intent'     AS regex_intent,
       classifier->'regex'->>'confidence' AS regex_conf,
       classifier->'final'->>'intent'     AS intent_final,
       classifier->'final'->>'source'     AS fonte,
       classifier->'routing'->>'decision' AS roteamento,
       dispatch->>'handler'               AS handler,
       fsm_state_after                    AS estado_depois,
       (SELECT string_agg(o->>'text', E'\n--\n' ORDER BY ord)
          FROM jsonb_array_elements(outbound) WITH ORDINALITY x(o, ord)) AS bot_respondeu,
       outcome
FROM bot_message_traces
WHERE whatsapp_hash = '<cole aqui>'
ORDER BY received_at;
```

### 3. Onde o bot errou — os três diagnósticos, separados

```sql
SELECT received_at AT TIME ZONE 'America/Sao_Paulo' AS quando,
       whatsapp_masked, fsm_state, user_input,
       CASE
         WHEN classifier->'regex'->>'matched' = 'false'
           THEN '1. regex NÃO casou'
         WHEN classifier->'routing'->>'decision' = 'ROUTED'
           THEN '3. casou e roteou — conferir se o handler tratou'
         ELSE '2. casou mas não roteou (confiança/shadow/módulo inativo)'
       END                                AS diagnostico,
       classifier->'regex'->>'intent'     AS regex_intent,
       classifier->'regex'->>'confidence' AS regex_conf,
       classifier->'final'->>'intent'     AS intent_final,
       classifier->'routing'->>'decision' AS roteamento,
       dispatch->>'handler'               AS handler,
       (SELECT o->>'text' FROM jsonb_array_elements(outbound) o LIMIT 1) AS primeira_resposta
FROM bot_message_traces
WHERE received_at > now() - interval '3 days'
  AND classifier ? 'regex'          -- só mensagens que passaram pelo classificador
ORDER BY received_at DESC;
```

### 4. Formas de falar — o texto cru que o classificador viu

O insumo direto do redesenho do catálogo.

```sql
SELECT user_input                         AS cliente_disse,
       classifier->'final'->>'intent'     AS virou,
       classifier->'final'->>'source'     AS por,
       classifier->'routing'->>'decision' AS roteamento,
       count(*)                           AS vezes
FROM bot_message_traces
WHERE received_at > now() - interval '3 days'
  AND classifier ? 'final'
GROUP BY 1, 2, 3, 4
ORDER BY vezes DESC, cliente_disse;
```

### 5. Por que o classificador nem rodou

```sql
SELECT dispatch->'detail'->>'reason' AS motivo,
       fsm_state, user_input,
       received_at AT TIME ZONE 'America/Sao_Paulo' AS quando
FROM bot_message_traces
WHERE received_at > now() - interval '3 days'
  AND dispatch->'path' ? 'classifier_skipped'
ORDER BY received_at DESC;
```

### 6. Reações e outros tipos que o parser de texto não conhece

```sql
SELECT message_type,
       outcome,
       count(*)                                 AS eventos,
       count(DISTINCT whatsapp_hash)            AS pessoas,
       min(received_at AT TIME ZONE 'America/Sao_Paulo') AS primeira,
       max(received_at AT TIME ZONE 'America/Sao_Paulo') AS ultima
FROM bot_message_traces
WHERE received_at > now() - interval '3 days'
  AND event = 'messages.upsert'
GROUP BY 1, 2
ORDER BY eventos DESC;
```

E as reações em detalhe — **inclusive em que estado a conversa estava**:

```sql
SELECT received_at AT TIME ZONE 'America/Sao_Paulo' AS quando,
       whatsapp_masked,
       dispatch->'detail'->>'emoji'             AS emoji,
       dispatch->'detail'->>'removed'           AS foi_removida,
       dispatch->'detail'->>'target_message_id' AS reagiu_a
FROM bot_message_traces
WHERE outcome = 'IGNORED_REACTION'
  AND received_at > now() - interval '3 days'
ORDER BY received_at DESC;
```

⚠️ `fsm_state` fica **NULL** nas reações: o retorno acontece antes do lock de
sessão, justamente para não ter efeito colateral. Para saber o estado, olhe o
evento anterior do mesmo `whatsapp_hash` (query 2).

### 7. Abandono — a última resposta antes do silêncio

O sinal mais forte de que algo não funcionou.

```sql
WITH seq AS (
  SELECT *,
         lead(received_at) OVER (PARTITION BY whatsapp_hash ORDER BY received_at) AS proximo
  FROM bot_message_traces
  WHERE received_at > now() - interval '3 days'
    AND outcome = 'PROCESSED'
)
SELECT received_at AT TIME ZONE 'America/Sao_Paulo' AS quando,
       whatsapp_masked, fsm_state, user_input,
       dispatch->>'handler' AS handler,
       (SELECT string_agg(o->>'text', E'\n--\n') FROM jsonb_array_elements(outbound) o)
         AS ultima_resposta_do_bot
FROM seq
WHERE proximo IS NULL OR proximo - received_at > interval '60 minutes'
ORDER BY received_at DESC;
```

### 8. Eventos que hoje somem sem rastro

```sql
SELECT outcome, event, message_type, instance_name,
       count(*) AS eventos,
       max(received_at AT TIME ZONE 'America/Sao_Paulo') AS ultimo
FROM bot_message_traces
WHERE received_at > now() - interval '3 days'
  AND outcome <> 'PROCESSED'
GROUP BY 1, 2, 3, 4
ORDER BY eventos DESC;
```

### 9. Saúde do próprio instrumento

Erros de processamento e latência do webhook — inclusive o custo do shadow
enquanto a `LLM_API_KEY` não for esvaziada.

```sql
SELECT date_trunc('hour', received_at AT TIME ZONE 'America/Sao_Paulo') AS hora,
       count(*)                                    AS eventos,
       count(*) FILTER (WHERE outcome = 'ERROR')   AS erros,
       max(duration_ms)                            AS pior_ms,
       max((classifier->'llm'->>'latency_ms')::int) AS pior_llm_ms
FROM bot_message_traces
WHERE received_at > now() - interval '3 days'
GROUP BY 1
ORDER BY hora DESC;
```

### 10. Costura com a telemetria do F5a

```sql
SELECT t.received_at AT TIME ZONE 'America/Sao_Paulo' AS quando,
       t.user_input, t.fsm_state,
       ic.classified_intent, ic.source, ic.routing_decision,
       COALESCE(io.outcome, 'PENDING') AS desfecho
FROM bot_message_traces t
JOIN intent_classifications ic
  ON ic.id = (t.classifier->'final'->>'classification_id')::uuid
LEFT JOIN intent_outcomes io ON io.classification_id = ic.id
WHERE t.received_at > now() - interval '3 days'
ORDER BY t.received_at DESC;
```

---

## 7. Suíte

| | Resultado |
|---|---|
| **Baseline** (`7a0cfe1`, worktree limpo) | **1427 passed**, 6 skipped, 1 xfailed, **0 failed** |
| **Depois** (esta branch) | **1463 passed**, 6 skipped, 1 xfailed, **0 failed** |

1427 + 36 novos = 1463. **Zero regressões.**

Baseline medida em worktree separado, conforme a lição do S-housekeeping (a
árvore de trabalho contamina).

Testes novos: `tests/test_sbot1_telemetria_reacoes.py` — os cinco requisitos do
enunciado, sendo o quinto ("falha ao registrar telemetria NÃO derruba o
processamento") coberto por quatro ângulos: commit da telemetria explodindo,
`SessionLocal` indisponível, payload hostil ao `sanitize`, e toda função de
trace chamada fora de um request.

---

## 8. Pendências e avisos

1. **Decisão de privacidade em aberto** (§3): manter o texto do cliente no trace.
   Mitigação de uma linha se a resposta for não.
2. **Ação do Silva no Railway:** `LLM_API_KEY=` (vazio). `LLM_MODE` fica em
   `shadow`.
3. **Expurgo:** revisitar em **2026-09-07**.
4. **Migration `e0s34` não aplicada** em nenhum ambiente.
5. **Fora de escopo, medido:** outros tipos de mensagem (áudio, imagem, sticker,
   `protocolMessage`) produzem o mesmo sintoma da reação. A query nº 6 mede.
6. **Um trace por request do webhook.** Um `messages.update` com vários votos de
   enquete gera uma linha só, com os dados do último. Irrelevante no volume
   atual; registrado para não surpreender na leitura.
7. **Uma conexão de banco a mais por evento** (a sessão própria do trace, do
   mesmo pool de 5+10). Deliberado: é o que faz o trace de uma falha sobreviver
   ao rollback dela. No volume do bot é desprezível.
