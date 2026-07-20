## Isolamento multi-tenant no módulo `users` (S0.2)

⚠️ **Não há rede de segurança no banco.** O `set_rls_context` é chamado, mas o role
da aplicação tem `BYPASSRLS` e é dono das tabelas — as policies de RLS **nunca são
avaliadas**. O isolamento entre tenants depende **inteiramente** dos filtros
`company_id` no código. Um filtro esquecido é um vazamento real, não um risco
mitigado por segunda camada.

### Regra

Toda função que resolve um **recurso-alvo por ID** deve filtrar também pelo tenant
do ator. Buscar só por `Model.id` é o anti-padrão que produziu os dois vazamentos
corrigidos no S0.2 (`assign_role` e `deactivate_user` permitiam que um OWNER/ADMIN
alterasse o papel e desativasse usuários de **outro** tenant, bastando conhecer o
UUID).

### Escopo do `PLATFORM_OWNER` (decisão do S0.2)

O filtro de posse vale **também** para o `PLATFORM_OWNER` nestes endpoints — não há
exceção para o staff da plataforma.

Isso é **deliberado**, não efeito colateral do fix:

- O `effective_company_id` da impersonação é injetado pelo middleware, mas o módulo
  `users` **nunca o lê** (só o `audit/router.py` consome). Não existe, portanto,
  caminho *desenhado* para o staff administrar usuários de um tenant por aqui — o
  único caminho era o próprio vazamento.
- Com `actor.company_id IS NULL`, o `PLATFORM_OWNER` continua gerenciando **usuários
  de plataforma**, que é o caso legítimo — coerente com `invite_user`, que grava
  `company_id = NULL` para convites de plataforma.
- Mesma semântica que `cancel_invitation` já usava corretamente por construção.

**Se a plataforma precisar administrar usuários de tenants**, o caminho correto é
ligar o `effective_company_id` (impersonação ELEVATED, time-boxed e auditada) a
este módulo — **não** afrouxar o filtro. Está na fila.

### Erro indistinguível

Alvo inexistente e alvo de outro tenant devem produzir **o mesmo status e o mesmo
`detail`**. Distinguir os dois transforma o endpoint em oráculo de enumeração de
UUIDs — trocaria um vazamento de escrita por um de leitura.

### Dívidas conhecidas neste módulo (fila pós-S0.2)

- **Trilha de auditoria incompleta:** `deactivate_user` é a única das três operações
  sensíveis do módulo **sem** `record_sensitive_action` — bloquear o login de um
  usuário não deixa rastro. Somado a isto: o `assign_role` registrava
  `company_id = actor.company_id`, então a trilha mentia sobre *onde* o fato
  ocorreu (mitigado pelo fix, já que agora ator e alvo são sempre do mesmo tenant).
- **`transfer_ownership` — ternário sem parênteses:**
  `User.company_id == str(actor.company_id) if actor.company_id else None`
  — a precedência faz o `filter()` receber `None` cru quando `company_id` é `None`,
  o que levantaria `ArgumentError`. Inalcançável hoje (o guard de entrada exige
  OWNER, que sempre tem `company_id`), mas armado se aquele gate for flexibilizado.
  **Ocorrência única** no módulo — `cancel_invitation` é correto por construção.
- **12 testes de RBAC não rodam na suíte completa** — ver abaixo.

### ⚠️ `test_sprint2_rbac.py` — cobertura desligada

As 12 falhas "pré-existentes conhecidas" da suíte **não são ruído**: são classes de
`test_sprint2_rbac.py` (incluindo `TestAssignRoleService` e `TestDeactivateUser`)
que falham por **contaminação de ordem de import** — o monkey-patch de modelos do
arquivo não re-vincula o `User` que `users/service.py` já importou, então qualquer
arquivo que importe o service antes quebra o arquivo inteiro. Isoladas, passam 35/35.

**Consequência:** a cobertura de RBAC destes endpoints está efetivamente desligada
na suíte completa. Foi um dos dois motivos pelos quais os vazamentos do S0.2
sobreviveram — o outro é que nenhum dos testes existentes cobria cenário
cross-tenant. Não normalize essas falhas como "conhecidas": é um mecanismo de
defesa em silêncio. Correção na fila.

## Bot F4 — turno como SUB-ESTADO do canal bot (b534605)
  Decisão D1: o turno vive na CAMADA DE ADAPTAÇÃO do bot. O FSM (compartilhado
  com o web) NÃO conhece turno — engine com ZERO mudanças.
  Fluxo bot: serviço → profissional → data → TURNO → horário → confirmar.
  Fluxo web: data → horário direto (INALTERADO — provado por teste;
    update(SELECT_SHIFT) ainda levanta InvalidActionError).

  Implementação: quando SELECT_DATE devolve AWAITING_TIME, a camada marca
  bot_substate="AWAITING_SHIFT" no context e deriva as contagens da MESMA lista
  que o FSM entregou (result.options, dia inteiro) via _SHIFT_DEFS +
  _filter_slots_by_shift → contagem == lista POR CONSTRUÇÃO (invariante do F2),
  sem query extra. A escolha do turno NUNCA passa por engine.update() (travado
  por teste); chama _handle_select_shift direto e espelha os metadados de sessão
  (last_action, expires_at, guard de expiração) manualmente.
  O FSM permanece em AWAITING_TIME o tempo todo.

  Primitivas órfãs reusadas SEM alteração: get_shift_availability (stateless),
  _SHIFT_DEFS, _filter_slots_by_shift, _handle_select_shift.
  Ajustes só na apresentação: _send_shifts + "← Voltar" (F3); parser espelha o
  título exibido ("Tarde (12 horários)") p/ voto de enquete.

  Turno vazio: exibido com "— indisponível", escolha rejeitada com mensagem
  (mesma UX do legado; mantém a NUMERAÇÃO DAS LINHAS ESTÁVEL entre datas).
  Conflito de confirm (SLOT_UNAVAILABLE) re-entra no menu de TURNOS.
  Sessões pré-F4 (AWAITING_TIME sem selected_shift) degradam p/ o BACK antigo.

## Dívida p/ o F6
  Reagendamento vai direto a ESCOLHENDO_HORARIO (pool sem data); o turno legado
  só aparece via "outra data" — inconsistência do dispatcher duplo.

