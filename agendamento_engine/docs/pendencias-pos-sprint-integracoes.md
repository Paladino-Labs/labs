# Auditoria de Pendências — Pós-Sprint de Integrações
**Gerado em:** 2026-06-04 · **Encoding:** UTF-8
**Sessão:** Análise exclusiva — nenhum arquivo de código foi criado ou modificado.
**Commits analisados:** desde `d1e2f3g4h5i6` até HEAD local (`457d807` + working tree)

---

## Resumo executivo

| # | Item | Classificação | Ação imediata |
|---|------|:---:|---|
| P1 | Migration `g3h4i5j6k7l8` não commitada; ORM model staged sem commit; vários arquivos ` M` | **BLOQUEADOR** | Commitar antes de qualquer deploy |
| P2 | ID de migration `e1f2g3h4i5j6` já usado — plano Sprint 11 prevê o mesmo ID | **BLOQUEADOR** | Atualizar brief antes do Sprint 11 |
| P3 | `payment_service.refund()` nunca chama `provider.refund()` — estorno não acontece no gateway | **IMPORTANTE** | Registrar e corrigir antes de habilitar estorno em produção |
| P4 | `EVOLUTION_WEBHOOK_SECRET` — estado desconhecido no Railway (webhook potencialmente aberto) | **IMPORTANTE** | Verificar e configurar no Railway imediatamente |
| P5 | `asyncio.create_task` ainda ativo no lifespan — flip para Celery pendente | **IMPORTANTE** | Remover após confirmar 24 h sem erros |
| P6 | `birthDate` ausente em `create_subaccount` Asaas — CPF obrigatório em produção | **IMPORTANTE** | Coletar birthDate no onboarding antes de ir a produção Asaas |
| P7 | `PagSeguroProvider.refund()` é STUB com endpoint não confirmado — retorna HTTP 500 se chamado | **IMPORTANTE** | Bloquear rota de estorno para pagamentos PagSeguro até confirmar endpoint |
| P8 | CLAUDE.md com HEAD migration desatualizado (`d1e2f3g4h5i6`); endpoints novos não listados | **IMPORTANTE** | Atualizar CLAUDE.md no próximo commit |
| P9 | `SPRINT-LOG.md` não existe | **DÍVIDA** | Criar e manter |
| P10 | TODO `payment_submethod` — MAQUININHA cai em MAQUININHA_CREDIT sem distinção CREDIT/DEBIT | **DÍVIDA** | Adicionar campo `payment_submethod` em PaymentCreate no Sprint 11 |
| P11 | `fee_percentage=0` (≠ NULL) em MAQUININHA_CREDIT/DEBIT para tenants existentes — silencioso | **DÍVIDA** | UX: comunicar ao operador que a taxa precisa ser configurada |
| P12 | LOG DE DIAGNÓSTICO com dados completos da mensagem no webhook WhatsApp — risco de PII em logs | **DÍVIDA** | Remover blocos de diagnóstico após confirmação em produção |
| P13 | `ASAAS_API_URL` default `sandbox.asaas.com` — deve ser trocado para produção antes do Stage 0 | **DÍVIDA** | Configurar no Railway antes do go-live |
| P14 | `use_communication_service` — estado da flag no banco de produção desconhecido | **INFORMATIVO** | Verificar e ativar por tenant quando pronto |
| P15 | `MAILTRAP_SANDBOX_INBOX_ID` — 0 = produção na Mailtrap HTTP API; confirmar intenção no Railway | **INFORMATIVO** | Confirmar configuração antes de usar email em produção |

---

## Detalhe por pendência

---

### P1 — Migration `g3h4i5j6k7l8` não commitada + working tree divergente

**Classificação:** BLOQUEADOR

**O que foi encontrado:**

O `git status` no início da sessão revela:

```
M  agendamento_engine/app/infrastructure/db/models/tenant_fee_routing_policy.py  ← staged
 M agendamento_engine/app/modules/companies/service.py                            ← modificado, não staged
 M agendamento_engine/app/modules/payments/router.py                              ← modificado, não staged
 M agendamento_engine/app/modules/payments/schemas.py                             ← modificado, não staged
 M agendamento_engine/app/modules/payments/service.py                             ← modificado, não staged
 M agendamento_engine/migrations/versions/f2g3h4i5j6k7_add_fee_calc_to_routing_policy.py  ← modificado, não staged
 M agendamento_engine/migrations/versions/psg1a2b3c4d5_add_pagseguro_provider.py          ← modificado, não staged
 M agendamento_engine/tests/test_cash_payment.py                                  ← modificado, não staged
 M agendamento_engine/tests/test_fee_policies.py                                  ← modificado, não staged
 M agendamento_engine/tests/test_sprint6_financial_core.py                        ← modificado, não staged
?? agendamento_engine/migrations/versions/g3h4i5j6k7l8_add_maquininha_pix_fee_source.py   ← UNTRACKED
```

O último commit `457d807` capturou parte do trabalho da taxa automática de maquininha mas deixou de fora:
- A migration `g3h4i5j6k7l8` (MAQUININHA_PIX + fee_percentage nullable) — **nunca adicionada ao git**
- O ORM model com `fee_percentage = Column(Numeric(7,4), nullable=True)` — **staged mas não commitado**
- Todos os arquivos de serviço, router, schemas e testes — **modificados mas não staged**

**Impacto em produção:**

| Cenário | O que acontece |
|---------|---------------|
| Deploy do código commitado sem a migration | `alembic upgrade head` para em `f2g3h4i5j6k7` (fee_percentage NOT NULL); ORM espera nullable=True após commit do modelo staged |
| Criação de nova empresa após deploy parcial | `create_company()` tenta INSERT MAQUININHA_PIX com `fee_percentage=NULL` → violação de constraint NOT NULL → HTTP 500 |
| Testes rodados no CI (se existir) | Testam o código commitado (457d807), não o working tree — passam na versão antiga |

