# Plano de Sprint — Integrações: 5 Blocos com APIs Externas
**Gerado em:** 2026-06-02 · **Encoding:** UTF-8
**Sessão:** Análise e planejamento exclusivo — nenhum arquivo de código foi criado ou modificado.

> **Escopo deste sprint:** Fazer cada bloco de integração funcionar de ponta a ponta
> em ambiente sandbox antes de ir para produção. Não são funcionalidades novas —
> é validação e correção do que já existe ou implementação do que está completamente ausente.

---

## Achados da leitura prévia obrigatória

| Documento lido | Relevância para este sprint |
|---|---|
| `CLAUDE.md` | Feature flag `use_communication_service=False` por default; convenções de credenciais (Fernet); EVOLUTION_API_URL e EVOLUTION_API_KEY confirmados como campos de settings |
| `brief-fase3-backend-only.md` | Fase 3 usa Asaas para cobrança de assinaturas (Sprint 15) e pacotes (Sprint 14) — integração Asaas CRÍTICA para a Fase 3 funcionar |
| `plano-execucao-fase3.md` | Sprint 15 adiciona `subscription_id` em `payments`; Sprint 14 usa `payment.confirmed` para ativar pacotes — ambos dependem do webhook Asaas funcionando corretamente |

**Impacto direto:** Se o webhook Asaas (Bloco 2) não funcionar, os Sprints 14 e 15 da Fase 3
não são executáveis em produção. O email (Bloco 1) é pré-requisito para `forgot_password`
e convites de usuário chegarem ao destinatário.

---

## Bloco 1 — SMTP / Email

### Estado atual (o que existe)

- `CommunicationService.dispatch()` existe em `modules/communication/service.py`
- O método roteia por canal — mas o canal está **hardcoded como "WHATSAPP"** (linha 99 do arquivo):
  `channel = "WHATSAPP"` sem nenhum ramo de decisão para EMAIL
- `_send_whatsapp()` é o único transport implementado; abre conexão via `evolution_client.send_text()`
- `forgot_password()` em `auth/service.py` chama `communication_service.dispatch()` com:
  `event_type="auth.password_reset_requested"`, `recipient_phone=None`
  → Cai em `_send_whatsapp()` → `phone = context.get("recipient_phone")` → `None` → `ValueError`
  → Capturado por `except Exception: pass` → silencioso. Token gravado, email nunca enviado.
- `IntegrationCredential.provider` tem `"SMTP"` no enum `credentialprovider` ✅
- Campos de configuração SMTP esperados: armazenados em `config` (JSONB), sem schema fixo;
  `secret_encrypted` para a senha; não há campos dedicados nem validação de formato
- `handlers.py` registra apenas `payment.confirmed → handle_payment_confirmed_notification`
  (envia WhatsApp); nenhum handler de email existe
- Feature flag `use_communication_service` em `TenantConfig.permission_overrides`:
  default `False` — mas a flag não é verificada dentro de `dispatch()` em si; é responsabilidade
  do caller não chamar dispatch quando a flag está off. `forgot_password()` chama dispatch
  diretamente sem verificar a flag.

### Respostas diretas às perguntas

**a) Emails chegam ao destinatário real?**
Não. O fluxo de `forgot_password` grava o token no banco e chama `dispatch()`, que
hardcodeia o canal como WHATSAPP, busca uma conexão WhatsApp ativa, e falha silenciosamente
quando `recipient_phone=None`. O token existe no banco, mas o código não chega ao usuário
por nenhum canal.

**b) O que está faltando?**
1. Canal `EMAIL` em `dispatch()` — ramo `if channel == "EMAIL": self._send_email(...)`
2. Transport `_send_email()` com biblioteca SMTP
3. Templates com `channel="EMAIL"` no banco (hoje todos são `channel="WHATSAPP"`)
4. Variáveis de ambiente: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
   `SMTP_FROM_EMAIL`, `SMTP_USE_TLS`
5. Campos `SMTP_*` em `app/core/config.py`
6. `CommunicationSetting` com campo `email_enabled` (já existe no modelo — `email_enabled=False` default)
   e campos de configuração SMTP (hoje não há campos smtp_* no modelo)

**c) Biblioteca de email no requirements.txt?**
`smtplib` (nativa do Python, sem instalação). Recomendação: `aiosmtplib>=2.0.2` para
operação assíncrona compatível com FastAPI. Não está no requirements.txt.

**d) Feature flag `use_communication_service` ativa ou off?**
`False` por default. `forgot_password()` chama dispatch diretamente sem verificar a flag.

### Gaps identificados

- `dispatch()` não tem ramo EMAIL — channel hardcoded "WHATSAPP"
- `_send_email()` não existe — transport ausente
- Variáveis `SMTP_*` ausentes em `config.py` e em `.env.example`
- Templates `channel="EMAIL"` não são semeados em `create_company()` — apenas WHATSAPP
- `CommunicationSetting` não tem campos `smtp_host`, `smtp_port`, `smtp_user`, etc.
  (opção A: ler do IntegrationCredential com provider=SMTP; opção B: campos diretos no modelo)
- `forgot_password()` passa `recipient_phone=None` e o email do usuário está disponível
  mas não é passado no contexto como `recipient_email`

### Sandbox / ambiente de teste

