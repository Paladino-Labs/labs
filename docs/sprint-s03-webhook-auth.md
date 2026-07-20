# Sprint S0.3 — Autenticar o webhook Asaas de transaction

**Branch:** `fix/s03-webhook-auth` (base: `fix/s01-webhook-confirm` @ 4ac901d — ver "Nota de git" abaixo)
**Status:** implementado, aguardando auditoria e autorização de push do Silva.
**Fecha o Bloco 0** (S0.1 → S0.2 → S0.3).

---

## 1. Investigação (Passo 1) — a parte mais importante

### 1.1 Como o `account_status` validava

Token estático lido de `settings.ASAAS_WEBHOOK_TOKEN` (env var, default `""` em
`app/core/config.py:98`), comparado com o header `asaas-access-token`. Três defeitos:

1. **Comparação `!=` simples** — não tempo-constante (vazamento por timing).
2. **Fail-open silencioso**: `if expected_token and ...` — com a env var vazia, a
   validação era **pulada sem log**. Token vazio = porta aberta.
3. **Log vazava credencial**: a rejeição logava `token_received[:8]` — se o remetente
   legítimo errasse a config, 8 caracteres do token real iam para o log.

Falha respondia 401 (correto — Asaas reenvia em não-2xx).

### 1.2 O que o Asaas oferece

Verificado na documentação oficial (docs.asaas.com/docs/about-webhooks): o único
mecanismo é **token estático** enviado em **toda notificação** no header
`asaas-access-token`, configurável **por webhook** no painel (até 10 webhooks, cada um
com seu token). **Não existe HMAC do payload.** A opção "superior" do enunciado não
está disponível no provider — token estático não é escolha nossa, é o teto do Asaas.

### 1.3 O segredo existe no ambiente?

- `.env` local: **não** contém `ASAAS_WEBHOOK_TOKEN`.
- Railway: **sim, configurado — mas é o token sandbox** (confirmado pelo Silva).
- ⚠️ **Fila (ação do Silva):** ao ativar a conta Asaas de produção, gerar token novo
  no painel de produção e atualizar a env var no Railway. O código não muda.

**Consumidores da env var no repo (grep completo, pedido da revisão):** 2 de produção —
`app/core/config.py:98` (definição) e `app/modules/payments/router.py` (os dois
webhooks, agora via helper único) — mais os testes. Nenhum terceiro consumidor;
por isso o tipo permaneceu `str` default `""` (sem risco de `AttributeError` remoto).

### 1.4 Tráfego legítimo hoje?

Consulta read-only em produção (2026-07-19):

- 4 payments `provider=asaas`, **todos CONFIRMED entre 02–03/jun** — testes de sandbox
  (`evt_teste_pix_001`, `evt_idem_teste_001` e 3 eventos sandbox reais `evt_d26e...`).
- **0 empresas com subconta Asaas** (`external_account_id IS NULL` em todas).
- Nenhum evento processado desde 03/jun.

**A integração está dormente.** Ativar validação fail-closed não derruba tráfego
legítimo porque não há tráfego legítimo. Zero risco operacional no deploy.

---

## 2. Escolha de mecanismo e desenho

**Token estático** — única opção do provider (§1.2). Decisões de desenho:

- **Helper único** `_require_asaas_webhook_token()` em `payments/router.py`, usado
  pelos dois endpoints — mesmo mecanismo, mesmo arquivo, sem espaço para divergirem.
- **Fail-closed** (decisão do Silva): token não configurado → 401 para tudo. O
  fail-open do `account_status` era exatamente o buraco; replicá-lo no endpoint de
  dinheiro seria manter a porta aberta com aparência de fechada.
- **`hmac.compare_digest`** sobre bytes — tempo constante.
- **Ausente / vazio / errado / não-configurado → mesmo 401, mesmo `detail`**
  ("Token de webhook inválido"). Indistinguível por construção — princípio do S0.2
  (sem oráculo). Header ausente e header vazio chegam ambos como `""` ao handler
  (`Header(default="")`); `""` nunca passa porque o ramo fail-closed rejeita antes
  mesmo de comparar, e `compare_digest` só roda com esperado não-vazio.
- **Validação ANTES de qualquer processamento** — antes do parse de `event_id`, antes
  de qualquer query (provado por teste: `db.query` não é chamado na rejeição).