**Ação recomendada:**
1. Adicionar `g3h4i5j6k7l8` ao git: `git add agendamento_engine/migrations/versions/g3h4i5j6k7l8_*.py`
2. Stagear os demais arquivos modificados
3. Criar o commit de fechamento
4. Aplicar em produção: `alembic upgrade head`

---

### P2 — ID de migration `e1f2g3h4i5j6` usado — conflito com Sprint 11

**Classificação:** BLOQUEADOR

**O que foi encontrado:**

O brief `brief-fase3-backend-only.md` planeja a migration do Sprint 11 com:
```python
# brief-fase3-backend-only.md linha 99
**`e1f2g3h4i5j6_catalog_optins`**
```

O Sprint de Integrações já criou e commitou:
```
agendamento_engine/migrations/versions/e1f2g3h4i5j6_add_asaas_customer_id_to_customers.py
revision: str = "e1f2g3h4i5j6"
```

O Alembic identifica migrations pelo campo `revision`, não pelo nome do arquivo. Dois arquivos com `revision = "e1f2g3h4i5j6"` quebrariam o grafo de migrações.

**IDs usados pelo Sprint de Integrações:**

| Revision ID | Arquivo | Status |
|-------------|---------|--------|
| `e1f2g3h4i5j6` | add_asaas_customer_id_to_customers | ✅ commitado |
| `psg1a2b3c4d5` | add_pagseguro_provider | ✅ commitado (` M` local) |
| `f2g3h4i5j6k7` | add_fee_calc_to_routing_policy | ✅ commitado (` M` local) |
| `g3h4i5j6k7l8` | add_maquininha_pix_fee_source | ❌ não commitado |

**IDs do brief Fase 3 afetados:**

| Sprint | ID Planejado | Conflito? |
|--------|-------------|----------|
| Sprint 11 | `e1f2g3h4i5j6` | **SIM — já em uso** |
| Sprint 12 | `f1g2h3i4j5k6` | Não (diferente de `f2g3h4i5j6k7`) |
| Sprint 13 | `g1h2i3j4k5l6` | Não (diferente de `g3h4i5j6k7l8`) |
| Sprint 14+ | `h1i2...` em diante | Nenhum conflito identificado |

**Ação recomendada:**
- Sprint 11 deve usar ID diferente, por exemplo `e2f3g4h5i6j7_catalog_optins`
- Atualizar `brief-fase3-backend-only.md` antes de iniciar o Sprint 11

---

### P3 — `payment_service.refund()` não chama `provider.refund()` — estorno apenas contábil

**Classificação:** IMPORTANTE

**O que foi encontrado:**

`payments/service.py:refund()` (linhas 497–566) implementa estorno via:
1. `financial_core.handle_payment_refunded()` → Movement OUTFLOW + Entry ESTORNO
2. `payment.status = "REFUNDED"`
3. `record_sensitive_action()`
4. `db.commit()`
5. `EventBus.publish("payment.refunded")`

**Em nenhum momento chama `provider.refund(external_charge_id, reason)`.**

Isso significa que para pagamentos Asaas (PIX, BOLETO), o estorno é registrado localmente no Financial Core mas o cliente **não recebe o dinheiro de volta** — a cobrança continua aberta no Asaas. O operador precisaria fazer o estorno manualmente no painel Asaas.

Para PagSeguro, o problema é duplo: além de não ser chamado, `PagSeguroProvider.refund()` é um STUB com endpoint não confirmado (ver P7).

**Impacto:**
- Operadores que clicam em "Estornar" veem sucesso na tela, mas o dinheiro não volta ao cliente automaticamente
- Sem aviso ao usuário sobre a necessidade de ação manual no painel do gateway

**Ação recomendada:**
- Adicionar chamada `provider.refund()` antes do `financial_core.handle_payment_refunded()` para payments com provider != "manual"
- Para provider=manual/CASH: sem chamada ao provider (correto)
- Para Asaas: chamar `provider.refund()` e lidar com `AsaasError`
- Para PagSeguro: bloquear temporariamente (ver P7)
- Adicionar `fee_warning` no response de refund quando estorno no gateway falha mas contabilidade foi registrada

---

### P4 — `EVOLUTION_WEBHOOK_SECRET` — estado desconhecido no Railway

**Classificação:** IMPORTANTE

**O que foi encontrado:**

`config.py:45`: `EVOLUTION_WEBHOOK_SECRET: str = ""`

`whatsapp/router.py:92–96`:
```python
if settings.EVOLUTION_WEBHOOK_SECRET:
    incoming_key = request.headers.get("x-evolution-global-apikey", "")
    if incoming_key != settings.EVOLUTION_WEBHOOK_SECRET:
        return JSONResponse(status_code=401, content={"status": "rejected"})
```

Se `EVOLUTION_WEBHOOK_SECRET` estiver vazio (default), **qualquer request HTTP ao endpoint `POST /whatsapp/webhook` é aceito sem validação**. Um agente malicioso pode injetar mensagens sintéticas, triggerando o FSM do bot com dados fabricados.

**Ação recomendada:**
- Verificar no painel Railway se `EVOLUTION_WEBHOOK_SECRET` está configurado
- Se não estiver: configurar imediatamente com um valor aleatório forte (`openssl rand -hex 32`)
- Configurar o mesmo valor em `AUTHENTICATION_API_KEY` da Evolution API para que ela envie o header

---

### P5 — `asyncio.create_task` ainda ativo no lifespan

