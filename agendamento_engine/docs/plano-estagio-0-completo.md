# Plano de Execução — Estágio 0 Completo (Backend)
**Gerado em:** 2026-06-10 · Sessão exclusiva de planejamento — nenhum código modificado
**Fonte de verdade do produto:** `visao-estagio-0.md` (derivado de visao-produto-paladino.md v23.0)
**Insumos:** gaps-visao-vs-codigo.md · plano-execucao-fase3.md · analise-planejado-vs-executado.md · brief-fase2-financial-core-v2.md · CLAUDE.md · SPRINT-LOG.md
**Status:** ✅ APROVADO em 2026-06-11 — as 9 decisões da Seção 2 (D1–D9) foram validadas pelo owner. Plano liberado para execução a partir do Sprint I.

---

## 0. Erratas sobre gaps-visao-vs-codigo.md (verificadas em código nesta sessão)

Duas correções ao diagnóstico anterior, confirmadas por inspeção direta:

1. **DRE backend JÁ EXISTE.** `aggregate_dre()` em `financial_core/service.py:430` e `GET /financial/dre` em `financial_core/router.py:156` estão implementados desde o Sprint 6 (conforme brief-fase2 v2). O "Sprint F" proposto no escopo deste planejamento **não é necessário como sprint novo** — o DRE só ficará completo (com CUSTO/DESPESA reais) após os Sprints 17/18, e isso vira casos de teste nos DoD desses sprints + Sprint 25.
2. **Rateio 3-vias JÁ EXISTE NO SCHEMA.** `tenant_fee_routing_policies` tem `client_share/tenant_share/professional_share` com CHECK soma=100 (migration `k1l2m3n4o5p6`), modelo ORM, schemas com validação e `PUT /tenant/fee-routing/{fee_source}`. O gap real é o **comportamento** (client_share como acréscimo de preço no checkout; professional_share como desconto automático de comissão) — ver Decisão D2.

---

## 1. Resumo Executivo

**O que falta para o Estágio 0:** 15 sprints de backend, agrupados em 3 trilhas. A trilha **Domínio/Financeiro** fecha os módulos internos obrigatórios que já tinham plano (Despesas, Estoque, Promoções) mais o ExternalStatementEntry; a trilha **Identidade/Plataforma** cria o que nunca foi planejado (Identidade Paladino, Portal do Cliente backend, Painel Owner backend, link de gestão); a trilha **Relacionamento/Bot** entrega NPS, Fila, CRM, IntentClassifier e o inbox de atendimento humano. O Sprint 25 (schema-only + testes de contrato) fecha o estágio.

**Sequência linear recomendada:**
`I → 18 → 17 → 16 → E → B → A → D → C → G → H → 2.0 → 2.6 → 2.7 → 25`

**Pré-requisito de tudo:** validar as 9 decisões de produto da Seção 2.

**Estado de entrada:** HEAD migration `m5n6o7p8q9r0` (add_payment_submethod) · 68 migrations em cadeia linear · ~460+ testes · Sprints 1–15 + hotfixes concluídos.

**Convenção nova de revision IDs (obrigatória):** o esquema mnemônico alfabético (`a1b2c3...`) gerou 4 colisões documentadas e uma quinta nesta sessão (`k3l4m5n6o7p8`, reservado ao Sprint 17 no plano da Fase 3, foi consumido por `commission_fee_policy_v2`). Deste plano em diante, revision IDs usam o formato semântico **`e0s{NN}{letra}_{slug}`** (ex.: `e0s18a_expenses`) — impossível de colidir com o esquema antigo. Antes de criar qualquer migration, o executor DEVE rodar `Glob migrations/versions/{id}*` para confirmar unicidade e usar como `down_revision` o HEAD real (`alembic heads`), não o previsto neste plano.

---

## 2. Decisões de Produto — ✅ VALIDADAS em 2026-06-11 (todas as recomendações aprovadas)

