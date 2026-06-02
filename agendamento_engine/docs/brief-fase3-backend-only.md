# Brief de execução — Fase 3: Catálogo Avançado + Comissões + Crédito
## BACKEND ONLY — Sprints 11–18 · ~16 semanas
**Gerado em:** 2026-06-01 · **Encoding:** UTF-8

> **Decisão de fase:** Esta fase implementa exclusivamente o backend.
> Nenhuma página, componente ou rota do `painel/` é criada ou alterada
> durante os Sprints 11–18. O brief de frontend será gerado separadamente
> após os 8 sprints de backend estarem completos, auditados e testados
> em produção. Prompts de executor que não sigam esta restrição devem
> ser rejeitados.

---

## Estado de entrada (pós-Fase 2 + correções)

```
Backend — agendamento_engine/
  HEAD migrations: d1e2f3g4h5i6 (align_orm_schema_gaps)
  53 migrations totais (33 Fase 1 + 19 Fase 2 + 1 alinhamento)

  Financial Core completo:
    Account, Movement (append-only), Entry (append-only),
    Transfer, ReconciliationRecord, MovementReconciliation, CashCount,
    TenantFeeRoutingPolicy (chave natural)

  Pagamentos completo:
    PaymentsEngine FSM, webhook idempotente, DepositPolicy,
    AsaasProvider + NullProvider, PaymentSource

  Agenda completo:
    Reservation SOFT/FIRME (EXCLUDE tstzrange status=ACTIVE),
    ScheduleException, DirectOccupancy, FSM Appointment

  Comunicação + Integração:
    CommunicationService, EventBus, Celery Beat

  Handlers registrados:
    payment.confirmed → CommunicationService (best-effort)
    agenda.soft_reservation.expired → SoftReservationHandler

  289 testes passando + 3 skips (trigger PostgreSQL)

  O que NÃO existe (canvas em branco para Fase 3):
    ServicePricingOverride, ServiceVariant
    CommissionPolicy, Commission, CommissionPayout
    CustomerCredit, CustomerCreditConsumption
    Package, PackagePurchase
    SubscriptionPlan, CustomerSubscription
    Promotion, Coupon, CouponRedemption
    StockMovement, Supplier, SupplierOrder
    Payable, PayableInstallment
    Expense, ExpenseRecurrence
```

---

## Princípios que guiam a Fase 3

**Comissão acompanha valor real, não liquidação.**
Comissão gerada pelo evento de valor (serviço prestado),
não pelo meio ou timing de pagamento.

**Dois trabalhos = duas comissões independentes.**
Vendedor de pacote/assinatura e prestador do serviço são
funções separadas com comissões independentes.

**CustomerCredit é cota de direito de uso, não saldo monetário.**
Não tem valor em reais — representa uma unidade de uso (ex: 1 corte).
Não pode ser sacado, transferido ou estornado como dinheiro.

**Custo vs Despesa (nunca misturar).**
Custo: ligado diretamente à produção (pomada, produto vendido).
Despesa: operacional sem vínculo com venda específica (aluguel, energia).
Comissão variável é gerada automaticamente — nunca lançar como Despesa
(geraria dupla contagem).

**API-first restrito.**
Endpoints devem estar completos, documentados e testados antes que
qualquer tela os consuma. Esta fase garante esse estado.

---

## Sprint 11 — Catálogo opt-ins

**Objetivo:** Flexibilizar o catálogo de serviços com preços por profissional,
variantes, tempos de preparo e horários estruturados.

**Critério de conclusão:**
- `GET /booking/{slug}/services?professional_id=X` retorna preço efetivo
  do override quando existe, com fallback correto para preço base
- `GET /booking/{slug}/profile` inclui `business_hours_structured` como
  lista estruturada `[{weekday, open, close}]`
- `GET /availability/slots` considera `preparation_minutes_before/after`
  no cálculo de disponibilidade
- DELETE em service → `appointment_services.service_id` vira NULL

### Migrations Sprint 11

**`e1f2g3h4i5j6_catalog_optins`**
```sql
-- 1. Tempos de preparo em services
ALTER TABLE services
  ADD COLUMN IF NOT EXISTS preparation_minutes_before INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS preparation_minutes_after  INTEGER NOT NULL DEFAULT 0;

-- 2. business_hours estruturado (sem remover o campo string livre existente)
ALTER TABLE company_profiles
  ADD COLUMN IF NOT EXISTS business_hours_structured JSONB;
-- Formato: [{weekday: 0-6, open: "09:00", close: "18:00"}]
-- 0=Segunda ... 6=Domingo

-- 3. Fix FK AppointmentService.service_id (desvio #11 do roadmap)
ALTER TABLE appointment_services
  DROP CONSTRAINT IF EXISTS appointment_services_service_id_fkey,
  ADD CONSTRAINT appointment_services_service_id_fkey
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE SET NULL;

-- 4. ServicePricingOverride
CREATE TABLE service_pricing_overrides (
  override_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id      UUID NOT NULL REFERENCES companies(id),
  professional_id UUID NOT NULL REFERENCES professionals(id),
  service_id      UUID NOT NULL REFERENCES services(id),
  price           NUMERIC(10,2) NOT NULL CHECK (price >= 0),
  duration_min    INTEGER nullable,  -- NULL = usa duração do serviço base
  is_active       BOOLEAN NOT NULL DEFAULT true,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ,
  UNIQUE(professional_id, service_id)
);
CREATE POLICY tenant_isolation ON service_pricing_overrides
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE service_pricing_overrides ENABLE ROW LEVEL SECURITY;

-- 5. ServiceVariant
CREATE TABLE service_variants (
  variant_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id      UUID NOT NULL REFERENCES companies(id),
  service_id      UUID NOT NULL REFERENCES services(id),
  name            VARCHAR NOT NULL,
  price           NUMERIC(10,2) NOT NULL CHECK (price >= 0),
  duration_min    INTEGER NOT NULL,
  is_active       BOOLEAN NOT NULL DEFAULT true,
  sort_order      INTEGER NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ
);
CREATE POLICY tenant_isolation ON service_variants
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE service_variants ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 11

**Modelos:** `ServicePricingOverride`, `ServiceVariant`
Adicionar `preparation_minutes_before`, `preparation_minutes_after` em `Service`.
Adicionar `business_hours_structured` em `CompanyProfile`.
Corrigir `AppointmentService.service_id` com `ondelete='SET NULL'`.

**`app/modules/services/service.py`** — resolver preço efetivo:
```python
def get_effective_price(
    service_id, professional_id, variant_id=None, company_id, db
) -> tuple[Decimal, int]:
    """
    Retorna (price, duration_min) com prioridade:
    1. ServiceVariant (se variant_id fornecido)
    2. ServicePricingOverride (se existe para professional_id + is_active)
    3. Service.price / Service.duration_min (fallback)
    """
