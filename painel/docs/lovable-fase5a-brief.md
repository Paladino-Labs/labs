# PALADINO — BRIEF DA FASE 5A (LOVABLE)

**Objetivo:** especificar as **superfícies públicas** — páginas acessadas pelo
**cliente final, sem login no painel** — da Fase 5A: (P1) a aba **Produtos** no
link público de agendamento (extensão do `/book/[slug]` existente); (P2) a tela
nova de **gestão de agendamento por token** (`/manage/[token]` — ver §3.2 sobre o
nome da rota); e (P3) a **resposta pública de NPS** (`/nps/respond/[survey_id]` —
**já prototipada na Fase 4**, formalizada aqui). Derivado de
`painel/docs/inventario-funcional.md` (§5 Públicas · §7 fluxo 8 · §8 detalhe) e de
`agendamento_engine/openapi.json` (head `e0s25f_product_extras`). Shapes, FSMs e o
contrato de segurança do token **conferidos diretamente no backend** (módulos
`public/manage_service.py`, `appointments/manage_tokens.py`, `nps/`,
`booking-public`) — não inferidos.

> **Continuação das Fases 0–4.** O painel autenticado e seus componentes já
> existem. Esta fase **não toca** no shell do painel: as três superfícies rodam
> **fora dele** — sem sidebar, sem header do painel, sem guard de auth. **Dados
> mockados** no protótipo Lovable; a integração real é feita depois pelo Claude
> Code.

> **Escopo rígido:** apenas as 3 superfícies públicas abaixo. **NÃO** entram o
> Portal do Cliente (`(portal)/*`, login/dashboard/histórico/cotas) nem o Painel
> Owner (`(owner)/*`, `PLATFORM_OWNER`) — são as Fases 5B e 5C.

> **⚠️ Já implementado — verificar/realinhar, não refazer do zero:**
> - **P3 — NPS público** já existe em `app/(public)/nps/respond/[survey_id]/page.tsx`
>   (entregue na Fase 4): seletor 0–10 com faixas detrator/neutro/promotor,
>   `Textarea` de comentário, estados idle→enviando→sucesso|erro, chamada via
>   `publicFetch` **sem JWT**. A Fase 5A **re-hospeda essa tela sob o shell público
>   compartilhado** (§2) e corrige a detecção de erro 422 (ver §3.3, nota do
>   `publicFetch`). **Não reescrever o formulário de nota.**
> - **`/book/[slug]`** já existe completo (`app/book/[slug]/page.tsx` + `BookingFlow.tsx`):
>   vitrine 2 colunas, abas **Serviços · Profissionais · Avaliações**, FSM de
>   agendamento, `publicFetch`. A Fase 5A **apenas acrescenta a aba Produtos** —
>   não mexe no resto da vitrine nem no `BookingFlow`.

---

## 1. Contexto

**Superfícies públicas** são páginas que o **cliente final** abre **sem login no
painel**, normalmente a partir de um link recebido pelo **WhatsApp**. Cada uma tem
**shell próprio**: apenas logo/marca do estabelecimento e um rodapé discreto — **sem
sidebar, sem header do painel, sem qualquer redirecionamento para a área
autenticada**. O visual é **minimalista e mobile-first** (a maioria dos acessos
vem do celular, dentro do WhatsApp). As chamadas são **sempre sem JWT**
(`publicFetch`); nenhum token de painel pode vazar para essas páginas. O isolamento
de tenant é **implícito** no identificador da URL (slug, token de gestão ou
`survey_id`) — o backend resolve o `company_id` a partir dele.

---

## 2. Shell público — o que as 3 superfícies compartilham

Um **layout público compartilhado** (grupo de rota `(public)`), **distinto do
`(dashboard)/layout.tsx`**:

- **Header mínimo:** logo do estabelecimento **quando a superfície fornece esse
  dado** (ver tabela abaixo); caso contrário, **fallback para o wordmark
  `PALADINO`** (`font-display tracking-[0.3em] text-primary`). Sem navegação, sem
  avatar, sem toggle de tema.
- **Sem sidebar.** Fundo `bg-background`. Conteúdo centralizado, largura máxima
  estreita (`max-w-md`/`max-w-xl` nas telas de ação; a vitrine `/book` mantém seu
  próprio grid largo).