| # | Decisão | Recomendação | Por quê |
|---|---------|--------------|---------|
| **D1** | Promoções: `DiscountApplication` (tabela, fiel à visão) ou JSONB simples (plano antigo)? | **Tabela DiscountApplication** | O payload de `payment.confirmed` da visão exige `discount_breakdown[]` com `application_id`, `sequence` e `base_amount_at_application`. JSONB não sustenta reversão (`promotion.application_reverted`) nem auditoria por aplicação. Custo marginal agora; retrabalho certo depois. |
| **D2** | Rateio 3-vias: ativar comportamento no Estágio 0 ou deferir? | **Deferir `client_share` formalmente para Estágio 1; não duplicar `professional_share`** | Schema + validação já existem (errata 2). `professional_share` (desconto na comissão) já é coberto pelo eixo `commission_fee_policy CUSTOM.professional_share` do Sprint 12 — implementar de novo no routing violaria o Princípio 6 (responsabilidade única). `client_share` (acréscimo no preço) mexe na precificação de checkout em 3 canais; risco alto, demanda zero do piloto. Registrar na Seção 7. |
| **D3** | Assinaturas: recorrência nativa Asaas ou renewal_worker interno? | **Manter renewal_worker interno como motor canônico do Estágio 0** | Já implementado e testado (Sprint 15); implementa exatamente o lifecycle da visão (ACTIVE/PAUSED/OVERDUE/SUSPENDED/CANCELLED com grace de 7d/30d); funciona com qualquer payment source (dinheiro, maquininha) — a recorrência nativa Asaas só cobre cobrança via gateway e tira o controle da FSM. A cobrança de cada ciclo continua podendo ser uma charge Asaas avulsa. Registrar na Seção 7. |
| **D4** | Migração de Customer para Identidade Paladino: big-bang ou aditiva? | **Aditiva** | Nova tabela `paladino_identities` (global, sem company_id) + coluna `customers.identity_id` nullable + backfill por telefone E.164. Zero breaking change; `Customer` permanece a visão tenant-scoped da identidade (anotações, classificação ficam nele — exatamente a segmentação da Parte 7 da visão). |
| **D5** | Prefixo dos endpoints do Portal do Cliente | **`/portal/*`** (não `/customer/*`) | Evita colisão semântica com `/customers/*` (tenant-facing) já existente. |
| **D6** | Auth do Portal: e-mail+senha, magic link, Google, Apple (visão lista 4) | **MVP: e-mail+senha + magic link; social login deferido para Estágio 0.5** | Social login exige apps OAuth registrados e telas de consentimento — burocracia sem valor para o piloto de barbearia. Magic link cobre o caso "cliente sem senha". Registrar na Seção 7. |
| **D7** | Painel Owner: replay de eventos no Estágio 0? | **Replay mínimo: re-dispatch de comunicações falhas apenas; replay genérico deferido** | A visão exige replay com aviso de idempotência e bloqueio para consumers financeiros. O EventBus atual é in-process sem dead-letter persistente — replay genérico exige primeiro uma tabela de eventos falhos. Escopo mínimo (re-enviar CommunicationLog FAILED) entrega o valor operacional real. |
| **D8** | Provider do IntentClassifier | **Regex primeiro; fallback LLM com modelo leve (provider a confirmar na execução do Sprint 2.0)** | A arquitetura ChainClassifier (decisão registrada no roadmap) não depende do provider. Decidir provider/modelo no sprint, com teste de custo/latência — não travar agora. |
| **D9** | Inbox de atendimento humano: dentro do Sprint I (dívidas) ou trilha bot? | **Sprint próprio (2.7) na trilha bot** | É feature nova (endpoints de conversas + persistência de mensagens + estado RESOLVIDA), não dívida. Agrupar com 2.6 aproveita o contexto do bot_service. |

---

## 3. Sprints Existentes Ajustados

> Os Sprints 16–18 reaproveitam os briefs da Fase 3 (`brief-fase3-backend-only.md` + `plano-execucao-fase3.md`) com os ajustes abaixo. **A ordem foi invertida (18 → 17 → 16)** por dependência crescente, o que move `handle_expense_paid` do Sprint 17 para o 18.

---

### Sprint 18 — Despesas + recorrência

**Objetivo:** ExpensesService completo (lifecycle PENDENTE→PAGA|CANCELLED, recorrência, workers de vencimento) — primeiro módulo da fila por ter dependência mínima.
**Dependências:** Financial Core ✅ (nenhum sprint pendente).
**Arquivos principais:** `app/modules/expenses/` (novo) · `financial_core/service.py` (**criar `handle_expense_paid` aqui** — ajuste vs. plano antigo, que o punha no Sprint 17) · `workers/tasks/expense_due_soon.py`, `expense_recurrence.py` · `workers/beat_schedule.py`
**Migrations:** `e0s18a_expenses` (tabelas `expenses`, `expense_recurrences`; RLS em ambas)
**DoD mínimo:**
- [ ] Expense CRUD com lifecycle PENDENTE → PAGA | CANCELLED; categorias DESPESA do `entry_category.py` (validação: categoria CUSTO → 422)
- [ ] `pay_expense` → `handle_expense_paid` → Movement OUTFLOW + Entry DESPESA atômicos
- [ ] Recorrência MONTHLY com clamp de fim de mês (`dateutil.relativedelta`); próxima Expense criada FORA da transação de pagamento
- [ ] Vínculo opcional a fornecedor preparado (FK nullable que o Sprint 17 ativa — coluna `supplier_id UUID` sem FK até suppliers existir, FK adicionada na migration do 17)
- [ ] Workers `expense_due_soon` (07:30, janela 3 dias — default da visão) e `expense_recurrence` (06:00) no beat
- [ ] Eventos `expense.created/due_soon/overdue/paid/cancelled` com idempotency keys padrão B (`expense.due_soon:{id}:{n}_days`)
**Testes obrigatórios:** pay_expense atômico · categoria CUSTO rejeitada · recorrência day_of_month=31 em fevereiro · falha na próxima Expense não cancela pagamento · DRE: Entry DESPESA aparece em `aggregate_dre` · cross-tenant

---

### Sprint 17 — Estoque + Fornecedores + Payables