- **401 (não-2xx)** → o Asaas reenfileira. Se o segredo estiver errado de um lado, o
  problema **aparece** (fila de retry crescendo + logs), em vez de eventos legítimos
  sumirem em silêncio. Interação correta com o contrato de status do S0.1.

### Logs (níveis e conteúdo — pedido da revisão)

| Situação | Nível | Momento | Conteúdo |
|---|---|---|---|
| Token não configurado | **ERROR** | boot (`lifespan` em `main.py`) **e** a cada request rejeitado | nomeia a consequência: "webhooks Asaas rejeitarão todas as requisições" |
| Token errado | WARNING | por request | `endpoint`, `event`, `origin` (IP), `token_len` |

O token recebido **nunca** vai ao log — nem prefixo (o `token_received[:8]` do
`account_status` foi removido). Assimetria deliberada: token errado é problema de
terceiro (warning); token ausente é falha **nossa** de config que bloqueia webhooks
legítimos até alguém agir (error). Coberto por teste.

---

## 3. Veredito sobre o `account_status` (item 5 do enunciado)

Tinha os 3 defeitos do §1.1. **Corrigido junto**, no mesmo commit, passando a usar o
mesmo helper: tempo-constante, fail-closed, log sem credencial. Os dois endpoints são
agora byte-idênticos na autenticação.

---

## 4. Idioma fail-open no restante do repo (grep pedido pelo Silva)

São **três** ocorrências do padrão "credencial configurada? senão aceita":

1. `account_status` — `if expected_token and ...` → **corrigido neste sprint**.
2. `transaction` — fail-open por omissão total (nenhuma validação) → **corrigido**.
3. **Webhook Evolution** (`whatsapp/router.py:94`) — `if settings.EVOLUTION_WEBHOOK_SECRET:`
   → **reportado, não corrigido** (fora de escopo).

**Veredito sobre o Evolution (pedido na 2ª revisão): é VARIAÇÃO, não copiar-colar.**
A forma difere (guard de bloco em vez de `and` na condição; `!=`; 401 via
`JSONResponse`; dois headers candidatos `apikey`/`x-evolution-global-apikey`) **e há
uma restrição operacional documentada no próprio código**: a Evolution API v2 **não
envia header de autenticação nos webhooks** — o comentário em `router.py:91-93` manda
manter o segredo vazio e confiar na URL privada. Ou seja: fail-open ali é hoje uma
*necessidade* documentada, não descuido. A correção futura **não é mecânica** — exige
análise própria (assinatura por URL secreta? validação por IP? upgrade da Evolution?).
Fica na fila com essa qualificação.

Nenhuma quarta ocorrência: grep por comparações de credencial contra `settings.*`
(`SECRET|TOKEN|KEY`) no `app/` inteiro não encontrou outros casos. O manage-token é
lookup por hash SHA-256 no banco (não comparação de segredo estático) — padrão correto.

---

## 5. Testes

### Suíte

Rodada completa na branch (`.\venv\Scripts\python.exe -m pytest tests/`):

**1309 passed, 12 failed, 6 skipped, 1 xfailed**

- As 12 failed são **exatamente** as conhecidas de `test_sprint2_rbac.py`
  (contaminação de ordem de import, documentadas no CLAUDE.md) — lista conferida
  uma a uma contra o output. **Nenhuma falha nova.**
- **Desvio da baseline 1294 (esperado e explicado pela base de git)**: a baseline do
  enunciado foi medida sobre `fix/s02-cross-tenant-users`; esta branch nasce de
  `fix/s01-webhook-confirm` (ver §6), então os 15 testes do S0.2 **não estão
  presentes aqui**, e entram os 17 novos do S0.3. O invariante que importa:
  **zero falha nova, zero teste removido, 17 adicionados, 10 ajustados** (abaixo).
- Nota de honestidade: a primeira rodada completa acusou uma 13ª falha —
  `test_asaas_integration.py::test_webhook_transaction_returns_503_when_payment_not_found`
  (teste do S0.1 que chamava o endpoint sem credencial). Ajustado com a mesma
  justificativa dos demais; rodada final limpa.

### Novos — `tests/test_s03_webhook_auth.py` (17 testes)

1. transaction sem credencial → 401, `confirm` não chamado, **nenhuma query executada**
2. transaction com credencial errada → 401, `confirm` não chamado
3. ausente/vazio/quase-certo → **mesmo status e mesmo detail** (indistinguibilidade)
4. token não configurado (`""`/`"   "`) → 401 para tudo + log **ERROR** (fail-closed;
   4 combinações parametrizadas)
