# Brief de execução — Fase 2: Financial Core + Pagamentos (v2)
Sprints 6–10 · ~10 semanas
**Gerado em:** 2026-05-30 — revisão pós-review estrutural
**Encoding:** UTF-8

---

## Decisões arquiteturais fechadas nesta revisão

| # | Decisão | Adotado |
|---|---------|---------|
| 1 | TenantFeeRoutingPolicy | Sem FK em tenant_configs; company_id+fee_source como chave natural |
| 2 | Movement imutabilidade vs reconciliação | Opção A — movement_reconciliations separada; movements 100% append-only |
| 3 | Account constraint | CREATE UNIQUE INDEX com COALESCE(provider, '__none__') |
| 4 | Range type | tstzrange (TIMESTAMPTZ correto) |
| 5 | SOFT reservation concorrência | EXCLUDE com WHERE status='ACTIVE'; promoção SOFT→FIRME atômica |
| 6 | PaymentSources | Apenas métodos salvos/tokenizados; payments.payment_method para método usado |
| 7 | PaymentTransaction unicidade | UNIQUE(company_id, provider_transaction_id) |
| 8 | confirm() atomicidade | Explicitado: ProcessedIdempotencyKey na mesma transação |
| 9 | handle_expense_paid / handle_commission_paid | Removidos do Sprint 6; adicionados nos sprints das engines respectivas |
| 10 | payment.confirmed → Comunicação | Via EventBus handler fora da transação; não dentro de confirm() |
| 11 | CPF/CNPJ | Opção H: encrypted (Fernet) + hash (HMAC-SHA256) + masked; sem plaintext |
| 12 | RLS | Políticas explícitas em cada migration |

---

## Estado de entrada (pós-Fase 1 + sprints intermediários)

```
Backend — agendamento_engine/
  HEAD migrations: j1k2l3m4n5o6 (add_last_password_change_at)
  33 migrations; chain linear após merge em 906df50dc028

  Stack: FastAPI + SQLAlchemy 2.0 + Alembic + Python 3.11
  PostgreSQL via Supabase; RLS ativo em 30 tabelas
  Workers: Celery + Redis (coexistência asyncio resolvida)
  EventBus: in-process best-effort (fluxos tolerantes)
  Eventos críticos: Celery task direta

  Infra pronta para Financial Core:
    OK ProcessedIdempotencyKey — PK(key, consumer)
    OK CommunicationService — feature flag ativa, templates seedados
    OK IntegrationCredential — ASAAS no enum credentialprovider
    OK TenantConfig — fee_routing_policy_id UUID nullable SEM FK (a ser dropado Sprint 6)
    OK AuditLog — append-only via trigger no banco
    OK SensitiveAuditContext — compartilhado entre modulos
    OK IntegrationCredential — Fernet ja implementado (base para PII)
    OK Celery + Redis — retry, backoff, dead-letter
    OK RLS — 30 tabelas com tenant_isolation
    OK last_password_change_at — sessoes invalidadas na troca de senha

  Modelos existentes (27):
    Company, User, UserInvitation, AuditLog, Customer, Professional,
    Service, ProfessionalService, Product, Appointment, AppointmentService,
    AppointmentStatusLog, WorkingHour, ScheduleBlock, CompanySettings,
    CompanyProfile, BotSession, WhatsAppConnection, WebBookingSession,
    BookingSession, TenantConfig, ModuleActivation, TenantBranding,
    Category, IntegrationCredential, CommunicationSetting,
    CommunicationTemplate, CommunicationLog, PasswordResetToken

  Financial Core: canvas em branco
    Unico vestígio: financial_status em appointments +
    calculate_commission / calculate_net_value em financial.py (sem modelo)

Variaveis de ambiente novas nesta fase:
  PII_ENCRYPTION_KEY   — Fernet key para CPF/CNPJ encrypted
  PII_HASH_KEY         — chave HMAC-SHA256 para cpf_cnpj_hash
  (pode iniciar reutilizando CREDENTIAL_ENCRYPTION_KEY se PII_* atrasar,
   com migracao planejada para separar chaves antes de Estagio 1)
```

---

## Prefixo de eventos financeiros (canonico)

```
financial_core.*   — nunca financial.* sem _core

Eventos canonicos:
  financial_core.account.created
  financial_core.movement_created
  financial_core.entry_created
  financial_core.transfer_completed
  financial_core.transfer_failed
  financial_core.manual_adjustment_created
  financial_core.reconciliation_opened
  financial_core.reconciliation_closed
  cash_count.recorded
  cash_count.adjustment_created
```

---

## Sprint 6 — Financial Core: fundacao

**Objetivo:** TenantFeeRoutingPolicy, Account, Movement, Entry com imutabilidade no banco
e FinancialCoreEngine como service central.

**Criterio de conclusao:** Tenant criado tem Account CAIXA + 7 TenantFeeRoutingPolicies;
Movements e Entries imutaveis por trigger de banco e @validates ORM; handle_payment_confirmed
cria Movement INFLOW + Entry RECEITA (+ OUTFLOW + TAXA se provider_fee > 0) atomicamente.

### Migrations Sprint 6

**`k1l2m3n4o5p6_add_tenant_fee_routing_policies`**
```sql
CREATE TABLE tenant_fee_routing_policies (
    policy_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    fee_source          VARCHAR NOT NULL,
    -- ASAAS_PIX | ASAAS_CARD | MAQUININHA_DEBIT | MAQUININHA_CREDIT
    -- | ANTECIPACAO | ESTORNO | RECORRENTE_FEE
    client_share        NUMERIC(5,2) NOT NULL DEFAULT 0,
    tenant_share        NUMERIC(5,2) NOT NULL DEFAULT 100,
    professional_share  NUMERIC(5,2) NOT NULL DEFAULT 0,
    CONSTRAINT shares_sum_100 CHECK (
        client_share + tenant_share + professional_share = 100
    ),
    UNIQUE(company_id, fee_source),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ
);
CREATE POLICY tenant_isolation ON tenant_fee_routing_policies
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE tenant_fee_routing_policies ENABLE ROW LEVEL SECURITY;
```
Nota: sem FK em tenant_configs. Lookup por (company_id, fee_source).

**`l1m2n3o4p5q6_drop_fee_routing_policy_id_from_tenant_configs`**
```sql
-- Remove o placeholder UUID que existia sem FK real
ALTER TABLE tenant_configs DROP COLUMN IF EXISTS fee_routing_policy_id;
```

**`m1n2o3p4q5r6_add_accounts`**
```sql
CREATE TABLE accounts (
    account_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    name                VARCHAR NOT NULL,
    type                VARCHAR NOT NULL,
    -- CAIXA | ACQUIRER | BANK | ESCROW
    provider            VARCHAR,           -- ex: "asaas"
    external_ref        VARCHAR,
    currency            CHAR(3) NOT NULL DEFAULT 'BRL',
    status              VARCHAR NOT NULL DEFAULT 'ACTIVE',
    is_default_inflow   BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ
);

-- Constraint correta: partial unique index com COALESCE para NULLs
CREATE UNIQUE INDEX uq_default_inflow_provider
    ON accounts(company_id, COALESCE(provider, '__none__'))
    WHERE is_default_inflow = true;

CREATE POLICY tenant_isolation ON accounts
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
```