**Classificação:** IMPORTANTE

**O que foi encontrado:**

`app/main.py:138–139`:
```python
asyncio.create_task(run_session_cleanup_worker(), name="session_cleanup_worker"),
asyncio.create_task(run_reminder_worker(), name="reminder_worker"),
```

O CLAUDE.md (linhas 157–158) diz explicitamente:
> "asyncio.create_task ainda ATIVO no lifespan (coexistência) — remover somente após 24h sem erros em produção"

O Sprint de Integrações decorreu sem que o flip fosse feito. Não se sabe há quantos dias o Celery está em produção.

**Impacto:**
- Dois sistemas de worker coexistindo: Celery Beat (session-cleanup, reminder-worker) E `asyncio.create_task` no lifespan
- Duplicação de execuções: o mesmo cleanup/reminder roda duas vezes
- Possibilidade de race condition em operações de cleanup

**Ação recomendada:**
1. Verificar logs de produção — se não há erros de Celery há mais de 24 h, proceder com o flip
2. Remover as linhas `asyncio.create_task` do lifespan
3. Atualizar CLAUDE.md: remover a ressalva de coexistência

---

### P6 — `birthDate` ausente em `create_subaccount` Asaas

**Classificação:** IMPORTANTE

**O que foi encontrado:**

`providers/asaas.py:92–109`, `create_subaccount()`:
```python
payload = {
    "name": name,
    "email": email,
    "cpfCnpj": cpf_cnpj,
    "companyType": "MEI",
}
```

Campo `birthDate` ausente. A Asaas **exige** `birthDate` para subcontas com CPF (pessoa física / MEI) na API de produção.

`companies/service.py:255–258` chama:
```python
provider.create_subaccount(
    name=company.name,
    cpf_cnpj="",  # owner CPF não disponível neste fluxo — Asaas aceita vazio para MEI
    email=owner_email,
)
```

`cpf_cnpj=""` e `birthDate` ausente — dois campos críticos faltando para o ambiente de produção Asaas. O ambiente sandbox pode aceitar, mas produção provavelmente rejeita.

**Impacto:**
- Novos tenants em produção Asaas ficarão sem `external_account_id`
- Cobrança PIX/BOLETO via Asaas não funcionará para esses tenants (sem conta vinculada)
- A falha é silenciosa: `create_company()` captura a exceção e loga apenas `warning`

**Ação recomendada:**
1. Coletar `birth_date` (ISO `YYYY-MM-DD`) e `cpf_cnpj` do OWNER no fluxo de criação de empresa
2. Passar para `create_subaccount()` e incluir no payload Asaas
3. Alternativa de curto prazo: coletar via endpoint separado `PATCH /companies/payment-provider` após onboarding

---

### P7 — `PagSeguroProvider.refund()` é STUB — retorna HTTP 500 se chamado

**Classificação:** IMPORTANTE

**O que foi encontrado:**

`providers/pagseguro.py:430–443`:
```python
def refund(self, external_charge_id: str, reason: str) -> dict:
    """[STUB] Estorno de cobrança em terminal PagSeguro.

    ⚠ ENDPOINT NÃO CONFIRMADO: URLs de estorno retornaram 404 em 2026-06-03.
    """
    logger.warning("pagseguro_refund_endpoint_unconfirmed", ...)
    data = self._post(f"/charges/{external_charge_id}/cancel", {})
    return data
```

Se chamado: `self._post` faz HTTP real para `/charges/{id}/cancel`. Se retornar 404 → `PagSeguroError` → propagada para cima → HTTP 500 para o cliente.

Combinado com o P3 (provider.refund não chamado em payments/service.py), a situação atual é:
- `POST /payments/{id}/refund` para pagamento PagSeguro: registra estorno contábil localmente ✅, **não chama provider.refund** ✅ (acidentalmente correto)
- Se P3 for corrigido sem antes confirmar o endpoint: passará a chamar e retornará 500

**Ação recomendada:**
- Contatar time comercial PagBank para confirmar endpoint de estorno
- Candidato documentado: `POST /charges/{charge_id}/cancel`
- Implementar apenas quando endpoint confirmado em sandbox
- Enquanto isso: adicionar guard em `payment_service.refund()` para bloquear chamada ao provider quando `provider == "pagseguro"` e logar instrução de ação manual

---

### P8 — CLAUDE.md com HEAD migration desatualizado e endpoints novos não listados

**Classificação:** IMPORTANTE

**O que foi encontrado:**

CLAUDE.md linha 24: `**HEAD migration:** d1e2f3g4h5i6 (align_orm_schema_gaps)`

O HEAD atual deveria ser `g3h4i5j6k7l8` (quando commitado) ou `f2g3h4i5j6k7` (atual no git).

Endpoints criados no sprint **não listados no CLAUDE.md**:
- `POST /payments/{id}/confirm-manual` — OWNER/ADMIN; CASH/manual; retorna `ConfirmManualResponse` com `fee_warning` opcional
- `GET /payments/terminals` — OWNER/ADMIN; lista terminais PagSeguro Point (stub)
- `GET /financial/fee-policies` — OWNER/ADMIN; lista 8 políticas MDR do tenant
- `PATCH /financial/fee-policies/{fee_source}` — OWNER/ADMIN; atualiza `fee_percentage` / `fee_flat`

Padrões arquiteturais novos não documentados:
- `confirm_manual()` retorna `tuple[Payment, Optional[dict]]` — wrapper determinístico de `confirm()`
- `_calc_manual_fee()` — cálculo de taxa MDR via `TenantFeeRoutingPolicy`
- `FeeWarning` schema — retornado quando taxa não configurada (fee_percentage=NULL)
- `provider_factory` com seleção de provider: PAGSEGURO → `PagSeguroProvider`; fallback → `AsaasProvider`

