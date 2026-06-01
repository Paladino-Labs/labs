# Payments — Domínio de Pagamentos

## Responsabilidade

O PaymentsEngine gerencia o ciclo de vida de cobranças ao cliente.
Integra com provedores externos (Asaas), processa webhooks de forma
idempotente e delega ao FinancialCoreEngine o registro econômico.

```
PaymentsEngine DEFINE
  Criação e ciclo de vida de Payments
  Integração com providers (Asaas, futuro: outros)
  Webhook idempotente
  Reembolso classificado
  DepositPolicy (sinal/depósito)
  PaymentSources (métodos salvos)

PaymentsEngine NÃO DEFINE
  Registro de Movements/Entries  → FinancialCoreEngine
  Notificações ao cliente        → CommunicationService (via EventBus)
  Reservas de agenda             → AgendaEngine
```

---

## FSM de Payments

```
PENDING → CONFIRMED (webhook ou confirmação manual)
PENDING → FAILED    (erro do provider)
PENDING → CANCELLED (cancelamento antes de processar)
CONFIRMED → REFUNDED (reembolso)
```

### Modelo: Payment

```
payment_id              UUID PK
company_id              UUID FK → companies [RLS]
customer_id             UUID nullable FK → customers
appointment_id          UUID nullable FK → appointments
currency                CHAR(3) DEFAULT 'BRL'

gross_catalog_amount    NUMERIC(15,2) NOT NULL   # preço cheio do catálogo
discount_amount         NUMERIC(15,2) DEFAULT 0  # descontos aplicados
net_charged_amount      NUMERIC(15,2) NOT NULL   # valor cobrado ao cliente
provider_fee            NUMERIC(15,2) DEFAULT 0  # taxa do provider

payment_method          VARCHAR NOT NULL
  -- CASH | PIX | BOLETO | CARD_CREDIT | CARD_DEBIT | MAQUININHA
payment_source_id       UUID nullable FK → payment_sources
  -- nulo para CASH/PIX/BOLETO; preenchido para cartão salvo

provider                VARCHAR NOT NULL   # ⚡ IMUTÁVEL após criação
target_account_id       UUID FK → accounts
external_charge_id      VARCHAR nullable   # ID da cobrança no provider

status                  VARCHAR DEFAULT 'PENDING'
manual_override_count   INTEGER DEFAULT 0

created_at              TIMESTAMPTZ DEFAULT now()
paid_at                 TIMESTAMPTZ nullable
refunded_at             TIMESTAMPTZ nullable
```

**⚡ Invariante:** `provider` é imutável após criação.
Trigger de banco rejeita UPDATE do campo `provider`.
`@validates("provider")` no ORM como segunda camada.

---

## PaymentTransaction

Registro de cada interação com o provider externo.

```
transaction_id          UUID PK
payment_id              UUID FK → payments
company_id              UUID FK → companies [RLS]
provider_transaction_id VARCHAR NOT NULL
amount                  NUMERIC(15,2) NOT NULL
status                  VARCHAR NOT NULL
raw_response            JSONB NOT NULL
created_at              TIMESTAMPTZ DEFAULT now()
UNIQUE(company_id, provider_transaction_id)
```

O `UNIQUE(company_id, provider_transaction_id)` é a segunda camada de
proteção contra duplicatas (além do ProcessedIdempotencyKey).

---

## confirm() — Atomicidade ⚡ (CRÍTICA)

```python
def confirm(payment_id, event_id, webhook_data, company_id, db):
    """
    TODOS OS 5 PASSOS NA MESMA TRANSAÇÃO DE BANCO.
    Se qualquer passo falhar, TODOS fazem rollback.
    """
    BEGIN TRANSACTION
      # 1. Verificar idempotência (saída antecipada se já processado)
      if is_processed(key=event_id, consumer="payment_confirmed"):
          return db.get(Payment, payment_id)

      # 2. Registrar interação com provider
      #    UNIQUE viola → já processado → rollback automático
      db.add(PaymentTransaction(
          provider_transaction_id=event_id,
          raw_response=webhook_data, ...
      ))
      db.flush()

      # 3. Atualizar status do Payment
      payment.status = 'CONFIRMED'
      payment.paid_at = datetime.now(UTC)
      db.flush()

      # 4. Registrar no Financial Core (Movements + Entries)
      financial_core_engine.handle_payment_confirmed(
          gross_amount=payment.net_charged_amount,
          provider_fee=payment.provider_fee,
          target_account_id=payment.target_account_id,
          fee_source=_fee_source_for(payment.payment_method),
          company_id=company_id, db=db
      )

      # 5. Marcar como processado
      mark_processed(key=event_id, consumer="payment_confirmed")
    COMMIT

    # FORA DA TRANSAÇÃO (após commit):
    event_bus.publish("payment.confirmed", payment_id=payment_id, ...)
    # → Handler separado: CommunicationService.send_transactional (best-effort)
```

**Por que ProcessedIdempotencyKey + UNIQUE juntos?**
- `ProcessedIdempotencyKey`: proteção primária, verifica antes de processar
- `UNIQUE(company_id, provider_transaction_id)`: proteção no banco,
  rejeita duplicata mesmo em condição de race (dois processos simultâneos)

---

## Webhook Idempotente

```
POST /payments/webhook/asaas/transaction   (público, sem auth)
```

```python
event_id = payload['id']   # ID único do evento Asaas

# Idempotência delegada para confirm()
# O webhook handler não verifica por conta própria
payment_service.confirm(
    payment_id=lookup_payment_by_external(payload),
    event_id=event_id,
    webhook_data=payload,
    company_id=company_id,
    db=db
)
```