**Serviço recomendado:** Mailtrap (https://mailtrap.io) — SMTP sandbox gratuito,
captura emails sem entregar ao destinatário real. Alternativa: Gmail com App Password.

**Variáveis de ambiente necessárias (novas):**
```
SMTP_HOST=sandbox.smtp.mailtrap.io
SMTP_PORT=587
SMTP_USER=<mailtrap_user>
SMTP_PASSWORD=<mailtrap_password>
SMTP_FROM_EMAIL=noreply@paladino.app
SMTP_USE_TLS=true
```

**Como verificar funcionamento:**
1. `POST /auth/forgot-password` com email de usuário ativo
2. Acessar inbox Mailtrap → email com código de 6 dígitos deve aparecer
3. Token de 6 dígitos visível no corpo do email
4. `POST /auth/reset-password` com o token recebido → HTTP 200

### Ordem de implementação

1. Adicionar campos `SMTP_*` em `app/core/config.py`
2. Adicionar campo `smtp_host` / ler config SMTP do IntegrationCredential provider=SMTP
   (recomendado: IntegrationCredential — consistente com o padrão de credenciais já implementado;
   `config` JSONB armazena `host`, `port`, `from_email`, `use_tls`; `secret_encrypted` para senha)
3. Adicionar library `aiosmtplib==2.0.2` ao `requirements.txt`
4. Implementar `_send_email()` em `communication/service.py`
5. Adicionar ramo `EMAIL` em `dispatch()` com seleção de canal baseada no template/configuração
6. Criar templates email em `_DEFAULT_TEMPLATES` de `companies/service.py`
   (event_type=`auth.password_reset_requested`, channel=`EMAIL`)
7. Corrigir `forgot_password()`: passar `recipient_email` no context
8. Corrigir `forgot_password()`: verificar `email_enabled` na CommunicationSetting antes de dispatch
9. Testes unitários com mock do SMTP transport

### Testes obrigatórios

**Rodam sempre (mock SMTP):**
- `dispatch()` com channel implícito EMAIL → chama `_send_email()` (mock)
- `dispatch()` sem template EMAIL → status `SKIPPED_NO_TEMPLATE`
- `forgot_password()` → token gravado no banco independente de falha de email
- `forgot_password()` com email inexistente → silencioso (não revela existência)
- `_send_email()` com falha SMTP → log `FAILED`, não propaga exceção

**Requerem sandbox real (skip sem credenciais):**
```python
@pytest.mark.skipif(not os.getenv("SMTP_HOST"), reason="SMTP sandbox não configurado")
def test_real_email_delivery(): ...
```

### Prompt de execução — Bloco 1

```
Implementar o canal EMAIL no CommunicationService do projeto agendamento_engine.

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md (feature flag, Fernet encryption)
  2. agendamento_engine/app/modules/communication/service.py (fluxo atual)
  3. agendamento_engine/app/modules/auth/service.py (forgot_password e send_invite)
  4. agendamento_engine/app/core/config.py (adicionar campos SMTP_*)
  5. agendamento_engine/app/infrastructure/db/models/integration_credential.py
     (padrão de armazenamento de credencial com secret_encrypted + config JSONB)
  6. agendamento_engine/app/modules/companies/service.py (_DEFAULT_TEMPLATES)

Escopo:
  DO:
    - Adicionar SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL,
      SMTP_USE_TLS em app/core/config.py
    - Adicionar aiosmtplib==2.0.2 em requirements.txt
    - Implementar _send_email() em communication/service.py usando IntegrationCredential
      provider=SMTP (decrypt_secret para senha; config JSONB para host/port/from_email/use_tls)
    - Adicionar ramo EMAIL em dispatch(): quando template.channel == "EMAIL", chamar _send_email()
    - Corrigir forgot_password(): passar recipient_email no context, verificar email_enabled
    - Adicionar template auth.password_reset_requested channel=EMAIL em _DEFAULT_TEMPLATES
    - Testes em tests/test_smtp_email.py

  NÃO FAZER:
    - Não remover o canal WHATSAPP existente
    - Não modificar _send_whatsapp() nem evolution_client.py
    - Não criar migrations (SMTP já está no enum credentialprovider)
    - Não modificar nenhum arquivo em painel/

Notas técnicas críticas:
  - aiosmtplib é assíncrono. Como dispatch() é síncrono (usa Session), usar
    asyncio.get_event_loop().run_until_complete() ou trocar para smtplib nativo.
    Recomendado: smtplib nativo (stdlib) para manter dispatch() síncrono e evitar
    conflito com o event loop do FastAPI. Usar starttls() quando SMTP_USE_TLS=true.
  - A seleção de canal (EMAIL vs WHATSAPP) em dispatch() deve ser determinada pelo
    template disponível e pela configuração de canal habilitado no CommunicationSetting.
    Lógica sugerida: tentar EMAIL se email_enabled=True E existe template EMAIL;
    fallback para WHATSAPP se whatsapp_enabled=True.
  - forgot_password() deve continuar funcionando mesmo sem template EMAIL cadastrado
    (token gravado, envio falha graciosamente).
  - Credencial SMTP: buscar IntegrationCredential com provider="SMTP" e status="ACTIVE"
    do tenant. Se ausente, usar SMTP_* de settings (fallback global).
  - secret_encrypted → decrypt_secret() → senha SMTP em plaintext (nunca logar).
  - config JSONB esperado: {"host": "smtp.example.com", "port": 587,
    "from_email": "noreply@x.com", "use_tls": true}

Casos de teste obrigatórios:
  - dispatch() EMAIL com template válido → _send_email() chamado (mock)
  - dispatch() sem template EMAIL → SKIPPED_NO_TEMPLATE
  - _send_email() com SMTP mock → log SENT gravado
  - _send_email() com falha → log FAILED, sem propagação
  - forgot_password() → token no banco mesmo com SMTP indisponível
  - forgot_password() com email desconhecido → silencioso

Sinal de conclusão:
  - pytest tests/test_smtp_email.py -v → todos passando
  - Email de reset chega ao Mailtrap sandbox com token correto
```

---

## Bloco 2 — Asaas (validação de implementação existente)

### Estado atual (o que existe)

**AsaasProvider** em `modules/payments/providers/asaas.py`:
- Usa `httpx` com `timeout=15` ✅
- Tratamento de erros: `HTTPStatusError → AsaasError`; `RequestError → AsaasError` ✅
- `create_subaccount(name, cpf_cnpj, email)` → `POST /accounts` → retorna `accountId` e `status` ✅
- `create_charge(amount, customer, payment_method, **kwargs)` → `POST /payments` ✅
- `handle_webhook(payload)` → normaliza payload, retorna `{event, external_id, status, raw}` ✅
- `refund(external_charge_id, reason)` → `POST /payments/{id}/refund` ✅
- `get_status(external_charge_id)` → `GET /payments/{id}` ✅

**Webhooks:**
- `POST /payments/webhook/asaas/transaction` → existe, processa ✅
- `POST /payments/webhook/asaas/account_status` → existe, valida `asaas-access-token` header ✅

**create_company → create_subaccount:**
- Chamado em `companies/service.py` após commit da company ✅
- Resultado salvo em `company.external_account_id` ✅
- **Problema:** `cpf_cnpj=""` passado (Asaas sandbox pode rejeitar sem CPF/CNPJ válido)

### Respostas diretas às perguntas

**a) AsaasProvider faz chamadas HTTP reais ou é stub/mock?**
Chamadas HTTP reais via `httpx`. Não é stub. Em produção, aponta para
`ASAAS_API_URL=https://sandbox.asaas.com/api/v3` (sandbox) ou `https://api.asaas.com/v3` (produção).

**b) Há tratamento de erros HTTP?**
Sim: `resp.raise_for_status()` convertido para `AsaasError` em ambos os métodos
`_post()` e `_get()`. Timeout de 15 segundos. Sem retry automático — falha propaga imediatamente.

**c) Webhook de transaction processa payload real do Asaas?**
**PARCIAL — BUG CRÍTICO.**

O webhook Asaas real para `PAYMENT_RECEIVED` tem estrutura:
```json
{
  "event": "PAYMENT_RECEIVED",
  "payment": {
    "id": "pay_abc123",
    "status": "RECEIVED",
    "value": 100.00,
    "netValue": 97.00,
    "fee": 3.00
  }
}
```

O código em `confirm()` extrai `value` e `fee` assim:
```python
amount = Decimal(str(webhook_data.get("value", str(payment.net_charged_amount))))
provider_fee = Decimal(str(webhook_data.get("fee", str(payment.provider_fee))))
```

`webhook_data` é o payload bruto. `payload.get("value")` → `None` (o campo está em `payload.payment.value`).
Resultado: `amount` cai no fallback `payment.net_charged_amount` e `provider_fee` não é extraído.
O pagamento é confirmado com o valor incorreto — não o valor real pago no Asaas.

**d) O que está faltando ou provavelmente diverge do sandbox Asaas real?**

1. **BUG CRÍTICO — `external_charge_id` nunca populado:** `create_payment()` cria o Payment
   mas NÃO chama `create_charge()` no provider. O campo `Payment.external_charge_id` fica `None`.
   O webhook busca por `external_charge_id` — nunca encontra o payment → sempre retorna
   `{"ok": True, "skipped": "payment_not_found"}`. O webhook está completamente quebrado para
   pagamentos digitais (PIX, BOLETO, CARD).

2. **BUG CRÍTICO — extração de `value`/`fee` do payload Asaas:** conforme descrito acima.

3. **provider_factory hardcoded:** `get_payment_provider()` sempre retorna `AsaasProvider`.
   Não suporta múltiplos providers por tenant.

