# Relatório Sprint S0.1 — Webhook Asaas + `confirm()`: parar de perder pagamento sem rastro

Branch: `fix/s01-webhook-confirm` (sem push — aguarda revisão do auditor e autorização do Silva).
Refs: A4 §2.1 (Defeito A) e §2.2 (Defeito B). Data: 2026-07-19.

## O que mudou, arquivo por arquivo

### `agendamento_engine/app/modules/payments/service.py` — `confirm()`

**Defeito A.** O `try` que cobria os passos 2–5 foi dividido em dois blocos:

1. **Passo 2 isolado** (INSERT do PaymentTransaction, o evento de idempotência):
   é o ÚNICO lugar onde `IntegrityError` é candidato a duplicata
   (UNIQUE `(company_id, provider_transaction_id)`).
2. **Verificação antes de declarar duplicata:** no caminho de `IntegrityError`,
   após o rollback o `Payment` é **recarregado do banco**. Só é tratado como
   duplicata benigna se `status == "CONFIRMED"`. Caso contrário (PENDING, ou
   linha inexistente), a exceção original **propaga** com `logger.error`
   contextualizado — antes, esse caso devolvia o Payment PENDING como se fosse
   o caminho feliz.
3. **Passos 3–5 + commit** ficam num segundo `try` com `except Exception:
   rollback + logger.exception + raise` — violação de FK/NOT NULL do
   `financial_core.handle_payment_confirmed` agora propaga em vez de ser
   engolida como "duplicata".

Logs adicionados carregam apenas identificadores (`payment_id`, `event_id`,
`external_charge_id`, `status`) — sem PII, sem payload. `mask_cpf_cnpj` não foi
tocado nem ganhou uso novo (A5 §2.2).

Docstring atualizada para refletir a semântica nova.

### `agendamento_engine/app/modules/payments/router.py` — `webhook_asaas_transaction`

**Defeito B.** O contrato de resposta agora segue o que o Asaas realmente lê
(status HTTP, nunca o corpo):

- **`confirm()` falhou** → `HTTPException 500` (antes: 200 com `{"ok": false}`,
  que o Asaas interpretava como processado e nunca reenviava). `logger.exception`
  mantido, enriquecido com `event`, `external_charge_id` e `payment_id`.
- **Payment não encontrado (`:263`)** → veredito: **corrida, não skip**. Com o
  gate de evento (abaixo), só chegam a esse ponto eventos de pagamento
  confirmado — se o Payment não existe, o webhook chegou antes do commit da
  linha Payment. Resposta: `HTTPException 503` + `logger.warning` → Asaas
  reenvia quando a linha existir. Escolha documentada em comentário no código.
- **Sem `event_id` (`:242`)** → veredito: **skip legítimo, 200 mantido**.
  Payload sem `id` é malformado/não-nosso; o reenvio traria o MESMO payload —
  retry não resolve nada. `logger.warning` já existia; comentário adicionado.
- **Gate de tipo de evento (decisão aprovada pelo Silva no planejamento):**
  só `PAYMENT_RECEIVED` e `PAYMENT_CONFIRMED` chamam `confirm()`; demais →
  200 `{"skipped": "event_not_handled"}` com `logger.info`. Dois motivos:
  (a) **bug real pré-existente**: qualquer evento com `id` que resolvesse um
  Payment o confirmava — um `PAYMENT_CREATED` ou `PAYMENT_OVERDUE` marcaria o
  pagamento como pago; (b) sem o gate, o 503 do `payment_not_found` prenderia a
  fila de retry do Asaas com eventos irrelevantes de cobranças desconhecidas
  (o Asaas pausa a fila após falhas repetidas — um evento eternamente 5xx
  bloquearia os legítimos atrás dele).

### `agendamento_engine/tests/test_s01_webhook_confirm.py` (novo, 11 testes)

Estilo unitário com mocks, mesmo padrão de `test_sprint9_payments.py`:

1. Duplicata legítima (IntegrityError + Payment CONFIRMED no banco) → retorna
   Payment, sem commit, sem financial_core, sem mark_processed.
2. IntegrityError com Payment ainda PENDING → propaga + log de erro (caplog).
3. IntegrityError com Payment inexistente no reload → propaga.
4. IntegrityError dentro do Financial Core → propaga, rollback, mark_processed
   não chamado, log "falha nos passos 3-5".
