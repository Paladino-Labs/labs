# Plano de Execução — Fase 3: Sprints 11–18
**Gerado em:** 2026-06-01 · **Encoding:** UTF-8
**Fonte:** Análise cruzada entre `brief-fase3-backend-only.md` e estado atual do código.

> **Atenção executor:** Este documento é a fonte canônica de execução da Fase 3.
> O brief original contém 7 colisões críticas de revision ID de migrations
> (Sprints 12–18). Use **exclusivamente os IDs deste plano**, não os do brief.

---

## Resumo das divergências encontradas

| # | Sprint | Tipo | Descrição |
|---|--------|------|-----------|
| 1 | 12 | **BLOQUEADOR** | Revision ID `f1g2h3i4j5k6` já existe em `f1g2h3i4j5k6_create_password_reset_tokens.py` |
| 2 | 13 | **BLOQUEADOR** | Revision ID `g1h2i3j4k5l6` já existe em `g1h2i3j4k5l6_seed_template_password_reset_existing_tenants.py` |
| 3 | 14 | **BLOQUEADOR** | Revision ID `h1i2j3k4l5m6` já existe em `h1i2j3k4l5m6_enable_rls_policies.py` |
| 4 | 15 | **BLOQUEADOR** | Revision ID `i1j2k3l4m5n6` já existe em `i1j2k3l4m5n6_rls_remaining_tables.py` |
| 5 | 16 | **BLOQUEADOR** | Revision ID `j1k2l3m4n5o6` já existe em `j1k2l3m4n5o6_add_last_password_change_at.py` |
| 6 | 17 | **BLOQUEADOR** | Revision ID `k1l2m3n4o5p6` já existe em `k1l2m3n4o5p6_add_tenant_fee_routing_policies.py` |
| 7 | 18 | **BLOQUEADOR** | Revision ID `l1m2n3o4p5q6` já existe em `l1m2n3o4p5q6_drop_fee_routing_policy_id_from_tenant_configs.py` |
| 8 | 15 | **BLOQUEADOR** | Payment sem campo `subscription_id` — o handler `payment.confirmed` não consegue identificar qual assinatura renovar sem vínculo explícito |
| 9 | 14 | **AJUSTE** | Brief menciona "verificar se Payment.appointment_id está vinculado a PackagePurchase" — a lógica correta é buscar `PackagePurchase` por `payment_id`, não por `appointment_id` |
| 10 | 11 | **AJUSTE** | `Service.duration` (coluna existente) vs `duration_min` (nome usado em variantes e return value de `get_effective_price`) — padrão inconsistente; solução: usar `service.duration` ao montar o tuple retornado |
| 11 | 17 | **AJUSTE** | `products.stock` já existe (adicionado em `d1e2f3g4h5i6`). Migration Sprint 17 deve usar `ADD COLUMN IF NOT EXISTS` apenas para `stock_min_alert` e `unit`; não tentar adicionar `stock` novamente |
| 12 | 12 | **OBSERVAÇÃO** | O brief usa `handle_commission_paid` com `account_id` como parâmetro, mas `create_payout` já determina `account_id` internamente. Manter conforme especificado — FinancialCoreEngine recebe account_id explicitamente para permitir composição futura |
| 13 | 15 | **OBSERVAÇÃO** | `expense_recurrence_worker` (Sprint 18) e `subscription_renewal_worker` (Sprint 15) ambos agendados para 06:00 — sem conflito pois são tasks independentes no Celery |
| 14 | 14 | **OBSERVAÇÃO** | O fluxo `payment.confirmed → activate()` cria CustomerCredit fora da transação principal; Commission PACKAGE_SOLD também fora da transação. Alinhado com padrão da Fase 2 (best-effort após commit) |

---

## Sprint 11 — Catálogo opt-ins

### Estado de entrada verificado

- **HEAD migration:** `d1e2f3g4h5i6` (align_orm_schema_gaps)
- **Modelos existentes usados:** `Service`, `CompanyProfile`, `AppointmentService`, `Professional`
- **Serviços existentes modificados:** `app/modules/services/service.py`, `app/modules/availability/service.py`, `app/modules/public/service.py`, `app/modules/company_profile/service.py`

### Gaps e ajustes em relação ao brief

**O que já existe (NÃO fazer):**
- `Service.duration` existe — não criar coluna `duration_min`; usar `duration` como sinônimo no código (a coluna se chama `duration`, o campo na variante/override se chama `duration_min` — no `get_effective_price`, retornar `service.duration` como segundo elemento)
- `AppointmentService.service_id` já é nullable no ORM — o ajuste é apenas na FK constraint do banco (ON DELETE SET NULL)

**O que o brief omite mas é necessário:**
- Atualizar `AppointmentService` ORM para `ForeignKey("services.id", ondelete="SET NULL")` além da migration
- Schemas Pydantic de resposta para `ServiceVariant` e `ServicePricingOverride` (o brief lista endpoints mas não schemas explícitos)
- `booking/router.py` e `public/router.py` precisam ser atualizados para aceitar `professional_id` query param em `GET /booking/{slug}/services`

**Colisões:** **SIM** — `e1f2g3h4i5j6` já está em uso por `add_asaas_customer_id_to_customers` (Sprint de Integrações, commitado em 2026-06-04). Sprint 11 passa a usar `e2f3g4h5i6j7`.

### Ordem de implementação

1. **Migration** `e2f3g4h5i6j7_catalog_optins` (conforme brief — sem alteração)
2. **Modelos ORM:**
   - `app/infrastructure/db/models/service.py`: adicionar `preparation_minutes_before`, `preparation_minutes_after`
   - `app/infrastructure/db/models/service.py`: novas classes `ServicePricingOverride`, `ServiceVariant`
   - `app/infrastructure/db/models/company_profile.py`: adicionar `business_hours_structured` (JSONB via `postgresql.JSONB`)
   - `app/infrastructure/db/models/appointment.py`: `AppointmentService.service_id` → `ForeignKey("services.id", ondelete="SET NULL")`
3. **Services:**
   - `app/modules/services/service.py`: adicionar `get_effective_price(service_id, professional_id, variant_id, company_id, db)`
   - `app/modules/services/service.py`: CRUD de `ServiceVariant` e `ServicePricingOverride`
4. **Integração com disponibilidade:**
   - `app/modules/availability/service.py`: substituir `duration = service.duration` por `duration, _ = get_effective_price(service_id, professional_id=None, ..., company_id, db)` considerando `preparation_minutes_before + duration + preparation_minutes_after`
5. **Integração com BookingFlow:**
   - `app/modules/public/service.py` ou `app/modules/booking/`: endpoint `GET /booking/{slug}/services?professional_id=` chama `get_effective_price`
6. **CompanyProfile:**
   - `app/modules/company_profile/service.py`: aceitar e validar `business_hours_structured`
   - `app/modules/company_profile/schemas.py`: Pydantic com validador weekday 0-6 e formato HH:MM