Decisões arquiteturais não documentadas:
- PagSeguro Point não tem REST API pública para push de cobranças (pesquisa 2026-06-03)
- `fee_percentage=NULL` significa "não configurado" → dispara `fee_warning`; `fee_percentage=0` significa "0% configurado" → sem aviso
- Mailtrap HTTP API como fallback quando Railway bloqueia SMTP (portas 25/465/587/2525) — parcialmente documentado, mas Mailtrap sandbox ≠ produção

---

### P9 — `SPRINT-LOG.md` não existe

**Classificação:** DÍVIDA

**O que foi encontrado:**

O arquivo `agendamento_engine/SPRINT-LOG.md` não existe no repositório. O roadmap e CLAUDE.md referenciam o conceito de log de sprints, mas nenhum arquivo foi criado para registrar o histórico.

**Ação recomendada:**

Criar `agendamento_engine/SPRINT-LOG.md` com a entrada do Sprint de Integrações (ver seção "Entrada para SPRINT-LOG.md" abaixo).

---

### P10 — TODO `payment_submethod` — MAQUININHA sem distinção CREDIT/DEBIT

**Classificação:** DÍVIDA

**O que foi encontrado:**

`payments/service.py:383–385` (comentário inline):
```python
# TODO: usar payment_submethod ("CREDIT"/"DEBIT") para distinguir
#        MAQUININHA_CREDIT vs MAQUININHA_DEBIT quando o campo for
#        implementado em PaymentCreate e salvo no Payment.
```

`_PAYMENT_METHOD_TO_FEE_SOURCE`:
```python
"MAQUININHA": "MAQUININHA_CREDIT",  # fallback — sem distinção
```

Quando o operador cria um pagamento com `payment_method="MAQUININHA"` sem especificar se é crédito ou débito, o sistema usa a taxa MDR de MAQUININHA_CREDIT silenciosamente. Se as taxas de crédito e débito forem diferentes (o que é comum — crédito tipicamente 1,5–3%, débito 1–1,5%), o cálculo será incorreto para transações de débito registradas como "MAQUININHA" genérico.

**Impacto para Stage 0:** baixo — o operador pode usar `MAQUININHA_CREDIT` ou `MAQUININHA_DEBIT` diretamente. O tipo genérico `MAQUININHA` é um facilitador, não obrigatório.

**Ação recomendada:**
- Adicionar campo `payment_submethod: Optional[str]` em `PaymentCreate` com valores `"CREDIT" | "DEBIT" | None`
- Quando presente, sobrescrever o fee_source em `_calc_manual_fee()`
- Sugestão de Sprint: pode ser feito em Sprint 11 junto com outros fixes de schema

---

### P11 — `fee_percentage=0` em MAQUININHA_CREDIT/DEBIT para tenants existentes — silencioso

**Classificação:** DÍVIDA

**O que foi encontrado:**

A migration `f2g3h4i5j6k7` adicionou `fee_percentage NOT NULL DEFAULT 0`. Isso significa que todos os registros `MAQUININHA_CREDIT` e `MAQUININHA_DEBIT` existentes antes do sprint foram preenchidos com `fee_percentage=0`.

Na lógica de `_calc_manual_fee()`:
```python
if policy.fee_percentage is None:
    return Decimal("0"), fee_source  # dispara warning
```

`fee_percentage=0` ≠ `None`, portanto **não dispara warning**. O cálculo resulta em `fee=0` (0% de MDR), sem aviso ao operador.

Situação por tipo de tenant:

| Tenant | MAQUININHA_CREDIT | MAQUININHA_DEBIT | MAQUININHA_PIX |
|--------|:---:|:---:|:---:|
| Criado antes do sprint | `fee_percentage=0` (sem warning) | `fee_percentage=0` (sem warning) | Não existe ainda |
| Criado após commit g3h4i5j6k7l8 | `fee_percentage=0` (sem warning) | `fee_percentage=0` (sem warning) | `fee_percentage=NULL` (com warning) |

O comportamento é **semanticamente correto** (0 = "configurado, sem taxa") mas é **confuso para tenants existentes** que nunca configuraram a taxa — eles não saberão que deveriam configurar uma taxa MDR.

**Ação recomendada:**
- Adicionar um aviso visual no painel ao acessar Configurações → Financeiro → Taxas quando `fee_percentage=0` e o operador nunca atualizou a política
- Alternativa: mudar DEFAULT de 0 para NULL para MAQUININHA_CREDIT/DEBIT também, e migrar os existentes (breaking change)
- Decisão de produto necessária antes de implementar

---

### P12 — LOG DE DIAGNÓSTICO com dados completos da mensagem no webhook WhatsApp

**Classificação:** DÍVIDA

**O que foi encontrado:**

`whatsapp/router.py:110–118`:
```python
# LOG DE DIAGNÓSTICO — remover após confirmar funcionamento
import json as _json
logger.info(
    "WEBHOOK RECEBIDO event=%s event_normalized=%s instance=%s data_keys=%s",
    event, event_normalized, instance_name,
    list(data.keys()) if isinstance(data, dict) else type(data).__name__,
)
if event_normalized == "messages.upsert":
    logger.info("WEBHOOK DATA COMPLETO: %s", _json.dumps(data, default=str)[:1000])
```

Problemas:
1. `import json as _json` dentro do handler — executado a cada webhook (ineficiente)
2. `WEBHOOK DATA COMPLETO` loga até 1000 chars do payload, que pode conter o texto da mensagem do cliente (PII)
3. O comentário "remover após confirmar funcionamento" não foi removido pós-validação