4. **CASH sem `create_charge()`:** Para CASH, não chamar `create_charge()` é correto —
   mas o webhook nunca chegará. Falta fluxo de confirmação síncrona.

5. **`cpf_cnpj=""` em `create_subaccount()`:** Asaas sandbox pode aceitar string vazia
   para MEI, mas a API de produção requer CPF/CNPJ válido. Precisa ser testado.

**e) Split de comissão (walletId)?**
Não implementado. `create_charge()` não passa `walletId` nem `split`. O Asaas suporta
split direto no payload de `/payments`, mas o provider não implementa.

### Gaps identificados

1. `create_payment()` não chama `create_charge()` → `external_charge_id` nunca preenchido
2. Extração de `value` e `fee` do payload Asaas incorreta (aninhado sob `payment.*`)
3. Fluxo completo PIX/BOLETO não testado end-to-end em sandbox
4. `cpf_cnpj=""` em create_subaccount não testado em sandbox real
5. Sem suporte a `walletId` para split de comissão

### Sandbox / ambiente de teste

**Criar conta sandbox Asaas:** https://sandbox.asaas.com (cadastro gratuito)

**Variáveis de ambiente necessárias:**
```
ASAAS_API_KEY=$aact_sandbox_xxxx     # token da conta sandbox
ASAAS_API_URL=https://sandbox.asaas.com/api/v3
ASAAS_WEBHOOK_TOKEN=webhook-secret-local
```

**Expor webhook local:** usar ngrok ou similar para receber webhook do Asaas sandbox:
```
ngrok http 8000
# URL gerada: https://abc.ngrok.io
# Configurar webhook no painel Asaas: https://abc.ngrok.io/payments/webhook/asaas/transaction
```

**Como verificar:**
1. `POST /companies` → company criada → `external_account_id` preenchido no banco
2. Criar Payment PIX → `external_charge_id` deve aparecer no response
3. Simular pagamento no painel Asaas sandbox → webhook chega → Payment muda para CONFIRMED
4. `GET /payments/{id}` → `status="CONFIRMED"`, `paid_at` preenchido

### Ordem de implementação

1. **Fix extração payload:** em `confirm()`, alterar para ler `webhook_data.get("payment", {}).get("value")` com fallback para top-level `webhook_data.get("value")`
2. **Implementar `create_charge()` no fluxo:** em `create_payment()` de `payments/service.py`,
   quando `provider == "asaas"` (e `payment_method` for PIX/BOLETO/CARD), chamar
   `provider.create_charge()` e salvar resultado em `payment.external_charge_id`
3. **Testar `create_subaccount()` em sandbox** com CPF/CNPJ real (ou dummy válido)
4. **Teste end-to-end do webhook:** criar charge → simular pagamento no Asaas → webhook → CONFIRMED
5. **Opcional (Fase 3, Sprint 15):** adicionar `walletId` no `create_charge()` para split

### Testes obrigatórios

**Rodam sempre (NullProvider):**
- `create_payment(provider="asaas")` → `create_charge()` chamado → `external_charge_id` preenchido
- `confirm()` com payload `{"payment": {"value": 100.0, "fee": 3.0}}` → amount=100, fee=3
- `confirm()` com payload antigo (top-level `value`) → fallback funciona
- Webhook `skipped: payment_not_found` quando `external_charge_id` não existe

**Requerem sandbox Asaas real (skip sem `ASAAS_API_KEY`):**
```python
@pytest.mark.skipif(not os.getenv("ASAAS_API_KEY"), reason="Asaas sandbox não configurado")
def test_real_asaas_charge(): ...
```

### Prompt de execução — Bloco 2

```
Validar e corrigir a integração Asaas no projeto agendamento_engine.

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md
  2. agendamento_engine/app/modules/payments/providers/asaas.py
  3. agendamento_engine/app/modules/payments/service.py (create_payment + confirm)
  4. agendamento_engine/app/modules/payments/router.py (webhooks)
  5. agendamento_engine/app/modules/companies/service.py (create_company)
  6. agendamento_engine/app/modules/payments/providers/null_provider.py
     (padrão para testes)

Escopo:
  DO:
    - Corrigir extração de value/fee em confirm(): ler de webhook_data.get("payment", {})
      com fallback para top-level
    - Implementar chamada a create_charge() em create_payment() quando provider="asaas"
      e payment_method não for CASH; salvar retorno em payment.external_charge_id
    - Atualizar NullProvider.create_charge() para retornar external_charge_id compatível
    - Adicionar testes sandbox-skipáveis para fluxo completo
    - Testar create_subaccount() em sandbox com CPF/CNPJ dummy válido

  NÃO FAZER:
    - Não implementar walletId/split (Fase 3, Sprint 15 pode fazer isso)
    - Não modificar provider_factory (mantém AsaasProvider para todos por ora)
    - Não modificar migrations existentes
    - Não alterar comportamento do CASH (não deve chamar create_charge)

Notas técnicas críticas:
  - create_payment() deve chamar create_charge() ANTES de db.commit() mas só se
    provider != "manual"/"cash". Se create_charge() falhar, payment não é salvo
    (transação inteira é revertida). Essa decisão é intencional: não criar payment
    no banco sem referência no provider.
  - Payload real Asaas PAYMENT_RECEIVED:
    {"event": "PAYMENT_RECEIVED", "payment": {"id": "pay_xxx", "value": 100.0,
     "netValue": 97.0, "fee": 3.0, "status": "RECEIVED", "paymentDate": "2026-06-02"}}
  - external_charge_id é o campo "id" do response de create_charge() no Asaas
    (ex: "pay_abc123"). Salvar em payment.external_charge_id.
  - O webhook busca por: db.query(Payment).filter(Payment.external_charge_id == external_charge_id)
    Isso só funciona se external_charge_id estiver preenchido.
  - ASAAS_API_URL default já está em settings.py como sandbox.asaas.com — correto.

Casos de teste obrigatórios:
  - create_payment(provider="asaas", method="PIX") → external_charge_id preenchido
  - create_payment(provider="manual", method="CASH") → external_charge_id None
  - confirm() com payload {"payment": {"value": 100, "fee": 3}} → amount=100, fee=3
  - confirm() com payload {"value": 100, "fee": 3} (legado/fallback) → amount=100, fee=3
  - Webhook transaction com external_charge_id inexistente → skipped: payment_not_found
  - [sandbox] create_subaccount() → accountId preenchido, sem HTTP error

Sinal de conclusão:
  - pytest tests/test_asaas_integration.py -v → todos passando
  - [sandbox] Fluxo completo: POST /companies → external_account_id ✅;
    POST /payments PIX → external_charge_id ✅;
    Webhook simulado → Payment CONFIRMED ✅
```

---

## Bloco 3 — PagSeguro (novo provider)

### Estado atual (o que existe)

**ABC PaymentProvider** em `modules/payments/providers/base.py`:
```python
create_subaccount(name, cpf_cnpj, email) -> dict  # accountId, status
create_charge(amount, customer, payment_method, **kwargs) -> dict
handle_webhook(payload) -> dict
refund(external_charge_id, reason) -> dict
get_status(external_charge_id) -> str
```

**`credentialprovider` enum** (`integration_credential.py`):
`WHATSAPP_EVOLUTION | WHATSAPP_META | SMTP | ASAAS`
→ **PAGSEGURO ausente** → migration necessária.