## Bot F3 — navegação BACK (2cbf71e)
  "voltar"/"volta"/nav_voltar/"← voltar" (helpers.BACK_WORDS, fonte única) →
    BACK de UM estado. Reset total só com 0/menu/início/sair.
    "ver agendamentos" e "atendente/humano" intactos.
  BACK no 1º estado (AWAITING_SERVICE) → menu principal, interceptado no
    bot_service ANTES do engine (canal web NÃO afetado).
  "voltar" tratado ANTES do classificador → não vira linha FALLBACK na telemetria.
  Handlers legados (_handle_legacy_back, central): CANCELANDO→GERENCIANDO;
    GERENCIANDO→VER_AGENDAMENTOS **limpando is_rescheduling** (⚠️ sem isso o
    marker do F1 vazaria e cancelaria o agendamento antigo num booking futuro);
    CONFIRMANDO→re-lista horários; ESCOLHENDO_HORARIO/TURNO→escolha de data;
    demais→menu (idêntico ao comportamento antigo, nenhum hábito quebra).

  ⚠️ BÔNUS — corrigiu desalinhamento de índice PRÉ-EXISTENTE: _parse_time agora
  espelha a página exibida (nav + slots da página + Voltar, mesma ordem do
  formatter). ANTES: o número indexava a lista COMPLETA → na pág. 2, digitar "2"
  selecionava o 2º slot do DIA, não o da linha 2 (outra fonte de "confirmou
  horário diferente"). Slot fora da página só resolve por row_id/título.

## Dívida pré-existente (não do F3)
  Appointment.idempotency_key é UNIQUE NÃO-PARCIAL → barra re-booking do mesmo
  cliente+serviço+slot mesmo após CANCELLED (cliente que cancela não consegue
  remarcar o mesmo horário). Correção seria índice PARCIAL (só não-cancelados).

## Bot F2 — truncamentos residuais de horário (74e99a8)
  1. Re-listagem pós-conflito (engine.py:1362): limit=6 → limit=0.
     Antes: o conflito gravava lista truncada de 6 (manhã) em last_listed_slots
     para o RESTO da sessão — reintroduzia o bug que 7ebde4a corrigiu.
  2. Pool legado (escolhendo_horario.py:76): caminho COM data busca o dia
     inteiro (limit=0), mesma fonte da contagem de turno. Caminho SEM data
     mantém pool de 30 (ali não há contagem a alinhar; limit=0 vira 6 em
     list_next_available_slots e REDUZIRIA a oferta).
  3. list_next_available_slots (engine.py:507): ordena por start_at ANTES de
     truncar + removido o break precoce (descartava profissionais inteiros —
     sem isso a ordenação operaria sobre conjunto enviesado) + dedup por
     horário (espelha list_available_slots pós-7ebde4a).
  Evidência (dev, 42 slots, 2 profs, 9h-21h): contagens {manhã 6, tarde 12,
  noite 6} batem com a lista nos 3 turnos. Antes: o pool de 30 entregava
  0 dos 6 horários de noite prometidos. → DESTRAVA O F4.

## UX registrado (candidato a fase futura)
  No conflito de confirm, o profissional fica PINADO no select_time — cliente
  que escolheu "qualquer profissional" é re-listado só com a agenda daquele.
  Correto por construção, mas talvez não ideal. Decidir se o conflito deve
  re-listar com "qualquer" de novo.

## Bot F1 — BUG C: reagendar mudando serviço cancela o antigo (b742e96)
  CAUSA REAL (divergiu do mapa): o vínculo NUNCA se perdia — reagendar_mudar
  preserva managing_appointment_id/is_rescheduling no BotSession.context.
  O bug: o fluxo entra no pipeline BookingEngine (AWAITING_SERVICE); a
  confirmação acontece em _handle_booking_state → CONFIRMED, que NÃO lia
  os marcadores — e reset_session os apagava em seguida.
  (Mesmo achado do F5a: INTENT_TO_STATE é nominal; o pipeline real difere.)

  FIX: marcadores consumidos em bot_service.py:483 (branch CONFIRMED), ANTES
  do reset. Sem migration. Ordem: engine só devolve CONFIRMED com o novo já
  criado+commitado → só então cancela o antigo (cancel_appointment,
  skip_policy=True, reason="Substituído por reagendamento com serviço diferente").
  Falha na criação (slot roubado) → nunca chega ao cancel → antigo permanece.

  ⚠️ TRADE-OFF INERENTE À ORDEM SEGURA: o cliente NÃO consegue remarcar para
  um horário que colida com o PRÓPRIO agendamento antigo (slot ainda ocupado
  no confirm → 409 → escolhe outro). É intencional: o inverso (cancelar antes)
  permitiria, mas deixaria o cliente SEM NADA se a criação falhasse.
  skip_policy=True no cancel: re-aplicar política depois do novo existir
  poderia bloquear a substituição e RECRIAR o órfão. Janela já validada na
  entrada (gate opt_reagendar).

  Código morto removido: confirmando.py:112-153 (branch inalcançável),
  reagendando.py inteiro (0 dispatches), original_service_id/professional_id.
  INTENT_TO_STATE["REMARCAR"] → VER_AGENDAMENTOS (o roteamento real).
  Telemetria: substituição consome marker REMARCAR + service_changed=True
  + replaced_appointment_id.

## Bot F5a — shadow mode + volante de telemetria (29209d9, feat/bot-shadow-telemetry)
  Shadow gate (bot_service _classify_and_route): LLM_MODE=shadow (default) →
    resultado source=LLM PERSISTE mas devolve False (não roteia; menu exibido).
    regex continua roteando (comportamento do usuário byte-idêntico ao atual).
    LLM_MODE=live (futuro) → LLM roteia; mudança informada pela telemetria.
    Ligar a LLM = setar LLM_API_KEY (coleta pura em shadow); key no Railway no
    deploy, mantendo LLM_MODE=shadow.
  Migration e0s30_intent_telemetry (head ← e0s29; aplicada SÓ no dev):
    intent_outcomes (tabela-irmã 1:1, classification_id UNIQUE FK CASCADE, RLS):
    ausência de linha = PENDING (LEFT JOIN). fsm_state + routing_decision
    (ROUTED | MENU_FALLBACK | SHADOW_NOT_ROUTED | INACTIVE_MODULE_MSG)
    ficam na própria intent_classifications (contexto do mesmo request).
  Correlação classificação→desfecho: marker intent_track no BotSession.context
    (NÃO por session_id — que é reutilizada). Morre com a conversa; substituído
    a cada classificação (anterior vira ABANDONED superseded); janela 30min.
    Telemetria ambígua NUNCA vira linha.
  Write-backs (best-effort, nunca derrubam o bot): 3a clique-pós-fallback/shadow
    (ground truth — MENU_CLICK_AFTER_FALLBACK {menu_option, suggested_intent});
    3b confirmação/cancelamento — instrumentado em _handle_booking_state
    (pipeline BookingEngine, onde AGENDAR materializa) E confirmando.py
    (reagendamento), cancelando.py (CANCELAR), comprando_produto/pacote
    (COMPRAR_*). Consumo só quando a intenção do marker casa com o ponto.
  _CLASSIFY_TOOL: entities apertado (servico/dia/hora/profissional, opcionais,
    additionalProperties=false) — p/ F5b consumir.
  ACHADO: AGENDAR via classificador entra no BookingEngine FSM (AWAITING_SERVICE),
    NÃO no legado ESCOLHENDO_SERVICO. INTENT_TO_STATE é nominal.
  Validação dev 30/30 checks (migration up/down/up limpa; shadow contém LLM incl.
    FALAR_COM_HUMANO; ponta-a-ponta regex→FSM real→agendamento→FLOW_CONFIRMED).
    Sem LLM_API_KEY no ambiente — camada LLM exercitada via NullLLMClassifier
    (source=LLM real no fluxo). Suíte 1183 passed (12 rbac pré-existentes) +
    17 novos (tests/test_bot_f5a_shadow_telemetry.py); test_sprint26 atualizado
    (deliberado): FALAR_COM_HUMANO via LLM agora exige LLM_MODE=live p/ rotear.

## Telemetria de intenção — avisos de qualidade de dados
  - Filtrar por source (REGEX|LLM|FALLBACK), NÃO por llm_provider: linhas
    FALLBACK têm llm_provider preenchido mesmo sem LLM real (curto-circuito
    sem key seta provider/model quando a camada LLM é tentada).
  - session_id NÃO delimita conversa (reutilizada entre conversas). Qualquer
    correlação exige o marker intent_track + janela temporal, nunca session_id só.

## Remoção código morto predictor.py (49005e3, chore/remove-dead-predictor)
  booking/predictor.py deletado (74 linhas): 0 callers; construía
  PredictiveOfferResult (importado de schemas.py) com campos inexistentes
  slot_start_at/slot_end_at → TypeError latente se chamado.
  Removido o import + entrada em __all__ de booking/__init__.py.
  Código real BookingEngine.get_predictive_offer (engine.py:654) e o
  dataclass PredictiveOfferResult (schemas.py:88, next_slot/expires_at) intocados.

## Bot F0 — hotfix exibição de fuso (5891eb8, fix/bot-timezone-display)
  Bug: fluxo PREDITIVO gravava/exibia UTC; fluxo NORMAL já convertia
    (engine.py:423) → bug intermitente (cliente via hora certa às vezes).
  Fix: abordagem (a) — persiste UTC (inalterado), converte só na EXIBIÇÃO.
    helpers.to_company_tz = wrapper fino delegando a BookingEngine._to_company_tz.
    8 pontos de exibição convertidos (gerenciando:31, cancelando:44, inicio:144,
    confirmando:35-37/88, oferta_recorrente, label_date:125).
    GRAVAÇÃO byte-idêntica (slot_start_at persistido continua UTC ISO).
  Display-only, sem migration. Validado no dev (16/16 checks), 9 testes novos.

## Dívidas registradas (bot)
  - bot chama list_available_slots SEM passar o timezone do tenant (usa
    default America/Sao_Paulo). OK hoje (tenants SP); bug se tenant ≠ SP.

## Ambiente de dev isolado + migration baseline (feat/dev-environment)
  Baseline `e0s00_baseline_core_tables` = nova RAIZ da cadeia Alembic: cria as
    12 tabelas núcleo pré-Alembic (appointments, companies, users, clients→
    customers, professionals, services, professional_services, company_settings,
    appointment_services, appointment_status_log, blocked_slots→schedule_blocks,
    working_hours) no shape LEGADO — a cadeia as transforma até produção.
    ⚠️ NUNCA rodar upgrade da baseline em produção (já tem as tabelas; está em
    e0s29, descendente — o Alembic a considera aplicada; nenhum stamp preciso).
  Banco DEV: projeto Supabase tvguwtdfayhrctlpollf (produção = uhhygdqioqcgcfqfbmif).
    Nasce de `alembic upgrade head` puro (baseline→e0s29, 98 migrations) —
    validado 2026-07-07: schema dev ≡ produção (diff completo: colunas, tipos,
    constraints, índices, RLS, policies, triggers, enums, extensões).
  Alternar ambiente: `.env` = produção (realidade atual), `.env.dev` = dev
    (gitignored). Para rodar contra dev: copiar .env.dev sobre .env OU exportar
    DATABASE_URL na sessão (env var vence o .env — load_dotenv não sobrescreve).
  Alembic: URL vem SÓ de DATABASE_URL (env.py; alembic.ini sem URL hardcoded;
    sem DATABASE_URL → RuntimeError). env.py pré-cria alembic_version com
    VARCHAR(255) (IF NOT EXISTS — no-op em bancos existentes).
  Migrations antigas com patches [retrofit baseline e0s00] (só afetam replay
    em banco vazio; produção está além delas): 16014789aa88 (remove criação de
    4 índices que produção não tem), 36e2e1f526da (guard: working_hours já
    existe via baseline), 540331d2c848 (3 guards anti-duplicata),
    a8c81686f38e (financial_status VARCHAR — enum nunca existiu em produção).
  Seed: `scripts/seed_dev.py` (guard: aborta se DATABASE_URL contém o ref de
    produção). Cria PLATFORM_OWNER, company barbearia-dev via create_company(),
    OWNER, 2 services, 1 professional c/ escala, 2 customers, 1 product,
    1 package. Senha dev: DevPaladino2026.
  ⚠️ DRIFT DE PRODUÇÃO detectado 2026-07-07: integration_credentials em
    produção NÃO tem as colunas provider/status (migration e ORM as definem;
    tabela com 0 linhas em produção). Corrigir em janela de manutenção:
    ALTER TABLE integration_credentials
      ADD COLUMN provider credentialprovider NOT NULL,
      ADD COLUMN status credentialstatus NOT NULL DEFAULT 'ACTIVE';
    (conferir spec exata em e1f5g2h3i4j5 antes de rodar).

## Sprint C Produtos — aviso de pendências na conclusão (1ce4854)
  get_pending_pickups(customer_id, company_id): product_sale RESERVED|
    PURCHASED (não PICKED_UP), colunas indexadas. Módulo novo
    app/modules/product_sales/ (service + schemas, sem router próprio).
  GET /appointments/{id}/pending-products (padrão available-credit,
    auth OWNER/PROFESSIONAL, posse por company): {has_pending, items[]}.
  _send_pos_atendimento: após appointment.completed, se há pendência →
    dispatch novo event_type "product_pickup.reminder" (CLIENT/WHATSAPP).
    NÃO-transacional: fora de _QUIET_HOURS_SCHEDULED/_TRANSACTIONAL →
    descartado em quiet hours (SKIPPED_QUIET_HOURS). Painel é garantia primária.
  complete_appointment (service) NÃO tocado — cota/transition/sinal intactos.
  Template semeado em _DEFAULT_TEMPLATES (create_company) só p/ tenants NOVOS.
    Tenants existentes: INSERT manual (caveat Sprints G/I). Sem template →
    SKIPPED_NO_TEMPLATE (degrada limpo).
  Edge aceito: Customer duplicado pré-backfill pode esconder pendência
    (check por client_id do agendamento).

## get_dashboard — counts (F4b)
  get_dashboard retorna counts {coupons, reserved_products, payments}
  além das listas de cotas/assinaturas. Respeita company_id (mesmo
  filtro dos demais). coupons reusa a lógica de vigência de get_coupons;
  reserved_products e payments são count() simples.

## Filtro company_id nos endpoints do portal (766162a)
  credits, subscriptions, coupons, payments, product-sales, dashboard
    aceitam company_id: Optional[UUID] = Query(None) — padrão de /history.
  Filtro opera sobre customer_ids da identity (nunca direto na tabela):
    company_id alheio → customers vazio → resultado vazio. Seguro por construção.
  Cupons genéricos (customer_id NULL) respeitam o filtro (company_ids
    derivado dos customers já filtrados).
  product-sales: + ProductSale.company_id direto (defesa em profundidade);
    combina com filtro de status.
  payments/product-sales: filtro reduz ANTES de paginar (total = filtrado).
  dashboard: filtra as 3 sub-listas (upcoming/credits/subscriptions)
    simultaneamente — base do menu de empresas do hub (resumos por empresa).
  Ausência de company_id = comportamento atual (não regride).

## Sprint B Produtos (9b4f574, integration/validacao-pre-push)
  GET /portal/product-sales?status=&page=&page_size=
    status opcional: RESERVED | PURCHASED | PICKED_UP (pattern-validado)
    sem status → histórico completo (todas as vendas da identity)
    cross-tenant, paginado, isolado por identity (padrão get_payments)
  Resposta inclui product_id (link de volta à vitrine; FK RESTRICT sempre resolve)
    + snapshot (product_name, quantity, unit_price, total_price), status,
    created_at, picked_up_at, company_name.
  As 3 visões do portal saem desta rota única filtrada por status.

## Sprint A Produtos (c1dd288, integration/validacao-pre-push)
  Modelo ProductSale (product_sales, migration e0s29 — head agora e0s29):
    company_id, customer_id, product_id, payment_id (nullable),
    product_name/quantity/unit_price/total_price (snapshots),
    status RESERVED|PURCHASED|PICKED_UP, picked_up_at. SEM appointment_id
    (compra avulsa). TimestampMixin de db.base (não há módulo mixins).
  Checkout grava ProductSale RESERVED por item de products[], payment_id
    vinculado ao Payment manual CASH PENDING (produto tem Payment hoje —
    pago no local; None só defensivo).
  Migration e0s29 NÃO aplicada — rodar em janela controlada.

## Pré-deploy — RESOLVIDO (verificado 2026-07-07)
  alembic_version.version_num em produção JÁ É VARCHAR(255) (verificado via
  information_schema). Além disso env.py agora pré-cria a tabela com
  VARCHAR(255) em bancos novos — o problema não volta.

## Portal Camada 2 (a142fc9, integration/validacao-pre-push)
  GET /portal/companies — empresas cross-tenant da identity (com slug p/ link agendar)
  GET /portal/coupons — nominais (customer_id) + genéricos (NULL) do tenant
  GET /portal/payments — histórico read-only paginado (Payment.customer_id)
  GET /portal/appointments/{id} — detalhe rico + endereço (CompanyProfile) + can_cancel/reschedule
  POST /portal/appointments/{id}/cancel — reusa appointment_svc.cancel_appointment
    (user_id=None, skip_policy=True); deposit_retained computado ANTES do cancel
  POST /portal/appointments/{id}/reschedule — reusa reschedule_appointment
    (skip_policy=True, bypass_working_hours=False); 409→422; novo manage_token automático
  get_current_portal_identity_optional (core/deps) — None se sem token,
    401 se token inválido (NÃO degrada para anônimo)
  Checkout JWT portal opcional: identity precede body; phone_e164 NUNCA
    passa por validate_user_phone_input; consent SourceChannel.PORTAL

## Fatos de modelo (não-óbvios, confirmados no Camada 2)
  Coupon NÃO tem discount_type/value/valid_until próprios — vêm da
    Promotion pai via promotion_id (batch lookup p/ evitar N+1).
    Expiração do cupom = Coupon.expires_at (fallback promotion.valid_until).
  Payment PK = payment_id (não id).
  resolve_deposit_policy(service_id, company_id, db) — db por último.
  is_within_refund_window(start_at, now, refundable_until_hours_before) — escalares.
  _compute_deposit_retained checa Payment CONFIRMED além das primitivas
    (sem sinal pago → False) p/ paridade exata com /manage.
  AppointmentService.duration_snapshot é Numeric — int() na resposta.

## Validação de telefone em formulários públicos
  valid_ddds.py: whitelist ANATEL (67 DDDs válidos)
  validate_user_phone_input (resolver.py): função SEPARADA de
    normalize_phone_e164 (que fica intocado para bot/painel/portal).
    Regra: strip não-dígitos → remove zero inicial único → 10-11
    dígitos → DDD em VALID_DDDS → senão InvalidUserPhoneError.
    Limite 11 díg. rejeita DDI automaticamente.
  Aplicado em 4 pontos de formulário público:
    SET_CUSTOMER (FSM), /confirm, /start, /checkout.
    NÃO aplicado: bot (E.164 do Meta), painel tenant, portal register.
  Dívida: public_book legado (public/service.py) sem validação —
    candidato a deprecação.

## Checkout unificado — B2 endpoints públicos (2026-06-25)
Branch `feat/checkout-unificado-backend` (continua do B1). **Sem migration** (head `e0s28`).
5 endpoints novos em `booking/router.py` (prefixo `/booking/{slug}`, gate `_require_online_booking`):
  - `GET /packages?service_id=` → `PublicPackageOut[]` (pacotes ativos; filtro opcional por serviço)
  - `GET /subscription-plans?service_id=` → `PublicPlanOut[]`
  - `GET /promotions` → `PublicPromotionOut[]` (só `ACTIVE` + `AUTOMATIC` vigentes)
  - `POST /coupon/validate` → `CouponValidateResponse` (usa `compute_preview`, nunca persiste)
  - `POST /checkout` (201) → `CheckoutResponse` (agendamento + pacote + assinatura + produto)
Schemas em **`booking/checkout_schemas.py`** (arquivo novo).
Service functions novas: `packages.get_packages_containing_service`,
  `subscriptions.get_plans_containing_service` (ambas anexam item names via
  `_attach_item_names`/`_attach_plan_item_names`), `promotions.list_active_promotions`.
**`apply_coupon_to_payment` NÃO existe** — alternativa adotada (prevista no enunciado):
  `packages.purchase()` e `subscriptions.subscribe()` ganharam param `coupon_code: Optional`
  repassado a `create_payment` (que já aceitava `coupon_code`); produtos passam direto.
  Cupom roteado a UM destino: pacote → senão assinatura → senão produto (1º item de cada).
**`_resolve_owner_user_id` DUPLICADO** como helper local em `booking/router.py` (lógica idêntica
  à de `whatsapp/handlers/comprando_produto`) para não acoplar router público ao módulo do bot.
  Sem OWNER → produto cobra mas pula baixa de estoque + adiciona `warnings[]`.
`compute_preview` retorna `{final_amount, discount_total, applications, coupon_valid}` (NÃO
  `net_charged_amount`/`discount_amount`/`promotion_name` do enunciado) — `validate_coupon`
  mapeia: net_amount=final_amount, discount_value=discount_total, discount_type=applications[0].
Agendamentos: `bypass_working_hours=False` (cliente nunca bypassa); slot ocupado propaga **409**
  (o DoD mencionava 422 genérico, mas `_assert_slot_available` real levanta 409 p/ conflito).
`total_charged` = soma de pacotes+assinaturas+produtos (agendamento não cobra aqui);
  `discount_amount` da resposta fica `None` (frontend usa `/coupon/validate` p/ exibir desconto).
Testes: `tests/test_checkout_b2.py` (14 testes, estilo unitário com handlers + mocks). 1041 passed.

## Checkout unificado — B1 (2026-06-25)
Branch `feat/checkout-unificado-backend`, commit `c9529d3`. **Sem migration** (head permanece `e0s28`).
`create_appointment`: retorna `(appointment, raw_token: str)` como tupla.
  Callers: router do painel ignora o raw_token (já enviado via notificação);
  engine FSM usa para montar `manage_url` no `BookingResult`/`ConfirmationHTTP`.
`BookingResult` + `ConfirmationHTTP`: `manage_url: Optional[str] = None`.
`_handle_set_customer` (FSM web): usa `resolver.resolve_for_tenant` +
  `grant_consent(COMMUNICATION, LINK)` quando `is_new=True`.
  DDD inválido → `InvalidActionError` (não propaga HTTPException 422 cru).
Consent: módulo real é `app.modules.identity.consent_service`
  (não `app.modules.consent.service`).
Testes: `tests/test_checkout_unificado.py` (8 testes).

## OWNER bypass de horário de trabalho (2026-06-24)
Branch `feat/owner-bypass-working-hours`, commit `021eb20`. **Sem migration** (head permanece `e0s28`).
`_assert_slot_available(bypass_working_hours=False)`:
  - `True` → pula passos 1 (dia sem escala) e 2 (janela opening/closing)
  - `False` → comportamento original (todos os roles exceto OWNER)
  - Passos 3 (conflito) e 4 (bloqueio manual) **sempre executados**.
Router injeta `bypass_working_hours=(user.role == "OWNER")` em:
  `POST /appointments/` e `PATCH /appointments/{id}/reschedule`.
`create_appointment` e `reschedule_appointment` propagam o flag (assinatura usa `user_id`).
Testes: `tests/test_owner_bypass_working_hours.py` (16 testes, 6 casos do DoD).

**Fase 2 concluída.** Sprint 25 concluído (2026-06-13 — schema-only Estágio 1+ + suite de contrato + wiring DEPOSIT). **Estágio 0 fechado** (suite de contrato verde contra PostgreSQL real). HEAD migration: `e0s28_professional_contact_customer_filter`. Suite: 1003 passed / 12 failed (12 pré-existentes por contaminação de ordenação em `test_sprint2_rbac` — `app.main` importado antes do monkey-patch de modelos; corrigir em sprint dedicado de housekeeping de testes, não é regressão nem dívida de lógica de produção).

## e0s28 — Professional contact + customer filter (2026-06-23)
Sprint complementar de backend. **HEAD migration: `e0s28_professional_contact_customer_filter`**
(← e0s27_professional_user_link). Branch `feat/professional-scope-backend`, commit `def56aa`.
+8 testes (`tests/test_sprint28_professional_contact.py`).
- `professionals`: `email VARCHAR(255)` nullable + `phone VARCHAR(20)` nullable (E.164, sem
  normalização/validação no backend — campo livre, ao contrário de `Customer.phone`).
- `ProfessionalCreate`/`Update`/`Response`: `email` e `phone` opcionais.
- `GET /customers/`: `professional_id` como query param. **PROFESSIONAL tem o filtro forçado**
  ao próprio cadastro (sem vínculo → `UUID(int=0)` → subquery não casa → lista vazia) — mesmo
  padrão do `GET /appointments/` no Sprint 27; router passou a depender de `get_current_user`.
  Subquery: `Customer.id IN (SELECT client_id FROM appointments WHERE professional_id = ? AND
  company_id = ?)` — campo é **client_id**, não customer_id.

**HEAD migration:** e0s28_professional_contact_customer_filter

## Vínculo User↔Professional + escopo PROFESSIONAL (2026-06-22)
Backend para o papel PROFESSIONAL ver os próprios dados. **HEAD migration:
`e0s27_professional_user_link`** (← e0s26_multiitem_packages). Branch
`feat/professional-scope-backend`. +19 testes (`tests/test_sprint27_professional_scope.py`).

### Modelo / migration
- `professionals.user_id` FK users(id) ON DELETE SET NULL, **UNIQUE parcial**
  (`uq_professionals_user_id WHERE user_id IS NOT NULL`) — 1:1 opcional.
  `Professional.user = relationship("User", foreign_keys=[user_id])`.
- `user_invitations.professional_id` FK professionals(id) ON DELETE SET NULL — linka no aceite.

### Endpoints / comportamento
- `GET /auth/me` agora retorna `professional_id` (str ou None; só preenchido p/ role=PROFESSIONAL vinculado).
- `GET /professionals/me` (declarado ANTES de `/{professional_id}`): 200 cadastro próprio;
  403 não-PROFESSIONAL; 404 sem vínculo.
- `PATCH /professionals/{id}` aceita `user_id`: UUID vincula (valida tenant + role=PROFESSIONAL;
  400 inválido; 409 se já vinculado a outro), `null` explícito desvincula. Detecção via
  `model_fields_set` (exclude_none descartaria o null). `ProfessionalResponse.user_id` exposto.
- Convite: `InviteUserRequest.professional_id` opcional; persistido na UserInvitation;
  `activate_account` linka `prof.user_id` no aceite (with_for_update + user_id IS NULL).
- `GET /appointments/` ganhou param `professional_id`; **PROFESSIONAL tem o filtro forçado**
  ao próprio cadastro (sem vínculo → lista vazia, serviço nem é chamado).
- `GET /commissions/me` (antes de `/commissions`): comissões do profissional logado;
  403 não-PROFESSIONAL; sem vínculo → `[]`.
- Helper único `professionals/service.get_linked_professional(db, user_id, company_id)`
  reusado por auth/me, professionals/me, appointments e commissions/me.
- **Desvio do enunciado (implementação, não arquitetura):** lookup centralizado no helper
  do service em vez de `db.query(Professional)` inline em cada router (DRY/testável).

**HEAD migration:** e0s27_professional_user_link

## Multi-item packages (2026-06-22)
Pacotes e assinaturas multi-item. **HEAD migration: `e0s26_multiitem_packages`**
(← e0s25f_product_extras). **988 testes** (976 + 12 novos), zero regressões.
Branch `feat/multiitem-packages-backend`, commit `cdc500a`.

### Modelos multi-item
- `package_items`: {package_id, item_type SERVICE|PRODUCT, service_id?, product_id?,
  quantity, display_order} — CHECK chk_package_item_target (exatamente 1 alvo);
  CASCADE delete do pacote pai; FK service/product ON DELETE SET NULL; RLS canônico.
- `plan_items`: mesma estrutura para `subscription_plans`.
- `customer_credits`: ganha `service_id` FK (services) e `product_id` FK (products),
  ambas ON DELETE SET NULL.
- `Package.total_cotas` e `SubscriptionPlan.cotas_per_cycle`: **mantidos como colunas
  derivadas** (= sum items.quantity, sincronizadas na criação) — o bot WhatsApp
  (`comprando_pacote.py`) depende de `total_cotas`. Migration **não** as dropa.
- `service_id` **dropado** de `packages` e `subscription_plans` (substituído por itens).

### Lógica de negócio (multi-item)
- `activate()`: 1 CustomerCredit por PackageItem (service_id/product_id persistidos).
- subscription handler: 1 CustomerCredit por PlanItem por ciclo de renovação.
- `subscribe()`: retorna `(subscription, payment)`; router responde
  `SubscribeResponse {subscription_id, payment_id}`. Cria Payment PENDING
  (provider=manual) no mesmo request (primeiro ciclo). `create_payment()` ganhou
  param `subscription_id` (Payment.subscription_id já existia no modelo).
- `consume_for_operation(... service_id?, product_id?)`: match por service_id (ou
  product_id) se fornecido; senão cota genérica. FEFO + SELECT FOR UPDATE SKIP LOCKED
  preservados. `NoCreditAvailableError` se não há cota para o alvo.
- `find_available_credit()`: busca sem consumir (para o endpoint available-credit).
- Comissão `PACKAGE_SOLD` usa `service_id=None` (pacote multi-item, sem serviço único).
- Eventos `package.purchased`/`subscription.renewed`: `credit_id` → `credit_ids[]`.
- portal `_resolve_credit_service_name()`: lê FK direta (sem cadeia source_id).
- `crm/service.py`: cobertura de pacote migrada para `items[]` (pkg.service_id removido).
- Serialização sem N+1: `_attach_item_names`/`_attach_plan_item_names`/`_attach_credit_names`
  resolvem service_name/product_name em batch e setam atributos transientes (from_attributes).

### Endpoints adicionados
- `GET  /appointments/{id}/available-credit`
  → `{has_credit, credit_id, service_name, remaining_cotas}`.
- `PATCH /appointments/{id}/complete` aceita body `{use_credit: bool = false}`
  (permanece PATCH — preserva contrato existente). `use_credit=true` consome 1 cota
  ANTES da transição; **409** se não há cota disponível para o serviço.

## Dívidas de backend Fases 5A–5B (2026-06-19)
Corrigidas as 6 lacunas de endpoint identificadas no frontend 5A–5B. **Sem migration**
(head `e0s25f_product_extras` preservado). **976 testes** (951 + 25 novos), zero regressões.
Branch `fix/backend-dividas-5a-5b`, commit `4708522`.

### Endpoints adicionados
- `GET  /portal/credits/{credit_id}/consumptions` → `CreditConsumptionOut[]`
  (occurred_at, appointment_id, service_name, professional_name, quantity_used=1).
  404 se crédito inexistente ou de outra identity. Usa **dados reais** —
  `CustomerCreditConsumption` já existia (FK `appointment_id`); era lacuna de endpoint.
- `POST /portal/subscriptions/{subscription_id}/resume` → assinatura atualizada (PAUSED→ACTIVE).
  Reexpõe `subscriptions/service.resume` (já existia no tenant). **Gate `allow_subscription_pause`**:
  pausar/retomar são a MESMA capacidade — se o tenant permite o cliente pausar pelo Portal,
  permite retomar. NÃO significa "resume sempre disponível se PAUSED" — sem o flag → 403.
- `GET  /booking/{slug}/products` → `ProductOptionResponse[]` (público, no `booking_router`,
  path que o frontend `book/[slug]` espera). Só produtos `active`; `available` = stock NULL
  (sem controle) ou stock > 0. 404 slug inválido, 403 se online_booking off.

### Campos adicionados a respostas existentes (portal)
- dashboard/history/credits/subscriptions → `company_name` (lookup em batch
  `Company.id.in_(...)`, sem N+1).
- credits → `service_name`: resolve via `source_id` (PACKAGE→PackagePurchase→Package.service_id;
  SUBSCRIPTION→Plan.service_id → Service.name). **Fallback** por entitlement_type quando a
  cadeia não resolve (pacote/plano genérico com service_id NULL, ou GRANT_COTA):
  PACKAGE→"Pacote", SUBSCRIPTION→"Assinatura", GRANT_COTA→"Cota cortesia". CustomerCredit
  **não tem FK service_id** — limitação de modelo, não de endpoint.
- `GET /portal/history` → parâmetro opcional `status` (422 se fora do universo de Appointment;
  status válido não-histórico, ex. SCHEDULED → lista vazia, não 422).

### Nota para o wiring frontend (aba Produtos)
`price` em `ProductOptionResponse` é **Decimal** (mesmo padrão de `ServiceOptionResponse` no
booking_router), NÃO int centavos. O wiring deve aplicar o MESMO `formatBRL` já usado para
`GET /booking/{slug}/services` — conferir explicitamente, não assumir.

## Estado final — Estágio 0 conforme (2026-06-13, pré-push)
Análise de conformidade plano vs. código: **`docs/conformidade-estagio-0.md`**. Os 15 sprints
(`I → 18 → 17 → 16 → E → B → A → D → C → G → H → 2.0 → 2.6 → 2.7 → 25`) estão implementados e
verificados em código: migration + módulo + router em `main.py` (44 routers) + handlers no
lifespan (12 grupos, incl. `register_deposit_handlers`) + workers no beat_schedule. Cadeia
Alembic **linear, head único `e0s25f_product_extras`** (sem multi-head). Suite: **951 passed,
6 skipped, 1 xfailed** (zero regressões). `tests/contract/` (7 contratos) verde.
- **Veredicto: pronto para push com ressalvas operacionais** (não são bug de código):
  1. Vars Railway — `SECRET_KEY` ainda é `"troque-em-producao"` (TROCAR); configurar
     `CREDENTIAL_ENCRYPTION_KEY`, `EMAIL_PROVIDER`+chave real, `LLM_API_KEY` (vazio → sem LLM,
     só regex), `FRONTEND_BASE_URL`, `ASAAS_API_URL` de produção. Checklist na Seção 8 do relatório.
  2. `scripts/backfill_identity.py` pronto mas **NÃO executado** (janela de manutenção, antes de crescer a base).
  3. Templates `appointment.completed` (Sprint I) + 5 do Sprint G via SQL para tenants antigos.
  4. PagSeguro Point continua bloqueado (stubs não confirmados).
- **Único DoD não cumprido (não bloqueador, Estágio 1+):** eixos CUSTOM de comissão
  (`professional_share`/`prior_commission_share`/`use_net_of_discount`) não existem no schema.
- Nenhum desvio não documentado de impacto; nenhum bloqueador de segurança/dados/contrato de API.

## Sprint 25 — Schema-only Estágio 1+ + suite de contrato + DEPOSIT (2026-06-13)
- **6 migrations schema-only em cadeia** (← e0s27a), SEM endpoint/service/tela —
  apenas estruturas para o Estágio 1+, RLS canônico `app.current_company_id`:
  `e0s25a_locations` (multi-unidade) → `e0s25b_stock_batches` (FEFO/lotes) →
  `e0s25c_encomenda` (encomenda_orders + encomenda_items, FSM em VARCHAR) →
  `e0s25d_operation_professionals` (multi-profissional, UNIQUE appt+prof) →
  `e0s25e_service_input_checklists` (insumos por serviço) →
  `e0s25f_product_extras` (products.barcode + products.location_id FK locations
  ON DELETE SET NULL; índice parcial idx_products_barcode).
  **HEAD migration: e0s25f_product_extras** (próxima down_revision).
- **Wiring DEPOSIT** (`modules/payments/deposit_service.py`) — conecta primitivas
  que existiam isoladas, SEM nova coluna de schema:
  - `resolve_deposit_policy` (service-specific → global) + `compute_deposit_amount`
    (FIXED_AMOUNT | PERCENTAGE, nunca > total).
  - `create_deposit_payment`: Payment PENDING (provider=manual) vinculado ao
    appointment; no-op sem DepositPolicy.
  - `payment.confirmed` → `deposit_handler` promove Reservation **SOFT→FIRME**
    (vínculo pelo slot: professional + start/end, pois Payment não referencia
    Reservation). Registrado no lifespan (`register_deposit_handlers`).
  - `complete_appointment` → `recognize_balance_on_completion`: saldo restante
    (total − sinal confirmado) → `financial_core.handle_deposit_balance_recognized`
    (Movement INFLOW + Entry RECEITA/SERVICOS). No-op sem pagamento parcial.
  - `mark_no_show` (nova função em appointments/service) → `handle_no_show_deposit`:
    retém se `retain_on_no_show` (default True); estorna se False. Sinal retido
    **NÃO gera comissão** salvo `commission_on_retained_deposit` (default False).
  - `cancel_appointment` → `handle_cancellation_deposit`: refund dentro da janela
    (`is_within_refund_window`: now ≤ start − refundable_until_hours_before),
    retenção fora dela. Todas as chamadas no lifecycle são **best-effort
    pós-commit** (try/except logado) — no-op sem DepositPolicy → zero regressão.
- **Suite de contrato `tests/contract/`** (7 contratos, 54 testes SQLite/FakeDB +
  2 gated → **56 verdes contra PostgreSQL real**). `conftest.py`: FakeDB que
  avalia critérios reais do SQLAlchemy (eq/ne/is/ge/le/gt/lt/in_/notin_), `options`
  passthrough, e `execute` mínimo replicando `processed_idempotency_keys`.
  `requires_postgres` = skipif sem DATABASE_URL.
  - C1 FSM (estados REAIS — não DRAFT/REQUESTED/CONFIRMED do enunciado);
    C2 conflito (`_assert_slot_available` + EXCLUDE constraint real);
    C3 DEPOSIT (deposit_service ponta a ponta); C4 comissão dois eixos
    (BARBERSHOP_PAYS=40,00 / SPLIT_50_50=38,50 / BARBER_PAYS=37,00);
    C5 idempotência (mecanismo is_processed/mark_processed + guarda de domínio
    do commission_handler via SessionLocal monkeypatched); C6 DRE; C7 multi-tenant
    (+ RLS real gated).
- **GAP documentado (Estágio 1+, não bloqueador):** eixos CUSTOM de comissão
  (`professional_share`, `prior_commission_share`, `use_net_of_discount`) **não
  existem** no modelo `commission_policies`. O modelo tem `commission_base`
  (GROSS_SERVICE|NET_SERVICE|GROSS_OPERATION|CUSTOM_AMOUNT) e
  `commission_fee_policy` (BARBERSHOP_PAYS|SPLIT_50_50|BARBER_PAYS; legado
  BEFORE_FEES|AFTER_FEES). Implementar os eixos CUSTOM é trabalho de Estágio 1+.
- Sem migração de dados (apenas wiring de lógica). Suite completa: 951 passed,
  6 skipped, 1 xfailed (zero regressões).

**HEAD migration:** e0s25f_product_extras

## Sprint 2.7 — Inbox de atendimento humano + estado RESOLVIDA (2026-06-13)
- Migration `e0s27a_conversation_messages` (HEAD ← e0s20a): tabela
  `conversation_messages` (RLS canônico) — id, company_id FK, session_id FK
  bot_sessions, direction (INBOUND|OUTBOUND), content, content_type, sender_type
  (CLIENT|BOT|AGENT), agent_user_id FK users nullable, whatsapp_message_id,
  created_at. Índices (session_id, created_at ASC) e (company_id, created_at DESC).
  A migration também faz **seed idempotente** do template conversation.escalated
  (WHATSAPP+EMAIL, OWNER) para tenants existentes (padrão g1h2i3j4k5l6).
- **STATE_RESOLVIDA** (bot_service.py): marcador terminal. `resolve` seta RESOLVIDA;
  o dispatcher consome RESOLVIDA na próxima mensagem → reset_session(keep_customer)
  + MENU_PRINCIPAL + show_menu_principal (**bot reassume, não silencia**). Permite
  `GET /conversations?status=resolved` listar conversas resolvidas por estado.
- bot_service: `_persist_message` (best-effort, db.add+flush), `_escalate_to_human`
  centraliza os 2 gatilhos de escalada (comando universal "humano"/"atendente"/
  "ajuda"/"suporte" + intenção FALAR_COM_HUMANO): persiste INBOUND do gatilho →
  state=HUMANO → envia+persiste HUMANO_CHAMADO (OUTBOUND BOT) → publica
  conversation.escalated. Branch STATE_HUMANO **agora persiste INBOUND CLIENT** e
  silencia (antes era `pass`). BotSession **não tem coluna customer_id** — vem de
  `session.context["customer_id"]`.
- `conversation.escalated` (trigger=INTENT|MENU) → handler
  `workers/handlers/conversation_handler.py` notifica OWNER via
  CommunicationService (template conversation.escalated). Registrado no lifespan.
  `conversation.resolved` publicado no resolve (best-effort).
- `modules/conversations/` — service + router `/conversations` (RBAC
  OWNER/ADMIN/OPERATOR em TODOS): GET / (status=escalated|resolved), GET /{id},
  GET /{id}/messages (asc), POST /{id}/reply (422 se != HUMANO; envia via
  sender.send_text resolvendo instance via WhatsAppConnection.company_id; persiste
  OUTBOUND AGENT), PATCH /{id}/resolve. Isolamento cross-tenant: sessão precisa
  pertencer ao company_id → 404.
- Template conversation.escalated (WHATSAPP+EMAIL, OWNER) em _DEFAULT_TEMPLATES.
  ⚠ Tenants pré-2.7: já cobertos pelo seed da migration (não precisa SQL manual).
- messages.ATENDIMENTO_ENCERRADO nova.
- Testes: tests/test_sprint27_inbox.py (12 testes, FakeDB com filtros reais +
  order_by funcional; dispatcher via handle_inbound_message async).

**HEAD migration:** e0s27a_conversation_messages


## Sprint 2.6 — ChainClassifier integrado ao FSM + compras (2026-06-13)
- **Sem migration** — estados novos usam a coluna `bot_sessions.state` existente.
  HEAD permanece `e0s20a_intent_classifications`.
- `bot_service._classify_and_route()`: texto livre em **INICIO/MENU_PRINCIPAL**
  (cliente já identificado + input que não casa com opção do menu) → ChainClassifier
  sugere; o FSM decide (invariante 1). Bloco roda APÓS comandos universais e só
  para esses dois estados; `resolve_input(...) is None` garante que cliques de
  botão não acionam o classificador (B6 — estados guiados por menu preservados).
  Erro do classificador é capturado e cai no menu (não quebra o bot).
- `INTENT_TO_STATE` (7 intenções). Roteamento real:
  AGENDAR→ESCOLHENDO_SERVICO · CONSULTAR→VER_AGENDAMENTOS ·
  FALAR_COM_HUMANO→HUMANO · COMPRAR_PRODUTO/PACOTE→fluxo de compra.
  **CANCELAR** (`_route_cancelar`): 0 agendamentos→menu; **1→auto-seleciona e entra
  em CANCELANDO**; >1→VER_AGENDAMENTOS. **REMARCAR** (`_route_remarcar`)→sempre
  VER_AGENDAMENTOS (cliente escolhe e gerencia — REAGENDANDO exige agendamento).
- **`is_universal_command` não trata mais "cancelar" como menu** — virou intenção
  CANCELAR. Abortar fluxo continua via `0/menu/início/voltar/sair`.
- Módulo inativo: ChainClassifier converte intenção fora do catálogo em FALLBACK
  (sem mensagem). `_inactive_module_intent()` faz regex SEM filtro sobre ALL_INTENTS
  e, se o texto pede produto/pacote com módulo desligado, envia `RECURSO_INDISPONIVEL`
  em vez de só reexibir o menu.
- **PRODUCT×SALE NÃO criado como Operation/Appointment** — `Appointment` exige
  profissional+horário; o plano prevê "sem migration". A venda via bot é
  representada pela primitiva real: **Payment (manual/CASH) + StockMovement VENDA**
  (Sprint 17). `StockMovement.created_by` é NOT NULL → bot resolve o **OWNER** do
  tenant como ator; sem owner, registra o Payment e pula a baixa (best-effort logado).
  Checa estoque antes de cobrar (mensagem amigável se insuficiente).
- `handlers/comprando_produto.py`: ESCOLHENDO_PRODUTO (stock>0, list se >3 / botões
  se ≤3, máx 10) → CONFIRMANDO_QUANTIDADE_PRODUTO (parse de inteiro) →
  CONFIRMANDO_PRODUTO ([Confirmar]/[Cancelar]) → `_finalize` (Payment + StockMovement).
- `handlers/comprando_pacote.py`: ESCOLHENDO_PACOTE (is_active) → CONFIRMANDO_PACOTE
  → `_finalize` reutiliza `packages.purchase(seller_user_id=None, payment_method=CASH)`
  → PackagePurchase PENDING_PAYMENT + Payment PENDING.
- Testes: tests/test_sprint26_bot_integration.py (12 testes, FakeDB + serviços
  monkeypatched — não exercita webhook async nem Postgres).

**HEAD migration:** e0s20a_intent_classifications

## Sprint 2.0 — IntentClassifier isolado (2026-06-13)
- Migration `e0s20a_intent_classifications`: tabela append-only
  `intent_classifications` (RLS canônico) — toda classificação (REGEX | LLM |
  FALLBACK) é persistida, sem dedup. Colunas: confidence NUMERIC(4,3),
  entities JSONB, llm_provider/llm_model/llm_latency_ms (NULL fora de LLM)
- Novo pacote `modules/whatsapp/intent/` — **ZERO integração com
  bot_service.py ou handlers/** (deferido ao Sprint 2.6)
  - `schemas.py`: `IntentResult` (intent, confidence, entities, source,
    raw_input), `FALLBACK_INTENT="MENU_PRINCIPAL"`, `CONFIDENCE_THRESHOLD=0.7`
  - `catalog.py`: `ALL_INTENTS` (7 intenções), `INTENT_MODULE_REQUIREMENTS`
    (COMPRAR_PRODUTO→ESTOQUE, COMPRAR_PACOTE→PACOTES — valores reais do enum
    `modulename`, não placeholders em inglês), `get_active_intents()` —
    catálogo dinâmico por tenant (FALAR_COM_HUMANO sempre ativo)
  - `regex_classifier.py`: `RegexClassifier` — confidence 0.9 (padrão
    específico) / 0.75 (genérico) / 0.0+MENU_PRINCIPAL (sem match); filtra
    por `active_intents`; ordem CANCELAR > REMARCAR > CONSULTAR >
    COMPRAR_PRODUTO > COMPRAR_PACOTE > FALAR_COM_HUMANO > AGENDAR
  - `llm_classifier.py`: `LLMClassifier` (Anthropic Claude Haiku 4.5, tool use
    forçado — nunca texto livre; timeout 5s; qualquer falha → FALLBACK) +
    `NullLLMClassifier` (test double, `NULL_LLM_OUTCOME=fallback|agendar|
    falar_com_humano`, nunca chama API externa)
  - `classifier.py`: `ChainClassifier` — regex primeiro; LLM só se
    confidence < 0.7; resultado fora do catálogo ativo → MENU_PRINCIPAL;
    persiste 100% das classificações; `known_intents` property
- Modelo ORM `IntentClassification` em
  `infrastructure/db/models/intent_classification.py`
- `LLM_PROVIDER`/`LLM_MODEL`/`LLM_API_KEY`/`LLM_TIMEOUT_SECONDS` em config.py
  (defaults: anthropic / claude-haiku-4-5 / "" / 5.0)
- `anthropic==0.69.0` adicionado ao requirements.txt
- Testes: tests/test_sprint20_intent_classifier.py (9 testes, FakeDB
  in-memory) — cobre os 7 casos do DoD + invariantes 1/2/3/5
- Ver decisão de provider LLM no commit "docs: escolha de provider LLM para
  Sprint 2.0"

**HEAD migration:** e0s20a_intent_classifications

## Sprint H — CRM básico (2026-06-12)
- Migration `e0sH1_crm`: crm_configs (thresholds 1:1 por tenant),
  customer_classifications (APPEND por recomputação — histórico preservado;
  atual = linha mais recente via idx_customer_classifications_current),
  customers.custom_fields JSONB (notes já existia — IF NOT EXISTS). RLS canônico.
- `modules/crm/service.py`: compute_customer_metrics (dinâmico, ZERO persistência
  — visita = Appointment COMPLETED; gasto = Payment CONFIRMED net_charged_amount;
  FK é client_id), classify_customer (puro/determinístico, prioridade
  VIP > RECUPERADO > EM_RISCO > FREQUENTE > NOVO > REGULAR; EM_RISCO usa
  max(risk_min_days, avg_freq × risk_multiplier); RECUPERADO = previous EM_RISCO
  e não está mais em risco), recompute_all_classifications (insere se mudou OU
  última > 24h; commit em lote a cada 100), get_customer_insights (heurísticas
  SEM ML: churn_risk HIGH=EM_RISCO / MEDIUM=days>avg×1.5; RESCHEDULE = cancel
  < 7d sem SCHEDULED; PACKAGE = mesmo serviço 3×/60d sem purchase ACTIVE que
  cubra — pacote sem service_id é genérico e cobre qualquer um; PRODUCT = mais
  vendido em VENDA com source_id nos appointments do serviço preferido),
  get_crm_alerts (dedupe pela linha mais recente por customer)
- Filtros de status/escopo aplicados em Python sobre a query company+customer
  (compatível com FakeDB; volumes por cliente são pequenos)
- Rotas: /crm/alerts (OWNER/ADMIN), /crm/classifications (filtros
  classification+date_from), /crm/config GET (OPERATOR ok) / PUT (só OWNER);
  /customers/{id}/insights e /customers/{id}/classification (última + 5)
  com require_role — PATCH /customers/{id} pré-existente ganhou custom_fields
- Worker beat: crm-recompute-classifications (03:00) —
  workers/tasks/crm_recompute.py aceita company_id opcional p/ forçar 1 tenant
- SEM ML/IA; SEM sugestão automática ao cliente (deferidos pela visão)
- Testes: tests/test_sprint_h_crm.py (30 testes + 1 skip celery-ausente-no-venv,
  FakeDB in-memory)

**HEAD migration:** e0sH1_crm

## Sprint G — NPS + Fila de espera (2026-06-12)
- 2 migrations: `e0sG1_nps` (nps_configs 1:1 por tenant; nps_surveys
  PENDING|SENT|RESPONDED|EXPIRED com UNIQUE(appointment_id) — idempotência;
  nps_responses UNIQUE(survey_id), CHECK score 0–10) → `e0sG2_waitlist`
  (waitlist_configs 1:1; waitlist_entries com CHECK check_waitlist_scope —
  exatamente 1 de service_id/professional_id/product_id conforme scope_type).
  RLS canônico em todas.
- **NPS dispara APENAS após operation.completed** — handler
  `workers/handlers/nps_handler.py` (idempotência dupla:
  processed_idempotency_keys "nps.schedule:{appointment_id}" + UNIQUE no banco)
- payload de operation.completed ganhou `customer_id` (transitions.py);
  handler tem fallback que resolve via Appointment.client_id p/ eventos antigos
- `modules/nps/service.py`: schedule (delay + min_interval_days por cliente),
  send_pending (worker — dispatch trata consent/quiet hours; SCHEDULED conta
  como sucesso; SKIPPED_CONSENT_REVOKED → survey EXPIRED; FAILED → retry),
  expire (48h), record_response (público — survey_id é o token; só SENT → 422
  caso contrário), add_tenant_response (nunca edita score — só adiciona)
- Nota baixa (score <= low_score_threshold): publica nps.low_score_alert +
  dispatch best-effort ao OWNER (User role=OWNER ativo; sem phone em User →
  template EMAIL audience OWNER cobre; WHATSAPP existe mas falha sem phone)
- **Slot liberado é implícito no domínio** — Sprint G adicionou
  `_publish_slot_released` em appointments/service.py: cancel_appointment →
  appointment.cancelled, reschedule_appointment → appointment.rescheduled
  (best-effort, pós-commit, payload com service_ids[] + professional_id)
- stock.entry_recorded payload ganhou `product_ids[]` (stock/service.py)
- `modules/waitlist/service.py`: join (dup mesmo escopo → 409; operação ativa
  equivalente → 422), notify_waitlist (priority DESC + created_at ASC;
  PULA cliente com operação ativa e consent revogado; notifica APENAS o 1º
  elegível — não reserva slot), expire (NOTIFIED vencida → EXPIRED + notifica
  próximo). "Operação ativa" = Appointment SCHEDULED|IN_PROGRESS (não existe
  CONFIRMED no enum); escopo PRODUCT nunca tem operação equivalente
- Handlers em `workers/handlers/waitlist_handler.py`: appointment.cancelled,
  appointment.rescheduled, stock.entry_recorded — registrados no lifespan
- Workers beat: nps-send-pending (*/15), nps-expire-surveys (01:00),
  waitlist-expire-entries (*/30)
