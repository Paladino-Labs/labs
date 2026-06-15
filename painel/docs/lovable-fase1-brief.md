# PALADINO — BRIEF DA FASE 1 (LOVABLE)

**Objetivo:** especificar as telas da **operação diária completa** do Painel do Tenant — detalhe de operação + transições, CRM e cotas na ficha do cliente, Inbox de atendimento humano, Fila de espera, e o ciclo de Pagamentos (lista, detalhe, deposit policies). Derivado de `painel/docs/inventario-funcional.md` (§5 tabela mestre, §7 fluxos, §9 Fase 1) e de `agendamento_engine/openapi.json` (head `e0s25f_product_extras`, 951 testes verdes).

> **Continuação da Fase 0.** O *shell* (sidebar role-aware, header, branding, guards, tokens) **já existe** — ver §2. Esta fase preenche o shell com as 9 telas abaixo. **Dados mockados** no protótipo Lovable; integração real é feita depois pelo Claude Code.

> **Escopo rígido:** apenas as 9 telas dos Blocos A–D. Nada de catálogo, financeiro profundo, estoque, promoções, pacotes, NPS, owner ou portal (ver §6).

---

## 1. Contexto do produto (herdado da Fase 0)

Paladino é uma plataforma **SaaS multi-tenant** para gestão de negócios de serviço pessoal (barbearias no piloto — vertical-âncora do Estágio 0). Stack: **Next.js 15 (App Router) · TypeScript · shadcn/ui · TailwindCSS · Lucide icons**, **Cormorant Garamond** (display) e **Inter** (corpo). RBAC do frontend **espelha** as regras de negócio mas não é a verdade — a verdade é o backend (403 → ocultar/desabilitar). Zero lógica de negócio no frontend: nenhum cálculo financeiro, nenhuma validação de FSM no cliente.

---

## 2. Shell existente — **NÃO reimplementar**

A Fase 0 já entregou (branch `feat/fase0-shell`):

- **Sidebar role-aware** (`components/Sidebar.tsx`) — 5 grupos, submenus, colapsável (`w-60 ↔ w-16`, persistido em `localStorage`), drawer mobile. Os itens **Operações**, **Clientes / CRM**, **Atendimento humano**, **Fila**, **Pagamentos** já existem e apontam para as rotas desta fase.
- **Header** — logo, toggle sidebar, nome do tenant, nome+role do usuário (`ROLE_LABELS`), tema claro/escuro, logout.
- **`(dashboard)/layout.tsx`** — guard de autenticação + branding via CSS vars + breadcrumbs.
- **Design tokens** em `globals.css` — paleta petrol/brass, tipografia, modo claro/escuro.
- **`useAuth()`** (`context/AuthContext.tsx`) — `role` (`OWNER|ADMIN|OPERATOR|PROFESSIONAL|PLATFORM_OWNER`), `companyId`, `name`, `userId`.
- **Glossários** (`lib/constants.ts`) — `ROLE_LABELS`, `PAYMENT_METHOD_LABELS`, `PAYMENT_METHOD_OPTIONS`, `FEE_SOURCE_LABELS`, `APPOINTMENT_STATUS_LABELS`, `APPOINTMENT_STATUS_VARIANT`.
- **Utils** — `formatBRL()` e `formatDateTime()` em `lib/utils.ts`.

**O protótipo Lovable produz apenas o conteúdo das páginas** (o que vai dentro de `<main>`). Não recriar sidebar, header, layout, providers ou tokens — eles são injetados pelo shell.

### Tokens e convenções (relembrete)

| Token | Valor | Uso |
|---|---|---|
| `bg-background` | `#faf9f5` | fundo de página |
| `bg-primary` / `bg-sidebar` | `#16242c` (petrol) | botões primários, sidebar |
| `text-sidebar-primary` (accent) | `#c79a5a` (brass) | destaques, item ativo |