**Ação recomendada:**
- Verificar se o WhatsApp webhook está funcionando corretamente em produção
- Após confirmar: remover os blocos de `logger.info("WEBHOOK DATA COMPLETO...")` e `logger.info("MESSAGES_UPDATE DATA...")`
- Mover o `import json` para o topo do arquivo se ainda necessário

---

### P13 — `ASAAS_API_URL` default aponta para sandbox

**Classificação:** DÍVIDA

**O que foi encontrado:**

`config.py:93`: `ASAAS_API_URL: str = "https://sandbox.asaas.com/api/v3"`

Se o Railway não tiver `ASAAS_API_URL` configurado explicitamente, o sistema usará o sandbox Asaas em produção. Cobranças "confirmadas" via webhook não correspondem a dinheiro real.

**Ação recomendada:**
- Configurar `ASAAS_API_URL=https://api.asaas.com/v3` no Railway antes do Stage 0
- Configurar `ASAAS_API_KEY` com a chave de produção (não sandbox)
- Verificar se `ASAAS_WEBHOOK_TOKEN` está configurado (validação do webhook de transação)

---

### P14 — `use_communication_service` — estado desconhecido em produção

**Classificação:** INFORMATIVO

**O que foi encontrado:**

A feature flag está em `TenantConfig.permission_overrides["use_communication_service"]` com default `False`. Quando False, notificações de appointment ainda usam `evolution_client.send_text()` diretamente (caminho legado).

Não foi possível verificar o estado no Railway sem acesso direto ao banco.

**Procedimento para ativar por tenant (não automatizar):**
```sql
UPDATE tenant_configs
SET permission_overrides = permission_overrides || '{"use_communication_service": true}'::jsonb
WHERE company_id = '<company_uuid>';
```

---

### P15 — `MAILTRAP_SANDBOX_INBOX_ID` — 0 = produção na HTTP API

**Classificação:** INFORMATIVO

**O que foi encontrado:**

`config.py:109`: `MAILTRAP_SANDBOX_INBOX_ID: int = 0  # 0 = produção; > 0 = sandbox (testing)`

A lógica em `_send_email()` provavelmente usa `MAILTRAP_SANDBOX_INBOX_ID` para determinar o endpoint:
- `0` → API de envio real (`https://send.api.mailtrap.io/...`)
- `> 0` → Sandbox inbox (`https://sandbox.api.mailtrap.io/...`)

Se o Railway tiver `MAILTRAP_SANDBOX_INBOX_ID` não configurado (default `0`), emails irão para destinatários reais quando `MAILTRAP_API_TOKEN` estiver preenchido.

**Ação recomendada:**
- Configurar `MAILTRAP_SANDBOX_INBOX_ID` com o ID do inbox de sandbox durante testes
- Remover ou setar para 0 apenas quando pronto para envio real em produção
- Documentar a semântica no CLAUDE.md

---

## Migrations pendentes de aplicação em produção

A cadeia atual de migrations adicionadas no Sprint de Integrações:

```
d1e2f3g4h5i6 (HEAD anterior ao sprint)
    ↓
e1f2g3h4i5j6  add_asaas_customer_id_to_customers
    ↓
psg1a2b3c4d5  add_pagseguro_credential_provider
    ↓
f2g3h4i5j6k7  add_fee_calc_to_routing_policy
    ↓
g3h4i5j6k7l8  add_maquininha_pix_fee_source  ← NÃO COMMITADA
```

**Estado estimado em produção Railway:** provavelmente `d1e2f3g4h5i6` (HEAD pré-sprint)

**Pré-requisito:** commitar `g3h4i5j6k7l8` e todos os arquivos pendentes (ver P1)

**Comando de aplicação (depois do commit):**
```bash
alembic upgrade head
```

**Análise de risco por migration:**

| Migration | Operação | Risco | Observação |
|-----------|----------|:-----:|------------|
| `e1f2g3h4i5j6` | `ADD COLUMN IF NOT EXISTS asaas_customer_id VARCHAR(50)` | Baixo | Nullable, sem default — seguro em tabela com dados |
| `psg1a2b3c4d5` | `ALTER TYPE credentialprovider ADD VALUE IF NOT EXISTS 'PAGSEGURO'` | Baixo | Idempotente com IF NOT EXISTS; irrevogável (downgrade é no-op) |
| `f2g3h4i5j6k7` | `ADD COLUMN fee_percentage NOT NULL DEFAULT 0, fee_flat NOT NULL DEFAULT 0, is_active BOOLEAN NOT NULL DEFAULT TRUE` | Baixo | IF NOT EXISTS; DEFAULT garante retrocompatibilidade |
| `g3h4i5j6k7l8` | `ALTER COLUMN fee_percentage DROP NOT NULL` + seed INSERT MAQUININHA_PIX | Baixo | ON CONFLICT proteção implícita via UNIQUE; DROP NOT NULL sem lock longo no PostgreSQL 12+ |

**Seed SQL da migration `g3h4i5j6k7l8`** (inserido automaticamente pelo `upgrade()`):
```sql
INSERT INTO tenant_fee_routing_policies (...)
SELECT gen_random_uuid(), id, 'MAQUININHA_PIX', 0, 100, 0, NULL, 0, TRUE, now()
FROM companies
WHERE NOT EXISTS (
    SELECT 1 FROM tenant_fee_routing_policies tfp
    WHERE tfp.company_id = companies.id AND tfp.fee_source = 'MAQUININHA_PIX'
)
```
Este seed roda dentro do `alembic upgrade` — não precisa de execução separada.

---

## Variáveis de ambiente — estado atual vs. necessário

