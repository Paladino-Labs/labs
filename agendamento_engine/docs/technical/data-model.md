# Modelo de Dados — Paladino

Todas as entidades do sistema com campos, tipos e constraints.
Organizado por domínio. Total: 42 modelos (33 Fase 1 + 9 Fase 2 novos).

---

## Tenant e Configuração

### Company
```
id                          UUID PK DEFAULT gen_random_uuid()
slug                        VARCHAR UNIQUE NOT NULL
name                        VARCHAR NOT NULL
phone                       VARCHAR nullable
timezone                    VARCHAR DEFAULT 'America/Sao_Paulo'
payment_provider            VARCHAR nullable         # ex: "asaas"
external_account_id         VARCHAR nullable         # ID subconta Asaas
external_account_status     VARCHAR nullable         # pending_verification | active | suspended
external_account_created_at TIMESTAMPTZ nullable
created_at                  TIMESTAMPTZ DEFAULT now()
updated_at                  TIMESTAMPTZ
```

### CompanySettings
```
company_id              UUID PK FK → companies
online_booking_enabled  BOOLEAN DEFAULT false
```

### CompanyProfile
```
company_id      UUID PK FK → companies
bio             TEXT nullable
business_hours  TEXT nullable           # string livre (dívida: estruturar)
social_media    JSONB nullable          # {instagram, facebook, tiktok, website}
gallery_urls    JSONB nullable          # list[str]
logo_url        VARCHAR nullable
address         VARCHAR nullable
updated_at      TIMESTAMPTZ
```

### TenantConfig
```
tenant_config_id        UUID PK
company_id              UUID FK UNIQUE NOT NULL → companies
timezone                VARCHAR DEFAULT 'America/Sao_Paulo'
soft_reservation_ttl_min    INTEGER DEFAULT 15
draft_expiration_min        INTEGER DEFAULT 60
requested_expiration_h      INTEGER DEFAULT 24
no_show_threshold_min       INTEGER DEFAULT 30
no_penalty_cancel_h         INTEGER DEFAULT 12
require_payment_upfront     BOOLEAN DEFAULT false
default_commission_pct      NUMERIC(5,2) DEFAULT 40.00
accounting_mode             VARCHAR DEFAULT 'CASH'  # CASH | ACCRUAL (trigger bloqueia ACCRUAL)
permission_overrides        JSONB DEFAULT '{}'
updated_at                  TIMESTAMPTZ
```

**Nota:** `fee_routing_policy_id` foi removido (era placeholder sem FK; substituído por TenantFeeRoutingPolicy com chave natural).

### ModuleActivation
```
activation_id       UUID PK
company_id          UUID FK NOT NULL → companies
module_name         VARCHAR NOT NULL
  -- ESTOQUE | COMISSOES | PACOTES | ASSINATURAS | PROMOCOES
  -- | CRM | NPS | FILA | BOT_WHATSAPP | LINK_PUBLICO
is_active           BOOLEAN DEFAULT false
activated_at        TIMESTAMPTZ nullable
deactivated_at      TIMESTAMPTZ nullable
activated_by_user_id UUID nullable FK → users
UNIQUE(company_id, module_name)
```

### TenantBranding
```
company_id      UUID PK FK → companies
logo_url        VARCHAR nullable
primary_color   VARCHAR nullable
secondary_color VARCHAR nullable
font_family     VARCHAR nullable
favicon_url     VARCHAR nullable
custom_texts    JSONB DEFAULT '{}'
updated_at      TIMESTAMPTZ
```

### Category
```
category_id     UUID PK
company_id      UUID nullable FK → companies  # NULL = categoria global
name            VARCHAR NOT NULL
entity_type     VARCHAR NOT NULL     # SERVICE | PRODUCT | EXPENSE
is_default      BOOLEAN DEFAULT false
sort_order      INTEGER DEFAULT 0
active          BOOLEAN DEFAULT true
created_at      TIMESTAMPTZ DEFAULT now()
```

---

## Usuários e Autenticação

### User
```
id                      UUID PK DEFAULT gen_random_uuid()
company_id              UUID nullable FK → companies  # NULL para PLATFORM_*
email                   VARCHAR UNIQUE NOT NULL
password_hash           VARCHAR NOT NULL
role                    UserRole NOT NULL
active                  BOOLEAN DEFAULT true
last_password_change_at TIMESTAMPTZ nullable
created_at              TIMESTAMPTZ DEFAULT now()
updated_at              TIMESTAMPTZ
```

