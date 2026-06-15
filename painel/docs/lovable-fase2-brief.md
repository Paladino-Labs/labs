# PALADINO — BRIEF DA FASE 2 (LOVABLE)

**Objetivo:** especificar as telas do **Comercial** do Painel do Tenant — catálogo completo (categorias, variantes de serviço, overrides de preço por profissional, imagens de produto), **Pacotes** (planos + venda + compras/cotas), **Assinaturas** (planos + instâncias) e **Promoções/Cupons** (CRUD + ciclo de vida + geração em lote + preview de desconto). Derivado de `painel/docs/inventario-funcional.md` (§5 tabela mestre — Catálogo/Comercial; §7 fluxos 3 e 6; §9 Fase 2) e de `agendamento_engine/openapi.json` (head `e0s25f_product_extras`, 951 testes verdes).

> **Continuação das Fases 0 e 1.** O *shell* (sidebar role-aware, header, branding, guards, tokens) e os componentes/utilitários da Fase 1 (FsmBadge, formatBRLFromDecimal, sonner/toast) **já existem** — ver §2. Esta fase preenche o shell com as 10 telas abaixo. **Dados mockados** no protótipo Lovable; integração real é feita depois pelo Claude Code.

> **Escopo rígido:** apenas o Comercial (Blocos E–H). Nada de financeiro profundo, estoque, despesas, NPS, inbox, owner ou portal (ver §6).

---

## 1. Contexto do produto (herdado da Fase 0/1)

Paladino é uma plataforma **SaaS multi-tenant** para gestão de negócios de serviço pessoal (barbearias no piloto — vertical-âncora do Estágio 0). Stack: **Next.js 15 (App Router) · TypeScript · shadcn/ui · TailwindCSS · Lucide icons**, **Cormorant Garamond** (display) e **Inter** (corpo). RBAC do frontend **espelha** as regras de negócio mas não é a verdade — a verdade é o backend (403 → ocultar/desabilitar). Zero lógica de negócio no frontend: nenhum cálculo de desconto, nenhuma validação de FSM no cliente — o preview de desconto vem **sempre** da API.

---

## 2. Shell e componentes existentes — **NÃO reimplementar**

Entregues nas Fases 0 e 1 e reaproveitados aqui:

- **Sidebar role-aware** (`components/Sidebar.tsx`) — grupo **Comercial** já existe com itens **Catálogo (Serviços · Produtos · Categorias)**, **Pacotes/Assinaturas** e **Promoções/Cupons** apontando para as rotas desta fase.
- **Header**, **`(dashboard)/layout.tsx`** (guard de auth + branding via CSS vars + breadcrumbs), **`useAuth()`** (`role`, `companyId`, `name`, `userId`), **Design tokens** em `globals.css`.
- **`components/FsmBadge.tsx`** — já exporta `AppointmentBadge`, `PaymentBadge`, `CrmBadge`. **Esta fase adiciona** `PackagePurchaseBadge`, `SubscriptionBadge`, `PromotionBadge`, `CouponBadge` no mesmo arquivo, mesmo padrão (`<Badge variant="outline" className={cn("font-normal", CLASS[status])}>`).
- **Glossários** (`lib/constants.ts`) — `ROLE_LABELS`, `PAYMENT_METHOD_LABELS`, **`PAYMENT_METHOD_OPTIONS`** (usar no seletor de método de pagamento da venda de pacote), `FEE_SOURCE_LABELS`. **Esta fase adiciona** os glossários de enum desta fase (discount_type, application_mode, generation_type, FSMs) — `constants.ts` é a fonte única.
- **Utils** — **`formatBRLFromDecimal()`** (string decimal → BRL, trata null/undefined) e `formatDateTime()` (timezone explícito) em `lib/utils.ts`.
- **Upload existente** — `services/page.tsx` e `products/page.tsx` já têm o padrão `api.postForm<{ url: string }>("/uploads/", fd)` com preview e `<input type="file" hidden>`. Reaproveitar/estender.

**O protótipo Lovable produz apenas o conteúdo das páginas** (dentro de `<main>`). Não recriar sidebar, header, layout, providers ou tokens.

### Tokens e convenções (relembrete)