**`n1o2p3q4r5s6_add_movements_with_immutability_trigger`**
```sql
-- IMPORTANTE: sem colunas de reconciliacao — movements e 100% append-only
-- Reconciliacao via movement_reconciliations (Sprint 7)
CREATE TABLE movements (
    movement_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    account_id          UUID NOT NULL REFERENCES accounts(account_id),
    type                VARCHAR NOT NULL,
    -- INFLOW | OUTFLOW | TRANSFER_IN | TRANSFER_OUT
    amount              NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_type         VARCHAR NOT NULL,
    source_id           UUID NOT NULL,
    transfer_id         UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION prevent_movement_modification()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'movements e append-only: % nao permitido', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER movement_no_update
    BEFORE UPDATE ON movements FOR EACH ROW
    EXECUTE FUNCTION prevent_movement_modification();

CREATE TRIGGER movement_no_delete
    BEFORE DELETE ON movements FOR EACH ROW
    EXECUTE FUNCTION prevent_movement_modification();

CREATE POLICY tenant_isolation ON movements
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE movements ENABLE ROW LEVEL SECURITY;
```

**`o1p2q3r4s5t6_add_entries_with_immutability_trigger`**
```sql
CREATE TABLE entries (
    entry_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    type                VARCHAR NOT NULL,
    -- RECEITA | CUSTO | DESPESA | TAXA | COMISSAO | ESTORNO | AJUSTE
    direction           VARCHAR NOT NULL,  -- ADDS | SUBTRACTS
    amount              NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    category            VARCHAR NOT NULL,
    source_type         VARCHAR NOT NULL,
    source_id           UUID NOT NULL,
    movement_id         UUID,  -- vinculo opcional
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION prevent_entry_modification()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'entries e append-only: % nao permitido', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER entry_no_update
    BEFORE UPDATE ON entries FOR EACH ROW
    EXECUTE FUNCTION prevent_entry_modification();

CREATE TRIGGER entry_no_delete
    BEFORE DELETE ON entries FOR EACH ROW
    EXECUTE FUNCTION prevent_entry_modification();

CREATE POLICY tenant_isolation ON entries
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE entries ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 6

**`app/modules/financial_core/service.py`** — FinancialCoreEngine

API publica (queries):
```python
def get_account(account_id, company_id, db) -> Account
def list_accounts(company_id, db) -> list[Account]
def compute_balance(account_id, as_of=None, company_id=None, db=None) -> Decimal
def list_movements(company_id, filters, db) -> list[Movement]
def list_entries(company_id, filters, db) -> list[Entry]
def aggregate_dre(company_id, date_from, date_to, db) -> dict
def create_manual_adjustment(
    amount, direction, category, account_id,
    reason, actor_id, company_id, db
) -> tuple[Movement, Entry]
```

API privada (apenas handlers internos — nunca expostos como endpoints):
```python
def _record_movement(account_id, type, amount, source_type, source_id,
                     transfer_id=None, occurred_at=None, company_id=None, db=None) -> Movement
def _record_entry(type, direction, amount, category, source_type, source_id,
                  movement_id=None, occurred_at=None, company_id=None, db=None) -> Entry
```

Handlers publicos para outros modulos (chamados via evento ou diretamente):
```python
def handle_payment_confirmed(
    payment_id, gross_amount, provider_fee,
    target_account_id, fee_source, company_id, db
) -> dict:
    """
    Cria atomicamente:
      Movement INFLOW gross_amount no target_account
      Entry RECEITA gross_amount
      Se provider_fee > 0:
        Movement OUTFLOW provider_fee no target_account (fee deducted by acquirer)
        Entry TAXA provider_fee (category via TenantFeeRoutingPolicy.fee_source)
    Nao chama CommunicationService — comunicacao via EventBus fora desta transacao.
    """

# handle_expense_paid   — ADIADO para Sprint 18 (Expense module)
# handle_commission_paid — ADIADO para Sprint 12 (CommissionEngine)
```

@validates no ORM (defesa em profundidade):
```python
# models/movement.py
@validates('amount', 'type', 'account_id', 'source_type', 'source_id')
def validate_immutable(self, key, value):
    if self._sa_instance_state.has_identity:
        raise ValueError(f"Movement.{key} e imutavel apos persistencia")
    return value
```

**Hook create_company** — adicionar apos blocos existentes:
```python
# Account default CAIXA
caixa = Account(
    company_id=company.id, name="Caixa principal",
    type="CAIXA", is_default_inflow=True
)
db.add(caixa)

# TenantFeeRoutingPolicy defaults — tenant_share=100% (sem repasse)
fee_sources = [
    "ASAAS_PIX", "ASAAS_CARD", "MAQUININHA_DEBIT",
    "MAQUININHA_CREDIT", "ANTECIPACAO", "ESTORNO", "RECORRENTE_FEE"
]
for fs in fee_sources:
    db.add(TenantFeeRoutingPolicy(
        company_id=company.id, fee_source=fs,
        client_share=0, tenant_share=100, professional_share=0
    ))
# Tudo na mesma transacao do create_company
```

**Endpoints Sprint 6:**
```
GET    /financial/accounts
POST   /financial/accounts           OWNER/ADMIN
GET    /financial/accounts/{id}/balance   OWNER/ADMIN/OPERATOR
GET    /financial/movements          OWNER/ADMIN
GET    /financial/entries            OWNER/ADMIN
GET    /financial/dre                OWNER/ADMIN
POST   /financial/manual-adjustment  OWNER/ADMIN + record_sensitive_action(reason obrigatorio)
GET    /tenant/fee-routing           OWNER/ADMIN
PUT    /tenant/fee-routing/{fee_source}   OWNER/ADMIN (valida soma=100)
```

**Categorias de Entry** — `app/domain/enums/entry_category.py`:
```
RECEITA:   SERVICOS, PRODUTOS, PACOTE, ASSINATURA_ADESAO,
           ASSINATURA_RENOVACAO, SINAL_SERVICO, OUTROS
CUSTO:     INSUMOS_USO_INTERNO, PRODUTO_VENDIDO, MATERIAL_DESCARTAVEL,
           PERDA_ESTOQUE, PERDA_OPERACIONAL, OUTROS
DESPESA:   ALUGUEL, UTILITIES, MARKETING, SOFTWARE, CONTABILIDADE,
           LIMPEZA, MANUTENCAO, SALARIO, SERVICOS_PJ, ALIMENTACAO_COPA,
           EQUIPAMENTOS, TAXAS_BANCARIAS, TREINAMENTO, OUTROS
