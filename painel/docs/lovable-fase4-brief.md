# PALADINO — BRIEF DA FASE 4 (LOVABLE)

**Objetivo:** especificar as telas de **Relacionamento** (NPS — config, surveys e a tela **pública** de resposta do cliente; Comunicação — templates e logs de envio; WhatsApp — conexão/QR) e de **Administração** (Usuários/Acessos com anti-escalonamento, Módulos do tenant, Branding com preview ao vivo, Trilha de Auditoria append-only). Derivado de `painel/docs/inventario-funcional.md` (§5 tabela mestre — Relacionamento/Administração; §9 Fase 4) e de `agendamento_engine/openapi.json` (head `e0s25f_product_extras`, 951 testes verdes). FSMs, enums e shapes **conferidos diretamente no backend** (models, services, routers) — não inferidos.

> **Continuação das Fases 0, 1, 2 e 3.** O *shell* (sidebar role-aware, header, branding, guards, tokens) e os componentes/utilitários já existem — ver §2. Esta fase preenche os grupos **Relacionamento** e **Administração** da sidebar com as 10 telas/superfícies abaixo. **Dados mockados** no protótipo Lovable; a integração real é feita depois pelo Claude Code.

> **Escopo rígido:** apenas Relacionamento + Administração (Blocos L–N). Nada de portal do cliente, painel owner ou as telas públicas `/gestao/[token]` (Fase 5). **A única tela pública desta fase é o NPS de resposta do cliente** (`/nps/respond/[survey_id]`), que roda **fora do shell do painel** (sem sidebar/header).

> **⚠️ Já implementado — NÃO refazer (verificar/alinhar apenas):**
> - **M3 — WhatsApp (conexão/QR)** já existe completo em `app/(dashboard)/settings/integracoes/page.tsx` (`TabWhatsApp`): polling 3s/30s/60s, contagem regressiva do QR, render `data:image/png;base64,${qr_code}`, Conectar/Gerar novo QR/Desconectar, `StatusBadge`. A Fase 4 **não reescreve** essa aba — só documenta o contrato (§3 M3) e, opcionalmente, expõe `whatsapp_api_type` + quiet hours na tela de Comunicação.
> - **N1 — Usuários** existe **parcialmente** em `app/(dashboard)/settings/usuarios/page.tsx` (lista + convidar com `name`). A Fase 4 **acrescenta** atribuição de papel, desativação, transferência de propriedade, lista/cancelamento de convites e o **anti-escalonamento na UI** (§3 N1, §4 N1).
> - **Settings de canais** (`/settings/comunicacao`) existe (toggles WhatsApp/Email via `PUT /communication/settings`) — **não refazer**; os **templates (M1)** e **logs (M2)** são telas novas em `/comunicacao`.

---

## 1. Contexto do produto (herdado das Fases 0/1/2/3)

Paladino é uma plataforma **SaaS multi-tenant** para gestão de negócios de serviço pessoal (barbearias no piloto — vertical-âncora do Estágio 0). Stack: **Next.js 15 (App Router) · TypeScript · shadcn/ui · TailwindCSS · Lucide icons**, **Cormorant Garamond** (display) e **Inter** (corpo). RBAC do frontend **espelha** as regras de negócio mas não é a verdade — a verdade é o backend (403 → ocultar/desabilitar). Nesta fase o RBAC é crítico no módulo de Usuários: a UI deve **enforçar o anti-escalonamento** (não só reagir ao 403) para nunca oferecer um papel que o ator não pode atribuir. Datas com `formatDateTime()`; não há cálculo financeiro nesta fase.

---

## 2. Shell e componentes existentes — **NÃO reimplementar**

Entregues nas Fases 0–3 e reaproveitados aqui:

- **Sidebar role-aware** (`components/Sidebar.tsx`) — os grupos **Relacionamento** e **Administração** já existem na estrutura. Esta fase **adiciona/ativa as rotas** que ainda apontam para "Em breve": `/nps`, `/nps/config`, `/comunicacao`, `/comunicacao/logs`, `/settings/usuarios` (expandir), `/settings/modulos`, `/settings/branding`, `/audit`. WhatsApp continua dentro de `/settings/integracoes`.
- **Header**, **`(dashboard)/layout.tsx`** (guard de auth + branding via CSS vars + breadcrumbs), **`useAuth()`** (`role`, `companyId`, `name`, `userId`), **design tokens** em `globals.css`.
- **`components/FsmBadge.tsx`** — já exporta os badges das Fases 1–3. **Esta fase adiciona** `NpsSurveyBadge` e `CommunicationLogBadge` no mesmo arquivo e mesmo padrão (`<Badge variant="outline" className={cn("font-normal", CLASS[status])}>`, constantes `EMERALD/AMBER/DESTRUCTIVE/NEUTRAL/SKY` já definidas). Ver §5.
- **`components/ActiveBadge.tsx`** (ativo/inativo) — reaproveitar para `User.active`, `ModuleActivation.is_active`, status de convite.
- **`components/PageHeader.tsx`**, **`components/empty-state.tsx`** (`EmptyState`), **`components/ErrorState.tsx`** — estados vazio/erro de toda tela.
- **`components/CustomerAutocomplete.tsx`** e **`components/DateTimePicker.tsx`** — reaproveitar (filtros de data em surveys, logs e audit).
- **Glossários** (`lib/constants.ts`) — `ROLE_LABELS` (já tem OWNER/ADMIN/OPERATOR/PROFESSIONAL/CLIENT). **Esta fase adiciona** os glossários desta fase (ver §5) — `constants.ts` é a fonte única.
- **Utils** — `formatDateTime()` (timezone do tenant, fallback `America/Sao_Paulo`) em `lib/utils.ts`.
- **Upload existente** — `services/page.tsx` / `products/page.tsx` têm o padrão `api.postForm<{ url }>("/uploads/", fd)` com `<input type="file" hidden>`, spinner e toast. O **upload de logo/favicon (N3)** reaproveita esse padrão e grava em `logo_url`/`favicon_url`.
- **WhatsApp tab** — `settings/integracoes/page.tsx::TabWhatsApp` já implementa conexão/QR/polling (ver nota de topo). Reaproveitar como referência canônica de UX de QR.
- **sonner/toast** — após toda ação.