**Objetivo:** StockEngine com custo médio ponderado, fornecedores, Payables com installments e os quatro fatos econômicos separados (Financial-1).
**Dependências:** Sprint 18 (`handle_expense_paid` existente) · Financial Core ✅ · Pagamentos ✅
**Arquivos principais:** `app/modules/stock/`, `app/modules/suppliers/`, `app/modules/payables/` (novos) · `infrastructure/db/models/{stock_movement,supplier,supplier_order,payable,payable_installment}.py` · `workers/tasks/stock_alert.py`, `payable_due.py`
**Migrations:** `e0s17a_stock_suppliers_payables` (tabelas `stock_movements`, `suppliers`, `supplier_orders`, `payables`, `payable_installments`; `products` + `stock_min_alert`, `unit` — **NÃO re-adicionar `stock`, já existe**; FK `expenses.supplier_id`)
**DoD mínimo:**
- [ ] `record_movement` com saídas `VENDA | USO_INTERNO | PERDA | AJUSTE`; entrada incrementa `quantity_on_hand` e **recalcula custo médio ponderado** (campo `avg_cost` em products — exigência explícita da visão, ausente do plano antigo)
- [ ] `stock.entry_recorded` cria Payable, **sem** Entry CUSTO (Financial-1: receber ≠ reconhecer custo)
- [ ] `stock.consumed/sold/loss_recorded` → Entry CUSTO (categorias INSUMOS_USO_INTERNO / PRODUTO_VENDIDO / PERDA_ESTOQUE) **sem Movement** (cash flow foi na compra) — valorizado a custo médio
- [ ] `stock.adjusted` → Entry AJUSTE category=CONTAGEM_ESTOQUE + audit com notes obrigatório
- [ ] Payable lifecycle OPEN → PARTIALLY_PAID → PAID | CANCELLED; `pay_installment` atômico (Movement OUTFLOW, sem Entry — origem stock_purchase)
- [ ] `receive_order` recebe `{items: [{product_id, quantity, unit_cost}]}` → StockMovements + Payable na mesma transação
- [ ] Supplier: cadastro mínimo (nome + contato); desativável, nunca apagado (Princípio 10)
- [ ] Workers: `stock_alert` (07:00) e `payable_due` (due_soon/overdue — exigência da visão, ausente do plano antigo)
- [ ] Venda com estoque zerado: permitida se tenant configurar (default: controlado)
**Testes obrigatórios:** custo médio recalculado em 2 entradas com custos diferentes · entrada → Payable sem Entry · consumo → Entry CUSTO sem Movement · pay_installment atômico · stock ≤ min_alert → evento · DRE com CUSTO correto · cross-tenant

---

### Sprint 16 — Promoções e Cupons (fidelidade elevada — Decisão D1)

**Objetivo:** PromotionEngine com preview sem efeito colateral, efetivação revalidada no `payment.confirmed`, DiscountApplication rastreável e desconto manual auditado.
**Dependências:** Pagamentos ✅ · Operações ✅ · Sprint 15 ✅ (condições de ciclo de assinatura)
**Arquivos principais:** `app/modules/promotions/` (novo) · `workers/handlers/promotion_payment_handler.py` · `workers/tasks/promotions_expiry.py` · `payments/service.py` (transporte de coupon_code)
**Migrations:** `e0s16a_promotions_coupons` (tabelas `promotions`, `coupons`, `coupon_redemptions`, **`discount_applications`**; `payments` + `coupon_code VARCHAR` nullable)
**DoD mínimo:**
- [ ] Promotion conforme visão: `discount_type` (PERCENTAGE/FIXED_AMOUNT/OVERRIDE_PRICE/FREE_ITEM), `application_mode` (AUTOMATIC/COUPON_REQUIRED), `cumulative`, `priority`, limits, conditions (incl. `subscription_cycle_number_in/_min/_max` como condição — nota v16 da visão), status DRAFT/ACTIVE/PAUSED/EXPIRED/CANCELLED
- [ ] Coupon com `generation_type` (BULK/SINGLE_USE/PER_CUSTOMER), `coupon_reopen_policy` (NEVER_REOPEN default), `generate_bulk` (OWNER/ADMIN)
- [ ] `compute_preview`: zero efeito colateral (testado por COUNT antes/depois); algoritmo da visão (elegíveis → cumulative vs exclusive → CUSTOMER_FAVORABLE → sequência sobre gross_catalog_amount)
- [ ] `effectuate` no handler de `payment.confirmed`: revalida tudo; cria DiscountApplication (com `sequence`, `base_amount_at_application`) + CouponRedemption; `uses_count` com SELECT FOR UPDATE
- [ ] Promoção inválida na efetivação → modo STRICT: refund automático (registrar como caso de borda testado)
- [ ] `payment.confirmed` payload passa a incluir `discount_breakdown[]`, `promotion_ids[]`, `coupon_ids[]` (formato da Parte 5 da visão)
- [ ] `POST /payments/{id}/manual-discount` (manual_discount_override): reason obrigatório + record_sensitive_action + `manual_override_count` incrementado
- [ ] Worker `promotions_expiry_scanner` (move Promotion/Coupon → EXPIRED)
- [ ] Eventos `promotion.*` e `coupon.*` do catálogo da visão, incl. `coupon.redemption_reverted` e `promotion.application_reverted` no `payment.refunded`
**Testes obrigatórios:** preview sem persistência · exclusivas → maior desconto · cumulativas em sequência sobre residual · cupom esgotado → 422 · revalidação na efetivação (promoção pausada entre preview e confirm) · refund → redemption_reverted (+ reopen se policy) · race de uses_count (PostgreSQL real, skip em SQLite) · cross-tenant

---

### Sprint 25 — Schema-only `[SCHEMA APENAS]` + suite de testes de contrato

