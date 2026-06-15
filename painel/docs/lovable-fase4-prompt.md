# PALADINO — PROMPT DA FASE 4 (LOVABLE)

> Cole este prompt no Lovable. Ele especifica **10 telas/superfícies** de **Relacionamento** (NPS) e **Administração** (Comunicação, WhatsApp, Usuários, Módulos, Branding, Auditoria). Tudo com **dados mockados** — a integração real vem depois pelo Claude Code. **Vença sempre este documento** onde houver conflito com o protótipo de referência.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 0. CONTEXTO E O QUE JÁ EXISTE (NÃO REIMPLEMENTAR)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Paladino é um SaaS multi-tenant (barbearias no piloto). Stack: **Next.js 15 (App Router) · TypeScript · shadcn/ui · TailwindCSS · Lucide**. Display **Cormorant Garamond**, corpo **Inter**.

O **shell das Fases 0/1/2/3 já existe** — **não recriar**: sidebar role-aware (grupos **Relacionamento** e **Administração** já presentes), header, `(dashboard)/layout.tsx` (guard + branding + breadcrumbs), `useAuth()` (`role`, `companyId`, `name`, `userId`), tokens em `globals.css`. Reaproveitar `PageHeader`, `EmptyState`, `ErrorState`, `ActiveBadge`, `FsmBadge`, `CustomerAutocomplete`, `DateTimePicker`, `sonner/toast`, `formatDateTime()`, e o padrão de upload `api.postForm<{url}>("/uploads/", fd)`.

**Já implementado — só verificar/alinhar, NÃO refazer:**
- **WhatsApp (conexão/QR)** já está completo em `settings/integracoes` (`TabWhatsApp`): polling, contagem do QR, render `data:image/png;base64,${qr_code}`, Conectar/Gerar novo QR/Desconectar. **Não reescrever.**
- **Usuários** existe parcialmente em `settings/usuarios` (lista + convidar com `name`). **Acrescentar** papéis/desativar/transferir/convites + anti-escalonamento.
- **Settings de canais** (`settings/comunicacao`, toggles WhatsApp/Email) existe. **Templates e logs são telas novas em `/comunicacao`.**

**Convenções:** tokens semânticos (`bg-card`, `text-muted-foreground`, `bg-primary`…), nunca cores hardcoded (única exceção: o **preview** do Branding usa as cores escolhidas como literais). Ícones Lucide 16px/strokeWidth 1.5, nunca emojis. Título de página `font-display text-3xl tracking-wide`. Toda ação → `sonner`. Erro deriva do `detail` da API. Datas via `formatDateTime()`.

**Tradução TanStack → Next.js:** o protótipo `barberflow-system` é **TanStack Router + Vite**. Aqui é **Next.js App Router**: `createFileRoute`→`page.tsx` em `app/...`; `Link`/`useNavigate` do TanStack → `next/link` + `useRouter` de `next/navigation`; loaders do TanStack → `useEffect`+`fetch` (ou Server Components quando fizer sentido). **Importante:** o barberflow **NÃO tem nenhuma rota desta fase** — desenhe do zero herdando o vocabulário visual das Fases 1–3.