- **Rodapé discreto:** `© PALADINO` (`text-xs text-muted-foreground`).
- **Paleta:** segue os **tokens do sistema** (`.book-page` / `bg-background`,
  `bg-card`, `text-primary`…). Ver a **ressalva de branding** abaixo — não há, hoje,
  caminho público para as cores por tenant nas telas de token/NPS.

> **Estado atual:** **não existe `app/(public)/layout.tsx`.** A tela de NPS já
> desenha seu próprio wrapper `.book-page`. A Fase 5A **cria o layout público
> compartilhado** e passa NPS + Gestão a usá-lo. O `/book/[slug]` vive hoje **fora**
> do grupo `(public)` (em `app/book/[slug]`) e já tem chrome próprio — **mantê-lo
> onde está**; o shell compartilhado vale para `/manage` (P2) e `/nps/respond` (P3).

### ⚠️ Branding por tenant nas superfícies públicas — ressalva importante

O enunciado supõe "branding via `GET /tenant/branding` (com `company_id` ou slug)".
**Conferido no backend:** o endpoint público é `GET /tenant/branding?company_id={uuid}`
— **exige `company_id` (query, obrigatória); não há variante por slug.** As
superfícies públicas **não carregam `company_id`** diretamente. Consequência real do
que cada superfície consegue exibir no header:

| Superfície | Identificador na URL | Logo/nome do tenant disponível? | Fonte |
|---|---|---|---|
| `/book/[slug]` (P1) | `slug` | **Sim** — `logo_url` + `company_name` | `GET /booking/{slug}/profile` (já usado) |
| `/manage/[token]` (P2) | token opaco | **Não** — `ManageDetailsResponse` não traz dados do tenant | — |
| `/nps/respond/[survey_id]` (P3) | `survey_id` | **Não** — não há GET público da survey | — |

> **Decisão para a Fase 5A:** o header público usa **logo + nome do tenant apenas
> onde a superfície já fornece esses dados** (hoje, só `/book`); em `/manage` e
> `/nps/respond` o header cai no **wordmark `PALADINO`**. **Cores/fonte por tenant
> nas telas públicas continuam sendo a paleta do sistema** (`.book-page`) — não há
> endpoint público que entregue `primary_color`/`font_family` por slug/token.
> Tratar "branding completo por tenant nas públicas" como **dívida de backend**
> (precisaria expor `company_id`/branding em `ManageDetailsResponse` e numa rota de
> survey), **não** como entrega desta fase. **Não inventar** chamada a
> `/tenant/branding` sem `company_id`.

---

## 3. Endpoints por superfície

Todos **públicos (sem `security`)**. Métodos, campos e enums **confirmados contra
`openapi.json` + serviços do backend**. `*` = obrigatório. Helper de chamada:
**`publicFetch<T>(path, { method, body })`** de `lib/api.ts` (sem JWT). **Não existe
`api.publicPost`** — o enunciado cita esse nome, mas o helper real é `publicFetch`.

### 3.1 — P1 · `/book/[slug]` — aba Produtos (extensão)

A vitrine atual é servida por (já implementado, **não alterar**):

| Dado | Endpoint | Observação |
|---|---|---|
| Perfil/marca/horários | `GET /booking/{slug}/profile` | `logo_url`, `company_name`, `tagline`, `business_hours`, `online_booking_enabled`, redes, endereço |
| Serviços | `GET /booking/{slug}/services` | `id, name, price, duration_minutes, description?` |
| Profissionais | `GET /booking/{slug}/professionals?service_id=` | filtra "Qualquer disponível" |
| Datas/slots/sessão | `GET /booking/{slug}/dates|slots|session/{token}`, `POST /booking/{slug}/start|update|confirm` | FSM do `BookingFlow` |

**⚠️ Não existe endpoint público de produtos.** Conferido: `GET /products/` é
**autenticado (OWNER/ADMIN)**; **não há** `GET /booking/{slug}/products` nem
`GET /public/{slug}/products`. Portanto:

- **No protótipo Lovable:** a aba **Produtos** é construída com **dados mockados**
  (lista de produtos com nome, preço, imagem, descrição curta, "esgotado"). É o
  comportamento que se quer validar visualmente.
