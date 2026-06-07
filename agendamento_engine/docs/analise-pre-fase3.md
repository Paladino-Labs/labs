# Análise pré-Fase 3 — Estado atual vs. plano de execução
**Data:** 2026-06-07 · **Encoding:** UTF-8

> Esta análise foi realizada antes do início dos Sprints 11–18 para verificar
> se o estado atual do repositório está alinhado com o que o plano de execução
> pressupõe. Os diffs corretivos foram aplicados em `plano-execucao-fase3.md`.

---

## 3a — HEAD de migrations

### Cadeia reconstruída (d1e2f3g4h5i6 até HEAD)

| Revision | down_revision | Arquivo | Sprint |
|----------|--------------|---------|--------|
| `d1e2f3g4h5i6` | (anterior) | `d1e2f3g4h5i6_align_orm_schema_gaps.py` | Sprint 10 alinhamento |
| `e1f2g3h4i5j6` | `d1e2f3g4h5i6` | `e1f2g3h4i5j6_add_asaas_customer_id_to_customers.py` | Sprint Integrações |
| `psg1a2b3c4d5` | (branch lateral) | `psg1a2b3c4d5_add_pagseguro_provider.py` | Sprint Integrações |
| `f2g3h4i5j6k7` | `g3h4i5j6k7l8`←dependência | `f2g3h4i5j6k7_add_fee_calc_to_routing_policy.py` | Sprint Integrações |
| `g3h4i5j6k7l8` | `f2g3h4i5j6k7` | `g3h4i5j6k7l8_add_maquininha_pix_fee_source.py` | Sprint Integrações |
| `h2i3j4k5l6m7` | `g3h4i5j6k7l8` | `h2i3j4k5l6m7_add_name_to_users.py` | Sprint Frontend pré-req |
| `i3j4k5l6m7n8` | `h2i3j4k5l6m7` | `i3j4k5l6m7n8_add_asaas_fields_to_companies.py` | Ajuste 9 backend |
| **`j2k3l4m5n6o7`** | `i3j4k5l6m7n8` | `j2k3l4m5n6o7_fix_fee_source_names.py` | Correções produção |

**HEAD atual verificado:** `j2k3l4m5n6o7` (fix_fee_source_names)

**Divergência encontrada:** CLAUDE.md documentava `i3j4k5l6m7n8` como HEAD. A migration
`j2k3l4m5n6o7` foi criada durante os hotfixes de produção de 2026-06-07 e não estava
documentada. **Corrigido em CLAUDE.md.**

---

## 3b — Revision IDs do plano de execução

### Resultado das verificações

| Sprint | ID no plano (corrigido) | Colisão? | Arquivo conflitante |
|--------|------------------------|----------|---------------------|
| 11 | `e2f3g4h5i6j7` | ✅ Livre | — |
| 12 | `f3g4h5i6j7k8` | ✅ Livre | — |
| 13 | `g3h4i5j6k7l8` | ❌ **COLISÃO** | `g3h4i5j6k7l8_add_maquininha_pix_fee_source.py` |
| 14 | `h3i4j5k6l7m8` | ✅ Livre | — |
| 15 | `i3j4k5l6m7n8` | ❌ **COLISÃO** | `i3j4k5l6m7n8_add_asaas_fields_to_companies.py` |
| 16 | `j3k4l5m6n7o8` | ✅ Livre | — (j2k3l4m5n6o7 existe mas ID diferente) |
| 17 | `k3l4m5n6o7p8` | ✅ Livre | — |
| 18 | `l3m4n5o6p7q8` | ✅ Livre | — |

### Causa das colisões

O plano-execucao-fase3.md foi gerado em 2026-06-01 e corrigiu IDs da Fase 1.
O Sprint de Integrações (2026-06-02–04) e o Ajuste 9 (2026-06-05) usaram
exatamente os IDs "corrigidos" pelo plano para Sprints 13 e 15.

### Novos IDs atribuídos

| Sprint | ID anterior (conflito) | Novo ID |
|--------|------------------------|---------|
| 13 | `g3h4i5j6k7l8` | `g4h5i6j7k8l9` |
| 15 | `i3j4k5l6m7n8` | `i4j5k6l7m8n9` |

### Impacto em cascata dos novos IDs