- Tokens semânticos sempre (`bg-card`, `border-border`, `text-muted-foreground`) — **nunca** `bg-white`/`text-gray-*` nem cores hardcoded.
- Ícones **Lucide** `size={16}` `strokeWidth={1.5}` — nunca emojis.
- `h1/h2/h3` herdam Cormorant Garamond; títulos de página: `font-display text-3xl tracking-wide`.
- **Moeda:** `formatBRL()`. ⚠️ A API devolve valores monetários como **string decimal** (`"38.50"`) — converter para número antes de `formatBRL()`.
- **Datas:** `formatDateTime()` com `timeZone` explícito (timezone do tenant, fallback `America/Sao_Paulo`).
- Nomenclatura Estágio 0: `professionals` → **"Barbeiros/Profissional"**; campos ausentes na resposta → fallback `"Em breve"` (`text-xs text-muted-foreground opacity-50`), **não** mockar valores no código real.

---

## 3. Endpoints por tela

Todos exigem JWT (`HTTPBearer`) salvo indicação. **Valores monetários = string decimal.** Métodos confirmados contra `openapi.json`.

### Bloco A — `/appointments/[id]` (Detalhe de operação)
| Ação | Método + Path | Campos principais |
|---|---|---|
| Detalhe | `GET /appointments/{id}` | `id, status, financial_status, start_at, end_at, subtotal_amount, discount_amount, total_amount, services[]{service_name, price_snapshot, duration_snapshot}, professional{id,name}, customer{id,name,phone}` |
| Cancelar | `PATCH /appointments/{id}/cancel` | body `CancelRequest{reason?}` → `AppointmentResponse` |
| Remarcar | `PATCH /appointments/{id}/reschedule` | body `RescheduleRequest{start_at}` → `AppointmentResponse` |
| Concluir | `PATCH /appointments/{id}/complete` | sem body → `AppointmentResponse` (dispara cobrança/saldo) |
| Sinal/saldo (DEPOSIT) | `GET /payments` (filtrar por `appointment_id` no cliente) | sinal = Payment `provider=manual` vinculado; `net_charged_amount`, `status` (PENDING/CONFIRMED). Saldo = `total_amount − sinal confirmado` |

> ⚠️ **Não existe endpoint para "Iniciar" (IN_PROGRESS) nem "Marcar NO_SHOW"** no Estágio 0. `mark_no_show` é interno (ciclo DEPOSIT/FSM), não exposto no painel. **Prototipar esses botões visualmente desabilitados com tooltip "Em breve"** — não prometer wiring. As ações com endpoint real são **Cancelar · Remarcar · Concluir**. Não há FSM `CONFIRMED` para agendamento (isso é do Payment) — ver §5.

### Bloco B — Clientes / CRM
| Tela | Método + Path | Campos principais |
|---|---|---|
| Lista clientes | `GET /customers/` | `id, name, phone, email?, notes?, custom_fields, active`. ⚠️ **Não** traz `visit_count`/`total_spent`/classificação — renderizar como `"Em breve"` ou compor (ver nota) |
| Ficha | `GET /customers/{id}` | idem acima |
| Insights | `GET /customers/{id}/insights` | dict heurístico (Sprint H): `churn_risk` (HIGH/MEDIUM), sugestões RESCHEDULE / PACKAGE / PRODUCT |
| Classificação | `GET /customers/{id}/classification` | última + histórico (5): `NOVO, FREQUENTE, VIP, EM_RISCO, RECUPERADO, REGULAR` |
| Histórico | `GET /customers/{id}/appointments` | lista de `CustomerAppointmentItem` (ativos + concluídos + cancelados) |
| Consentimentos | `GET /customers/{id}/consents` · `POST .../grant` · `POST .../revoke` | tipos ex.: `COMMUNICATION, MARKETING, DATA_PROCESSING` (catálogo vem da API) |
| Cotas (lista) | `GET /customer-credits?customer_id=` (param **obrigatório**) | `entitlement_type, total_cotas, remaining_cotas, status, granted_at, expires_at` |
| Cotas (saldo) | `GET /customer-credits/balance?customer_id=` | `BalanceItem[]` agregado |
| Conceder cota | `POST /customer-credits/grant-cota` | body `{customer_id, total_cotas>0, expires_at?, reason*}` (**reason obrigatório**) |
| Revogar cota | `POST /customer-credits/{credit_id}/revoke` | — |
| CRM alertas | `GET /crm/alerts` | `at_risk_count, at_risk_customers[]{customer_id, days_since_last_visit, computed_at}, new_this_month, vip_count, recovered_this_week` |
| CRM classificações | `GET /crm/classifications?classification=&date_from=` | lista por cliente |
| CRM config | `GET/PUT /crm/config` | thresholds (`new_customer_days, vip_min_visits, vip_min_spend, risk_*…`) |