- **No wiring real (Claude Code, depois):** **BLOQUEADO por backend** — depende de
  um novo endpoint público (sugestão: `GET /booking/{slug}/products` retornando
  `id, name, price, image_url?, description?, available(bool)`). Até existir, a aba
  renderiza **`EmptyState` "Em breve"**. Documentar como **dependência de backend**,
  não implementar chamada inexistente.
- A aba é **vitrine, não checkout**: o cliente **vê** os produtos; a compra pública
  de produto **não** faz parte do Estágio 0 do link (sem carrinho/pagamento de
  produto no `/book`). CTA por item, no máximo, "Falar no WhatsApp" reaproveitando
  `profile.whatsapp` (mesmo padrão do card de contato).

### 3.2 — P2 · `/manage/[token]` — gestão de agendamento por token

> **⚠️ Nome da rota — divergência crítica a registrar.** O inventário (§3/§5)
> chama esta rota de `/gestao/[token]`. Mas o **link que o backend efetivamente
> envia ao cliente** é `/manage/{token}` (`build_manage_url` →
> `{FRONTEND_BASE_URL}/manage/{raw_token}`, em `appointments/manage_tokens.py`). Para
> o link do WhatsApp funcionar, **a rota Next.js precisa ser `/manage/[token]`** (ou
> manter `/gestao/[token]` e adicionar um `rewrite` `/manage/:token → /gestao/:token`
> + apontar `FRONTEND_BASE_URL`). **Recomendação:** adotar **`/manage/[token]`** como
> caminho canônico (espelha o backend) e, se quiser, manter `/gestao` como alias.
> O protótipo Lovable é mockado e agnóstico de path; esta nota é para o Claude Code.

| Ação | Método + Path | Body | Resposta |
|---|---|---|---|
| Detalhe | `GET /manage/{token}` | — | `ManageDetailsResponse` |
| Cancelar | `POST /manage/{token}/cancel` | **(sem corpo)** | `ManageCancelResponse` |
| Remarcar | `POST /manage/{token}/reschedule` | `ManageRescheduleRequest{new_datetime*}` | `ManageRescheduleResponse` |

**`ManageDetailsResponse`** (PII-mínimo — **não** é o `AppointmentResponse`
completo):
`service_name*(string|null)`, `professional_name*(string|null)`,
`scheduled_datetime*(date-time)`, `status*(string)`, `can_cancel*(bool)`,
`can_reschedule*(bool)`.
> ⚠️ O enunciado pede "campos exatos de `AppointmentResponse`" — **corrigir**: o
> endpoint de gestão retorna **deliberadamente** só esses 6 campos (sem nome/telefone
> do cliente, sem valores). `can_cancel`/`can_reschedule` são `true` **apenas quando
> `status == "SCHEDULED"`** — usá-los para habilitar/desabilitar os botões. Exibir:
> serviço, profissional, data/hora (`formatDateTime`), e um badge de status.
> **`status` é enum inglês** (`SCHEDULED`, `CANCELLED`, …) — a UI **mapeia para
> label em português** no badge (ex.: `SCHEDULED → "Agendado"`); não exibir o enum
> cru. (No mock do protótipo a string já vem traduzida — o wiring real faz o mapa.)

**`ManageCancelResponse`:** `status*("CANCELLED")`, `deposit_retained*(bool)`,
`message*(string)`.
> ⚠️ O **POST cancel não recebe corpo** (sem campo de motivo no contrato público).
> O backend **nunca bloqueia** o cancelamento pela janela — a janela decide
> **consequência**: se houver sinal pago e o cancelamento for fora do prazo,
> `deposit_retained=true` e a `message` já vem pronta explicando a retenção do
> sinal. **Exibir a `message` da resposta** (não montar texto próprio); destacar
> visualmente quando `deposit_retained`.

**`ManageRescheduleRequest`:** `new_datetime*(date-time)`.
**`ManageRescheduleResponse`:** `status*`, `scheduled_datetime*(date-time)`, `message*`.
> ⚠️ **Confirmado: o reschedule recebe `new_datetime` (um único date-time), NÃO uma
> lista de slots.** O fluxo de gestão por token **não expõe** um seletor de
> disponibilidade (não há slug/`service_id` no contexto do token; os endpoints
> `/booking/{slug}/slots` exigem ambos). Portanto a tela oferece um **seletor de
> data + hora** (`DateTimePicker`) e envia `new_datetime`; **o backend valida a
> disponibilidade** e responde **`422`** se o horário estiver indisponível
> (mensagem "horário indisponível"). Em sucesso, **o token antigo deixa de
> funcionar** (um novo é emitido) e o cliente recebe **nova confirmação com o link
> atualizado** — a `message` da resposta já diz isso.