**Comportamento:** múltiplas entregas do mesmo `event_id` resultam em
exatamente 1 PaymentTransaction e 1 par Movement+Entry.

---

## Reembolso

```
POST /payments/{id}/refund   (OWNER/ADMIN + reason obrigatório) 🔒
```

```python
class RefundReason(str, Enum):
    SERVICE_FAILURE     = "SERVICE_FAILURE"
    REGISTRATION_ERROR  = "REGISTRATION_ERROR"
    DEADLINE_POLICY     = "DEADLINE_POLICY"
    OTHER               = "OTHER"
```

**Fluxo:**
1. Verificar que `payment.status == 'CONFIRMED'`
2. Chamar `provider.refund(external_charge_id, reason)`
3. FinancialCoreEngine.handle_payment_refunded(
       payment_id, amount, account_id
   ) → Movement OUTFLOW + Entry ESTORNO (REEMBOLSO_CLIENTE)
4. `payment.status = 'REFUNDED'`, `payment.refunded_at = now()`
5. `record_sensitive_action(action="refund_payment", reason=reason)`
6. EventBus.publish("payment.refunded") após commit

---

## PaymentSource (Métodos Salvos)

Apenas métodos tokenizados (cartão com token do provider).
PIX, BOLETO, CASH não são PaymentSources — são registrados em
`payment.payment_method`.

```
source_id       UUID PK
company_id      UUID FK → companies [RLS]
customer_id     UUID FK → customers
type            VARCHAR NOT NULL    # CARD_CREDIT | CARD_DEBIT
provider        VARCHAR NOT NULL
external_token  TEXT NOT NULL       # token do provider
last4           VARCHAR(4) nullable
brand           VARCHAR nullable    # Visa, Master, etc.
is_active       BOOLEAN DEFAULT true
created_at      TIMESTAMPTZ DEFAULT now()
```

---

## DepositPolicy (Política de Sinal/Depósito)

```
policy_id                       UUID PK
company_id                      UUID FK → companies [RLS]
service_id                      UUID nullable FK → services
  -- NULL = política global do tenant
deposit_type                    VARCHAR    # FIXED_AMOUNT | PERCENTAGE
deposit_value                   NUMERIC(10,2)
refundable_until_hours_before   INTEGER DEFAULT 24
refund_on_tenant_fault          BOOLEAN DEFAULT true
retain_on_no_show               BOOLEAN DEFAULT true
commission_on_retained_deposit  BOOLEAN DEFAULT false
created_at                      TIMESTAMPTZ DEFAULT now()
updated_at                      TIMESTAMPTZ
```

**Lookup:** serviço específico tem prioridade sobre política global.
Se nem serviço nem global: sem exigência de depósito.

**Fluxo DEPOSIT (integração com Agenda — Sprint 10/11):**
1. Cliente inicia checkout → SOFT Reservation criada
2. DepositPolicy ativa → Payment criado com `net_charged_amount=deposit_value`
3. Cliente paga → Payment.status = CONFIRMED
4. `payment.confirmed` → SOFT → FIRME (promote_to_firme)
5. Entry RECEITA registrada como `SINAL_SERVICO`

---

## Providers (Adaptadores de Pagamento)

### Interface: PaymentProvider (ABC)
```python
class PaymentProvider(ABC):
    def create_subaccount(name, cpf_cnpj, email) → dict
    def create_charge(amount, customer, payment_method, **kwargs) → dict
    def handle_webhook(payload) → dict
    def refund(external_charge_id, reason) → dict
    def get_status(external_charge_id) → str
```

### AsaasProvider
- Usa `IntegrationCredential` (provider=ASAAS) do tenant via `decrypt_secret`
- Fallback para `settings.ASAAS_API_KEY` se tenant sem credential
- Descriptografa `cpf_cnpj_encrypted` internamente antes de enviar para a API
- Nunca retorna o valor descriptografado para fora do adaptador

### NullProvider (testes)
```python
class NullProvider(PaymentProvider):
    calls: list[dict]    # spy — registra todos os métodos chamados
    outcome: str         # "success" | "error"
```

### Seleção de Provider
`payments/provider_factory.py → get_payment_provider(company_id, db)`
- Busca `IntegrationCredential` ativo com provider=ASAAS para o tenant
- Se encontrado: `AsaasProvider(credential)`
- Se não encontrado: `AsaasProvider(api_key=settings.ASAAS_API_KEY)`
- Em testes: `NullProvider` injetado via dependency override

---

## Mapeamento payment_method → fee_source

```python
_PAYMENT_METHOD_TO_FEE_SOURCE: dict[str, Optional[str]] = {
    "PIX":          "ASAAS_PIX",
    "CARD_CREDIT":  "ASAAS_CARD",
    "CARD_DEBIT":   "ASAAS_CARD",
    "BOLETO":       "ASAAS_PIX",      # Asaas cobra como PIX
    "MAQUININHA":   "MAQUININHA_DEBIT",
    "CASH":         None,             # Sem taxa de provider para dinheiro
}
```

Se `fee_source=None` e `provider_fee=0`: sem Movement OUTFLOW nem Entry TAXA.

---

## Invariantes do Domínio de Payments

1. **`Payment.provider` é imutável.** Trigger de banco + @validates.
2. **`confirm()` é atômico.** 5 passos ou nenhum persiste.
3. **Idempotência dupla.** ProcessedIdempotencyKey + UNIQUE no banco.
4. **CommunicationService fora da transação.** Via EventBus após commit.
5. **Reembolso exige reason classificado.** HTTP 422 sem reason.
6. **Reembolso é auditado.** record_sensitive_action obrigatório.
7. **PaymentSource ≠ payment_method.** Sources são tokenizados; method é o meio.