> **Nota de composição:** as colunas da lista de clientes (última visita, ticket médio, classificação, cotas ativas) **não vêm de um único endpoint**. No protótipo são mockadas; na integração real serão compostas a partir de `/crm/classifications` (classificação) e `/customer-credits` (cotas), com `visit_count`/`total_spent` em `"Em breve"` até o backend expor. Esta tela **não** depende de módulo inexistente — apenas de agregação client-side.

### Bloco C — Inbox e Fila
| Tela | Método + Path | Campos principais |
|---|---|---|
| Conversas | `GET /conversations?status=escalated\|resolved` (default `escalated`) | `session_id, state, phone, customer_id?, customer_name?, last_message?, escalated_at?` |
| Detalhe conversa | `GET /conversations/{session_id}` | idem (ConversationOut) |
| Mensagens | `GET /conversations/{session_id}/messages` | `direction (INBOUND/OUTBOUND), content, content_type, sender_type (CLIENT/BOT/AGENT), agent_user_id?, created_at` (ordem asc) |
| Responder | `POST /conversations/{session_id}/reply` | body `{content*}` — **422 se `state != HUMANO`** |
| Resolver | `PATCH /conversations/{session_id}/resolve` | bot reassume (RESOLVIDA → MENU na próxima mensagem) |
| Config fila | `GET/PUT /waitlist/config` | `enabled, priority_mode, notification_window_hours` |
| Entradas fila | `GET /waitlist/entries?status=&scope_type=&customer_id=` | `id, customer_id, scope_type (SERVICE/PROFESSIONAL/PRODUCT), service_id?, professional_id?, product_id?, status, priority, source_channel, notified_at?` |
| Remover da fila | `DELETE /waitlist/entries/{entry_id}` | — |

> ⚠️ **Não existe endpoint de "Notificar manualmente"** na fila — a notificação é disparada por evento (slot liberado / cancelamento). **Prototipar o botão desabilitado com "Em breve".** A ação real disponível é **Remover** (DELETE).

### Bloco D — Pagamentos
| Tela | Método + Path | Campos principais |
|---|---|---|
| Lista | `GET /payments` | `PaymentResponse[]` — ⚠️ **flat, sem paginação nem filtros no servidor** → filtrar/paginar no cliente |
| Detalhe | `GET /payments/{id}` | `payment_id, customer_id?, appointment_id?, gross_catalog_amount, discount_amount, net_charged_amount, provider_fee, payment_method, payment_submethod?, provider, status, manual_override_count, coupon_code?, created_at, paid_at?, refunded_at?` |
| Confirmar manual | `POST /payments/{id}/confirm-manual` | body `{payment_submethod?}` → response **flat** + possível `fee_warning` (taxa não configurada) |
| Desconto manual | `POST /payments/{id}/manual-discount` | body `{discount_amount>0, reason*}` — só `PENDING`; **OWNER/ADMIN** |
| Estornar | `POST /payments/{id}/refund` | body `{reason: SERVICE_FAILURE\|REGISTRATION_ERROR\|DEADLINE_POLICY\|OTHER, force_local?}` — só `CONFIRMED`; `force_local` é **OWNER-only** |
| Deposit policies (lista) | `GET /deposit-policies` | `policy_id, service_id?(null=global), deposit_type (FIXED_AMOUNT\|PERCENTAGE), deposit_value, refundable_until_hours_before, refund_on_tenant_fault, retain_on_no_show, commission_on_retained_deposit` |
| Deposit policy (CRUD) | `POST /deposit-policies` · `GET/PATCH/DELETE /deposit-policies/{id}` | mesmos campos |

