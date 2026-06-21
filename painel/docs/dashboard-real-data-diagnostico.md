# Diagnóstico — Conectar o dashboard à API real

**Status:** ✅ IMPLEMENTADO 2026-06-20 (branch `feat/dashboard-dados-reais`).
**Data do diagnóstico:** 2026-06-19.
**Arquivo-alvo:** `painel/app/(dashboard)/dashboard/page.tsx`.

> **Passo 0 — resolvido como GAP.** Não há vínculo `User → Professional` no backend:
> o JWT e `GET /auth/me` expõem só `{ id, email, name, company_id, role }` (sem
> `professional_id`), e o modelo `Professional` não tem `user_id`. Logo o
> `ProfessionalDashboard` é um `EmptyState` "Perfil profissional não vinculado"
> + TODO de backend. OWNER/ADMIN e OPERATOR foram ligados a dados reais.
>
> **Notas de wiring:** `Commission` usa `commission_amount` (não `amount`);
> `/payments` é array plano filtrado client-side (status `PENDING`/`CONFIRMED`);
> `crm/alerts.at_risk_customers[]` só traz `customer_id` → nome resolvido via
> `/customers/`; limites de mês do DRE em datetime LOCAL (sem `toISOString()`)
> para não deslocar o dia nas bordas; "Caixa do dia ainda não conferido" =
> ausência de `cash-count` criado hoje (a semântica `!resolution` do diagnóstico
> não se aplica — `resolution` é sempre preenchido). Falha por seção é isolada
> (cada fetch em guard que não rejeita); falha TOTAL (zero sucessos) → `ErrorState`.

## Contexto

O dashboard está **100% mockado** (badge "Mock · Fase 0"), regressão deliberada
da Fase 0. A versão real anterior (commit `9e5e220`) derivava os KPIs client-side
a partir de `/appointments/`. Decisão de produto: **manter o design atual dividido
por papel** (OWNER/ADMIN, OPERATOR, PROFESSIONAL) e ligar cada painel a um endpoint
real.

**Não existe** endpoint agregador `/dashboard` — cada painel é um fetch próprio.
Paralelizar com `Promise.all` e disparar **apenas** os fetches do papel logado
(evita 403 quando OPERATOR/PROFESSIONAL chamam `/financial/*` ou `/crm/*`).

## OWNER / ADMIN

| Painel (mock atual) | Fonte real | Status |
|---|---|---|
| KPI "Agendamentos hoje" | `GET /appointments/?start_after&start_before` (dia) → `.length` | ✅ existe |
| KPI "Faturamento do mês" | `GET /financial/dre?date_from&date_to` → `receita_total` (ou soma de `/payments` CONFIRMED) | ✅ existe |
| KPI "Ocupação" | — (sem endpoint de capacidade vs. ocupado) | ❌ **gap backend** → manter "em breve" |
| Gráfico "Receita × Despesa × Margem" (6 meses) | `GET /financial/dre` é **período único** → 6 chamadas (1/mês) usando `receita_total`/`despesa_total`/derivar margem | ⚠️ viável com N chamadas, ou pedir endpoint de série mensal |
| Alertas "pagamentos a confirmar" | `GET /payments/?status=PENDING` → `.length` | ✅ existe |
| Alertas "estoque baixo" | `GET /stock/` → filtrar `stock <= stock_min_alert` client-side | ⚠️ derivável client-side (sem endpoint dedicado) |
| Alertas "promoção expirando" | `GET /promotions` → filtrar por data de expiração | ✅ existe |
| Pendências "payables vencendo 7d" | `GET /payables/` → filtrar `due_date` client-side | ✅ existe (filtro client-side) |
| Pendências "conciliação de caixa" | `GET /financial/movements/unreconciled` ou `/financial/cash-counts` | ✅ existe |
| Pendências "fechamento de comissão" | `GET /commission-payouts` → filtrar pendentes | ✅ existe |
| "CRM · clientes em risco" | `GET /crm/alerts` (`CrmAlertsResponse`) | ✅ existe (pronto p/ esse painel) |

## OPERATOR

| Painel | Fonte real | Status |
|---|---|---|
| KPI "Agendamentos hoje" | `GET /appointments/` (dia) | ✅ |
| KPI "Na fila" | `GET /waitlist/entries` → `.length` | ✅ |
| KPI "Caixa do dia" | `GET /financial/cash-counts` ou `/financial/movements` (dia) | ✅ |
| "Agenda do dia" | `GET /appointments/` (dia), ordenar por `start_at` | ✅ |
| "Fila de espera" | `GET /waitlist/entries` | ✅ |
| "Atendimento humano" | `GET /conversations?status=escalated` → `.length` | ✅ |
| "Cobranças pendentes" | `GET /payments/?status=PENDING` | ✅ |

## PROFESSIONAL

| Painel | Fonte real | Status |
|---|---|---|
| "Próximos atendimentos" (próprios) | `GET /appointments/` filtrado pelo profissional logado | ✅ (confirmar filtro `professional_id` no endpoint vs. client-side) |
| "Comissões do mês" (próprias) | `GET /commissions` filtrado por profissional + mês | ✅ existe |

## Gaps que exigem decisão de backend

1. **KPI Ocupação** — não há endpoint de capacidade. Manter "em breve" ou criar agregação.
2. **Série mensal do gráfico** — DRE é período único. Opções: (a) front faz 6 chamadas mensais; (b) novo endpoint `GET /financial/dre/series?months=6`. Recomendação: (a) para não bloquear; (b) como melhoria.
3. **NPS no dashboard** — `/nps` existe mas sem agregado de score; original já tinha "em breve". Manter ou agregar.

## Notas de implementação

- Substituir os arrays hardcoded (`REVENUE_SERIES`, `kpis`, agenda/alertas/CRM) por estado com `useEffect` + `api.get` (`lib/api.ts`).
- `loading` (Skeleton) e `error` (ErrorState) **por painel** — falha de um endpoint não deve derrubar o dashboard inteiro.
- Disparar só os fetches do papel logado.
- Remover o badge "Mock · Fase 0" do `PageHeader`.
- Filtros client-side (estoque baixo, payables vencendo) são aceitáveis no volume de um tenant; revisar se a base crescer.
- Endpoints confirmados em código (2026-06-19): `/financial/dre`, `/financial/movements/unreconciled`, `/financial/cash-counts`, `/crm/alerts`, `/waitlist/entries`, `/conversations`, `/payables/`, `/commissions`, `/commission-payouts`, `/stock/`, `/appointments/`, `/payments/`, `/promotions`.
