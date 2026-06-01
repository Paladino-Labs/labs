# Agenda — Domínio de Agendamentos e Reservas

## Responsabilidade

O domínio de Agenda gerencia o tempo dos profissionais:
agendamentos, reservas (SOFT e FIRME), bloqueios, exceções de
horário e ocupações diretas. Garante que dois agendamentos nunca
colidam no mesmo slot do mesmo profissional.

---

## FSM de Agendamentos (Appointment)

### Estados

```python
class AppointmentStatus(str, Enum):
    DRAFT       = "DRAFT"       # Rascunho — checkout iniciado
    SCHEDULED   = "SCHEDULED"   # Legado (alias: REQUESTED no ORM)
    REQUESTED   = "REQUESTED"   # Solicitado — aguardando confirmação
    CONFIRMED   = "CONFIRMED"   # Confirmado pelo estabelecimento
    IN_PROGRESS = "IN_PROGRESS" # Em andamento
    COMPLETED   = "COMPLETED"   # Concluído
    CANCELLED   = "CANCELLED"   # Cancelado
    NO_SHOW     = "NO_SHOW"     # Cliente não compareceu
    FAILED      = "FAILED"      # Falha técnica
```

**Nota:** `SCHEDULED` permanece no banco por compatibilidade com dados
legados. Código Python usa `REQUESTED` como equivalente semântico.

### Transições válidas

```
DRAFT       → REQUESTED   (checkout confirmado)
DRAFT       → CANCELLED   (soft_reservation expirada)
REQUESTED   → CONFIRMED   (confirmação manual ou pagamento)
REQUESTED   → CANCELLED   (cancelamento ou expiração)
CONFIRMED   → IN_PROGRESS (início do atendimento)
CONFIRMED   → CANCELLED   (cancelamento)
CONFIRMED   → NO_SHOW     (cliente não compareceu após threshold)
IN_PROGRESS → COMPLETED   (conclusão)
IN_PROGRESS → CANCELLED   (cancelamento excepcional)
* → FAILED              (erro técnico, qualquer estado)
```

### Campos do Appointment

```
appointment_id      UUID PK
company_id          UUID FK → companies [RLS]
professional_id     UUID FK → professionals
customer_id         UUID FK → customers
start_at            TIMESTAMPTZ NOT NULL
end_at              TIMESTAMPTZ NOT NULL
status              AppointmentStatus DEFAULT 'REQUESTED'
financial_status    VARCHAR DEFAULT 'pending'
  -- pending | paid | cancelled | refunded
operation_type      VARCHAR DEFAULT 'SERVICE_SCHEDULED'
  -- SERVICE_SCHEDULED | SERVICE_DIRECT | PRODUCT_SALE
idempotency_key     VARCHAR UNIQUE nullable
reminder_24h_sent   BOOLEAN DEFAULT false
reminder_1h_sent    BOOLEAN DEFAULT false
cancelled_at        TIMESTAMPTZ nullable
cancelled_by        UUID nullable FK → users
created_at          TIMESTAMPTZ DEFAULT now()
updated_at          TIMESTAMPTZ
```

### EXCLUDE CONSTRAINT (anti-overlap)

```sql
EXCLUDE USING gist (
  company_id WITH =,
  professional_id WITH =,
  tsrange(start_at::timestamp, end_at::timestamp, '[)') WITH &&
) WHERE (status NOT IN ('CANCELLED', 'FAILED', 'EXPIRED'))
```

Agendamentos CANCELLED e FAILED não participam da constraint.
Tentativas de criar overlap resultam em HTTP 409.

---

## Sistema de Reservas (Reservation)

### Motivação
O BookingFlow público leva tempo (o cliente escolhe serviço, barbeiro,
data, horário, preenche dados). Durante esse processo, outro cliente pode
reservar o mesmo slot. A Reservation garante que o slot está "segurado"
enquanto o checkout acontece.

### Tipos e Status