7. **Router + endpoints** (ver brief — 8 endpoints novos)
8. **Registro em main.py:** incluir routers novos (variants_router, overrides_router)
9. **Testes:** `tests/test_sprint11_catalog.py`

### Riscos identificados

- `availability/service.py` atualmente usa `service.duration` diretamente em `get_available_slots`. A refatoração para considerar `preparation_minutes` é cirúrgica mas pode afetar o BookingFlow (booking WhatsApp também usa disponibilidade). Testar regressão.
- `GET /booking/{slug}/services` está em `public/router.py` (sem auth) — adicionar `professional_id` como query param opcional não quebra clientes existentes.

### Prompt de execução — Sprint 11

```
Implementar Sprint 11 da Fase 3 (Catálogo opt-ins).

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md (convenções críticas)
  2. agendamento_engine/docs/brief-fase3-backend-only.md (seção Sprint 11)
  3. agendamento_engine/docs/plano-execucao-fase3.md (esta seção)
  4. agendamento_engine/app/infrastructure/db/models/service.py
  5. agendamento_engine/app/infrastructure/db/models/company_profile.py
  6. agendamento_engine/app/infrastructure/db/models/appointment.py
  7. agendamento_engine/app/modules/availability/service.py
  8. agendamento_engine/app/modules/services/service.py

Escopo:
  DO: migration e2f3g4h5i6j7, modelos ServicePricingOverride + ServiceVariant,
      campos preparation_minutes_before/after em Service, business_hours_structured
      em CompanyProfile, get_effective_price, integração com availability,
      integração com booking/public services, fix FK AppointmentService,
      endpoints de variantes e overrides, testes.
  NÃO FAZER: nenhum arquivo em painel/, nenhum Sprint além do 11.

Notas técnicas críticas:
  - Service.duration é o nome da coluna existente (não duration_min). Em
    get_effective_price retornar (price, duration_minutes) onde o terceiro
    fallback usa service.duration.
  - AppointmentService.service_id: atualizar tanto o ORM (ondelete="SET NULL")
    quanto a migration (DROP CONSTRAINT + ADD CONSTRAINT ON DELETE SET NULL).
  - availability/service.py: bloco ocupado = prep_before + duration + prep_after.
    Não alterar a assinatura pública de get_available_slots (adicionar lógica
    internamente para quando o serviço tiver campos de preparo).
  - business_hours_structured validator: weekday deve ser 0-6, open/close no
    formato "HH:MM"; HTTP 422 se inválido.
  - RLS: service_pricing_overrides e service_variants precisam de
    CREATE POLICY + ENABLE ROW LEVEL SECURITY (ver migration no brief).

Casos de teste obrigatórios (conforme brief Sprint 11):
  - get_effective_price: variant > override > base (3 caminhos)
  - Slot com prep_before=15, duration=30, prep_after=10 → bloco 55min
  - business_hours_structured salvo e retornado
  - PATCH /companies/profile com weekday=7 → 422
  - DELETE service → appointment_services.service_id = NULL (não CASCADE)
  - Override UNIQUE(professional_id, service_id): segundo POST → 409
  - Cross-tenant: overrides e variantes isolados

Sinal de conclusão: pytest tests/test_sprint11_catalog.py -v → todos passando.
```

---

## Sprint 12 — CommissionEngine

### Estado de entrada verificado

- **HEAD migration no início:** `e2f3g4h5i6j7` (após Sprint 11)
- **Modelos existentes usados:** `Appointment`, `Professional`, `Account`, `Movement`, `Entry`
- **Serviços existentes modificados:** `app/modules/financial_core/service.py` (adicionar `handle_commission_paid`)
- **Handlers existentes:** `agenda.soft_reservation.expired`, `payment.confirmed` (communication) — **nenhum** `operation.completed`

### Gaps e ajustes em relação ao brief

**Revision ID BLOQUEADOR:** ID `f1g2h3i4j5k6` do brief está ocupado por Sprint 5 (password reset tokens).
**Novo ID:** `f3g4h5i6j7k8_commission_engine`

**O que o brief omite mas é necessário:**
- `operation.completed` ainda não é publicado por nenhum código existente. Sprint 12 precisa também publicar esse evento quando o appointment muda para COMPLETED (em `appointments/service.py` ou `appointments/transitions.py`). Sem isso, o handler `operation.completed` nunca dispara.
- Schemas Pydantic completos para `CommissionPolicy`, `Commission`, `CommissionPayout`
- `commission_handler.py` precisa de uma session própria (padrão do soft_reservation_handler.py — não recebe `db` de fora, abre SessionLocal internamente)

**O que já existe (verificado):**
- `EntryCategory.COMISSAO_SERVICO`, `COMISSAO_VENDA`, `COMISSAO_RENOVACAO`, `COMISSAO_PERSONALIZADA` — existem em `entry_category.py`. ✅
- `CATEGORY_TO_ENTRY_TYPE` já mapeia todos os tipos COMISSAO → "COMISSAO". ✅

### Ordem de implementação

1. **Migration** `f3g4h5i6j7k8_commission_engine` (SQL conforme brief, apenas com novo revision ID)
2. **Modelos ORM:** `CommissionPolicy`, `CommissionPayout`, `Commission` em `app/infrastructure/db/models/`
3. **Services:**
   - `app/modules/commission/service.py`: `calculate_commission`, `mark_due`, `create_payout`, `reverse_commission`
   - `app/modules/financial_core/service.py`: adicionar `handle_commission_paid(payout_id, amount, account_id, professional_id, company_id, db)`
4. **Publicação de `operation.completed`** em `appointments/transitions.py` ou `appointments/service.py`: quando status → COMPLETED, emitir evento via EventBus com `{appointment_id, professional_id, service_id, gross_amount, provider_fee, company_id}`
5. **Handler** `app/workers/handlers/commission_handler.py`: `handle_operation_completed` com `register_handlers()`
6. **Registrar no lifespan** (`app/main.py`): importar e chamar `register_commission_handlers()`
7. **Router + endpoints** `app/modules/commission/router.py` (9 endpoints conforme brief)
8. **Registro no main.py:** incluir commission_router
9. **Testes** `tests/test_sprint12_commissions.py`

### Riscos identificados

- `handle_commission_paid` em FinancialCoreEngine usa `_record_movement` + `_record_entry` internamente — mesma estrutura de `handle_payment_confirmed`. Não há risco de quebrar testes existentes se os parâmetros forem adicionados como função nova (não altera funções existentes).
- O handler `operation.completed` precisa de `db` session própria (assim como `soft_reservation_handler`). Garantir que não usa asyncio.create_task.
- `create_payout` é operação financeira crítica (Movement + Entry). Deve estar na mesma transação que as atualizações de Commission.status.

