# CLAUDE.md — Paladino Labs (Monorepo)

> Contexto persistente para sessões Claude Code. Leia antes de escrever qualquer linha.

---

## Navegação obrigatória — use Token Savior primeiro

Este monorepo tem dois projetos grandes (`agendamento_engine` ~50 arquivos Python,
`painel` ~30 arquivos TypeScript/TSX). Antes de editar qualquer arquivo:

1. `get_project_summary` → visão geral de módulos e exports
2. `get_class_source` / `get_function_source` → código exato sem abrir arquivos inteiros
3. Só então `Read` se precisar de contexto amplo

Nunca abra `engine.py` (49 KB) ou `bot_service.py` (28 KB) completos — use Token Savior.

---

## Stack

### Backend — `agendamento_engine/`
| Componente | Versão / detalhe |
|-----------|-----------------|
| Python | 3.12 |
| FastAPI | 0.2.0 |
| SQLAlchemy | 2.0 (ORM síncrono) |
| Alembic | migrações — HEAD: `f1e2d3c4b5a6` |
| PostgreSQL | multi-tenant por `company_id` |
| Auth | JWT HS256 + bcrypt; `HTTPBearer(auto_error=False)` |
| WhatsApp | Evolution API v2 (cliente HTTP próprio) |

### Frontend — `painel/`
| Componente | Versão / detalhe |
|-----------|-----------------|
| Next.js | App Router — leia `node_modules/next/dist/docs/` antes de assumir convenções |
| TypeScript | strict |
| Tailwind CSS | — |
| shadcn/ui | componentes em `components/ui/` |
| Fetch | `lib/api.ts` centralizado |

---

## Estrutura — Backend

```
agendamento_engine/
  app/
    core/
      config.py          ← Settings (Pydantic); todas as configs devem vir daqui
      security.py
    infrastructure/db/
      base.py            ← Base, TimestampMixin
      models/            ← um arquivo por modelo
    modules/
      appointments/      ← CRUD agendamentos + polices.py (política de 2h)
      auth/
      availability/      ← cálculo de slots disponíveis
      booking/           ← BookingEngine (source of truth de agendamento)
        engine.py        ← BookingEngine class + singleton booking_engine
        schemas.py       ← BookingIntent, SessionUpdateResult, SlotOption...
        actions.py       ← BookingAction enum
        exceptions.py    ← SlotUnavailableError, BookingNotFoundError
        http_schemas.py  ← schemas para a API REST
        router.py        ← endpoints /booking/*
        predictor.py     ← oferta preditiva
      companies/
      company_profile/
      customers/
        service.py       ← get_or_create_by_phone com IntegrityError catch (race cond.)
      notifications.py   ← envio de notificações
      products/
      professionals/
      public/            ← endpoints sem auth
      schedule/
      services/
      uploads/
      users/
      whatsapp/
        bot_service.py   ← dispatcher FSM principal
        sender.py        ← wrapper envio (send_text / send_buttons / send_list)
        evolution_client.py
        session.py
        helpers.py
        input_parser.py
        response_formatter.py
        messages.py      ← strings de UX em PT-BR
        router.py        ← webhook + endpoints de conexão
        handlers/        ← um handler por estado FSM
  migrations/versions/   ← Alembic; HEAD atual: f1e2d3c4b5a6
```

## Estrutura — Frontend

```
painel/
  app/
    (dashboard)/         ← rota autenticada
      appointments/      ← agendamentos (lista + novo)
      customers/
      dashboard/         ← página inicial com KPIs
      integrations/      ← WhatsApp connection
      products/
      professionals/
      services/
      settings/
    book/[slug]/         ← fluxo público de agendamento online
      BookingFlow.tsx    ← FSM de 8 estados (IDLE → CONFIRMED)
  components/
    ui/                  ← shadcn primitivos
  hooks/
    useAuth.ts           ← re-export intencional — NÃO remover
  lib/
    api.ts               ← fetch centralizado; sempre usar este
    utils.ts             ← formatBRL, formatDateTime (centralizar aqui)
    constants.ts         ← APPOINTMENT_STATUS_LABELS, APPOINTMENT_STATUS_VARIANT
```

---

## Decisões arquiteturais

### BookingEngine é o único ponto de entrada para operações de agendamento
- **Nunca** chame `appointment_svc.create_appointment()` diretamente de handlers de bot ou rotas do painel
- `booking_engine.confirm()` / `.cancel()` / `.reschedule()` são as únicas APIs de escrita
- Os services subjacentes (`appointment_svc`, `availability_svc`) existem mas são implementação interna do engine

### FSM do bot — 13 estados
```
INICIO → AGUARDANDO_NOME → OFERTA_RECORRENTE
MENU_PRINCIPAL → ESCOLHENDO_SERVICO → ESCOLHENDO_PROFISSIONAL
→ ESCOLHENDO_DATA → ESCOLHENDO_HORARIO → CONFIRMANDO → INICIO (reset)
VER_AGENDAMENTOS → GERENCIANDO_AGENDAMENTO → CANCELANDO / REAGENDANDO
HUMANO (silêncio)
```
- `AWAITING_CUSTOMER` na BookingSession é bypassado automaticamente pelo bot (cliente já identificado via WhatsApp)
- O bypass usa `BookingAction.SET_CUSTOMER` com `{"customer_id": UUID}` — sem coletar nome/telefone

