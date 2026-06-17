# PALADINO — BRIEF DA FASE 5B (LOVABLE)

**Objetivo:** especificar o **Portal do Cliente** — o aplicativo web onde o **cliente
final** (não o operador do tenant) gerencia sua relação com **todos os
estabelecimentos** que frequenta: agendamentos, cotas, assinaturas, consentimentos
e perfil. É um **shell completamente separado** do painel do tenant e das
superfícies públicas. Derivado de `painel/docs/inventario-funcional.md`
(§5 Portal do Cliente · §3 estrutura `(portal)/`) e de
`agendamento_engine/openapi.json` (tag `portal`, 18 endpoints; head
`e0s25f_product_extras`). Contratos e divergências **conferidos diretamente no
backend** (`modules/portal/`, `modules/identity/`) — não inferidos.

> **Continuação das Fases 0–5A.** O painel autenticado (`(dashboard)/`) e as
> superfícies públicas (`(public)/`) já existem. Esta fase **não toca** em nenhum
> dos dois: o Portal roda num **terceiro shell** (`(portal)/`), com **autenticação
> própria** (JWT `type="portal"`). **Dados mockados** no protótipo Lovable; a
> integração real é feita depois pelo Claude Code.

> **Escopo rígido:** apenas as 9 telas do Portal abaixo. **NÃO** entra o Painel
> Owner (`(owner)/*`, `PLATFORM_OWNER`) — é a **Fase 5C**.

> **⚠️ Já existe — não recriar do zero:**
> - **`app/(portal)/layout.tsx`** já existe (entregue na Fase 0): shell mínimo com
>   wordmark `PALADINO` + `max-w-3xl`, **sem nav, sem guard de auth**. A Fase 5B
>   **estende** esse grupo de rota — ver §2 sobre como separar as páginas de
>   autenticação (sem nav) das páginas autenticadas (com nav + guard).
> - **Identidade `PaladinoIdentity`** é global (cross-tenant) — o backend resolve
>   os dados por tenant a partir dela. O Portal **não** escolhe `company_id` no
>   header de auth; ele aparece como **filtro/agrupador** nas telas multi-tenant.

---

## 1. Contexto

O **Portal do Cliente** é **Paladino-wide**: uma única conta (`PaladinoIdentity`,
resolvida por telefone E.164) dá ao cliente acesso à sua relação com **todos os
tenants** onde ele tem histórico. As telas são, por natureza, **multi-tenant** —
um agendamento, uma cota ou uma assinatura sempre pertencem a **um
estabelecimento**, e o portal **destaca o estabelecimento** em cada item.

O cliente entra por **magic link** (padrão) ou **e-mail + senha**. O JWT emitido
tem `type="portal"` e **não carrega `company_id`** — o backend cruza
`identity → customers.identity_id → dados tenant-scoped` em cada chamada. Esse
token **nunca** pode se misturar com o JWT do painel do tenant nem vazar para as
chamadas públicas (`publicFetch`).

O Portal é **mobile-first** (o cliente abre no celular), mas, ao contrário das
superfícies públicas, é uma **área autenticada de sessão longa**: tem navegação
persistente (lateral em `md+`, bottom nav no mobile) e **guard que redireciona ao
login em `401`**.

---

## 2. Shell do Portal — separação dos três contextos

O projeto passa a ter **três shells de produto independentes**:

| Shell | Grupo de rota | Auth | Helper de API | Header / Nav |
|---|---|---|---|---|
| **Painel do Tenant** | `(dashboard)/` | JWT tenant (`localStorage["token"]`) | `apiFetch` / `api.*` | Sidebar petrol + Header do operador |
| **Públicas** | `(public)/` + `book/[slug]/` | **nenhuma** | `publicFetch` (sem JWT) | Wordmark PALADINO, sem nav |
| **Portal do Cliente** | `(portal)/` | **JWT portal** (chave separada) | **`portalFetch`** (a criar) | Nav própria do cliente; **sem** sidebar/Header do tenant |

> **Princípio inviolável:** o Portal **não importa** o `Sidebar`, o `Header`, o
> `AuthContext` nem o `apiFetch` do painel do tenant. Nenhum elemento de operador
> (RBAC, "Barbeiros", financeiro do tenant) aparece. O cliente vê **a relação dele
> com os estabelecimentos**, não a administração de nenhum deles.

### 2.1 Tabela de JWT por shell