**Objetivo:** criar as estruturas de dados que a visão exige no schema do Estágio 0 (sem endpoint/service/tela) e a suite de testes de contrato que valida as 5 metas mínimas da Parte 10.
**Dependências:** Sprints 16, 17, 18 (as tabelas schema-only referenciam stock/products) · idealmente último sprint do plano (fechamento).
**Arquivos principais:** `migrations/versions/` · `tests/contract/` (novo diretório)
**Migrations:** `e0s25a_locations` · `e0s25b_stock_batches` (lote + `expiry_date` p/ FEFO Estágio 1) · `e0s25c_encomenda` (EncomendaOrder/Item) · `e0s25d_operation_professionals` (multi-profissional) · `e0s25e_service_input_checklists` (insumos pós-atendimento) · `e0s25f_product_extras` (`barcode`, variações complexas)
**DoD mínimo:**
- [ ] 6 migrations schema-only com RLS, **sem** endpoints/services/telas (regra explícita da visão)
- [ ] `tests/contract/`: FSM de Operações — todas as transições · conflito de agenda soft+firme concorrente · **fluxo DEPOSIT ponta a ponta** (sinal → SOFT→FIRME → saldo no COMPLETED → retenção em NO_SHOW → `commission_on_retained_deposit=false` default) · comissão dois eixos incl. CUSTOM (`professional_share`, `prior_commission_share`, `use_net_of_discount`) · idempotência dupla dos eventos críticos · DRE agregando RECEITA/CUSTO/DESPESA/TAXA/COMISSAO corretos · isolamento multi-tenant transversal
- [ ] Gaps encontrados pelos testes de contrato → corrigidos no próprio sprint ou registrados como bloqueador
**Testes obrigatórios:** a suite É o entregável; rodar contra PostgreSQL real (Supabase) além de SQLite.

---

### Sprint 2.0 — IntentClassifier (isolado)

**Objetivo:** classificador de intenção como componente isolado e testável — IA classifica, nunca gera resposta (invariante 2 do canal).
**Dependências:** nenhuma (componente isolado; trilha bot).
**Arquivos principais:** `app/modules/whatsapp/intent/` (novo: `classifier.py`, `catalog.py`, `schemas.py`) · tabela de auditoria de classificações
**Migrations:** `e0s20a_intent_classifications` (log auditável: input, intent, confidence, fonte regex|llm, tenant)
**DoD mínimo:**
- [ ] `ChainClassifier`: regex/keywords primeiro; fallback LLM quando `confidence < 0.7` (provider/modelo decididos na execução — Decisão D8); retorno `{intent, entities, confidence}`
- [ ] Catálogo de intenções dinâmico por tenant: intents habilitados conforme ModuleActivation (COMPRAR_PACOTE só se Pacotes ativo, etc.) — invariante 5
- [ ] Intenções do Estágio 0: `AGENDAR | COMPRAR_PRODUTO | COMPRAR_PACOTE | CONSULTAR | REMARCAR | CANCELAR | FALAR_COM_HUMANO`
- [ ] Toda classificação persistida (auditável — invariante 3); falha do LLM → fallback para menu (nunca trava o bot)
- [ ] ZERO integração com bot_service neste sprint
**Testes obrigatórios:** contrato do retorno · regex match não chama LLM · confidence baixa → fallback · catálogo filtrado por módulos ativos · LLM indisponível → degradação para menu

---

### Sprint 2.6 — Integração do classificador com FSM + intenções de compra

**Objetivo:** plugar o classificador no entry point do bot e implementar os fluxos COMPRAR_PRODUTO e COMPRAR_PACOTE — FSM permanece soberano (invariante 1).
**Dependências:** Sprint 2.0 · Pacotes ✅ (Sprint 14) · Produtos ✅ (Estoque/S17 recomendado antes, para baixa automática)
**Arquivos principais:** `whatsapp/bot_service.py` · `whatsapp/handlers/` (novos: `comprando_produto.py`, `comprando_pacote.py`)
**Migrations:** nenhuma prevista (estados novos em bot_sessions usam coluna state existente)
**DoD mínimo:**
- [ ] Texto livre no INICIO/MENU → classificador → FSM decide a transição (classificador nunca transiciona sozinho)
- [ ] COMPRAR_PRODUTO: produto → quantidade → pagamento → Operation PRODUCT×SALE + Payment; **verificar se o caminho PRODUCT×SALE existe em appointments/transitions — se ausente, criá-lo neste sprint** (risco registrado)
- [ ] COMPRAR_PACOTE: pacote → pagamento → `packages.purchase()` (fluxo Sprint 14 reutilizado)
- [ ] FALAR_COM_HUMANO por texto livre → state HUMANO (rota de escape sempre disponível — invariante 4)
- [ ] Formato WhatsApp respeitado: botões máx 3, listas até 10 linhas, paginação de slots
**Testes obrigatórios:** texto "quero marcar um corte" → fluxo AGENDAR · compra de produto cria Operation + Payment · compra de pacote → PackagePurchase PENDING_PAYMENT · intent de módulo inativo → resposta de indisponível · escape humano de qualquer estado

---

### Sprint 2.7 — Inbox de atendimento humano + estado RESOLVIDA (Decisão D9)

**Objetivo:** dar ao atendente do tenant a superfície backend para ver e responder conversas escaladas, e fechar o ciclo BOT_ATIVO → EM_ATENDIMENTO_HUMANO → RESOLVIDA da visão.
**Dependências:** Sprint 2.6 (ou diretamente após 2.0 — o state HUMANO já existe hoje).
**Arquivos principais:** `app/modules/conversations/` (novo) · `whatsapp/bot_service.py` (persistir mensagens; transição RESOLVIDA)
**Migrations:** `e0s27a_conversation_messages` (mensagens in/out por bot_session; RLS)
**DoD mínimo:**
- [ ] Mensagens do cliente persistidas quando state=HUMANO (e opcionalmente sempre — decidir volume)
- [ ] `GET /conversations?status=ESCALATED` · `GET /conversations/{id}/messages` · `POST /conversations/{id}/reply` (envia via CommunicationService) · `PATCH /conversations/{id}/resolve` → state RESOLVIDA → bot reassume
- [ ] Escalonamento por conversa, não global (visão); RBAC: OWNER/ADMIN/OPERATOR
- [ ] Evento `conversation.escalated` → notificação ao tenant (CommunicationService)
**Testes obrigatórios:** reply chega via canal correto · resolve → bot volta a responder · conversa de outro tenant invisível · mensagens em ordem