### Multi-tenant
- Toda tabela tem `company_id` (UUID FK para `companies`)
- Constraint de unicidade de customer: `UNIQUE(company_id, phone)` — não apenas `UNIQUE(phone)`
- Migration `f1e2d3c4b5a6` corrigiu a constraint legada `clients_phone_key`

### Timezone
- `company_timezone` é snapshot na criação da BookingSession — imutável
- Todos `DateTime` no SQLAlchemy usam `timezone=True`
- No frontend, sempre passar `timeZone: companyTimezone` em `toLocaleString`

### Race condition em customers
- `get_or_create_by_phone` captura `IntegrityError` do SQLAlchemy, faz `db.rollback()` e re-tenta SELECT
- Isso cobre o padrão TOCTOU (dois requests simultâneos passam pelo SELECT sem achar, ambos tentam INSERT)

---

## Convenções

### Python / Backend
- Modelos usam `TimestampMixin` de `app.infrastructure.db.base` (não definir `created_at`/`updated_at` manualmente)
- Schemas Pydantic v2: usar `model_config = ConfigDict(from_attributes=True)` (não `class Config`)
- Exceções de domínio: sem HTTP codes (`SlotUnavailableError`, `PolicyViolationError`, `BookingNotFoundError`)
- Routers capturam exceções de domínio → HTTP codes
- `user_id=None` é aceito por todos os services chamados pelo bot

### TypeScript / Frontend
- Imports de `lib/api.ts` sempre — nunca `fetch` raw
- Formatação monetária: `formatBRL()` de `lib/utils.ts`
- Formatação de data: `formatDateTime()` de `lib/utils.ts` com `timeZone` explícito
- Status de agendamento: constantes de `lib/constants.ts`
- Badge de ativo/inativo: `<ActiveBadge>` de `components/ActiveBadge.tsx`

---

## Estado atual do Sprint

### Concluído
- Sprint 1: schema alignment, modelos, migrações base
- Sprint 2: WhatsApp bot (FSM, Evolution API)
- Sprint 3: BookingEngine (10 métodos, schemas, exceções)
- Sprint 4: Booking FSM unificado (web + bot)
- Sprint 4 fix: `AWAITING_CUSTOMER` bypass para bot
- Sprint 5: timezone fix no painel (`BookingFlow.tsx`)
- Fix produção: `get_or_create_by_phone` race condition + migration `f1e2d3c4b5a6`

### Pendente (próximos sprints)
1. **Cleanup Grupo 1** (zero risco): deletar 5 `repository.py` vazios, padronizar Pydantic v2, criar `ActiveBadge`, `STATUS_LABELS` em constants, `formatBRL`/`formatDateTime` em utils
2. **Cleanup Grupo 2**: `get_or_404` genérico em `core/db_utils.py`, `update_entity` genérico, hook `useFetch`
3. **Workers**: limpeza de sessões expiradas (`bot_sessions`), lembretes 24h/2h (migration `reminder_24h_sent`, `reminder_2h_sent`)
4. **Painel → BookingEngine**: migrar `appointments/router.py` para usar `booking_engine.confirm/cancel/reschedule`

---

## Protocolo de Sprint

Antes de iniciar qualquer sprint:
1. Confirmar escopo exato com o usuário
2. Listar arquivos afetados
3. Executar um arquivo por vez com validação intermediária
4. **Nunca** deletar código antigo na mesma PR que introduz o novo
5. **Nunca** migrar todos os handlers em bloco — um por vez

---

## Migrações Alembic

Cadeia atual (linear, HEAD = `f1e2d3c4b5a6`):
```
None → 16014789aa88 → 36e2e1f526da → 540331d2c848 → 906df50dc028 (merge)
     → a1b2c3d4e5f6 → a2b3c4d5e6f7 → ... → e3c9a1d84f17 → f1e2d3c4b5a6
```

Para aplicar: `alembic upgrade head` no container de produção.
Para criar nova migration: `alembic revision --autogenerate -m "descricao"` + revisar antes de aplicar.

---

## Variáveis de ambiente relevantes

Definidas em `app/core/config.py` (classe `Settings`):
- `BOT_SESSION_TTL_MINUTES` (30)
- `BOT_PREDICTIVE_OFFER_TTL_MINUTES` (5)
- `BOT_MAX_SLOTS_DISPLAYED` (6)
- `BOT_FALLBACK_MAX_COUNT` (3)
- `APPOINTMENT_MIN_HOURS_BEFORE_CANCEL` (2)
- `APPOINTMENT_MIN_HOURS_BEFORE_RESCHEDULE` (2)
- `SECRET_KEY` — **OBRIGATÓRIO em produção** (padrão `"troque-em-producao"` é inseguro)