### Prompt de execução — Sprint 12

```
Implementar Sprint 12 da Fase 3 (CommissionEngine).

Pré-requisito: Sprint 11 concluído (migration e2f3g4h5i6j7 aplicada).

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md
  2. agendamento_engine/docs/brief-fase3-backend-only.md (seção Sprint 12)
  3. agendamento_engine/docs/plano-execucao-fase3.md (esta seção)
  4. agendamento_engine/app/modules/financial_core/service.py
  5. agendamento_engine/app/workers/handlers/soft_reservation_handler.py
     (padrão para novos handlers)
  6. agendamento_engine/app/modules/appointments/transitions.py
  7. agendamento_engine/app/domain/enums/entry_category.py

Escopo:
  DO: migration f3g4h5i6j7k8, modelos CommissionPolicy+Commission+CommissionPayout,
      CommissionEngine service, handle_commission_paid em FinancialCoreEngine,
      handler operation.completed, publicar operation.completed nos transitions,
      endpoints, registro no lifespan/main.py, testes.
  NÃO FAZER: painel/, outros sprints.

Notas técnicas críticas:
  - Revision ID OBRIGATÓRIO: f3g4h5i6j7k8 (NÃO usar f1g2h3i4j5k6 — conflito).
  - down_revision da migration Sprint 12 = "e2f3g4h5i6j7".
  - handle_commission_paid: seguir padrão de handle_payment_confirmed —
    _record_movement OUTFLOW + _record_entry COMISSAO; category = COMISSAO_SERVICO.
  - commission_handler.py: abrir SessionLocal() própria (ver soft_reservation_handler.py).
    Não receber db como parâmetro do EventBus.
  - operation.completed NÃO é emitido em lugar nenhum atualmente. Adicionar em
    appointments/transitions.py quando status → COMPLETED via EventBus.publish.
  - create_payout: record_sensitive_action obrigatório (ver create_manual_adjustment
    como referência de como usar SensitiveAuditContext).
  - reverse_commission: também precisa de record_sensitive_action.

Casos de teste obrigatórios:
  - GROSS_SERVICE + BEFORE_FEES + 40%: gross=100 → commission=40
  - AFTER_FEES + 40%: gross=100, fee=2 → commission=39.20
  - CUSTOM_AMOUNT: fixed_amount=25 → commission=25
  - Prioridade de política: (prof+serv) > (prof) > (serv) > (global) > None
  - Sem política ativa → None (sem erro)
  - create_payout: Movement OUTFLOW + Entry COMISSAO atômicos
  - operation.completed → Commission CALCULATED criada (best-effort)
  - Cross-tenant isolation

Sinal de conclusão: pytest tests/test_sprint12_commissions.py -v → todos passando.
Suite completa sem regressões.
```

---

## Sprint 13 — CustomerCredit (Cotas)

### Estado de entrada verificado

- **HEAD migration no início:** `f3g4h5i6j7k8` (após Sprint 12)
- **Modelos existentes usados:** `Customer`, `Appointment`
- **Serviços existentes modificados:** nenhum — módulo novo isolado

### Gaps e ajustes em relação ao brief

**Revision ID BLOQUEADOR:** ID `g1h2i3j4k5l6` do brief está ocupado por Sprint 5 (seed templates).
**Novo ID:** `g3h4i5j6k7l8_customer_credit`

**O que o brief omite mas é necessário:**
- `NoCreditAvailableError` precisa ser uma exceção customizada (HTTP 422) — definir em `app/modules/customer_credit/exceptions.py`
- `consume_for_operation` verifica `subscription.status` (Sprint 15 adicionará) — por ora, só verificar `credit.status`
- Celery task `customer_credit_expiry_worker` precisa de importação no `celery_beat_entrypoint.py` para ser visível ao beat

### Ordem de implementação

1. **Migration** `g3h4i5j6k7l8_customer_credit`
2. **Modelos ORM:** `CustomerCredit`, `CustomerCreditConsumption`
3. **Exceções:** `app/modules/customer_credit/exceptions.py` com `NoCreditAvailableError`
4. **Service:** `app/modules/customer_credit/service.py`: `consume_for_operation`, `grant_cota`, `revoke`, `get_balance`
5. **Celery task:** `app/workers/tasks/customer_credit_expiry.py`
6. **Beat schedule:** adicionar `customer_credit_expiry_worker` em `workers/beat_schedule.py` (diário às 02:30)
7. **Router + endpoints** (4 endpoints conforme brief)
8. **Registro no main.py**
9. **Testes** `tests/test_sprint13_customer_credit.py`

### Riscos identificados

- `SELECT ... FOR UPDATE SKIP LOCKED` requer PostgreSQL real. Testar em staging, não apenas SQLite/mock. Provavelmente um dos 2-3 skips no pytest.
- `customer_credit_expiry_worker` usa `celery_db_context` padrão do projeto — verificar como outros tasks Celery multi-tenant fazem o scan (ver `expire_soft_reservations.py` como referência).

### Prompt de execução — Sprint 13

```
Implementar Sprint 13 da Fase 3 (CustomerCredit — Cotas).

Pré-requisito: Sprint 12 concluído (migration f3g4h5i6j7k8 aplicada).

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md
  2. agendamento_engine/docs/brief-fase3-backend-only.md (seção Sprint 13)
  3. agendamento_engine/docs/plano-execucao-fase3.md (esta seção)
  4. agendamento_engine/app/workers/tasks/expire_reservations.py
     (padrão para Celery task multi-tenant)
  5. agendamento_engine/app/workers/beat_schedule.py
  6. agendamento_engine/app/core/idempotency.py

Escopo:
  DO: migration g3h4i5j6k7l8, modelos CustomerCredit+CustomerCreditConsumption,
      service com FEFO + SELECT FOR UPDATE, NoCreditAvailableError, grant_cota,
      revoke, get_balance, Celery task expiry, beat_schedule, endpoints, testes.
  NÃO FAZER: integração com Package/Subscription (Sprint 14/15), painel/.

Notas técnicas críticas:
  - Revision ID OBRIGATÓRIO: g3h4i5j6k7l8 (NÃO usar g1h2i3j4k5l6 — conflito).
  - down_revision = "f3g4h5i6j7k8".
  - consume_for_operation: SELECT FOR UPDATE SKIP LOCKED é obrigatório.
    FEFO: ORDER BY expires_at NULLS LAST, granted_at ASC.
  - grant_cota: NÃO cria Movement/Entry — não é receita. record_sensitive_action obrigatório.
  - customer_credit_expiry_worker: scan multi-tenant (company_id=None para bypass
    RLS), depois processar por tenant. Ver expire_reservations.py como referência.
  - Celery task: registrar no celery_beat_entrypoint.py imports para visibilidade.
  - NoCreditAvailableError → HTTP 422.

Casos de teste obrigatórios:
  - FEFO: 2 créditos (30d e 60d) → consome o de 30d
  - Cota EXPIRED não é consumida → NoCreditAvailableError
  - remaining_cotas 0 → status EXHAUSTED automaticamente
  - SELECT FOR UPDATE: 2 consumos simultâneos, 1 remaining → apenas 1 sucede
  - grant_cota → sem Movement/Entry
  - expiry_worker: ACTIVE com expires_at passado → EXPIRED

Sinal de conclusão: pytest tests/test_sprint13_customer_credit.py -v → todos passando.
```

