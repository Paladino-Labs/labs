# Roadmap Técnico — Paladino

## Fases de Desenvolvimento

### Fase 1 — Base Operacional ✅ (Concluída)
**Sprints 1–5 + sprints intermediários**

| Componente | Status |
|-----------|--------|
| Auth + JWT + sessão | ✅ |
| RBAC (9 papéis, anti-escalonamento) | ✅ |
| Clientes, Profissionais, Serviços, Produtos | ✅ |
| Agendamento manual + EXCLUDE CONSTRAINT | ✅ |
| Disponibilidade de slots | ✅ |
| Link público (Vitrine + BookingFlow G13, 4 steps) | ✅ |
| WhatsApp Bot (infra FSM) | ✅ |
| CommunicationService (templates, quiet hours) | ✅ |
| IntegrationCredential (Fernet) | ✅ |
| TenantConfig + ModuleActivation + TenantBranding | ✅ |
| Auditoria append-only | ✅ |
| RLS (30 tabelas) | ✅ |
| Upload (Supabase Storage) | ✅ |
| Recuperação de senha | ✅ |
| Invalidação de sessão na troca de senha | ✅ |
| ProcessedIdempotencyKey | ✅ |
| Celery + Redis (workers + beat) | ✅ |
| EventBus in-process | ✅ |

---

### Fase 2 — Financial Core + Pagamentos ✅ (Concluída)
**Sprints 6–10**

| Componente | Sprint | Status |
|-----------|--------|--------|
| TenantFeeRoutingPolicy | 6 | ✅ |
| Account + Movement (append-only) + Entry (append-only) | 6 | ✅ |
| FinancialCoreEngine | 6 | ✅ |
| Transfer + ReconciliationRecord + MovementReconciliation | 7 | ✅ |
| CashCount | 7 | ✅ |
| AsaasProvider + NullProvider | 8 | ✅ |
| CPF/CNPJ encrypted+hash+masked | 8 | ✅ |
| PaymentSource (métodos tokenizados) | 8 | ✅ |
| Subconta Asaas no onboarding | 8 | ✅ |
| PaymentsEngine FSM | 9 | ✅ |
| Webhook idempotente (dupla proteção) | 9 | ✅ |
| DepositPolicy | 9 | ✅ |
| Reservation SOFT/FIRME (EXCLUDE tstzrange) | 10 | ✅ |
| promote_to_firme atômico | 10 | ✅ |
| ScheduleException | 10 | ✅ |
| DirectOccupancy | 10 | ✅ |
| Handler agenda.soft_reservation.expired | 10 | ✅ |
| Celery Beat: expire_soft_reservations_scan | 10 | ✅ |

---

### Fase 3 — Catálogo Avançado + Comissões (Planejada)
**Sprints 11–18**

| Componente | Sprint | Status |
|-----------|--------|--------|
| ServicePricingOverride, ServiceVariant | 11 | 🔲 |
| preparation_minutes_before/after | 11 | 🔲 |
| business_hours_structured JSONB | 11 | 🔲 |
| CommissionEngine (CALCULATED→DUE→PAID) | 12 | 🔲 |
| handle_commission_paid no FinancialCoreEngine | 12 | 🔲 |
| CustomerCredit (cotas, FEFO, lifecycle) | 13 | 🔲 |
| Pacotes e Assinaturas (schema) | 14-15 | 🔲 |
| Portal do Cliente (núcleo) | 15 | 🔲 |
| Estoque completo + Fornecedores | 17 | 🔲 |
| Payable + PayableInstallment + SupplierCredit | 17 | 🔲 |
| handle_expense_paid no FinancialCoreEngine | 18 | 🔲 |
| Expense (lifecycle PENDENTE→PAGA, recorrência) | 18 | 🔲 |

---

### Fase 4 — Promoções e Fidelidade (Planejada)
**Sprints 16–17**

| Componente | Status |
|-----------|--------|
| Promotion + Coupon + CouponRedemption | 🔲 |
| DiscountApplication | 🔲 |
| apply_coupon_at_checkout | 🔲 |
| apply_manual_discount_override | 🔲 |

---

### Fase 5 — Painéis e Relatórios (Planejada)
**Sprint 19+**

| Componente | Status |
|-----------|--------|
| Dashboard DRE visual | 🔲 |
| Reconciliação visual | 🔲 |
| CashCount UI | 🔲 |
| Relatório de comissão por profissional | 🔲 |
| Portal do Cliente (completo) | 🔲 |
| Painel PLATFORM_OWNER | 🔲 |
| Onboarding self-service (Estágio 0.5) | 🔲 |

---

## Dívidas Técnicas

| Dívida | Prioridade | Fase |
|--------|-----------|------|
| `business_hours_structured JSONB` em company_profiles | Alta | Sprint 11 |
| Separar PII_ENCRYPTION_KEY de CREDENTIAL_ENCRYPTION_KEY | Alta | Antes Estágio 1 |
| Dead-letter queue Celery | Média | Fase 3 |
| asyncio.create_task coexistindo com Celery | Baixa | Monitorar 24h |
| CORS configuração produção | Alta | Antes onboarding >1 tenant |
| 2 testes de trigger (imutabilidade) em staging PostgreSQL | Média | Próximo deploy |
| Accounting mode ACCRUAL (bloqueado por trigger) | — | Estágio 1+ |

---

## Restrições do Estágio 0

Funcionalidades bloqueadas até Estágio 1 (múltiplos tenants em produção):

- `accounting_mode = ACCRUAL` — trigger de banco bloqueia
- `PLATFORM_SUPPORT`, `PLATFORM_BILLING`, `PLATFORM_READONLY` — schema only
- Bot WhatsApp do Tenant (não confundir com bot do cliente) — Estágio 1+
- Assinatura (modelo) — schema only no Estágio 0
- Consignação e jornada avançada — deferidas