| Claim | JWT tenant | JWT portal |
|---|---|---|
| `sub` | user_id | **identity_id** |
| `type` | (ausente) | **`"portal"`** |
| `company_id` | presente | **ausente** |
| Expiração | — | **24h** |
| Storage | `localStorage["token"]` | **chave separada** (ex.: `localStorage["portal_token"]`) |

`get_current_user` (endpoints do tenant) **rejeita** qualquer JWT com claim `type`;
`verify_portal_token` **rejeita** `type != "portal"`. Ou seja: os tokens são
**mutuamente inutilizáveis** — manter as chaves de storage separadas é obrigatório.

### 2.2 Helper `portalFetch` — **ainda não existe; criar em `lib/portal-api.ts`**

`lib/api.ts` hoje tem **dois** helpers: `apiFetch` (JWT do tenant, com handler de
`401` que faz logout do painel) e `publicFetch` (sem JWT, expõe `.status` no erro).
**Nenhum dos dois serve ao Portal.** O Claude Code criará um **terceiro**:

```
portalFetch<T>(path, options?)  →  em lib/portal-api.ts
```

Convenção que `portalFetch` deve seguir (espelha `apiFetch`, mas isolado):
- **Lê o token de uma chave própria** do `localStorage` (ex.: `portal_token`) — **nunca** a chave `"token"` do tenant.
- Anexa `Authorization: Bearer <portal_token>` quando há token.
- **No `401`:** redireciona para **`/portal/login`** (não para o login do tenant) e limpa a chave do portal. Um `setPortalAuthErrorHandler` análogo ao `setAuthErrorHandler` resolve o redirect via contexto do portal.
- **Expõe `.status` no erro lançado** (mesmo padrão `Object.assign` de `apiFetch`/`publicFetch`), para as telas distinguirem `401`/`409`/`422`.
- `204 → undefined`; demais `2xx → res.json()`.
- Helpers de conveniência opcionais: `portal.get/post/patch/delete` espelhando `api.*`.

> No **protótipo Lovable** nada disso existe — os dados são mockados. Esta seção é a
> **especificação para o wiring real**. Documentar a lacuna; **não** reaproveitar
> `apiFetch` (faria logout do painel) nem `publicFetch` (não manda Authorization).

### 2.3 Estrutura de rotas recomendada (separar auth de área autenticada)

As telas de **autenticação** (`login`, `magic`) **não** têm nav nem guard; as
**autenticadas** têm ambos. Em App Router, recomenda-se um **grupo aninhado**:

```
app/(portal)/
  layout.tsx                 ← shell externo mínimo (já existe; wordmark, sem nav)
  login/page.tsx             ← FORA da área autenticada (sem nav, sem guard)
  magic/[token]/page.tsx     ← FORA da área autenticada (landing de consumo)
  (app)/                     ← grupo autenticado
    layout.tsx               ← guard (401→/portal/login) + nav lateral/bottom
    dashboard/page.tsx
    historico/page.tsx
    cotas/page.tsx
    assinaturas/page.tsx
    consentimentos/page.tsx
    pagamentos/page.tsx
    perfil/page.tsx
```

> O protótipo Lovable é agnóstico de path (TanStack/Vite) — esta árvore é a
> tradução-alvo para o Claude Code. **Importante:** a nav do cliente vive no layout
> do grupo `(app)/`, **não** no `(portal)/layout.tsx` externo (senão apareceria na
> tela de login).

---

## 3. Autenticação do Portal

### 3.1 Magic link (modo padrão)
1. `/portal/login` (aba Magic link): campo e-mail → `POST /portal/auth/magic-link {email}`.
   **O backend responde sempre `200`** — nunca revela se o e-mail existe. UI: estado
   "enviado" genérico ("Se houver uma conta com esse e-mail, enviamos um link").
2. O cliente recebe um e-mail com um link. **⚠️ O backend gera o link como
   `{FRONTEND_BASE_URL}/portal/magic/{token}`** (token cru no **path**) —
   ver §3.4. A landing lê o token **do segmento de rota** e chama
   `POST /portal/auth/magic-link/verify {token}` → `PortalTokenResponse{access_token}`.