| Sprint | down_revision antes | down_revision depois |
|--------|---------------------|----------------------|
| 11 | `d1e2f3g4h5i6` (antigo) | `j2k3l4m5n6o7` (HEAD real) |
| 12 | `e2f3g4h5i6j7` | `e2f3g4h5i6j7` ✅ sem mudança |
| 13 | `f3g4h5i6j7k8` | `f3g4h5i6j7k8` ✅ sem mudança (só o revision ID mudou) |
| 14 | `g3h4i5j6k7l8` (antigo) | `g4h5i6j7k8l9` |
| 15 | `h3i4j5k6l7m8` | `h3i4j5k6l7m8` ✅ sem mudança |
| 16 | `i3j4k5l6m7n8` (antigo) | `i4j5k6l7m8n9` |
| 17 | `j3k4l5m6n7o8` | `j3k4l5m6n7o8` ✅ sem mudança |
| 18 | `k3l4m5n6o7p8` | `k3l4m5n6o7p8` ✅ sem mudança |

---

## 3c — Modelos que a Fase 3 pressupõe criar

Verificação: nenhum dos modelos abaixo foi criado parcialmente em sprints posteriores
ao planejamento da Fase 3 (Sprint Integrações, Sprint Frontend, Ajuste 9, hotfixes).

| Modelo | Status |
|--------|--------|
| ServicePricingOverride | ✅ Não existe — canvas em branco |
| ServiceVariant | ✅ Não existe — canvas em branco |
| CommissionPolicy | ✅ Não existe |
| Commission | ✅ Não existe |
| CommissionPayout | ✅ Não existe |
| CustomerCredit | ✅ Não existe |
| CustomerCreditConsumption | ✅ Não existe |
| Package | ✅ Não existe |
| PackagePurchase | ✅ Não existe |
| SubscriptionPlan | ✅ Não existe |
| CustomerSubscription | ✅ Não existe |
| Promotion | ✅ Não existe |
| Coupon | ✅ Não existe |
| CouponRedemption | ✅ Não existe |
| StockMovement | ✅ Não existe |
| Supplier | ✅ Não existe |
| SupplierOrder | ✅ Não existe |
| Payable | ✅ Não existe |
| PayableInstallment | ✅ Não existe |
| Expense | ✅ Não existe |
| ExpenseRecurrence | ✅ Não existe |

**Conclusão:** canvas 100% em branco para Fase 3. Nenhum modelo parcial.

---

## 3d — Handlers de evento registrados no lifespan

### Estado atual de app/main.py (lifespan)

```python
register_booking_handlers()       # booking_session_handlers.py
register_reminder_handlers()      # appointment_reminder_handler.py
register_communication_handlers() # communication/handlers.py
register_soft_reservation_handlers() # handlers/soft_reservation_handler.py
```

### Comparação com o plano

| Handler | Arquivo | Status |
|---------|---------|--------|
| `booking_session.*` | `booking_session_handlers.py` | ✅ Registrado |
| `appointment.reminder_due` | `appointment_reminder_handler.py` | ✅ Registrado (stub) |
| `payment.confirmed` (comunicação) | `communication/handlers.py` | ✅ Registrado |
| `agenda.soft_reservation.expired` | `soft_reservation_handler.py` | ✅ Registrado |

**Handlers que a Fase 3 adicionará** (ainda não registrados — correto):
- `operation.completed` → `commission_handler.py` (Sprint 12)
- `payment.confirmed` (pacote) → `package_payment_handler.py` (Sprint 14)
- `payment.refunded` (pacote) → `package_payment_handler.py` (Sprint 14)
- `payment.confirmed` (assinatura) → `subscription_payment_handler.py` (Sprint 15)
- `payment.confirmed` (promoção) → `promotion_payment_handler.py` (Sprint 16)

**Handlers não antecipados pelo plano:** nenhum. O Sprint de Integrações
**não registrou nenhum handler adicional no lifespan** — as correções foram
em service.py e providers, não em handlers EventBus.

---

## 3e — EntryCategory e enums

### Verificação das categorias necessárias para Fase 3

| Categoria | Tipo | Verificada em entry_category.py |
|-----------|------|---------------------------------|
| `COMISSAO_SERVICO` | COMISSAO | ✅ Linha 50 |
| `COMISSAO_VENDA` | COMISSAO | ✅ Linha 51 |
| `COMISSAO_RENOVACAO` | COMISSAO | ✅ Linha 52 |
| `COMISSAO_PERSONALIZADA` | COMISSAO | ✅ Linha 53 |
| `ASSINATURA_RENOVACAO` | RECEITA | ✅ Linha 15 |
| `ASSINATURA_ADESAO` | RECEITA | ✅ Linha 14 |
| `PACOTE` | RECEITA | ✅ Linha 13 |
| Categorias DESPESA | DESPESA | ✅ 14 categorias (ALUGUEL...DESPESA_OUTROS) |
| Categorias CUSTO | CUSTO | ✅ 6 categorias (INSUMOS...CUSTO_OUTROS) |