---

## Sprint 14 — Pacotes

### Estado de entrada verificado

- **HEAD migration no início:** `g3h4i5j6k7l8` (após Sprint 13)
- **Modelos existentes usados:** `Customer`, `Payment` (PaymentsEngine), `CustomerCredit`, `CommissionEngine`
- **Serviços existentes modificados:** `app/modules/payments/service.py` (extend handler `payment.confirmed`)

### Gaps e ajustes em relação ao brief

**Revision ID BLOQUEADOR:** ID `h1i2j3k4l5m6` do brief está ocupado por Sprint 3 (enable_rls_policies).
**Novo ID:** `h3i4j5k6l7m8_packages`

**Ajuste de lógica — CRÍTICO:** O brief diz "verificar se `Payment.appointment_id` está vinculado a um `PackagePurchase`". Isso está errado — a lógica correta é: após `payment.confirmed`, buscar `PackagePurchase` onde `payment_id == payment.payment_id`. O modelo `PackagePurchase` tem `payment_id UUID nullable REFERENCES payments(payment_id)`.

**O que o brief omite mas é necessário:**
- O handler `payment.confirmed` já existe para comunicação (em `communication/handlers.py`). O handler de pacotes deve ser SEPARADO, registrado como listener adicional do mesmo evento via EventBus (múltiplos listeners são suportados).
- O handler de reembolso de pacote (`payment.refunded`) também precisa ser criado para REVOGAR CustomerCredit e REVERTER Commission.

### Ordem de implementação

1. **Migration** `h3i4j5k6l7m8_packages`
2. **Modelos ORM:** `Package`, `PackagePurchase`
3. **Service:** `app/modules/packages/service.py`: `purchase`, `activate`
4. **Handler** `app/workers/handlers/package_payment_handler.py`:
   - listener `payment.confirmed` → busca PackagePurchase por `payment_id` → `activate()`
   - listener `payment.refunded` → REVOKE CustomerCredit + REVERSE Commission
5. **Registrar handlers no lifespan** (`app/main.py`)
6. **Router + endpoints** (6 endpoints conforme brief)
7. **Registro no main.py**
8. **Testes** `tests/test_sprint14_packages.py`

### Riscos identificados

- `payment.confirmed` já tem listener de comunicação. O novo listener de pacotes deve ser independente — falha no listener de pacotes NÃO deve impactar o listener de comunicação (best-effort isolado).
- `activate()` fora da transação de `payment.confirmed` segue padrão da Fase 2. Garantir que o handler trate exceções sem propagar para o EventBus.

### Prompt de execução — Sprint 14

```
Implementar Sprint 14 da Fase 3 (Pacotes).

Pré-requisitos: Sprints 12 e 13 concluídos (CommissionEngine e CustomerCredit ativos).

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md
  2. agendamento_engine/docs/brief-fase3-backend-only.md (seção Sprint 14)
  3. agendamento_engine/docs/plano-execucao-fase3.md (esta seção)
  4. agendamento_engine/app/modules/customer_credit/service.py
  5. agendamento_engine/app/modules/commission/service.py
  6. agendamento_engine/app/modules/payments/service.py
  7. agendamento_engine/app/modules/communication/handlers.py
     (padrão para handler payment.confirmed adicional)
  8. agendamento_engine/app/infrastructure/db/models/payment.py

Escopo:
  DO: migration h3i4j5k6l7m8, modelos Package+PackagePurchase, service purchase+activate,
      handler payment.confirmed (lookup por payment_id → PackagePurchase), handler
      payment.refunded (revoke crédito + reverse comissão), registro no lifespan, endpoints, testes.
  NÃO FAZER: painel/, outros sprints.

Notas técnicas críticas:
  - Revision ID OBRIGATÓRIO: h3i4j5k6l7m8 (NÃO usar h1i2j3k4l5m6 — conflito).
  - down_revision = "g3h4i5j6k7l8".
  - O brief diz "verificar se Payment.appointment_id está vinculado a PackagePurchase"
    — IGNORAR essa frase. A lógica correta: buscar PackagePurchase por payment_id.
    PackagePurchase.payment_id → payments.payment_id é o vínculo.
  - Multiple listeners: EventBus.register("payment.confirmed", handler_packages)
    NÃO substitui o handler de comunicação — adiciona um segundo listener.
  - activate() deve rodar em db session separada (pós-commit do payment.confirm).
  - Commission PACKAGE_SOLD: professional_id = seller_user_id (se for Professional).
    Se seller_user_id não for Professional (ou for None), sem comissão.
  - Reembolso: payment.refunded → CustomerCredit.status = REVOKED +
    Commission.status = REVERSED (via commission_service.reverse_commission).

Casos de teste obrigatórios:
  - purchase() → PackagePurchase PENDING_PAYMENT + Payment PENDING
  - payment.confirmed → activate() → CustomerCredit ACTIVE
  - CustomerCredit.total_cotas == package.total_cotas
  - activate() → Commission PACKAGE_SOLD calculada para seller
  - Refund → CustomerCredit REVOKED + Commission REVERSED
  - purchase() com package inativo → 422
  - Cross-tenant isolation

Sinal de conclusão: pytest tests/test_sprint14_packages.py -v → todos passando.
```

---

## Sprint 15 — Assinaturas

### Estado de entrada verificado

- **HEAD migration no início:** `h3i4j5k6l7m8` (após Sprint 14)
- **Modelos existentes usados:** `Customer`, `Payment`, `CustomerCredit`
- **Serviços existentes modificados:** `app/modules/payments/service.py` (criar pagamentos de renovação)

### Gaps e ajustes em relação ao brief

**Revision ID BLOQUEADOR:** ID `i1j2k3l4m5n6` do brief está ocupado por Sprint 3 (rls_remaining_tables).
**Novo ID:** `i3j4k5l6m7n8_subscriptions`

**BLOQUEADOR de design — subscription_id em Payment:** O handler `payment.confirmed` para renovação de assinatura precisa saber qual `CustomerSubscription` está sendo renovada. O modelo `Payment` não tem `subscription_id`. Solução: adicionar `subscription_id UUID nullable REFERENCES customer_subscriptions(subscription_id)` à tabela `payments` como parte da migration `i3j4k5l6m7n8`. O `subscription_renewal_worker` passa `subscription_id` ao criar o Payment de renovação.