TAXA:      ACQUIRER_FEE, WITHDRAW_FEE, ANTECIPATION_FEE, OUTROS
COMISSAO:  COMISSAO_SERVICO, COMISSAO_VENDA, COMISSAO_RENOVACAO,
           COMISSAO_PERSONALIZADA
ESTORNO:   REEMBOLSO_CLIENTE, CHARGEBACK, REVERSAO_TAXA
AJUSTE:    CONTAGEM_CAIXA, CONTAGEM_ESTOQUE, CORRECAO_LANCAMENTO,
           CORRECAO_COMISSAO, OUTROS
```

### Frontend Sprint 6
Nenhuma. Financial Core UI e Sprint 19.

### Testes Sprint 6
- [ ] UPDATE direto em movements via SQL -> rejeitado pelo trigger de banco
- [ ] DELETE direto em entries via SQL -> rejeitado pelo trigger de banco
- [ ] @validates ORM rejeita mutacao de campo apos flush()
- [ ] compute_balance com 50 Movements INFLOW+OUTFLOW mistos -> resultado correto
- [ ] aggregate_dre retorna RECEITA, DESPESA, TAXA separados por categoria
- [ ] create_company -> Account CAIXA criada + 7 TenantFeeRoutingPolicies (tenant_share=100%)
- [ ] PUT /tenant/fee-routing/ASAAS_PIX com soma != 100 -> 422
- [ ] handle_payment_confirmed: gross=100, fee=2 -> Movement INFLOW 100 + Entry RECEITA + Movement OUTFLOW 2 + Entry TAXA
- [ ] handle_payment_confirmed: gross=100, fee=0 -> apenas Movement INFLOW + Entry RECEITA
- [ ] Falha no segundo Movement -> rollback completo (INFLOW nao persiste)
- [ ] POST /financial/manual-adjustment sem reason -> 422
- [ ] POST /financial/manual-adjustment -> record_sensitive_action gravado
- [ ] Tenant sem TenantFeeRoutingPolicy para fee_source -> fallback tenant_share=100%
- [ ] Tenant cruzado: GET /financial/accounts nao retorna contas de outro tenant

---

## Sprint 7 — Financial Core: Transfer, Reconciliacao, CashCount

**Objetivo:** Transfer atomico (2 Movements, sem Entry), movement_reconciliations
para rastreabilidade, CashCount com ajuste automatico via FinancialCoreEngine.

**Criterio de conclusao:** Transfer COMPLETED cria exatamente 2 Movements; falha no 2o
Movement faz rollback do 1o; CashCount com ADJUSTED gera Movement OUTFLOW/INFLOW + Entry AJUSTE;
mark_movement_reconciled vincula via tabela separada sem alterar Movement.

### Migrations Sprint 7

**`p1q2r3s4t5u6_add_transfers`**
```sql
CREATE TABLE transfers (
    transfer_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    from_account_id     UUID NOT NULL REFERENCES accounts(account_id),
    to_account_id       UUID NOT NULL REFERENCES accounts(account_id),
    amount              NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    status              VARCHAR NOT NULL DEFAULT 'REQUESTED',
    -- REQUESTED | COMPLETED | FAILED
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    failed_at           TIMESTAMPTZ,
    failure_reason      VARCHAR,
    notes               TEXT
);
CREATE POLICY tenant_isolation ON transfers
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE transfers ENABLE ROW LEVEL SECURITY;
```

**`q1r2s3t4u5v6_add_reconciliation_records`**
```sql
CREATE TABLE reconciliation_records (
    reconciliation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    account_id          UUID NOT NULL REFERENCES accounts(account_id),
    status              VARCHAR NOT NULL DEFAULT 'OPEN',
    -- OPEN | CLOSED
    opened_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at           TIMESTAMPTZ,
    opened_by           UUID NOT NULL REFERENCES users(id),
    closed_by           UUID REFERENCES users(id),
    notes               TEXT
);
CREATE POLICY tenant_isolation ON reconciliation_records
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE reconciliation_records ENABLE ROW LEVEL SECURITY;
```

**`r1s2t3u4v5w6_add_movement_reconciliations`**
```sql
-- Opção A: Movement 100% append-only; reconciliacao via tabela de vinculo
CREATE TABLE movement_reconciliations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    -- desnormalizado para RLS sem JOIN
    movement_id         UUID NOT NULL REFERENCES movements(movement_id),
    reconciliation_id   UUID NOT NULL REFERENCES reconciliation_records(reconciliation_id),
    reconciled_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    reconciled_by       UUID NOT NULL REFERENCES users(id),
    UNIQUE(movement_id, reconciliation_id)
);
CREATE POLICY tenant_isolation ON movement_reconciliations
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE movement_reconciliations ENABLE ROW LEVEL SECURITY;
```

**`s1t2u3v4w5x6_add_cash_counts`**
```sql
CREATE TABLE cash_counts (
    cash_count_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    account_id          UUID NOT NULL REFERENCES accounts(account_id),
    expected_amount     NUMERIC(15,2) NOT NULL,
    counted_amount      NUMERIC(15,2) NOT NULL,
    discrepancy         NUMERIC(15,2) NOT NULL,
    -- computado: counted_amount - expected_amount
    resolution          VARCHAR NOT NULL,
    -- ADJUSTED | NO_ADJUSTMENT
    notes               TEXT,
    -- obrigatorio quando discrepancy != 0 (422 na service layer)
    entry_id            UUID REFERENCES entries(entry_id),
    -- vinculo com Entry AJUSTE se ADJUSTED
    created_by          UUID NOT NULL REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON cash_counts
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE cash_counts ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 7

**transfer_service.py**
```python
def create_transfer(
    from_account_id, to_account_id, amount, notes,
    actor_id, company_id, db
) -> Transfer:
    """
    Unica transacao de banco:
      INSERT Transfer (REQUESTED)
      _record_movement(TRANSFER_OUT, from_account)
      _record_movement(TRANSFER_IN, to_account)
      Transfer.status = COMPLETED
    Sem Entry — Transfer e movimentacao, nao fato economico.
    Falha em qualquer passo -> rollback completo.
    Emite financial_core.transfer_completed via EventBus (best-effort, fora da tx).
    """
```

**reconciliation_service.py**
```python
def open_reconciliation(account_id, notes, actor_id, company_id, db) -> ReconciliationRecord
def close_reconciliation(reconciliation_id, actor_id, company_id, db)
def mark_movement_reconciled(movement_id, reconciliation_id, actor_id, company_id, db)
    # INSERT INTO movement_reconciliations — Movement nao e alterado
def list_unreconciled_movements(account_id, company_id, db) -> list[Movement]
    # LEFT JOIN movement_reconciliations WHERE mr.id IS NULL
```

**cash_count_service.py**
```python
def record_count(
    account_id, counted_amount, resolution, notes,
    actor_id, company_id, db
) -> CashCount:
    """
    discrepancy = counted_amount - expected_amount (compute_balance)
    Se resolution=ADJUSTED e discrepancy != 0:
      notes obrigatorio (422 se ausente)
      direction = ADDS se discrepancy > 0, SUBTRACTS se < 0
      movement, entry = FinancialCoreEngine.create_manual_adjustment(
          amount=abs(discrepancy), direction=direction,
          category=CONTAGEM_CAIXA, account_id=account_id,
          reason=notes, actor_id=actor_id
      )
      cash_count.entry_id = entry.entry_id
    Emite cash_count.recorded e (se ADJUSTED) cash_count.adjustment_created.
    """
```

**Endpoints adicionais Sprint 7:**
```
POST  /financial/transfers
GET   /financial/transfers              OWNER/ADMIN
POST  /financial/reconciliation         OWNER/ADMIN
PUT   /financial/reconciliation/{id}/close
GET   /financial/movements/unreconciled?account_id=
POST  /financial/movements/{id}/reconcile
GET   /financial/cash-counts
POST  /financial/cash-counts            OWNER/ADMIN/OPERATOR
```

### Frontend Sprint 7
Nenhuma.

### Testes Sprint 7
- [ ] create_transfer -> exatamente 2 Movements (OUTFLOW + INFLOW) na mesma transacao
- [ ] create_transfer nao cria nenhuma Entry
- [ ] Falha simulada no 2o _record_movement -> rollback do 1o (TRANSFER_OUT nao persiste)
- [ ] mark_movement_reconciled -> row em movement_reconciliations; Movement inalterado
- [ ] list_unreconciled_movements exclui movements ja vinculados
- [ ] CashCount ADJUSTED com discrepancy > 0 -> Movement INFLOW + Entry AJUSTE ADDS
- [ ] CashCount ADJUSTED com discrepancy < 0 -> Movement OUTFLOW + Entry AJUSTE SUBTRACTS
- [ ] CashCount ADJUSTED, discrepancy != 0, notes ausente -> 422
- [ ] CashCount NO_ADJUSTMENT -> sem Movement, sem Entry
- [ ] CashCount.entry_id aponta para Entry AJUSTE criada

---

## Sprint 8 — Asaas: adapter, subcontas, PaymentSource, PII

**Objetivo:** Conexão com Asaas via IntegrationCredential existente, subconta no
onboarding, NullProvider para testes, PaymentSources (metodos salvos apenas),
CPF/CNPJ como PII criptografado.

**Criterio de conclusao:** NullProvider passa em 100% dos testes do modulo sem chamar
Asaas real; CPF/CNPJ de profissional nunca plaintext no banco ou nos logs;
webhook de ativacao de subconta atualiza external_account_status.

**Principio PII:**
```
CPF/CNPJ e PII sensivel. Nao armazenar plaintext.
  cpf_cnpj_encrypted  — Fernet(PII_ENCRYPTION_KEY, normalized_value)
  cpf_cnpj_hash       — HMAC-SHA256(normalized_value, PII_HASH_KEY)
  cpf_cnpj_masked     — "***.***.***-12" / "**.***.***/****-34"

Decrypt permitido apenas:
  - AsaasAdapter ao enviar para API do provider
  - Comando explicitamente auditado (ex: export PII sob OWNER + motivo)

Logs e UI sempre usam masked.
```

### Migrations Sprint 8

**`t1u2v3w4x5y6_add_company_payment_columns`**
```sql
ALTER TABLE companies ADD COLUMN IF NOT EXISTS payment_provider VARCHAR;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS external_account_id VARCHAR;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS external_account_status VARCHAR;
-- pending_verification | active | suspended
ALTER TABLE companies ADD COLUMN IF NOT EXISTS external_account_created_at TIMESTAMPTZ;
```

**`u1v2w3x4y5z6_add_professional_pii_fields`**
```sql
ALTER TABLE professionals ADD COLUMN IF NOT EXISTS cpf_cnpj_encrypted TEXT;
ALTER TABLE professionals ADD COLUMN IF NOT EXISTS cpf_cnpj_hash TEXT;
ALTER TABLE professionals ADD COLUMN IF NOT EXISTS cpf_cnpj_masked VARCHAR(18);
ALTER TABLE professionals ADD COLUMN IF NOT EXISTS external_wallet_id VARCHAR;
-- Unicidade por hash (deduplicacao sem plaintext)
CREATE UNIQUE INDEX uq_professional_cpf_cnpj_hash
    ON professionals(company_id, cpf_cnpj_hash)
    WHERE cpf_cnpj_hash IS NOT NULL;
```

**`v1w2x3y4z5a6_add_payment_sources`**
```sql
-- payment_sources = apenas metodos salvos/tokenizados do cliente (cartao, etc.)
-- payment.payment_method (Sprint 9) registra o metodo usado em cada pagamento
CREATE TABLE payment_sources (
    source_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    customer_id         UUID NOT NULL REFERENCES customers(id),
    type                VARCHAR NOT NULL,
    -- CARD_CREDIT | CARD_DEBIT
    -- (PIX/BOLETO/CASH nao sao metodos salvos; usam payment_method no pagamento)
    provider            VARCHAR NOT NULL,
    external_token      TEXT NOT NULL,  -- token do provider; NOT NULL valido aqui
    last4               VARCHAR(4),
    brand               VARCHAR,
    is_active           BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE POLICY tenant_isolation ON payment_sources
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE payment_sources ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 8

**`app/modules/payments/providers/base.py`** — PaymentProvider (ABC)
```python
class PaymentProvider(ABC):
    @abstractmethod
    def create_subaccount(self, name: str, cpf_cnpj: str, email: str) -> dict
    @abstractmethod
    def create_charge(self, amount, customer, payment_method, **kwargs) -> dict
    @abstractmethod
    def handle_webhook(self, payload: dict) -> dict
    @abstractmethod
    def refund(self, external_charge_id: str, reason: str) -> dict
    @abstractmethod
    def get_status(self, external_charge_id: str) -> str
```

**`app/modules/payments/providers/asaas.py`** — AsaasProvider
Usa IntegrationCredential do tenant (provider=ASAAS) para obter API key via decrypt_secret.
Fallback para settings.ASAAS_API_KEY se tenant nao tem credential.
Decrypt de cpf_cnpj_encrypted (via PII_ENCRYPTION_KEY) antes de enviar para Asaas.

**`app/modules/payments/providers/null_provider.py`** — NullProvider
```python
class NullProvider(PaymentProvider):
    def __init__(self, outcome: str = "success"):
        self.outcome = outcome
        self.calls: list[dict] = []

    def create_subaccount(self, *args, **kwargs) -> dict:
        self.calls.append({"method": "create_subaccount", "args": args})
        if self.outcome == "error":
            raise AsaasError("null_provider_error")
        return {"accountId": f"null_{uuid4().hex[:8]}", "status": "pending_verification"}
    # ... demais metodos
```

**`app/modules/payments/validators.py`**
```python
def normalize_cpf_cnpj(raw: str) -> str:
    """Remove pontuacao, valida digito verificador. Raise ValueError se invalido."""

def validate_cpf(digits: str) -> bool: ...
def validate_cnpj(digits: str) -> bool: ...

def encrypt_pii(value: str) -> str:   # Fernet(PII_ENCRYPTION_KEY)
def hash_pii(value: str) -> str:      # HMAC-SHA256(value, PII_HASH_KEY)
def mask_cpf(digits: str) -> str:     # "***.***.***-12"
def mask_cnpj(digits: str) -> str:    # "**.***.***/****-34"
```

**Hook create_company** — adicionar subconta Asaas de forma nao-bloqueante:
```python
try:
    provider = get_payment_provider(company_id=company.id, db=db)
    result = provider.create_subaccount(name=company.name, cpf_cnpj=owner_cpf, email=owner.email)
    company.payment_provider = "asaas"
    company.external_account_id = result["accountId"]
    company.external_account_status = "pending_verification"
    company.external_account_created_at = datetime.now(UTC)
except Exception as e:
    # Falha nao bloqueia criacao do tenant
    logger.warning("payment_subaccount_creation_failed",
                   company_id=str(company.id), error=str(e))
```

**Webhooks:**
```
POST /payments/webhook/asaas/account_status   — publico, sem auth
```
Valida `asaas-access-token` header -> atualiza `company.external_account_status`.

**Endpoints Sprint 8:**
```
GET    /payment-sources
POST   /payment-sources               OWNER/ADMIN
DELETE /payment-sources/{id}
GET    /financial/settings            OWNER/ADMIN (status subconta, contas, config)
```

**Regra de negocio — PATCH /professionals/{id}:**
Quando cpf_cnpj presente no body:
1. normalize_cpf_cnpj(raw) -> digits
2. Verificar duplicata via hash: EXISTS(company_id, hash) excluindo o proprio profissional
3. Gravar encrypted, hash, masked (nunca plaintext)

### Frontend Sprint 8
- `/dashboard/settings/financial/page.tsx`: banner status subconta Asaas
  (pending_verification -> amarelo; active -> verde; absent -> neutro)
- `/dashboard/professionals/[id]/page.tsx`: campo "CPF/CNPJ" com validacao
  client-side (digito verificador) e exibicao masked

### Testes Sprint 8
- [ ] validate_cpf("11111111111") -> False (digito verificador invalido)
- [ ] validate_cpf(cpf_valido) -> True
- [ ] validate_cnpj(cnpj_valido) -> True
- [ ] NullProvider(outcome="success"): create_subaccount appenda em self.calls
- [ ] NullProvider(outcome="error"): create_subaccount levanta AsaasError
- [ ] Todos os metodos do PaymentProvider implementados em NullProvider
- [ ] encrypt_pii / hash_pii / mask_cpf: roundtrip correto
- [ ] PATCH /professionals/{id} com CPF valido -> encrypted, hash, masked gravados; plaintext ausente
- [ ] PATCH /professionals/{id} com CPF de outro profissional da mesma empresa -> 409
- [ ] Webhook account_status -> company.external_account_status = "active"
- [ ] create_company com Asaas indisponivel (NullProvider outcome=error) -> company criada, external_account_status NULL
- [ ] Logs de operacoes com CPF: assertar que plaintext ausente nos registros

---

## Sprint 9 — PaymentsEngine: FSM, webhook idempotente, DepositPolicy

**Objetivo:** Engine de pagamentos com lifecycle FSM, webhook idempotente via
ProcessedIdempotencyKey na mesma transacao, integracao com FinancialCoreEngine
em payment.confirmed e payment.refunded, DepositPolicy configuravel.

**Criterio de conclusao:** Pix gerado via NullProvider e confirmado via webhook;
replay do mesmo webhook nao cria duplicata de PaymentTransaction; payment.confirmed
gera Movement INFLOW + Entry RECEITA (+ TAXA se fee>0); Payment.provider imutavel
por trigger; atomicidade de confirm() explicitada e testada.

### Migrations Sprint 9

**`w1x2y3z4a5b6_add_payments`**
```sql
CREATE TABLE payments (
    payment_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id              UUID NOT NULL REFERENCES companies(id),
    customer_id             UUID REFERENCES customers(id),
    appointment_id          UUID REFERENCES appointments(id),
    currency                CHAR(3) NOT NULL DEFAULT 'BRL',

    -- Valores
    gross_catalog_amount    NUMERIC(15,2) NOT NULL,
    discount_amount         NUMERIC(15,2) NOT NULL DEFAULT 0,
    net_charged_amount      NUMERIC(15,2) NOT NULL,
    provider_fee            NUMERIC(15,2) NOT NULL DEFAULT 0,

    -- Metodo de pagamento (separado de payment_source)
    payment_method          VARCHAR NOT NULL,
    -- CASH | PIX | BOLETO | CARD_CREDIT | CARD_DEBIT | MAQUININHA
    payment_source_id       UUID REFERENCES payment_sources(source_id),
    -- nulo para CASH/PIX/BOLETO; preenchido para cartao salvo

    -- Provider
    provider                VARCHAR NOT NULL,  -- imutavel apos criacao
    target_account_id       UUID NOT NULL REFERENCES accounts(account_id),
    external_charge_id      VARCHAR,

    -- Status FSM
    status                  VARCHAR NOT NULL DEFAULT 'PENDING',
    -- PENDING | CONFIRMED | FAILED | CANCELLED | REFUNDED
    manual_override_count   INTEGER NOT NULL DEFAULT 0,

    -- Timestamps
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at                 TIMESTAMPTZ,
    refunded_at             TIMESTAMPTZ
);

-- provider imutavel: trigger BEFORE UPDATE
CREATE OR REPLACE FUNCTION prevent_payment_provider_change()
RETURNS trigger AS $$
BEGIN
    IF OLD.provider IS DISTINCT FROM NEW.provider THEN
        RAISE EXCEPTION 'Payment.provider e imutavel apos criacao';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER payment_provider_immutable
    BEFORE UPDATE OF provider ON payments FOR EACH ROW
    EXECUTE FUNCTION prevent_payment_provider_change();

CREATE POLICY tenant_isolation ON payments
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
```

**`x1y2z3a4b5c6_add_payment_transactions`**
```sql
CREATE TABLE payment_transactions (
    transaction_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id              UUID NOT NULL REFERENCES payments(payment_id),
    company_id              UUID NOT NULL REFERENCES companies(id),
    provider_transaction_id VARCHAR NOT NULL,
    amount                  NUMERIC(15,2) NOT NULL,
    status                  VARCHAR NOT NULL,
    raw_response            JSONB NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Unicidade por provider: idempotencia no banco, nao so no codigo
    UNIQUE(company_id, provider_transaction_id)
);
CREATE POLICY tenant_isolation ON payment_transactions
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE payment_transactions ENABLE ROW LEVEL SECURITY;
```

**`y1z2a3b4c5d6_add_deposit_policies`**
```sql
CREATE TABLE deposit_policies (
    policy_id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id                      UUID NOT NULL REFERENCES companies(id),
    service_id                      UUID REFERENCES services(id),
    -- NULL = politica global do tenant
    deposit_type                    VARCHAR NOT NULL,
    -- FIXED_AMOUNT | PERCENTAGE
    deposit_value                   NUMERIC(10,2) NOT NULL,
    refundable_until_hours_before   INTEGER NOT NULL DEFAULT 24,
    refund_on_tenant_fault          BOOLEAN NOT NULL DEFAULT true,
    retain_on_no_show               BOOLEAN NOT NULL DEFAULT true,
    commission_on_retained_deposit  BOOLEAN NOT NULL DEFAULT false,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                      TIMESTAMPTZ
);
CREATE POLICY tenant_isolation ON deposit_policies
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE deposit_policies ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 9

**`app/modules/payments/service.py`** — PaymentsEngine

```python
def create_payment(
    company_id, customer_id, gross_amount, payment_method,
    provider, target_account_id, appointment_id=None,
    payment_source_id=None, db=None
) -> Payment

def confirm(payment_id: UUID, event_id: str, webhook_data: dict,
            company_id: UUID, db) -> Payment:
    """
    ATOMICIDADE CRITICA: tudo na mesma transacao de banco.

    BEGIN TRANSACTION
      1. Checar ProcessedIdempotencyKey(key=event_id, consumer="payment_confirmed")
         -> Se ja existe: return payment atual sem reprocessar
      2. INSERT PaymentTransaction (provider_transaction_id=event_id, raw_response)
         -> Se UNIQUE(company_id, provider_transaction_id) falhar: ja processado
      3. UPDATE payments SET status='CONFIRMED', paid_at=now()
      4. FinancialCoreEngine.handle_payment_confirmed(
             gross_amount, provider_fee, target_account_id, fee_source, company_id
         )  <- Movements + Entries criados nesta mesma tx
      5. INSERT ProcessedIdempotencyKey(key=event_id, consumer="payment_confirmed")
    COMMIT

    Apos commit (fora da transacao):
      EventBus.publish("payment.confirmed", payment_id=...)
      -> Handler separado dispara CommunicationService (best-effort, nao bloqueia)
    """

def refund(payment_id, reason: RefundReason, actor_id, company_id, db) -> Payment:
    """
    RefundReason: SERVICE_FAILURE | REGISTRATION_ERROR | DEADLINE_POLICY | OTHER
    -> FinancialCoreEngine: Movement OUTFLOW + Entry ESTORNO (mesma transacao)
    -> record_sensitive_action(action="refund_payment", reason=reason)
    -> EventBus.publish("payment.refunded") apos commit
    """
```

**EventBus handler — comunicacao:**
```python
# app/modules/communication/handlers.py
# Registrado no startup, fora da transacao de pagamento
@event_bus.on("payment.confirmed")
def handle_payment_confirmed_notification(payment_id, **kwargs):
    """Best-effort — falha nao impacta o pagamento confirmado."""
    communication_service.send_transactional(
        event_type="payment.confirmed",
        recipient_id=payment.customer_id,
        context={"amount": payment.net_charged_amount}
    )
```

**Webhook idempotente:**
```
POST /payments/webhook/asaas/transaction  — publico, sem auth
```
```python
idempotency_key = f"asaas_webhook:{payload['id']}"
# Atomicidade cuidada dentro de confirm()
payment_service.confirm(
    payment_id=..., event_id=payload['id'],
    webhook_data=payload, company_id=..., db=db
)
```

**Endpoints Sprint 9:**
```
POST  /payments
GET   /payments                     OWNER/ADMIN
GET   /payments/{id}
POST  /payments/{id}/refund         OWNER/ADMIN + reason enum
POST  /payments/webhook/asaas/transaction   — publico
GET   /deposit-policies             OWNER/ADMIN
POST  /deposit-policies             OWNER/ADMIN
PUT   /deposit-policies/{id}        OWNER/ADMIN
```

### Frontend Sprint 9
- `/dashboard/payments/page.tsx`: lista com status badges + filtro por periodo
- `/dashboard/payments/[id]/page.tsx`: detalhe + botao "Reembolsar" com dropdown de motivo
- Componente `<PixQrCodeDisplay>` se BookingFlow precisar de QR no checkout

### Testes Sprint 9
- [ ] confirm() com mesmo event_id duas vezes: 2a chamada retorna payment sem criar nova PaymentTransaction
- [ ] UNIQUE(company_id, provider_transaction_id) rejeita duplicata no banco
- [ ] payment.confirmed: gross=100, fee=2 -> Movement INFLOW 100 + Entry RECEITA + Movement OUTFLOW 2 + Entry TAXA
- [ ] confirm() com falha em handle_payment_confirmed -> rollback completo (sem PaymentTransaction, status=PENDING)
- [ ] ProcessedIdempotencyKey inserida na mesma transacao de confirm()
- [ ] Payment.provider imutavel: UPDATE -> erro do trigger
- [ ] refund() -> Movement OUTFLOW + Entry ESTORNO + record_sensitive_action
- [ ] EventBus.publish("payment.confirmed") chamado apos commit, nao dentro da transacao
- [ ] Comunicacao falha em handler -> payment ainda CONFIRMED (best-effort isolado)
- [ ] payment_source_id=None para PIX (campo nullable correto)
- [ ] Cross-tenant: GET /payments nao retorna pagamentos de outro tenant

---

## Sprint 10 — Operations FSM + Agenda granular

**Objetivo:** FSM completa de Operacoes, Reservation com lifecycle atomico
(SOFT -> FIRME), EXCLUDE bloqueando concorrencia via status='ACTIVE',
DirectOccupancy e handler agenda.soft_reservation.expired.

**Criterio de conclusao:** 2 clientes tentando reservar o mesmo slot:
o 2o recebe conflito pelo EXCLUDE; promocao SOFT->FIRME atomica;
handler registered e testado para expiração de SOFT.

**Nota migratoria:** `appointmentstatus` esta em producao. Adicionar valores
via `ADD VALUE IF NOT EXISTS` (nao recriar o tipo).
`SCHEDULED` permanece no banco por compatibilidade; alias `REQUESTED` no ORM.

### Migrations Sprint 10

**`z1a2b3c4d5e6_extend_appointments_for_operations`**
```sql
ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS 'DRAFT';
ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS 'FAILED';
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS
    operation_type VARCHAR NOT NULL DEFAULT 'SERVICE_SCHEDULED';
-- SERVICE_SCHEDULED | SERVICE_DIRECT | PRODUCT_SALE
```

**`a2b3c4d5e6f7_add_schedule_exceptions`**
```sql
CREATE TABLE schedule_exceptions (
    exception_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    professional_id     UUID NOT NULL REFERENCES professionals(id),
    exception_date      DATE NOT NULL,
    type                VARCHAR NOT NULL,
    -- SUBSTITUTIVE (substitui horario padrao) | ADDITIVE (adiciona horario extra)
    start_time          TIME,    -- NULL = dia todo de folga (apenas SUBSTITUTIVE)
    end_time            TIME,
    reason              VARCHAR,
    UNIQUE(professional_id, exception_date, type)
);
CREATE POLICY tenant_isolation ON schedule_exceptions
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE schedule_exceptions ENABLE ROW LEVEL SECURITY;
```

**`b2c3d4e5f6g7_add_reservations`**
```sql
CREATE TABLE reservations (
    reservation_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    professional_id     UUID NOT NULL REFERENCES professionals(id),
    start_at            TIMESTAMPTZ NOT NULL,
    end_at              TIMESTAMPTZ NOT NULL,
    type                VARCHAR NOT NULL,
    -- SOFT | FIRME  (natureza; imutavel apos criacao)
    status              VARCHAR NOT NULL DEFAULT 'ACTIVE',
    -- ACTIVE | EXPIRED | CANCELLED | PROMOTED | RELEASED | CONSUMED | NO_SHOW
    appointment_id      UUID REFERENCES appointments(id),
    expires_at          TIMESTAMPTZ,    -- apenas SOFT; NULL = sem TTL
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- EXCLUDE cobre SOFT e FIRME enquanto status=ACTIVE
-- Quando SOFT expira: status -> EXPIRED -> sai da constraint
-- Quando SOFT vira FIRME: atômico (ver promote_to_firme)
ALTER TABLE reservations ADD CONSTRAINT no_overlap_active
    EXCLUDE USING gist (
        company_id WITH =,
        professional_id WITH =,
        tstzrange(start_at, end_at, '[)') WITH &&
    ) WHERE (status = 'ACTIVE');

CREATE POLICY tenant_isolation ON reservations
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE reservations ENABLE ROW LEVEL SECURITY;
```

**`c2d3e4f5g6h7_add_direct_occupancies`**
```sql
CREATE TABLE direct_occupancies (
    occupancy_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    professional_id     UUID NOT NULL REFERENCES professionals(id),
    start_at            TIMESTAMPTZ NOT NULL,
    end_at              TIMESTAMPTZ NOT NULL,
    appointment_id      UUID REFERENCES appointments(id),
    reason              VARCHAR NOT NULL,
    opened_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at           TIMESTAMPTZ,
    opened_by           UUID NOT NULL REFERENCES users(id)
);
CREATE POLICY tenant_isolation ON direct_occupancies
    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
ALTER TABLE direct_occupancies ENABLE ROW LEVEL SECURITY;
```

### Backend Sprint 10

**`app/modules/agenda/reservation_service.py`**

```python
def create_soft_reservation(
    professional_id, start_at, end_at, ttl_minutes,
    company_id, db
) -> Reservation:
    """
    INSERT Reservation(type=SOFT, status=ACTIVE, expires_at=now()+ttl).
    Se EXCLUDE viola: raise SlotUnavailableError (HTTP 409).
    ttl_minutes de TenantConfig.soft_reservation_ttl_min (default 15).
    """

def promote_to_firme(reservation_id, appointment_id, company_id, db) -> Reservation:
    """
    ATOMICO — unica transacao:
      BEGIN
        soft.status = 'PROMOTED'   # sai do EXCLUDE
        db.flush()                 # constraint liberada antes do INSERT
        INSERT Reservation(type=FIRME, status=ACTIVE,
                           same slot, appointment_id=appointment_id)
      COMMIT
    Falha no INSERT FIRME -> rollback; SOFT volta a ACTIVE.
    """

def release_reservation(reservation_id, company_id, db):
    """status = RELEASED"""

def expire_soft_reservation(reservation_id, company_id, db):
    """status = EXPIRED; emite agenda.soft_reservation.expired via Celery"""

def create_firme_direct(professional_id, start_at, end_at, appointment_id, company_id, db):
    """Walk-in: INSERT FIRME direto sem SOFT intermediaria."""

def open_direct_occupancy(professional_id, start_at, end_at, reason, actor_id, company_id, db)
def close_direct_occupancy(occupancy_id, company_id, db)
```

**Handler `agenda.soft_reservation.expired`** — primeiro registro deste handler:
```python
# app/workers/handlers/soft_reservation_handler.py
@event_bus.on("agenda.soft_reservation.expired")
def handle_soft_reservation_expired(reservation_id, company_id, **kwargs):
    """
    Se appointment vinculado em DRAFT ou REQUESTED:
      appointment.status = CANCELLED
    Emite appointment.cancelled best-effort.
    """
```

**Celery Beat task** — scan periodico de SOFT expiradas:
```python
# Separado do booking_session_worker existente
@celery.task
def expire_soft_reservations():
    expired = db.query(Reservation).filter(
        Reservation.type == 'SOFT',
        Reservation.status == 'ACTIVE',
        Reservation.expires_at < datetime.now(UTC)
    ).all()
    for r in expired:
        reservation_service.expire_soft_reservation(r.reservation_id, r.company_id, db)
```

**TTLs de TenantConfig (ja existem):**
```
soft_reservation_ttl_min   default 15
draft_expiration_min       default 60
requested_expiration_h     default 24
no_show_threshold_min      default 30
```

**Overbooking manual:** apenas OWNER/ADMIN; reason obrigatorio; record_sensitive_action.

**Endpoints Sprint 10:**
```
POST  /agenda/soft-reservation
POST  /agenda/soft-reservation/{id}/promote
POST  /agenda/soft-reservation/{id}/release
POST  /agenda/firme-direct              OWNER/ADMIN/OPERATOR
POST  /agenda/direct-occupancy          OWNER/ADMIN/OPERATOR
PUT   /agenda/direct-occupancy/{id}/close
GET   /schedule/exceptions/{professional_id}
POST  /schedule/exceptions
DELETE /schedule/exceptions/{id}
```

### Frontend Sprint 10
- Atualizar `/dashboard/appointments/`: aceitar DRAFT e FAILED no enum de status
- `/dashboard/appointments/new/`: botao "Ocupacao direta" para OWNER/ADMIN/OPERATOR
- Cronometro TTL no BookingFlow se soft_reservation.expires_at retornado pela API

### Testes Sprint 10
- [ ] 2 create_soft_reservation simultaneos no mesmo slot: 2o levanta SlotUnavailableError
- [ ] promote_to_firme: SOFT.status=PROMOTED + INSERT FIRME ACTIVE (atomico)
- [ ] promote_to_firme: falha no INSERT FIRME -> SOFT ainda ACTIVE (rollback)
- [ ] SOFT expirada (status=EXPIRED): create_soft_reservation no mesmo slot -> sucesso
- [ ] expire_soft_reservations task: SOFT com expires_at no passado -> status=EXPIRED
- [ ] handler agenda.soft_reservation.expired: appointment em DRAFT -> CANCELLED
- [ ] handler agenda.soft_reservation.expired: reservation ja EXPIRED -> idempotente (sem erro)
- [ ] Overbooking forçado sem reason -> 422
- [ ] Overbooking forcado com reason -> record_sensitive_action gravado
- [ ] tstzrange: criar reserva com timezone aware start_at/end_at -> sem erro de tipo

---

## Criterios de conclusao da Fase 2

```
pytest -v tests/test_sprint6_financial_core.py
  OK Movement imutavel (UPDATE/DELETE por trigger de banco)
  OK Entry imutavel
  OK compute_balance correto
  OK handle_payment_confirmed: Movement INFLOW + Entry RECEITA atomicos
  OK handle_payment_confirmed com fee: + OUTFLOW + TAXA
  OK Falha no 2o Movement -> rollback completo
  OK create_company: Account CAIXA + 7 TenantFeeRoutingPolicies
  OK fee_routing_policy_id removido de tenant_configs
  OK PUT /tenant/fee-routing soma != 100 -> 422
  OK manual-adjustment sem reason -> 422
  OK Cross-tenant: accounts isoladas

pytest -v tests/test_sprint7_transfer_reconciliation.py
  OK Transfer: 2 Movements OUTFLOW+INFLOW atomicos; sem Entry
  OK Falha no 2o Movement -> rollback do 1o
  OK movement_reconciliations: Movement nao alterado
  OK CashCount ADJUSTED: Movement + Entry AJUSTE
  OK CashCount notes ausente com discrepancy != 0 -> 422

pytest -v tests/test_sprint8_asaas_pii.py
  OK validate_cpf("11111111111") -> False
  OK CPF valido -> True; CNPJ valido -> True
  OK NullProvider: todos os metodos registrados em self.calls
  OK CPF gravado como encrypted+hash+masked; plaintext ausente
  OK Duplicata CPF por hash -> 409
  OK Webhook ativacao -> external_account_status = "active"
  OK create_company com Asaas indisponivel -> company criada
  OK Logs sem plaintext CPF/CNPJ

pytest -v tests/test_sprint9_payments.py
  OK confirm() com mesmo event_id 2x -> 1 PaymentTransaction
  OK UNIQUE(company_id, provider_transaction_id) rejeita no banco
  OK confirm() atomico: falha em handle_payment_confirmed -> rollback total
  OK payment.confirmed -> CommunicationService via EventBus, fora da tx
  OK Payment.provider imutavel pelo trigger
  OK refund() -> Movement OUTFLOW + Entry ESTORNO + audit
  OK Cross-tenant: payments isolados

pytest -v tests/test_sprint10_operations.py
  OK 2 SOFT simultaneas -> 2a levanta SlotUnavailableError (EXCLUDE)
  OK promote_to_firme atomico (SOFT PROMOTED + FIRME ACTIVE)
  OK promote_to_firme: falha FIRME -> SOFT volta ACTIVE
  OK SOFT expirada -> status EXPIRED -> slot liberado
  OK handler agenda.soft_reservation.expired registrado e idempotente
  OK tstzrange sem erro de tipo com TIMESTAMPTZ

Estado de saida — contratos estaveis para Fase 3:
  OK Financial Core: Account, Movement (append-only), Entry (append-only),
     Transfer, ReconciliationRecord, movement_reconciliations, CashCount
  OK TenantFeeRoutingPolicy: chave natural (company_id+fee_source); sem FK em tenant_configs
  OK FinancialCoreEngine: handlers privados + queries publicas + manual_adjustment
  OK PaymentsEngine: PENDING->CONFIRMED->REFUNDED; webhook idempotente; atomicidade explicita
  OK AsaasProvider + NullProvider; CPF/CNPJ encrypted+hash+masked
  OK DepositPolicy configuravel
  OK Reservations SOFT/FIRME: EXCLUDE por status=ACTIVE; promocao atomica
  OK Operations FSM: DRAFT/REQUESTED/CONFIRMED/IN_PROGRESS/COMPLETED/CANCELLED/NO_SHOW/FAILED
  OK handler agenda.soft_reservation.expired registrado
  OK PII_ENCRYPTION_KEY + PII_HASH_KEY em producao
```

---

## Restricoes desta fase

- NAO criar CommissionEngine — Fase 3 (Sprint 12)
- NAO criar handle_expense_paid — Fase 3 (Sprint 18)
- NAO criar handle_commission_paid — Fase 3 (Sprint 12)
- NAO criar CustomerCredit — Fase 3 (Sprint 13)
- NAO criar Package, Subscription — Fases 3/4
- NAO criar Promotion, Coupon — Fase 4 (Sprint 16)
- NAO criar Expense, Supplier, Payable — Fase 3 (Sprint 17/18)
- NAO criar Stock — Fase 3 (Sprint 17)
- NAO ativar accounting_mode=ACCRUAL — trigger de banco bloqueia
- NAO expor _record_movement ou _record_entry como endpoints
- NAO armazenar CPF/CNPJ como plaintext
- NAO chamar CommunicationService dentro da transacao de confirm()

---

## Notas para fases seguintes

- **Fase 3 / Sprint 11:** Catalogo opt-ins — ServicePricingOverride, ServiceVariant,
  preparation_minutes_before/after.

- **Fase 3 / Sprint 12:** CommissionEngine. Adicionar handle_commission_paid ao
  FinancialCoreEngine. Dois eixos: commission_base x commission_fee_policy.
  Lifecycle CALCULATED -> DUE -> PAID.

- **Fase 3 / Sprint 13:** CustomerCredit como cota de direito de uso (nao saldo).
  FEFO, lifecycle ACTIVE/EXHAUSTED/EXPIRED/REVOKED.

- **Fase 3 / Sprint 17:** Estoque, Fornecedores, Payables, PayableInstallment.
  Adicionar handle_expense_paid ao FinancialCoreEngine.

- **Fase 3 / Sprint 18:** Despesas — lifecycle PENDENTE -> PAGA, recorrencia,
  worker expense.due_soon.

- **Fase 5 / Sprint 19:** Gestao Financeira UI — DRE, reconciliacao visual, CashCount UI.

- **Dívida business_hours estruturado:** CompanyProfile.business_hours e string livre.
  Para filtro visual de dias fechados no BookingFlow, adicionar
  business_hours_structured JSONB em company_profiles. Hotfix ou Sprint 11.

- **Dependencia Sprint 9 x Sprint 10:** Sprint 9 implementa PaymentsEngine sem
  fluxo DEPOSIT completo. Fluxo sinal (SOFT promovido por payment.confirmed)
  e validado no Sprint 10 ou sprint de integracao dedicado.

- **Separacao de chaves PII:** Se PII_ENCRYPTION_KEY = CREDENTIAL_ENCRYPTION_KEY
  no inicio, planejar migracao de chaves antes do Estagio 1 (mais tenants).

---

*v2 — gerado apos review estrutural em 2026-05-30.
Todos os 6 bloqueadores e problemas importantes endereçados.
Fonte canonica de comportamento: visao-produto-paladino.md v23.0.*