### UserInvitation
```
invitation_id   UUID PK
company_id      UUID FK NOT NULL → companies
email           VARCHAR NOT NULL
role            UserRole NOT NULL
token_hash      VARCHAR(255) NOT NULL UNIQUE
status          VARCHAR DEFAULT 'PENDING'  # PENDING | ACCEPTED | CANCELLED
expires_at      TIMESTAMPTZ NOT NULL       # now() + 48h
invited_by      UUID FK → users
created_at      TIMESTAMPTZ DEFAULT now()
```

### PasswordResetToken
```
token_hash  VARCHAR(255) NOT NULL UNIQUE  # SHA-256
expires_at  TIMESTAMPTZ NOT NULL
used        BOOLEAN DEFAULT false
user_id     UUID FK → users
created_at  TIMESTAMPTZ DEFAULT now()
```

### AuditLog
```
audit_id        UUID PK
company_id      UUID nullable FK → companies
actor_id        UUID FK → users
actor_role      VARCHAR NOT NULL
action          VARCHAR NOT NULL
resource_type   VARCHAR nullable
resource_id     UUID nullable
before_snapshot JSONB nullable
after_snapshot  JSONB nullable
amount          NUMERIC nullable
account_id      UUID nullable
ip_address      VARCHAR nullable
created_at      TIMESTAMPTZ DEFAULT now()
```
Append-only. Sem UPDATE ou DELETE possíveis.

---

## Operações (Clientes, Profissionais, Serviços, Produtos)

### Customer
```
id          UUID PK
company_id  UUID FK NOT NULL → companies [RLS]
name        VARCHAR NOT NULL
phone       VARCHAR NOT NULL
email       VARCHAR nullable
notes       TEXT nullable
active      BOOLEAN DEFAULT true
created_at  TIMESTAMPTZ DEFAULT now()
updated_at  TIMESTAMPTZ
UNIQUE(company_id, phone)
```

### Professional
```
id                  UUID PK
company_id          UUID FK NOT NULL → companies [RLS]
name                VARCHAR NOT NULL
specialty           VARCHAR nullable
photo_url           VARCHAR nullable
cpf_cnpj_encrypted  TEXT nullable      # Fernet(PII_ENCRYPTION_KEY)
cpf_cnpj_hash       TEXT nullable      # HMAC-SHA256(PII_HASH_KEY)
cpf_cnpj_masked     VARCHAR(18) nullable
external_wallet_id  VARCHAR nullable   # ID de carteira no Asaas
active              BOOLEAN DEFAULT true
created_at          TIMESTAMPTZ DEFAULT now()
updated_at          TIMESTAMPTZ
```
```sql
CREATE UNIQUE INDEX uq_professional_cpf_cnpj_hash
  ON professionals(company_id, cpf_cnpj_hash)
  WHERE cpf_cnpj_hash IS NOT NULL;
```

### Service
```
id              UUID PK
company_id      UUID FK NOT NULL → companies [RLS]
name            VARCHAR NOT NULL
description     TEXT nullable
price           NUMERIC(10,2) NOT NULL
duration_min    INTEGER NOT NULL
image_url       VARCHAR nullable
active          BOOLEAN DEFAULT true
created_at      TIMESTAMPTZ DEFAULT now()
updated_at      TIMESTAMPTZ
```

### ProfessionalService (join table)
```
professional_id UUID FK → professionals
service_id      UUID FK → services
company_id      UUID FK → companies [RLS]
PRIMARY KEY (professional_id, service_id)
```

### Product
```
id          UUID PK
company_id  UUID FK NOT NULL → companies [RLS]
name        VARCHAR NOT NULL
price       NUMERIC(10,2) NOT NULL
stock       INTEGER DEFAULT 0
active      BOOLEAN DEFAULT true
created_at  TIMESTAMPTZ DEFAULT now()
updated_at  TIMESTAMPTZ
```

---

## Agenda