- Rotas: /nps/config (GET/PUT), /nps/surveys (lista/detalhe/respond tenant),
  POST /nps/respond/{survey_id} PÚBLICO rate limit 3/min;
  /waitlist/config (GET/PUT), /waitlist/entries (GET/POST/DELETE)
- nps.survey_request e waitlist.slot_available adicionados a
  _QUIET_HOURS_SCHEDULED_EVENTS (quiet hours → SCHEDULED, drain envia depois)
- 5 templates novos em _DEFAULT_TEMPLATES. ⚠ Tenants pré-Sprint G não os têm —
  inserir via SQL (mesmo caveat do Sprint I)
- Testes: tests/test_sprint_g_nps_waitlist.py (35 testes, FakeDB in-memory)

**HEAD migration:** e0sG2_waitlist

## Sprint C — Painel Owner Paladino (2026-06-12)
- 3 migrations: `e0sC1_tenant_status` (companies.status TRIAL|ACTIVE|SUSPENDED|
  CHURNED, default ACTIVE) → `e0sC2_impersonation_grants` (tabela de PLATAFORMA
  sem RLS; quase-append-only: trigger bloqueia DELETE e qualquer UPDATE que não
  seja revogação revoked_at NULL→valor) → `e0sC3_platform_settings` (key/value
  JSONB global, sem RLS, acesso só via service layer)