**O protótipo Lovable produz apenas o conteúdo das páginas** (dentro de `<main>`), **exceto** a tela pública de NPS (L3), que é uma página **standalone sem o shell do painel**.

### Tokens e convenções (relembrete)

- Tokens semânticos sempre (`bg-card`, `border-border`, `text-muted-foreground`, `bg-primary`, `bg-sidebar`, `text-success`, `text-destructive`) — **nunca** `bg-white`/`text-gray-*` nem cores hardcoded. (Exceção controlada: o **preview de branding** (N3) usa as cores escolhidas pelo usuário como valor literal — é o objetivo da tela.)
- Ícones **Lucide** `size={16}` `strokeWidth={1.5}` — nunca emojis. Sugestões: `Star`/`Gauge` (NPS), `MessageSquare`/`FileText` (templates), `ScrollText`/`Send` (logs), `Smartphone`/`QrCode` (WhatsApp), `Users`/`UserPlus`/`UserCog` (usuários), `Mail` (convites), `ToggleLeft`/`Blocks` (módulos), `Palette`/`Brush` (branding), `ShieldCheck`/`History`/`Download` (audit).
- `h1/h2/h3` herdam Cormorant Garamond; título de página: `font-display text-3xl tracking-wide`.
- **Datas:** `formatDateTime()`. Campos `*_at` vêm como date-time ISO.

---

## 2b. Referências visuais

Para cada tela desta fase, **consultar a pasta de screenshots compartilhada na sessão**. Se houver screenshot aprovada, ela é o contrato visual; o código em `/tmp/barberflow` é a referência de **estrutura**.

> **⚠️ Status real desta fase (reportar ao Lovable):** **não há screenshots aprovadas** para nenhuma tela da Fase 4. E o protótipo **barberflow-system NÃO possui nenhuma rota desta fase** — verificado em `/tmp/barberflow/src/routes/` (atualizado nesta sessão): **não existe** `nps*`, `comunicacao*`, `usuarios*`, `modulos*`, `branding*`, `audit*` nem `whatsapp*`. O protótipo tem apenas `owner.tsx`/`portal.tsx` (stubs vazios) e as rotas das Fases 0–3.
>
> **Consequência:** estas 10 telas são **desenhadas do zero**, herdando o **vocabulário visual já consolidado nas Fases 1–3** (mesma régua de `PageHeader`, `Table`, `Dialog`/`Sheet`, `FsmBadge`, filtros client-side, KPIs em `Card`). Para a **aba WhatsApp**, o molde já existe no próprio painel (`settings/integracoes`). Para a **tela pública de NPS (L3)**, espelhar o vocabulário visual do link público `book/[slug]` (`.book-page`, sem sidebar).

---

## 3. Endpoints por tela

Todos os endpoints autenticados usam JWT (`HTTPBearer`), **exceto L3 (público)**. Métodos, campos, defaults, enums e roles **confirmados contra `openapi.json` + models/services do backend**. `*` = obrigatório.

### Bloco L — NPS

**L1 — Configuração** (`/nps/config`) · roles: **OWNER/ADMIN**.
| Ação | Método + Path | Campos |
|---|---|---|
| Obter | `GET /nps/config` | `NpsConfigResponse` |
| Atualizar | `PUT /nps/config` | `NpsConfigUpdate` → `NpsConfigResponse` |

`NpsConfigResponse`: `id, company_id, enabled(bool), channel(str — default "WHATSAPP"), delay_minutes(int), min_interval_days(int), low_score_threshold(int 0–10, default 6), low_score_alert_enabled(bool)`.
`NpsConfigUpdate` (todos opcionais): `enabled?, channel?, delay_minutes?(≥0), min_interval_days?(≥0), low_score_threshold?(0–10), low_score_alert_enabled?`.
> ⚠️ `channel` é **string livre** no backend, mas os únicos valores úteis são **`WHATSAPP`** e **`EMAIL`** (espelham `CommunicationChannel`) → oferecer `Select` com esses dois. `delay_minutes` = atraso após `operation.completed` para disparar a pesquisa. `min_interval_days` = intervalo mínimo entre pesquisas para o mesmo cliente. `low_score_threshold` = nota ≤ limiar dispara alerta ao OWNER (se `low_score_alert_enabled`).