---

## 4. Especificação das telas

Para cada tela: **rota · role · layout · componentes shadcn · estados · ações**.

### A1 — `/appointments/[id]` — Detalhe de operação
- **Role:** OWNER, ADMIN, OPERATOR; PROFESSIONAL só o próprio (scope — o backend filtra).
- **Layout:** detalhe em 2 colunas. Coluna principal: header com **Badge de status FSM** + cliente + horário; cards de Serviço(s), Profissional, Valores (subtotal/desconto/total). Coluna lateral (aside): card de **Sinal/Depósito** (se houver) e **histórico de transições**.
- **Componentes:** `Card`, `Badge`, `Separator`, `Button`, `Dialog` (confirmação), `Table` (serviços), `Tooltip` (botões desabilitados), `Skeleton`.
- **Estados:** *loading* (skeleton de cards); *erro* (card de erro + retry); *dados*; *vazio* não se aplica (detalhe de 1 registro → 404 se não existe).
- **Ações e feedback:**
  - **Concluir** → `Dialog` de confirmação → `PATCH /complete` → toast success "Atendimento concluído" → atualiza badge.
  - **Cancelar** → `Dialog` com campo `reason` (opcional, `Textarea`) → `PATCH /cancel` → toast.
  - **Remarcar** → `Dialog` com seletor de novo `start_at` (date+time) → `PATCH /reschedule` → toast.
  - **Iniciar** e **Marcar NO_SHOW** → botões presentes mas **`disabled`** com `Tooltip` "Em breve" (sem endpoint no Estágio 0).
  - **DEPOSIT:** se houver sinal, card mostra "Sinal pago `formatBRL(net_charged_amount)`" (badge do status do Payment) e "Saldo pendente `formatBRL(total − sinal)`". Sem sinal → ocultar card.
- **Badge FSM:** usar `APPOINTMENT_STATUS_LABELS` + cores semânticas de §5.

### B1 — `/customers` — Lista de clientes
- **Role:** OWNER, ADMIN, OPERATOR, PROFESSIONAL (view).
- **Layout:** página com título + barra de filtros + `Table` paginada.
- **Colunas:** Nome · Telefone · Última visita (`"Em breve"`) · Classificação (Badge) · Ticket médio (`"Em breve"`) · Cotas ativas (badge contagem) · ações (link para ficha).
- **Filtros:** `Select` de classificação (NOVO/FREQUENTE/VIP/EM_RISCO/RECUPERADO); `Input`/`Select` "sem visita há X dias". Filtragem client-side no protótipo.
- **Componentes:** `Table`, `Badge`, `Input`, `Select`, `Button`, `Pagination`, `Skeleton`.
- **Estados:** *vazio* ("Nenhum cliente encontrado"); *loading* (skeleton rows); *erro*; *dados*.
- **Ações:** clique na linha → `/customers/[id]`.

### B2 — `/customers/[id]` — Ficha do cliente (abas)
- **Role:** scope (OWNER/ADMIN/OPERATOR; PROFESSIONAL view dos atendidos).
- **Layout:** header com avatar (iniciais), nome, telefone, **Badge de classificação**; abaixo, `Tabs`.
- **Abas:**
  1. **Resumo** — dados + classificação + **insights heurísticos** (`GET /insights`): cards de churn risk, sugestão de remarcar/pacote/produto. Insight ausente → ocultar card.
  2. **Histórico** — `GET /{id}/appointments`, `Table` com status badge, paginada client-side.
  3. **Cotas** — `GET /customer-credits?customer_id=`, lista de cards: tipo, `remaining_cotas/total_cotas`, validade (`expires_at` ou "sem validade"), status. Botão **Conceder cota** (modal) + **Revogar** por cota.
  4. **Consentimentos** — `GET /consents`, lista de tipos com toggle/estado (GRANTED/REVOKED) + ações grant/revoke.