```

**Integração com disponibilidade:**
`GET /availability/slots` e `GET /booking/{slug}/slots` devem usar
`preparation_minutes_before + duration_min + preparation_minutes_after`
como duração total do bloco ocupado no calendário.

**Integração com BookingFlow:**
`GET /booking/{slug}/services` com query param `professional_id` deve
retornar preço via `get_effective_price(service_id, professional_id)`.

**`company_profiles`:**
- `PATCH /companies/profile` aceita e salva `business_hours_structured`
- `GET /booking/{slug}/profile` retorna ambos os campos:
  `business_hours` (string legado) e `business_hours_structured` (JSONB)
- Validação de `business_hours_structured`: lista de objetos
  `{weekday: int(0-6), open: str("HH:MM"), close: str("HH:MM")}`
  HTTP 422 se formato inválido

**Endpoints Sprint 11:**
```
GET    /services/{id}/variants
POST   /services/{id}/variants                OWNER/ADMIN
PATCH  /services/{id}/variants/{variant_id}   OWNER/ADMIN
DELETE /services/{id}/variants/{variant_id}   OWNER/ADMIN

GET    /professionals/{id}/pricing-overrides
POST   /professionals/{id}/pricing-overrides         OWNER/ADMIN
PATCH  /professionals/{id}/pricing-overrides/{oid}   OWNER/ADMIN
DELETE /professionals/{id}/pricing-overrides/{oid}   OWNER/ADMIN
```

### Testes Sprint 11
- [ ] `get_effective_price`: variant > override > base (todos os 3 caminhos testados)
- [ ] `get_effective_price` sem override → retorna Service.price e duration_min
- [ ] Slot com `preparation_minutes_before=15` e `after=10`: bloco ocupa 15+30+10=55min
- [ ] `business_hours_structured` salvo e retornado corretamente no profile
- [ ] `GET /booking/{slug}/profile` retorna campo `business_hours_structured`
- [ ] `PATCH /companies/profile` com weekday inválido (7) → 422
- [ ] `GET /availability/slots` com professional em dia fora do `business_hours_structured` → lista vazia
- [ ] DELETE service → `appointment_services.service_id` = NULL (não CASCADE DELETE)
- [ ] Override `UNIQUE(professional_id, service_id)`: segundo POST → 409
- [ ] Cross-tenant: overrides e variantes isolados por company_id

---

## Sprint 12 — CommissionEngine

**Objetivo:** Calcular, registrar e pagar comissões de profissionais de forma
auditável, com dois eixos configuráveis.

**Critério de conclusão:** Operação COMPLETED com serviço de R$100 e política
`GROSS_SERVICE / BEFORE_FEES / 40%` → Commission CALCULATED de R$40;
`create_payout` → Movement OUTFLOW + Entry COMISSAO atômicos;
handler `operation.completed` registrado e disparando cálculo automático.

### Migrations Sprint 12

**`f1g2h3i4j5k6_commission_engine`**
```sql
CREATE TABLE commission_policies (
  policy_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id            UUID NOT NULL REFERENCES companies(id),
  professional_id       UUID nullable REFERENCES professionals(id),
  service_id            UUID nullable REFERENCES services(id),
  -- NULL em ambos = política global do tenant
  commission_base       VARCHAR NOT NULL,
  -- GROSS_SERVICE | NET_SERVICE | GROSS_OPERATION | CUSTOM_AMOUNT
  commission_fee_policy VARCHAR NOT NULL,
  -- BEFORE_FEES | AFTER_FEES
  rate                  NUMERIC(5,2) nullable,    -- percentual (0-100)
  fixed_amount          NUMERIC(10,2) nullable,   -- para CUSTOM_AMOUNT
  CONSTRAINT rate_or_fixed CHECK (
    (rate IS NOT NULL AND fixed_amount IS NULL) OR
    (rate IS NULL AND fixed_amount IS NOT NULL)
  ),
  is_active             BOOLEAN NOT NULL DEFAULT true,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ
);
CREATE POLICY tenant_isolation ON commission_policies
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE commission_policies ENABLE ROW LEVEL SECURITY;