**O que o brief omite mas é necessário:**
- A migration precisa incluir `ALTER TABLE payments ADD COLUMN IF NOT EXISTS subscription_id UUID REFERENCES customer_subscriptions(subscription_id)`
- O modelo ORM `Payment` precisa ser atualizado com `subscription_id = Column(UUID, nullable=True)`
- `consume_for_operation` deve verificar `CustomerSubscription.status` para bloquear SUSPENDED (Sprint 13 não tem essa verificação — Sprint 15 adiciona)

### Ordem de implementação

1. **Migration** `i3j4k5l6m7n8_subscriptions` (inclui: tabelas `subscription_plans` + `customer_subscriptions` + `ALTER TABLE payments ADD COLUMN subscription_id`)
2. **Modelos ORM:** `SubscriptionPlan`, `CustomerSubscription`; atualizar `Payment` com `subscription_id`
3. **Atualizar `customer_credit/service.py`:** `consume_for_operation` verifica se crédito vem de assinatura SUSPENDED → NoCreditAvailableError
4. **Celery tasks:**
   - `app/workers/tasks/subscription_renewal.py`: `subscription_renewal_worker` (06:00)
   - `app/workers/tasks/subscription_overdue.py`: `subscription_overdue_worker` (08:00)
5. **Handler** `app/workers/handlers/subscription_payment_handler.py`:
   - listener `payment.confirmed` → busca CustomerSubscription por `Payment.subscription_id` → renova crédito + Entry ASSINATURA_RENOVACAO
6. **Beat schedule:** adicionar os 2 novos workers
7. **Router + endpoints** (8 endpoints conforme brief)
8. **Registro no lifespan + main.py**
9. **Testes** `tests/test_sprint15_subscriptions.py`

### Riscos identificados

- Alterar `payments` table é uma migração de tabela existente com dados em produção. Usar `ADD COLUMN IF NOT EXISTS` (nullable sem DEFAULT é seguro para ALTER TABLE em PostgreSQL).
- `subscription_renewal_worker` cria pagamentos em massa — idempotência deve ser garantida. Se o worker rodar duas vezes (falha de rede), não criar pagamento duplicado. Sugestão: verificar se já existe Payment pendente para aquela subscription com `next_billing_at` antes de criar novo.

### Prompt de execução — Sprint 15

```
Implementar Sprint 15 da Fase 3 (Assinaturas).

Pré-requisitos: Sprints 12, 13 e 14 concluídos.

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md
  2. agendamento_engine/docs/brief-fase3-backend-only.md (seção Sprint 15)
  3. agendamento_engine/docs/plano-execucao-fase3.md (esta seção — LEIA O BLOQUEADOR)
  4. agendamento_engine/app/modules/payments/service.py
  5. agendamento_engine/app/infrastructure/db/models/payment.py
  6. agendamento_engine/app/modules/customer_credit/service.py
  7. agendamento_engine/app/workers/tasks/expire_reservations.py (padrão multi-tenant)

Escopo:
  DO: migration i3j4k5l6m7n8 (tabelas subscription + ALTER TABLE payments ADD subscription_id),
      modelos SubscriptionPlan+CustomerSubscription, atualizar Payment ORM,
      subscription_renewal_worker, subscription_overdue_worker, handler payment.confirmed
      para renovação, atualizar consume_for_operation para bloquear SUSPENDED,
      beat_schedule, endpoints, testes.
  NÃO FAZER: painel/, outros sprints.

Notas técnicas críticas:
  - Revision ID OBRIGATÓRIO: i3j4k5l6m7n8 (NÃO usar i1j2k3l4m5n6 — conflito).
  - down_revision = "h3i4j5k6l7m8".
  - A migration DEVE incluir: ALTER TABLE payments ADD COLUMN IF NOT EXISTS
    subscription_id UUID REFERENCES customer_subscriptions(subscription_id).
    Sem isso, o handler payment.confirmed não consegue identificar a assinatura.
  - subscription_renewal_worker: verificar se já existe Payment PENDING para
    a subscription antes de criar novo (idempotência).
  - SUSPENDED: consume_for_operation em customer_credit/service.py deve
    verificar se credit.source_id é uma subscription SUSPENDED → NoCreditAvailableError.
  - rollover_enabled=false: expires_at = now() + cycle_days (cotas não acumulam).
  - Handler payment.confirmed para assinaturas: cria CustomerCredit novo a cada ciclo
    + Entry RECEITA category=ASSINATURA_RENOVACAO.

Casos de teste obrigatórios:
  - subscription_renewal_worker: ACTIVE + next_billing_at passado → Payment PENDING
  - payment.confirmed (sub) → CustomerCredit renovado + Entry ASSINATURA_RENOVACAO
  - rollover_enabled=false: expires_at = now()+cycle_days
  - 7d sem pagamento → OVERDUE; 30d → SUSPENDED
  - SUSPENDED → consume_for_operation bloqueado → NoCreditAvailableError
  - pause/resume/cancel flow
  - Cross-tenant isolation

Sinal de conclusão: pytest tests/test_sprint15_subscriptions.py -v → todos passando.
```

---

## Sprint 16 — Promoções e Cupons

### Estado de entrada verificado

- **HEAD migration no início:** `i3j4k5l6m7n8` (após Sprint 15)
- **Modelos existentes usados:** `Payment`, `Customer`
- **Serviços existentes modificados:** `app/modules/payments/service.py` (verificar cupom em `payment.confirmed`)

### Gaps e ajustes em relação ao brief

**Revision ID BLOQUEADOR:** ID `j1k2l3m4n5o6` do brief está ocupado (add_last_password_change_at).
**Novo ID:** `j3k4l5m6n7o8_promotions_coupons`

**O que o brief omite mas é necessário:**
- `effectuate` é chamado em `payment.confirmed` — precisa ser integrado ao handler existente ou ao service de pagamento. Recomendação: adicionar ao `payment.confirmed` handler (no service ou como listener adicional) passando `coupon_code` e `promotion_ids` que devem ser armazenados no Payment (como JSONB ou campos extras) **ou** via context externo.
  - Solução mais simples: adicionar `coupon_code VARCHAR nullable` e `applied_promotion_ids JSONB nullable` em `payments` como parte da migration Sprint 16.
- `POST /promotions/preview`: endpoint público ou autenticado? Brief diz "público ou autenticado" — usar auth opcional (depende do contexto).

### Ordem de implementação