**`provider_factory.py`:** Hardcoded para `AsaasProvider`. Sem suporte a múltiplos providers.
Um único método: `get_payment_provider(company_id, db) -> PaymentProvider`

### Respostas diretas às perguntas

**a) Enum precisa de migration para PAGSEGURO?**
Sim. `ALTER TYPE credentialprovider ADD VALUE 'PAGSEGURO'` — migration nova necessária.
Como o enum é `create_type=False`, apenas o `ALTER TYPE` no banco é necessário;
o modelo ORM aceita a string dinamicamente após a migration ser aplicada.

**b) Factory suporta múltiplos providers por tenant?**
Não. Hardcoded `return AsaasProvider(...)`. Para suportar PagSeguro, o factory precisa
verificar a `Company.payment_provider` ou uma `IntegrationCredential` com provider=PAGSEGURO.

**c) PagSeguro tem dois produtos relevantes:**
- **PagSeguro Checkout/API:** cobranças online (PIX, cartão, boleto) via REST
  URL base sandbox: `https://sandbox.api.pagseguro.com`
  Autenticação: `Authorization: Bearer {TOKEN}`
- **PagSeguro Point (maquininha física):** terminal físico com SDK proprietário;
  pagamento inicia no terminal, resultado chega via webhook com `event_type=CHARGE_PAID`
  A API REST é diferente da API de Checkout

O ABC atual (`create_charge`, `handle_webhook`, `refund`, `get_status`) cobre a API online.
Para maquininha física:
- `create_charge()` não faz sentido — a cobrança é iniciada no terminal, não pela API
- O fluxo é: o operador digita valor no terminal → webhook chega quando pago
- O ABC precisaria de um método adicional: `notify_terminal(terminal_id, amount)` ou
  simplesmente suportar o webhook sem criar a charge previamente

**d) O que PagSeguroProvider precisará além do ABC base?**
Para a maquininha (PagSeguro Point):
- `list_terminals(company_id)` — listar terminais vinculados à conta
- `notify_terminal(terminal_id, amount)` — iniciar cobrança no terminal (opcional,
  depende do modelo de operação: pode ser o operador que inicia no terminal fisicamente)
- `handle_webhook()` com formato distinto do PagSeguro online

Para PagSeguro online:
- `create_customer()` — PagSeguro exige cadastro prévio do cliente antes de criar charge

### Gaps identificados

1. **PAGSEGURO ausente do enum** — migration necessária
2. **Nenhuma implementação** `PagSeguroProvider` — arquivo não existe
3. **Factory não suporta seleção por tenant** — hardcoded para Asaas
4. **ABC sem método para maquininha** (notify_terminal)
5. **Sem credencial PagSeguro** no banco — IntegrationCredential com provider=PAGSEGURO
   não pode ser criada enquanto enum não existir

### Sandbox / ambiente de teste

**Criar conta sandbox PagSeguro:** https://sandbox.pagseguro.uol.com.br

**Variáveis de ambiente necessárias:**
```
PAGSEGURO_TOKEN=<sandbox_token>
PAGSEGURO_API_URL=https://sandbox.api.pagseguro.com
PAGSEGURO_CLIENT_ID=<client_id>    # para OAuth2 (API v4)
PAGSEGURO_CLIENT_SECRET=<secret>   # para OAuth2 (API v4)
```

**Aviso:** A API PagSeguro v4 usa OAuth2 com client_credentials. O token expira em ~3600s.
O provider precisará implementar refresh de token (ou re-autenticar a cada chamada).

**Como verificar:**
1. `POST /integrations/credentials` com provider=PAGSEGURO → credencial salva
2. `POST /payments` com provider="pagseguro", method="PIX" → charge criada
3. Simular pagamento no sandbox → webhook chega → Payment CONFIRMED

### Ordem de implementação

1. **Migration** — `ALTER TYPE credentialprovider ADD VALUE 'PAGSEGURO'`
   (revision ID novo, após sprint atual; down_revision = HEAD atual `d1e2f3g4h5i6`)
2. **`app/modules/payments/providers/pagseguro.py`** — implementar `PagSeguroProvider`
   baseado no ABC. Usar `httpx` (já disponível). Cobrir: PIX, cartão, boleto online.
3. **Estender factory** — `get_payment_provider()` verificar `company.payment_provider`
   ou `IntegrationCredential` com provider=PAGSEGURO ativo para selecionar o provider correto
4. **Testes com mock** para o PagSeguroProvider
5. **Maquininha (segunda iteração):** definir interface e implementar apenas após
   validação do fluxo online

### Testes obrigatórios

**Rodam sempre (mock HTTP):**
- `PagSeguroProvider.create_charge()` → HTTP mock → retorna `external_charge_id`
- `PagSeguroProvider.handle_webhook()` → payload PagSeguro → dict normalizado
- Factory com `company.payment_provider="pagseguro"` → retorna `PagSeguroProvider`
- Factory com `company.payment_provider="asaas"` → retorna `AsaasProvider` (regressão)

**Requerem sandbox PagSeguro:**
```python
@pytest.mark.skipif(not os.getenv("PAGSEGURO_TOKEN"), reason="PagSeguro sandbox não configurado")
def test_real_pagseguro_charge(): ...
```

### Prompt de execução — Bloco 3

```
Implementar o PagSeguroProvider como novo provider de pagamento no projeto agendamento_engine.

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md
  2. agendamento_engine/app/modules/payments/providers/base.py (ABC PaymentProvider)
  3. agendamento_engine/app/modules/payments/providers/asaas.py (referência de implementação)
  4. agendamento_engine/app/modules/payments/provider_factory.py
  5. agendamento_engine/app/infrastructure/db/models/integration_credential.py
  6. agendamento_engine/app/infrastructure/db/models/company.py
     (campo payment_provider para seleção no factory)

Escopo:
  DO:
    - Migration: ALTER TYPE credentialprovider ADD VALUE 'PAGSEGURO' (nova migration)
    - app/modules/payments/providers/pagseguro.py: PagSeguroProvider(PaymentProvider)
      Métodos: create_subaccount, create_charge (PIX/cartão/boleto online),
               handle_webhook, refund, get_status
    - Estender provider_factory.get_payment_provider(): verificar IntegrationCredential
      com provider=PAGSEGURO ativo antes de retornar AsaasProvider como fallback
    - Testes em tests/test_pagseguro_integration.py

  NÃO FAZER:
    - Não implementar maquininha PagSeguro Point neste bloco (prioridade menor)
    - Não alterar AsaasProvider nem NullProvider
    - Não criar endpoints novos (os existentes /payments já funcionarão com o factory atualizado)
    - Não modificar nenhum arquivo em painel/

Notas técnicas críticas:
  - PagSeguro API v4 usa OAuth2 client_credentials. Token retornado tem expires_in=3600.
    Implementação simples: re-autenticar a cada instância do provider (sem cache).
    Token endpoint: POST https://sandbox.api.pagseguro.com/oauth2/token
    Body (form): grant_type=client_credentials&client_id=X&client_secret=Y
  - Credencial PagSeguro no IntegrationCredential:
    provider=PAGSEGURO, secret_encrypted=(client_secret Fernet), 
    config={"client_id": "...", "api_url": "https://sandbox.api.pagseguro.com"}
  - create_charge() PIX no PagSeguro:
    POST /orders com body contendo charges[].payment_method.type="PIX"
    Response tem charges[0].id como external_charge_id
  - handle_webhook() PagSeguro: event_type pode ser "CHARGE_PAID", "CHARGE_CANCELED"
    O campo de referência é charges[0].id para lookup do Payment
  - Webhook de maquininha tem formato diferente — NOT implementar neste bloco
  - Factory: order de resolução sugerida:
    1. IntegrationCredential com provider=PAGSEGURO e status=ACTIVE → PagSeguroProvider
    2. IntegrationCredential com provider=ASAAS e status=ACTIVE → AsaasProvider
    3. settings.ASAAS_API_KEY → AsaasProvider (fallback global)
    4. AsaasError: nenhum provider disponível

Casos de teste obrigatórios:
  - Factory: company sem credential → fallback AsaasProvider
  - Factory: company com PAGSEGURO credential → PagSeguroProvider
  - Factory: company com ASAAS credential → AsaasProvider (regressão)
  - PagSeguroProvider.create_charge() mock PIX → external_charge_id retornado
  - PagSeguroProvider.handle_webhook() CHARGE_PAID → status CONFIRMED normalizado
  - Migration: credentialprovider aceita 'PAGSEGURO' sem erro

Sinal de conclusão:
  - pytest tests/test_pagseguro_integration.py -v → todos passando
  - Suite completa sem regressões (especialmente test_payments_*)
  - [sandbox] POST /payments com provider="pagseguro" → charge criada no PagSeguro sandbox
```