- **Componentes:** `Tabs`, `Card`, `Badge`, `Table`, `Dialog` (conceder cota), `Avatar`, `Switch`/`Button` (consentimentos), `Skeleton`.
- **Modal "Conceder cota":** `Input` numérico `total_cotas` (>0), `DatePicker` `expires_at` (opcional), `Textarea` `reason` (**obrigatório**) → `POST /grant-cota` → toast + refresh da aba.
- **Estados:** por aba — vazio/loading/erro/dados.

### B3 — `/crm` — Dashboard CRM
- **Role:** OWNER, ADMIN.
- **Layout:** grid de 4 **cards de KPI** no topo + 2 listas abaixo.
- **Cards (de `GET /crm/alerts`):** Em risco (`at_risk_count`) · Novos no mês (`new_this_month`) · VIP (`vip_count`) · Recuperados na semana (`recovered_this_week`). Card "Em janela de retorno" pode reusar `at_risk_customers` com `days_since_last_visit`.
- **Listas:** Top 10 em risco (`at_risk_customers` ordenado por `days_since_last_visit` desc, link p/ ficha) · Sugestões de ação (derivadas de insights — remarcar / enviar pacote; rótulo estático no protótipo).
- **Componentes:** `Card`, `Badge`, `Table`/lista, `Button` (link), `Skeleton`.
- **Estados:** vazio (sem alertas → "Tudo em dia"); loading; erro; dados.

### C1 — `/inbox` — Conversas escaladas
- **Role:** OWNER, ADMIN, OPERATOR.
- **Layout:** **master-detail** — lista à esquerda, thread + reply à direita.
- **Lista (`GET /conversations?status=escalated`):** por item — `customer_name`/`phone`, `last_message` truncada, **tempo esperando** (de `escalated_at`, ex.: "há 12 min"), **Badge "Em atendimento"**. Toggle/aba para `status=resolved` (Badge "Resolvida").
- **Detalhe (`GET /{id}/messages`):** bolhas de chat por `direction`/`sender_type` (INBOUND cliente à esquerda; OUTBOUND BOT/AGENT à direita, com rótulo do remetente); campo de **reply** (`Textarea` + enviar).
- **Componentes:** `Card`, `ScrollArea`, `Badge`, `Textarea`, `Button`, `Avatar`, `Skeleton`, `Tabs` (escaladas/resolvidas).
- **Ações:**
  - **Enviar resposta** → `POST /reply` → adiciona bolha OUTBOUND/AGENT → toast em erro (lembrar: **422 se conversa não está em HUMANO** → mensagem "Conversa não está em atendimento humano").
  - **Resolver conversa** → `Dialog` de confirmação → `PATCH /resolve` → move para "Resolvidas" + toast "Bot reassumiu o atendimento".
- **Estados:** lista vazia ("Nenhuma conversa em atendimento"); thread loading; erro; envio em andamento (desabilitar botão).

### C2 — `/fila` — Fila de espera
- **Role:** OWNER, ADMIN, OPERATOR (entradas); config OWNER/ADMIN.
- **Layout:** `Tabs` — **Entradas** | **Configuração**.
- **Entradas (`GET /waitlist/entries`):** `Table` — cliente · escopo (badge SERVICE/PROFESSIONAL/PRODUCT + nome do alvo) · prioridade · **tempo na fila** · status (badge) · ações. Filtros: status, scope_type.
- **Config (`GET/PUT /waitlist/config`):** form — `Switch` `enabled`, `Select` `priority_mode` (FIFO/prioridade), `Input` numérico `notification_window_hours`. Botão Salvar → `PUT` → toast.
- **Componentes:** `Tabs`, `Table`, `Badge`, `Switch`, `Select`, `Input`, `Button`, `Dialog`, `Skeleton`.
- **Ações:**
  - **Remover da fila** → `Dialog` de confirmação → `DELETE /entries/{id}` → toast + remove linha.
  - **Notificar manualmente** → botão **`disabled`** + `Tooltip` "Em breve" (sem endpoint).