**Contrato de segurança do token (conferido em `manage_service.py` /
`manage_tokens.py`):**
- **Token opaco = UUID4**, enviado apenas no link; no banco persiste **somente o
  SHA-256** (`appointments.manage_token_hash`). Resposta à pergunta do enunciado:
  **sim, é opaco e hasheado (SHA-256)** — a URL carrega o token cru.
- **Expira em `start_at`** (após o início do atendimento o link morre) e é
  **invalidado ao atingir estado terminal** (COMPLETED/CANCELLED/NO_SHOW).
- **Token inválido / expirado / de agendamento terminal → `404` genérico**
  ("Link inválido ou expirado") — nunca 401/403 (não revela existência). A tela
  trata 404 como **página de erro clara** (ver §4/§5).
- **Rate limit:** `GET` 10/min, `cancel` 5/min, `reschedule` 5/min por IP → no
  `429`, mensagem "Muitas tentativas, tente novamente em instantes".

> **barberflow:** **não possui** rota de gestão/manage (verificado em
> `/tmp/barberflow/src/routes/` — não há `gestao*`/`manage*`). P2 é desenhada do
> zero, herdando o vocabulário visual do `/book` (`.book-page`, card centralizado).

### 3.3 — P3 · `/nps/respond/[survey_id]` — resposta pública de NPS (retroativo da Fase 4)

| Ação | Método + Path | Body | Resposta |
|---|---|---|---|
| Responder | `POST /nps/respond/{survey_id}` | `PublicNpsRespondRequest{score*, comment?}` | `NpsResponseOut` |

**`PublicNpsRespondRequest`:** `score*(int 0–10)`, `comment?(string, máx 2000)`.
> ⚠️ **`survey_id` na URL É o token** — não há outro segredo. **Não existe GET
> público** da survey: a tela é **cega** (não pré-carrega nome do cliente nem do
> tenant). Só surveys no estado **`SENT`** aceitam resposta; qualquer outro estado
> (já respondida / expirada) → **`422`**. Rate limit **3/min**.

**Estado atual & confirmação de retroatividade:** **já implementada na Fase 4**
(`app/(public)/nps/respond/[survey_id]/page.tsx`) e prototipada no barberflow
(`nps.respond.$surveyId.tsx`, mockado). A Fase 5A apenas: (a) re-hospeda sob o
**shell público compartilhado** do §2; (b) **corrige a detecção do 422**.

> ⚠️ **Bug latente a corrigir (wiring):** a tela atual faz
> `(err as {status?}).status === 422`, mas **`publicFetch` lança um `Error` simples
> sem campo `status`** (só a mensagem do `detail`). Hoje o ramo "indisponível"
> nunca dispara — cai sempre no erro genérico. **Fix:** ou `publicFetch` passa a
> expor o `status` HTTP no erro, ou a tela passa a inferir a indisponibilidade pela
> mensagem do `detail`. Documentar; o protótipo Lovable trata os estados por
> **comportamento** (mock), não pelo código HTTP.

---

## 4. Especificação das 3 superfícies

Estados mínimos (onde fizer sentido): **loading (`Skeleton`/"Carregando…") ·
erro (página clara, sem retry ao painel) · sucesso · dados**. **Mobile-first** em
todas.

### P1 — aba **Produtos** em `/book/[slug]`
- **Onde:** dentro do `<Tabs>` existente da vitrine, **uma nova `TabsTrigger`
  "Produtos"** **após "Profissionais"** — ordem canônica de `visao-estagio-0.md`
  (Serviços · Profissionais · **Produtos** · Pacotes · Assinaturas · Avaliações).
  Não alterar as abas existentes.
- **Conteúdo (`TabsContent value="products"`):** grid de **cards de produto** no
  mesmo molde dos cards de serviço — ícone/imagem, nome, descrição curta
  (`line-clamp`), preço (`formatBRL`), e um selo "Esgotado" quando indisponível.
  **Sem botão de comprar/agendar** (vitrine, não checkout); CTA opcional "Falar no
  WhatsApp" reaproveitando `profile.whatsapp`.