---

## Bloco 4 — Pagamento manual (CASH)

### Estado atual (o que existe)

**`PaymentsEngine.create_payment()`:** Existe ✅. Cria Payment com qualquer `payment_method`
incluindo CASH. `_PAYMENT_METHOD_TO_FEE_SOURCE["CASH"] = None` ✅ — sem taxa de provider.

**`confirm()`:** Requer `event_id` (de webhook externo) e `webhook_data`. Não há fluxo
síncrono de confirmação. Para CASH, não existe webhook — o `confirm()` só é chamado pelo
endpoint `POST /payments/webhook/asaas/transaction`, que busca por `external_charge_id`
(nulo para CASH) → sempre retorna `skipped: payment_not_found`.

**`PaymentCreate` schema:** `payment_method` é `str` livre — aceita "CASH" sem validação.
`provider` é `str` livre — sem enum.

**Movimento INFLOW:** Quando `confirm()` for chamado para CASH, `fee_source = None`,
`target_account_id` é o da Account passada pelo caller (CAIXA da empresa).
`FinancialCoreEngine.handle_payment_confirmed()` com `fee_source=None` — funciona
(sem routing de taxa).

### Respostas diretas às perguntas

**a) É possível criar e confirmar um Payment imediatamente sem webhook?**
Não através da API HTTP atual. `confirm()` existe na camada de serviço e pode ser chamado
com dados sintéticos, mas não há endpoint HTTP para isso. O único endpoint que chama
`confirm()` é o webhook Asaas, que filtra por `external_charge_id`.

**b) O que precisa ser adicionado para provider="manual" com confirmação síncrona?**
1. Endpoint `POST /payments/{id}/confirm-manual` (OWNER/ADMIN) para CASH/manual
2. Chamada direta a `payment_service.confirm()` com `event_id=f"manual-{uuid4()}"` e
   `webhook_data={"value": str(payment.net_charged_amount), "fee": "0"}`
3. Validação: só funciona para `payment.provider in ("manual", "MANUAL")` ou
   `payment.payment_method == "CASH"`

**c) Movement INFLOW para CASH → qual Account?**
A Account é definida pelo `target_account_id` passado em `create_payment()`. Para CASH,
o caller deve passar o ID da Account CAIXA da empresa (criada por default em `create_company()`).
O `FinancialCoreEngine` não tem opinião sobre qual Account usar — recebe o `target_account_id`
diretamente. A semântica de "CAIXA" é do caller.

### Gaps identificados

1. Sem endpoint HTTP para confirmação manual síncrona de CASH
2. `provider` em `PaymentCreate` aceita qualquer string — sem enum/validação
3. Sem validação que impede chamar `create_charge()` para CASH (após fix do Bloco 2)
4. Sem teste end-to-end do fluxo CASH completo

### Sandbox / ambiente de teste

**Não requer serviço externo.** CASH é 100% local.

**Variáveis de ambiente necessárias:** nenhuma nova.

**Como verificar:**
1. `POST /payments` com `payment_method="CASH"`, `provider="manual"`, `target_account_id=<caixa_id>`
   → Payment PENDING criado, `external_charge_id=null`
2. `POST /payments/{id}/confirm-manual` → Payment CONFIRMED, Movement INFLOW criado
3. `GET /financial/accounts/{id}/movements` → Movement INFLOW visível

### Ordem de implementação

1. Adicionar endpoint `POST /payments/{id}/confirm-manual` em `payments/router.py`
   (OWNER/ADMIN; valida que `payment.payment_method == "CASH"` ou `provider == "manual"`)
2. Chamar `payment_service.confirm()` com `event_id=f"manual-{uuid4()}"` e
   `webhook_data={"value": str(payment.net_charged_amount), "fee": "0"}`
3. Garantir que `create_payment()` (após fix Bloco 2) NÃO chame `create_charge()` para CASH
4. Testes do fluxo completo

### Testes obrigatórios

**Rodam sempre:**
- `create_payment(method="CASH")` → `external_charge_id=None`, `provider_fee=0`
- `POST /payments/{id}/confirm-manual` (CASH) → 200, Payment CONFIRMED
- `POST /payments/{id}/confirm-manual` em Payment não-CASH → 422
- `POST /payments/{id}/confirm-manual` em Payment já CONFIRMED → idempotente (via `is_processed`)
- Movement INFLOW criado na Account CAIXA após confirmação
- Webhook Asaas com CASH payment → `skipped: payment_not_found` (não deve processar)

### Prompt de execução — Bloco 4

```
Implementar confirmação manual síncrona de pagamentos CASH no projeto agendamento_engine.

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md
  2. agendamento_engine/app/modules/payments/service.py (create_payment + confirm)
  3. agendamento_engine/app/modules/payments/router.py (padrão de endpoints existentes)
  4. agendamento_engine/app/modules/payments/schemas.py
  5. agendamento_engine/app/modules/financial_core/service.py (handle_payment_confirmed)

Escopo:
  DO:
    - Adicionar endpoint POST /payments/{id}/confirm-manual em payments/router.py
      Autenticação: OWNER/ADMIN
      Validação: payment.payment_method == "CASH" OU payment.provider == "manual"
                 payment.status == "PENDING" (422 se não for PENDING)
      Implementação: chamar payment_service.confirm() com event_id sintético e webhook_data
    - Adicionar função confirm_manual() em payments/service.py (wrapper de confirm())
    - Garantir que create_payment() com method="CASH" não chama create_charge()
      (validação de que external_charge_id fica None)
    - Testes em tests/test_cash_payment.py

  NÃO FAZER:
    - Não criar novo FSM — reutilizar confirm() existente com dados sintéticos
    - Não modificar o webhook Asaas
    - Não criar migrations
    - Não modificar painel/

Notas técnicas críticas:
  - event_id sintético para idempotência: f"manual-{payment.payment_id}"
    (determinístico — re-submit do confirm-manual é idempotente via is_processed)
  - webhook_data para confirm(): {"value": str(payment.net_charged_amount), "fee": "0"}
    Isso garante que amount=net_charged_amount e provider_fee=0.
  - fee_source=None para CASH — FinancialCoreEngine.handle_payment_confirmed com fee_source=None
    funciona corretamente (sem routing de taxa, sem Movement de taxa).
  - O endpoint confirm-manual deve ser RESTRITO a CASH/manual para evitar bypass
    do processo de confirmação por webhook em pagamentos digitais.
  - target_account_id em create_payment() é obrigatório — o caller especifica a Account.
    Para CASH na operação do dia-a-dia, seria a Account CAIXA da empresa.

Casos de teste obrigatórios:
  - create_payment(method="CASH") → external_charge_id=None, status=PENDING
  - POST /payments/{id}/confirm-manual → Payment CONFIRMED, paid_at preenchido
  - Movement INFLOW criado em target_account após confirmação (via list_movements)
  - confirm-manual em Payment PIX → 422 (método não-manual bloqueado)
  - confirm-manual em Payment já CONFIRMED → idempotente (via is_processed → return payment)
  - EventBus payment.confirmed emitido após confirm-manual (best-effort)

Sinal de conclusão:
  - pytest tests/test_cash_payment.py -v → todos passando
  - Fluxo manual: POST /payments CASH → POST /payments/{id}/confirm-manual
    → Payment CONFIRMED → Movement INFLOW → Entry RECEITA ✅
```