- **Estados:** entradas vazias ("Fila vazia"); loading; erro; salvando config.

### D1 — `/financeiro/pagamentos` — Lista consolidada
- **Role:** OWNER, ADMIN, OPERATOR.
- **Layout:** título + filtros + `Table`. (Esta rota **consolida** `/payments` e `/financeiro/pagamentos` — só existe `/financeiro/pagamentos`.)
- **Colunas:** Data (`created_at`) · Cliente · Valor (`formatBRL(net_charged_amount)`) · Método (`PAYMENT_METHOD_LABELS[payment_method (+submethod)]`) · Status (Badge Payment FSM) · ações.
- **Filtros (client-side):** status (PENDING/CONFIRMED/REFUNDED), método, período (date range).
- **Componentes:** `Table`, `Badge`, `Select`, `DateRangePicker`/`Input`, `Button`, `Pagination`, `Skeleton`.
- **Ações rápidas:** **Confirmar** (só linhas `PENDING`) → `Dialog` → `POST /confirm-manual` → toast (+ banner `fee_warning` se vier). Clique na linha → detalhe.
- **Estados:** vazio; loading (skeleton rows); erro; dados. Paginação client-side (lista é flat).

### D2 — `/financeiro/pagamentos/[id]` — Detalhe do pagamento
- **Role:** OWNER, ADMIN (ações sensíveis); OPERATOR view.
- **Layout:** detalhe em cards. Card "Valores": bruto (`gross_catalog_amount`), desconto (`discount_amount`), líquido (`net_charged_amount`), taxa (`provider_fee`). Card "Origem": método/submétodo, provider, `appointment_id` vinculado (link p/ A1), cupom. Card "Datas": criado/pago/estornado.
- **Componentes:** `Card`, `Badge`, `Separator`, `Button`, `Dialog`, `Select` (RefundReason), `Input` (desconto), `Textarea` (reason).
- **Ações e feedback:**
  - **Confirmar** (se `PENDING`) → `Dialog` → `POST /confirm-manual` → toast.
  - **Estornar** (se `CONFIRMED`) → `Dialog` com `Select` **RefundReason** (`SERVICE_FAILURE/REGISTRATION_ERROR/DEADLINE_POLICY/OTHER`, **obrigatório**) + checkbox `force_local` **só para OWNER** → `POST /refund` → toast.
  - **Aplicar desconto manual** (OWNER/ADMIN, só `PENDING`) → `Dialog` com `Input` valor (>0) + `Textarea` reason (**obrigatório**) → `POST /manual-discount` → toast.
- **Estados:** loading; erro; dados; ações desabilitadas conforme status e role.

### D3 — `/settings/financial` (aba Deposit Policies)
- **Role:** OWNER, ADMIN.
- **Layout:** aba dentro de Settings Financeiro — `Table`/lista de políticas + botão "Nova política".
- **Colunas/campos:** Serviço (`service_id` → nome, ou **"Global"** se null) · Tipo (`FIXED_AMOUNT`/`PERCENTAGE`) · Valor (`formatBRL` ou `%`) · Janela de cancelamento (`refundable_until_hours_before` h) · Reter em NO_SHOW (`retain_on_no_show` badge sim/não).
- **Form (criar/editar, `Dialog` ou seção):** `Select` serviço (ou Global) · `Select` tipo · `Input` valor · `Input` h janela · `Switch` `refund_on_tenant_fault` · `Switch` `retain_on_no_show` · `Switch` `commission_on_retained_deposit`.
- **Componentes:** `Table`, `Dialog`, `Select`, `Input`, `Switch`, `Badge`, `Button`.
- **Ações:** criar (`POST`), editar (`PATCH`), excluir (`DELETE` + `Dialog` confirmação) → toast.
- **Estados:** vazio ("Nenhuma política — depósito desativado"); loading; erro; dados.

---

## 5. Padrões de UX (consistentes entre todas as telas)

### Badges de status — **dois FSMs distintos**
Há duas máquinas de estado separadas; não confundir.

