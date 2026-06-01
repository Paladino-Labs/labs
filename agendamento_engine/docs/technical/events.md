# Catálogo de Eventos — Paladino

Todos os eventos publicados no sistema, agrupados por domínio.
Formato: `dominio.entidade.acao` ou `dominio.acao`.

---

## Convenções

| Campo | Descrição |
|-------|-----------|
| Prefixo | Domínio de origem do evento |
| Tipo | `EventBus` (best-effort) ou `Celery` (garantido) |
| Handlers | Quem consome o evento |

---

## Financial Core (`financial_core.*`)

| Evento | Tipo | Handlers |
|--------|------|----------|
| `financial_core.account.created` | EventBus | — |
| `financial_core.movement_created` | EventBus | — |
| `financial_core.entry_created` | EventBus | — |
| `financial_core.transfer_completed` | EventBus | — |
| `financial_core.transfer_failed` | EventBus | — |
| `financial_core.manual_adjustment_created` | EventBus | — |
| `financial_core.reconciliation_opened` | EventBus | — |
| `financial_core.reconciliation_closed` | EventBus | — |

---

## Cash Count (`cash_count.*`)

| Evento | Tipo | Handlers |
|--------|------|----------|
| `cash_count.recorded` | EventBus | — |
| `cash_count.adjustment_created` | EventBus | — |

---

## Payments (`payment.*`)

| Evento | Tipo | Handlers |
|--------|------|----------|
| `payment.created` | EventBus | — |
| `payment.confirmed` | EventBus | CommunicationHandler (notifica cliente) |
| `payment.failed` | EventBus | — |
| `payment.cancelled` | EventBus | — |
| `payment.refunded` | EventBus | CommunicationHandler (notifica cliente) |

---

## Agenda (`agenda.*`, `appointment.*`)

| Evento | Tipo | Handlers |
|--------|------|----------|
| `agenda.soft_reservation.created` | EventBus | — |
| `agenda.soft_reservation.expired` | **Celery** | SoftReservationHandler |
| `agenda.soft_reservation.cancelled` | **Celery** | — |
| `agenda.reservation.confirmed` | **Celery** | — |
| `agenda.reservation.released` | EventBus | — |
| `agenda.direct_occupancy.opened` | EventBus | — |
| `agenda.direct_occupancy.closed` | EventBus | — |
| `agenda.overbooking_forced` | EventBus | — |
| `operation.completed` | EventBus | — |
| `operation.cancelled` | EventBus | CommunicationHandler |
| `operation.no_show` | EventBus | — |

**Nota:** `agenda.soft_reservation.expired` usa Celery (não EventBus)
porque é fluxo crítico — a expiração deve ser garantida mesmo que
o processo reinicie.

---

## Appointment (`appointment.*`)

| Evento | Tipo | Handlers |
|--------|------|----------|
| `appointment.confirmed` | EventBus | CommunicationHandler (lembrete agendado) |
| `appointment.cancelled` | EventBus | CommunicationHandler |
| `appointment.reminder_24h` | **Celery Beat** | CommunicationHandler |
| `appointment.reminder_1h` | **Celery Beat** | CommunicationHandler |

---

## Auth (`auth.*`)

| Evento | Tipo | Handlers |
|--------|------|----------|
| `auth.password_reset_requested` | **Celery** | CommunicationHandler (e-mail) |

---

## Communication (`statement.*`) — Reconciliação (Fase 3)

| Evento | Tipo | Handlers |
|--------|------|----------|
| `statement.imported` | EventBus | ReconciliationHandler |
| `reconciliation.matched` | EventBus | — |
| `reconciliation.orphan_flagged` | EventBus | — |
| `reconciliation.orphan_dismissed` | EventBus | — |

---

## Formato de Payload (convenção)

```python
event_bus.publish(
    "payment.confirmed",
    payment_id=str(payment.payment_id),
    company_id=str(payment.company_id),
    amount=float(payment.net_charged_amount),
    customer_id=str(payment.customer_id) if payment.customer_id else None,
)
```

Todos os IDs como `str` (UUID serializado). Valores monetários como `float`.
Nunca incluir objetos SQLAlchemy no payload (sessão pode estar fechada no handler).