---

## Bloco 5 — Evolution API (WhatsApp)

### Estado atual (o que existe)

**`evolution_client.py`:** Implementação completa ✅
- `create_instance()`, `get_qr()`, `get_connection_state()`, `logout_instance()`,
  `delete_instance()`, `set_webhook()` — gerenciamento de instâncias
- `send_text()`, `send_buttons()`, `send_poll()`, `send_list()` — envio de mensagens
- Usa `httpx` com `timeout=15` ✅; normaliza números para JID `@s.whatsapp.net`

**Webhook** `POST /whatsapp/webhook`:
- Existe ✅; processa `connection.update`, `qrcode.updated`, `messages.upsert`, `messages.update`
- `messages.upsert` → `bot_service.handle_inbound_message(db, instance_name, data)` ✅
- `messages.update` (votos de enquete) → cria mensagem sintética e roteia como texto ✅
- Sempre retorna 200 (não quebra o webhook mesmo com erro interno) ✅

**QR Code** `GET /whatsapp/qr`:
- Chama `connection_service.refresh_qr()` → `evolution_client.get_qr(instance_name)`
- Retorna QR real da Evolution API ✅ (não apenas redireciona)

**BotSession FSM** em `bot_service.py`:
- Estados implementados: INICIO, AGUARDANDO_NOME, CONFIRMAR_NOME, OFERTA_RECORRENTE,
  MENU_PRINCIPAL, ESCOLHENDO_SERVICO, ESCOLHENDO_PROFISSIONAL, ESCOLHENDO_DATA,
  ESCOLHENDO_TURNO, ESCOLHENDO_HORARIO, CONFIRMANDO, VER_AGENDAMENTOS,
  GERENCIANDO_AGENDAMENTO, CANCELANDO, REAGENDANDO (15 estados)
- Todos os handlers importados e roteados ✅
- FSM completo — não é schema vazio

**`CommunicationService._send_whatsapp()`:** Envia via `evolution_client.send_text()` ✅

**Config:**
- `EVOLUTION_API_URL: str = "http://localhost:8080"` ✅
- `EVOLUTION_API_KEY: str = "evolution-api-key"` ✅

### Respostas diretas às perguntas

**a) Webhook alimenta BotSession FSM?**
Sim. `messages.upsert` → `handle_inbound_message()` → busca/cria BotSession →
`get_session_locked()` (SELECT FOR UPDATE NOWAIT) → roteia para handler do estado atual
→ atualiza estado e `expires_at` → salva com `save_session()`.
É o FSM completo, não apenas log.

**b) Existe código que chama Evolution API REST para enviar mensagem?**
Sim: `evolution_client.send_text(instance_name, phone, text)` →
`POST /message/sendText/{instance_name}` ✅
Também: `send_poll()` para enquetes e `send_list()` para listas de opções.

**c) QR Code é gerado pelo backend ou redireciona?**
Gerado pelo backend: `GET /whatsapp/qr` → `evolution_client.get_qr()` →
`GET /instance/connect/{instance_name}` na Evolution API → retorna base64 do QR.
Backend não redireciona — retorna o QR no response JSON.

**d) BotSession FSM tem transições implementadas?**
Sim, implementação completa. 15 estados com handlers dedicados.
SELECT FOR UPDATE NOWAIT previne race condition de mensagens simultâneas.
`last_message_id` para idempotência de re-entregas do webhook.

**e) CommunicationService tem despacho via WhatsApp?**
Sim: `dispatch()` chama `_send_whatsapp()` que usa `evolution_client.send_text()`.
O canal está hardcoded como WHATSAPP. A CommunicationService já opera exclusivamente
via WhatsApp — o suporte a EMAIL é o gap (Bloco 1).

### Gaps identificados

1. **Feature flag `use_communication_service=False`:** Notificações pós-appointment
   (reminders, confirmações) usam o caminho antigo `evolution_client.send_text()` direto.
   O novo caminho via CommunicationService está implementado mas não ativo por default.
   Flip exige validação em staging por 24h (conforme CLAUDE.md).

2. **`send_list()` tem debug log em nível ERROR:** Linha no código:
   `logger.error("sendList PAYLOAD: %s", ...)` — claramente debug temporário.
   Polui logs de produção com nível ERROR para operação normal.

3. **`send_buttons()` não funciona no Baileys** (WhatsApp Web): comentário no código
   documenta isso. `BOT_USE_BUTTONS=False` por default — correto. Mas se ativado
   acidentalmente, silencia silenciosamente no cliente.

4. **Webhook sem validação de assinatura:** O endpoint `POST /whatsapp/webhook` não valida
   nenhum segredo/assinatura da Evolution API. Qualquer request chega e é processado.
   Risco de spam/injeção de mensagens sintéticas.

5. **`ASAAS_WEBHOOK_TOKEN` validado; webhook Evolution não validado:** Inconsistência.

### Sandbox / ambiente de teste

**Opção A — Docker local:**
```bash
docker run --rm -p 8080:8080 \
  -e AUTHENTICATION_API_KEY=minha-chave \
  atendai/evolution-api:latest
```

**Opção B — Instância cloud** (recomendado para testar webhook):
Serviço Railway/Render com Evolution API + ngrok para expor o webhook local.

**Variáveis de ambiente necessárias:**
```
EVOLUTION_API_URL=http://localhost:8080   # ou URL da instância cloud
EVOLUTION_API_KEY=minha-chave-aqui
WEBHOOK_BASE_URL=https://abc.ngrok.io    # URL pública para o backend
```

**Como verificar:**
1. `POST /whatsapp/connection` → QR code retornado em JSON
2. Escanear QR com celular de teste → status muda para CONNECTED
3. Enviar mensagem WhatsApp para o número → webhook recebe → bot responde
4. Seguir o fluxo completo de agendamento via WhatsApp

### Ordem de implementação

Este bloco tem o menor gap — é primariamente validação.

1. **Remover debug `logger.error` de `send_list()`** → trocar para `logger.debug`
2. **Flip da feature flag `use_communication_service`** para True em staging → monitorar 24h
3. **Adicionar validação de webhook** se Evolution API suportar HMAC/segredo
   (verificar versão da Evolution API em uso)