**L2 — Surveys + resposta do tenant** (`/nps/surveys`) · roles: **OWNER/ADMIN**.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /nps/surveys?status=&date_from=&date_to=` | `NpsSurveyResponse[]` (array plano) |
| Detalhe | `GET /nps/surveys/{survey_id}` | `NpsSurveyDetailResponse` |
| Responder ao cliente | `POST /nps/surveys/{survey_id}/respond` | `TenantResponseRequest{response*}` → `NpsResponseOut` |

`NpsSurveyResponse`: `id, company_id, customer_id, appointment_id, status(**PENDING|SENT|RESPONDED|EXPIRED**), scheduled_for(date-time), sent_at?, responded_at?, expires_at(date-time)`.
`NpsSurveyDetailResponse`: tudo de `NpsSurveyResponse` + `response?(NpsResponseOut)`.
`NpsResponseOut`: `id, survey_id, score(int 0–10), comment?, tenant_response?, responded_at?`.
`TenantResponseRequest`: `response*(string 1–2000)`.
> ⚠️ `POST /{id}/respond` (autenticado) é a **réplica do tenant ao cliente** — adiciona `tenant_response`, **nunca edita o `score`**. O score e o comentário vêm da resposta pública (L3). `customer_id`/`appointment_id` → compor nome via `/customers/` (ou exibir id curto + "Em breve" para nome). **Sem paginação** no servidor → filtrar client-side; `status`/`date_from`/`date_to` viram query.

**L3 — Resposta pública do cliente** (`/nps/respond/{survey_id}`) · **PÚBLICO (sem auth)** · rate limit 3/min.
| Ação | Método + Path | Campos |
|---|---|---|
| Responder | `POST /nps/respond/{survey_id}` | `PublicNpsRespondRequest{score*, comment?}` → `NpsResponseOut` |

`PublicNpsRespondRequest`: `score*(int, 0–10)`, `comment?(string, max 2000)`.
> ⚠️ **`survey_id` na URL É o token** (não há outro segredo). Só surveys **`SENT`** aceitam resposta (422 caso contrário — ex.: já respondida/expirada). **Sem `GET` público** desta survey: a tela não pré-carrega dados do cliente; é uma página cega de envio (nota + comentário). Usar `publicFetch`/`api.publicPost` (sem JWT) — **nunca** anexar token de painel. Página **fora do shell** (sem sidebar/header), no grupo de rota `(public)`.

### Bloco M — Comunicação e WhatsApp

**M1 — Templates** (`/communication/templates`) · roles: **OWNER/ADMIN**.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /communication/templates` | `TemplateResponse[]` |
| Criar | `POST /communication/templates` | `TemplateCreate` → `201 TemplateResponse` |
| Editar | `PUT /communication/templates/{template_id}` | `TemplateUpdate{body_template?, is_active?}` → `TemplateResponse` |
| Excluir | `DELETE /communication/templates/{template_id}` | → sem corpo |

`TemplateCreate`: `event_type*(str), channel*(**WHATSAPP|EMAIL|SMS**), audience*(**CLIENT|PROFESSIONAL|OWNER**), body_template*(str com `{{variáveis}}`), is_active=true, is_default=false`.
`TemplateResponse`: `template_id, company_id, event_type, channel, audience, body_template, is_active, is_default`.
> ⚠️ **No editar (`PUT`) só `body_template` e `is_active` são alteráveis** — `event_type/channel/audience` são imutáveis após criação (refletir como read-only no form de edição). `is_default=true` marca o template padrão semeado pelo onboarding — exibir badge "Padrão" e permitir editar o corpo (não excluir os default; se o backend recusar, tratar o erro). Catálogo de `event_type` e variáveis disponíveis em §5.