- **Suspensão bloqueia login**: check em `auth/service.py::authenticate` após
  credenciais — company.status==SUSPENDED → 403; PLATFORM_OWNER
  (company_id=None) nunca passa pelo check
- `app/middleware/impersonation.py` — ImpersonationMiddleware (header
  `X-Impersonate-Grant: {grant_id}`): valida JWT PLATFORM_OWNER + grant ativo +
  dono do grant; injeta request.state.{impersonating, impersonation_grant,
  effective_company_id}; audita CADA request impersonada em audit_logs com
  action="impersonated_request", resource_type="ImpersonationGrant",
  resource_id=grant_id, company_id=tenant (audit_logs NÃO ganhou coluna nova).
  READ_ONLY bloqueia métodos != GET/HEAD/OPTIONS já no middleware (defesa
  dupla com a dependency `require_not_read_only`)
- `modules/platform/` — service + router `/platform/*` (TODOS exigem
  require_role("PLATFORM_OWNER")): tenants (list/get/health/PATCH status),
  impersonation grants (POST/DELETE/GET — ELEVATED exige reason ≥20 chars,
  default 30min), flags por tenant (permission_overrides — reatribuição, não
  mutação in-place do JSONB), platform settings (upsert), GET /platform/audit
  (acesso auditado com action="platform_audit_access" ANTES de retornar —
  RBAC-4), redispatch