---

## 4. Novos Sprints (gaps de planejamento)

---

### Sprint I — Dívidas críticas de pagamento e comunicação

**Objetivo:** eliminar os riscos financeiros/operacionais ativos antes de empilhar módulos novos (regra: >3 dívidas → sprint dedicado).
**Dependências:** nenhuma. **Primeiro sprint da sequência.**
**Arquivos principais:** `payments/service.py` (refund) · `modules/communication/` + chamadas diretas a `evolution_client` espalhadas · `core/config.py` (provider de email)
**Migrations:** nenhuma prevista
**DoD mínimo:**
- [ ] `refund()` chama `provider.refund()` ANTES do estorno contábil; falha do gateway → 502 sem Movement/Entry; override `force_local=true` (OWNER, reason obrigatório, record_sensitive_action) para estornos já processados fora do sistema. PagSeguro permanece bloqueado (stub → 500, comportamento atual mantido)
- [ ] Feature flag `use_communication_service` → default True; chamadas diretas `evolution_client.send_text()` removidas; CommunicationLog passa a capturar 100% dos envios
- [ ] Email de produção: adapter para provider transacional real (SendGrid/Mailgun/Mailtrap Email API — decidir na execução por custo); Mailtrap sandbox permanece para dev
- [ ] Documentar status birthDate/subconta Asaas (backend pronto; pendência é frontend — fora deste plano)
**Testes obrigatórios:** refund com NullProvider outcome=error → nada persiste · refund ok → Movement OUTFLOW + Entry ESTORNO + chamada ao provider registrada · force_local sem reason → 422 · convite/reset de senha passam pelo adapter de email

---

### Sprint E — ExternalStatementEntry (conciliação com extrato externo)

**Objetivo:** importar extrato externo (CSV) e casar/dispensar lançamentos contra Movements — fecha o Grupo Financeiro do RBAC e a reconciliação Level 1 da visão.
**Dependências:** Financial Core ✅.
**Arquivos principais:** `app/modules/financial_core/statement_service.py` + endpoints no router existente
**Migrations:** `e0sE1_external_statement_entries` (entry importada: account_id, occurred_at, amount, direction, description, raw_line, status PENDING|MATCHED|DISMISSED, matched_movement_id nullable; RLS)
**DoD mínimo:**
- [ ] `POST /financial/statement/import` (CSV; mapeamento de colunas simples; OFX/integração bancária deferidos — Seção 7)
- [ ] Sugestão de match automático: mesmo account, |amount| igual, occurred_at ±2 dias, movement ainda não casado — apenas SUGESTÃO; confirmação é manual
- [ ] `POST /financial/statement/{id}/match` (vincula a Movement — Movement NÃO é alterado; vínculo na própria entry) · `POST /financial/statement/{id}/dismiss` (com reason)
- [ ] RBAC: import/match/dismiss OWNER/ADMIN (OPERATOR por config — conforme Parte 4); tudo auditado
- [ ] Import idempotente (hash da linha → não duplica em re-upload)
**Testes obrigatórios:** re-import do mesmo CSV não duplica · match sugere candidato correto · match de movement já casado → 409 · dismiss sem reason → 422 · cross-tenant

---

### Sprint B — Link de gestão com token único

**Objetivo:** cliente remarca/cancela agendamento sem login, via link com token enviado no WhatsApp — requisito explícito do Link Público.
**Dependências:** nenhuma técnica (Agenda ✅, Operações ✅). Escopo pequeno — pode ser encaixado em qualquer ponto ou em paralelo.
**Arquivos principais:** `appointments/` (geração do token) · `modules/public/manage_router.py` (novo, sem auth) · templates de comunicação (incluir link)
**Migrations:** `e0sB1_appointment_manage_tokens` (coluna `manage_token_hash` em appointments + índice; token cru nunca armazenado)
**DoD mínimo:**
- [ ] Token único por appointment (UUID4 cru no link; hash no banco), gerado na confirmação e incluído na mensagem de confirmação do WhatsApp
- [ ] `GET /manage/{token}` → detalhe do agendamento (sem PII além do necessário) · `POST /manage/{token}/cancel` · `POST /manage/{token}/reschedule` (consulta slots + remarca via fluxo normal da Agenda)
- [ ] **Janela decide CONSEQUÊNCIA, não permissão** (decisão transversal da visão): cancelar fora da janela é permitido, com efeito de retenção de sinal conforme DepositPolicy
- [ ] Token invalidado quando operação atinge estado terminal; rate limiting no endpoint público
- [ ] Eventos normais da FSM emitidos (cancelamento via link = transição normal com actor CLIENT)
**Testes obrigatórios:** token inválido/expirado → 404 genérico · cancel dentro/fora da janela (consequências distintas) · reschedule respeita disponibilidade · token de outro tenant inútil · rate limit ativo

---

### Sprint A — Identidade Paladino (PaladinoIdentity + PhoneIdentityResolver + ConsentRecord)