### Appointment
```
appointment_id  UUID PK
company_id      UUID FK NOT NULL → companies [RLS]
professional_id UUID FK → professionals
customer_id     UUID FK → customers
start_at        TIMESTAMPTZ NOT NULL
end_at          TIMESTAMPTZ NOT NULL
status          AppointmentStatus DEFAULT 'REQUESTED'
financial_status VARCHAR DEFAULT 'pending'
operation_type  VARCHAR DEFAULT 'SERVICE_SCHEDULED'
idempotency_key VARCHAR UNIQUE nullable
reminder_24h_sent BOOLEAN DEFAULT false
reminder_1h_sent  BOOLEAN DEFAULT false
cancelled_at    TIMESTAMPTZ nullable
cancelled_by    UUID nullable FK → users
created_at      TIMESTAMPTZ DEFAULT now()
updated_at      TIMESTAMPTZ
```
EXCLUDE CONSTRAINT: ver [domains/agenda.md](domains/agenda.md).

### AppointmentService (snapshot)
```
id              UUID PK
appointment_id  UUID FK → appointments
company_id      UUID FK → companies [RLS]
service_id      UUID nullable FK → services  # nullable (SET NULL se service deletado)
service_name    VARCHAR NOT NULL             # snapshot
service_price   NUMERIC(10,2) NOT NULL       # snapshot
duration_min    INTEGER NOT NULL             # snapshot
```

### AppointmentStatusLog
```
log_id          UUID PK
appointment_id  UUID FK → appointments
company_id      UUID FK → companies [RLS]
from_status     VARCHAR nullable
to_status       VARCHAR NOT NULL
changed_by      UUID nullable FK → users
changed_at      TIMESTAMPTZ DEFAULT now()
reason          TEXT nullable
```

### WorkingHour
```
id              UUID PK
company_id      UUID FK → companies [RLS]
professional_id UUID FK → professionals
weekday         INTEGER NOT NULL    # 0=Segunda ... 6=Domingo
start_time      TIME NOT NULL
end_time        TIME NOT NULL
```

### ScheduleBlock
```
id              UUID PK
company_id      UUID FK → companies [RLS]
professional_id UUID FK → professionals
starts_at       TIMESTAMPTZ NOT NULL
ends_at         TIMESTAMPTZ NOT NULL
reason          VARCHAR nullable
```

### ScheduleException
```
exception_id    UUID PK
company_id      UUID FK → companies [RLS]
professional_id UUID FK → professionals
exception_date  DATE NOT NULL
type            VARCHAR NOT NULL    # SUBSTITUTIVE | ADDITIVE
start_time      TIME nullable
end_time        TIME nullable
reason          VARCHAR nullable
UNIQUE(professional_id, exception_date, type)
```

### Reservation
```
reservation_id  UUID PK
company_id      UUID FK → companies [RLS]
professional_id UUID FK → professionals
start_at        TIMESTAMPTZ NOT NULL
end_at          TIMESTAMPTZ NOT NULL
type            VARCHAR NOT NULL    # SOFT | FIRME (imutável)
status          VARCHAR DEFAULT 'ACTIVE'
  -- ACTIVE | EXPIRED | CANCELLED | PROMOTED | RELEASED | CONSUMED | NO_SHOW
expires_at      TIMESTAMPTZ nullable
appointment_id  UUID nullable FK → appointments
created_at      TIMESTAMPTZ DEFAULT now()
```
EXCLUDE CONSTRAINT: `tstzrange WHERE status='ACTIVE'`.

### DirectOccupancy
```
occupancy_id    UUID PK
company_id      UUID FK → companies [RLS]
professional_id UUID FK → professionals
start_at        TIMESTAMPTZ NOT NULL
end_at          TIMESTAMPTZ NOT NULL
appointment_id  UUID nullable FK → appointments
reason          VARCHAR NOT NULL
opened_at       TIMESTAMPTZ DEFAULT now()
closed_at       TIMESTAMPTZ nullable
opened_by       UUID FK → users
```

---

## Financial Core

### Account
Ver [domains/financial-core.md](domains/financial-core.md).

### Movement
Ver [domains/financial-core.md](domains/financial-core.md).

### Entry
Ver [domains/financial-core.md](domains/financial-core.md).

### Transfer
Ver [domains/financial-core.md](domains/financial-core.md).

### ReconciliationRecord
Ver [domains/financial-core.md](domains/financial-core.md).