4. **Teste end-to-end completo** do fluxo de booking via WhatsApp em sandbox

### Testes obrigatórios

**Rodam sempre (mock evolution_client):**
- `CommunicationService.dispatch()` com WhatsApp connection → `send_text()` chamado
- `dispatch()` sem WhatsApp connection → RuntimeError capturado → log FAILED
- `dispatch()` com quiet_hours ativo em evento automático → status SCHEDULED
- `dispatch()` com evento transacional em quiet_hours → bypass → SENT

**Requerem Evolution API real:**
```python
@pytest.mark.skipif(not os.getenv("EVOLUTION_API_URL") or "localhost" in os.getenv("EVOLUTION_API_URL", ""),
                    reason="Evolution API sandbox não configurado")
def test_real_evolution_send_text(): ...
```

### Prompt de execução — Bloco 5

```
Validar e ajustar a integração Evolution API (WhatsApp) no projeto agendamento_engine.

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md (feature flag use_communication_service, Estágio 0)
  2. agendamento_engine/app/modules/whatsapp/evolution_client.py
  3. agendamento_engine/app/modules/whatsapp/router.py (webhook)
  4. agendamento_engine/app/modules/communication/service.py
  5. agendamento_engine/app/modules/whatsapp/bot_service.py
  6. agendamento_engine/app/core/config.py (EVOLUTION_API_URL, EVOLUTION_API_KEY)

Escopo:
  DO:
    - Corrigir send_list(): trocar logger.error de debug para logger.debug
    - Adicionar validação de segredo no webhook /whatsapp/webhook (header X-Evolution-Hmac
      ou similar, conforme versão da Evolution API em uso). Se Evolution API não suportar
      HMAC, adicionar IP allowlist ou token simples via settings.EVOLUTION_WEBHOOK_SECRET
    - Testar em sandbox real: fluxo completo de conexão + booking via WhatsApp
    - Adicionar settings.EVOLUTION_WEBHOOK_SECRET: str = "" em config.py
    - Testes em tests/test_whatsapp_integration.py

  NÃO FAZER:
    - Não fazer flip da feature flag (exige 24h de monitoramento em staging — fora do escopo de código)
    - Não modificar o FSM do bot (está correto)
    - Não alterar evolution_client.py além do log nível
    - Não criar endpoints novos além da validação de webhook
    - Não modificar painel/

Notas técnicas críticas:
  - O webhook DEVE retornar 200 mesmo com erro (Evolution API desabilita instância em 5xx).
    A validação de segredo deve retornar 200 com {"status": "rejected"} em vez de 401/403
    OU retornar 401 aceitando a consequência de que a Evolution API pode desabilitar o webhook.
    DECISÃO: retornar 401 — é mais seguro contra injeção. Configurar Evolution API para
    ignorar erros HTTP e não desabilitar (verificar configuração IGNORE_WEBHOOK_ERRORS).
  - EVOLUTION_WEBHOOK_SECRET: string comparada com header "x-evolution-global-apikey"
    (cabeçalho que a Evolution API envia em algumas versões). Se string vazia → sem validação.
  - send_list() tem logger.error em uso normal — trocar para logger.debug imediatamente.
    Isso reduz ruído nos logs de produção.
  - Para o flip da feature flag: NÃO fazer via código. O OWNER da empresa ativa via
    TenantConfig.permission_overrides["use_communication_service"] = True no banco/admin.
    Documentar o procedimento, não automatizar.

Casos de teste obrigatórios:
  - dispatch() → send_text() chamado com phone e rendered_body corretos
  - dispatch() → WhatsApp DISCONNECTED → RuntimeError → log FAILED (sem propagação)
  - Webhook /whatsapp/webhook sem segredo configurado → aceita qualquer request (compatibilidade)
  - Webhook com EVOLUTION_WEBHOOK_SECRET configurado + header correto → 200
  - Webhook com EVOLUTION_WEBHOOK_SECRET configurado + header errado → 401
  - send_list() não gera log em nível ERROR
  - [sandbox] Fluxo completo: POST /whatsapp/connection → QR → CONNECTED → bot responde

Sinal de conclusão:
  - pytest tests/test_whatsapp_integration.py -v → todos passando
  - [sandbox] Mensagem de agendamento completa via WhatsApp funciona end-to-end
  - Logs de produção sem logger.error espúrios de send_list
```

---

## Passo 3 — Dependências e ordem de execução

**a) Qual bloco tem mais código já existente (menor esforço)?**
**Bloco 5 — Evolution API.** Tudo está implementado: cliente HTTP, FSM completo,
webhook handler, CommunicationService wrap. É primariamente validação + pequenas correções.

**b) Qual bloco é completamente ausente (maior esforço)?**
**Bloco 3 — PagSeguro.** Zero código de provider, zero no enum, factory não suporta.
Implementação do zero.

**c) Existem dependências entre blocos?**

```
Bloco 4 (CASH) ──────────────────────────────────────────► Independente
Bloco 2 (Asaas) ──────────────────────────────────────────► Independente
Bloco 5 (Evolution) ──────────────────────────────────────► Independente
Bloco 1 (SMTP) ───────────────────────────────────────────► Independente (técnico)
                                                              Mas: auth flows dependem
                                                              de email para UX completo
Bloco 3 (PagSeguro) ─────── depende de ──► Bloco 2 (factory pattern deve existir)
```

**Observação:** Bloco 3 não tem dependência técnica rígida do Bloco 2, mas é
muito mais simples implementar o factory de forma limpa após ter feito o
refactor do factory no Bloco 2 (seleção de provider por tenant).

**d) Email (Bloco 1) é pré-requisito para outros blocos?**
**Tecnicamente: não.** Os outros blocos de pagamento não usam email.
**Funcionalmente para testes: sim parcialmente.** `forgot_password` é usado
em testes de integração E2E para recuperar acesso. Sem email funcionando,
os testes de integração precisam de acesso direto ao banco para recuperar o token.
**Recomendação:** implementar Bloco 1 antes de iniciar testes E2E intensivos.

---

## Passo 4 — Verificação de bibliotecas e dependências

### Presentes no requirements.txt

| Biblioteca | Versão | Uso |
|---|---|---|
| `httpx` | 0.27.2 | HTTP client — Asaas, PagSeguro, Evolution API ✅ |
| `requests` | 2.33.1 | HTTP síncrono — não usado nos novos blocos |
| `cryptography` | 46.0.7 | Fernet para credenciais ✅ |
| `sqlalchemy` | 2.0.36 | ORM ✅ |
| `celery[redis]` | 5.4.0 | Workers ✅ |

### Ausentes — necessárias para os blocos

| Biblioteca | Versão recomendada | Bloco | Motivo |
|---|---|---|---|
| `aiosmtplib` | 2.0.2 | Bloco 1 | SMTP assíncrono para FastAPI |

**Alternativa ao aiosmtplib:** `smtplib` (stdlib Python) + `ssl` — síncrona mas sem
instalação adicional. Adequada se `dispatch()` permanecer síncrono.
Recomendação: usar `smtplib` nativo para evitar dependência extra e manter
`dispatch()` síncrono (compatível com o SessionLocal síncrono da camada de dados).

### Ausentes — opcionais mas recomendadas

| Biblioteca | Versão recomendada | Bloco | Motivo |
|---|---|---|---|
| `pagseguro` / `pagbank-python` | N/A | Bloco 3 | **Não existe SDK oficial Python** — implementar REST manual com httpx |