CREATE TABLE commission_payouts (
  payout_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES companies(id),
  professional_id   UUID NOT NULL REFERENCES professionals(id),
  total_amount      NUMERIC(10,2) NOT NULL,
  account_id        UUID NOT NULL REFERENCES accounts(account_id),
  status            VARCHAR NOT NULL DEFAULT 'PENDING',
  -- PENDING | PAID | CANCELLED
  paid_at           TIMESTAMPTZ nullable,
  created_by        UUID NOT NULL REFERENCES users(id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON commission_payouts
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE commission_payouts ENABLE ROW LEVEL SECURITY;

CREATE TABLE commissions (
  commission_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES companies(id),
  professional_id   UUID NOT NULL REFERENCES professionals(id),
  policy_id         UUID nullable REFERENCES commission_policies(policy_id),
  appointment_id    UUID nullable REFERENCES appointments(id),
  operation_type    VARCHAR NOT NULL,
  -- SERVICE_RENDERED | PACKAGE_SOLD | SUBSCRIPTION_SOLD
  gross_amount      NUMERIC(10,2) NOT NULL,
  commission_amount NUMERIC(10,2) NOT NULL,
  status            VARCHAR NOT NULL DEFAULT 'CALCULATED',
  -- CALCULATED | DUE | PAID | REVERSED
  due_date          DATE nullable,
  paid_at           TIMESTAMPTZ nullable,
  payout_id         UUID nullable REFERENCES commission_payouts(payout_id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON commissions
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE commissions ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 12

**`app/modules/commission/service.py`** — CommissionEngine:

```python
def calculate_commission(
    professional_id, service_id, gross_amount, provider_fee,
    operation_type, appointment_id, company_id, db
) -> Commission | None:
    """
    Lookup de política com prioridade:
    1. (professional_id, service_id) específico
    2. (professional_id, None) — profissional, qualquer serviço
    3. (None, service_id) — serviço, qualquer profissional
    4. (None, None) — global do tenant
    5. Sem política ativa → retorna None (sem comissão, sem erro)

    commission_base:
      GROSS_SERVICE  → base = gross_amount
      NET_SERVICE    → base = gross_amount - discount_amount
      CUSTOM_AMOUNT  → commission = policy.fixed_amount (ignora rate)

    commission_fee_policy:
      BEFORE_FEES → base não deduz provider_fee
      AFTER_FEES  → base -= provider_fee antes de aplicar rate
    """

def mark_due(commission_id, due_date, company_id, db) -> Commission
    # CALCULATED → DUE

def create_payout(
    professional_id, commission_ids, account_id,
    actor_id, company_id, db
) -> CommissionPayout:
    """
    Valida que todas as commissions pertencem ao professional_id.
    Cria CommissionPayout (PENDING → PAID imediatamente).
    Atualiza Commission.status = PAID + payout_id para todas.
    FinancialCoreEngine.handle_commission_paid() → Movement OUTFLOW
    + Entry COMISSAO na mesma transação.
    record_sensitive_action obrigatório.
    Emite commission.payout_created após commit.
    """

def reverse_commission(commission_id, reason, actor_id, company_id, db)
    # CALCULATED/DUE → REVERSED (ex: reembolso do serviço)
    # record_sensitive_action obrigatório
```

**Adicionar ao FinancialCoreEngine:**
```python
def handle_commission_paid(
    payout_id, amount, account_id, professional_id, company_id, db
) -> tuple[Movement, Entry]:
    # Movement OUTFLOW + Entry COMISSAO category=COMISSAO_SERVICO
```

**Handler `operation.completed`** — registrar no lifespan:
```python
# app/workers/handlers/commission_handler.py
@event_bus.on("operation.completed")
def handle_operation_completed(
    appointment_id, professional_id, service_id,
    gross_amount, provider_fee, company_id, **kwargs
):
    """Best-effort. Falha não impacta a operação concluída."""
    commission_service.calculate_commission(
        professional_id=professional_id,
        service_id=service_id,
        gross_amount=gross_amount,
        provider_fee=provider_fee,
        operation_type="SERVICE_RENDERED",
        appointment_id=appointment_id,
        company_id=company_id,
        db=db
    )
```

**Endpoints Sprint 12:**
```
GET    /commission-policies            OWNER/ADMIN
POST   /commission-policies            OWNER/ADMIN
PATCH  /commission-policies/{id}       OWNER/ADMIN
DELETE /commission-policies/{id}       OWNER/ADMIN (soft: is_active=false)
GET    /commissions                    OWNER/ADMIN (filtros: professional_id, status, date_from, date_to)
PATCH  /commissions/{id}/mark-due      OWNER/ADMIN
POST   /commission-payouts             OWNER/ADMIN + record_sensitive_action
  Body: {professional_id, commission_ids: [uuid], account_id}
GET    /commission-payouts             OWNER/ADMIN
GET    /commission-payouts/{id}        OWNER/ADMIN
```

### Testes Sprint 12
- [ ] GROSS_SERVICE + BEFORE_FEES + 40%: gross=100 → commission=40
- [ ] AFTER_FEES + 40%: gross=100, fee=2 → base=98 → commission=39.20
- [ ] CUSTOM_AMOUNT: fixed_amount=25 → commission=25 (ignora gross)
- [ ] Prioridade de política: (prof+serv) > (prof) > (serv) > (global) > None
- [ ] Sem política ativa → `calculate_commission` retorna None (sem erro)
- [ ] `create_payout`: Movement OUTFLOW + Entry COMISSAO atômicos (rollback se falhar)
- [ ] `create_payout` sem `record_sensitive_action` → falha silenciosa registrada
- [ ] `operation.completed` handler → Commission CALCULATED criada (best-effort)
- [ ] `reverse_commission` CALCULATED → REVERSED + audit
- [ ] Cross-tenant: commissions e policies isoladas

---

## Sprint 13 — CustomerCredit (Cotas)

**Objetivo:** Sistema de cotas de uso de serviços — base para pacotes e assinaturas.
FEFO (First Expired, First Out): cota com vencimento mais próximo é consumida primeiro.

**Critério de conclusão:** Cliente com 2 cotas (30d e 60d) → `consume_for_operation`
consome a de 30d; SELECT FOR UPDATE garante atomicidade em consumo concorrente;
cota expirada nunca é consumida; `customer_credit_expiry_worker` move para EXPIRED.

### Migrations Sprint 13

**`g1h2i3j4k5l6_customer_credit`**
```sql
CREATE TABLE customer_credits (
  credit_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES companies(id),
  customer_id       UUID NOT NULL REFERENCES customers(id),
  entitlement_type  VARCHAR NOT NULL,
  -- PACKAGE | SUBSCRIPTION | GRANT_COTA
  source_id         UUID nullable,  -- package_purchase_id ou subscription_id
  total_cotas       INTEGER NOT NULL CHECK (total_cotas > 0),
  remaining_cotas   INTEGER NOT NULL,
  status            VARCHAR NOT NULL DEFAULT 'ACTIVE',
  -- ACTIVE | EXHAUSTED | EXPIRED | REVOKED
  granted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at        TIMESTAMPTZ nullable,  -- NULL = sem vencimento
  CONSTRAINT remaining_lte_total CHECK (remaining_cotas <= total_cotas),
  CONSTRAINT remaining_gte_zero  CHECK (remaining_cotas >= 0)
);
CREATE POLICY tenant_isolation ON customer_credits
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE customer_credits ENABLE ROW LEVEL SECURITY;

CREATE TABLE customer_credit_consumptions (
  consumption_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  credit_id       UUID NOT NULL REFERENCES customer_credits(credit_id),
  company_id      UUID NOT NULL REFERENCES companies(id),
  customer_id     UUID NOT NULL REFERENCES customers(id),
  appointment_id  UUID nullable REFERENCES appointments(id),
  consumed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON customer_credit_consumptions
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE customer_credit_consumptions ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 13

**`app/modules/customer_credit/service.py`:**
```python
def consume_for_operation(
    customer_id, appointment_id, company_id, db
) -> CustomerCreditConsumption:
    """
    FEFO: ORDER BY expires_at NULLS LAST, granted_at ASC.
    SELECT ... FOR UPDATE SKIP LOCKED (concorrência segura).
    Filtra: status=ACTIVE AND (expires_at IS NULL OR expires_at > now()).
    remaining_cotas -= 1.
    Se remaining_cotas == 0: status = EXHAUSTED.
    Cria CustomerCreditConsumption.
    Emite customer_credit.consumed via EventBus.
    Se nenhuma cota disponível: raise NoCreditAvailableError (HTTP 422).
    """

def grant_cota(
    customer_id, total_cotas, expires_at,
    reason, actor_id, company_id, db
) -> CustomerCredit:
    """
    Concessão manual (entitlement_type=GRANT_COTA).
    NÃO gera Movement/Entry — não é receita, é cortesia ou ajuste.
    record_sensitive_action obrigatório com reason.
    """

def revoke(credit_id, reason, actor_id, company_id, db) -> CustomerCredit:
    # ACTIVE/EXHAUSTED → REVOKED.
    # record_sensitive_action obrigatório.
    # Emite customer_credit.revoked.

def get_balance(customer_id, company_id, db) -> list[dict]:
    # Retorna lista de créditos ACTIVE com saldo, vencimento e origem.
```

**Celery Beat task** — `customer_credit_expiry_worker`:
```python
@celery.task
def customer_credit_expiry_worker():
    # ACTIVE com expires_at < now() → EXPIRED
    # Emite customer_credit.expired via EventBus (best-effort)
```
Schedule: diário às 02:30.

**Endpoints Sprint 13:**
```
GET    /customer-credits?customer_id=    OWNER/ADMIN
GET    /customer-credits/balance?customer_id=   OWNER/ADMIN/OPERATOR
POST   /customer-credits/grant-cota      OWNER/ADMIN + record_sensitive_action
  Body: {customer_id, total_cotas, expires_at?, reason}
POST   /customer-credits/{id}/revoke     OWNER/ADMIN
  Body: {reason}
```

### Testes Sprint 13
- [ ] FEFO: 2 créditos (30d e 60d) → consome o de 30d primeiro
- [ ] Cota EXPIRED não é consumida → NoCreditAvailableError
- [ ] Cota EXHAUSTED não é consumida → NoCreditAvailableError
- [ ] remaining_cotas chega a 0 → status automaticamente EXHAUSTED
- [ ] SELECT FOR UPDATE: 2 consumos simultâneos para mesma cota com 1 remaining → apenas 1 sucede
- [ ] `grant_cota` → sem Movement/Entry (verificar via list_movements)
- [ ] `grant_cota` sem reason → 422
- [ ] `revoke` → status REVOKED + audit
- [ ] `customer_credit_expiry_worker` → ACTIVE com expires_at no passado → EXPIRED

---

## Sprint 14 — Pacotes

**Objetivo:** Venda de pacote gera CustomerCredit; comissão separada para vendedor
(PACKAGE_SOLD) e para o prestador a cada uso da cota (SERVICE_RENDERED).

**Critério de conclusão:**
- `purchase()` → PackagePurchase PENDING_PAYMENT + Payment criados
- `payment.confirmed` (pacote) → `activate()` → CustomerCredit ACTIVE
- Commission PACKAGE_SOLD calculada para o vendedor na ativação
- Refund → CustomerCredit REVOKED + Commission REVERSED

### Migrations Sprint 14

**`h1i2j3k4l5m6_packages`**
```sql
CREATE TABLE packages (
  package_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES companies(id),
  name              VARCHAR NOT NULL,
  service_id        UUID nullable REFERENCES services(id),
  -- NULL = vale para qualquer serviço
  total_cotas       INTEGER NOT NULL CHECK (total_cotas > 0),
  price             NUMERIC(10,2) NOT NULL CHECK (price >= 0),
  validity_days     INTEGER nullable,  -- NULL = sem vencimento
  is_active         BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ
);
CREATE POLICY tenant_isolation ON packages
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE packages ENABLE ROW LEVEL SECURITY;

CREATE TABLE package_purchases (
  purchase_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES companies(id),
  customer_id       UUID NOT NULL REFERENCES customers(id),
  package_id        UUID NOT NULL REFERENCES packages(package_id),
  seller_user_id    UUID nullable REFERENCES users(id),
  payment_id        UUID nullable REFERENCES payments(payment_id),
  total_price       NUMERIC(10,2) NOT NULL,
  status            VARCHAR NOT NULL DEFAULT 'PENDING_PAYMENT',
  -- PENDING_PAYMENT | ACTIVE | REVOKED
  activated_at      TIMESTAMPTZ nullable,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON package_purchases
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE package_purchases ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 14

**`app/modules/packages/service.py`:**
```python
def purchase(
    customer_id, package_id, seller_user_id,
    payment_method, target_account_id, company_id, db
) -> PackagePurchase:
    """
    Cria PackagePurchase (PENDING_PAYMENT).
    Cria Payment via PaymentsEngine.create_payment(
        gross_amount=package.price,
        payment_method=payment_method,
        appointment_id=None
    ).
    PackagePurchase.payment_id = payment.payment_id.
    """

def activate(purchase_id, company_id, db) -> PackagePurchase:
    """
    Chamado por handler payment.confirmed quando payment está
    vinculado a um PackagePurchase.

    Numa única transação:
      PackagePurchase.status = ACTIVE
      PackagePurchase.activated_at = now()
      CustomerCredit(
          entitlement_type=PACKAGE,
          source_id=purchase_id,
          total_cotas=package.total_cotas,
          expires_at=now()+validity_days se definido
      )

    Após commit:
      CommissionEngine.calculate_commission(
          operation_type=PACKAGE_SOLD,
          professional_id=seller_user_id (se for professional),
          gross_amount=package.price
      )
      EventBus.publish("package.purchased")
    """
```

**Integração com `payment.confirmed`:**
Antes de publicar `payment.confirmed` via EventBus, verificar se
`Payment.appointment_id` está vinculado a um `PackagePurchase`.
Se sim: chamar `package_service.activate(purchase_id)`.

**Endpoints Sprint 14:**
```
GET    /packages               OWNER/ADMIN
POST   /packages               OWNER/ADMIN
PATCH  /packages/{id}          OWNER/ADMIN
DELETE /packages/{id}          OWNER/ADMIN (soft: is_active=false)
POST   /packages/{id}/sell     OWNER/ADMIN/OPERATOR
  Body: {customer_id, seller_user_id?, payment_method, target_account_id}
  → Retorna {purchase_id, payment_id}
GET    /package-purchases       OWNER/ADMIN (filtros: customer_id, status)
GET    /package-purchases/{id}  OWNER/ADMIN
```

### Testes Sprint 14
- [ ] `purchase()` → PackagePurchase PENDING_PAYMENT + Payment PENDING criados
- [ ] `payment.confirmed` (purchase) → `activate()` → CustomerCredit ACTIVE
- [ ] CustomerCredit.total_cotas == package.total_cotas
- [ ] CustomerCredit.expires_at = now()+validity_days (quando definido)
- [ ] `activate()` com Commission PACKAGE_SOLD calculada para seller
- [ ] Refund do Payment → CustomerCredit REVOKED + Commission REVERSED
- [ ] `purchase()` com package inativo → 422
- [ ] Cross-tenant: packages e purchases isolados

---

## Sprint 15 — Assinaturas

**Objetivo:** Planos recorrentes com cobrança automática via Asaas, geração de cotas
por ciclo e lifecycle ACTIVE/PAUSED/OVERDUE/SUSPENDED/CANCELLED.

**Critério de conclusão:**
- `subscription_renewal_worker` gera Payment no `next_billing_at` e avança data
- `payment.confirmed` (assinatura) → cotas renovadas + Entry ASSINATURA_RENOVACAO
- Inadimplência por 7d → OVERDUE; 30d → SUSPENDED; consumo de cota bloqueado

### Migrations Sprint 15

**`i1j2k3l4m5n6_subscriptions`**
```sql
CREATE TABLE subscription_plans (
  plan_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES companies(id),
  name              VARCHAR NOT NULL,
  service_id        UUID nullable REFERENCES services(id),
  cotas_per_cycle   INTEGER NOT NULL CHECK (cotas_per_cycle > 0),
  price             NUMERIC(10,2) NOT NULL CHECK (price >= 0),
  cycle_days        INTEGER NOT NULL DEFAULT 30,
  rollover_enabled  BOOLEAN NOT NULL DEFAULT false,
  -- false: cotas não usadas expiram no fim do ciclo
  is_active         BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ
);
CREATE POLICY tenant_isolation ON subscription_plans
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE subscription_plans ENABLE ROW LEVEL SECURITY;

CREATE TABLE customer_subscriptions (
  subscription_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES companies(id),
  customer_id       UUID NOT NULL REFERENCES customers(id),
  plan_id           UUID NOT NULL REFERENCES subscription_plans(plan_id),
  status            VARCHAR NOT NULL DEFAULT 'ACTIVE',
  -- ACTIVE | PAUSED | OVERDUE | SUSPENDED | CANCELLED
  next_billing_at   TIMESTAMPTZ NOT NULL,
  overdue_since     TIMESTAMPTZ nullable,
  paused_at         TIMESTAMPTZ nullable,
  cancelled_at      TIMESTAMPTZ nullable,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON customer_subscriptions
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE customer_subscriptions ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 15

**Workers Celery Beat:**

`subscription_renewal_worker` — diário às 06:00:
```python
# Seleciona ACTIVE com next_billing_at <= now()
# → PaymentsEngine.create_payment(gross_amount=plan.price)
# → subscription.next_billing_at += cycle_days
```

`subscription_overdue_worker` — diário às 08:00:
```python
# ACTIVE sem pagamento há > grace_period_days (default 7):
#   → status = OVERDUE; overdue_since = now()
# OVERDUE há > auto_cancel_threshold_days (default 30):
#   → status = SUSPENDED
#   (consumo de cotas bloqueado; CustomerCredit.status não muda,
#    mas consume_for_operation deve verificar subscription.status)
```

**Handler `payment.confirmed`** (subscription):
```python
# Identifica subscription vinculada ao payment
# Renova CustomerCredit: cria novo credit com cotas_per_cycle cotas
#   (se rollover_enabled=false: expires_at = now()+cycle_days)
# Entry RECEITA category=ASSINATURA_RENOVACAO
# Emite subscription.renewed
```

**Endpoints Sprint 15:**
```
GET    /subscription-plans               OWNER/ADMIN
POST   /subscription-plans               OWNER/ADMIN
PATCH  /subscription-plans/{id}          OWNER/ADMIN
GET    /subscriptions                    OWNER/ADMIN (filtros: customer_id, status)
POST   /subscriptions                    OWNER/ADMIN
  Body: {customer_id, plan_id, first_billing_at?}
GET    /subscriptions/{id}               OWNER/ADMIN
PATCH  /subscriptions/{id}/pause         OWNER/ADMIN
PATCH  /subscriptions/{id}/resume        OWNER/ADMIN
PATCH  /subscriptions/{id}/cancel        OWNER/ADMIN
```

### Testes Sprint 15
- [ ] `subscription_renewal_worker`: ACTIVE + next_billing_at no passado → Payment PENDING criado
- [ ] `payment.confirmed` (subscription) → CustomerCredit renovado + Entry ASSINATURA_RENOVACAO
- [ ] `rollover_enabled=false`: cotas expiram em now()+cycle_days (não acumulam)
- [ ] Inadimplência 7d → OVERDUE; 30d → SUSPENDED
- [ ] SUSPENDED → `consume_for_operation` bloqueado → NoCreditAvailableError
- [ ] `pause` → status PAUSED; `resume` → ACTIVE; `cancel` → CANCELLED
- [ ] Cross-tenant: subscriptions e plans isolados

---

## Sprint 16 — Promoções e Cupons

**Objetivo:** Promoções automáticas e cupons de desconto com algoritmo
cumulative/exclusive, preview sem efeito colateral, revalidação na efetivação.

**Critério de conclusão:**
- `compute_preview` calcula desconto sem nenhum registro no banco
- Cupom `PROMO10` aplicado: preview=R$10 desconto; efetivação só em `payment.confirmed`
- Promoção revalidada antes de efetivar (pode ter expirado entre preview e pagamento)

### Migrations Sprint 16

**`j1k2l3m4n5o6_promotions_coupons`**
```sql
CREATE TABLE promotions (
  promotion_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES companies(id),
  name              VARCHAR NOT NULL,
  discount_type     VARCHAR NOT NULL,  -- PERCENTAGE | FIXED_AMOUNT
  discount_value    NUMERIC(10,2) NOT NULL CHECK (discount_value > 0),
  stacking_policy   VARCHAR NOT NULL DEFAULT 'EXCLUSIVE',
  -- EXCLUSIVE | CUMULATIVE
  conditions        JSONB DEFAULT '{}',
  -- {min_items?, service_ids?, weekdays?, time_from?, time_to?}
  audience          JSONB DEFAULT '{}',
  -- {new_customers_only?, customer_ids?}
  starts_at         TIMESTAMPTZ nullable,
  ends_at           TIMESTAMPTZ nullable,
  usage_limit       INTEGER nullable,  -- NULL = ilimitado
  usage_count       INTEGER NOT NULL DEFAULT 0,
  is_active         BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON promotions
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE promotions ENABLE ROW LEVEL SECURITY;

CREATE TABLE coupons (
  coupon_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES companies(id),
  code              VARCHAR NOT NULL,
  promotion_id      UUID NOT NULL REFERENCES promotions(promotion_id),
  max_uses          INTEGER nullable,  -- NULL = ilimitado
  uses_count        INTEGER NOT NULL DEFAULT 0,
  is_active         BOOLEAN NOT NULL DEFAULT true,
  UNIQUE(company_id, code)
);
CREATE POLICY tenant_isolation ON coupons
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE coupons ENABLE ROW LEVEL SECURITY;

CREATE TABLE coupon_redemptions (
  redemption_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID NOT NULL REFERENCES companies(id),
  coupon_id         UUID NOT NULL REFERENCES coupons(coupon_id),
  customer_id       UUID nullable REFERENCES customers(id),
  payment_id        UUID nullable REFERENCES payments(payment_id),
  discount_applied  NUMERIC(10,2) NOT NULL,
  redeemed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON coupon_redemptions
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE coupon_redemptions ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 16

**`app/modules/promotions/service.py`:**
```python
def find_eligible(
    customer_id, service_ids, appointment_data, company_id, db
) -> list[Promotion]:
    """
    Filtra promoções ativas, dentro do período e com usage_count < usage_limit.
    Aplica conditions: service_ids, weekdays, time_from/to.
    Aplica audience: new_customers_only, customer_ids.
    """

def compute_preview(
    gross_amount, promotion_ids, coupon_code, company_id, db
) -> dict:
    """
    Retorna {discount_total, net_amount, applied, coupon_valid}.
    NÃO persiste nenhum dado — apenas calcula.
    Algoritmo:
      1. Separa EXCLUSIVE vs CUMULATIVE das promoções elegíveis
      2. EXCLUSIVE: aplica a de maior desconto (CUSTOMER_FAVORABLE)
      3. CUMULATIVE: aplica em sequência sobre o valor residual
      4. Cupom: valida formato + uses_count < max_uses + is_active
         Se inválido: coupon_valid=false, desconto do cupom não aplicado
    """

def effectuate(
    payment_id, coupon_code, promotion_ids,
    customer_id, company_id, db
):
    """
    Chamado em payment.confirmed.
    Revalida promoções e cupom (podem ter expirado entre preview e pagamento).
    Cria CouponRedemption.
    Incrementa coupon.uses_count e promotion.usage_count atomicamente
    (SELECT ... FOR UPDATE).
    Atualiza payment.discount_amount + net_charged_amount.
    """
```

**Desconto manual:** `POST /payments/{id}/manual-discount`
(OWNER/ADMIN + reason obrigatório + record_sensitive_action).

**Endpoints Sprint 16:**
```
GET    /promotions              OWNER/ADMIN
POST   /promotions              OWNER/ADMIN
PATCH  /promotions/{id}         OWNER/ADMIN
DELETE /promotions/{id}         OWNER/ADMIN (soft: is_active=false)
GET    /coupons                 OWNER/ADMIN
POST   /coupons                 OWNER/ADMIN
PATCH  /coupons/{id}            OWNER/ADMIN
POST   /promotions/preview
  Body: {gross_amount, service_ids, coupon_code?, customer_id?}
  → Retorna preview sem persistência; público ou autenticado
GET    /coupon-redemptions      OWNER/ADMIN (filtros: coupon_id, date_from, date_to)
```

### Testes Sprint 16
- [ ] EXCLUSIVE: 2 promoções elegíveis → aplica a de maior desconto
- [ ] CUMULATIVE: 10% + 5% sobre R$100 → R$90 → R$85.50
- [ ] `compute_preview` não cria nenhum registro no banco (verificar via SELECT)
- [ ] Cupom expirado ou uses_count >= max_uses → coupon_valid=false no preview
- [ ] `effectuate`: revalidação antes de efetivar — promoção expirada entre preview/pagamento → desconto não aplicado
- [ ] `uses_count` incrementado atomicamente: 2 usos simultâneos do mesmo cupom com max_uses=1 → apenas 1 sucede
- [ ] Desconto manual sem reason → 422; com reason → audit gravado
- [ ] Cross-tenant: promoções e cupons isolados por company_id

---

## Sprint 17 — Estoque + Fornecedores + Payables

**Objetivo:** Controle de estoque com rastreamento de movimentações, gestão de
fornecedores e obrigações a pagar vinculadas a compras ou lançamentos manuais.

**Critério de conclusão:**
- Venda de produto via Operação → StockMovement SAIDA criado automaticamente
- Recebimento de ordem de compra → StockMovement ENTRADA + Payable criado
- `pay_installment` → Movement OUTFLOW + Entry CUSTO atômicos
- `stock_alert_worker` emite alerta quando stock <= stock_min_alert

### Migrations Sprint 17

**`k1l2m3n4o5p6_stock_suppliers_payables`**
```sql
-- Campos adicionais em products (stock e unit já existem)
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS stock_min_alert INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS unit            VARCHAR DEFAULT 'un';

-- Movimentações de estoque
CREATE TABLE stock_movements (
  movement_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    UUID NOT NULL REFERENCES companies(id),
  product_id    UUID NOT NULL REFERENCES products(id),
  type          VARCHAR NOT NULL,
  -- ENTRADA | SAIDA | AJUSTE | PERDA
  quantity      INTEGER NOT NULL,
  -- positivo = entrada de estoque, negativo = saída
  source_type   VARCHAR nullable,
  -- SALE | PURCHASE_ORDER | MANUAL | APPOINTMENT
  source_id     UUID nullable,
  notes         TEXT nullable,
  created_by    UUID NOT NULL REFERENCES users(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON stock_movements
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE stock_movements ENABLE ROW LEVEL SECURITY;

-- Fornecedores
CREATE TABLE suppliers (
  supplier_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    UUID NOT NULL REFERENCES companies(id),
  name          VARCHAR NOT NULL,
  document      VARCHAR nullable,  -- CNPJ ou CPF (plaintext — pessoa jurídica)
  email         VARCHAR nullable,
  phone         VARCHAR nullable,
  is_active     BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON suppliers
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE suppliers ENABLE ROW LEVEL SECURITY;

CREATE TABLE supplier_orders (
  order_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    UUID NOT NULL REFERENCES companies(id),
  supplier_id   UUID NOT NULL REFERENCES suppliers(supplier_id),
  status        VARCHAR NOT NULL DEFAULT 'DRAFT',
  -- DRAFT | SENT | RECEIVED | CANCELLED
  total_amount  NUMERIC(10,2) NOT NULL DEFAULT 0,
  ordered_at    TIMESTAMPTZ nullable,
  received_at   TIMESTAMPTZ nullable,
  notes         TEXT nullable,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON supplier_orders
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE supplier_orders ENABLE ROW LEVEL SECURITY;

-- Contas a pagar
CREATE TABLE payables (
  payable_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id    UUID NOT NULL REFERENCES companies(id),
  description   VARCHAR NOT NULL,
  category      VARCHAR NOT NULL,   -- EntryCategory (CUSTO ou DESPESA)
  total_amount  NUMERIC(10,2) NOT NULL CHECK (total_amount > 0),
  supplier_id   UUID nullable REFERENCES suppliers(supplier_id),
  source_type   VARCHAR nullable,   -- SUPPLIER_ORDER | MANUAL
  source_id     UUID nullable,
  status        VARCHAR NOT NULL DEFAULT 'OPEN',
  -- OPEN | PARTIAL | PAID | CANCELLED
  due_date      DATE nullable,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON payables
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE payables ENABLE ROW LEVEL SECURITY;

CREATE TABLE payable_installments (
  installment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES companies(id),
  payable_id     UUID NOT NULL REFERENCES payables(payable_id),
  amount         NUMERIC(10,2) NOT NULL CHECK (amount > 0),
  due_date       DATE NOT NULL,
  status         VARCHAR NOT NULL DEFAULT 'PENDING',
  -- PENDING | PAID | OVERDUE
  paid_at        TIMESTAMPTZ nullable,
  account_id     UUID nullable REFERENCES accounts(account_id),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON payable_installments
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE payable_installments ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 17

**`app/modules/stock/service.py`:**
```python
def record_movement(
    product_id, type, quantity, source_type,
    source_id, notes, actor_id, company_id, db
) -> StockMovement:
    """
    products.stock += quantity (pode ficar negativo — alerta, não erro).
    Cria StockMovement.
    Se products.stock <= products.stock_min_alert:
        EventBus.publish("stock.below_minimum", ...) (best-effort)
    """
```

**Adicionar ao FinancialCoreEngine:**
```python
def handle_expense_paid(
    source_id, source_type, amount, account_id,
    category, company_id, db
) -> tuple[Movement, Entry]:
    # Movement OUTFLOW + Entry CUSTO ou DESPESA
    # category deve pertencer a EntryCategory.CUSTO ou CUSTO/DESPESA
```

**`app/modules/payables/service.py`:**
```python
def pay_installment(
    installment_id, account_id, actor_id, company_id, db
) -> PayableInstallment:
    """
    Numa única transação:
      installment.status = PAID; paid_at = now()
      FinancialCoreEngine.handle_expense_paid(...)
      Se todas as installments do Payable estão PAID: payable.status = PAID
    """
```

**Integração com supplier_orders:**
`PATCH /supplier-orders/{id}/receive`:
- supplier_order.status = RECEIVED; received_at = now()
- Para cada item da ordem: `record_movement(type=ENTRADA, quantity=+n)`
- Cria Payable vinculado à ordem (supplier_id + total_amount)

**Celery Beat** — `stock_alert_worker` — diário às 07:00:
```python
# SELECT products WHERE stock <= stock_min_alert AND active=true
# Emite stock.below_minimum por produto (EventBus best-effort)
```

**Endpoints Sprint 17:**
```
GET    /stock/movements?product_id=        OWNER/ADMIN
POST   /stock/adjustment                   OWNER/ADMIN + reason obrigatório
  Body: {product_id, quantity, notes, reason}
GET    /suppliers                          OWNER/ADMIN
POST   /suppliers                          OWNER/ADMIN
PATCH  /suppliers/{id}                     OWNER/ADMIN
GET    /supplier-orders                    OWNER/ADMIN
POST   /supplier-orders                    OWNER/ADMIN
PATCH  /supplier-orders/{id}/receive       OWNER/ADMIN
GET    /payables                           OWNER/ADMIN (filtros: status, due_date, supplier_id)
POST   /payables                           OWNER/ADMIN
PATCH  /payables/{id}                      OWNER/ADMIN
POST   /payables/{id}/installments         OWNER/ADMIN (cria parcela)
POST   /payable-installments/{id}/pay      OWNER/ADMIN + account_id
```

### Testes Sprint 17
- [ ] `record_movement` ENTRADA: products.stock incrementado + StockMovement criado
- [ ] `record_movement` SAIDA: products.stock decrementado (pode ir negativo)
- [ ] stock <= stock_min_alert → stock.below_minimum emitido (EventBus)
- [ ] `pay_installment` → Movement OUTFLOW + Entry CUSTO atômicos
- [ ] Todas as installments PAID → Payable.status = PAID
- [ ] `receive_order` → StockMovement ENTRADA + Payable criados (mesma transação)
- [ ] `handle_expense_paid` no FinancialCoreEngine sem quebrar testes existentes
- [ ] Cross-tenant: stock, suppliers e payables isolados

---

## Sprint 18 — Despesas

**Objetivo:** Registro e ciclo de vida de despesas operacionais, com recorrência
automática e worker de alerta de vencimento.

**Critério de conclusão:**
- Despesa de aluguel paga → Movement OUTFLOW + Entry DESPESA via FinancialCoreEngine
- Despesa recorrente mensal paga → próxima instância criada automaticamente
- `expense_due_soon_worker` emite alerta 3 dias antes do vencimento

### Migrations Sprint 18

**`l1m2n3o4p5q6_expenses`**
```sql
CREATE TABLE expense_recurrences (
  recurrence_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id      UUID NOT NULL REFERENCES companies(id),
  description     VARCHAR NOT NULL,
  category        VARCHAR NOT NULL,   -- EntryCategory.DESPESA
  amount          NUMERIC(10,2) NOT NULL CHECK (amount > 0),
  frequency       VARCHAR NOT NULL,
  -- MONTHLY | WEEKLY | YEARLY | CUSTOM
  custom_days     INTEGER nullable,  -- para CUSTOM
  day_of_month    INTEGER nullable,  -- para MONTHLY (1-28)
  next_due_date   DATE NOT NULL,
  account_id      UUID nullable REFERENCES accounts(account_id),
  supplier_id     UUID nullable REFERENCES suppliers(supplier_id),
  is_active       BOOLEAN NOT NULL DEFAULT true,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON expense_recurrences
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE expense_recurrences ENABLE ROW LEVEL SECURITY;

CREATE TABLE expenses (
  expense_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id      UUID NOT NULL REFERENCES companies(id),
  description     VARCHAR NOT NULL,
  category        VARCHAR NOT NULL,   -- EntryCategory.DESPESA
  amount          NUMERIC(10,2) NOT NULL CHECK (amount > 0),
  account_id      UUID nullable REFERENCES accounts(account_id),
  supplier_id     UUID nullable REFERENCES suppliers(supplier_id),
  status          VARCHAR NOT NULL DEFAULT 'PENDENTE',
  -- PENDENTE | PAGA | CANCELADA
  due_date        DATE NOT NULL,
  paid_at         TIMESTAMPTZ nullable,
  recurrence_id   UUID nullable REFERENCES expense_recurrences(recurrence_id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON expenses
  USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE expenses ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 18

**`app/modules/expenses/service.py`:**
```python
def pay_expense(
    expense_id, account_id, actor_id, company_id, db
) -> Expense:
    """
    Expense PENDENTE → PAGA.
    FinancialCoreEngine.handle_expense_paid(
        source_id=expense_id, source_type="EXPENSE",
        amount=expense.amount, account_id=account_id,
        category=expense.category  -- deve ser EntryCategory.DESPESA
    ) → Movement OUTFLOW + Entry DESPESA (mesma transação).
    Se expense.recurrence_id: cria próxima Expense a partir da
    recorrência (fora da transação — falha não cancela o pagamento).
    Emite expense.paid.
    """
```

**Validação de categoria:** `handle_expense_paid` rejeita categoria
que não seja do tipo DESPESA com HTTP 422 (previne mistura com CUSTO).

**Celery Beat workers:**

`expense_due_soon_worker` — diário às 07:30:
```python
# PENDENTE com due_date entre hoje e hoje+3d
# → EventBus.publish("expense.due_soon") por despesa (best-effort)
```

`expense_recurrence_worker` — diário às 06:00:
```python
# ExpenseRecurrence ativa com next_due_date <= today
# → INSERT Expense(status=PENDENTE, recurrence_id=...)
# → Calcula próximo next_due_date conforme frequency
# → UPDATE expense_recurrences.next_due_date
```

**next_due_date por frequency:**
```
MONTHLY:  next = due_date + 1 mês (respeitando day_of_month)
WEEKLY:   next = due_date + 7 dias
YEARLY:   next = due_date + 1 ano
CUSTOM:   next = due_date + custom_days
```

**Endpoints Sprint 18:**
```
GET    /expenses                    OWNER/ADMIN (filtros: status, due_date_from, due_date_to, category)
POST   /expenses                    OWNER/ADMIN
PATCH  /expenses/{id}               OWNER/ADMIN (apenas PENDENTE)
POST   /expenses/{id}/pay           OWNER/ADMIN
  Body: {account_id}
DELETE /expenses/{id}               OWNER/ADMIN (soft: CANCELADA; apenas PENDENTE)
GET    /expense-recurrences         OWNER/ADMIN
POST   /expense-recurrences         OWNER/ADMIN
PATCH  /expense-recurrences/{id}    OWNER/ADMIN
DELETE /expense-recurrences/{id}    OWNER/ADMIN (soft: is_active=false)
```

### Testes Sprint 18
- [ ] `pay_expense` → Movement OUTFLOW + Entry DESPESA atômicos
- [ ] `pay_expense` com categoria CUSTO → 422 (mistura proibida)
- [ ] Despesa recorrente paga → nova Expense PENDENTE criada com next_due_date correto
- [ ] `expense_recurrence_worker` MONTHLY: next = mês seguinte
- [ ] `expense_due_soon_worker`: due_date em 2d → expense.due_soon emitido
- [ ] `PATCH` em despesa PAGA → 422 (somente PENDENTE editável)
- [ ] DELETE em despesa PAGA → 422
- [ ] Cross-tenant: expenses e recurrences isolados

---

## Critérios de conclusão da Fase 3

```bash
pytest tests/test_sprint11_catalog.py          -v
pytest tests/test_sprint12_commissions.py      -v
pytest tests/test_sprint13_customer_credit.py  -v
pytest tests/test_sprint14_packages.py         -v
pytest tests/test_sprint15_subscriptions.py    -v
pytest tests/test_sprint16_promotions.py       -v
pytest tests/test_sprint17_stock.py            -v
pytest tests/test_sprint18_expenses.py         -v
# + suite completa sem regressões

Estado de saída — contratos estáveis para brief de frontend Fase 3:
  OK ServicePricingOverride + ServiceVariant + get_effective_price
  OK business_hours_structured retornado em /booking/{slug}/profile
  OK preparation_minutes considerado no cálculo de slots
  OK CommissionEngine: CALCULATED → DUE → PAID; dois eixos; handler registrado
  OK handle_commission_paid no FinancialCoreEngine
  OK CustomerCredit: FEFO + ACTIVE/EXHAUSTED/EXPIRED/REVOKED; SELECT FOR UPDATE
  OK Package + PackagePurchase + activate() → CustomerCredit
  OK SubscriptionPlan + CustomerSubscription + Celery renewal/overdue
  OK Promotion + Coupon: compute_preview sem efeito colateral; revalidação
  OK StockMovement + Supplier + SupplierOrder + Payable/Installment
  OK handle_expense_paid no FinancialCoreEngine (DESPESA apenas)
  OK Expense + ExpenseRecurrence + workers due_soon + recurrence
  OK RLS em todas as novas 18+ tabelas
  OK Cross-tenant testado em cada sprint
```

---

## Restrições desta fase

**NÃO criar ou alterar nenhum arquivo em `painel/`** — zero frontend nesta fase.

- NÃO criar Portal do Cliente (Sprint 21)
- NÃO criar Painel PLATFORM_OWNER (Sprint 24)
- NÃO criar NPS ou Fila (Sprint 22)
- NÃO criar CRM (Sprint 23)
- NÃO implementar `accounting_mode=ACCRUAL` (trigger bloqueia)
- NÃO criar DiscountApplication como tabela (resolve em memória no preview)
- NÃO expor `_record_movement` ou `_record_entry` diretamente
- NÃO criptografar `supplier.document` (plaintext aceitável — pessoa jurídica)
- NÃO cobrar assinatura fora do Asaas nesta fase

---

## Notas para o brief de frontend (Fase 3 FE)

O brief de frontend será gerado após conclusão e validação em produção
de todos os 8 sprints acima. Ele cobrirá:

- Catálogo: gestão de variantes, pricing overrides, formulário de
  horários estruturado, filtro visual de dias fechados no BookingFlow
- Comissões: relatório por profissional, fluxo de pagamento de comissão
- CustomerCredit: saldo de cotas na ficha do cliente, concessão manual
- Pacotes: CRUD, fluxo de venda
- Assinaturas: gestão de planos, lista de assinantes, status e próxima cobrança
- Promoções: CRUD de promoções e cupons
- Estoque: posição atual, movimentações, alertas
- Fornecedores e Payables: cadastro e contas a pagar
- Despesas: lista filtrada, fluxo de pagamento

---

## Notas para Fase 4

- **Sprint 19 — Gestão Financeira UI:** DRE visual, reconciliação,
  CashCount UI, relatório de comissão. Requer Sprints 6–12 completos.
- **Sprint 20 — Identidade Paladino:** PaladinoIdentity multi-tenant.
  Feature flag para rollout gradual.
- **Sprint 21 — Portal do Cliente:** Auth por telefone/e-mail; histórico,
  cotas, assinatura. Requer Sprint 20 + Sprint 13.
- **Sprint 22 — NPS + Fila de espera**
- **Sprint 23 — CRM:** timeline unificada. Requer Sprints 10 + 13.
- **Sprint 24 — Painel PLATFORM_OWNER**
- **Sprint 25 — Schema apenas (Estágio 1 reservado)**
- **Separação de chaves PII** antes do Estágio 1 (múltiplos tenants).
- **Supplier.document:** plaintext aceito (pessoa jurídica). Reavaliar
  se fornecedores pessoas físicas forem adicionados futuramente.

---

*Brief backend-only gerado em 2026-06-01.
Fonte canônica: visao-produto-paladino.md + roadmap-estagio-0.md.
Conflitos devem ser resolvidos na visão antes da implementação.*