### MovementReconciliation
Ver [domains/financial-core.md](domains/financial-core.md).

### CashCount
Ver [domains/financial-core.md](domains/financial-core.md).

### TenantFeeRoutingPolicy
Ver [domains/financial-core.md](domains/financial-core.md).

---

## Pagamentos

### Payment
Ver [domains/payments.md](domains/payments.md).

### PaymentTransaction
Ver [domains/payments.md](domains/payments.md).

### PaymentSource
Ver [domains/payments.md](domains/payments.md).

### DepositPolicy
Ver [domains/payments.md](domains/payments.md).

---

## Comunicação e Integrações

### IntegrationCredential
```
credential_id   UUID PK
company_id      UUID FK → companies [RLS]
provider        VARCHAR NOT NULL
  -- WHATSAPP_EVOLUTION | WHATSAPP_META | SMTP | ASAAS
secret_encrypted TEXT NOT NULL    # Fernet(CREDENTIAL_ENCRYPTION_KEY)
masked_preview  VARCHAR(20)       # últimos 4 chars
config          JSONB nullable    # configurações extras do provider
status          VARCHAR DEFAULT 'ACTIVE'
created_at      TIMESTAMPTZ DEFAULT now()
updated_at      TIMESTAMPTZ
```

### CommunicationSetting
```
company_id              UUID PK FK → companies
canal                   VARCHAR NOT NULL    # WHATSAPP | EMAIL
quiet_hours_start       TIME nullable
quiet_hours_end         TIME nullable
use_communication_service BOOLEAN DEFAULT false
feature_flag            BOOLEAN DEFAULT false
```

### CommunicationTemplate
```
template_id     UUID PK
company_id      UUID FK → companies [RLS]
event_type      VARCHAR NOT NULL
channel         VARCHAR NOT NULL
body_template   TEXT NOT NULL
is_active       BOOLEAN DEFAULT true
is_default      BOOLEAN DEFAULT false
```

### CommunicationLog
```
log_id          UUID PK
company_id      UUID FK → companies [RLS]
customer_id     UUID nullable FK → customers
event_type      VARCHAR
channel         VARCHAR
status          VARCHAR    # SENT | SCHEDULED | FAILED
sent_at         TIMESTAMPTZ nullable
scheduled_for   TIMESTAMPTZ nullable
error_message   TEXT nullable
created_at      TIMESTAMPTZ DEFAULT now()
```

### ProcessedIdempotencyKey
```
key             VARCHAR NOT NULL
consumer        VARCHAR NOT NULL
company_id      UUID nullable    # auditoria; não usado em RLS
processed_at    TIMESTAMPTZ DEFAULT now()
PRIMARY KEY (key, consumer)
```

---

## WhatsApp Bot

### BotSession
```
session_id      UUID PK
company_id      UUID FK → companies [RLS]
phone           VARCHAR NOT NULL
state           VARCHAR NOT NULL    # estado do FSM do bot
session_data    JSONB DEFAULT '{}'
created_at      TIMESTAMPTZ DEFAULT now()
updated_at      TIMESTAMPTZ
UNIQUE(company_id, phone)
```

### WhatsAppConnection
```
connection_id   UUID PK
company_id      UUID FK UNIQUE → companies [RLS]
state           VARCHAR NOT NULL    # DISCONNECTED | CONNECTING | CONNECTED
instance_name   VARCHAR nullable
qr_code         TEXT nullable
created_at      TIMESTAMPTZ DEFAULT now()
updated_at      TIMESTAMPTZ
```

---

## Booking Público

### WebBookingSession
```
token       VARCHAR(64) UNIQUE NOT NULL
company_id  UUID FK → companies
state       VARCHAR NOT NULL
session_data JSONB DEFAULT '{}'
expires_at  TIMESTAMPTZ NOT NULL
created_at  TIMESTAMPTZ DEFAULT now()
updated_at  TIMESTAMPTZ
```

### BookingSession (domínio bot — separado de WebBookingSession)
```
session_id      UUID PK
company_id      UUID FK → companies [RLS]
customer_phone  VARCHAR NOT NULL
state           VARCHAR NOT NULL
data            JSONB DEFAULT '{}'
expires_at      TIMESTAMPTZ
created_at      TIMESTAMPTZ DEFAULT now()
```