5. Router: confirm falha → HTTPException 500.
6. Router: payment não encontrado com evento de confirmação → HTTPException 503,
   confirm não chamado.
7. Router: gate — PAYMENT_CREATED/PAYMENT_OVERDUE/PAYMENT_UPDATED/"" → 200
   skipped, confirm não chamado (parametrizado).
8. Router: PAYMENT_RECEIVED/PAYMENT_CONFIRMED → confirm chamado (parametrizado).
9. Router: sem event_id → 200 skipped (comportamento preservado).

## Decisões de implementação

- **`:242`** — 200 mantido: retry de payload imutável sem `id` é inútil por
  definição; não esconde falha nossa (nada foi tentado).
- **`:263`** — 503 (Service Unavailable): semanticamente "tente de novo mais
  tarde", exatamente a corrida webhook × commit. Condicionado ao gate de evento
  para não travar a fila do Asaas com cobranças que nunca existirão no nosso
  banco.
- **500 para falha de `confirm()`**: falha de processamento do nosso lado;
  qualquer não-2xx faz o Asaas reenviar, e o reenvio passa pela idempotência
  (`is_processed` + UNIQUE) — reprocessamento é seguro.
- **Duplicata verificada contra o banco**: o critério de "duplicata bem-sucedida"
  é o `Payment` recarregado estar CONFIRMED — não o objeto em memória.
- Os testes existentes 6 e 7 de `test_sprint9_payments.py` continuam válidos sem
  alteração (o 6 já mockava o reload devolvendo CONFIRMED; o 7 usa RuntimeError,
  que já propagava).

## Resultado da suíte

- **Baseline (main, antes das mudanças):** 1279 passed, 12 failed, 6 skipped,
  1 xfailed — as 12 falhas são as rbac pré-existentes conhecidas
  (`test_sprint2_rbac.py`, contaminação de ordenação de import; documentadas
  no CLAUDE.md desde o Estágio 0).
- **Depois das mudanças:** 1292 passed, 12 failed (as MESMAS 12 rbac), 6
  skipped, 1 xfailed. +13 passed = 11 testes novos + 1 teste existente
  atualizado (abaixo) + 1 parametrização.
- Módulo payments direcionado: `test_s01_webhook_confirm.py` (11) +
  `test_sprint9_payments.py` (24) + `test_asaas_integration.py` (12 + 1 xfail)
  = **47 passed, 1 xfailed**.

### Teste pré-existente que quebrou — e por quê

`test_asaas_integration.py::test_webhook_transaction_skips_when_payment_not_found`
afirmava o comportamento defeituoso do `:263`: 200 + `skipped=payment_not_found`
para evento `PAYMENT_RECEIVED` cuja cobrança não existe no banco — exatamente a
corrida que este sprint corrige. Não foi "consertado para passar": o contrato
mudou de propósito, e o teste foi atualizado para o contrato novo (renomeado
para `test_webhook_transaction_returns_503_when_payment_not_found`, espera
HTTPException 503 `payment_not_yet_visible`), com o motivo documentado na
docstring. Nenhuma outra quebra fora das 12 rbac pré-existentes.

## Achados fora de escopo (para a fila, não para agora)

1. **Evento de confirmação sem checagem de status atual do Payment**: `confirm()`
   confirma mesmo se o Payment estiver REFUNDED/CANCELLED (um `event_id` novo
   para um Payment já estornado o re-confirmaria). A idempotência é por evento,
   não por estado do Payment. Candidato ao sprint de idempotência D7.
2. **Webhook `/asaas/transaction` sem validação de assinatura**: o endpoint
   irmão `/asaas/account_status` valida `asaas-access-token`
   (`ASAAS_WEBHOOK_TOKEN`); o de transaction não valida nada — qualquer POST
   anônimo com payload bem-formado poderia confirmar um pagamento cujo
   `external_charge_id` seja conhecido/adivinhado. Mitigado parcialmente pela
   idempotência, mas é superfície de fraude. Fica para a fila (mexeria no
   contrato do endpoint; não era escopo deste sprint).
3. **`webhook_asaas_account_status` `:304`** devolve 200 `skipped=missing_fields`
   para payload incompleto — análogo ao `:242`, parece skip legítimo, mas não
   foi auditado neste sprint (fora do caminho de transaction).