1. **Migration** `j3k4l5m6n7o8_promotions_coupons` (tabelas promotions+coupons+coupon_redemptions + `ALTER TABLE payments ADD COLUMN coupon_code + applied_promotion_ids`)
2. **Modelos ORM:** `Promotion`, `Coupon`, `CouponRedemption`; atualizar `Payment` ORM
3. **Service:** `app/modules/promotions/service.py`: `find_eligible`, `compute_preview`, `effectuate`
4. **Handler ou integração:** `effectuate` chamado via listener `payment.confirmed` (best-effort) quando `Payment.coupon_code` não é nulo
5. **Endpoints:** `POST /promotions/preview` usa `compute_preview` sem persistir nada
6. **Endpoint de desconto manual:** `POST /payments/{id}/manual-discount` (OWNER/ADMIN)
7. **Router + registro no main.py**
8. **Testes** `tests/test_sprint16_promotions.py`

### Riscos identificados

- `compute_preview` deve ser 100% sem efeito colateral. Testar com verificação de `SELECT COUNT(*)` em `coupon_redemptions` antes e depois.
- `SELECT ... FOR UPDATE` em cupons (atomicidade de `uses_count`) — requer PostgreSQL real.

### Prompt de execução — Sprint 16

```
Implementar Sprint 16 da Fase 3 (Promoções e Cupons).

Pré-requisito: Sprint 15 concluído (migration i3j4k5l6m7n8 aplicada).

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md
  2. agendamento_engine/docs/brief-fase3-backend-only.md (seção Sprint 16)
  3. agendamento_engine/docs/plano-execucao-fase3.md (esta seção)
  4. agendamento_engine/app/infrastructure/db/models/payment.py
  5. agendamento_engine/app/modules/payments/service.py

Escopo:
  DO: migration j3k4l5m6n7o8 (tabelas + ALTER TABLE payments ADD coupon_code +
      applied_promotion_ids), modelos Promotion+Coupon+CouponRedemption,
      PromotionEngine service, effectuate via listener payment.confirmed,
      desconto manual, endpoints, testes.
  NÃO FAZER: painel/, outros sprints.

Notas técnicas críticas:
  - Revision ID OBRIGATÓRIO: j3k4l5m6n7o8 (NÃO usar j1k2l3m4n5o6 — conflito).
  - down_revision = "i3j4k5l6m7n8".
  - compute_preview NÃO persiste nada. Testar via SELECT COUNT.
  - effectuate: revalida tudo antes de persistir (promoção pode ter expirado).
  - EXCLUSIVE: maior desconto CUSTOMER_FAVORABLE.
  - CUMULATIVE: aplicação sequencial sobre valor residual.
  - uses_count SELECT FOR UPDATE evita race condition.
  - desconto manual: reason obrigatório + record_sensitive_action.

Casos de teste obrigatórios (todos do brief Sprint 16).

Sinal de conclusão: pytest tests/test_sprint16_promotions.py -v → todos passando.
```

---

## Sprint 17 — Estoque + Fornecedores + Payables

### Estado de entrada verificado

- **HEAD migration no início:** `j3k4l5m6n7o8` (após Sprint 16)
- **Modelos existentes usados:** `Product`, `Account`, `Movement`, `Entry`
- **Serviços existentes modificados:** `app/modules/financial_core/service.py` (adicionar `handle_expense_paid`)

### Gaps e ajustes em relação ao brief

**Revision ID BLOQUEADOR:** ID `k1l2m3n4o5p6` do brief está ocupado (add_tenant_fee_routing_policies).
**Novo ID:** `k3l4m5n6o7p8_stock_suppliers_payables`

**Ajuste — `products.stock` já existe:**
A migration Sprint 17 tenta `ADD COLUMN IF NOT EXISTS stock INTEGER DEFAULT 0`. Esta coluna já existe (adicionada em `d1e2f3g4h5i6`). Como usa `IF NOT EXISTS`, não causará erro — mas não é necessário incluir. Incluir apenas `stock_min_alert` e `unit`.

**O que o brief omite mas é necessário:**
- `Product` ORM precisa ser atualizado com `stock_min_alert` e `unit`
- `handle_expense_paid` valida que `category` pertence ao grupo CUSTO ou DESPESA via `CATEGORY_TO_ENTRY_TYPE` — definir lista de categorias aceitas
- `SupplierOrder` items: o brief menciona "para cada item da ordem: record_movement" mas não define tabela `supplier_order_items`. Simplificação: `receive_order` cria uma StockMovement por produto com base em `order.total_amount` (ajuste não ideal mas consistente com escopo). Alternativa: definir que `PATCH /supplier-orders/{id}/receive` recebe `{items: [{product_id, quantity}]}` no body e cria StockMovements para cada item.

### Ordem de implementação

1. **Migration** `k3l4m5n6o7p8_stock_suppliers_payables` (apenas `stock_min_alert`, `unit` nos products; tabelas stock_movements, suppliers, supplier_orders, payables, payable_installments)
2. **Modelos ORM:** `StockMovement`, `Supplier`, `SupplierOrder`, `Payable`, `PayableInstallment`; atualizar `Product` ORM
3. **Services:**
   - `app/modules/stock/service.py`: `record_movement`
   - `app/modules/suppliers/service.py`: CRUD de Supplier + SupplierOrder + `receive_order`
   - `app/modules/payables/service.py`: CRUD de Payable + Installment + `pay_installment`
   - `app/modules/financial_core/service.py`: adicionar `handle_expense_paid`
4. **Celery task:** `app/workers/tasks/stock_alert.py` (diário 07:00)
5. **Beat schedule:** adicionar `stock_alert_worker`
6. **Router + endpoints** (conforme brief — 12 endpoints)
7. **Registro no main.py**
8. **Testes** `tests/test_sprint17_stock.py`

### Riscos identificados

- `handle_expense_paid` deve aceitar categorias CUSTO e DESPESA (para Sprint 17) e apenas DESPESA (para Sprint 18). A validação diferente entre os dois sprints sugere passar a validação para quem chama, ou ter dois handlers separados. Recomendação: um único `handle_expense_paid` que valida que a categoria existe em `CATEGORY_TO_ENTRY_TYPE` (não vazia) sem restringir ao tipo.
- `receive_order` cria StockMovements por produto — definir interface clara para o body do endpoint.

### Prompt de execução — Sprint 17