- **Redispatch (D7)**: só logs FAILED; CommunicationLog NÃO persiste context →
  re-renderizar via dispatch() é impossível — re-envia rendered_body direto
  pelo canal (padrão drain_scheduled); cria NOVO log (original intocado)
- `GET /audit/impersonation-accesses` (audit/router.py): tenant vê acessos
  impersonados do próprio company_id; PLATFORM_OWNER → 403 (usa /platform/audit)
- Notificação de suspensão ao OWNER do tenant: email DIRETO
  (`modules/platform/emails.py`, padrão _send_reset_email_direct) — evento de
  plataforma não passa pelo CommunicationService do tenant; best-effort
- Testes: tests/test_sprint_c_platform.py (33 testes, FakeDB in-memory)

**HEAD migration:** e0sC3_platform_settings

## Sprint D — Portal do Cliente (2026-06-12)
- 2 migrations: `e0sD1_portal_auth` (portal_credentials UNIQUE por identity e
  por email, password_hash NULLABLE — magic-link-only; portal_magic_tokens
  com SHA-256 do token, cru NUNCA persiste — padrão Sprint B) →
  `e0sD2_payment_source_authorizations` (UNIQUE identity+company+token,
  mode ALWAYS|ONCE). Tabelas GLOBAIS sem company_id — RLS HABILITADO SEM
  POLICY (padrão e0sA1); acesso só via service layer
- **JWT portal** (`modules/portal/auth_service.py`): claims
  `{sub: identity_id, type: "portal", iat, exp 24h}` — SEM company_id.
  `verify_portal_token` rejeita type != "portal" → 401.
  `get_current_user` (deps.py) rejeita EXPLICITAMENTE payload com claim
  `type` (JWT portal nunca autentica em endpoint tenant — antes do lookup)
- `get_current_portal_identity` em core/deps.py → PaladinoIdentity
- Auth: register (resolver por telefone — 422 sem DDD; identity existente →
  has_existing_history=true = adoção de histórico), login email+senha,
  magic link (15min, single-use, endpoint sempre 200 — não revela email).
  Email enviado DIRETO (Mailtrap HTTP/SMTP, padrão _send_reset_email_direct)
  — identity é global, CommunicationService.dispatch exige company_id
- Rotas `/portal/*`: dashboard/history/credits/subscriptions cross-tenant
  (identity → customers.identity_id → dados tenant-scoped); pause/cancel de
  assinatura com config do tenant; consents (source=PORTAL); payment-sources
  exigem consent PAYMENT_STORAGE (422); PATCH profile (phone re-resolve —
  E.164 de outra identity → 409; email novo → email_verified=false +
  verificação); GET /portal/identity/me e /identity/me (501 do Sprint A
  resolvido — ambos usam o dependency portal)
- B5: `allows_subscription_pause` (default False) /
  `allows_subscription_cancel` (default True) em modules/tenant/service.py
  via permission_overrides — SEM migration de coluna
- Asaas NÃO tem tokenização de cartão no adapter — POST /portal/payment-sources
  recebe source_token já tokenizado; tokenização no provider fica p/ sprint futura
- Tabela legada payment_sources (tenant-scoped) NÃO foi tocada
- Testes: tests/test_sprint_d_portal.py (48 testes, FakeDB in-memory)

**HEAD migration:** e0sD2_payment_source_authorizations

## Sprint A — Identidade Paladino (2026-06-12)
- 3 migrations em cadeia: `e0sA1_paladino_identities` (tabela GLOBAL sem
  company_id — RLS HABILITADO SEM POLICY, intencional; acesso só via service
  layer) → `e0sA2_consent_records` (append-only, trigger
  consent_records_no_update no banco; company_id NULL = consent global) →
  `e0sA3_customers_identity_link` (customers.identity_id nullable + índice
  parcial; backfill via script, NÃO na migration)
- `modules/identity/resolver.py` — PhoneIdentityResolver:
  normalize_phone_e164 ESTRITA (DDD obrigatório → 422; insere 9º dígito como
  customers/service.normalize_phone — decisão: SEM phonenumbers, a lib não
  insere o 9 e duplicaria identidades); resolve() create-if-new idempotente;
  resolve_for_tenant() → (customer, is_new) com lazy-link de identity_id NULL
- phone_e164 com '+' na identity; customers.phone continua SEM '+' (convenção)
- `modules/identity/consent_service.py` — append-only; check_consent:
  COMMUNICATION default True (opt-out), MARKETING/demais default False;
  channel NULL vale p/ todos os canais; company_id NULL = global
- Integrações: create_customer (PAINEL, não-fatal se telefone sem DDD),
  bot aguardando_nome (BOT) e public_book (LINK) usam resolver + consent
  GRANTED na criação; inicio.py faz lazy backfill no primeiro contato
- dispatch() passo 4: consent verificado p/ CLIENT no canal escolhido →
  SKIPPED_CONSENT_REVOKED; sem identity_id (UUID real) → envia (fallback
  transacional); event_type `marketing.*` → ConsentType.MARKETING e
  BLOQUEIA sem identity
- Rotas: GET/POST /customers/{id}/consents[/grant|/revoke] (writes
  OWNER/ADMIN, source=PAINEL); GET /identity/me → 501 até Sprint D
- `scripts/backfill_identity.py` (--dry-run): agrupa por E.164, colisões de
  nome → mais recente + backfill_collision_report.csv; idempotente;
  **NÃO executado — operação de produção com janela de manutenção**
- Testes: tests/test_sprint_a_identity.py (32 testes, FakeDB in-memory)

**HEAD migration:** e0sA3_customers_identity_link

## Sprint B — Link de gestão com token único (2026-06-11)
- `appointments.manage_token_hash` (SHA-256; cru NUNCA persiste) +
  `manage_token_expires_at` (= start_at) + índice único parcial —
  migration `e0sB1_appointment_manage_tokens`
- `modules/appointments/manage_tokens.py`: issue_manage_token (gera UUID4 cru,
  persiste hash), hash_token, invalidate_manage_token, build_manage_url
  (FRONTEND_BASE_URL, vazio → fallback FRONTEND_URL)
- Token gerado em create_appointment E reschedule_appointment (novo token
  invalida o anterior); cru vai só na mensagem via context {{manage_url}}
  (template appointment.confirmed CLIENT ganhou "Para remarcar ou cancelar: …")
- `modules/public/manage_router.py` + `manage_service.py` — público, sem JWT:
  GET /manage/{token} (10/min) · POST cancel (5/min) · POST reschedule (5/min)
- **404 genérico SEMPRE** p/ token inválido/expirado/terminal (nunca 401/403)
- **Janela decide CONSEQUÊNCIA, não permissão**: cancel via link usa
  skip_policy=True; DepositPolicy (service-specific → global) + Payment
  CONFIRMED no appointment → fora da janela cancela E deposit_retained=true
  (retenção é informativa — refund continua manual/OWNER)
- transitions.py: transição p/ estado terminal zera manage_token_hash/expires
- Reschedule: 409 de conflito → 422 no contrato público
- Tenants pré-Sprint B: appointments existentes sem token (manage_url vazio
  na mensagem) — só novos agendamentos ganham link
- Testes: tests/test_sprint_b_manage_token.py (21 testes)

**HEAD migration:** e0sB1_appointment_manage_tokens

## Sprint E — ExternalStatementEntry (2026-06-11)
- Tabela `external_statement_entries` (RLS canônico) — migration
  `e0sE1_external_statement_entries`; UNIQUE (company_id, line_hash)
  garante idempotência de re-upload (line_hash = SHA-256 da linha crua)
- `modules/financial_core/statement_service.py`: import_csv, suggest_match,
  confirm_match, dismiss_entry, list_statement_entries, list_batches
- `modules/financial_core/statement_router.py` (prefixo /financial/statement,
  registrado em main.py): POST /import (multipart: file + account_id +
  column_mapping JSON), GET /, GET /batches, GET /{id}/suggestions,
  POST /{id}/match, POST /{id}/dismiss
- **Movement NUNCA é alterado** — vínculo unidirecional em
  entry.matched_movement_id (append-only preservado)
- `auto_matched` no import = entries com candidato encontrado; é APENAS
  sugestão — nada persiste como MATCHED (confirmação manual via /match)
- Match: mesmo account, |amount| ±0.01, occurred_at ±2 dias, direção
  compatível (INFLOW→INFLOW/TRANSFER_IN), movement não casado; critérios
  revalidados em Python (defesa em profundidade + testável com mocks)
- direction inferido pelo sinal do valor (negativo → OUTFLOW) ou coluna
  explícita (D/DEBIT/SAIDA → OUTFLOW); amount armazenado sempre positivo
- dismiss: reason obrigatório (422); só entries PENDING (422); audit completo
- **Primeiro uso real de `require_action()`** (deps.py): writes exigem
  OWNER/ADMIN; OPERATOR só com permission_overrides["OPERATOR"]["statement_*"]
  (actions: statement_import, statement_match, statement_dismiss)
- Eventos: statement.batch_imported / entry_matched / entry_dismissed
- Testes: tests/test_sprint_e_statement.py (30 testes)

**HEAD migration:** e0sE1_external_statement_entries