**M2 — Logs de envio** (`/communication/logs`) · roles: **OWNER/ADMIN** · **paginado no servidor (sem envelope)**.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /communication/logs?event_type=&status=&channel=&date_from=&date_to=&page=1&limit=50` | `CommunicationLogResponse[]` (array plano da página) |

`CommunicationLogResponse`: `log_id, company_id, template_id?, event_type, channel(WHATSAPP|EMAIL|SMS), recipient_id, recipient_type(CLIENT|PROFESSIONAL|OWNER), status(**SENT|FAILED|SKIPPED_QUIET_HOURS|SKIPPED_NO_CONSENT|SKIPPED_CHANNEL_DISABLED|SKIPPED_NO_TEMPLATE|SCHEDULED**), scheduled_send_at?, rendered_body?, sent_at?, error_message?, created_at`.
> ⚠️ **Paginação server-side por query (`page`, `limit`; `limit` máx 200, default 50), mas a resposta é um array PLANO** — **não** há `{total, page, limit, items}`. A UI controla `page` no estado; **"Próxima" habilitada quando `resposta.length === limit`**, **"Anterior" quando `page > 1`**. `date_from/date_to` são strings (sem `format` no schema) — enviar ISO. `error_message` só em `FAILED`; `scheduled_send_at` só em `SCHEDULED`. Tratamento especial de paginação descrito em §5.

**M3 — WhatsApp (conexão + QR)** (`/whatsapp/*`) · roles: **OWNER/ADMIN** · **JÁ IMPLEMENTADO** em `settings/integracoes`.
| Ação | Método + Path | Campos |
|---|---|---|
| Status | `GET /whatsapp/connection` | `ConnectionResponse` |
| Iniciar | `POST /whatsapp/connection` | (sem body) → `ConnectionResponse` |
| Desconectar | `DELETE /whatsapp/connection` | (sem corpo) |
| Atualizar QR | `GET /whatsapp/qr` | `QRCodeResponse` |

`ConnectionResponse`: `status(**DISCONNECTED|CONNECTING|CONNECTED|ERROR**), phone_number?, connected_at?(ISO), qr_code?(**base64 SEM prefixo**), qr_expires_in?(seg), disconnect_reason?`.
`QRCodeResponse`: `qr_code(**base64 SEM o prefixo `data:image/png;base64,`**), expires_in(int, ~60s)`.
> ⚠️ **Shape do QR confirmado no código:** `qr_code` é **base64 puro, sem o prefixo** — renderizar com `<img src={`data:image/png;base64,${qr_code}`} />`. `POST /connection` retorna `CONNECTING` + `qr_code` (409 se já `CONNECTED`); `GET /qr` regenera (409 se `CONNECTED`); `DELETE /connection` desconecta. **Polling do estado**: `GET /connection` (o backend sincroniza com a Evolution API quando `CONNECTING` e vira `CONNECTED`). **Esta aba já existe** — Fase 4 não a reescreve. Opcional: expor `whatsapp_api_type` (`UNOFFICIAL_BAILEYS|OFFICIAL_META`) e quiet hours via `PUT /communication/settings` na tela de Comunicação.

### Bloco N — Administração

**N1 — Usuários e Acessos** (`/users/*`) · roles: **OWNER/ADMIN** · **parcialmente implementado** (lista + convite).
| Ação | Método + Path | Campos |
|---|---|---|
| Lista de usuários | `GET /users/` | `UserResponse[]` |
| Convidar | `POST /users/invite` | `InviteUserRequest{email*, role*, name?}` → `201 InviteUserResponse` |
| Alterar papel | `PATCH /users/{user_id}/role` | `AssignRoleRequest{role*}` → `UserResponse` |
| Desativar | `DELETE /users/{user_id}` | → `UserResponse` (active=false) |
| Transferir propriedade | `POST /users/transfer-ownership` | `TransferOwnershipRequest{new_owner_user_id*, current_owner_new_role="ADMIN"}` → `UserResponse` |
| Convites pendentes | `GET /users/invitations` | `InvitationResponse[]` |
| Cancelar convite | `DELETE /users/invitations/{invitation_id}` | → `InvitationResponse` (status=CANCELLED) |

`UserResponse`: `id, company_id?, email, name?, role, active`.
`InviteUserResponse`: `invitation_id, expires_at`.
`InvitationResponse`: `invitation_id, email, role, status(PENDING|CANCELLED|…), expires_at, created_at, invited_by_user_id, company_id?`.
> ⚠️ **Anti-escalonamento — regras EXATAS do backend** (`INVITE_PERMISSION` em `models/user.py`; a UI deve enforçar, não só reagir ao 403):
> - **OWNER** pode convidar/atribuir: `OWNER, ADMIN, OPERATOR, PROFESSIONAL` (e `CLIENT`, irrelevante no painel de equipe).
> - **ADMIN** pode convidar/atribuir **apenas** `OPERATOR, PROFESSIONAL` — **nunca** `OWNER` nem `ADMIN`.
> - `OPERATOR/PROFESSIONAL/CLIENT` não convidam ninguém (não chegam a esta tela — é OWNER/ADMIN only).
> - **`PLATFORM_OWNER`** só é atribuível por outro `PLATFORM_OWNER` (403) → **nunca oferecer** no painel do tenant.
> - **`PLATFORM_SUPPORT/PLATFORM_BILLING/PLATFORM_READONLY`** são *schema-only* → 422 → **nunca oferecer**.
> - **Não alterar o próprio papel** (`PATCH role` no próprio id → 403) → ocultar/desabilitar a ação na própria linha.
> - **Não desativar o último OWNER ativo** (`DELETE` → 422) → desabilitar com `Tooltip` quando só houver 1 OWNER ativo.
> - **`transfer-ownership` só para OWNER** (403 p/ ADMIN): promove o alvo a OWNER e rebaixa o ator para `current_owner_new_role` (default `ADMIN`) — ação sensível, `Dialog` de confirmação dupla.
> - **DIVERGÊNCIA com o enunciado da fase:** o backend **não bloqueia** um OWNER rebaixar **outro** OWNER via `PATCH role` (a única proteção a OWNER é o self-guard + o "último OWNER ativo"). Tratar "OWNER não rebaixa outro OWNER" como **guarda de UX opcional** (confirmação extra), **não** como regra do backend. Documentar como tal — não afirmar que o 403 cobre isso.

**N2 — Módulos do tenant** (`/tenant/modules`) · roles: **OWNER/ADMIN**.
| Ação | Método + Path | Campos |
|---|---|---|
| Lista | `GET /tenant/modules` | `ModuleActivationResponse[]` |
| Ativar | `POST /tenant/modules/{module_name}/activate` | → `ModuleActivationResponse` |
| Desativar | `POST /tenant/modules/{module_name}/deactivate` | → `ModuleActivationResponse` |

`ModuleActivationResponse`: `activation_id, company_id, module_name, is_active(bool)`.
> ⚠️ **`module_name` é enum fechado** (`models/module_activation.py`): **`ESTOQUE, COMISSOES, PACOTES, ASSINATURAS, PROMOCOES, CRM, NPS, FILA, BOT_WHATSAPP, LINK_PUBLICO`** (10). O onboarding cria as 10 ativações por tenant — a lista vem completa; o toggle chama activate/deactivate. Glossário de nomes amigáveis + descrição em §5. Não há campo de dependências no backend; documentar dependências conhecidas apenas como **texto informativo** (ex.: PACOTES/ASSINATURAS usam pagamentos; BOT_WHATSAPP depende de conexão ativa em Integrações) — não inventar campo.

**N3 — Branding** (`/tenant/branding`) · GET **público** (query `company_id`), PUT **OWNER/ADMIN**.
| Ação | Método + Path | Campos |
|---|---|---|
| Obter | `GET /tenant/branding?company_id={uuid}` | `TenantBrandingResponse` |
| Atualizar | `PUT /tenant/branding` | `TenantBrandingUpdate` → `TenantBrandingResponse` |

`TenantBrandingResponse`: `branding_id, company_id, logo_url?, primary_color?(hex `#RRGGBB`), secondary_color?(hex), font_family?, favicon_url?, custom_texts(object)`.
`TenantBrandingUpdate` (todos opcionais): `logo_url?, primary_color?, secondary_color?, font_family?, favicon_url?, custom_texts?`.
> ⚠️ **DIVERGÊNCIA com o enunciado:** os campos reais são **`primary_color`, `secondary_color`, `font_family`, `logo_url`, `favicon_url`, `custom_texts`** — **não** existem `accent_color` nem `font_display`. `primary_color`/`secondary_color` são strings hex de 7 chars (`#RRGGBB`). `custom_texts` é um objeto JSON livre (chave→texto). **Upload de logo/favicon** via `POST /uploads/` (multipart, padrão existente) → grava a URL retornada em `logo_url`/`favicon_url`. **GET é público** (usa `company_id` como query) — para o painel autenticado, usar `useAuth().companyId`.

**N4 — Auditoria** (`/audit/*`) · roles: lista/impersonation **OWNER/ADMIN**; **export OWNER apenas (ADMIN → 403)**.
| Ação | Método + Path | Campos |
|---|---|---|
| Logs | `GET /audit/logs?company_id=&action=&actor_id=&date_from=&date_to=&page=1&limit=50` | `{total, page, limit, items[]}` |
| Exportar | `GET /audit/logs/export?company_id=&action=&actor_id=&date_from=&date_to=` | **CSV** (download) |
| Acessos de impersonation | `GET /audit/impersonation-accesses?page=1&limit=50` | `{total, page, limit, items[]}` |

`items[]` de `/logs`: `{audit_id, company_id?, actor_id, actor_role, action, resource_type, resource_id?, reason?, before_snapshot?, after_snapshot?, occurred_at(ISO), ip_address?}`.
`items[]` de `/impersonation-accesses`: `{audit_id, grant_id?, actor_id, reason?, request, occurred_at}`.
> ⚠️ **Paginação server-side COM envelope** (`{total, page, limit, items}`) — diferente de M2 (que é array plano). `limit` máx 500. **Tenant só vê o próprio `company_id`** (o backend força; passar `company_id` de outro tenant é ignorado salvo PLATFORM_OWNER). **`/logs/export` é OWNER-only** (ADMIN → 403) e retorna **`text/csv`** (`Content-Disposition: attachment; filename=audit_logs.csv`) — abrir como download (anchor/`window.open` com header de auth, ou `api` que respeite blob). O próprio export **gera um registro de auditoria** ("export_audit"). **Append-only:** a trilha **não tem ações de edição/exclusão** — só leitura, filtro, paginação e export.

---

## 4. Especificação das 10 telas

Para cada tela: **rota · role · layout · componentes shadcn · estados · ações**. Estados obrigatórios em todas (exceto L3): **vazio (`EmptyState`) · loading (`Skeleton`) · erro (`ErrorState` com retry) · dados**.

### L1 — `/nps/config` — Configuração do NPS
- **Role:** OWNER/ADMIN.
- **Layout:** `PageHeader` "NPS — Configuração"; `Card` com formulário.
- **Form (`GET` preenche, `PUT` salva):** `Switch` "Pesquisa ativada" (`enabled`), `Select` canal (`WHATSAPP`/`EMAIL`), `Input` numérico `delay_minutes` (atraso pós-atendimento, hint "minutos após a conclusão"), `Input` numérico `min_interval_days` (hint "dias mínimos entre pesquisas ao mesmo cliente"), `Input`/`Slider` `low_score_threshold` (0–10), `Switch` "Alertar OWNER em nota baixa" (`low_score_alert_enabled`).
- **Ação:** botão "Salvar" → `PUT /nps/config` → toast. Loading/erro do `GET`.

### L2 — `/nps` — Surveys + resposta do tenant
- **Role:** OWNER/ADMIN.
- **Layout:** `PageHeader` "NPS — Pesquisas" + link/botão "Configuração" (→ L1); faixa de filtros (status, período) + `Table`.
- **Colunas:** Cliente (`customer_id`→nome ou "Em breve") · **Status** (`NpsSurveyBadge`) · Agendada para (`scheduled_for`) · Enviada (`sent_at` ou "—") · Respondida (`responded_at` ou "—") · **Nota** (do detalhe / `response.score` — chip colorido por faixa NPS, ver §5) · ações.
- **Filtros (client+query):** `status` (PENDING/SENT/RESPONDED/EXPIRED), `date_from/to` (`DateTimePicker`). Repassar ao `GET`.
- **Detalhe (`Sheet`/`Dialog`, `GET /{id}`):** dados da survey + bloco da **resposta do cliente** (`score`, `comment`) + **réplica do tenant** (`tenant_response`). Se `status=RESPONDED` e `tenant_response` vazio → `Textarea` "Responder ao cliente" (1–2000) + botão → `POST /{id}/respond` → toast. **Nunca** editar o score.
- **Componentes:** `Table`, `Sheet`, `Textarea`, `Badge`, `Select`, `Skeleton`, `EmptyState`.

### L3 — `/nps/respond/[survey_id]` — Resposta pública (sem auth, sem shell)
- **Role:** público (sem login). **Grupo de rota `(public)`** — **sem sidebar, sem header do painel.**
- **Layout:** página minimalista centralizada (espelhar `book/[slug]` / `.book-page`): logo/marca opcional, título "Como foi sua experiência?", **seletor de nota 0–10** (11 botões/segmentos ou `RadioGroup` horizontal — destacar faixas detrator/neutro/promotor visualmente, ver §5), `Textarea` "Comentário (opcional)" (max 2000), botão "Enviar".
- **Ação:** `POST /nps/respond/[survey_id]` via `publicFetch`/`api.publicPost` (**sem JWT**) com `{score, comment?}`.
- **Estados:** **idle** (form) · **enviando** (botão desabilitado + spinner) · **sucesso** (tela de agradecimento "Obrigado pelo seu feedback!", sem voltar ao form) · **erro** (422 já respondida/expirada → mensagem "Esta pesquisa não está mais disponível"; outros → "Não foi possível enviar, tente novamente"). Não há `GET` público — não pré-carregar nada.

### M1 — `/comunicacao` — Templates (CRUD + preview de canal)
- **Role:** OWNER/ADMIN.
- **Layout:** `PageHeader` "Comunicação — Templates" + botão "Novo template"; abas/segmentação por **canal** (Todos · WhatsApp · Email) **client-side** + `Table` (ou cards agrupados por `event_type`).
- **Colunas/cartão:** Evento (`COMMUNICATION_EVENT_TYPE_LABELS`) · Canal (`COMMUNICATION_CHANNEL_LABELS`) · Público (`COMMUNICATION_AUDIENCE_LABELS`) · Ativo (`ActiveBadge` por `is_active`) · Padrão (badge se `is_default`) · ações.
- **Form criar (`Dialog`):** `Select` evento (catálogo §5), `Select` canal (WHATSAPP/EMAIL/SMS), `Select` público (CLIENT/PROFESSIONAL/OWNER), `Textarea` corpo com **hint das `{{variáveis}}` disponíveis por evento** (chips clicáveis que inserem a variável no cursor — ver §5), `Switch` ativo. → `POST`.
- **Form editar (`Dialog`):** evento/canal/público **read-only** (mostrar como rótulos), só `Textarea` corpo + `Switch` ativo editáveis → `PUT`.
- **Preview de canal:** painel ao lado do `Textarea` renderizando o corpo como "bolha" de WhatsApp ou "email" (apenas visual; substituir `{{var}}` por valores de exemplo). 
- **Ações:** criar, editar, excluir (`Dialog` de confirmação; default templates: permitir editar corpo, alertar antes de excluir).

### M2 — `/comunicacao/logs` — Histórico de envios (paginado)
- **Role:** OWNER/ADMIN.
- **Layout:** `PageHeader` "Logs de comunicação" + filtros (evento, status, canal, período) + `Table` + **controles de paginação** (Anterior/Próxima + indicador "Página N").
- **Colunas:** Data (`created_at`) · Evento (`COMMUNICATION_EVENT_TYPE_LABELS`) · Canal · Destinatário (`recipient_type` + id curto) · **Status** (`CommunicationLogBadge`) · Agendado p/ (`scheduled_send_at` se SCHEDULED) · ações (ver corpo renderizado).
- **Detalhe (`Sheet`):** `rendered_body` (texto do que foi enviado) + `error_message` (se FAILED).
- **Paginação (especial — array plano):** estado `page` (1-based) + `limit` (50); "Próxima" habilitada se `length === limit`; "Anterior" se `page>1`. Filtros e page repassados ao `GET` (server-side). Ver §5.

### M3 — `/settings/integracoes` (aba WhatsApp) — **verificar/alinhar, não refazer**
- **Role:** OWNER/ADMIN.
- **Estado:** **já implementado** (`TabWhatsApp`): Conectar → `POST /connection`; QR via `data:image/png;base64,${qr_code}`; contagem regressiva (`qr_expires_in`); "Gerar novo QR" → `GET /qr`; Desconectar → `DELETE /connection`; polling 3s (CONNECTING) / 30s (CONNECTED) / 60s (idle); `StatusBadge` (DISCONNECTED/CONNECTING/CONNECTED/ERROR).
- **Lacunas opcionais (Ajustar):** trocar `confirm()` por `Dialog`; trocar texto de erro cru por `sonner`; (opcional) `Select` `whatsapp_api_type` (UNOFFICIAL_BAILEYS/OFFICIAL_META) e quiet hours via `PUT /communication/settings`. **Não reescrever o fluxo de QR.**

### N1 — `/settings/usuarios` — Lista + convidar + papéis (+ transferir/convites)
- **Role:** OWNER/ADMIN.
- **Estado:** lista + convidar (com `name`) **já existem**; **acrescentar** o restante.
- **Layout:** `PageHeader` "Usuários" + botão "Convidar usuário"; `Tabs` "Membros" | "Convites pendentes".
- **Tab Membros (`GET /users/`):** Nome (`name` ou "—") · E-mail · Papel (`ROLE_LABELS`) · Ativo (`ActiveBadge`) · ações.
  - **Alterar papel:** `Select` (com **opções filtradas pelo papel do ator** — ver anti-escalonamento §3 N1) → `PATCH /{id}/role`. **Oculto na própria linha.**
  - **Desativar:** `DELETE /{id}` (`Dialog`). **Desabilitado (Tooltip) se for o último OWNER ativo.**
  - **Transferir propriedade:** botão **visível só para OWNER** → `Dialog` (escolher novo OWNER entre membros ativos + `Select` "Seu novo papel" default ADMIN) → `POST /transfer-ownership`, confirmação dupla.
- **Tab Convites (`GET /users/invitations`):** E-mail · Papel · Status · Expira em · Convidado por · **Cancelar** (`DELETE /invitations/{id}`, só PENDING).
- **Convidar (`Dialog`):** `Input` e-mail, `Input` nome (opcional), `Select` papel (**opções conforme ator**: OWNER→[OWNER, ADMIN, OPERATOR, PROFESSIONAL]; ADMIN→[OPERATOR, PROFESSIONAL]). → `POST /invite` → toast com expiração.
- **Regra dura na UI:** o `Select` de papel **nunca** lista PLATFORM_* nem papéis acima do permitido ao ator.

### N2 — `/settings/modulos` — Ativar/desativar módulos
- **Role:** OWNER/ADMIN.
- **Layout:** `PageHeader` "Módulos" + grid de **cards de módulo** (`GET /tenant/modules`).
- **Card:** ícone + Nome amigável (`MODULE_LABELS`) + descrição (`MODULE_DESCRIPTIONS`) + dependências (texto informativo, §5) + `Switch` (`is_active`).
- **Ação:** `Switch` → `POST /{module_name}/activate` | `/deactivate` → toast + atualiza card. Desabilitar o switch durante a chamada (otimista com rollback no erro).
- **Componentes:** `Card`, `Switch`, `Skeleton`, `Tooltip`.

### N3 — `/settings/branding` — Logo, cores, fonte (preview ao vivo)
- **Role:** OWNER/ADMIN.
- **Layout:** duas colunas — **esquerda: formulário**, **direita: preview ao vivo**.
- **Form (`GET ...?company_id=useAuth().companyId` preenche):** upload de **logo** (`/uploads/`→`logo_url`) com preview da imagem, upload de **favicon** (`favicon_url`), **color picker** `primary_color` (`#RRGGBB`) e `secondary_color`, `Select`/`Input` `font_family`. (`custom_texts` opcional — editor chave→valor simples; pode ficar "Em breve" se não priorizado.)
- **Preview ao vivo:** mini-mock (header + botão + card) usando **as cores/fonte escolhidas como valores literais** (inline style ou CSS var local) — atualiza a cada mudança, antes de salvar.
- **Ação:** "Salvar" → `PUT /tenant/branding` → toast. Validar hex (`#` + 6).
- **Componentes:** `Input[type=color]` ou color picker, upload (padrão `/uploads/`), `Card`, `Button`.

### N4 — `/audit` — Trilha de auditoria (paginada, append-only, export)
- **Role:** OWNER/ADMIN (export **OWNER only**).
- **Layout:** `PageHeader` "Auditoria" + botão **"Exportar CSV"** (visível/habilitado só p/ OWNER) + filtros + `Tabs` "Trilha" | "Acessos de impersonation".
- **Tab Trilha (`GET /audit/logs`):** `Table` — Data (`occurred_at`) · Ator (`actor_id` curto + `actor_role`) · Ação (`action`) · Recurso (`resource_type` + `resource_id` curto) · Motivo (`reason` ou "—") · IP (`ip_address` ou "—") · ações (ver `before/after_snapshot` em `Sheet`/`Dialog` — JSON formatado, read-only).
- **Filtros (query):** `action`, `actor_id`, `date_from/to`. (`company_id` é forçado ao próprio tenant — não expor.)
- **Paginação (envelope):** usar `total/page/limit` da resposta → "Página N de ⌈total/limit⌉", Anterior/Próxima.
- **Tab Impersonation (`GET /audit/impersonation-accesses`):** Data · Grant (`grant_id`) · Ator (`actor_id`) · Motivo · Requisição (`request` — JSON em `Sheet`). Mesma paginação.
- **Export:** `GET /audit/logs/export` com os filtros atuais → download CSV. Se ADMIN (sem permissão) → ocultar/desabilitar com `Tooltip` "Apenas OWNER".
- **Append-only:** **sem** editar/excluir/criar — só leitura + filtro + paginação + export.

> **Contagem das 10 telas/superfícies:** L1(1) · L2 surveys+detalhe(2) · L3 pública(3) · M1 templates(4) · M2 logs(5) · M3 WhatsApp tab(6) · N1 usuários(7) · N2 módulos(8) · N3 branding(9) · N4 audit(10).

---

## 5. Padrões de UX específicos da Fase 4

### Badges de FSM novos — adicionar a `components/FsmBadge.tsx`
Reusar `EMERALD/AMBER/DESTRUCTIVE/NEUTRAL/SKY` já definidos. Valores **exatos do backend**.

**NpsSurvey** (`NpsSurveyBadge`):
| Estado | Label | Cor |
|---|---|---|
| `PENDING` | Pendente | âmbar |
| `SENT` | Enviada | sky |
| `RESPONDED` | Respondida | emerald |
| `EXPIRED` | Expirada | muted |

**CommunicationLog** (`CommunicationLogBadge`):
| Estado | Label | Cor |
|---|---|---|
| `SENT` | Enviada | emerald |
| `SCHEDULED` | Agendada | sky |
| `FAILED` | Falhou | destructive |
| `SKIPPED_QUIET_HOURS` | Adiada (silêncio) | muted |
| `SKIPPED_NO_CONSENT` | Sem consentimento | muted |
| `SKIPPED_CHANNEL_DISABLED` | Canal desativado | muted |
| `SKIPPED_NO_TEMPLATE` | Sem template | muted |

### Score NPS — faixa de cor (apenas display)
Convenção NPS: **0–6 detrator (vermelho)**, **7–8 neutro (âmbar)**, **9–10 promotor (emerald)**. Usar como chip colorido do `score` em L2/L3. É **exibição**, não regra de negócio. (O alerta de "nota baixa" do backend usa `low_score_threshold`, default 6 — independente desta faixa visual.)

### Glossários de enum — adicionar a `lib/constants.ts` (fonte única)
- `NPS_SURVEY_STATUS_LABELS`: `PENDING`→"Pendente", `SENT`→"Enviada", `RESPONDED`→"Respondida", `EXPIRED`→"Expirada".
- `COMMUNICATION_LOG_STATUS_LABELS`: `SENT`→"Enviada", `SCHEDULED`→"Agendada", `FAILED`→"Falhou", `SKIPPED_QUIET_HOURS`→"Adiada (silêncio)", `SKIPPED_NO_CONSENT`→"Sem consentimento", `SKIPPED_CHANNEL_DISABLED`→"Canal desativado", `SKIPPED_NO_TEMPLATE`→"Sem template".
- `COMMUNICATION_CHANNEL_LABELS`: `WHATSAPP`→"WhatsApp", `EMAIL`→"E-mail", `SMS`→"SMS".
- `COMMUNICATION_AUDIENCE_LABELS`: `CLIENT`→"Cliente", `PROFESSIONAL`→"Profissional", `OWNER`→"Proprietário".
- `WHATSAPP_API_TYPE_LABELS`: `UNOFFICIAL_BAILEYS`→"Não-oficial (Baileys)", `OFFICIAL_META`→"Oficial (Meta)".
- `MODULE_LABELS`: `ESTOQUE`→"Estoque", `COMISSOES`→"Comissões", `PACOTES`→"Pacotes", `ASSINATURAS`→"Assinaturas", `PROMOCOES`→"Promoções", `CRM`→"CRM", `NPS`→"NPS", `FILA`→"Fila de espera", `BOT_WHATSAPP`→"Bot WhatsApp", `LINK_PUBLICO`→"Link público".
- `MODULE_DESCRIPTIONS` (texto curto por módulo — informativo): ex. `BOT_WHATSAPP`→"Atendimento automático via WhatsApp (requer conexão ativa em Integrações)", `LINK_PUBLICO`→"Página pública de agendamento", etc.
- `COMMUNICATION_EVENT_TYPE_LABELS` (catálogo do backend, `_DEFAULT_TEMPLATES`):
  - `appointment.confirmed`→"Agendamento confirmado", `appointment.cancelled`→"Agendamento cancelado", `appointment.reminder_24h`→"Lembrete 24h", `appointment.reminder_2h`→"Lembrete 2h", `appointment.completed`→"Atendimento concluído", `appointment.no_show`→"Não comparecimento", `auth.password_reset_requested`→"Redefinição de senha", `user.invitation_sent`→"Convite de usuário", `nps.survey_request`→"Pesquisa NPS", `nps.low_score_alert`→"Alerta de nota baixa", `waitlist.slot_available`→"Vaga disponível (fila)", `conversation.escalated`→"Conversa escalada".

### Editor de template — variáveis por evento
O backend usa `{{variavel}}`. Conjunto observado nos templates default: `{{cliente_nome}}, {{servico}}, {{profissional}}, {{data}}, {{horario}}, {{empresa_nome}}, {{manage_url}}, {{nps_url}}, {{token}}, {{user_name}}, {{company_name}}, {{activation_link}}, {{nota}}, {{comentario}}, {{customer_name}}, {{phone}}, {{panel_url}}`. Sugestão de mapa `TEMPLATE_VARIABLES_BY_EVENT` (chips clicáveis no editor):
- `appointment.*`: `{{cliente_nome}} {{servico}} {{profissional}} {{data}} {{horario}} {{empresa_nome}} {{manage_url}}`
- `nps.survey_request`: `{{cliente_nome}} {{nps_url}}`
- `nps.low_score_alert`: `{{cliente_nome}} {{nota}} {{comentario}}`
- `user.invitation_sent`: `{{company_name}} {{activation_link}} {{role}}`
- `auth.password_reset_requested`: `{{user_name}} {{token}}`
- `waitlist.slot_available`: `{{cliente_nome}}`
- `conversation.escalated`: `{{customer_name}} {{phone}} {{panel_url}}`
> É um **hint de UX** (chips que inserem a variável no `Textarea`), não validação — o backend não valida o conjunto. Não bloquear variáveis fora da lista.

### QR code WhatsApp — como renderizar
`qr_code` é **base64 SEM prefixo** → `<img src={`data:image/png;base64,${qr_code}`} alt="QR Code WhatsApp" />`. **Polling** do `GET /whatsapp/connection` (3s enquanto CONNECTING) detecta a transição para CONNECTED (o backend sincroniza com a Evolution API). Contagem regressiva a partir de `qr_expires_in`; ao zerar, limpar o QR e oferecer **"Gerar novo QR"** (`GET /whatsapp/qr`). **Esse comportamento já está implementado** em `settings/integracoes` — usar como referência; **não duplicar**.

### Paginação — duas formas distintas nesta fase
- **`/communication/logs` (M2): array PLANO.** Server pagina por `page`/`limit`; resposta sem `total`. UI: "Próxima" habilitada quando `resposta.length === limit`; "Anterior" quando `page>1`. Mostrar só "Página N".
- **`/audit/logs` e `/audit/impersonation-accesses` (N4): envelope `{total, page, limit, items}`.** UI: "Página N de ⌈total/limit⌉", botões habilitados conforme `total`.
> Não unificar os dois — são contratos diferentes. Documentar no código qual endpoint é qual.

### NPS público (L3) — tela sem auth e sem shell
- **Grupo `(public)`** — sem `(dashboard)/layout.tsx`, sem sidebar/header. Espelhar o visual de `book/[slug]` (`.book-page`).
- Chamada **sem JWT** (`publicFetch`/`api.publicPost`). Não há `GET` — não pré-carregar.
- Estados: idle → enviando → sucesso (agradecimento) | erro (422 = "indisponível").

### Anti-escalonamento (N1) — a UI enforça, não só reage ao 403
Resumo operacional (regras exatas em §3 N1): o `Select` de papel é **derivado do papel do ator**; PLATFORM_* nunca aparecem; própria linha não tem "alterar papel"; último OWNER ativo não desativável; transfer-ownership só OWNER. O 403 do backend é a rede de segurança — a UI não deve **oferecer** a ação proibida.

### Regras transversais (idênticas às Fases 1–3)
- **Toast** (`sonner`) após toda ação (success/error); erro deriva do `detail` da API (array 422 já tratado em `lib/api.ts`).
- **Datas** com `formatDateTime()` (timezone do tenant).
- **Sem paginação no servidor** em L2 e M1 → filtrar client-side; M2 e N4 paginam no servidor (ver acima).
- **Ação sem endpoint** (editar evento/canal/público de template; reabrir/editar audit; criar módulo novo) → **não renderizar** ou `disabled` + `Tooltip`.
- **Campos ausentes** (nome do cliente/usuário quando só vem id) → compor via lista correspondente ou `"Em breve"`.

---

## 6. O que NÃO entra na Fase 4

- **Portal do Cliente** (`(portal)/*`) e **Painel Owner** (`(owner)/*`, `PLATFORM_OWNER`) — Fase 5.
- **Telas públicas `/gestao/[token]`** (gestão de agendamento por token) — Fase 5. (A **única** pública desta fase é `/nps/respond/[survey_id]`.)
- **`/platform/*`** (audit cross-tenant, redispatch, impersonation grants, settings globais) — Painel Owner, Fase 5. A Fase 4 só consome `/audit/impersonation-accesses` (visão do tenant), **não** `/platform/audit`.
- **Reescrever a aba WhatsApp** (já existe) e **a tela de settings de canais** (`/settings/comunicacao`, toggles já existem) — só expandir se priorizado.
- **Tokenização de cartão / payment-sources do cliente** — Portal, Fase 5.
- **Validação semântica de `{{variáveis}}`** no editor de template — o backend não valida; a UI só oferece chips de inserção.
- **Campos inexistentes** — não inventar `accent_color`/`font_display` (branding usa `secondary_color`/`font_family`), nem campo de "dependências" de módulo (apenas texto informativo).

---

*Fonte de verdade de comportamento: `visao-estagio-0.md` + `openapi.json` (head `e0s25f_product_extras`); FSMs/enums conferidos em `app/infrastructure/db/models/` (`user.py` → `INVITE_PERMISSION`; `module_activation.py`; `communication_log.py`; `nps.py`; `tenant_branding.py`; `communication_setting.py`), `app/modules/{nps,users,communication,whatsapp,audit}/`. O protótipo `barberflow-system` **não cobre esta fase** (referência visual apenas). Onde divergir, vence este documento. Documento de planejamento — nenhuma regra de negócio vive no frontend.*