```
Implementar Sprint 17 da Fase 3 (Estoque + Fornecedores + Payables).

Pré-requisito: Sprint 16 concluído.

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md
  2. agendamento_engine/docs/brief-fase3-backend-only.md (seção Sprint 17)
  3. agendamento_engine/docs/plano-execucao-fase3.md (esta seção)
  4. agendamento_engine/app/infrastructure/db/models/product.py
  5. agendamento_engine/app/modules/financial_core/service.py
  6. agendamento_engine/app/domain/enums/entry_category.py
  7. agendamento_engine/app/workers/tasks/expire_reservations.py

Escopo:
  DO: migration k3l4m5n6o7p8 (sem re-adicionar products.stock que já existe),
      modelos StockMovement+Supplier+SupplierOrder+Payable+PayableInstallment,
      handle_expense_paid em FinancialCoreEngine, services stock+suppliers+payables,
      stock_alert_worker, beat_schedule, endpoints, testes.
  NÃO FAZER: painel/, outros sprints.

Notas técnicas críticas:
  - Revision ID OBRIGATÓRIO: k3l4m5n6o7p8 (NÃO usar k1l2m3n4o5p6 — conflito).
  - down_revision = "j3k4l5m6n7o8".
  - products.stock JÁ EXISTE. Migration: ADD COLUMN IF NOT EXISTS apenas para
    stock_min_alert e unit. Não incluir stock na migration.
  - handle_expense_paid: Movement OUTFLOW + Entry (CUSTO ou DESPESA conforme category).
    Usar CATEGORY_TO_ENTRY_TYPE para determinar entry_type.
  - receive_order: body deve receber lista de itens [{product_id, quantity}].
    Criar StockMovement(type=ENTRADA, source_type=PURCHASE_ORDER) por item.
    Criar Payable vinculado à ordem (status=OPEN, category=CUSTO_OUTROS default).
  - pay_installment: mesma transação (installment PAID + handle_expense_paid).
  - stock_alert_worker: scan multi-tenant (ver expire_reservations.py).

Casos de teste obrigatórios:
  - record_movement ENTRADA: products.stock incrementado
  - record_movement SAIDA: pode ir negativo (alerta, não erro)
  - stock <= stock_min_alert → stock.below_minimum emitido
  - pay_installment → Movement OUTFLOW + Entry CUSTO atômicos
  - receive_order → StockMovement ENTRADA + Payable (mesma transação)
  - Cross-tenant isolation

Sinal de conclusão: pytest tests/test_sprint17_stock.py -v → todos passando.
```

---

## Sprint 18 — Despesas

### Estado de entrada verificado

- **HEAD migration no início:** `k3l4m5n6o7p8` (após Sprint 17)
- **Modelos existentes usados:** `Account`, `Supplier` (Sprint 17), `Movement`, `Entry`
- **Serviços existentes modificados:** nenhum — módulo novo usando `handle_expense_paid` existente

### Gaps e ajustes em relação ao brief

**Revision ID BLOQUEADOR:** ID `l1m2n3o4p5q6` do brief está ocupado (drop_fee_routing_policy_id).
**Novo ID:** `l3m4n5o6p7q8_expenses`

**O que o brief omite mas é necessário:**
- `handle_expense_paid` em `FinancialCoreEngine` já existe após Sprint 17. Sprint 18 usa mas **não** precisa criar novamente — apenas adicionar validação de que a categoria seja do grupo DESPESA (não CUSTO). Isso pode ser feito no `pay_expense` service antes de chamar o handler.
- `expense_recurrence_worker` e `expense_due_soon_worker` precisam ser importados no `celery_beat_entrypoint.py`.

### Ordem de implementação

1. **Migration** `l3m4n5o6p7q8_expenses`
2. **Modelos ORM:** `ExpenseRecurrence`, `Expense`
3. **Service:** `app/modules/expenses/service.py`: `pay_expense`, CRUD completo, `create_next_from_recurrence`
4. **Validação de categoria DESPESA** no `pay_expense` (antes de chamar `handle_expense_paid`)
5. **Celery tasks:**
   - `app/workers/tasks/expense_due_soon.py` (07:30)
   - `app/workers/tasks/expense_recurrence.py` (06:00)
6. **Beat schedule:** adicionar os 2 novos workers
7. **Router + endpoints** (10 endpoints conforme brief)
8. **Registro no main.py**
9. **Testes** `tests/test_sprint18_expenses.py`

### Riscos identificados

- `expense_recurrence_worker` e `subscription_renewal_worker` ambos às 06:00 — sem conflito (Celery tasks paralelas).
- `next_due_date` por MONTHLY com `day_of_month`: calcular corretamente fevereiro (28 dias). Usar `dateutil.relativedelta` ou lógica de clamp para dia 29-31.
- Criação da próxima Expense pós-pagamento ("fora da transação") segue padrão da Fase 2. Se falhar, o pagamento ainda é PAGO.

### Prompt de execução — Sprint 18

```
Implementar Sprint 18 da Fase 3 (Despesas).

Pré-requisito: Sprint 17 concluído (handle_expense_paid disponível em FinancialCoreEngine).

Ler antes de começar:
  1. agendamento_engine/CLAUDE.md
  2. agendamento_engine/docs/brief-fase3-backend-only.md (seção Sprint 18)
  3. agendamento_engine/docs/plano-execucao-fase3.md (esta seção)
  4. agendamento_engine/app/modules/financial_core/service.py (ver handle_expense_paid)
  5. agendamento_engine/app/domain/enums/entry_category.py
  6. agendamento_engine/app/workers/beat_schedule.py

Escopo:
  DO: migration l3m4n5o6p7q8, modelos Expense+ExpenseRecurrence, service pay_expense,
      validação categoria DESPESA, expense_due_soon_worker, expense_recurrence_worker,
      beat_schedule, endpoints, testes.
  NÃO FAZER: painel/, outros sprints. NÃO recriar handle_expense_paid (já existe).

Notas técnicas críticas:
  - Revision ID OBRIGATÓRIO: l3m4n5o6p7q8 (NÃO usar l1m2n3o4p5q6 — conflito).
  - down_revision = "k3l4m5n6o7p8".
  - pay_expense: validar que expense.category está em CATEGORY_TO_ENTRY_TYPE com
    entry_type == "DESPESA" antes de chamar handle_expense_paid → HTTP 422 se CUSTO.
  - Criação da próxima Expense pós-pagamento: FORA da transação (try/except separado).
    Falha não cancela o pagamento.
  - next_due_date MONTHLY: usar dateutil.relativedelta para lidar com meses curtos.
    Se day_of_month=31 e o próximo mês tem 30 dias, usar o último dia do mês.
  - expense_recurrence_worker: multi-tenant scan (company_id=None).
  - expense_due_soon_worker: PENDENTE com due_date entre today e today+3d.

Casos de teste obrigatórios (todos do brief Sprint 18).

Sinal de conclusão: pytest tests/test_sprint18_expenses.py -v → todos passando.
Suite completa sem regressões — garantir que handle_expense_paid não quebrou
testes do Sprint 17.
```

---

## Sumário executivo do plano

### Tabela de ordem de execução com dependências