## Sprint 16 — Promoções e Cupons (2026-06-11)
- Tabelas `promotions`, `coupons`, `coupon_redemptions`, `discount_applications`
  (RLS canônico) + `payments.coupon_code` — migration `e0s16a_promotions_coupons`
  ⚠ `discount_applications.promotion_id` é NULLABLE (manual-discount usa NULL)
  ⚠ `manual_override_count` já existia desde w1x2y3z4a5b6 — não recriado
- `modules/promotions/service.py`:
  `compute_preview()` ZERO efeito colateral; `effectuate()` revalida tudo com
  SELECT FOR UPDATE em coupons.uses_count; `revert_for_refund()` no refund
- Seleção: exclusivas (cumulative=false) → a de maior desconto
  (CUSTOMER_FAVORABLE); cumulativas em priority DESC sobre o residual
- Revalidação falhou (modo STRICT) → publica `promotion.effectuation_failed`,
  NÃO bloqueia o pagamento (decisão de produto — supersede "refund automático"
  do DoD original do plano)
- `promotion_payment_handler`: 5º listener de payment.confirmed
  (+ payment.refunded para reverter redenções); registrado no lifespan
- payload de payment.confirmed agora inclui `coupon_code`
- `create_payment(coupon_code=...)`: aplica preview na criação —
  net_charged_amount nasce com desconto → Entry RECEITA reflete o líquido
  (desconto reduz receita no DRE; NÃO existe categoria DESCONTO)
- `POST /payments/{id}/manual-discount` (OWNER/ADMIN): reason obrigatório,
  só PENDING, audit `manual_discount_override`, manual_override_count++
- Rotas `/promotions` (CRUD + activate/pause/cancel + /preview + /coupons)
- Worker `promotions_expiry_scanner` (00:05): Promotion ACTIVE vencida →
  EXPIRED; Coupon ACTIVE vencido → CANCELLED
- `coupon_reopen_policy`: NEVER_REOPEN (default) | REOPEN_ON_REFUND
- Testes: tests/test_sprint16_promotions.py (27 + 1 skip PostgreSQL)

**HEAD migration:** e0s16a_promotions_coupons

## Sprint 18 — Despesas + recorrência (2026-06-11)
- Modelo `Expense` (tabela `expenses`, RLS padrão `app.current_company_id`):
  lifecycle PENDENTE → PAGA | CANCELLED; categoria validada contra
  `DESPESA_CATEGORIES` (derivado de entry_category.py — CUSTO → 422)
- `handle_expense_paid` em financial_core/service.py: Movement OUTFLOW +
  Entry DESPESA atômicos (flush sem commit, padrão handle_payment_confirmed);
  resolve conta `is_default_inflow` se account_id não informado
- Recorrência MONTHLY em JSONB (`recurrence_rule`) com clamp de fim de mês
  (`next_occurrence` usa dateutil.relativedelta); instâncias encadeadas via
  `parent_expense_id`; geração FORA da transação de pagamento (falha não
  desfaz o pagamento); `generate_next_instance` idempotente
- `supplier_id` UUID SEM FK — Sprint 17 adiciona a FK via ALTER TABLE
- Rotas `/expenses/` (POST, GET, GET/{id}, PATCH/{id}/pay, PATCH/{id}/cancel)
- Workers: `expense_due_soon` (07:30, janela 3 dias, também publica
  expense.overdue; dedup via processed_idempotency_keys) e
  `expense_recurrence` (06:00) no beat_schedule
- Eventos: expense.created/due_soon/overdue/paid/cancelled com keys canônicos
- ⚠ Categorias da visão FOLHA_PAGAMENTO/IMPOSTOS/OUTROS_DESPESAS não existem
  no enum — usar SALARIO/DESPESA_OUTROS (entry_category.py é fonte de verdade)
- python-dateutil==2.9.0.post0 explicitado no requirements.txt
- Testes: tests/test_sprint18_expenses.py (28 testes)

**HEAD migration:** e0s18a_expenses

## Sprint I — Dívidas críticas (2026-06-11)
- `refund()`: gateway ANTES da contabilidade; falha do provider → HTTP 502, nenhum Movement/Entry
- `force_local=true` no POST /payments/{id}/refund: apenas OWNER (403 p/ ADMIN);
  reason obrigatório (422); audit action `refund_payment_forced_local`
  com after_snapshot {"force_local": true, "note": "estorno forçado sem gateway"}
- NullProvider.refund(): env var `NULLPROVIDER_REFUND_OUTCOME=success|error` (default success)
- Chamadas diretas `evolution_client.send_text` de NOTIFICAÇÃO removidas:
  notifications.py, reminder_worker.py, appointments/router.py (pós-atendimento)
  → tudo via CommunicationService.dispatch; CommunicationLog captura 100% dos envios
  Bot conversacional (whatsapp/sender.py + handlers) fora do escopo — é diálogo FSM, trilha 2.6/2.7
- Flag `use_communication_service`: agora kill-switch — ausente → **True**
  (`overrides.get("use_communication_service", True)` em todos os pontos)
- Template novo `appointment.completed` (WHATSAPP/CLIENT) em _DEFAULT_TEMPLATES.
  ⚠ Tenants criados ANTES do Sprint I não têm esse template — inserir via SQL
  para manter a mensagem de pós-atendimento (sem template → SKIPPED_NO_TEMPLATE)
- Email plugável: `EMAIL_PROVIDER=mailtrap|sendgrid|smtp` (default mailtrap);
  `modules/communication/email_adapters.py` (EmailAdapter ABC + Mailtrap + SendGrid);
  credencial ausente → fallback SMTP (credencial tenant → SMTP_* global)
- reminder_worker: flags reminder_*_sent só marcados quando dispatch != FAILED
  (FAILED → retry no próximo scan da janela)

## Canal EMAIL — CommunicationService (Sprint 11)
- `_send_email()` em `modules/communication/service.py` via smtplib nativo (síncrono)
- `dispatch()` tenta EMAIL primeiro (se email_enabled=True), fallback WHATSAPP
  Usa `is True` para checar bool (seguro com MagicMock nos testes)
- Credencial SMTP: IntegrationCredential provider=SMTP (decrypt_secret para senha);
  config JSONB: {"host", "port", "from_email", "use_tls"} — fallback para SMTP_* de settings
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL, SMTP_USE_TLS em config.py
- Template auth.password_reset_requested channel=EMAIL audience=CLIENT adicionado em _DEFAULT_TEMPLATES
- forgot_password(): recipient_type="CLIENT", context inclui recipient_email + token
- recipient_email obrigatório no context para envio EMAIL
- Testes: tests/test_smtp_email.py (14 testes — todos passando)

## Operations FSM + Agenda granular (Sprint 10 concluído)
- Reservation SOFT/FIRME: EXCLUDE tstzrange WHERE status='ACTIVE'
- promote_to_firme: PROMOTED + db.flush() + INSERT FIRME (atômico)
- expire_soft_reservation: Celery (crítico); handler idempotente registrado
- Celery Beat: expire_soft_reservations_scan (*/5 min)
- ScheduleException: SUBSTITUTIVE | ADDITIVE por data
- DirectOccupancy com overbooking auditado
- Appointment: DRAFT, FAILED, operation_type

**HEAD migration:** m5n6o7p8q9r0 (add_payment_submethod)
**Total migrations Fase 2 + alinhamento + Sprint Integrações + pré-req frontend + Ajuste 9 + correções:** 27 (k1→d1→e1→psg→f2→g3→h2→i3→j2)
**Total testes:** 142/142 (+ 2 skips PostgreSQL real)

## PaymentsEngine (Sprint 9 concluído)
- Payment FSM: PENDING → CONFIRMED → REFUNDED
- confirm() atômico (5 passos na mesma transação; ver brief v2)
- Idempotência: ProcessedIdempotencyKey + UNIQUE no banco
- payment.confirmed → CommunicationService via EventBus (best-effort, fora da tx)
- handle_payment_refunded em FinancialCoreEngine
- Payment.provider imutável (trigger banco + @validates)
- DepositPolicy por serviço ou global

### Webhook Asaas — contrato de `/payments/webhook/asaas/transaction`

⚠️ **Este é o caminho de entrada de dinheiro.** As regras abaixo são deliberadas;
não amplie nenhuma delas sem entender o motivo original.

#### Gate de eventos (S0.1)

Somente `PAYMENT_RECEIVED` e `PAYMENT_CONFIRMED` chamam `confirm()`. Qualquer
outro tipo de evento é **descartado com 200 e log de baixo nível**.

Motivo: antes do S0.1, qualquer evento com `id` no payload chamava `confirm()` —
o que fazia `PAYMENT_CREATED` (cobrança apenas gerada) e `PAYMENT_OVERDUE`
(cobrança vencida) **confirmarem o pagamento**, gerando Movement, Entry e comissão
para dinheiro que nunca entrou.

**Ao adicionar um novo tipo de evento à lista, verifique que ele significa
"dinheiro entrou"** — não "cobrança existe", "cobrança mudou" ou "cobrança
venceu". O descarte é logado justamente para que se possa auditar, depois, se
algum evento relevante está caindo fora.

#### Semântica dos status de resposta

O Asaas decide reenviar **pelo status HTTP**, nunca pelo corpo. Portanto:

| Situação | Status | Racional |
|---|---|---|
| Evento fora do gate | 200 | Descarte legítimo; reenviar não muda nada |
| Payload sem `event_id` | 200 | Payload imutável — o retry traria o mesmo defeito |
| Evento relevante, `Payment` não encontrado | 503 | **Corrida**: a linha pode existir em instantes; queremos reenvio |
| `confirm()` levantou exceção | 500 | Falha nossa de processamento; queremos reenvio |
| Sucesso / duplicata confirmada | 200 | Processado |

⚠️ **Nunca devolver 2xx para uma falha de processamento.** Foi esse o defeito
original (A4 §2.1): o corpo dizia `{"ok": false}` e ninguém o lia, então o Asaas
considerava o evento entregue e nunca reenviava — pagamento pago ficava PENDING
para sempre, sem Movement, sem Entry, sem comissão.

#### Escopo do `except IntegrityError` em `confirm()`

O `except IntegrityError` cobre **apenas o INSERT do evento de idempotência**
(passo 2). Falhas dos passos 3–5 — incluindo violação de integridade do Financial
Core — **propagam**.

E mesmo no caminho de `IntegrityError`, a duplicata só é aceita como sucesso se o
`Payment`, recarregado do banco, estiver de fato `CONFIRMED`. Caso contrário a
exceção propaga.

Motivo (A4 §2.2): quando o `except` cobria os passos 2–5, uma violação de FK do
Financial Core era **indistinguível** da duplicata esperada do UNIQUE — o handler
fazia rollback e devolvia o `Payment` ainda PENDING como se fosse caminho feliz,
**sem uma linha de log**.

#### Dívidas conhecidas neste caminho (fila pós-S0.1)

- ~~**Sem validação de assinatura**~~ → **RESOLVIDO no S0.3** (ver seção abaixo).
- **`confirm()` não checa o status atual do `Payment`** — um `event_id` novo
  re-confirmaria um `Payment` já REFUNDED/CANCELLED. → sprint **D7**
- **`account_status:304`** (`skipped=missing_fields`) tem o mesmo padrão do
  `:242` e não foi auditado. → fila

#### Autenticação dos webhooks Asaas (S0.3)

Ambos os endpoints (`/transaction` e `/account_status`) exigem o header
`asaas-access-token`, validado pelo helper único
`_require_asaas_webhook_token`. **Não duplique a validação** — se o mecanismo
mudar, deve mudar num lugar só.

**Mecanismo:** token estático. Não é escolha de desenho — o Asaas **não oferece
HMAC do payload**; token no header é o teto do provider. Se um dia oferecer,
migrar (HMAC resiste a replay; token estático não).

**Fail-closed.** Token ausente, vazio, errado ou **não configurado no ambiente**
produzem todos o **mesmo 401, com o mesmo `detail`**, e a validação ocorre
**antes de qualquer query** — sem diferença de resposta nem de tempo entre os
casos.

⚠️ **Nunca reintroduzir `if expected_token and ...`.** Esse era o defeito do
`account_status` antes do S0.3: com a env var vazia, a validação era pulada em
silêncio. Configuração incompleta virava superfície aberta sem que nada parecesse
errado.

**Severidade de log é assimétrica, e é deliberado:**

| Caso | Nível | Por quê |
|---|---|---|
| Token errado | `WARNING` | Tentativa de terceiro ou remetente mal configurado |
| Token **não configurado** | `ERROR` (boot **e** por request) | Falha **nossa** — *todos* os webhooks legítimos estão sendo rejeitados |

O log de rejeição registra endpoint, tipo de evento, origem e `token_len` —
**nunca o conteúdo do token**. (Antes do S0.3, o `account_status` gravava
`token_received[:8]`.)

**401 é não-2xx, portanto o Asaas reenfileira** — coerente com o contrato de
status do S0.1: erro de configuração *aparece* em vez de sumir evento.

#### ⚠️ Token de produção (pendência do Silva)

O `ASAAS_WEBHOOK_TOKEN` no Railway é hoje o token de **sandbox**. Ao ativar a
conta Asaas de produção, o token precisa ser trocado nos **dois lados**: gerar no
painel do Asaas de produção **e** atualizar a env var. Trocar só um lado faz o
webhook rejeitar tudo — falha barulhenta (desejável), mas saiba o diagnóstico de
antemão.

#### Webhook Evolution (WhatsApp) — fail-open por limitação do provider

O `EVOLUTION_WEBHOOK_SECRET` tem soft-gate fail-open, mas **não é o mesmo caso**:
a Evolution v2 **não envia header de autenticação**, então não há token a validar.
Não é o idioma do `account_status` copiado — é uma limitação estrutural.
Corrigir exige **análise própria** (restringir por IP de origem? segredo na URL?
aceitar e documentar?), não replicação do helper Asaas. Superfície real, mas de
natureza distinta: forjar mensagem de bot é menos grave que forjar confirmação de
pagamento. Está na fila.

**HEAD migration:** y1z2a3b4c5d6 (add_deposit_policies)

## Sprint de Integrações (pós-Fase 2)

