# API Contract V1

## Objective

This document defines the target HTTP contract for the scheduling platform API.
It is the source of truth for:

- route naming
- request and response shapes
- authentication context
- multi-tenant rules
- appointment snapshots
- error conventions

This contract is designed for a real multi-tenant scheduling system and should guide the backend refactor and frontend integration.

## Global Principles

### Multi-tenant

- Every authenticated request is scoped by `tenant_id` from the JWT.
- Clients must never send `tenant_id` in the request body.
- The backend must always enforce tenant isolation in queries and writes.
- Internal code may temporarily use `company_id`, but the external contract should standardize on `tenant_id`.

### Resource IDs

- Requests must always reference entities by ID.
- Requests must never depend on names as identifiers.
- Responses should be enriched with names and useful metadata for UI rendering.

### Time

- All datetimes in requests and responses must be ISO 8601.
- Datetimes should be stored and returned in UTC.
- Availability responses may additionally expose UI-friendly labels.

### Pagination

- Collection endpoints should support pagination, even if the first implementation returns all items.
- Standard query params:
  - `limit`
  - `offset`

### Errors

- All non-2xx responses should use a standard error envelope.

```json
{
  "error": {
    "code": "APPOINTMENT_CONFLICT",
    "message": "Time slot is no longer available",
    "details": {}
  }
}
```

Recommended error codes:

- `UNAUTHENTICATED`
- `FORBIDDEN`
- `NOT_FOUND`
- `VALIDATION_ERROR`
- `APPOINTMENT_CONFLICT`
- `INVALID_STATUS_TRANSITION`
- `BUSINESS_RULE_VIOLATION`
- `DUPLICATE_REQUEST`

### Timestamps

Every mutable business resource should expose:

- `created_at`
- `updated_at`

### Soft Activation

Catalog resources should prefer activation flags over hard deletion:

- `clients.is_active` optional
- `services.is_active` required
- `professionals.is_active` required

### Appointment Snapshots

Appointments must persist immutable snapshots of display-critical data:

- `client_name`
- `professional_name`
- service snapshots per item:
  - `service_id`
  - `service_name`
  - `duration_minutes`
  - `price`

Responses may expose both current linked references and stored snapshot data, but the snapshot is the source of truth for historical rendering.

## Canonical Route Map

- `/auth`
- `/clients`
- `/services`
- `/professionals`
- `/professionals/{professional_id}/services`
- `/availability`
- `/appointments`

## Auth

### POST `/auth/login`

Authenticates a user and returns a bearer token.

Request:

```json
{
  "email": "admin@tenant.com",
  "password": "secret"
}
```

Response `200`:

```json
{
  "access_token": "jwt",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### GET `/auth/me`

Returns the authenticated user context.

Auth required: yes

Response `200`:

```json
{
  "id": "uuid",
  "name": "Admin",
  "email": "admin@tenant.com",
  "tenant_id": "uuid",
  "is_admin": true
}
```

## Clients

### Client Model

```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "Joao Silva",
  "phone": "+5511999999999",
  "email": "joao@email.com",
  "notes": "Prefere manha",
  "created_at": "2026-04-10T12:00:00Z",
  "updated_at": "2026-04-10T12:00:00Z"
}
```

### POST `/clients`

Auth required: yes

Request:

```json
{
  "name": "Joao Silva",
  "phone": "+5511999999999",
  "email": "joao@email.com",
  "notes": "Prefere manha"
}
```

Response `201`:

```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "Joao Silva",
  "phone": "+5511999999999",
  "email": "joao@email.com",
  "notes": "Prefere manha",
  "created_at": "2026-04-10T12:00:00Z",
  "updated_at": "2026-04-10T12:00:00Z"
}
```

### GET `/clients`

Auth required: yes

Query params:

- `search` optional
- `limit` optional
- `offset` optional

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Joao Silva",
      "phone": "+5511999999999",
      "email": "joao@email.com"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### GET `/clients/{client_id}`

Auth required: yes

Response `200`:

```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "Joao Silva",
  "phone": "+5511999999999",
  "email": "joao@email.com",
  "notes": "Prefere manha",
  "created_at": "2026-04-10T12:00:00Z",
  "updated_at": "2026-04-10T12:00:00Z"
}
```

### PATCH `/clients/{client_id}`

Auth required: yes

Request:

```json
{
  "name": "Joao da Silva",
  "phone": "+5511999999999",
  "email": "joao@email.com",
  "notes": "Gosta de atendimento cedo"
}
```

Response `200`: same as `GET /clients/{client_id}`

## Services

### Service Model

```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "Corte de cabelo",
  "duration_minutes": 30,
  "price": 50,
  "description": "Corte masculino",
  "is_active": true,
  "created_at": "2026-04-10T12:00:00Z",
  "updated_at": "2026-04-10T12:00:00Z"
}
```

### POST `/services`

Auth required: yes

Request:

```json
{
  "name": "Corte de cabelo",
  "duration_minutes": 30,
  "price": 50,
  "description": "Corte masculino",
  "is_active": true
}
```

Response `201`: service model

### GET `/services`

Auth required: yes

Query params:

- `is_active` optional
- `limit` optional
- `offset` optional

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Corte de cabelo",
      "duration_minutes": 30,
      "price": 50,
      "is_active": true
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### GET `/services/{service_id}`

Auth required: yes

Response `200`: service model

### PATCH `/services/{service_id}`

Auth required: yes

Request:

```json
{
  "name": "Corte masculino",
  "duration_minutes": 30,
  "price": 60,
  "description": "Corte atualizado",
  "is_active": true
}
```

Response `200`: service model

## Professionals

### Professional Model

```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "Maria",
  "email": "maria@salon.com",
  "is_active": true,
  "created_at": "2026-04-10T12:00:00Z",
  "updated_at": "2026-04-10T12:00:00Z"
}
```

### POST `/professionals`

Auth required: yes

Request:

```json
{
  "name": "Maria",
  "email": "maria@salon.com"
}
```

Response `201`: professional model

### GET `/professionals`

Auth required: yes

Query params:

- `is_active` optional
- `search` optional
- `limit` optional
- `offset` optional

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Maria",
      "email": "maria@salon.com",
      "is_active": true
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### GET `/professionals/{professional_id}`

Auth required: yes

Response `200`: professional model

### PATCH `/professionals/{professional_id}`

Auth required: yes

Request:

```json
{
  "name": "Maria",
  "email": "maria@salon.com",
  "is_active": true
}
```

Response `200`: professional model

## Professional Services

### POST `/professionals/{professional_id}/services`

Adds service links for a professional without replacing existing links.

Auth required: yes

Request:

```json
{
  "service_ids": ["uuid1", "uuid2"]
}
```

Response `200`:

```json
{
  "professional_id": "uuid",
  "services": [
    {
      "id": "uuid1",
      "name": "Corte de cabelo",
      "duration_minutes": 30,
      "price": 50,
      "is_active": true
    },
    {
      "id": "uuid2",
      "name": "Barba",
      "duration_minutes": 20,
      "price": 35,
      "is_active": true
    }
  ]
}
```

### PUT `/professionals/{professional_id}/services`

Replaces the full set of services linked to the professional.

Auth required: yes

Request:

```json
{
  "service_ids": ["uuid1", "uuid2"]
}
```

Response `200`: same as POST

### GET `/professionals/{professional_id}/services`

Auth required: yes

Response `200`:

```json
{
  "professional_id": "uuid",
  "services": [
    {
      "id": "uuid",
      "name": "Corte de cabelo",
      "duration_minutes": 30,
      "price": 50,
      "is_active": true
    }
  ]
}
```

## Availability

Availability is the heart of the scheduling system and must always be computed from:

- tenant rules
- professional schedule
- linked services
- blocked slots
- existing appointments
- minimum lead time

### GET `/availability`

Auth required: yes

Query params:

- `professional_id` required
- `service_id` required for single-service flow
- `date` required in `YYYY-MM-DD`

Future-compatible extension:

- `service_ids` may be added later for multi-service scheduling

Response `200`:

```json
{
  "date": "2026-04-10",
  "professional_id": "uuid",
  "service_ids": ["uuid"],
  "slot_duration_minutes": 30,
  "available_slots": [
    {
      "start_at": "2026-04-10T09:00:00Z",
      "end_at": "2026-04-10T09:30:00Z",
      "label": "09:00"
    },
    {
      "start_at": "2026-04-10T09:30:00Z",
      "end_at": "2026-04-10T10:00:00Z",
      "label": "09:30"
    }
  ]
}
```

Business rules:

- the professional must belong to the authenticated tenant
- the requested service must belong to the same tenant
- the professional must be linked to the requested service
- past times must not be returned
- lead time must be enforced
- overlapping appointments and blocked intervals must be excluded

## Appointments

Appointments should remain prepared for multiple services even if the initial UI selects only one.

### Public Statuses

- `scheduled`
- `confirmed`
- `completed`
- `cancelled`
- `no_show`

The backend may internally map legacy statuses during migration, but external responses must use one public status vocabulary.

### Appointment Model

```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "start_at": "2026-04-10T09:00:00Z",
  "end_at": "2026-04-10T09:30:00Z",
  "status": "scheduled",
  "financial_status": "pending",
  "client": {
    "id": "uuid",
    "name": "Joao Silva"
  },
  "professional": {
    "id": "uuid",
    "name": "Maria"
  },
  "services": [
    {
      "id": "uuid",
      "name": "Corte de cabelo",
      "duration_minutes": 30,
      "price": 50
    }
  ],
  "snapshot": {
    "client_name": "Joao Silva",
    "professional_name": "Maria",
    "services": [
      {
        "service_id": "uuid",
        "service_name": "Corte de cabelo",
        "duration_minutes": 30,
        "price": 50
      }
    ]
  },
  "created_at": "2026-04-10T12:00:00Z",
  "updated_at": "2026-04-10T12:00:00Z"
}
```

### POST `/appointments`

Auth required: yes

Preferred request contract:

```json
{
  "client_id": "uuid",
  "professional_id": "uuid",
  "start_at": "2026-04-10T09:00:00Z",
  "service_ids": ["uuid"],
  "idempotency_key": "uuid"
}
```

Compatibility note:

- the frontend may initially send only one service ID
- the backend should preserve support for multi-service appointment creation

Response `201`: appointment model

Business rules:

- the client must belong to the tenant
- the professional must belong to the tenant
- all services must belong to the tenant
- the professional must be linked to all requested services
- `start_at` must respect minimum lead time
- the slot must be available
- the request must be idempotent per tenant

### GET `/appointments`

Auth required: yes

Query params:

- `date` optional
- `professional_id` optional
- `client_id` optional
- `status` optional
- `limit` optional
- `offset` optional

Response `200`:

```json
{
  "items": [
    {
      "id": "uuid",
      "start_at": "2026-04-10T09:00:00Z",
      "end_at": "2026-04-10T09:30:00Z",
      "status": "scheduled",
      "client": {
        "id": "uuid",
        "name": "Joao Silva"
      },
      "professional": {
        "id": "uuid",
        "name": "Maria"
      },
      "services": [
        {
          "id": "uuid",
          "name": "Corte de cabelo",
          "duration_minutes": 30
        }
      ]
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### GET `/appointments/{appointment_id}`

Auth required: yes

Response `200`: appointment model

### PATCH `/appointments/{appointment_id}/cancel`

Auth required: yes

Request:

```json
{
  "reason": "Cliente cancelou"
}
```

Response `200`:

```json
{
  "id": "uuid",
  "status": "cancelled",
  "updated_at": "2026-04-10T12:30:00Z"
}
```

Business rules:

- only appointments in cancellable states may be cancelled
- cancellation lead-time rules must be enforced
- financial status must be updated consistently
- audit log must be persisted

### PATCH `/appointments/{appointment_id}/reschedule`

Auth required: yes

Request:

```json
{
  "start_at": "2026-04-10T11:00:00Z",
  "professional_id": "uuid",
  "service_ids": ["uuid"]
}
```

Rules:

- `professional_id` is optional
- `service_ids` is optional
- omitting them means keeping the current professional and services
- if either changes, the backend must fully revalidate availability and linkage rules

Response `200`: appointment model

### PATCH `/appointments/{appointment_id}/status`

Optional administrative endpoint.

Auth required: yes

Request:

```json
{
  "status": "confirmed"
}
```

Response `200`:

```json
{
  "id": "uuid",
  "status": "confirmed",
  "updated_at": "2026-04-10T12:30:00Z"
}
```

This endpoint should only exist if the product truly needs manual status transitions outside cancellation and rescheduling.

## Compatibility Decisions

To support the transition from the current backend to this contract:

- move the current root availability endpoint to `/availability`
- keep the old route only temporarily, marked deprecated
- normalize legacy status values to public status values in responses
- migrate `duration` to `duration_minutes`
- replace incorrect list response models for create endpoints
- keep `idempotency_key` in appointment creation
- keep support for one selected service in the UI while accepting `service_ids`

## Folder Organization Recommendation

Suggested structure by domain:

```text
app/
  main.py
  core/
    deps.py
    security.py
    errors.py
    config.py
  infra/
    db/
      session.py
      models/
  modules/
    auth/
      router.py
      schemas.py
      service.py
      repository.py
    clients/
      router.py
      schemas.py
      service.py
      repository.py
    services/
      router.py
      schemas.py
      service.py
      repository.py
    professionals/
      router.py
      schemas.py
      service.py
      repository.py
    availability/
      router.py
      schemas.py
      service.py
      repository.py
    appointments/
      router.py
      schemas.py
      service.py
      repository.py
      policies.py
      snapshots.py
```

## Immediate Next Steps

1. Reorganize folders around the target domains.
2. Create new schemas based on this contract before changing route logic.
3. Add migrations for missing fields and snapshots.
4. Introduce compatibility adapters for legacy routes and field names.
5. Update the frontend to consume only the canonical routes defined here.