| Variável | Adicionada neste sprint? | Obrigatória produção? | Status esperado no Railway |
|----------|:---:|:---:|---|
| `DATABASE_URL` | Não | Sim | ✅ Configurada |
| `SECRET_KEY` | Não | Sim | Verificar — default inseguro |
| `CREDENTIAL_ENCRYPTION_KEY` | Não | Sim | ✅ Configurada (vault) |
| `PII_ENCRYPTION_KEY` | Não | Sim | Verificar |
| `PII_HASH_KEY` | Não | Sim | Verificar |
| `ASAAS_API_KEY` | Não | Sim | ⚠️ Verificar se é sandbox ou produção |
| `ASAAS_API_URL` | Não | Sim | ⚠️ Provavelmente sandbox (default) — trocar para produção |
| `ASAAS_WEBHOOK_TOKEN` | Não | Sim | ⚠️ Verificar se foi configurado |
| `MAILTRAP_API_TOKEN` | **Sim** | Se email habilitado | ⚠️ Verificar — sandbox vs. produção |
| `MAILTRAP_SANDBOX_INBOX_ID` | **Sim** | Se email em sandbox | Verificar — 0 = produção |
| `SMTP_HOST` | **Sim** | Fallback se Mailtrap ausente | Não obrigatório se Mailtrap configurado |
| `SMTP_PORT` | **Sim** | Fallback | Não obrigatório se Mailtrap configurado |
| `SMTP_USER` | **Sim** | Fallback | Não obrigatório se Mailtrap configurado |
| `SMTP_PASSWORD` | **Sim** | Fallback | Não obrigatório se Mailtrap configurado |
| `SMTP_FROM_EMAIL` | **Sim** | Fallback | Não obrigatório se Mailtrap configurado |
| `SMTP_USE_TLS` | **Sim** | Fallback | Não obrigatório se Mailtrap configurado |
| `EVOLUTION_WEBHOOK_SECRET` | **Sim** | Recomendado | ⚠️ Estado desconhecido — verificar urgente (P4) |
| `REDIS_URL` | Não | Sim (Celery) | ✅ Configurada |
| `EVOLUTION_API_URL` | Não | Sim | ✅ Configurada |
| `EVOLUTION_API_KEY` | Não | Sim | ✅ Configurada |

**Nota sobre PagSeguro:** as credenciais são armazenadas via `IntegrationCredential` com provider=PAGSEGURO — não há variáveis de ambiente em `config.py` para o PagSeguro. O tenant configura via `POST /integrations/credentials`.

---

## Diff sugerido para CLAUDE.md

Apenas as seções que precisam mudar — não reescrever o arquivo inteiro.

### 1. Atualizar HEAD migration (linha 24)

```diff
-**HEAD migration:** d1e2f3g4h5i6 (align_orm_schema_gaps)
-**Total migrations Fase 2 + alinhamento:** 20 (k1→d1)
+**HEAD migration:** g3h4i5j6k7l8 (add_maquininha_pix_fee_source)
+**Total migrations Fase 2 + alinhamento + Sprint Integrações:** 24 (k1→d1→e1→psg→f2→g3)
```

### 2. Adicionar seção Sprint de Integrações após PaymentsEngine

```markdown
## Sprint de Integrações (pós-Fase 2)

### Email / CommunicationService
- Canal EMAIL em `dispatch()` via Mailtrap HTTP API (fallback: smtplib se SMTP_HOST configurado)
- `_send_email()` em `modules/communication/service.py`
- `forgot_password()` e `send_invite()` passam `recipient_email` no context
- MAILTRAP_API_TOKEN + MAILTRAP_SANDBOX_INBOX_ID em config.py
- Nota: Railway bloqueia SMTP (25/465/587/2525); usar Mailtrap HTTP API ou SendGrid em produção
- Templates `auth.password_reset_requested` e `user.invitation_sent` channel=EMAIL em `_DEFAULT_TEMPLATES`

### Asaas — correções críticas
- `create_payment()` chama `provider.create_charge()` antes do commit → `payment.external_charge_id` preenchido
- `confirm()` extrai value/fee do payload aninhado: `webhook_data.get("payment", {}).get("value")`
- Lazy registration de customer Asaas: `ensure_customer()` na primeira cobrança → `Customer.asaas_customer_id`
- `validate_and_clean_cpf_cnpj()` em `payments/service.py` — valida dígitos verificadores antes do Asaas
- **Dívida**: `create_subaccount()` sem `birthDate` — bloqueia produção Asaas com CPF

### PagSeguro (novo provider)
- `providers/pagseguro.py` — PagSeguroProvider(PaymentProvider) para terminais físicos
- OAuth2 client_credentials via `_authenticate()` — token descartado após uso
- `create_charge()`, `handle_webhook()`, `get_status()` implementados para terminal físico
- `refund()` — **STUB, endpoint `/charges/{id}/cancel` NÃO confirmado pela documentação PagBank (2026-06-03)**
- `list_terminals()` — **STUB, endpoint REST de listagem não encontrado na documentação pública**
- Decisão arquitetural: PagSeguro Point não tem REST API pública para push de cobranças
  → SmartPOS/PlugPag usam SDK Android; TEF usa middleware de parceiros — sem REST direto
- Migration `psg1a2b3c4d5`: `credentialprovider` enum recebeu valor 'PAGSEGURO'
- Factory em `provider_factory.py`: PAGSEGURO credential → PagSeguroProvider; fallback → AsaasProvider

### Pagamento manual / MAQUININHA
- `POST /payments/{id}/confirm-manual` — OWNER/ADMIN; CASH e provider=manual
- `confirm_manual()` retorna `tuple[Payment, Optional[dict]]` — segundo elemento é `fee_warning`
- `_calc_manual_fee()` consulta `TenantFeeRoutingPolicy` pelo `fee_source` do payment_method
- `fee_percentage=NULL` → fee=0 + `fee_warning` no response (taxa não configurada)
- `fee_percentage=0` → fee=0 sem warning (zero configurado explicitamente)
- `event_id` sintético determinístico: `f"manual-{payment.payment_id}"` — garante idempotência
- `MAQUININHA` (genérico) fallback para fee_source `MAQUININHA_CREDIT` — TODO para submethod

### Taxa MDR — fee-policies
- `GET  /financial/fee-policies` — OWNER/ADMIN; lista 8 políticas por tenant
- `PATCH /financial/fee-policies/{fee_source}` — OWNER/ADMIN; atualiza fee_percentage / fee_flat
- `fee_source` válidos agora incluem: `MAQUININHA_PIX` (adicionado neste sprint)
- Novos tenants: MAQUININHA_PIX criado com fee_percentage=NULL; demais com fee_percentage=0
- Migration `f2g3h4i5j6k7`: ADD COLUMN fee_percentage (nullable), fee_flat, is_active
- Migration `g3h4i5j6k7l8`: DROP NOT NULL fee_percentage + seed MAQUININHA_PIX para tenants existentes

### Evolution API — hardening
- Webhook `POST /whatsapp/webhook` valida `EVOLUTION_WEBHOOK_SECRET` se configurado
- Header validado: `x-evolution-global-apikey`; sem segredo configurado → sem validação
- `EVOLUTION_WEBHOOK_SECRET: str = ""` em config.py (default = sem validação)
```