### Email / CommunicationService
- Canal EMAIL em `dispatch()` via Mailtrap HTTP API (fallback: smtplib se SMTP_HOST configurado)
- `_send_email()` em `modules/communication/service.py`
- `forgot_password()` e `send_invite()` passam `recipient_email` no context
- MAILTRAP_API_TOKEN + MAILTRAP_SANDBOX_INBOX_ID em config.py
- Nota: Railway bloqueia SMTP (25/465/587/2525); usar Mailtrap HTTP API ou SendGrid em produção
- Templates `auth.password_reset_requested` e `user.invitation_sent` channel=EMAIL em `_DEFAULT_TEMPLATES`

### Asaas — correções críticas
- `create_payment()` chama `provider.create_charge()` antes do commit → `payment.external_charge_id` preenchido
- `confirm()` extrai value/fee do payload aninhado: `webhook_data.get("payment", {}).get("value")`
- Lazy registration de customer Asaas: `ensure_customer()` na primeira cobrança → `Customer.asaas_customer_id`
- `validate_and_clean_cpf_cnpj()` em `payments/service.py` — valida dígitos verificadores antes do Asaas
- **Dívida**: `create_subaccount()` sem `birthDate` — bloqueia produção Asaas com CPF

### PagSeguro (novo provider)
- `providers/pagseguro.py` — PagSeguroProvider(PaymentProvider) para terminais físicos
- OAuth2 client_credentials via `_authenticate()` — token descartado após uso
- `create_charge()`, `handle_webhook()`, `get_status()` implementados para terminal físico
- `refund()` — **STUB, endpoint `/charges/{id}/cancel` NÃO confirmado pela documentação PagBank (2026-06-03)**
- `list_terminals()` — **STUB, endpoint REST de listagem não encontrado na documentação pública**
- Decisão arquitetural: PagSeguro Point não tem REST API pública para push de cobranças
  → SmartPOS/PlugPag usam SDK Android; TEF usa middleware de parceiros — sem REST direto
- Migration `psg1a2b3c4d5`: `credentialprovider` enum recebeu valor 'PAGSEGURO'
- Factory em `provider_factory.py`: PAGSEGURO credential → PagSeguroProvider; fallback → AsaasProvider

### Pagamento manual / MAQUININHA
- `POST /payments/{id}/confirm-manual` — OWNER/ADMIN; CASH e provider=manual
- `confirm_manual()` retorna `tuple[Payment, Optional[dict]]` — segundo elemento é `fee_warning`
- `_calc_manual_fee()` consulta `TenantFeeRoutingPolicy` pelo `fee_source` do payment_method
- `fee_percentage=NULL` → fee=0 + `fee_warning` no response (taxa não configurada)
- `fee_percentage=0` → fee=0 sem warning (zero configurado explicitamente)
- `event_id` sintético determinístico: `f"manual-{payment.payment_id}"` — garante idempotência
- `MAQUININHA` (genérico) + `payment_submethod`: DEBIT → MAQUININHA_DEBIT; CREDIT/None → MAQUININHA_CREDIT