| Sprint | Nome | Rev ID (CORRIGIDO) | Depende de | Novos arquivos (~) |
|--------|------|-------------------|------------|-------------------|
| 11 | Catálogo opt-ins | `e2f3g4h5i6j7` | HEAD atual | 8 |
| 12 | CommissionEngine | `f3g4h5i6j7k8` | Sprint 11 | 9 |
| 13 | CustomerCredit | `g3h4i5j6k7l8` | Sprint 12 | 7 |
| 14 | Pacotes | `h3i4j5k6l7m8` | S12 + S13 | 7 |
| 15 | Assinaturas | `i3j4k5l6m7n8` | S12 + S13 + S14 | 9 |
| 16 | Promoções + Cupons | `j3k4l5m6n7o8` | Sprint 15 | 7 |
| 17 | Estoque + Fornecedores | `k3l4m5n6o7p8` | Sprint 16 | 12 |
| 18 | Despesas | `l3m4n5o6p7q8` | Sprint 17 | 7 |

### Lista consolidada de revision IDs (verificados)

| Sprint | ID original (brief) | ID corrigido (USAR ESTE) | Status |
|--------|---------------------|--------------------------|--------|
| 11 | `e1f2g3h4i5j6` | `e2f3g4h5i6j7` | 🔴 Conflito corrigido (Sprint Integrações) |
| 12 | `f1g2h3i4j5k6` | `f3g4h5i6j7k8` | 🔴 Conflito corrigido |
| 13 | `g1h2i3j4k5l6` | `g3h4i5j6k7l8` | 🔴 Conflito corrigido |
| 14 | `h1i2j3k4l5m6` | `h3i4j5k6l7m8` | 🔴 Conflito corrigido |
| 15 | `i1j2k3l4m5n6` | `i3j4k5l6m7n8` | 🔴 Conflito corrigido |
| 16 | `j1k2l3m4n5o6` | `j3k4l5m6n7o8` | 🔴 Conflito corrigido |
| 17 | `k1l2m3n4o5p6` | `k3l4m5n6o7p8` | 🔴 Conflito corrigido |
| 18 | `l1m2n3o4p5q6` | `l3m4n5o6p7q8` | 🔴 Conflito corrigido |

### Handlers de evento a registrar no lifespan

| Evento | Handler | Sprint | Arquivo |
|--------|---------|--------|---------|
| `operation.completed` | `handle_operation_completed` | 12 | `workers/handlers/commission_handler.py` |
| `payment.confirmed` (pacote) | `handle_payment_confirmed_package` | 14 | `workers/handlers/package_payment_handler.py` |
| `payment.refunded` (pacote) | `handle_payment_refunded_package` | 14 | `workers/handlers/package_payment_handler.py` |
| `payment.confirmed` (assinatura) | `handle_payment_confirmed_subscription` | 15 | `workers/handlers/subscription_payment_handler.py` |
| `payment.confirmed` (promoção) | `effectuate_promotions` | 16 | `workers/handlers/promotion_payment_handler.py` |

**Handlers existentes (não alterar):**
- `agenda.soft_reservation.expired` → `soft_reservation_handler.py`
- `payment.confirmed` → `communication/handlers.py` (notificação)
- `booking_session.*` → `booking_session_handlers.py`

### Celery Beat tasks a adicionar

| Task | Schedule | Sprint | Arquivo |
|------|----------|--------|---------|
| `customer_credit_expiry_worker` | Diário 02:30 | 13 | `workers/tasks/customer_credit_expiry.py` |
| `subscription_renewal_worker` | Diário 06:00 | 15 | `workers/tasks/subscription_renewal.py` |
| `subscription_overdue_worker` | Diário 08:00 | 15 | `workers/tasks/subscription_overdue.py` |
| `stock_alert_worker` | Diário 07:00 | 17 | `workers/tasks/stock_alert.py` |
| `expense_recurrence_worker` | Diário 06:00 | 18 | `workers/tasks/expense_recurrence.py` |
| `expense_due_soon_worker` | Diário 07:30 | 18 | `workers/tasks/expense_due_soon.py` |

**Beat tasks existentes (não alterar):**
- `reminder-check` (*/10 min)
- `session-cleanup` (*/5 min)
- `idempotency-key-cleanup` (03:00)
- `booking-session-expiry-scan` (*/5 min)
- `communication-drain` (*/5 min)
- `soft-reservation-expiry-scan` (*/5 min)

### Novas tabelas por sprint

| Sprint | Novas tabelas | ALTER TABLE existente |
|--------|---------------|----------------------|
| 11 | `service_pricing_overrides`, `service_variants` | `services` (+2 cols), `company_profiles` (+1 col), `appointment_services` (fix FK) |
| 12 | `commission_policies`, `commission_payouts`, `commissions` | — |
| 13 | `customer_credits`, `customer_credit_consumptions` | — |
| 14 | `packages`, `package_purchases` | — |
| 15 | `subscription_plans`, `customer_subscriptions` | `payments` (+subscription_id) |
| 16 | `promotions`, `coupons`, `coupon_redemptions` | `payments` (+coupon_code, +applied_promotion_ids) |
| 17 | `stock_movements`, `suppliers`, `supplier_orders`, `payables`, `payable_installments` | `products` (+stock_min_alert, +unit) |
| 18 | `expense_recurrences`, `expenses` | — |
| **Total** | **21 novas tabelas** | **5 tabelas alteradas** | |

### Riscos globais da Fase 3

1. **Migrations em produção:** 5 ALTER TABLE em tabelas existentes com dados (`services`, `company_profiles`, `appointment_services`, `payments` x2, `products`). Usar `ADD COLUMN IF NOT EXISTS` e garantir que são nullable ou têm DEFAULT.

2. **Múltiplos listeners `payment.confirmed`:** Após Sprint 16, o evento terá 4 listeners (comunicação, pacote, assinatura, promoção). O EventBus in-process é best-effort — garantir que cada listener seja isolado com try/except.

3. **SELECT FOR UPDATE requer PostgreSQL real:** Sprints 13 (CustomerCredit) e 16 (cupons) usam esta feature. Testes que dependem dela serão marcados como skip em SQLite — rodar em staging com PostgreSQL antes de declarar sprint concluído.

4. **Celery workers multi-tenant:** 6 novos workers precisam de scan multi-tenant. Usar padrão de `expire_reservations.py` (company_id=None para bypass RLS, iterar por tenant).

5. **Dependência Sprint 15:** O campo `subscription_id` em `payments` é necessário para o handler identificar assinaturas. Se a migration não incluir esse campo, o Sprint 15 não é executável.

6. **EntryCategory:** As categorias de COMISSAO e DESPESA já existem em `entry_category.py`. **Não duplicar**. Sprint 12 usa `COMISSAO_SERVICO`, Sprint 17/18 usam as categorias DESPESA/CUSTO existentes.

7. **Handler `operation.completed` sem emissor:** O evento `operation.completed` não é publicado em lugar nenhum atualmente. Sprint 12 precisa tanto do handler quanto da publicação do evento nos `appointments/transitions.py`.

---

*Plano gerado em 2026-06-01 por análise cruzada entre brief-fase3-backend-only.md e estado real do repositório.*
*Próxima ação: executar Sprint 11 usando o prompt de execução desta seção.*