- Tokens semânticos sempre (`bg-card`, `border-border`, `text-muted-foreground`, `bg-primary`, `bg-sidebar`, `text-sidebar-primary`) — **nunca** `bg-white`/`text-gray-*` nem cores hardcoded.
- Ícones **Lucide** `size={16}` `strokeWidth={1.5}` — nunca emojis.
- `h1/h2/h3` herdam Cormorant Garamond; título de página: `font-display text-3xl tracking-wide`. Em `span/div`: `[font-family:var(--font-display)]`.
- **Moeda:** `formatBRLFromDecimal()`. ⚠️ A API devolve **todo** valor monetário como **string decimal** (`"38.50"`, `"120.00"`). Nunca fazer `Number(x).toFixed` à mão; usar o helper.
- **Datas:** `formatDateTime()` com timezone do tenant (fallback `America/Sao_Paulo`).
- Nomenclatura Estágio 0: `professionals` → **"Barbeiros/Profissional"**; campos ausentes na resposta → fallback `"Em breve"` (`text-xs text-muted-foreground opacity-50`), **não** mockar no código real.

---

## 3. Endpoints por tela

Todos exigem JWT (`HTTPBearer`). **Valores monetários = string decimal.** Métodos, campos e roles confirmados contra `openapi.json` e os routers do backend.

### Bloco E — Catálogo

**E1 — Categorias** (`/categories`) · **role:** GET qualquer autenticado (escopo do tenant); POST/PATCH/DELETE **OWNER/ADMIN**.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /categories/?entity_type=` (filtro opcional) | `CategoryResponse[]` |
| Criar | `POST /categories/` | `CategoryCreate{name(1–255)*, entity_type*, is_active=true, sort_order=0}` |
| Editar | `PATCH /categories/{category_id}` | `CategoryPatch{name?, entity_type?, is_active?, sort_order?}` |
| Excluir | `DELETE /categories/{category_id}` | → `204` |

`CategoryResponse`: `category_id, company_id, name, entity_type, is_default, is_active, sort_order`.
> ⚠️ `is_default=true` (categorias semente do onboarding): **não deletável** (DELETE → erro) e `name`/`entity_type`/`sort_order` **imutáveis** (só `is_active` muda). Renderizar essas linhas com ações de exclusão/edição de nome **desabilitadas** + `Tooltip` "Categoria padrão". `entity_type` é o discriminador do catálogo (ex.: categorias de serviço, produto, despesa) — **agrupar a lista por `entity_type`**; o conjunto de valores vem da API, não inventar.

**E2 — Variantes de serviço** (`/services/{service_id}/variants`) · **role:** OWNER/ADMIN.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /services/{service_id}/variants` | `ServiceVariantResponse[]` |
| Criar | `POST /services/{service_id}/variants` | `ServiceVariantCreate{name*, price*, duration_min*, sort_order=0}` |
| Editar | `PATCH /services/{service_id}/variants/{variant_id}` | `ServiceVariantUpdate{name?, price?, duration_min?, is_active?}` |
| Excluir | `DELETE /services/{service_id}/variants/{variant_id}` | → `204` |

`ServiceVariantResponse`: `variant_id, service_id, company_id, name, price(str), duration_min, is_active, sort_order`.

**E3 — Overrides de preço/duração por profissional** (`/professionals/{professional_id}/pricing-overrides`) · **role:** OWNER/ADMIN.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /professionals/{professional_id}/pricing-overrides` | `PricingOverrideResponse[]` |
| Criar | `POST /professionals/{professional_id}/pricing-overrides` | `PricingOverrideCreate{service_id*, price*, duration_min?}` |
| Editar | `PATCH .../pricing-overrides/{override_id}` | `PricingOverrideUpdate{price?, duration_min?, is_active?}` |
| Excluir | `DELETE .../pricing-overrides/{override_id}` | → `204` |

`PricingOverrideResponse`: `override_id, professional_id, service_id, company_id, price(str), duration_min?, is_active`.
> Apoio: `GET /services/` (catálogo base) para o `Select` de serviço e para mostrar o preço-base ao lado do override.

**E4 — Imagens de produto** (extensão de `/products`) · **role:** OWNER/ADMIN.
| Ação | Método + Path | Campos |
|---|---|---|
| Upload | `POST /uploads/` (**multipart/form-data**, campo `file`) | resposta `{ url }` |
| Salvar no produto | `POST /products/` · `PATCH /products/{id}` | `image_url?` (1 string) |

`ProductResponse`: `id, company_id, name, price(str), description?, image_url?, active, stock?`.
> ⚠️ **O backend persiste apenas UMA imagem** (`image_url`) — **não existe `images[]`**. A UI pode apresentar uma galeria de até 5 *slots* com drag-and-drop, mas **só o slot primário persiste** em `image_url`; os demais ficam **"Em breve"** (desabilitados) até o backend expor `product_images[]`. Não simular persistência de múltiplas imagens.

### Bloco F — Pacotes

**F1 — Planos de pacote** (`/packages`) · **role:** OWNER/ADMIN.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /packages` | `PackageResponse[]` |
| Criar | `POST /packages` | `PackageCreate{name*, total_cotas*(int>0), price*, service_id?, validity_days?}` |
| Editar | `PATCH /packages/{package_id}` | `PackageUpdate{name?, total_cotas?, price?, service_id?, validity_days?, is_active?}` |
| Excluir | `DELETE /packages/{package_id}` | → `PackageResponse` |