### Taxa MDR — fee-policies
- `GET  /financial/fee-policies` — OWNER/ADMIN/**PROFESSIONAL** (leitura; tela Taxas
  read-only do PROFESSIONAL) via `_fee_policies_read`; lista 8 políticas por tenant
- `PATCH /financial/fee-policies/{fee_source}` — OWNER/ADMIN; atualiza fee_percentage / fee_flat
- `fee_source` válidos agora incluem: `MAQUININHA_PIX` (adicionado neste sprint)
- Novos tenants: MAQUININHA_PIX criado com fee_percentage=NULL; demais com fee_percentage=0
- Migration `f2g3h4i5j6k7`: ADD COLUMN fee_percentage (nullable), fee_flat, is_active
- Migration `g3h4i5j6k7l8`: DROP NOT NULL fee_percentage + seed MAQUININHA_PIX para tenants existentes

### Evolution API — hardening
- Webhook `POST /whatsapp/webhook` valida `EVOLUTION_WEBHOOK_SECRET` se configurado
- Header validado: `x-evolution-global-apikey`; sem segredo configurado → sem validação
- `EVOLUTION_WEBHOOK_SECRET: str = ""` em config.py (default = sem validação)

## Sprint Frontend (pós-Sprint de Integrações)

### Arquitetura de navegação (painel/)
- Sidebar: MENU (não "Navegação"); itens: Painel, Clientes, Serviços,
  Barbeiros, Produtos, Financeiro, Configurações
- /agenda: rota canônica para agendamentos (calendário por padrão)
- /appointments: redirect para /agenda
- /users: redirect para /settings/usuarios
- /integrations: redirect para /settings/integracoes

### Módulo Financeiro (/financeiro)
- Hub: dashboard com KPIs + gráfico de área (Recharts)
- /financeiro/pagamentos: lista com confirm-manual e FeeWarningBanner
- /financeiro/pagamentos/novo: formulário 4 métodos (CASH/PIX/MAQUININHA)
- /financeiro/movimentacoes: extrato com filtros
- /financeiro/taxas: políticas MDR por método (movido de /settings/taxas)

### Configurações (/settings)
- /settings/perfil: Meu Perfil (nome editável via PATCH /auth/profile)
- /settings/profile: Perfil da empresa (inclui Agendamento Online)
- /settings/integracoes: WhatsApp + Asaas (PagSeguro escondido até sandbox)
- /settings/comunicacao: toggles email/WhatsApp via PUT (não PATCH)
- /settings/usuarios: lista e convite de usuários (com campo name)
- /settings/taxas: redirect para /financeiro/taxas

### Componentes novos
- CustomerAutocomplete: autocomplete client-side de clientes
- FeeWarningBanner: aviso de taxa não configurada com link para /financeiro/taxas
- PaymentOnCompleteDialog: popup de pagamento ao concluir agendamento
  → fluxo: POST /payments → confirm-manual → PATCH /complete
  → "Concluir sem registrar": apenas PATCH /complete

### Decisões arquiteturais
- PagSeguro escondido da UI: componente TabPagSeguro comentado em
  settings/integracoes/page.tsx — reativar após sandbox PagBank validado
- Link de agendamento online: settings/profile (não settings/integracoes)
- Taxas MDR: módulo Financeiro (não Configurações)
- api.ts: parseDetailMessage() trata detail como array (FastAPI 422)
- AuthContext expõe setName para atualização do header sem reload

### Dívidas frontend
- Ajuste 9 (subconta Asaas): 5 campos obrigatórios ausentes no payload
  mobilePhone, incomeValue, address, addressNumber, province, postalCode
  Ver: painel/docs/plano-ajustes-pos-sprint.md seção Ajuste 9
- Visual das novas seções: genérico, não compatível com projeto de referência
  Deferido para após implementações prioritárias
- settings/financial/page.tsx: orphan (sem link no hub) — manter ou redirect
- Campo phone em User: não existe no modelo — requer migration separada

## Transfer + Reconciliação + CashCount (Sprint 7 concluído)
- Transfer: 2 Movements atômicos; sem Entry
- Movement permanece 100% append-only; reconciliação via movement_reconciliations
- CashCount ADJUSTED: create_manual_adjustment + entry_id vinculado
- notes obrigatório quando discrepancy != 0

**HEAD migration:** s1t2u3v4w5x6 (add_cash_counts)

## Financial Core — fundação (Sprint 6 concluído)
- TenantFeeRoutingPolicy: lookup por (company_id, fee_source); sem FK em tenant_configs
- Account, Movement (append-only), Entry (append-only)
- FinancialCoreEngine: handle_payment_confirmed, create_manual_adjustment, queries
- Hook create_company: Account CAIXA + 7 TenantFeeRoutingPolicies (mesma transação)
- Triggers de imutabilidade no banco + @validates ORM
- 2 testes de trigger pendentes de validação em staging (PostgreSQL real)

**HEAD migration:** o1p2q3r4s5t6 (add_entries_with_immutability_trigger)

## Ambiente de testes

### Executar SEMPRE com o venv
```powershell
cd agendamento_engine
.\venv\Scripts\python.exe -m pytest tests/ -v
```

NUNCA usar `pytest` direto — o Python global (pyenv) não tem `slowapi`, causando 9 ModuleNotFoundError em `test_user_name.py`. Esses erros são **ambientais**, não bugs de código. Não investigar.

#### test_user_name.py — 9 ModuleNotFoundError
Causa: importa `app.main` → carrega `slowapi` ausente no Python global.
Solução: sempre usar `.\venv\Scripts\python.exe -m pytest`. Não confundir com regressão — ignorar quando usando venv.

### Testes que exercitam services contra SQLite — o idioma do monkey-patch

Alguns arquivos de teste rodam os services contra uma **sessão SQLite real**
(INSERT/UPDATE/flush/refresh de verdade, não mock). Isso exige contornar os tipos
do PostgreSQL: `User.id` é `postgresql.UUID(as_uuid=True)`, cujo bind processor
chama `.hex` numa string e levanta
`StatementError: 'str' object has no attribute 'hex'` — e a `Base` completa usa
ARRAY/JSONB/EXCLUDE, então `create_all` real também não funciona.

O contorno: espelhar as tabelas necessárias numa `TestBase` com PKs `String(36)`
e re-vincular as referências de modelo no fixture.

⚠️ **Patchar os módulos de modelo NÃO é suficiente.** Services importam os
modelos no topo (`users/service.py:14`, `activate_service.py:11`), então o vínculo
congela na primeira importação do service. Se qualquer arquivo de teste importar o
service antes, o patch não alcança — e o arquivo inteiro falha.

**Sempre re-vincular também os namespaces consumidores**, com restauração no
teardown. É o idioma usado em `test_user_name.py`,
`test_sprint27_professional_scope.py`, `test_sprint28_professional_contact.py`,
`test_working_hours_multiperiod.py` e (desde o S0.4) `test_sprint2_rbac.py`.

Namespaces patchados hoje em `test_sprint2_rbac.py`:

| Namespace | Símbolos |
|---|---|
| `app.infrastructure.db.models.audit_log` | `AuditLog` |
| `app.infrastructure.db.models.user_invitation` | `UserInvitation` |
| `app.infrastructure.db.models.user` | `User` |
| `app.infrastructure.db.models` (pacote) | `AuditLog`, `UserInvitation`, `User`, `InvitationStatus` |
| `app.modules.users.service` | `User`, `UserInvitation` |
| `app.modules.auth.activate_service` | `User`, `UserInvitation` |

**Limitação conhecida:** a lista é explícita. Um consumidor novo que importe esses
modelos no topo e entre no caminho dos testes quebra com o mesmo erro `.hex` —
**falha barulhenta, não silenciosa**. Se você tropeçar nesse erro depois de
adicionar um service ou um import, acrescente o namespace ao fixture.

Eliminar a classe de problema exigiria refactor suite-wide da estratégia de
fixtures — está na fila, não é urgente enquanto a falha for barulhenta.

#### ❌ Convenção obsoleta (removida no S0.4)

Havia uma nota (em `test_sprint16_promotions.py` e neste arquivo) instruindo a
**não importar `app.main` antes de `test_sprint2_rbac`**. Era contorno do sintoma:
evitava-se o gatilho em vez de corrigir a causa. **Não vale mais** — o fixture é
robusto a ordem desde o S0.4, verificado em 6 permutações. Não replique essa
restrição em testes novos.

#### As duas coberturas de RBAC são complementares — não confunda

| Arquivo | O que verifica |
|---|---|
| `test_sprint2_rbac.py` | **Permissão** — quem pode fazer o quê (anti-escalonamento, papéis, guards 403/422) |
| `test_s02_cross_tenant_users.py` | **Posse** — sobre *quem* a ação recai (o alvo pertence ao tenant do ator?) |

Medido no S0.4: as classes `TestAssignRoleService` e `TestDeactivateUser`
exercitam o service real e atravessam até o banco, **mas as linhas do `raise 404`
do filtro de posse (S0.2) não executam** — ou seja, esses testes passariam contra
o código pré-S0.2.

**Religar os 12 não substitui o S0.2.** Foi essa a combinação que deixou os
vazamentos cross-tenant sobreviverem: cobertura de permissão desligada por
contaminação de ordem, e cobertura de posse inexistente. Ao mexer nesses
endpoints, os dois arquivos precisam continuar verdes.

### Testes skipados sem DATABASE_URL (PostgreSQL real) — validados 2026-06-08

Usam `@pytest.mark.skipif(not DATABASE_URL)` — pulam automaticamente sem banco real; passam contra Supabase. Implementados com SAVEPOINT + rollback: zero resíduo no banco, usam registros reais para satisfazer FKs.

| Teste | Arquivo | Trigger que valida | Validado |
|---|---|---|---|
| `TestTenantConfigAccrual::test_trigger_blocks_accrual_at_db_level` | `tests/test_sprint3_config.py` | `enforce_cash_mode` (fn `block_accrual_mode`) | ✓ 2026-06-08 |
| `TestImmutabilityTriggers::test_movement_update_rejected_by_trigger` | `tests/test_sprint6_financial_core.py` | `movement_no_update` (fn `prevent_movement_modification`) | ✓ 2026-06-08 |
| `TestImmutabilityTriggers::test_entry_delete_rejected_by_trigger` | `tests/test_sprint6_financial_core.py` | `entry_no_delete` (fn `prevent_entry_modification`) | ✓ 2026-06-08 |

Rodar contra Supabase:
```powershell
$env:DATABASE_URL="postgresql://postgres:<senha>@<host>:5432/postgres"
.\venv\Scripts\python.exe -m pytest tests/test_sprint3_config.py::TestTenantConfigAccrual::test_trigger_blocks_accrual_at_db_level tests/test_sprint6_financial_core.py::TestImmutabilityTriggers::test_movement_update_rejected_by_trigger tests/test_sprint6_financial_core.py::TestImmutabilityTriggers::test_entry_delete_rejected_by_trigger -v
```

### 1 xfail esperado (permanente)
`tests/test_asaas_integration.py::test_sandbox_create_subaccount`
Asaas sandbox rejeita criação de subconta sem todos os campos obrigatórios. Marcado `xfail(strict=False)` — comportamento esperado, não investigar.

## Stack e infraestrutura

- FastAPI 0.115 · SQLAlchemy 2.0 · Alembic
- slowapi ativo — rate limit 10 req/min/IP em POST /auth/login (X-Forwarded-For)
- Uploads: Supabase Storage (dual-write ativo; migração de URLs executada)
- EXCLUDE CONSTRAINT ativa em appointments (btree_gist + tsrange, company_id + professional_id)
- Tabelas criadas: `user_invitations`, `audit_logs` (append-only via triggers no banco)
- Tabelas: `tenant_configs`, `module_activations`, `tenant_brandings`, `categories`
- Onboarding: `create_company` cria TenantConfig + 10 ModuleActivations +
  TenantBranding + 16 categories default na mesma transação
- Workers: Celery + Redis (session_cleanup e reminder exclusivamente via Celery Beat)
- EventBus ativo em `app/infrastructure/event_bus.py` (best-effort, fluxos tolerantes)
- Idempotência: `processed_idempotency_keys` (PK composta key+consumer; company_id como auditoria)
- Beat: worker usa `-A app.infrastructure.celery_app:celery_app`
       beat usa `-A app.workers.celery_beat_entrypoint:celery_app` (evita import circular)
- CommunicationService ativo em `modules/communication/service.py`
- Tabelas: integration_credentials, communication_settings,
  communication_templates, communication_logs
- Fernet encryption via `core/encryption.py`
  (CREDENTIAL_ENCRYPTION_KEY obrigatório em produção; ausente → KeyError no startup)
- Feature flag: `TenantConfig.permission_overrides["use_communication_service"]`
  é kill-switch do dispatch (Sprint I: ausente → True; False = opt-out explícito)
- RLS ativo em 26 tabelas (políticas por tenant_isolation; superuser bypassa automaticamente)
- `core/db_rls.py` — set_rls_context() chamado em get_db() e workers Celery
- Workers: company_id=None para scans multi-tenant (bypass); específico para tasks por tenant

## Convenções críticas

- EXCLUDE CONSTRAINT no_overlap_per_professional: filtro WHERE status NOT IN
  ('CANCELLED','FAILED','EXPIRED') — NO_SHOW e COMPLETED ativam a constraint
- Upload: endpoint retorna URL Supabase; gravação local foi removida
- `User.role`: Enum `userrole` com 9 valores — OWNER|ADMIN|OPERATOR|PROFESSIONAL|CLIENT|PLATFORM_OWNER
  ativos; PLATFORM_SUPPORT|PLATFORM_BILLING|PLATFORM_READONLY schema-only (Estágio 1+)
- `User.company_id`: nullable — PLATFORM_OWNER tem NULL; demais têm company_id preenchido
- Auth: `require_role()` e `require_action()` — `require_admin` removido do codebase
- `require_action` lê `permission_overrides` de `tenant_configs` (fallback `{}` gracioso)
- `is_admin` property: `role in ("ADMIN", "OWNER", "PLATFORM_OWNER")`
- `accounting_mode=ACCRUAL` bloqueado por trigger `block_accrual_mode` no banco
- `fee_routing_policy_id` em `tenant_configs`: UUID sem FK (tabela criada na Fase 2 Sprint 6)
- Category `is_default=true`: desativável, não deletável, name/entity_type/sort_order imutáveis
- `GET /tenant/branding`: público — usa `company_id` como query param (sem auth)
- Invitations em `/users/invitations` (não `/invitations` independente)
- bot_sessions e booking_sessions são domínios separados:
    session_cleanup_worker → bot_sessions apenas
    handler booking_session.expired → booking_sessions apenas
- Fluxos críticos não passam pelo EventBus — Celery task direta:
    appointment.confirmed, appointment.cancelled, appointment.reminder_due, appointment.no_show
- idempotency_key dois domínios distintos:
    Appointment.idempotency_key → evita duplo-INSERT de agendamento (cliente envia)
    processed_idempotency_keys.key → evita dupla execução de consumer (infra)
- Credenciais armazenadas criptografadas via Fernet — nunca plaintext no banco
- `secret_encrypted` nunca retornado em respostas de API — apenas `masked_preview` + `config`
- Quiet hours: transacionais (appointment.confirmed, appointment.cancelled) → bypass → SENT;
  automáticos (appointment.reminder_due, appointment.no_show) → respeita → SCHEDULED
- Senha de usuário: mínimo 8 chars + 1 maiúscula + 1 número (validado no backend)
- Token de reset: 6 dígitos numéricos, TTL 15min, invalidado imediatamente após uso
- forgot_password requer template "auth.password_reset_requested" cadastrado no tenant

## Onde está o quê

- `core/audit/sensitive_context.py` — `SensitiveAuditContext`, `record_sensitive_action`, `REASON_REQUIRED`
- `domain/enums/action_scope.py` — `ActionScope` enum (re-export)
- `infrastructure/db/models/user_invitation.py`
- `infrastructure/db/models/audit_log.py`
- `modules/audit/router.py` — `GET /audit/logs`, `GET /audit/logs/export`
- `modules/auth/activate_service.py` — ativação de convite por token
- `modules/tenant/` — /tenant/config, /tenant/modules, /tenant/branding
- `modules/categories/` — /categories
- `infrastructure/db/models/{tenant_config,module_activation,tenant_branding,category}.py`
- `infrastructure/celery_app.py` — configuração Celery
- `infrastructure/event_bus.py` — EventBus (tolerantes)
- `core/idempotency.py` — is_processed, mark_processed
- `workers/beat_schedule.py` — reminder/10min, session-cleanup/5min,
    idempotency-cleanup/03:00, booking-session-scan/5min
- `workers/celery_beat_entrypoint.py` — entrypoint exclusivo do beat
- `workers/booking_session_worker.py` + `booking_session_handlers.py`
- `workers/appointment_reminder_handler.py` — stub, Sprint 5 substitui
- `workers/idempotency_cleanup.py`
- `core/encryption.py` — encrypt_secret, decrypt_secret, make_masked_preview
- `modules/communication/` — CommunicationService, routers /communication/*
- `modules/integrations/` — IntegrationCredential service, routers /integrations/credentials/*
- `workers/communication_worker.py` — Celery tasks para fluxos críticos de appointment
- `infrastructure/db/models/{integration_credential,communication_setting,
  communication_template,communication_log}.py`
- `infrastructure/db/models/password_reset_token.py`
- `modules/auth/router.py` — adicionados: POST /auth/forgot-password,
  POST /auth/reset-password, POST /auth/change-password

## O que NÃO fazer

- Não reintroduzir os.makedirs("static/uploads") — removido de main.py
- Não usar URLs de volume local (/static/uploads/) — fonte de verdade é Supabase Storage
- `POST /users` legado foi removido
- Não criar endpoints novos com `require_admin` — usar `require_role()` ou `require_action()`
- `require_admin` não existe mais — não referenciar
- Não criar `TenantFeeRoutingPolicy` — pertence ao Financial Core (Fase 2, Sprint 6)
- Não implementar `accounting_mode=ACCRUAL` — bloqueado por trigger no Estágio 0
- Não adicionar workers via asyncio.create_task no lifespan — usar Celery Beat
- Não publicar eventos sem idempotency_key
- Não chamar `evolution_client.send_text()` diretamente em código novo
  → usar CommunicationService.dispatch (chamadas diretas de notificação removidas no Sprint I;
  exceção: bot conversacional via whatsapp/sender.py)
- Não criar `integration_credentials` com `provider=WHATSAPP_EVOLUTION` no Estágio 0
- `CREDENTIAL_ENCRYPTION_KEY` nunca commitar no repositório — vault Railway apenas
- Não fazer queries fora de get_db() (HTTP) ou celery_db_session() (workers) — RLS context não será setado
- Não modificar migrations existentes para SET LOCAL row_security = off
  — superuser no Supabase bypassa automaticamente
- Não enviar ação SELECT_SHIFT pelo FSM — AWAITING_SHIFT foi removido
  do fluxo principal. O endpoint stateless GET /booking/{slug}/slots?shift=
  ainda funciona; apenas o step do FSM foi eliminado.
- Não chamar `provider.refund()` para PagSeguro em produção — endpoint não confirmado (stub retorna 500)
- Não usar revision ID `e1f2g3h4i5j6` para Sprint 11 — já em uso por add_asaas_customer_id

## Decisões registradas

- `ACCRUAL` bloqueado no Estágio 0 via trigger `block_accrual_mode` em `tenant_configs`
- Evolution API permanece global no Estágio 0 (Opção A — confirmada no Sprint 5):
  WHATSAPP_EVOLUTION no enum provider é schema-only; migração whatsapp_connection
  não aplicável no Estágio 0
- PagSeguro Point: documentação pública não expõe REST API para push de cobranças a terminais físicos.
  Soluções físicas (SmartPOS, PlugPag, TEF, Tap On) usam SDK Android, Bluetooth ou Intent local.
  PagSeguroProvider.create_charge() usa endpoint /orders como proxy — não confirmado para Point.
  Decisão: não ativar PagSeguro Point em produção até confirmar endpoint com time comercial PagBank.

- fee_percentage NULL vs. zero: NULL = "não configurado" → dispara fee_warning em confirm_manual.
  Zero = "0% configurado" → sem aviso, sem taxa. Semântica intencional para MAQUININHA_PIX.
  Tenants pré-sprint têm MAQUININHA_CREDIT/DEBIT com fee_percentage=0 (DEFAULT da migration) — sem warning.

## Bugs conhecidos / corrigidos

- [CORRIGIDO] Timezone no agendamento (local OK, prod −3h): `start_at` chegava
  *naive* (frontend montava string de horário local sem offset). A coluna é
  `timestamptz`, então o Postgres assumia o fuso da **sessão do servidor** — dev
  em horário de Brasília gravava certo, mas Railway em **UTC** deslocava −3h.
  Fix em `appointments/service.py`: `_normalize_start_at` (via `_resolve_tenant_tz`)
  coage qualquer `start_at` naive para o fuso do tenant (fallback America/Sao_Paulo)
  e converte para UTC, em `create_appointment` e `reschedule_appointment` —
  instante idêntico em qualquer servidor. Frontend também passou a enviar UTC
  (`toISOString()`); o backend é a defesa robusta contra qualquer cliente naive.
- [CORRIGIDO] Timezone na geração de slots: working_hours eram tratados
  como UTC em vez de horário local do tenant.
  Fix em availability/service.py + appointments/service.py.
  Usa TenantConfig.timezone como fonte canônica com fallback
  "America/Sao_Paulo". Requer tzdata==2026.2 (adicionado ao requirements).
- [CORRIGIDO] company_profile router: User object passado em vez de company_id — fix em 9fed210
- [CORRIGIDO] professionals/schemas: specialty ausente de ProfessionalUpdate/Response — fix em bbb5632
- [CORRIGIDO] products/schemas: stock ausente de ProductUpdate/Response — fix em bbb5632
- [CORRIGIDO] schedule/service: upsert_working_hour suportava apenas 1 período/dia — refatorado DELETE→INSERT em bbb5632
- [CORRIGIDO] booking FSM: SELECT_DATE e NAVIGATE_DATES bloqueados em AWAITING_TIME — fix ddb52c9
- [CORRIGIDO] working_hours: upsert suportava apenas 1 período/dia — refatorado DELETE→INSERT em bbb5632
- [CORRIGIDO] professionals: specialty ausente dos schemas — fix bbb5632
- [CORRIGIDO] products: stock ausente dos schemas — fix bbb5632
- [CORRIGIDO] Professional.specialty: ausente do modelo ORM — adicionado em d5c4741
- [CORRIGIDO] Product.stock: ausente do modelo ORM — adicionado com validator >= 0 em d5c4741
- [CORRIGIDO] WorkingHour: UniqueConstraint removido do ORM (nunca existiu no banco) — múltiplos períodos/dia funcionam em d5c4741
- replace_working_hours_for_day: DELETE+INSERT atômico, max 3 períodos, validação de sobreposição

## Segurança

- JWT agora inclui `iat` (issued at) em todos os tokens
- Troca de senha invalida tokens emitidos antes dela via `last_password_change_at`
  em User — tokens sem `iat` (pré-deploy) são aceitos por backward compat
- change_password e reset_password atualizam last_password_change_at

## Dívidas de integração
- [RESOLVIDO — Sprint I] Asaas refund: payment_service.refund() chama provider.refund()
  ANTES da contabilidade; falha do gateway → 502 sem Movement/Entry; force_local p/ OWNER
- [RESOLVIDO — Sprint I] Email em produção: adapter plugável via EMAIL_PROVIDER
  (mailtrap|sendgrid|smtp). Railway bloqueia SMTP → configurar EMAIL_PROVIDER=sendgrid
  + SENDGRID_API_KEY, ou mailtrap com token de produção (MAILTRAP_SANDBOX_INBOX_ID=0),
  no vault do Railway. Mailtrap sandbox permanece para dev.
- PagSeguro Point: REST API para push de cobranças não documentada publicamente;
  create_charge() e list_terminals() são stubs aguardando confirmação do time comercial PagBank
- Ajuste 9 Asaas: backend completo (migration i3j4k5l6m7n8, 8 colunas owner_* em
  companies; AsaasProvider.create_subaccount aceita todos os campos; service.py
  persiste e envia — inclui birthDate). Frontend pendente (5 campos no formulário
  de settings/integracoes). Tenants criados antes do Ajuste 9 sem external_account_id
  — subconta Asaas inexistente para esses tenants.

## Lições de produção (2026-06-07)
- FeePolicyResponse.fee_percentage: sempre Optional[Decimal] — coluna nullable no banco
- communicationaudience enum PostgreSQL: valores uppercase (CLIENT, PROFESSIONAL, OWNER)
  dispatch() normaliza recipient_type.upper() antes de qualquer query
- _DEFAULT_FEE_SOURCES deve estar sincronizado com _calc_manual_fee e frontend:
  CASH, CHAVE_PIX, MAQUININHA_PIX,
  MAQUININHA_CREDIT_VISA_MASTER, MAQUININHA_CREDIT_ELO,
  MAQUININHA_CREDIT_HIPER_AMEX, MAQUININHA_CREDIT_OUTROS,
  MAQUININHA_DEBIT_VISA_MASTER, MAQUININHA_DEBIT_ELO,
  MAQUININHA_DEBIT_OUTROS (migration l4m5n6o7p8q9).
  PIX/BOLETO/CARD_* removidos — taxa vem do webhook Asaas.
- GET /financial/movements retorna: type (não movement_type), movement_id (não id),
  occurred_at (não created_at), amount como string Decimal
- ConfirmManualResponse é flat — não tem camada payment: { ... }
- target_account_id em PaymentCreate: Optional — backend resolve conta CAIXA
- provider em PaymentCreate: Optional — default "manual"