```
type   VARCHAR  -- SOFT | FIRME  (natureza; imutável após criação)
status VARCHAR  -- ACTIVE | EXPIRED | CANCELLED | PROMOTED | RELEASED | CONSUMED | NO_SHOW
```

**SOFT:** criada ao iniciar o checkout. TTL configurável (padrão: 15 min).
Expira automaticamente se o checkout não for concluído.

**FIRME:** criada ao confirmar o agendamento. Não expira. Bloqueia o slot permanentemente.

### Modelo: Reservation

```
reservation_id  UUID PK
company_id      UUID FK → companies [RLS]
professional_id UUID FK → professionals
start_at        TIMESTAMPTZ NOT NULL
end_at          TIMESTAMPTZ NOT NULL
type            VARCHAR NOT NULL        # SOFT | FIRME (imutável)
status          VARCHAR DEFAULT 'ACTIVE'
expires_at      TIMESTAMPTZ nullable    # apenas SOFT; NULL = sem TTL
appointment_id  UUID nullable FK → appointments
created_at      TIMESTAMPTZ DEFAULT now()
```

### EXCLUDE CONSTRAINT (anti-concorrência)

```sql
ALTER TABLE reservations ADD CONSTRAINT no_overlap_active
  EXCLUDE USING gist (
    company_id WITH =,
    professional_id WITH =,
    tstzrange(start_at, end_at, '[)') WITH &&
  ) WHERE (status = 'ACTIVE');
```

**Cobertura:** SOFT ACTIVE e FIRME ACTIVE bloqueiam o mesmo recurso.
Quando SOFT expira (status → EXPIRED), sai da constraint.
Quando SOFT é promovida (status → PROMOTED), sai da constraint.

⚠️ Usa `tstzrange` (não `tsrange`) porque `start_at`/`end_at` são TIMESTAMPTZ.

### Operações

#### create_soft_reservation
```python
INSERT Reservation(type='SOFT', status='ACTIVE',
                   expires_at=now()+ttl_minutes)
# Se EXCLUDE viola: raise SlotUnavailableError (HTTP 409)
# ttl_minutes: TenantConfig.soft_reservation_ttl_min (default 15)
```

#### promote_to_firme ⚡ (operação crítica)
```python
# ATÔMICO — única transação
BEGIN
  soft.status = 'PROMOTED'     # SOFT sai do EXCLUDE
  db.flush()                   # constraint liberada ANTES do INSERT
  INSERT Reservation(type='FIRME', status='ACTIVE',
                     appointment_id=appointment_id, mesmo slot)
COMMIT
# Se INSERT FIRME falhar → rollback → SOFT volta a ACTIVE
```

**Por que o `flush()`?** Sem ele, PostgreSQL ainda vê a SOFT como ACTIVE
durante a mesma transação e o EXCLUDE bloqueia o INSERT FIRME.
O `flush()` envia o UPDATE para o banco sem commitar, permitindo
que o EXCLUDE avalie o estado atualizado.

#### expire_soft_reservation
```python
soft.status = 'EXPIRED'
# Emite agenda.soft_reservation.expired via Celery task direta (crítico)
# Se appointment vinculado em DRAFT/REQUESTED: appointment.status = CANCELLED
```

#### release_reservation
```python
reservation.status = 'RELEASED'
# Libera o slot para outros
```

#### create_firme_direct (walk-in)
```python
INSERT Reservation(type='FIRME', status='ACTIVE')
# Para walk-ins: sem SOFT intermediária
# Sujeito ao mesmo EXCLUDE — pode resultar em HTTP 409
```

---

## Expiração Automática de Reservas SOFT

### Celery Beat Task
`app/workers/tasks/expire_reservations.py → expire_soft_reservations_scan`

Schedule: `*/5` minutos.

```python
expired = db.query(Reservation).filter(
    Reservation.type == 'SOFT',
    Reservation.status == 'ACTIVE',
    Reservation.expires_at < datetime.now(UTC)
).all()
for r in expired:
    reservation_service.expire_soft_reservation(r.reservation_id, r.company_id, db)
```

### Handler de evento
`app/workers/handlers/soft_reservation_handler.py`