- **Estados:** **dados** (mock no protótipo) · **vazio** → `EmptyState` "Nenhum
  produto disponível." / "Em breve" (quando o endpoint real ainda não existir).
- **Responsivo:** 1 coluna no mobile, 2–3 colunas a partir de `sm`/`lg`.

### P2 — `/manage/[token]` — gestão sem login
Página **standalone** sob o shell público. Um único `Card` centralizado.

- **Loading:** "Carregando…" enquanto resolve o `GET /manage/{token}`.
- **Erro de token (404/expirado/terminal):** **página de erro clara** —
  ícone neutro (`Frown`/`LinkOff`), título "Link inválido ou expirado", texto
  curto ("Este link de gestão não está mais disponível. Fale com o
  estabelecimento para reagendar."). **Sem** botão para o painel, **sem** login.
- **Dados (status `SCHEDULED`):** card com **serviço**, **profissional**,
  **data/hora** (`formatDateTime`), **badge de status**, e duas ações:
  - **Cancelar** → `Dialog`/`AlertDialog`-substituto (o projeto usa `Dialog` +
    botões; **não há AlertDialog**) de confirmação ("Tem certeza que deseja
    cancelar?") → `POST /cancel` → **tela de resultado** exibindo a `message` da
    resposta; se `deposit_retained`, destacar o aviso de retenção do sinal.
    Desabilitar se `can_cancel === false`.
  - **Remarcar** → abre seletor **data + hora** (`DateTimePicker`) → botão
    "Confirmar remarcação" → `POST /reschedule {new_datetime}`. **Sucesso:** tela
    com a `message` (novo horário + aviso de que um novo link foi enviado).
    **`422`:** inline "Esse horário não está disponível. Escolha outro." (mantém o
    seletor aberto). Desabilitar se `can_reschedule === false`.
- **Estados terminais após ação:** depois de cancelar/remarcar com sucesso, **o
  token atual não vale mais** — não voltar ao formulário; mostrar a tela de
  resultado final.
- **`429`:** banner "Muitas tentativas, tente novamente em instantes."

### P3 — `/nps/respond/[survey_id]` — resposta pública (já existe; re-hospedar)
- **Layout:** card centralizado sob o shell público; título "Como foi sua
  experiência?", **seletor 0–10** (11 botões/segmentos, faixas
  **detrator 0–6 (vermelho) · neutro 7–8 (âmbar) · promotor 9–10 (emerald)** —
  apenas display), `Textarea` "Comentário (opcional)" (máx 2000), botão "Enviar".
- **Estados:** **idle** (form) · **enviando** (botão desabilitado + spinner) ·
  **sucesso** (agradecimento "Obrigado pelo seu feedback!", **sem** voltar ao form)
  · **erro** (`422`/indisponível → "Esta pesquisa não está mais disponível.";
  outros → "Não foi possível enviar, tente novamente."). **Não** pré-carrega nada
  (sem GET).

---

## 5. Padrões de UX específicos da Fase 5A

- **Mobile-first (obrigatório):** o cliente abre pelo WhatsApp, no celular. Largura
  base estreita, toque confortável (botões altos, alvo ≥ 44px), zero scroll
  horizontal, o seletor de nota e o `DateTimePicker` funcionam bem com o dedo.
  Desktop é progressivo (centraliza, não alarga demais).
- **Shell público ≠ shell do painel:** sem sidebar, sem header do painel, **sem
  redirecionamento à área autenticada** em nenhuma hipótese (nem em erro). Nada de
  link "voltar ao painel" / "fazer login".
- **Token/sessão inválido → página de erro clara**, nunca um 401/redirect. P2:
  404 genérico (não revelar se o agendamento existe). P3: 422 = "indisponível".
- **Rate limiting visível:** P3 já-respondida → "Esta pesquisa não está mais
  disponível"; P2 `429` → "muitas tentativas". Não martelar o endpoint (sem
  auto-retry agressivo).
- **Sem login, sem cadastro, sem JWT:** todas as chamadas via **`publicFetch`**
  (sem header de autorização). Nunca anexar token de painel a essas páginas.