**Conclusão:** todas as categorias necessárias para Fase 3 já existem.
`CATEGORY_TO_ENTRY_TYPE` mapeia corretamente todos os tipos. **Não duplicar.**

---

## 3f — Celery Beat schedule

### Workers existentes

| Task | Schedule | Arquivo |
|------|----------|---------|
| `reminder-check` | `*/10 min` | `reminder_worker.py` |
| `session-cleanup` | `*/5 min` | `session_cleanup_worker.py` |
| `idempotency-key-cleanup` | `03:00` | `idempotency_cleanup.py` |
| `booking-session-expiry-scan` | `*/5 min` | `booking_session_worker.py` |
| `communication-drain` | `*/5 min` | `communication_worker.py` |
| `soft-reservation-expiry-scan` | `*/5 min` | `tasks/expire_reservations.py` |

**Workers que a Fase 3 adicionará** (ainda não existem — correto):
- `customer_credit_expiry_worker` — diário 02:30 (Sprint 13)
- `subscription_renewal_worker` — diário 06:00 (Sprint 15)
- `subscription_overdue_worker` — diário 08:00 (Sprint 15)
- `stock_alert_worker` — diário 07:00 (Sprint 17)
- `expense_recurrence_worker` — diário 06:00 (Sprint 18)
- `expense_due_soon_worker` — diário 07:30 (Sprint 18)

**Conclusão:** nenhum dos workers da Fase 3 foi criado antecipadamente.
Sem risco de duplicação.

---

## Resumo das divergências e ações corretivas

| # | Tipo | Descrição | Ação |
|---|------|-----------|------|
| 1 | **CRÍTICO** | HEAD migration documentado incorreto em CLAUDE.md: `i3j4k5l6m7n8` → real é `j2k3l4m5n6o7` | Corrigido em CLAUDE.md |
| 2 | **CRÍTICO** | Sprint 11 down_revision no plano aponta para `d1e2f3g4h5i6` (desatualizado) → deve apontar para `j2k3l4m5n6o7` | Corrigido em plano-execucao-fase3.md |
| 3 | **CRÍTICO** | Sprint 13 revision ID `g3h4i5j6k7l8` em uso por `add_maquininha_pix_fee_source` | Novo ID `g4h5i6j7k8l9` em plano-execucao-fase3.md |
| 4 | **CRÍTICO** | Sprint 15 revision ID `i3j4k5l6m7n8` em uso por `add_asaas_fields_to_companies` | Novo ID `i4j5k6l7m8n9` em plano-execucao-fase3.md |
| 5 | **INFO** | Sprint 14 down_revision precisa apontar para `g4h5i6j7k8l9` (não `g3h4i5j6k7l8`) | Corrigido em plano-execucao-fase3.md |
| 6 | **INFO** | Sprint 16 down_revision precisa apontar para `i4j5k6l7m8n9` (não `i3j4k5l6m7n8`) | Corrigido em plano-execucao-fase3.md |
| 7 | OK | Nenhum modelo da Fase 3 criado parcialmente | Sem ação |
| 8 | OK | Handlers do lifespan: apenas os antecipados pelo plano | Sem ação |
| 9 | OK | EntryCategory: todas as categorias necessárias existem | Sem ação |
| 10 | OK | Beat schedule: nenhum worker da Fase 3 pré-criado | Sem ação |

---

## Verificação do brief-fase3-backend-only.md

O brief é o spec, não o plano de execução. Análise de possíveis contradições
com decisões tomadas nos sprints recentes:

| Item do brief | Decisão recente | Contradição? |
|---------------|----------------|--------------|
| "Sprint 14 — verificar se Payment.appointment_id está vinculado a PackagePurchase" | Plano já corrigiu para lookup por `payment_id` (Observação #9 do plano) | ✅ Sem conflito — plano já corrigiu |
| "289 testes passando + 3 skips" (estado de entrada) | Estado atual tem mais testes (Sprint de Integrações adicionou) | ✅ Sem conflito — brief é spec histórico |
| "HEAD migrations: d1e2f3g4h5i6" (estado de entrada) | HEAD atual é `j2k3l4m5n6o7` | ✅ Sem conflito — brief é spec, não plano |
| "O que NÃO existe (canvas em branco)" | Nenhum modelo foi criado | ✅ Canvas intacto |
| "payment.confirmed → CommunicationService" (handler) | Ainda registrado | ✅ Sem conflito |

**Conclusão:** o brief **não precisa de atualização**. Nenhuma decisão recente
contradiz as especificações do brief. As atualizações necessárias são apenas
no plano de execução (revision IDs e down_revisions).

---

*Análise gerada em 2026-06-07 antes do início dos Sprints 11–18 da Fase 3.*