**Appointment FSM** (`APPOINTMENT_STATUS_LABELS` / `APPOINTMENT_STATUS_VARIANT` em `constants.ts`):

| Estado | Label | Cor semântica |
|---|---|---|
| `SCHEDULED` | Agendado | verde (`default`) |
| `IN_PROGRESS` | Em andamento | âmbar (`secondary`) |
| `COMPLETED` | Concluído | neutro (`outline`) |
| `CANCELLED` | Cancelado | vermelho (`destructive`) |
| `NO_SHOW` | Não compareceu | vermelho (`destructive`) |
| `FAILED` | Falhou | vermelho (`destructive`) |
| `DRAFT` | Rascunho | neutro (`outline`) |

> ⚠️ **Não existe `CONFIRMED` no Appointment FSM** — `CONFIRMED` é do **Payment**. O estado "ativo/válido" do agendamento é `SCHEDULED`.

**Payment FSM:** `PENDING` (âmbar) → `CONFIRMED` (verde) → `REFUNDED` (neutro/cinza). Usar `PAYMENT_METHOD_LABELS` para o método.

**Classificação CRM** (badges): `NOVO` (azul/info), `FREQUENTE` (verde suave), `VIP` (brass/accent), `EM_RISCO` (âmbar/vermelho suave), `RECUPERADO` (verde), `REGULAR` (neutro).

### Regras transversais
- **Ações destrutivas/sensíveis sempre em `Dialog` de confirmação** (cancelar, estornar, remover da fila, revogar cota, excluir política, resolver conversa).
- **Toast de feedback após toda ação** (`success`/`error`); mensagem de erro deriva de `detail` da API (lembrar do formato array do FastAPI 422 já tratado em `lib/api.ts`).
- **Reason obrigatório** onde o backend exige: `manual-discount`, `grant-cota`, `refund` (enum). Validar no form antes de enviar.
- **Tabelas com paginação** (`page`/`page_size` onde o endpoint pagina — só `/appointments`; demais paginam client-side).
- **Campos monetários sempre `formatBRL()`** (converter string→número antes).
- **Datas sempre `formatDateTime()`** com timezone BR.
- **Ação sem endpoint no Estágio 0** (Iniciar, NO_SHOW, Notificar manualmente) → botão `disabled` + `Tooltip` "Em breve". Nunca prometer wiring inexistente.
- **RBAC visível:** ações OWNER-only (ex.: `force_local` no refund) ocultas/desabilitadas para ADMIN/OPERATOR; a verdade é o 403 do backend.
- **Estados obrigatórios por tela:** vazio · loading (`Skeleton`) · erro (com retry) · dados.

---

## 6. O que NÃO entra na Fase 1

- **Catálogo** (serviços, produtos, categorias, variantes, overrides, upload de imagens) — Fase 2.
- **Comercial** (pacotes, assinaturas, promoções, cupons) — Fase 2.
- **Financeiro profundo** (DRE, contas/saldos, transferências, conciliação, cash count, extrato/import CSV, movimentos, despesas) — Fase 3. *Exceção:* a aba Deposit Policies (D3) entra porque ancora o fluxo DEPOSIT da operação.
- **Estoque / Fornecedores / Payables** — Fase 3.
- **NPS, Comunicação (templates/logs), WhatsApp QR, Usuários, Módulos, Branding, Audit** — Fase 4.
- **Telas públicas (`/gestao/[token]`, `/nps/[survey_id]`), Portal do Cliente, Painel Owner** — Fase 5.
- **Nenhuma criação de agendamento** (`/appointments/new` já existe) nem calendário (`/agenda` já existe).
- **Nenhum cálculo financeiro no cliente** — saldo de depósito é exibição simples (`total − sinal`), não regra de negócio.

---

*Fonte de verdade de comportamento: `visao-estagio-0.md` + `openapi.json` (head `e0s25f_product_extras`). O protótipo `barberflow-system` é referência **visual apenas**. Onde divergir, vence este documento. Documento de planejamento — nenhuma regra de negócio vive no frontend.*