3. Sucesso: guarda o `access_token` na chave do portal → redireciona a `/portal/dashboard`.
4. Token expirado/usado → `422` → tela de erro ("Este link expirou ou já foi
   utilizado.") + CTA para pedir novo link (volta a `/portal/login`).

> Magic token: **UUID4 cru** só no e-mail; banco persiste só o **SHA-256**.
> **TTL 15min**, **uso único** (padrão Sprint B/D).

### 3.2 E-mail + senha
`/portal/login` (aba E-mail + senha): `POST /portal/auth/login {email, password}` →
`PortalTokenResponse`. **`401` → erro inline** "E-mail ou senha incorretos". Guarda
o token e redireciona ao dashboard.

### 3.3 Logout
Limpa **apenas** a chave do portal no storage e redireciona a `/portal/login`.
**Não** chama o handler de logout do painel do tenant. (Não há endpoint de logout —
o token portal é stateless; basta descartá-lo.)

### 3.4 ⚠️ Rota de consumo do magic link — divergência crítica a registrar

O escopo previa `/portal/magic-link` lendo **`?token`** da query. **Conferido no
backend** (`portal/auth_service.py::_magic_link_url`): o link enviado é
**`{base}/portal/magic/{raw_token}`** — **segmento de rota**, não query string, e o
caminho é **`/portal/magic/`**, não `/portal/magic-link`. Para o link do e-mail
funcionar, a rota Next precisa ser **`/portal/magic/[token]`** lendo o token via
`useParams`. **Recomendação:** adotar **`/portal/magic/[token]`** como caminho
canônico (espelha o backend). Se quiser manter `/portal/magic-link` como nome de
UI, adicionar `rewrite` no `next.config`. O protótipo Lovable é mockado e agnóstico
de path; esta nota é para o Claude Code. *(Mesma classe de problema do `/manage`
vs `/gestao` da Fase 5A.)*

### 3.5 Registro — **fora do escopo de UI** (mas o endpoint existe)
Existe `POST /portal/auth/register`, mas o escopo manda **não** expor "Criar conta"
nem "Esqueci a senha" (o magic link cobre entrada e recuperação). **Não** construir
tela de registro. `/portal/login` **não** tem links para registro/recuperação.

---

## 4. Endpoints por tela

Todos sob a tag `portal`. Salvo os 4 de auth, **todos exigem o JWT portal**
(`HTTPBearer`). `*` = obrigatório. Helper real: **`portalFetch`** (§2.2).

> **⚠️ Shapes de resposta não tipados no OpenAPI.** Vários GETs do portal
> (`dashboard`, `history`, `credits`, `subscriptions`, `payment-sources`) e o
> `PATCH profile` declaram `schema: {}` — o backend retorna **dict não tipado**.
> Os campos abaixo são a **expectativa de wiring**, **não confirmados pelo
> contrato** → marcados **⚠️**. No protótipo Lovable use o mock; no wiring real o
> Claude Code confere contra o backend rodando / o `service.py` do módulo.

### Auth (sem JWT)
| Ação | Método + Path | Body | Resposta |
|---|---|---|---|
| Magic link (enviar) | `POST /portal/auth/magic-link` | `{email*}` | `200` sempre (não revela existência) |
| Magic link (consumir) | `POST /portal/auth/magic-link/verify` | `{token*}` | `PortalTokenResponse{access_token*, token_type}` |
| Login senha | `POST /portal/auth/login` | `{email*, password*}` | `PortalTokenResponse` · `401` credencial inválida |

### Dashboard
| Ação | Método + Path | Resposta |
|---|---|---|
| Home | `GET /portal/dashboard` | **⚠️ não tipado** — esperado: próximos agendamentos + cotas ativas (multi-tenant) |

### Histórico (paginado)
| Ação | Método + Path | Params | Resposta |
|---|---|---|---|
| Operações | `GET /portal/history` | `page` (≥1, def 1), `page_size` (1–100, def 20), `company_id?` (uuid) | **⚠️ não tipado** — esperado: envelope paginado de operações com `service/professional/establishment/date/status/value` |

### Cotas
| Ação | Método + Path | Resposta |
|---|---|---|
| Cotas/créditos | `GET /portal/credits` | **⚠️ não tipado** — esperado: lista de `CustomerCredit` (serviço, estabelecimento, usos x/y, validade, status) |

### Assinaturas
| Ação | Método + Path | Body | Resposta |
|---|---|---|---|
| Listar | `GET /portal/subscriptions` | — | **⚠️ não tipado** — esperado: plano, estabelecimento, status, próxima renovação, valor |
| Pausar | `POST /portal/subscriptions/{subscription_id}/pause` | **(sem corpo)** | **⚠️ não tipado** |
| Cancelar | `POST /portal/subscriptions/{subscription_id}/cancel` | **(sem corpo)** | **⚠️ não tipado** |

> ⚠️ **Pausa/cancelamento são governados por config do tenant** (`allows_subscription_pause`
> default **False**; `allows_subscription_cancel` default **True**). Uma assinatura
> pode **não permitir** pausa → a ação pode voltar `403`/`422`. Tratar
> graciosamente (desabilitar ou mensagem inline). **Sem campo de motivo** no contrato.

### Consentimentos
| Ação | Método + Path | Body | Resposta |
|---|---|---|---|
| Listar | `GET /portal/consents` | — | `ConsentRecordResponse[]` |
| Conceder | `POST /portal/consents/grant` | `PortalConsentRequest{consent_type*, channel?, company_id?}` | `201 ConsentRecordResponse` |
| Revogar | `POST /portal/consents/revoke` | `PortalConsentRequest` | `201 ConsentRecordResponse` |

`ConsentRecordResponse`: `id*`, `identity_id*`, `company_id?`, `consent_type*(string)`,
`channel?(string|null)`, `status*(string)`, `source_channel*(string)`, `occurred_at*(date-time)`, `notes?`.

> ⚠️ **O toggle NÃO é PATCH.** O escopo dizia "PATCH no background"; os endpoints
> reais são **`POST /grant`** e **`POST /revoke`**. O switch otimista alterna entre
> os dois conforme o estado-alvo, reverte se a chamada falhar. `consent_type` ∈
> `COMMUNICATION · DATA_PROCESSING · PAYMENT_STORAGE · MARKETING`; `channel` ∈
> `WHATSAPP · EMAIL · SMS` (ou ausente = todos os canais). `company_id?` permite
> consent por estabelecimento (ou global quando ausente).

### Pagamentos (⚠️ bloqueado por Asaas)
| Ação | Método + Path | Body | Resposta |
|---|---|---|---|
| Listar | `GET /portal/payment-sources` | — | **⚠️ não tipado** (schema `PaymentSourceResponse` existe como referência: `source_id, type, provider, last4?, brand?, is_active, created_at`) |
| Adicionar | `POST /portal/payment-sources` | `PaymentSourceCreateRequest{company_id*, source_token*, mode*, last_four?, brand?}` | `201` |
| Revogar | `DELETE /portal/payment-sources/{authorization_id}` | — | `200` |

> ⚠️ **BLOQUEADO por backend (Asaas).** O adapter Asaas **não tokeniza cartão** — o
> `source_token` precisa vir **pré-tokenizado**, o que depende de conta/contrato
> Asaas pendentes. Além disso, adicionar fonte exige consent `PAYMENT_STORAGE`
> concedido (senão `422`). **Não** implementar a integração real → ver §5 P7
> (EmptyState + TODO). `mode` ∈ `ALWAYS | ONCE` (modelo de autorização).

### Perfil / Identidade
| Ação | Método + Path | Body | Resposta |
|---|---|---|---|
| Atualizar | `PATCH /portal/profile` | `PortalProfileUpdateRequest{name?, email?, phone?}` | **⚠️ não tipado** |
| Identidade | `GET /portal/identity/me` | — | `IdentityResponse{id*, phone_e164*, phone_national_normalized*, name?, email?, cpf_masked?}` |

> ⚠️ **Não existe `GET /portal/me`** (o escopo citou esse nome). A identidade vem de
> **`GET /portal/identity/me`** (`IdentityResponse`). **Não há flag explícita
> "identidade leve vs. completa"** no contrato — o banner de upgrade do dashboard
> (§5 P3) deve ser **inferido heuristicamente** (ex.: `email` ou `name` ausente em
> `IdentityResponse` ⇒ "complete seu perfil"). **Marcar ⚠️ verificar:** se o dict
> não tipado de `GET /portal/dashboard` trouxer um sinal de completude, usar; senão,
> derivar de `identity/me`. **CPF não entra no MVP** (vem `cpf_masked`, mas não há
> tela para editá-lo).

---

## 5. Especificação das 9 telas

Estados mínimos por tela: **loading (`Skeleton`) · vazio (`EmptyState`) · erro
(`ErrorState`) · dados**. Mobile-first; nav lateral em `md+`, bottom nav no mobile.
**Status em inglês → label PT** reusando os mapas da Fase 5A
(`APPOINTMENT_STATUS_LABELS`, `CUSTOMER_CREDIT_STATUS_LABELS` em `lib/constants.ts`);
para assinatura, **estender** com `SUBSCRIPTION_STATUS_LABELS` se ausente (aditivo).

### Bloco A — Autenticação (FORA da área autenticada)

#### P1 — `/portal/login`
- **Onde:** fora do grupo autenticado (sem nav, sem guard). Card centralizado, `max-w-sm`, sob o shell externo do portal.
- **Layout:** wordmark/logo no topo; **toggle de modo** (Tabs ou dois botões segmentados) — **Magic link (padrão)** · **E-mail + senha**.
  - *Magic link:* `Input` e-mail + `Button` "Enviar link". Estados **idle → enviando (spinner) → enviado** (mensagem genérica "Se houver uma conta…") **→ erro** (falha de rede, inline).
  - *E-mail + senha:* `Input` e-mail + `Input` senha + `Button` "Entrar". **`401` → erro inline** "E-mail ou senha incorretos".
- **shadcn:** `Card`, `Tabs`, `Input`, `Label`, `Button`, `Loader2`.
- **Sem** "Criar conta", **sem** "Esqueci a senha" (§3.5).

#### P2 — `/portal/magic/[token]` (canônica; ver §3.4)
- **Onde:** fora da área autenticada. Card centralizado.
- **Comportamento:** lê o token do **segmento de rota** no mount → chama o consume automaticamente (uma vez).
- **Estados:** **verificando** (spinner + "Validando seu acesso…") → **sucesso** (redireciona a `/portal/dashboard`) → **erro** (ícone + "Este link expirou ou já foi utilizado." + CTA "Pedir novo link" → `/portal/login`).
- **shadcn:** `Card`, `Loader2`, ícone Lucide (`LinkOff`/`Frown`), `Button`.

### Bloco B — Área autenticada (guard: `401 → /portal/login`)

#### P3 — `/portal/dashboard`
- **Onde:** dentro da área autenticada.
- **Layout:** duas seções empilhadas (mobile) / lado a lado (`lg`):
  - **"Próximos agendamentos"** — lista compacta (**máx 5**): serviço · profissional · **estabelecimento (destaque)** · data/hora (`formatDateTime` com tz) · `Badge` de status PT. Link "Ver histórico" → `/portal/historico`.
  - **"Cotas ativas"** — lista compacta (**máx 3**): serviço · estabelecimento · **cotas restantes (x de y)** + **barra de progresso** · validade. Link "Ver todas" → `/portal/cotas`.
  - **Banner de upgrade de identidade leve→completa** (opcional, dispensável) — ver §4 (⚠️ inferir de `identity/me`; ocultar se a completude não for determinável).
- **Estados:** `Skeleton` em cada seção; **vazio** → `EmptyState` por seção ("Você ainda não tem agendamentos."/"Nenhuma cota ativa."); **erro** → `ErrorState` com retry.
- **shadcn:** `Card`, `Badge`, barra de progresso (**div**, não há `Progress` — ver §6), `Skeleton`.

#### P4 — `/portal/historico`
- **Onde:** dentro da área autenticada.
- **Layout:** **tabela** (cards empilhados no mobile): serviço · profissional · **estabelecimento (destaque)** · data · `Badge` status · valor (`formatBRL`). **Filtros** por **status** (`Select`) e **estabelecimento** (`Select`, alimenta `company_id`). **Paginação** (`page`/`page_size`).
- **Estados:** `Skeleton` de linhas; **vazio** (com/sem filtro) → `EmptyState`; **erro** → `ErrorState`.
- **shadcn:** `Table`, `Select`, `Badge`, `Button` (paginação), `Skeleton`.

#### P5 — `/portal/cotas`
- **Onde:** dentro da área autenticada.
- **Layout:** **cards por cota**: serviço · estabelecimento · **barra de progresso (x/y usos)** · validade (**texto vermelho se expirada**) · `Badge` de status (`CUSTOMER_CREDIT_STATUS_LABELS`). Card **expansível** → histórico de consumo inline (**lazy**: só busca/expande ao abrir).
- **Estados:** `Skeleton` de cards; **vazio** → `EmptyState` "Você não tem cotas."; **erro** → `ErrorState`.
- **shadcn:** `Card`, `Badge`, barra (div), `Button`/collapsible para expandir, `Skeleton`.

#### P6 — `/portal/assinaturas`
- **Onde:** dentro da área autenticada.
- **Layout:** lista de assinaturas: plano · estabelecimento · `Badge` status · próxima renovação · valor. Ações **Pausar** / **Cancelar** → **`Dialog`** de confirmação (**não** `AlertDialog` — não existe; ver §6). Resultado **inline** (a tela reflete o novo status), não toast.
- **Regra:** desabilitar/ocultar **Pausar** quando o tenant não permite (§4); cancelamento idem. Falha `403/422` → mensagem inline.
- **Estados:** `Skeleton`; **vazio** → `EmptyState` (⚠️ **dependência de Asaas ativo** — estado vazio gracioso "Você não tem assinaturas." sem erro); **erro** → `ErrorState`.
- **shadcn:** `Card`, `Badge`, `Dialog`, `Button`, `Loader2`, `Skeleton`.

#### P7 — `/portal/pagamentos`  ⚠️ BLOQUEADO por Asaas
- **Onde:** dentro da área autenticada.
- **Layout real:** **`EmptyState` "Em breve"** com **TODO explícito** (tokenização de cartão depende de conta/contrato Asaas — registrado no CLAUDE.md).
- **Protótipo Lovable:** prototipar com **mock de 1–2 cartões** (bandeira + `•••• last4` + selo padrão) para validar o layout: lista de fontes + ação "Remover"; ao "Adicionar", abrir um formulário **com o modelo de autorização** em **radio**: **"Apenas esta vez" · "Permitir sempre" · "Cancelar"** (mapeia `mode` `ONCE`/`ALWAYS`). **Não há `RadioGroup`** no projeto → usar `<input type="radio">` estilizado (ver §6).
- **Estados:** mock de dados (Lovable) · EmptyState "Em breve" (wiring real).
- **shadcn:** `Card`, `Button`, `Dialog` (form de adicionar), inputs radio nativos, `EmptyState`.

#### P8 — `/portal/consentimentos`
- **Onde:** dentro da área autenticada.
- **Layout:** lista de **toggles (`Switch`) agrupados por `consent_type`**: `COMMUNICATION · DATA_PROCESSING · PAYMENT_STORAGE · MARKETING` (rótulos PT). **Sub-itens por canal** (`WHATSAPP/EMAIL/SMS`) quando o registro tiver `channel`. **Estado otimista:** alterna o `Switch` na hora → `POST /grant` ou `POST /revoke` no background → **reverte em erro**. Ao **revogar `DATA_PROCESSING`**: **aviso em card** (não modal blocante) explicando a consequência.
- **Estados:** `Skeleton` de toggles; **vazio** improvável (há defaults) → `EmptyState`; **erro** de carga → `ErrorState`. Erro de toggle → reverte + mensagem discreta.
- **shadcn:** `Switch`, `Label`, `Card`, `Skeleton`. (Toggle = POST grant/revoke — §4.)

#### P9 — `/portal/perfil`
- **Onde:** dentro da área autenticada.
- **Layout:** formulário: **nome** · **e-mail** · **telefone** (máscara pt-BR). Botão "Salvar" → `PATCH /portal/profile`. Estados **inline**: **idle → salvando → salvo / erro** (mensagem sob o botão; **não** toast).
- **Regra:** **CPF não aparece** neste MVP (mesmo vindo `cpf_masked`). Trocar telefone pode reagir do backend (`409` se já pertence a outra identidade) → mensagem inline.
- **Estados:** `Skeleton` ao carregar (`identity/me`); **erro** de carga → `ErrorState`.
- **shadcn:** `Card`, `Input`, `Label`, `Button`, `Loader2`.

---

## 6. Padrões de UX da Fase 5B

- **Auth guard redireciona em `401`** (oposto das públicas): qualquer chamada
  autenticada que volte `401` → `portalFetch` limpa o token do portal e manda para
  `/portal/login`. (Nas públicas, `401`/erro **nunca** redireciona — aqui **sim**.)
- **`portalFetch` separado** de `apiFetch` e `publicFetch` (§2.2). Nunca anexar o
  JWT do tenant ao Portal nem vice-versa; chaves de storage distintas.
- **Enums inglês → labels PT** com os **mesmos mapas da Fase 5A** (`lib/constants.ts`).
  Reusar `APPOINTMENT_STATUS_LABELS` (histórico) e `CUSTOMER_CREDIT_STATUS_LABELS`
  (cotas); **adicionar** `SUBSCRIPTION_STATUS_LABELS` se não existir (aditivo).
- **`Dialog` (não `AlertDialog`)** para ações destrutivas (pausar/cancelar
  assinatura, remover cartão, revogar consent crítico): o projeto **não tem
  `AlertDialog`** — usar `Dialog` + botões, como na Fase 5A (`/manage`).
- **Resultado inline (não toast)** para ações de **consequência permanente**
  (cancelar assinatura). Toast só para feedback efêmero leve, se necessário.
- **Barra de progresso de cotas com cor** (`>50%` normal/primária · `<25%` âmbar ·
  `0` cinza/`muted`). **Não há componente `Progress`** → barra é um `div`
  (trilho `bg-muted` + preenchimento por `width: %`), tokens semânticos.
- **`RadioGroup` não existe** → o seletor de autorização de pagamento (P7) usa
  `<input type="radio">` estilizado (mesma estratégia que a Fase 5A adotou para a
  ausência de `RadioGroup`).
- **Multi-tenant visível:** todo item (agendamento/cota/assinatura/operação)
  **destaca o estabelecimento**; histórico e dashboard agrupam/filtram por tenant.
- **Responsivo:** **nav lateral em `md+`, bottom nav no mobile**; conteúdo
  `max-w-3xl` (telas de lista) / `max-w-sm` (login/perfil). Toque ≥44px.
- **Datas:** `formatDateTime(iso, timeZone?)` de `lib/utils.ts`; valores `formatBRL`.
- **Magic link sempre `200`** (não revela existência de e-mail) — a UI nunca
  diferencia "e-mail não existe" de "enviado".

### Componentes a reaproveitar
`Card`, `Tabs`, `Input`, `Label`, `Button`, `Badge`, `Switch`, `Select`, `Table`,
`Dialog`, `Skeleton`, `Separator`, `EmptyState`, `ErrorState`, `PageHeader`,
`avatar-initials`, ícones **Lucide** (16px/`strokeWidth 1.5`), wordmark `PALADINO`
(`font-display tracking-[0.3em] text-primary`). **A criar:** `portalFetch`
(`lib/portal-api.ts`), nav do portal (lateral + bottom), barra de progresso de cota,
e `SUBSCRIPTION_STATUS_LABELS` (se ausente).

### Referência visual
- **barberflow-system** **não possui** área de conta/portal do cliente (verificado
  na Fase 5A — só `/b/$slug` e NPS público). O Portal é desenhado **do zero**,
  herdando o **vocabulário visual do painel** (tokens, `font-display`, cards) e a
  sobriedade mobile-first das superfícies públicas. **Sem screenshots aprovadas**
  para esta fase.

---

## 7. O que NÃO entra na Fase 5B

- **Painel Owner** (`(owner)/*`, `PLATFORM_OWNER` — tenants/saúde/impersonation/
  flags/audit/settings) → **Fase 5C**.
- **Tela de registro / "Esqueci a senha"** — endpoint `register` existe, mas o
  magic link cobre entrada e recuperação; **não** construir (§3.5).
- **OAuth Google/Apple** — fora do Estágio 0.
- **Tokenização de cartão** (P7) — bloqueada por Asaas; só EmptyState + mock visual.
- **CPF no perfil** — `cpf_masked` vem na identity, mas não há edição no MVP.
- **Checkout / novo agendamento pelo Portal** — o portal **gerencia** a relação
  existente; agendar continua no link público `/book/[slug]` (Fase 5A).
- **Reaproveitar** `apiFetch`/`AuthContext`/`Sidebar`/`Header` do painel do tenant —
  o Portal é shell isolado.
- **Inventar** campos em respostas não tipadas como se confirmados, `GET /portal/me`,
  `PATCH` de consent, ou `/portal/magic-link?token=` — nada disso existe (§3.4/§4).

---

*Fonte de verdade de comportamento: `visao-estagio-0.md` + `openapi.json`
(head `e0s25f_product_extras`), tag `portal`. Contratos e divergências conferidos em
`app/modules/portal/` (`auth_service.py`, `service.py`, `router.py`, `schemas.py`) e
`app/modules/identity/`. O protótipo `barberflow-system` **não cobre** o Portal do
Cliente — é referência visual apenas. Onde divergir, vence este documento. Documento
de planejamento — nenhuma regra de negócio vive no frontend.*