- **Cores/marca:** seguir os **tokens do sistema** (`.book-page`/`bg-background`);
  logo+nome do tenant só onde a superfície fornece (P1). Ver ressalva de branding
  no §2 — **não** chamar `/tenant/branding` sem `company_id`.
- **Toast/feedback:** em P2/P3, preferir **tela de resultado inline** (a página é
  de uso único pelo cliente) a `toast` efêmero; usar a `message` que o backend
  devolve quando houver.
- **Datas:** `formatDateTime()` (timezone do tenant, fallback `America/Sao_Paulo`).
  No `new_datetime` enviado ao reschedule, mandar **ISO date-time**.
- **Faixa NPS (display):** 0–6 vermelho · 7–8 âmbar · 9–10 emerald — só cor, não
  regra de negócio.

### Componentes a reaproveitar
- `DateTimePicker` (já existe, usado nas Fases 2–4) → seletor de remarcação (P2).
- `publicFetch` (`lib/api.ts`) → todas as chamadas.
- `EmptyState`, `Button`, `Textarea`, `Badge`, `Card`, `Dialog`, `Tabs`,
  `Skeleton`, ícones **Lucide** 16px/`strokeWidth 1.5`.
- O wordmark `PALADINO` (`font-display tracking-[0.3em] text-primary`) como
  fallback do header público.

### Referências visuais — estado real (reportar ao Lovable)
- **barberflow** (`/tmp/barberflow/src/routes/`, atualizado nesta sessão):
  - **Presente:** família `/b/$slug` (vitrine + agendar + confirmação) e
    `nps.respond.$surveyId` (NPS público, mockado — abas da vitrine são
    **Serviços · Profissionais · Avaliações**, **sem aba Produtos**).
  - **Ausente:** **nenhuma** rota de gestão/manage por token; **nenhuma** aba
    Produtos. P1 (aba) e P2 (tela) são desenhadas do zero, herdando o vocabulário
    do `/book` e do NPS público.
- **Sem screenshots aprovadas** para esta fase. O vocabulário visual consolidado
  é o do link público (`.book-page`).

---

## 6. O que NÃO entra na Fase 5A

- **Portal do Cliente** (`(portal)/*` — login/registro/magic-link/dashboard/
  histórico/cotas/assinaturas/consentimentos/pagamentos/perfil) → **Fase 5B**.
- **Painel Owner** (`(owner)/*`, `PLATFORM_OWNER` — tenants/saúde/impersonation/
  flags/audit/settings) → **Fase 5C**.
- **Checkout público de produto** (carrinho/pagamento de produto no `/book`) — fora
  do Estágio 0; a aba Produtos é **vitrine**.
- **Reescrever** o `BookingFlow` ou as abas existentes do `/book`, e **reescrever** o
  formulário de nota do NPS (já existe) — só re-hospedar/estender.
- **Branding completo por tenant nas públicas** (cores/fonte por slug/token) — não
  há endpoint público; é dívida de backend (§2).
- **Endpoint público de produtos** — não existe; a aba é mockada até o backend
  expor `GET /booking/{slug}/products` (ou equivalente).
- **Abas Pacotes e Assinaturas** no `/book/[slug]` — a ordem canônica da visão
  prevê 6 abas (Serviços · Profissionais · Produtos · **Pacotes · Assinaturas** ·
  Avaliações), mas **só Produtos entra nesta fase**. Pacotes e Assinaturas ficam
  **fora**: sem endpoint público e sem spec de exibição pública desses planos —
  deferidas para quando houver backend (mesma dívida da aba Produtos).
- **Inventar** `accent_color`/`font_display`/`api.publicPost`/`/tenant/branding?slug=`
  — nada disso existe.

---

*Fonte de verdade de comportamento: `visao-estagio-0.md` + `openapi.json`
(head `e0s25f_product_extras`). Contrato do token e shapes conferidos em
`app/modules/public/manage_service.py`, `app/modules/appointments/manage_tokens.py`,
`app/modules/nps/`, tag `booking-public`. O protótipo `barberflow-system` é
referência visual apenas e **não cobre** gestão por token nem aba de produtos. Onde
divergir, vence este documento. Documento de planejamento — nenhuma regra de
negócio vive no frontend.*
</content>
</invoke>