5. log de rejeição não contém o token recebido **nem prefixo dele**
6. assimetria de severidade: errado = WARNING, nunca ERROR
7. transaction com credencial correta → processa (fluxo S0.1)
8. account_status: mesmos casos + **regressão do fail-open antigo** (vazio agora rejeita)
9. **Interação S0.1×S0.3** (pedido da revisão): autenticado, o gate de eventos
   (PAYMENT_OVERDUE → skip), o 503 da corrida e o 500 da falha de confirm continuam
   valendo — 3 testes dedicados.

### Ajustados (com justificativa)

- **`test_s01_webhook_confirm.py`** (7 testes de router): o endpoint agora exige
  credencial; os testes passam a autenticar com token válido via helper
  `_call_webhook` (patch de `settings` + header). **Nenhuma asserção de contrato
  mudou** — docstrings originais preservadas. Casos de rejeição vivem no arquivo do
  S0.3, não misturados aqui.
- **`test_sprint8_asaas_pii.py`** (2 testes): usavam `ASAAS_WEBHOOK_TOKEN = ""` como
  atalho para "sem validação" — isso **documentava o fail-open**. Com fail-closed,
  configuram `tok_test` e o enviam no header. O 3º teste (token inválido → 401) passou
  sem mudança.
- **`test_asaas_integration.py`** (1 teste): `test_webhook_transaction_returns_503...`
  (do S0.1) chamava sem credencial; agora autentica. A asserção (503 da corrida)
  não mudou.

### Verificação ponta-a-ponta (HTTP real via TestClient, com lifespan)

| Requisição | Resultado |
|---|---|
| transaction sem header | **401** `{"detail": "Token de webhook inválido"}` |
| transaction token errado | **401** (mesmo corpo — indistinguível) |
| transaction token certo, charge inexistente | **503** `payment_not_yet_visible` (contrato S0.1 intacto) |
| account_status token certo | **200** (processa) |
| account_status token errado | **401** |
| boot sem `ASAAS_WEBHOOK_TOKEN` | log **ERROR** nomeando a consequência |

---

## 6. Nota de git (importante para o merge)

O S0.1 (`fix/s01-webhook-confirm`, 4ac901d) **não está mesclado** em `main`. Como o
S0.3 estende o endpoint que o S0.1 reescreveu, esta branch nasce **de
`fix/s01-webhook-confirm`**, não de `main` nem do S0.2.

Estado das branches do Bloco 0 (todas de base 4118647, exceto s03):

```
main ── 4118647 ──┬── fix/s01-webhook-confirm (4ac901d) ── fix/s03-webhook-auth
                  └── fix/s02-cross-tenant-users (afe99af)
```

s02 toca `users/`; s01+s03 tocam `payments/router.py` — **sem conflito de arquivo**,
mas a ordem importa para a baseline de testes. **Decisão do Silva registrada:** merge
do Bloco 0 inteiro de uma vez (s01 → s02 → s03), não três merges separados.

## 7. Arquivos alterados

- `agendamento_engine/app/modules/payments/router.py` — helper + os dois webhooks
- `agendamento_engine/app/main.py` — ERROR no boot quando token não configurado
- `agendamento_engine/tests/test_s03_webhook_auth.py` — novo (17 testes)
- `agendamento_engine/tests/test_s01_webhook_confirm.py` — autenticação nos 7 de router
- `agendamento_engine/tests/test_sprint8_asaas_pii.py` — 2 testes de account_status
- `agendamento_engine/tests/test_asaas_integration.py` — 1 teste do S0.1 (503 da corrida)
- `docs/sprint-s03-webhook-auth.md` — este relatório

`CLAUDE.md` **não** foi tocado. Sem push. Sem commit em `main`.
`app/core/security.py` tem WIP pré-existente (bcrypt) **não relacionado** — permanece
fora dos commits deste sprint.

## 8. Achados fora de escopo (fila)

1. **Webhook Evolution fail-open** — variação com restrição operacional própria (§4);
   correção exige análise, não é mecânica.
2. **Token sandbox no Railway** — trocar por token de produção ao ativar a conta Asaas
   real (painel + env var). Ação do Silva.
3. **Rate limiting nos webhooks** — continua na fila (explicitamente fora de escopo).
4. **Merge do Bloco 0** — fazer de uma vez, ordem s01 → s02 → s03 (§6).