---

## Sumário Executivo

### Tabela de ordem de execução com estimativa de esforço

| Ordem | Bloco | Nome | Esforço | Dependências | Status atual |
|---|---|---|---|---|---|
| 1 | 5 | Evolution API (WhatsApp) | **Baixo** (~4h) | Nenhuma | COMPLETO — validação |
| 2 | 4 | CASH / Pagamento manual | **Baixo** (~4h) | Nenhuma | PARCIAL — endpoint faltando |
| 3 | 2 | Asaas (validação) | **Médio** (~8h) | Nenhuma | PARCIAL — bugs críticos |
| 4 | 1 | SMTP / Email | **Médio** (~8h) | Nenhuma técnica | CRÍTICO — ausente |
| 5 | 3 | PagSeguro (novo) | **Alto** (~16h) | Factory (Bloco 2) | CRÍTICO — ausente |

**Total estimado:** ~40h de implementação + ~8h de validação em sandbox = ~48h.

### Variáveis de ambiente novas necessárias

| Variável | Bloco | Obrigatória em produção? |
|---|---|---|
| `SMTP_HOST` | 1 | Sim (se email habilitado) |
| `SMTP_PORT` | 1 | Sim |
| `SMTP_USER` | 1 | Sim |
| `SMTP_PASSWORD` | 1 | Sim (via vault) |
| `SMTP_FROM_EMAIL` | 1 | Sim |
| `SMTP_USE_TLS` | 1 | Sim (`true`) |
| `ASAAS_WEBHOOK_TOKEN` | 2 | Sim — já existe em settings, setar valor real |
| `PAGSEGURO_CLIENT_ID` | 3 | Sim |
| `PAGSEGURO_CLIENT_SECRET` | 3 | Sim (via vault) |
| `PAGSEGURO_API_URL` | 3 | Sim |
| `EVOLUTION_WEBHOOK_SECRET` | 5 | Recomendado — hoje sem validação |

### Bibliotecas a adicionar ao requirements.txt

| Biblioteca | Versão | Bloco |
|---|---|---|
| Nenhuma se usar `smtplib` nativo | — | 1 |
| `aiosmtplib==2.0.2` | — | 1 (se preferir assíncrono) |

**PagSeguro:** sem SDK Python oficial — usar `httpx` já presente.

### Migrations necessárias

| Migration | Tipo | Bloco | Descrição |
|---|---|---|---|
| `ALTER TYPE credentialprovider ADD VALUE 'PAGSEGURO'` | DDL | 3 | Adicionar enum value |

Nenhuma outra migration necessária para os outros blocos. O modelo de dados atual
suporta os blocos 1, 2, 4 e 5 sem alterações de schema.

### Riscos identificados

| Risco | Bloco | Severidade | Mitigação |
|---|---|---|---|
| **Asaas rejeitando `cpf_cnpj=""`** em create_subaccount na produção | 2 | Alta | Testar em sandbox; verificar se produção Asaas aceita sem CPF |
| **Webhook Asaas sem ngrok** em desenvolvimento local — não chega ao backend | 2 | Média | Usar ngrok ou endpoint de simulação no painel Asaas |
| **PagSeguro OAuth2 token expira** em ~3600s — sem refresh implementado | 3 | Média | Re-autenticar a cada instância do provider (aceitável para o volume inicial) |
| **Evolution API ToS** — uso de Baileys (WhatsApp Web reverse engineering) — uso comercial em área cinza | 5 | Alta | Meta tem tolerado no Brasil para PMEs; usar Evolution API apenas (sem cliente WhatsApp direto) |
| **Webhook Evolution sem autenticação** — injeção de mensagens sintéticas | 5 | Média | Implementar `EVOLUTION_WEBHOOK_SECRET` como parte deste sprint |
| **Feature flag `use_communication_service=False`** — notificações ainda via caminho antigo | 5 | Baixa | Flip manual por tenant após 24h de validação em staging |
| **SMTP em produção sem TLS** — credenciais em trânsito | 1 | Alta | Nunca ativar `SMTP_USE_TLS=false` em produção; validar no startup |
| **PagSeguro Point vs PagSeguro Checkout** — APIs completamente diferentes | 3 | Média | Implementar apenas Checkout neste sprint; Point é iteração separada |

### Como validar cada bloco em sandbox antes de ir para produção

**Bloco 1 — SMTP/Email:**
```
1. Configurar Mailtrap com SMTP_* vars
2. POST /auth/forgot-password com email válido
3. Verificar inbox Mailtrap: email recebido com token 6 dígitos
4. POST /auth/reset-password com token → 200
5. Verificar que token inválido → 400
```

**Bloco 2 — Asaas:**
```
1. Configurar conta sandbox Asaas + ngrok
2. POST /companies → external_account_id no response
3. POST /payments (PIX) → external_charge_id no response
4. Simular pagamento no painel Asaas sandbox
5. Verificar webhook chegou: logs mostram event_id
6. GET /payments/{id} → status=CONFIRMED, paid_at preenchido
7. GET /financial/accounts/{id}/movements → INFLOW visível
```

**Bloco 3 — PagSeguro:**
```
1. Configurar conta sandbox PagSeguro + credencial no banco
2. POST /integrations/credentials (provider=PAGSEGURO)
3. POST /payments (PIX, provider="pagseguro") → external_charge_id
4. Simular pagamento no sandbox PagSeguro
5. Verificar webhook + Payment CONFIRMED
```

**Bloco 4 — CASH:**
```
1. POST /payments (CASH, provider="manual", target_account_id=<caixa>)
2. Verificar: external_charge_id=null, status=PENDING
3. POST /payments/{id}/confirm-manual
4. Verificar: status=CONFIRMED, paid_at preenchido
5. GET /financial/accounts/{id}/movements → INFLOW na conta CAIXA
```

**Bloco 5 — Evolution API:**
```
1. Docker local da Evolution API OU instância cloud
2. POST /whatsapp/connection → QR Code no response
3. Escanear QR com celular de teste
4. GET /whatsapp/connection → status=CONNECTED
5. Enviar "Oi" via WhatsApp → bot responde (INICIO state)
6. Seguir fluxo completo até CONFIRMANDO
7. Verificar Appointment criado no banco
8. Verificar notificação WhatsApp enviada (appointment.confirmed)
```

---

## Classificação final por bloco

| Bloco | Nome | Classificação |
|---|---|---|
| **1** | SMTP / Email | 🔴 **CRÍTICO** — canal EMAIL ausente, `dispatch()` hardcoded WHATSAPP, nenhuma biblioteca SMTP |
| **2** | Asaas | 🟡 **PARCIAL** — provider faz HTTP real, mas `external_charge_id` nunca populado e extração de payload incorreta — webhook quebrado end-to-end |
| **3** | PagSeguro | 🔴 **CRÍTICO** — completamente ausente: sem provider, sem enum, sem factory support |
| **4** | CASH | 🟡 **PARCIAL** — `create_payment` suporta CASH mas não há endpoint de confirmação síncrona |
| **5** | Evolution API | 🟢 **COMPLETO** — cliente HTTP, bot FSM, webhook, CommunicationService wrap — validação e pequenas correções apenas |

---

*Plano gerado em 2026-06-02 por análise cruzada com o código real do repositório.*
*Nenhum arquivo de código foi criado ou modificado durante esta sessão.*
*Próxima ação: executar os blocos na ordem: 5 → 4 → 2 → 1 → 3.*