**Objetivo:** criar a identidade Paladino-wide em 3 níveis com migração aditiva do Customer existente (Decisão D4) — fundação do Portal e dos canais.
**Dependências:** nenhuma técnica; **executar antes do Sprint D e antes do crescimento da base** (backfill fica mais arriscado com volume).
**Arquivos principais:** `app/modules/identity/` (novo: `resolver.py`, `consent_service.py`, router) · `customers/service.py` (integração no create) · canais (bot/booking passam a resolver via PhoneIdentityResolver)
**Migrations:** `e0sA1_paladino_identities` (tabela GLOBAL sem company_id: identity_id, phone_e164, phone_national, name, email nullable, cpf_encrypted/hash/masked nullable — padrão PII do Sprint 8, user_id nullable p/ nível completo) · `e0sA2_consent_records` (identity_id, company_id nullable, consent_type, channel, status, source_channel, occurred_at — append-only) · `e0sA3_customers_identity_link` (`customers.identity_id` nullable + backfill)
**DoD mínimo:**
- [ ] `PhoneIdentityResolver`: input raw_phone + tenant_default_country → `phone_e164`, `phone_national_normalized`, `possible_aliases[]`, identity (DDD obrigatório; cria identity se inexistente)
- [ ] Backfill: customers existentes agrupados por telefone E.164 → mesma identity cross-tenant; colisões de nome divergente registradas para revisão manual (relatório, não bloqueio)
- [ ] **RLS/privacidade**: `paladino_identities` SEM política tenant (tabela global) — acesso exclusivamente via service layer; tenant NUNCA consulta histórico de outro tenant (queries de histórico continuam via `customers`, tenant-scoped); CPF visível só a tenants com consent explícito
- [ ] ConsentRecord append-only: GRANTED/REVOKED com source_channel; transacional capturado no fluxo; MARKETING separado e desmarcado por default
- [ ] Bot e Link Público passam a resolver identidade pelo resolver (substituindo lookup ad-hoc por telefone) — sem mudança de comportamento visível
- [ ] Upgrade leve→completo: endpoint preparado (vincula user_id à identity, **sempre com confirmação explícita** — nunca automático), consumido pelo Sprint D
**Testes obrigatórios:** mesmo telefone em 2 tenants → 1 identity, 2 customers · resolver com telefone sem DDD → 422 · backfill idempotente · consent revogado → canal bloqueado no CommunicationService (verificação no dispatch) · tenant A não enxerga dados tenant-scoped do B · CPF masked por default

---

### Sprint D — Portal do Cliente (backend)

**Objetivo:** área logada Paladino-wide do cliente final: histórico, cotas, assinaturas, consentimentos, perfil e métodos de pagamento.
**Dependências:** **Sprint A** (identidade + consents) · Pacotes/Assinaturas ✅ · Sprint B (reutiliza regras de remarcação/cancelamento).
**Arquivos principais:** `app/modules/portal/` (novo: auth, router, service) · `payment_sources` (re-vinculação a identity + autorização por tenant)
**Migrations:** `e0sD1_portal_auth` (credenciais do cliente: senha hash + magic link tokens vinculados a identity; ou reuso de `users` role=CLIENT com identity_id — decidir na execução, recomendação: reuso de users) · `e0sD2_payment_source_authorizations` (payment_sources ganha `identity_id`; nova tabela de autorização por tenant: identity_id, company_id, source_id, mode ALWAYS|ONCE, granted_at, revoked_at)
**DoD mínimo:**
- [ ] Auth: e-mail+senha + magic link (Decisão D6); JWT de cliente separado do JWT de tenant (claims distintos; sem company_id)
- [ ] `GET /portal/dashboard` (próximos agendamentos cross-tenant do cliente, cotas ativas) · `GET /portal/history` · `GET /portal/credits` · `GET /portal/subscriptions` + pause/cancel da própria assinatura **se o tenant permitir** (config)
- [ ] Remarcação/cancelamento usando as mesmas regras transversais do Sprint B
- [ ] `GET/POST /portal/consents` — gestão granular (conceder/revogar por tipo+canal)
- [ ] Métodos de pagamento: tokenização no provider (Asaas), exige consent PAYMENT_STORAGE; token vinculado à identity; autorização por tenant com modelo "Apenas esta vez | Permitir sempre | Cancelar"
- [ ] `PATCH /portal/profile` (nome/e-mail/telefone — telefone re-resolve identidade)
- [ ] Migração leve→completo: cliente cria conta → sistema oferece adotar histórico por telefone (confirmação explícita)
**Testes obrigatórios:** cliente vê histórico de TODOS os seus tenants; tenant vê só o dele · pause de assinatura bloqueada quando tenant não permite · método de pagamento sem consent PAYMENT_STORAGE → 422 · cobrança por tenant não autorizado → 403 · magic link expira e é single-use

---

### Sprint C — Painel Owner Paladino (backend)