```python
@event_bus.on("agenda.soft_reservation.expired")
def handle_soft_reservation_expired(reservation_id, company_id, **kwargs):
    reservation = db.get(Reservation, reservation_id)
    if reservation.status != 'EXPIRED':
        return  # idempotente
    if reservation.appointment_id:
        appointment = db.get(Appointment, reservation.appointment_id)
        if appointment.status in ('DRAFT', 'REQUESTED'):
            appointment.status = 'CANCELLED'
```

---

## Exceções de Horário (ScheduleException)

Substituem ou adicionam horários para um profissional em datas específicas.

```
exception_id    UUID PK
company_id      UUID FK → companies [RLS]
professional_id UUID FK → professionals
exception_date  DATE NOT NULL
type            VARCHAR NOT NULL    # SUBSTITUTIVE | ADDITIVE
start_time      TIME nullable       # NULL = dia todo de folga (SUBSTITUTIVE)
end_time        TIME nullable
reason          VARCHAR nullable
UNIQUE(professional_id, exception_date, type)
```

**SUBSTITUTIVE:** substitui o horário padrão da semana para aquela data.
Se `start_time=NULL`: dia todo de folga.

**ADDITIVE:** adiciona horário extra além do padrão.

---

## Ocupação Direta (DirectOccupancy)

Marca um profissional como ocupado sem um agendamento formal.
Usado para walk-ins, reuniões, bloqueios avulsos.

```
occupancy_id    UUID PK
company_id      UUID FK → companies [RLS]
professional_id UUID FK → professionals
start_at        TIMESTAMPTZ
end_at          TIMESTAMPTZ
appointment_id  UUID nullable FK → appointments
reason          VARCHAR NOT NULL
opened_at       TIMESTAMPTZ DEFAULT now()
closed_at       TIMESTAMPTZ nullable
opened_by       UUID FK → users
```

Acesso: OWNER/ADMIN/OPERATOR.
Overbooking forçado: apenas OWNER/ADMIN; reason obrigatório; 🔒 auditado.

---

## Horários de Trabalho (WorkingHour)

```
id              UUID PK
company_id      UUID FK → companies [RLS]
professional_id UUID FK → professionals
weekday         INTEGER    # 0=Segunda, 6=Domingo (ISO weekday - 1)
start_time      TIME NOT NULL
end_time        TIME NOT NULL
```

Combinado com ScheduleException para calcular disponibilidade de um
profissional em qualquer data.

---

## Bloqueios de Agenda (ScheduleBlock)

```
id              UUID PK
company_id      UUID FK → companies [RLS]
professional_id UUID FK → professionals
starts_at       TIMESTAMPTZ NOT NULL
ends_at         TIMESTAMPTZ NOT NULL
reason          VARCHAR nullable
```

Férias, licenças, bloqueios administrativos.

---

## TTLs Configuráveis (TenantConfig)

| Parâmetro | Default | Descrição |
|-----------|---------|-----------|
| `soft_reservation_ttl_min` | 15 | Validade da reserva SOFT (minutos) |
| `draft_expiration_min` | 60 | Expiração de Appointment em DRAFT |
| `requested_expiration_h` | 24 | Expiração de Appointment em REQUESTED |
| `no_show_threshold_min` | 30 | Minutos após start_at para marcar NO_SHOW |
| `no_penalty_cancel_h` | 12 | Horas antes para cancelar sem penalidade |
| `require_payment_upfront` | false | Exige pagamento antes de CONFIRMED |

---

## Invariantes do Domínio de Agenda

1. **Dois agendamentos não colidem.** EXCLUDE CONSTRAINT no banco.
2. **SOFT e FIRME ACTIVE não colidem.** EXCLUDE com `WHERE status='ACTIVE'`.
3. **`promote_to_firme` é atômica.** Falha reverte completamente.
4. **`type` de Reservation é imutável** após criação.
5. **Expiração de SOFT é via Celery** (fluxo crítico, não EventBus best-effort).
6. **Overbooking forçado exige reason** e é auditado.