### 3. Atualizar "O que NÃO fazer"

```diff
+- Não chamar `provider.refund()` para PagSeguro em produção — endpoint não confirmado (stub retorna 500)
+- Não usar revision ID `e1f2g3h4i5j6` para Sprint 11 — já em uso por add_asaas_customer_id
```

### 4. Atualizar "Dívidas de integração"

```diff
 ## Dívidas de integração
 - Asaas create_subaccount: campo birthDate obrigatório para CPF; onboarding atual
   não coleta o campo; novos tenants ficam sem external_account_id até ser corrigido
+- Asaas refund: payment_service.refund() não chama provider.refund() — estorno apenas
+  contábil local; gateway externo não processa o estorno automaticamente
+- PagSeguro Point: REST API para push de cobranças não documentada publicamente;
+  create_charge() e list_terminals() são stubs aguardando confirmação do time comercial PagBank
+- payment_submethod: MAQUININHA (genérico) usa MAQUININHA_CREDIT como fallback de fee_source;
+  campo payment_submethod ausente de PaymentCreate e do modelo Payment
+- asyncio.create_task: ainda ativo no lifespan; remover após 24h Celery sem erros
 - Email em produção: Railway bloqueia SMTP (portas 25/465/587/2525);
   implementação atual usa Mailtrap HTTP API (sandbox only);
   substituir por SendGrid/Mailgun/Mailtrap Email API antes de ir a produção
```

### 5. Atualizar "Decisões registradas"

```diff
+- PagSeguro Point: documentação pública não expõe REST API para push de cobranças a terminais físicos.
+  Soluções físicas (SmartPOS, PlugPag, TEF, Tap On) usam SDK Android, Bluetooth ou Intent local.
+  PagSeguroProvider.create_charge() usa endpoint /orders como proxy — não confirmado para Point.
+  Decisão: não ativar PagSeguro Point em produção até confirmar endpoint com time comercial PagBank.
+
+- fee_percentage NULL vs. zero: NULL = "não configurado" → dispara fee_warning em confirm_manual.
+  Zero = "0% configurado" → sem aviso, sem taxa. Semântica intencional para MAQUININHA_PIX.
+  Tenants pré-sprint têm MAQUININHA_CREDIT/DEBIT com fee_percentage=0 (DEFAULT da migration) — sem warning.
```

---

## Entrada para SPRINT-LOG.md

Texto pronto para copiar no novo arquivo `agendamento_engine/SPRINT-LOG.md`:

```markdown
# SPRINT-LOG — agendamento_engine

## Sprint de Integrações (APIs externas) — 2026-06-02 a 2026-06-04

**HEAD antes do sprint:** `d1e2f3g4h5i6` (align_orm_schema_gaps)
**HEAD após sprint (quando commitado):** `g3h4i5j6k7l8` (add_maquininha_pix_fee_source)
**Total de testes:** 338/338 (conforme commit 457d807)
**Commits do sprint:**

```
457d807  feat: taxa automatica de maquininha em confirm-manual (338/338)
a45fb65  feat: Bloco 1 — fluxo de convite de usuario validado
4a7d9e4  fix(auth): forgot_password para PLATFORM_OWNER (company_id=None)
10d1baa  fix(communication): header correto para Mailtrap producao vs sandbox
797fc99  fix(users): invitation_id ja e UUID no Postgres, nao requer conversao
f973a78  debug(users): logar excecao no envio de email de convite
6831021  fix(users): convite sempre usa audience=CLIENT no dispatch de email
48d8e91  docs: CLAUDE.md — dívida email produção (Railway bloqueia SMTP)
46a4f34  feat(users): envio de email de convite via CommunicationService
dac8341  feat: Bloco 1 — email recuperacao de senha via Mailtrap HTTP API
475e6a5  feat(communication): suporte a Mailtrap HTTP API como fallback ao SMTP bloqueado
5692541  feat: Bloco 1 — canal EMAIL no CommunicationService
720626b  fix(payments): validar CPF e CNPJ antes de enviar ao Asaas
6cc2697  fix(payments): mapear billingType interno para valores aceitos pelo Asaas
b581bad  fix(payments): adicionar dueDate e cpf_cnpj ao fluxo de cobranca Asaas
a9aef05  fix(payments): savepoint em _resolve_api_key para evitar InFailedSqlTransaction
4d1af3a  fix(payments): resolver Asaas customer ID antes de criar cobranca
ce69ab2  fix: Bloco 2 — Asaas bugs criticos de webhook e charge
3c21bd4  docs: CLAUDE.md — gap birthDate Asaas create_subaccount
31892ba  fix: Bloco 2 — Asaas bugs criticos (external_charge_id + value/fee parsing)
2063e58  feat: Bloco 4 — confirmação síncrona de pagamento CASH/manual
c2d5546  feat: Bloco 5 — Evolution API validação e hardening
```

**Pendências em aberto ao término do sprint:** ver `docs/pendencias-pos-sprint-integracoes.md`

### O que foi implementado

**Bloco 1 — Email (CommunicationService)**
- Canal EMAIL em `dispatch()` com suporte a Mailtrap HTTP API e smtplib
- `forgot_password()` e `send_invite()` corrigidos para passar `recipient_email`
- Templates EMAIL criados: `auth.password_reset_requested` e `user.invitation_sent`
- Variáveis: MAILTRAP_API_TOKEN, MAILTRAP_SANDBOX_INBOX_ID, SMTP_*

**Bloco 2 — Asaas (correções críticas)**
- `create_payment()` agora chama `provider.create_charge()` → `external_charge_id` preenchido
- `confirm()` extrai value/fee do payload Asaas aninhado (`payment.value` e `payment.fee`)
- Lazy registration: `ensure_customer()` cria customer Asaas na primeira cobrança
- Validação de CPF/CNPJ: `validate_and_clean_cpf_cnpj()` antes de enviar ao Asaas

**Bloco 3 — PagSeguro (novo provider)**
- `PagSeguroProvider` implementado para terminais físicos (Point/SmartPOS)
- OAuth2 client_credentials para autenticação
- `create_charge()`, `handle_webhook()`, `get_status()` implementados (stubs documentados)
- Migration `psg1a2b3c4d5`: enum PAGSEGURO adicionado
- Factory atualizado: PAGSEGURO credential → PagSeguroProvider

**Bloco 4 — CASH / Pagamento Manual**
- `POST /payments/{id}/confirm-manual` implementado (OWNER/ADMIN)
- `confirm_manual()` retorna `tuple[Payment, Optional[fee_warning]]`
- `_calc_manual_fee()` calcula MDR via TenantFeeRoutingPolicy
- Idempotência via `event_id = f"manual-{payment.payment_id}"`

**Bloco 5 — Evolution API (hardening)**
- Validação de `EVOLUTION_WEBHOOK_SECRET` no webhook
- Log de diagnóstico adicionado (a remover após confirmação em produção)

**Taxes MDR (adicionado no sprint)**
- `GET /financial/fee-policies` e `PATCH /financial/fee-policies/{fee_source}`
- Migration `f2g3h4i5j6k7`: colunas fee_percentage, fee_flat, is_active
- Migration `g3h4i5j6k7l8`: fee_percentage nullable + seed MAQUININHA_PIX (**pendente de commit**)

### Decisões arquiteturais

- PagSeguro Point não tem REST API pública; stubs documentados até confirmação do time PagBank
- `fee_percentage=NULL` = não configurado; `fee_percentage=0` = zero configurado sem aviso
- Mailtrap HTTP API como substituto SMTP para Railway (SMTP bloqueado)
- `asyncio.create_task` ainda no lifespan — flip para Celery pending 24h sem erros

---

## Sprint 10 — Operations FSM + Agenda granular — [registrar retroativamente]

HEAD: `d1e2f3g4h5i6` (align_orm_schema_gaps)
Total testes: 142/142
[detalhes conforme CLAUDE.md seção "Operations FSM + Agenda granular"]
```

---

## Checklist de ações imediatas (Stage 0 gate)

Antes de qualquer deploy para produção do Sprint de Integrações:

- [ ] **P1** — Commitar `g3h4i5j6k7l8`, ORM model e todos os arquivos ` M`
- [ ] **P4** — Verificar `EVOLUTION_WEBHOOK_SECRET` no Railway; configurar se ausente
- [ ] **P1** — Aplicar `alembic upgrade head` em produção após commit
- [ ] **P13** — Confirmar `ASAAS_API_URL` no Railway (não deve ser sandbox em produção)
- [ ] **P13** — Confirmar `ASAAS_WEBHOOK_TOKEN` no Railway
- [ ] **P2** — Atualizar `brief-fase3-backend-only.md`: Sprint 11 usar `e2f3g4h5i6j7` em vez de `e1f2g3h4i5j6`
- [ ] **P8** — Atualizar HEAD migration no CLAUDE.md
- [ ] **P9** — Criar SPRINT-LOG.md com a entrada acima
- [ ] **P5** — Verificar logs de produção; se Celery estável há >24h, remover `asyncio.create_task` do lifespan

Antes do Stage 0 go-live (pré-requisitos de negócio):
- [ ] **P6** — Coletar `birthDate` e CPF/CNPJ no onboarding de novo tenant (Asaas produção exige)
- [ ] **P3** — Implementar chamada `provider.refund()` em `payment_service.refund()` (para Asaas)
- [ ] **P12** — Remover blocos de LOG DE DIAGNÓSTICO do webhook WhatsApp
- [ ] **P14** — Ativar `use_communication_service=True` por tenant via SQL após validação

---

*Auditoria gerada em 2026-06-04.
Sessão exclusiva de análise — nenhum arquivo de código foi criado ou modificado.*
*Próxima ação recomendada: executar o checklist de ações imediatas antes do next deploy.*