`PackageResponse`: `package_id, company_id, name, service_id?, total_cotas, price(str), validity_days?, is_active, created_at, updated_at?`.
> ⚠️ Modelo real: **um `service_id` único (nullable)** — `null` = **pacote genérico** (cobre qualquer serviço). **Não há `services[]` nem `commission_on_sale_enabled`.** `validity_days` null = sem validade. Apoio: `GET /services/` para o `Select` de serviço.

**F2 — Venda de pacote** (modal lançado de F1) (`POST /packages/{package_id}/sell`) · **role:** OWNER/ADMIN/**OPERATOR**.
| Ação | Método + Path | Campos |
|---|---|---|
| Vender | `POST /packages/{package_id}/sell` | `SellPackageRequest{customer_id*, payment_method*, seller_user_id?, target_account_id?}` → `SellPackageResponse{purchase_id, payment_id?}` |

> ⚠️ A venda cria **PackagePurchase `PENDING_PAYMENT` + Payment `PENDING`** — **não confirma o pagamento automaticamente** (nem para CASH). Após vender, exibir toast "Pacote vendido — pagamento pendente de confirmação em Pagamentos" e (opcional) link para `/financeiro/pagamentos/{payment_id}` (tela D2 da Fase 1). `payment_method` é string canônica → usar as **chaves de `PAYMENT_METHOD_OPTIONS`** (`CASH`, `CHAVE_PIX`, `MAQUININHA_*`).

**F3 — Compras / cotas por cliente** (`/package-purchases`) · **role:** OWNER/ADMIN.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /package-purchases?customer_id=&status=` | `PackagePurchaseResponse[]` |
| Detalhe | `GET /package-purchases/{purchase_id}` | `PackagePurchaseResponse` |

`PackagePurchaseResponse`: `purchase_id, company_id, customer_id, package_id, seller_user_id?, payment_id?, total_price(str), status, activated_at?, created_at`.
> ⚠️ **Tela read-only** — não há endpoint de cancelar/estornar compra. As **cotas** (saldo `remaining/total`, validade, status `ACTIVE/EXHAUSTED/EXPIRED/REVOKED`) vivem em `/customer-credits` (já consumido na ficha do cliente, Fase 1) — **não** em `PackagePurchaseResponse`. Para ver cotas, link à ficha do cliente. `status` da compra: ver §5.

### Bloco G — Assinaturas

**G1 — Planos de assinatura** (`/subscription-plans`) · **role:** OWNER/ADMIN.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /subscription-plans` | `SubscriptionPlanResponse[]` |
| Criar | `POST /subscription-plans` | `SubscriptionPlanCreate{name*, cotas_per_cycle*, price*, cycle_days=30, rollover_enabled=false, service_id?}` |
| Editar | `PATCH /subscription-plans/{plan_id}` | `SubscriptionPlanUpdate{name?, cotas_per_cycle?, price?, cycle_days?, rollover_enabled?, service_id?, is_active?}` |

`SubscriptionPlanResponse`: `plan_id, company_id, name, service_id?, cotas_per_cycle, price(str), cycle_days, rollover_enabled, is_active, created_at, updated_at?`.
> ⚠️ **Não há DELETE de plano** — "excluir" = `PATCH is_active=false`. `service_id` null = plano genérico. `rollover_enabled` = cotas não usadas passam para o próximo ciclo.

**G2 — Instâncias (assinaturas ativas)** (`/subscriptions`) · **role:** OWNER/ADMIN.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /subscriptions?customer_id=&status=` | `SubscriptionResponse[]` |
| Detalhe | `GET /subscriptions/{subscription_id}` | `SubscriptionResponse` |
| Criar (assinar) | `POST /subscriptions` | `SubscribeRequest{customer_id*, plan_id*, first_billing_at?}` → `SubscriptionResponse` |
| Pausar | `PATCH /subscriptions/{id}/pause` | **sem body** → `SubscriptionResponse` |
| Retomar | `PATCH /subscriptions/{id}/resume` | **sem body** → `SubscriptionResponse` |
| Cancelar | `PATCH /subscriptions/{id}/cancel` | **sem body** → `SubscriptionResponse` |

`SubscriptionResponse`: `subscription_id, company_id, customer_id, plan_id, status, next_billing_at, overdue_since?, paused_at?, cancelled_at?, created_at`.
> ⚠️ pause/resume/cancel **não recebem `reason`** (sem body). Pré-pago. FSM em §5.

### Bloco H — Promoções e Cupons

**H1 — Promoções** (`/promotions`) · **role:** OWNER/ADMIN (preview qualquer autenticado).
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /promotions` | `PromotionResponse[]` |
| Criar | `POST /promotions` | `PromotionCreate` (ver abaixo) |
| Detalhe | `GET /promotions/{promotion_id}` | `PromotionResponse` |
| Ativar | `PATCH /promotions/{id}/activate` | **sem body** → `PromotionResponse` |
| Pausar | `PATCH /promotions/{id}/pause` | **sem body** |
| Cancelar | `PATCH /promotions/{id}/cancel` | **sem body** |
| Preview | `POST /promotions/preview` | `PreviewRequest` → `PreviewResponse` |

`PromotionCreate`: `name*(1–255), description?, discount_type*(PERCENTAGE|FIXED_AMOUNT|OVERRIDE_PRICE|FREE_ITEM), discount_value?(decimal; PERCENTAGE ≤100), application_mode(AUTOMATIC|COUPON_REQUIRED)=AUTOMATIC, cumulative=false, priority=0, valid_from?, valid_until?, max_uses?, max_uses_per_customer?, conditions?(object)`.
`PromotionResponse`: acima + `id, company_id, status, uses_count, created_by, created_at, updated_at?` (`discount_value` vem como string).
> ⚠️ **Não há PATCH de edição nem DELETE de promoção** — só criar + transições (activate/pause/cancel). Promoção é **imutável após criada**; para "mudar", cancelar e recriar. `conditions` é JSON livre — no protótipo, **somente leitura** (não construir editor de regras).

**H2 — Cupons** (`/promotions/{promotion_id}/coupons`) · **role:** OWNER/ADMIN.
| Ação | Método + Path | Campos |
|---|---|---|
| Gerar em lote | `POST /promotions/{promotion_id}/coupons` | `CouponGenerateRequest` → `CouponResponse[]` |
| Lista | `GET /promotions/{promotion_id}/coupons` | `CouponResponse[]` |

`CouponGenerateRequest`: `generation_type*(BULK|SINGLE_USE|PER_CUSTOMER), quantity=1, code?, prefix?, max_uses?, customer_id?, expires_at?, coupon_reopen_policy(NEVER_REOPEN|REOPEN_ON_REFUND)=NEVER_REOPEN`.
`CouponResponse`: `id, company_id, promotion_id, code, generation_type, max_uses?, uses_count, coupon_reopen_policy, status, customer_id?, expires_at?`.
> ⚠️ Regras do backend a refletir no form: **SINGLE_USE** força `max_uses=1` (desabilitar o campo); **PER_CUSTOMER** exige `customer_id` (obrigatório, com `CustomerAutocomplete`); **BULK** usa `quantity` + `prefix` opcional. `coupon_reopen_policy` controla reabertura no estorno.

`PreviewRequest`: `gross_amount*(decimal>0), service_ids?, product_ids?, customer_id?, coupon_code?, subscription_cycle?`.
`PreviewResponse`: `final_amount(str), discount_total(str), applications[](PreviewApplication), coupon_valid(bool)`.

---

## 4. Especificação das telas

Para cada tela: **rota · role · layout · componentes shadcn · estados · ações**. Estados obrigatórios em todas: **vazio · loading (`Skeleton`) · erro (com retry) · dados**.

### E1 — `/catalogo/categorias` — CRUD de categorias
- **Role:** OWNER/ADMIN (OPERATOR pode ver, edição oculta/desabilitada).
- **Layout:** título + botão "Nova categoria"; lista **agrupada por `entity_type`** (ex.: cabeçalhos de seção), cada grupo uma `Table` ou cards ordenados por `sort_order`.
- **Colunas/campos:** Nome · Tipo (`entity_type`) · Ordem (`sort_order`) · Status (`ActiveBadge`/Switch) · Padrão (badge "Padrão" se `is_default`) · ações.
- **Componentes:** `Table`, `Badge`, `Switch`, `Dialog` (form), `Input`, `Select` (entity_type), `Button`, `Tooltip`, `Skeleton`.
- **Form (criar/editar `Dialog`):** `Input` nome (1–255), `Select`/`Input` entity_type, `Input` numérico sort_order, `Switch` is_active.
- **Ações:** criar (`POST`), editar (`PATCH`), excluir (`DELETE` + `Dialog` de confirmação). **`is_default`:** excluir e editar nome/tipo/ordem **desabilitados** com `Tooltip` "Categoria padrão" (só `is_active` alterável).

### E2 — Variantes de serviço (`Sheet`/`Dialog` "Gerenciar variantes" em `/services`)
- **Role:** OWNER/ADMIN.
- **Layout:** na tela de Serviços, cada linha ganha ação **"Variantes"** que abre um `Sheet` lateral (ou `Dialog`) com o nome do serviço no topo + lista de variantes + form inline "Nova variante". (Alternativa equivalente: rota `/catalogo/servicos/[id]`; preferir o `Sheet` para não criar rota nova.)
- **Itens:** por variante — Nome · Preço (`formatBRLFromDecimal`) · Duração (`duration_min` min) · Ordem · Status · ações editar/excluir.
- **Componentes:** `Sheet`/`Dialog`, `Table`/lista, `Input`, `Button`, `Switch`, `Skeleton`, `Tooltip`.
- **Form:** `Input` nome, `Input` numérico preço (step 0.01), `Input` numérico duração (min), `Input` ordem.
- **Ações:** criar (`POST .../variants`), editar (`PATCH .../variants/{id}`), excluir (`DELETE` + confirmação).

### E3 — `/professionals/[id]` (nova aba **"Preços por serviço"**)
- **Role:** OWNER/ADMIN.
- **Layout:** **estender a ficha existente** (`app/(dashboard)/professionals/[id]/page.tsx` já tem horários, serviços e bloqueios) com uma seção/aba de overrides — `Table` de serviços com override + botão "Novo override".
- **Colunas:** Serviço (nome via `GET /services/`) · Preço base (do serviço) · Preço override (`price`) · Duração override (`duration_min` ou "—") · Status · ações.
- **Componentes:** `Table`, `Dialog` (form), `Select` (serviço — excluir serviços já com override), `Input`, `Switch`, `Button`, `Skeleton`.
- **Form (criar):** `Select` service_id, `Input` preço, `Input` duração (opcional). **Editar** só altera price/duration/is_active.
- **Ações:** criar (`POST`), editar (`PATCH`), excluir (`DELETE` + confirmação).

### E4 — `/products` (galeria de imagens no form)
- **Role:** OWNER/ADMIN.
- **Layout:** estender os diálogos criar/editar de produto com um **uploader de galeria**: até 5 *slots* em grid, drag-and-drop opcional, preview por slot, botão remover. **Slot 1 = primária** (persiste em `image_url`).
- **Upload:** `POST /uploads/` multipart (campo `file`), `accept="image/*"`; durante upload, spinner no slot; em erro, toast. Validar tamanho/tipo no cliente (feedback amigável) — o limite real é do backend.
- **Componentes:** grid de upload, `Button`, spinner/`Skeleton`, `Tooltip`, `Dialog`.
- **Persistência:** salvar `image_url` (slot primário) no `POST/PATCH /products`. **Slots 2–5: visuais e desabilitados com badge "Em breve"** — não enviar; documentar que dependem de `product_images[]` no backend.
- **Ações:** trocar/remover primária; reordenar é "Em breve".

### F1 — `/pacotes` — Planos de pacote (CRUD)
- **Role:** OWNER/ADMIN.
- **Layout:** título + "Novo pacote"; `Table` ou grid de cards.
- **Colunas:** Nome · Serviço (nome ou **"Genérico"** se `service_id` null) · Cotas (`total_cotas`) · Preço (`formatBRLFromDecimal`) · Validade (`validity_days` dias ou "Sem validade") · Status (`is_active`) · ações **Editar · Excluir · Vender**.
- **Componentes:** `Table`/`Card`, `Badge`, `Dialog`, `Select` (serviço opcional), `Input`, `Switch`, `Button`, `Skeleton`.
- **Form:** `Input` nome, `Input` numérico cotas (>0), `Input` preço, `Select` serviço (com opção "Genérico"), `Input` validade (dias, opcional), `Switch` is_active (editar).
- **Ações:** criar (`POST`), editar (`PATCH`), excluir (`DELETE` + confirmação), **Vender** → abre F2.

### F2 — Venda de pacote (modal guiado, lançado de F1)
- **Role:** OWNER/ADMIN/OPERATOR.
- **Layout:** **fluxo guiado em passos** (`Dialog` com stepper): **1) Selecionar cliente** (`CustomerAutocomplete`) → **2) Confirmar plano** (resumo: nome, cotas, preço, validade) → **3) Método de pagamento** (`Select`/grid usando `PAYMENT_METHOD_OPTIONS`, agrupado Dinheiro/Pix · Crédito · Débito) → **4) Confirmar**.
- **Componentes:** `Dialog`, stepper (passos), `CustomerAutocomplete` (já existe), `RadioGroup`/`Select`, `Card` (resumo), `Button`.
- **Ação:** `POST /packages/{id}/sell` com `{customer_id, payment_method}` (+ `seller_user_id` = usuário atual opcional). **Sucesso:** toast "Pacote vendido — pagamento pendente de confirmação" + link opcional ao pagamento (`payment_id`). **Não** marcar como pago aqui.
- **Estados:** validação por passo; enviar desabilita o botão; erro → toast com `detail` da API.

### F3 — `/pacotes/compras` — Histórico de compras
- **Role:** OWNER/ADMIN.
- **Layout:** título + filtros + `Table` (read-only).
- **Colunas:** Data (`created_at`) · Cliente (id → nome; compor via `/customers` ou "Em breve") · Pacote (nome via `/packages`) · Valor (`total_price`) · **Status** (`PackagePurchaseBadge`) · Pagamento (link a `payment_id` se houver) · ações (ver cotas → ficha do cliente).
- **Filtros (client-side):** status (`PENDING_PAYMENT`/`ACTIVE`/`REVOKED`), cliente (autocomplete → passa `customer_id` ao GET).
- **Componentes:** `Table`, `Badge`, `Select`, `CustomerAutocomplete`, `Button` (link), `Skeleton`, `Pagination` (client-side).
- **Ações:** linha → detalhe (`GET /{id}`) em `Dialog`; "Ver cotas" → `/customers/[customer_id]` (aba Cotas da Fase 1). Sem cancelar/estornar (não há endpoint).

### G1 — `/assinaturas/planos` — Planos de assinatura (CRUD)
- **Role:** OWNER/ADMIN.
- **Layout:** título + "Novo plano"; `Table`/cards.
- **Colunas:** Nome · Serviço (nome ou "Genérico") · Cotas/ciclo (`cotas_per_cycle`) · Preço (`formatBRLFromDecimal`) · Ciclo (`cycle_days` dias) · Rollover (badge sim/não) · Status (`is_active`) · ações.
- **Componentes:** `Table`/`Card`, `Badge`, `Dialog`, `Select`, `Input`, `Switch`, `Button`, `Skeleton`.
- **Form:** `Input` nome, `Input` numérico cotas/ciclo, `Input` preço, `Input` numérico ciclo (dias, default 30), `Switch` rollover_enabled, `Select` serviço (opcional), `Switch` is_active (editar).
- **Ações:** criar (`POST`), editar (`PATCH`); **"Excluir" = `PATCH is_active=false`** (sem DELETE) → rotular ação como "Desativar".

### G2 — `/assinaturas` — Instâncias (pause/resume/cancel)
- **Role:** OWNER/ADMIN.
- **Layout:** título + "Nova assinatura" + filtros + `Table`.
- **Colunas:** Cliente · Plano (nome via `/subscription-plans`) · **Status** (`SubscriptionBadge`) · Próx. cobrança (`next_billing_at`) · Em atraso desde (`overdue_since` se houver) · ações.
- **Filtros (client-side):** status, cliente.
- **Componentes:** `Table`, `Badge`, `Dialog`, `Select`, `CustomerAutocomplete`, `Button`, `Skeleton`.
- **Nova assinatura (`Dialog`):** `CustomerAutocomplete` + `Select` plano + `DateTimePicker` first_billing_at (opcional) → `POST /subscriptions`.
- **Ações (por status, ver §5):** **Pausar** (se `ACTIVE`) → `Dialog` confirmação → `PATCH /pause`; **Retomar** (se `PAUSED`) → `PATCH /resume`; **Cancelar** (se `ACTIVE`/`PAUSED`/`OVERDUE`) → `Dialog` confirmação → `PATCH /cancel`. **Sem `reason`** (sem body). Toast após cada ação; botão desabilitado durante envio.

### H1 — `/promocoes` — Lista + criar + ativar/pausar/cancelar
- **Role:** OWNER/ADMIN.
- **Layout:** título + "Nova promoção" + `Table`.
- **Colunas:** Nome · Tipo (`discount_type` glossário) · Valor (`%` se PERCENTAGE; `formatBRLFromDecimal` se FIXED_AMOUNT; "—" para OVERRIDE_PRICE/FREE_ITEM) · Modo (`application_mode`: Automática / Requer cupom) · **Status** (`PromotionBadge`) · Vigência (`valid_from`–`valid_until`) · Usos (`uses_count`/`max_uses`) · ações.
- **Componentes:** `Table`, `Badge`, `Dialog`, `Select`, `Input`, `Switch`, `DateTimePicker`, `Button`, `Skeleton`, `Tooltip`.
- **Form criar (`Dialog`):** nome, `Textarea` descrição, `Select` discount_type, `Input` discount_value (condicional ao tipo; validar ≤100 em PERCENTAGE — mas a validação dura é do backend), `Select` application_mode, `Switch` cumulative, `Input` priority, `DateTimePicker` valid_from/until, `Input` max_uses, `Input` max_uses_per_customer. **Sem editor de `conditions`** (read-only).
- **Ações (por status, §5):** **Ativar** (`DRAFT`/`PAUSED`) → `PATCH /activate`; **Pausar** (`ACTIVE`) → `PATCH /pause`; **Cancelar** (`DRAFT`/`ACTIVE`/`PAUSED`) → `Dialog` confirmação → `PATCH /cancel`. **Gerar/ver cupons** → H2 (habilitar quando `application_mode=COUPON_REQUIRED`, mas a API permite cupom em qualquer modo — não bloquear). **Sem editar/excluir** (não há endpoint) → não renderizar essas ações.

### H2 — `/promocoes/[id]/cupons` — Geração em lote + lista
- **Role:** OWNER/ADMIN.
- **Layout:** header com nome/status da promoção (`GET /promotions/{id}`) + botão "Gerar cupons" + `Table` de cupons.
- **Colunas:** Código (`code`, com botão copiar) · Tipo (`generation_type`) · Usos (`uses_count`/`max_uses`) · Cliente (`customer_id` se PER_CUSTOMER) · Validade (`expires_at`) · Reabertura (`coupon_reopen_policy`) · **Status** (`CouponBadge`).
- **Componentes:** `Table`, `Badge`, `Dialog` (gerar), `Select`, `Input`, `DateTimePicker`, `CustomerAutocomplete`, `Button`, `Skeleton`.
- **Form gerar (`Dialog`):** `Select` generation_type → campos condicionais:
  - **BULK:** `Input` quantity, `Input` prefix (opcional), `Input` max_uses.
  - **SINGLE_USE:** `Input` code (opcional) ou prefix; **max_uses fixo em 1 (desabilitado)**.
  - **PER_CUSTOMER:** `CustomerAutocomplete` **obrigatório**, `Input` max_uses.
  - comuns: `DateTimePicker` expires_at, `Select` coupon_reopen_policy.
- **Ações:** gerar (`POST .../coupons` → adiciona N linhas + toast "N cupons gerados"); copiar código (clipboard + toast).

### Preview de desconto (transversal — apoio ao checkout)
> O `POST /promotions/preview` **não é uma tela própria** desta fase; ele alimenta o **checkout de pagamento** (Fase 1, `/financeiro/pagamentos/novo`). Documentado aqui para consistência: ao informar valor bruto + (opcional) cupom/serviços/cliente, chamar `preview` e exibir `discount_total` e `final_amount` (ambos string decimal) + `coupon_valid`. No protótipo da Fase 2, expor um **mini-card de preview** opcional na venda de pacote/assinatura caso haja cupom — caso contrário, deixar para a Fase 1.

---

## 5. Padrões de UX específicos da Fase 2

### Badges de FSM novos — adicionar a `components/FsmBadge.tsx`
Cores semânticas **distintas** das FSMs da Fase 1 (Appointment/Payment), mas reusando a paleta de tokens (emerald/amber/sky/destructive/muted/sidebar-primary). Sugestão:

**PackagePurchase** (`PackagePurchaseBadge`):
| Estado | Label | Cor |
|---|---|---|
| `PENDING_PAYMENT` | Aguardando pagamento | âmbar |
| `ACTIVE` | Ativo | emerald |
| `REVOKED` | Estornado/Revogado | destructive |

**Subscription** (`SubscriptionBadge`):
| Estado | Label | Cor |
|---|---|---|
| `ACTIVE` | Ativa | emerald |
| `PAUSED` | Pausada | âmbar |
| `OVERDUE` | Em atraso | âmbar/destructive |
| `SUSPENDED` | Suspensa | destructive |
| `CANCELLED` | Cancelada | muted |

**Promotion** (`PromotionBadge`):
| Estado | Label | Cor |
|---|---|---|
| `DRAFT` | Rascunho | muted |
| `ACTIVE` | Ativa | emerald |
| `PAUSED` | Pausada | âmbar |
| `EXPIRED` | Expirada | muted |
| `CANCELLED` | Cancelada | destructive |

**Coupon** (`CouponBadge`):
| Estado | Label | Cor |
|---|---|---|
| `ACTIVE` | Ativo | emerald |
| `EXHAUSTED` | Esgotado | muted |
| `CANCELLED` | Cancelado | destructive |

> Cota (CustomerCredit, já da Fase 1, referenciada em F3): `ACTIVE`/`EXHAUSTED`/`EXPIRED`/`REVOKED`.

### Glossários de enum — adicionar a `lib/constants.ts`
- `DISCOUNT_TYPE_LABELS`: `PERCENTAGE`→"Percentual", `FIXED_AMOUNT`→"Valor fixo", `OVERRIDE_PRICE`→"Preço fixo", `FREE_ITEM`→"Item grátis".
- `APPLICATION_MODE_LABELS`: `AUTOMATIC`→"Automática", `COUPON_REQUIRED`→"Requer cupom".
- `GENERATION_TYPE_LABELS`: `BULK`→"Em lote", `SINGLE_USE`→"Uso único", `PER_CUSTOMER`→"Por cliente".
- `COUPON_REOPEN_LABELS`: `NEVER_REOPEN`→"Não reabrir", `REOPEN_ON_REFUND`→"Reabrir no estorno".

### Fluxos guiados e transições
- **Venda de pacote (F2):** fluxo em 4 passos (cliente → plano → método → confirmar); cada passo valida antes de avançar; o último faz `POST /sell` e informa pagamento pendente.
- **Transições de ciclo de vida** (assinatura, promoção): ações renderizadas **conforme o status atual** (mapa em §5/§3) — esconder ações inválidas, não só desabilitar.
- **Confirmação obrigatória (`Dialog`)** em ações destrutivas/de estado: cancelar assinatura, cancelar promoção, excluir (categoria/variante/override/pacote). **Sem campo `reason`** em assinatura/promoção (a API não recebe). Onde a API não pede reason, não inventar campo.
- **Preview de desconto** sempre vindo de `POST /promotions/preview` — nunca calcular no cliente.

### Regras transversais (idênticas à Fase 1)
- **Toast** (`sonner`) após toda ação (success/error); erro deriva do `detail` da API (array do FastAPI 422 já tratado em `lib/api.ts`).
- **Monetário** sempre `formatBRLFromDecimal()`; **datas** sempre `formatDateTime()` (timezone BR).
- **Sem paginação no servidor** nestes endpoints → filtrar/paginar **client-side**.
- **Ação sem endpoint** (editar/excluir promoção, cancelar compra de pacote, slots 2–5 de imagem, reordenar imagem) → **não renderizar** ou `disabled` + `Tooltip` "Em breve". Nunca prometer wiring inexistente.
- **RBAC visível:** OPERATOR só vende pacote (F2) e vê catálogo; escrita de catálogo/planos/promoções é OWNER/ADMIN; a verdade é o 403 do backend.
- **Campos ausentes** (nome do cliente/serviço/pacote quando o endpoint só traz o id) → compor via lista correspondente ou `"Em breve"`.

---

## 6. O que NÃO entra na Fase 2

- **Financeiro profundo** (DRE, contas/saldos, transferências, conciliação, cash count, extrato/import CSV, movimentos, ajuste manual) — Fase 3. *Exceção:* confirmar pagamento de pacote reaproveita a tela D2 da Fase 1 (não reconstruir).
- **Estoque / Fornecedores / Payables / Despesas** — Fase 3 (inclui receber pedido, custo médio, recorrência).
- **NPS, Comunicação (templates/logs), WhatsApp QR, Usuários, Módulos, Branding, Audit** — Fase 4.
- **Telas públicas (`/gestao/[token]`, `/nps/[survey_id]`), Portal do Cliente, Painel Owner** — Fase 5.
- **Editor de `conditions` de promoção** (regras complexas) — fora do Estágio 0; `conditions` é read-only no protótipo.
- **Galeria multi-imagem persistida** (`product_images[]`) — não há backend; só `image_url` (1).
- **Cancelar/estornar compra de pacote** e **DELETE de plano/promoção** — não há endpoint.
- **Tela dedicada de preview de desconto** — o preview alimenta o checkout da Fase 1.
- **Nenhum cálculo de desconto/comissão no cliente** — tudo vem da API.

---

*Fonte de verdade de comportamento: `visao-estagio-0.md` + `openapi.json` (head `e0s25f_product_extras`). O protótipo `barberflow-system` é referência **visual apenas**. Onde divergir, vence este documento. Documento de planejamento — nenhuma regra de negócio vive no frontend.*