**Referências visuais:** consultar a pasta de **screenshots** da sessão; se houver screenshot aprovada, ela é o contrato. (Nesta fase **não há** screenshots aprovadas nem cobertura no barberflow.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 1. GLOSSÁRIOS E BADGES (adicionar a `lib/constants.ts` e `components/FsmBadge.tsx`)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**`lib/constants.ts` (fonte única — adicionar):**
- `NPS_SURVEY_STATUS_LABELS`: PENDING→"Pendente", SENT→"Enviada", RESPONDED→"Respondida", EXPIRED→"Expirada".
- `COMMUNICATION_LOG_STATUS_LABELS`: SENT→"Enviada", SCHEDULED→"Agendada", FAILED→"Falhou", SKIPPED_QUIET_HOURS→"Adiada (silêncio)", SKIPPED_NO_CONSENT→"Sem consentimento", SKIPPED_CHANNEL_DISABLED→"Canal desativado", SKIPPED_NO_TEMPLATE→"Sem template".
- `COMMUNICATION_CHANNEL_LABELS`: WHATSAPP→"WhatsApp", EMAIL→"E-mail", SMS→"SMS".
- `COMMUNICATION_AUDIENCE_LABELS`: CLIENT→"Cliente", PROFESSIONAL→"Profissional", OWNER→"Proprietário".
- `WHATSAPP_API_TYPE_LABELS`: UNOFFICIAL_BAILEYS→"Não-oficial (Baileys)", OFFICIAL_META→"Oficial (Meta)".
- `MODULE_LABELS`: ESTOQUE→"Estoque", COMISSOES→"Comissões", PACOTES→"Pacotes", ASSINATURAS→"Assinaturas", PROMOCOES→"Promoções", CRM→"CRM", NPS→"NPS", FILA→"Fila de espera", BOT_WHATSAPP→"Bot WhatsApp", LINK_PUBLICO→"Link público".
- `MODULE_DESCRIPTIONS`: descrição curta por módulo (informativa).
- `COMMUNICATION_EVENT_TYPE_LABELS`: appointment.confirmed→"Agendamento confirmado", appointment.cancelled→"Agendamento cancelado", appointment.reminder_24h→"Lembrete 24h", appointment.reminder_2h→"Lembrete 2h", appointment.completed→"Atendimento concluído", appointment.no_show→"Não comparecimento", auth.password_reset_requested→"Redefinição de senha", user.invitation_sent→"Convite de usuário", nps.survey_request→"Pesquisa NPS", nps.low_score_alert→"Alerta de nota baixa", waitlist.slot_available→"Vaga disponível (fila)", conversation.escalated→"Conversa escalada".
- `TEMPLATE_VARIABLES_BY_EVENT`: mapa evento→array de `{{variáveis}}` (chips no editor). Conjunto: `{{cliente_nome}} {{servico}} {{profissional}} {{data}} {{horario}} {{empresa_nome}} {{manage_url}} {{nps_url}} {{token}} {{user_name}} {{company_name}} {{activation_link}} {{nota}} {{comentario}} {{customer_name}} {{phone}} {{panel_url}}`.
- (já existe `ROLE_LABELS`: OWNER→"Proprietário", ADMIN→"Administrador", OPERATOR→"Operador", PROFESSIONAL→"Profissional", CLIENT→"Cliente".)

**`components/FsmBadge.tsx` (adicionar 2 badges, padrão existente `<Badge variant="outline" className={cn("font-normal", CLASS[status])}>`):**
- `NpsSurveyBadge`: PENDING→âmbar, SENT→sky, RESPONDED→emerald, EXPIRED→muted.
- `CommunicationLogBadge`: SENT→emerald, SCHEDULED→sky, FAILED→destructive, todos os `SKIPPED_*`→muted.

**Score NPS (display):** chip colorido por faixa — **0–6 vermelho (detrator), 7–8 âmbar (neutro), 9–10 emerald (promotor)**. É só exibição.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 2. BLOCO L — NPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### L1 — `/nps/config` (OWNER/ADMIN)
- `GET /nps/config` → `{id, company_id, enabled, channel, delay_minutes, min_interval_days, low_score_threshold, low_score_alert_enabled}`. `PUT /nps/config` (campos opcionais) salva.
- `Card` com: `Switch` enabled · `Select` channel (**WHATSAPP/EMAIL** — só esses) · `Input#` delay_minutes (hint "min. após conclusão") · `Input#` min_interval_days (hint "dias entre pesquisas/cliente") · `Slider/Input` low_score_threshold (0–10) · `Switch` low_score_alert_enabled. Botão "Salvar" → `PUT` → toast.

### L2 — `/nps` (OWNER/ADMIN)
- `GET /nps/surveys?status=&date_from=&date_to=` → **array plano** de `{id, customer_id, appointment_id, status(PENDING|SENT|RESPONDED|EXPIRED), scheduled_for, sent_at?, responded_at?, expires_at}`.
- `PageHeader` "NPS — Pesquisas" + link "Configuração" (L1) + filtros (status, período) + `Table`: Cliente (`customer_id`→nome ou "Em breve") · **Status** (`NpsSurveyBadge`) · Agendada (`scheduled_for`) · Enviada · Respondida · Nota (chip por faixa) · ações.
- Detalhe (`Sheet`, `GET /nps/surveys/{id}` → inclui `response: {score, comment, tenant_response, responded_at}`): mostra resposta do cliente (`score`+`comment`) e réplica do tenant. Se `RESPONDED` sem `tenant_response`: `Textarea` (1–2000) + "Responder" → `POST /nps/surveys/{id}/respond {response}` → toast. **Nunca editar o score.** Filtros e paginação client-side.

### L3 — `/nps/respond/[survey_id]` — PÚBLICA, SEM SHELL
- **Grupo `(public)` — sem sidebar, sem header.** Espelhar o visual de `book/[slug]` (`.book-page`).
- **Sem `GET`** — não pré-carregar nada. Form cego: título "Como foi sua experiência?", **seletor 0–10** (11 segmentos/`RadioGroup` horizontal, faixas detrator/neutro/promotor coloridas), `Textarea` "Comentário (opcional)" (max 2000), botão "Enviar".
- `POST /nps/respond/[survey_id] {score, comment?}` via **`publicFetch`/`api.publicPost` (SEM JWT)** — `survey_id` é o token.
- Estados: **idle** → **enviando** (spinner, botão off) → **sucesso** ("Obrigado pelo seu feedback!", não volta ao form) | **erro** (422 → "Esta pesquisa não está mais disponível"; outro → "Não foi possível enviar, tente novamente").

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 3. BLOCO M — COMUNICAÇÃO E WHATSAPP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### M1 — `/comunicacao` — Templates (OWNER/ADMIN)
- `GET /communication/templates` → `[{template_id, company_id, event_type, channel(WHATSAPP|EMAIL|SMS), audience(CLIENT|PROFESSIONAL|OWNER), body_template, is_active, is_default}]`.
- `PageHeader` "Comunicação — Templates" + "Novo template" + abas/segmentação por canal (client-side). `Table`/cards: Evento (`COMMUNICATION_EVENT_TYPE_LABELS`) · Canal · Público · Ativo (`ActiveBadge`) · Padrão (badge se `is_default`) · ações.
- **Criar** (`Dialog`, `POST`): `Select` event_type (catálogo dos labels) · `Select` channel · `Select` audience · `Textarea` body_template + **chips de `{{variáveis}}`** do `TEMPLATE_VARIABLES_BY_EVENT` (clicar insere no cursor) · `Switch` is_active.
- **Editar** (`Dialog`, `PUT`): event_type/channel/audience **read-only** (rótulos); **só** `body_template` + `is_active` editáveis.
- **Excluir** (`DELETE`, confirmação). **Preview de canal:** painel ao lado renderizando o corpo como bolha WhatsApp / email (substituir `{{var}}` por exemplos — só visual).

### M2 — `/comunicacao/logs` — Logs (OWNER/ADMIN) — **paginado, array plano**
- `GET /communication/logs?event_type=&status=&channel=&date_from=&date_to=&page=1&limit=50` → **array plano** de `{log_id, template_id?, event_type, channel, recipient_id, recipient_type, status, scheduled_send_at?, rendered_body?, sent_at?, error_message?, created_at}`.
- `PageHeader` + filtros (evento, status, canal, período) + `Table`: Data (`created_at`) · Evento · Canal · Destinatário (`recipient_type`+id curto) · **Status** (`CommunicationLogBadge`) · ações. Detalhe (`Sheet`): `rendered_body` + `error_message` (se FAILED).
- **Paginação (sem envelope):** estado `page` (1) + `limit` (50). "Próxima" habilitada se `resposta.length === limit`; "Anterior" se `page>1`. Mostrar "Página N". Filtros+page → query (server-side).

### M3 — `/settings/integracoes` (aba WhatsApp) — **VERIFICAR, NÃO REFAZER**
- Já implementado (`TabWhatsApp`). Contrato: `GET/POST/DELETE /whatsapp/connection`, `GET /whatsapp/qr`. `ConnectionResponse{status(DISCONNECTED|CONNECTING|CONNECTED|ERROR), phone_number?, connected_at?, qr_code?(base64 SEM prefixo), qr_expires_in?, disconnect_reason?}`; `QRCodeResponse{qr_code(base64 sem prefixo), expires_in}`.
- **QR:** `<img src={`data:image/png;base64,${qr_code}`} />`. **Polling** `GET /connection` (3s CONNECTING / 30s CONNECTED / 60s idle) — o backend sincroniza e vira CONNECTED. Ao expirar `qr_expires_in` → "Gerar novo QR" (`GET /qr`).
- Lacunas **opcionais**: `Dialog` no lugar de `confirm()`; `sonner` no lugar de erro cru; `Select` `whatsapp_api_type` (UNOFFICIAL_BAILEYS/OFFICIAL_META) + quiet hours via `PUT /communication/settings`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 4. BLOCO N — ADMINISTRAÇÃO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### N1 — `/settings/usuarios` (OWNER/ADMIN) — expandir o existente
Endpoints: `GET /users/` → `[{id, company_id?, email, name?, role, active}]`; `POST /users/invite {email*, role*, name?}` → `{invitation_id, expires_at}`; `PATCH /users/{id}/role {role}`; `DELETE /users/{id}` (→ active=false); `POST /users/transfer-ownership {new_owner_user_id*, current_owner_new_role="ADMIN"}`; `GET /users/invitations` → `[{invitation_id, email, role, status, expires_at, created_at, invited_by_user_id}]`; `DELETE /users/invitations/{id}`.

`PageHeader` "Usuários" + "Convidar usuário" + `Tabs` **Membros** | **Convites pendentes**.
- **Membros:** Nome · E-mail · Papel (`ROLE_LABELS`) · Ativo (`ActiveBadge`) · ações: **Alterar papel** (`Select` filtrado — ver anti-escalonamento; **oculto na própria linha**) → `PATCH role`; **Desativar** (`Dialog`; **desabilitado se for o último OWNER ativo**, Tooltip) → `DELETE`; **Transferir propriedade** (**só OWNER**: `Dialog` escolhe novo OWNER + "seu novo papel" default ADMIN, confirmação dupla) → `POST transfer-ownership`.
- **Convites:** E-mail · Papel · Status · Expira · Convidado por · **Cancelar** (só PENDING) → `DELETE invitations/{id}`.
- **Convidar** (`Dialog`): e-mail + nome + `Select` papel (filtrado) → `POST invite` → toast com expiração.

**🔒 ANTI-ESCALONAMENTO — a UI ENFORÇA (não só reage ao 403). Regras EXATAS do backend (`INVITE_PERMISSION`):**
- **OWNER** pode convidar/atribuir: **OWNER, ADMIN, OPERATOR, PROFESSIONAL** (CLIENT irrelevante no painel).
- **ADMIN** pode convidar/atribuir **APENAS OPERATOR, PROFESSIONAL** — **nunca OWNER nem ADMIN**.
- **Nunca oferecer** `PLATFORM_OWNER` (só PLATFORM_OWNER atribui → 403) nem `PLATFORM_SUPPORT/PLATFORM_BILLING/PLATFORM_READONLY` (schema-only → 422).
- **Não alterar o próprio papel** (403) → sem ação na própria linha.
- **Não desativar o último OWNER ativo** (422) → desabilitar com Tooltip.
- **transfer-ownership só OWNER** (ADMIN → 403).
- ⚠️ O backend **NÃO** impede um OWNER rebaixar **outro** OWNER. Se quiser, adicione uma **confirmação extra** de UX nesse caso — mas **não** é regra do backend; não dependa do 403 para isso.

### N2 — `/settings/modulos` (OWNER/ADMIN)
- `GET /tenant/modules` → `[{activation_id, company_id, module_name, is_active}]` (10 módulos, enum fechado). `POST /tenant/modules/{module_name}/activate` | `/deactivate` → `ModuleActivationResponse`.
- Grid de **cards**: ícone + `MODULE_LABELS[module_name]` + `MODULE_DESCRIPTIONS[module_name]` + dependências (texto informativo) + `Switch` (`is_active`). Toggle → activate/deactivate (otimista + rollback no erro) → toast. **Não inventar** campo de dependências (só texto).

### N3 — `/settings/branding` (OWNER/ADMIN) — preview ao vivo
- `GET /tenant/branding?company_id={useAuth().companyId}` → `{logo_url?, primary_color?(#RRGGBB), secondary_color?(#RRGGBB), font_family?, favicon_url?, custom_texts(obj)}`. `PUT /tenant/branding` (campos opcionais) salva.
- **Duas colunas:** esquerda = form (upload **logo** via `/uploads/`→`logo_url`; upload **favicon**→`favicon_url`; **color picker** `primary_color` + `secondary_color`; `Select/Input` `font_family`); direita = **preview ao vivo** (mini-mock header+botão+card usando as cores/fonte escolhidas como **valores literais inline**, atualizando a cada mudança). Validar hex (`#`+6). "Salvar" → `PUT` → toast.
- ⚠️ **Campos reais:** `primary_color`, `secondary_color`, `font_family` — **NÃO** existem `accent_color`/`font_display`.

### N4 — `/audit` (OWNER/ADMIN; export OWNER-only) — append-only, paginado COM envelope
- `GET /audit/logs?action=&actor_id=&date_from=&date_to=&page=1&limit=50` → **`{total, page, limit, items[]}`**; item `{audit_id, company_id?, actor_id, actor_role, action, resource_type, resource_id?, reason?, before_snapshot?, after_snapshot?, occurred_at, ip_address?}`.
- `GET /audit/impersonation-accesses?page=1&limit=50` → `{total, page, limit, items[]}`; item `{audit_id, grant_id?, actor_id, reason?, request, occurred_at}`.
- `GET /audit/logs/export?...` → **CSV** (download; `text/csv`, attachment). **OWNER-only** (ADMIN → ocultar/desabilitar c/ Tooltip).
- `PageHeader` "Auditoria" + "Exportar CSV" (só OWNER) + filtros + `Tabs` **Trilha** | **Acessos de impersonation**.
  - **Trilha:** `Table` Data · Ator (`actor_id` curto + `actor_role`) · Ação · Recurso (`resource_type`+id) · Motivo · IP · ver snapshots (`Sheet`, JSON read-only).
  - **Impersonation:** Data · Grant · Ator · Motivo · Requisição (`Sheet`).
- **Paginação (envelope):** "Página N de ⌈total/limit⌉"; Anterior/Próxima conforme `total`. **Sem** editar/excluir/criar (append-only) — só leitura/filtro/paginação/export.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 5. REGRAS TRANSVERSAIS E ENTREGÁVEIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- **Estados obrigatórios** (exceto L3): vazio (`EmptyState`), loading (`Skeleton`), erro (`ErrorState` + retry), dados.
- **Toast** após toda ação. Erro do `detail` da API.
- **Duas paginações distintas:** M2 = **array plano** (próxima se `length===limit`); N4 = **envelope** (`total/page/limit`). Não unificar.
- **NPS público (L3)** = única tela sem shell, sem auth (`publicFetch`).
- **Anti-escalonamento (N1)** enforçado pela UI; 403 é só a rede de segurança.
- **QR (M3)** já existe — não duplicar; render `data:image/png;base64,${qr_code}`.
- **Não inventar campos:** branding = `secondary_color`/`font_family` (não accent/font_display); módulos sem campo de dependências; templates só editam corpo+ativo.
- **Não construir** (Fase 5): Portal do cliente, Painel Owner, `/gestao/[token]`, `/platform/*`.

**Telas a entregar (10):** L1 `/nps/config` · L2 `/nps` · L3 `/nps/respond/[survey_id]` (pública) · M1 `/comunicacao` · M2 `/comunicacao/logs` · M3 aba WhatsApp (verificar) · N1 `/settings/usuarios` (expandir) · N2 `/settings/modulos` · N3 `/settings/branding` · N4 `/audit`. Mais: 2 badges em `FsmBadge.tsx` e os glossários em `constants.ts`.

*Vença este documento onde divergir do protótipo. Nenhuma regra de negócio vive no frontend — a verdade é o backend (403/422 → ocultar/desabilitar).*