**Objetivo:** superfície de operação da plataforma para PLATFORM_OWNER: tenants, saúde, impersonation auditada, flags e meta-audit.
**Dependências:** RBAC PLATFORM_OWNER ✅ (company_id NULL já suportado). Independente das demais trilhas.
**Arquivos principais:** `app/modules/platform/` (novo) · `companies` (status de tenant) · middleware de impersonation
**Migrations:** `e0sC1_tenant_status` (`companies.status` TRIAL|ACTIVE|SUSPENDED|CHURNED, default ACTIVE p/ existentes) · `e0sC2_impersonation_grants` (grant: platform_user_id, company_id, mode READ_ONLY|ELEVATED, reason, expires_at, revoked_at — append-only) · `e0sC3_platform_settings` (flags globais key/value)
**DoD mínimo:**
- [ ] `GET/POST/PATCH /platform/tenants` — listar, criar, suspender/reativar (suspensão bloqueia login de usuários do tenant, preserva dados)
- [ ] `GET /platform/tenants/{id}/health` — métricas mínimas: nº usuários/clientes/appointments 30d, último acesso, falhas de CommunicationLog, status de credenciais (Asaas/WhatsApp conectados)
- [ ] Impersonation (PlatformSecurity-1): grant time-boxed (default 30 min), reason obrigatório, **read-only por default**, escrita exige mode=ELEVATED + reason; toda request impersonada auditada com o grant_id; tenant vê o acesso no próprio audit
- [ ] Feature flags: por tenant via `TenantConfig.permission_overrides` (já existe) + globais via platform_settings; `GET/PUT /platform/tenants/{id}/flags`
- [ ] Audit cross-tenant: `GET /platform/audit` — o acesso ao audit é ele mesmo auditado (RBAC-4); credenciais sempre masked (RBAC-3)
- [ ] Replay mínimo (Decisão D7): `POST /platform/communications/{log_id}/redispatch` com reason; replay financeiro inexiste por design
- [ ] Todos os endpoints exigem PLATFORM_OWNER; papéis PLATFORM_SUPPORT/BILLING/READONLY permanecem schema-only
**Testes obrigatórios:** OWNER de tenant → 403 em /platform/* · suspensão bloqueia login do tenant · impersonation expirada → 403 · escrita em modo READ_ONLY → 403 · acesso ao audit gera registro de audit · tenant enxerga o impersonation no próprio audit

---

### Sprint G — NPS + Fila de espera

**Objetivo:** pesquisa pós-atendimento configurável e fila de espera orientada a eventos.
**Dependências:** Operações ✅ · Comunicação ✅ · Estoque (S17) para fila de produto (a parte de produto fica condicionada).
**Arquivos principais:** `app/modules/nps/`, `app/modules/waitlist/` (novos) · handlers de `operation.completed`, `agenda.reservation.released/cancelled`, `stock.entry_recorded`
**Migrations:** `e0sG1_nps` (nps_configs, nps_surveys, nps_responses) · `e0sG2_waitlist` (waitlist_entries + config)
**DoD mínimo:**
- [ ] NPS: trigger APENAS após `operation.completed` (nunca antes); config por tenant: canal, delay, intervalo mínimo entre pesquisas por cliente, alerta de nota baixa (notificação ao OWNER), resposta do tenant
- [ ] Envio via CommunicationService respeitando quiet hours e consent COMMUNICATION
- [ ] Fila: entrada por canal (bot/painel) com escopo (serviço/profissional/produto); consome cancelamento/remarcação que libera slot e reabastecimento de estoque
- [ ] **Antes de notificar: verificar se cliente já tem operação ativa equivalente** (regra explícita da visão)
- [ ] Lógica de prioridade configurável (default: ordem de entrada); notificação não reserva o slot (primeiro a agir leva)
**Testes obrigatórios:** survey só após COMPLETED · intervalo mínimo respeitado · nota baixa → alerta · slot liberado → notificação ao 1º da fila sem operação ativa · cliente com operação equivalente pulado · cross-tenant

---

### Sprint H — CRM básico (classificações + insights heurísticos)

**Objetivo:** classificações automáticas configuráveis e insights heurísticos simples sobre a base de clientes do tenant.
**Dependências:** Operações ✅ · Customers ✅ · (melhor depois do Sprint A — usa frequência por customer tenant-scoped, então não bloqueia).
**Arquivos principais:** `app/modules/crm/` (novo) · `customers/` (anotações, campos custom) · worker diário de classificação
**Migrations:** `e0sH1_crm` (crm_configs por tenant: thresholds; customer_classifications: customer_id, classification, computed_at, append por recomputação; `customers` + `custom_fields JSONB`, `notes` se ausentes)
**DoD mínimo:**
- [ ] Rastreio automático: frequência de visita, último atendimento, profissional/serviços preferidos, ticket médio (agregações sobre appointments/payments — sem tabela nova de fatos)
- [ ] Classificações da visão, com thresholds configuráveis: novo (1ª operação ≤ X dias), frequente (≥N em M meses), VIP (composto), em risco (sem operação > X × frequência média), recuperado
- [ ] Worker diário de recomputação (multi-tenant scan, padrão expire_reservations)
- [ ] Insights heurísticos: risco de churn, janela de retorno, sugestão de remarcação pós-cancelamento, sugestão de pacote por padrão de consumo, sugestão de produto por serviços — expostos em `GET /customers/{id}/insights` e `GET /crm/alerts` (dashboard)
- [ ] Dados curados: anotações livres + classificação manual + campos custom (nível tenant — nunca vazam para outra empresa)
- [ ] SEM ML/IA, SEM sugestão automática ao cliente sem trigger manual (deferidos pela visão)
**Testes obrigatórios:** cliente sem operação há 3× a média → "em risco" · retorno após risco → "recuperado" · thresholds custom respeitados · insights determinísticos dado o histórico · cross-tenant

---

## 5. Sequência Recomendada (linear) com Dependências

| # | Sprint | Depende de | Migration chain (down_revision = HEAD real ao iniciar) |
|---|--------|-----------|----------------------------------------------------------|
| 1 | **I** — Dívidas críticas | — | sem migration |
| 2 | **18** — Despesas | Financial Core ✅ | `e0s18a` ← `m5n6o7p8q9r0` |
| 3 | **17** — Estoque/Fornecedores/Payables | 18 (handle_expense_paid) | `e0s17a` ← `e0s18a` |
| 4 | **16** — Promoções/Cupons | Pagamentos ✅, 15 ✅ | `e0s16a` ← `e0s17a` |
| 5 | **E** — ExternalStatementEntry | Financial Core ✅ | `e0sE1` ← `e0s16a` |
| 6 | **B** — Link de gestão | Agenda ✅ | `e0sB1` ← `e0sE1` |
| 7 | **A** — Identidade Paladino | — (antes de D; antes de crescer a base) | `e0sA1..A3` ← `e0sB1` |
| 8 | **D** — Portal do Cliente | A, B | `e0sD1..D2` ← `e0sA3` |
| 9 | **C** — Painel Owner | RBAC ✅ | `e0sC1..C3` ← `e0sD2` |
| 10 | **G** — NPS + Fila | Operações ✅, Comunicação ✅, 17 (fila de produto) | `e0sG1..G2` ← `e0sC3` |
| 11 | **H** — CRM básico | Operações ✅ | `e0sH1` ← `e0sG2` |
| 12 | **2.0** — IntentClassifier | — | `e0s20a` ← `e0sH1` |
| 13 | **2.6** — Classificador + FSM + compras | 2.0, 14 ✅, 17 | sem migration prevista |
| 14 | **2.7** — Inbox humano | 2.6 | `e0s27a` ← `e0s20a` |
| 15 | **25** — Schema-only + contrato | 16, 17, 18 | `e0s25a..f` ← `e0s27a` |

> **Regra de reencadeamento:** se a execução divergir desta ordem (trilhas paralelas), o `down_revision` de cada migration é o HEAD REAL no momento (`alembic heads`), não o desta tabela. Nunca criar duas migrations com o mesmo down_revision (gera multi-head).

---

## 6. Trilhas Paralelas Possíveis

Três trilhas independentes entre si (interseções anotadas). Migrations: apenas UMA trilha cria migrations por vez, ou o executor reencadeia conforme a regra acima.

```
TRILHA 1 — Domínio/Financeiro (crítica, sequencial):
  I → 18 → 17 → 16 → E → 25*
  (*25 por último globalmente — testa o conjunto)

TRILHA 2 — Identidade/Plataforma:
  B → A → D → C
  (B é isolado e pequeno — bom primeiro sprint da trilha;
   C não depende de A/D e pode pular à frente se houver urgência operacional)

TRILHA 3 — Relacionamento/Bot:
  2.0 → 2.6 → 2.7  e  G → H
  (2.0 não depende de nada; 2.6 idealmente após 17 (Trilha 1) para
   COMPRAR_PRODUTO dar baixa em estoque; G usa 17 só para fila de produto)
```

Interseções a respeitar: **2.6 ← 17** (baixa de estoque na venda via bot) · **G(produto) ← 17** · **D ← A e B** · **25 ← 16/17/18**.

---

## 7. O que fica FORA do Estágio 0 (deferimentos formais deste plano)

Além da Parte 13 da visão (já fora), este plano deferi explicitamente — registrar como decisão de produto ao aprovar:

| Item | Deferido para | Justificativa |
|---|---|---|
| `client_share` ativo (acréscimo de preço no checkout) | Estágio 1 | Schema pronto; comportamento mexe na precificação de 3 canais sem demanda do piloto (Decisão D2) |
| `professional_share` no fee-routing como mecanismo ativo | — (coberto por outro módulo) | Já implementado no eixo `commission_fee_policy CUSTOM` — duplicar violaria Princípio 6 (Decisão D2) |
| Recorrência nativa Asaas (subscription API do gateway) | Estágio 1 (reavaliar) | renewal_worker interno cobre o lifecycle da visão com mais flexibilidade (Decisão D3) |
| Social login no Portal (Google/Apple) | Estágio 0.5 | e-mail+senha + magic link cobrem o MVP (Decisão D6) |
| OFX/integração bancária no statement import | Estágio 1 | CSV cobre a conciliação manual Level 1 |
| Replay genérico de eventos no Painel Owner | Estágio 1 | exige dead-letter persistente; re-dispatch de comunicação cobre o caso real (Decisão D7) |
| API oficial Meta Cloud como opção por tenant | Estágio 1 | Evolution global é a decisão registrada do Estágio 0 (Opção A, Sprint 5); visão prevê escolha do tenant — reavaliar com 2º tenant |
| PagSeguro Point ativação | Bloqueado | endpoints não confirmados pelo PagBank (dívida registrada) |
| Inbox: histórico completo de mensagens fora de escalonamento | Avaliar no 2.7 | volume vs. valor; persistir só conversas escaladas é o mínimo da visão |

---

## 8. Riscos Globais

1. **Identidade global × RLS** (Sprint A): `paladino_identities` sem company_id quebra o padrão de RLS do projeto. Mitigação: acesso só via service layer + testes de privacidade cross-tenant obrigatórios no DoD.
2. **Múltiplos listeners em `payment.confirmed`**: após Sprint 16 serão 5+ (comunicação, pacote, assinatura, promoção). Cada um isolado com try/except (padrão atual); Sprint 25 testa idempotência do conjunto.
3. **JWT de cliente** (Sprint D): claims distintos do JWT de tenant; erro aqui é vulnerabilidade de escopo. Revisão de segurança obrigatória no DoD.
4. **Impersonation** (Sprint C): superfície de escrita cross-tenant. Read-only por default + grant time-boxed são inegociáveis (PlatformSecurity-1).
5. **Backfill de identidade**: telefone compartilhado (familiares) gera identity colidida. Mitigação: relatório de colisões + resolução manual; nunca merge automático de nomes divergentes.
6. **Ritmo**: os Sprints 11–15 foram executados em 2 dias sem testes de contrato. Este plano amarra a validação final no Sprint 25 — **não declarar Estágio 0 fechado sem a suite de contrato verde contra PostgreSQL real.**

---

*Para aprovação. Após validar a Seção 2, executar o Sprint I usando os DoD desta página como prompt-base, mantendo o protocolo de auditoria do SPRINT-LOG.md.*
