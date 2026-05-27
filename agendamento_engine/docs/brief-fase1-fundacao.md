# Brief de execução — Fase 1: Fundação técnica
Sprints 1–5 · ~10 semanas  
Baseado em: `visao-estagio-0.md` · `plano-execucao-estagio-0.md`  
Revisão: correções arquiteturais aplicadas (v2)

---

## Estado de entrada (o que já existe — não reimplementar)

```
Backend (agendamento_engine/)
  FastAPI app com 15 routers registrados
  SQLAlchemy 2.0 + Alembic (18 migrations, HEAD: f1e2d3c4b5a6)
  Modelos existentes: appointment, availability_slot, booking_session, bot_session,
    company, company_profile, company_settings, customer, product, professional,
    service, user, web_booking_session, whatsapp_connection
  Auth: JWT + bcrypt (core/security.py, core/deps.py)
    — User.role: String(20), valores: ADMIN | PROFESSIONAL | CLIENT
    — require_admin: binário (admin/não-admin)
    — company_id: NOT NULL em User (bloqueia PLATFORM_OWNER)
  Workers: reminder_worker + session_cleanup_worker (asyncio loop, SEM Celery/Redis)
  Observabilidade: Sentry + structlog + RequestContextMiddleware
  Multi-tenant: 442 ocorrências de company_id; sem vazamento identificado
  Agenda: BookingEngine FSM + SELECT FOR UPDATE NOWAIT (SEM EXCLUDE CONSTRAINT)
  Bot WhatsApp: 13 handlers FSM, idempotência via last_message_id
  Campos da tabela appointments: start_at, end_at (não start_time/end_time)

Frontend (painel/)
  Next.js 16.2 + React 19 + Tailwind + shadcn
  8 áreas de gestão; sidebar sem filtro por role
```

---

## Sprint 1 — Segurança e infraestrutura crítica

**Objetivo:** eliminar os desvios arquiteturais de segurança que existem com cliente real em produção.

### Backend

- [ ] Adicionar `EXCLUDE CONSTRAINT` na tabela `appointments` usando `btree_gist`.
      A constraint deve incluir `company_id` (padrão multi-tenant do projeto)
      e usar os nomes de campo corretos `start_at`/`end_at`:
      ```sql
      CREATE EXTENSION IF NOT EXISTS btree_gist;

      ALTER TABLE appointments
        ADD CONSTRAINT no_overlap_per_professional
        EXCLUDE USING gist (
          company_id   WITH =,
          professional_id WITH =,
          tsrange(start_at, end_at, '[)') WITH &&
        )
        WHERE (status NOT IN ('CANCELLED', 'NO_SHOW'));
      ```
      Migration obrigatória. Testar que INSERT sobreposto é rejeitado no banco.

- [ ] Instalar e configurar `slowapi`. Aplicar rate limiting em:
      `POST /auth/login` — 10 req/min por IP
      Endpoints de webhook — configurável por rota
      Retornar `Retry-After` no header 429.

- [ ] Adicionar security headers via middleware:
      `X-Content-Type-Options: nosniff`
      `X-Frame-Options: DENY`
      `Strict-Transport-Security: max-age=31536000; includeSubDomains`

- [ ] Fixar `bcrypt__rounds=12` explicitamente em `core/security.py`.
      Não depender do default da biblioteca entre versões.

- [ ] Migrar uploads para Supabase Storage.
      Remover `os.makedirs("static/uploads")` de `main.py`.
      Atualizar endpoints de upload para usar Supabase SDK.
      Manter URLs existentes funcionando via redirect ou re-upload.

### Testes

- [ ] INSERT de appointment sobreposto **no banco** rejeita com erro de constraint
      (não apenas na camada de aplicação)
- [ ] Appointments com status CANCELLED ou NO_SHOW não ativam a constraint
- [ ] `POST /auth/login` retorna 429 após 10 req/min com header `Retry-After`
- [ ] Todos os endpoints retornam os três security headers
- [ ] Upload grava no Supabase e retorna URL pública válida

---

## Sprint 2 — RBAC: papéis, convite e envelope de auditoria

**Objetivo:** sistema de identidade completo com 9 papéis no enum (6 ativos + 3 schema-only),
fluxo de convite seguro sem senha temporária, envelope de auditoria compartilhado e
endpoints de consulta do audit log.

### Migrations

- [ ] Alterar `User.company_id` para `nullable=True`
      (suporte a `PLATFORM_OWNER` sem tenant — revisar queries que fazem JOIN em User)

- [ ] Alterar `User.role` de `String(20)` para Enum com **9 valores**:
      ```
      Ativos no Estágio 0:
        OWNER | ADMIN | OPERATOR | PROFESSIONAL | CLIENT | PLATFORM_OWNER

      [SCHEMA APENAS] — Estágio 1+:
        PLATFORM_SUPPORT | PLATFORM_BILLING | PLATFORM_READONLY
      ```
      Os três papéis de plataforma adicionais devem existir no enum do PostgreSQL agora.
      Adicionar depois exigiria `ALTER TYPE` com migration adicional em fase futura.

- [ ] Criar `user_invitations`
      ```
      invitation_id      UUID PK
      company_id         UUID FK companies (nullable — PLATFORM_OWNER convida sem tenant)
      email              VARCHAR NOT NULL
      role               UserRole Enum NOT NULL
      token              UUID NOT NULL UNIQUE (uso único)
      expires_at         TIMESTAMPTZ NOT NULL DEFAULT now() + interval '48 hours'
      status             Enum [PENDING, ACCEPTED, EXPIRED, CANCELLED]
      invited_by_user_id UUID FK users NOT NULL
      created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
      ```

- [ ] Criar `audit_logs`
      ```
      audit_id          UUID PK
      company_id        UUID (nullable — ações de plataforma não têm tenant)
      actor_id          UUID NOT NULL
      actor_role        UserRole Enum NOT NULL
      action            VARCHAR NOT NULL
      resource_type     VARCHAR NOT NULL
      resource_id       UUID
      amount            NUMERIC(15,2)
      account_id        UUID
      reason            TEXT
      correlation_id    UUID
      before_snapshot   JSONB
      after_snapshot    JSONB
      occurred_at       TIMESTAMPTZ NOT NULL DEFAULT now()
      ip_address        VARCHAR
      user_agent        TEXT
      ```
      Sem DELETE nem UPDATE — append-only (RBAC-4).
      Sem FK para outras tabelas (audit nunca bloqueia cascade delete).

### Estrutura compartilhada — criar ANTES dos módulos que a consomem

- [ ] Criar `app/core/audit/sensitive_context.py`
      ```python
      from enum import Enum

      class ActionScope(str, Enum):
          OWN           = "OWN"           # apenas recursos próprios do ator
          OWN_CUSTOMERS = "OWN_CUSTOMERS" # clientes atendidos pelo ator
          TENANT        = "TENANT"        # qualquer recurso do tenant
          CROSS_TENANT  = "CROSS_TENANT"  # apenas PLATFORM_OWNER

      @dataclass
      class SensitiveAuditContext:
          actor_id:        UUID
          actor_role:      str
          action:          str          # ex: invite_user, assign_role, create_manual_adjustment
          resource_type:   str          # ex: User, Commission, Account
          resource_id:     UUID | None = None
          company_id:      UUID | None = None
          reason:          str | None = None   # opcional no dataclass — validado seletivamente
          amount:          Decimal | None = None
          account_id:      UUID | None = None
          correlation_id:  UUID | None = None
          before_snapshot: dict | None = None
          after_snapshot:  dict | None = None

      # Actions que exigem reason obrigatório:
      REASON_REQUIRED = {
          "create_manual_adjustment",
          "apply_manual_discount_override",
          "export_audit",
          "test_connection",
      }

      def record_sensitive_action(ctx: SensitiveAuditContext, db: Session) -> AuditLog:
          """Grava em audit_logs e retorna o registro criado.
          Levanta ValueError se ctx.action está em REASON_REQUIRED e ctx.reason é None.
          """
          if ctx.action in REASON_REQUIRED and not ctx.reason:
              raise ValueError(f"reason obrigatório para action={ctx.action}")
      ```
      Usado por: `invite_user`, `assign_role`, `create_manual_adjustment`,
      `apply_manual_discount_override`, `export_audit`, `IntegrationCredential.*`.
      **Nenhum módulo cria seu próprio esquema de audit.**

### Services e routers

- [ ] Refatorar `app/core/deps.py`:
      ```python
      def require_role(*roles: str) -> Callable
          # ex: require_role("OWNER", "ADMIN")

      def require_action(action: str, scope: ActionScope = ActionScope.TENANT) -> Callable
          # Verifica se o papel do usuário tem permissão para a ação no escopo dado.
          # Consulta permission_overrides de TenantConfig quando relevante.
          # Scope CROSS_TENANT: apenas PLATFORM_OWNER.
          # Scope OWN: PROFESSIONAL acessando recursos próprios.
          #
          # ATENÇÃO — tenant_configs só existe a partir do Sprint 3.
          # Implementar com fallback gracioso:
          #   try:
          #       config = db.query(TenantConfig).filter_by(company_id=company_id).first()
          #       overrides = config.permission_overrides if config else {}
          #   except Exception:
          #       overrides = {}
          # Após Sprint 3 + seed de onboarding, o fallback {} nunca é atingido
          # para tenants ativos. Não lançar erro se tabela ainda não existir.

      def get_current_company_id(user) -> UUID | None:
          # PLATFORM_OWNER: retorna None
          # outros: retorna user.company_id, levanta 403 se None
      ```
      Criar `app/domain/enums/action_scope.py` com `ActionScope` (mesmo enum de cima).

- [ ] Fluxo de convite — RBAC-3 (sem senha temporária, sem credencial gerada pelo sistema):
      ```
      POST /users/invite
        Requer: OWNER (para ADMIN); OWNER/ADMIN (para OPERATOR/PROFESSIONAL)
        Body: { email, role }
        → Valida que role é um dos papéis ativos no Estágio 0:
            [OWNER, ADMIN, OPERATOR, PROFESSIONAL, CLIENT, PLATFORM_OWNER]
          Rejeitar PLATFORM_SUPPORT, PLATFORM_BILLING, PLATFORM_READONLY → 422
          "Este papel está reservado para uso futuro e não pode ser atribuído."
        → Se role = PLATFORM_OWNER:
            Requer actor.role = PLATFORM_OWNER → caso contrário 403
            "PLATFORM_OWNER só pode ser atribuído por outro PLATFORM_OWNER."
        → Valida anti-escalonamento
        → Cria UserInvitation (token UUID, expires_at = now() + 48h)
        → Envia e-mail com link: https://.../auth/activate?token={token}
        → NÃO cria User; NÃO gera senha
        → record_sensitive_action(action=invite_user)
        → Retorna { invitation_id, expires_at }

      POST /auth/activate
        Body: { token, password, password_confirm }
        → Valida token: status=PENDING e not expired
        → Cria User com:
            email      = invitation.email
            role       = invitation.role
            company_id = invitation.company_id  -- NULL para PLATFORM_OWNER; tenant_id para demais
            password   = bcrypt(password, rounds=12)
        → invitation.status = ACCEPTED
        → Token invalidado imediatamente (ireutilizável)
        → Retorna JWT
      ```

- [ ] Anti-escalonamento enforced em código (não apenas documentado):
      ```
      OWNER    → pode convidar para qualquer role do tenant
      ADMIN    → pode convidar para OPERATOR e PROFESSIONAL apenas
      Qualquer → não eleva o próprio role
      OWNER    → não pode remover o último OWNER ativo do tenant
      ```

- [ ] `GET  /users` — lista usuários do tenant (OWNER/ADMIN)
- [ ] `PATCH /users/{id}/role` — altera role com validação de escalonamento (OWNER/ADMIN)
      ```
      → Rejeitar PLATFORM_SUPPORT, PLATFORM_BILLING, PLATFORM_READONLY → 422
          "Este papel está reservado para uso futuro e não pode ser atribuído."
      → Se role = PLATFORM_OWNER:
          Requer actor.role = PLATFORM_OWNER → caso contrário 403
          "PLATFORM_OWNER só pode ser atribuído por outro PLATFORM_OWNER."
      → Valida anti-escalonamento (não elevar para OWNER/ADMIN sem ser OWNER)
      → Atualiza role
      → record_sensitive_action(
            action="assign_role",
            resource_type="User",
            resource_id=user_id,
            before_snapshot={ role: role_anterior },
            after_snapshot={ role: novo_role }
          )
      ```
- [ ] `DELETE /users/{id}` — desativa (não apaga), com restrição de último OWNER
- [ ] `GET  /invitations` — lista convites pendentes (OWNER/ADMIN)
- [ ] `DELETE /invitations/{id}` — cancela convite pendente

- [ ] `POST /users/transfer-ownership` — apenas o OWNER atual do tenant
      ```
      Body: { new_owner_user_id, current_owner_new_role? (default: ADMIN) }
      → Valida: new_owner_user_id é membro ativo do tenant
      → Atribui OWNER ao usuário destino
      → OWNER atual recebe current_owner_new_role (sem downgrade forçado automático)
      → record_sensitive_action(
            action="transfer_ownership",
            before_snapshot={ owner_id: atual, role: "OWNER" },
            after_snapshot={
              new_owner_id: novo,
              new_owner_role: "OWNER",
              previous_owner_new_role: current_owner_new_role
            }
          )
      Nota: action="transfer_ownership" é consultável diretamente no audit log
      sem necessidade de filtros compostos — facilita auditoria futura.
      ```

- [ ] `GET  /audit/logs` — OWNER/ADMIN
      Query params: `company_id`, `action`, `actor_id`, `date_from`, `date_to`, `page`, `limit`
      Retorna paginado; sem dados mascarados (audit é leitura fiel).

- [ ] `GET  /audit/logs/export` — OWNER; ADMIN com `permission_overrides`
      Retorna CSV via `StreamingResponse`.
      record_sensitive_action(action=export_audit) antes de retornar o stream.

### Testes

- [ ] OWNER convida ADMIN → convite criado, User não existe ainda
- [ ] ADMIN tenta convidar ADMIN → 403
- [ ] ADMIN tenta convidar OWNER → 403
- [ ] Usuário tenta elevar o próprio role → 403
- [ ] Último OWNER do tenant: remoção bloqueada
- [ ] Token de ativação: segundo uso → 410
- [ ] Token expirado (> 48h) → 410
- [ ] Ativação bem-sucedida: User criado, JWT retornado, token invalidado
- [ ] `SensitiveAuditContext` gravado para `invite_user` e `assign_role`
- [ ] `record_sensitive_action` sem `reason` para `invite_user` → sem erro (reason opcional)
- [ ] `record_sensitive_action` sem `reason` para `export_audit` → ValueError (reason obrigatório)
- [ ] `PATCH /users/{id}/role` → audit gravado com `action=assign_role` e before/after
- [ ] `GET /audit/logs` com role PROFESSIONAL → 403
- [ ] `GET /audit/logs/export` grava audit de `export_audit` antes de responder
- [ ] PLATFORM_SUPPORT, PLATFORM_BILLING, PLATFORM_READONLY existem no enum (value check)
- [ ] `POST /users/invite` com `role=PLATFORM_SUPPORT` → 422
- [ ] `PATCH /users/{id}/role` com `role=PLATFORM_BILLING` → 422
- [ ] `POST /users/invite` por OWNER do tenant com `role=PLATFORM_OWNER` → 403
- [ ] `PATCH /users/{id}/role` por ADMIN com `role=PLATFORM_OWNER` → 403
- [ ] Ativação de convite com `role=PLATFORM_OWNER` → User criado com `company_id=NULL`
- [ ] Ativação de convite com `role=OPERATOR` → User criado com `company_id` do tenant
- [ ] `POST /users/transfer-ownership` por não-OWNER → 403
- [ ] Transferência bem-sucedida → OWNER atual vira ADMIN, novo OWNER atribuído,
      audit gravado com `action=transfer_ownership` e before/after snapshots

---

## Sprint 3 — TenantConfig, módulos e branding

**Objetivo:** configuração completa do tenant desde o início, sem migrations fragmentadas.
`fee_routing_policy` **não entra aqui** — pertence ao Financial Core (Fase 2, Sprint 6).
Sprint 3 reserva apenas o FK placeholder.

### Migrations

- [ ] Criar `tenant_configs` — um registro por tenant, criado no onboarding
      ```
      tenant_config_id              UUID PK
      company_id                    UUID FK UNIQUE NOT NULL

      -- Operacional
      timezone                      VARCHAR DEFAULT 'America/Sao_Paulo'
      soft_reservation_ttl_min      INTEGER DEFAULT 15
      draft_expiration_min          INTEGER DEFAULT 60
      requested_expiration_h        INTEGER DEFAULT 24
      no_show_threshold_min         INTEGER DEFAULT 30
      no_penalty_cancel_h           INTEGER DEFAULT 12
      require_payment_upfront       BOOLEAN DEFAULT false
      default_commission_pct        NUMERIC(5,2) DEFAULT 40.00

      -- Financeiro (placeholder — policy criada no Sprint 6)
      fee_routing_policy_id         UUID FK tenant_fee_routing_policies NULLABLE
        -- FK para tabela criada na Fase 2. NULL até lá.

      -- Contábil
      accounting_mode               Enum [CASH, ACCRUAL] DEFAULT 'CASH'
        -- trigger de banco bloqueia UPDATE para ACCRUAL no Estágio 0 (ver abaixo)

      -- RBAC opt-ins granulares
      permission_overrides          JSONB DEFAULT '{}'
        -- estrutura: { "OPERATOR": { "create_manual_adjustment": true,
        --                            "max_adjustment_amount": 50.00 } }

      updated_at                    TIMESTAMPTZ
      ```

      Trigger que bloqueia `accounting_mode = ACCRUAL`:
      ```sql
      CREATE OR REPLACE FUNCTION block_accrual_mode()
      RETURNS trigger AS $$
      BEGIN
        IF NEW.accounting_mode = 'ACCRUAL' THEN
          RAISE EXCEPTION 'accounting_mode ACCRUAL indisponível no Estágio 0';
        END IF;
        RETURN NEW;
      END;
      $$ LANGUAGE plpgsql;

      CREATE TRIGGER enforce_cash_mode
        BEFORE INSERT OR UPDATE ON tenant_configs
        FOR EACH ROW EXECUTE FUNCTION block_accrual_mode();
      ```

- [ ] Criar `module_activations`
      ```
      activation_id         UUID PK
      company_id            UUID FK NOT NULL
      module_name           Enum [ESTOQUE, COMISSOES, PACOTES, ASSINATURAS,
                                   PROMOCOES, CRM, NPS, FILA,
                                   BOT_WHATSAPP, LINK_PUBLICO]
      is_active             BOOLEAN DEFAULT false
      activated_at          TIMESTAMPTZ
      deactivated_at        TIMESTAMPTZ
      activated_by_user_id  UUID FK users
      UNIQUE(company_id, module_name)
      ```
      Seed no onboarding: todos inativos por padrão.

- [ ] Criar `tenant_brandings` — um registro por tenant
      ```
      branding_id       UUID PK
      company_id        UUID FK UNIQUE NOT NULL
      logo_url          VARCHAR
      primary_color     VARCHAR(7)
      secondary_color   VARCHAR(7)
      font_family       VARCHAR
      favicon_url       VARCHAR
      custom_texts      JSONB DEFAULT '{}'
      updated_at        TIMESTAMPTZ
      ```

- [ ] Criar `categories`
      ```
      category_id   UUID PK
      company_id    UUID FK NOT NULL
      name          VARCHAR NOT NULL
      entity_type   Enum [SERVICE, PRODUCT, EXPENSE]
      is_default    BOOLEAN DEFAULT false
      is_active     BOOLEAN DEFAULT true
      sort_order    INTEGER DEFAULT 0
      UNIQUE(company_id, name, entity_type)
      ```
      Seed no onboarding: categorias default por entity_type.
      `is_default=true`: desativáveis, não deletáveis.

### Services e routers

- [ ] `GET  /tenant/config` — OWNER/ADMIN; view: +OPERATOR
- [ ] `PUT  /tenant/config` — OWNER/ADMIN
      Validar: rejeitar `accounting_mode=ACCRUAL` (redundante com trigger, mas fail-fast no service)
      Nota: `fee_routing_policy_id` é read-only neste endpoint — gerenciado pelo Financial Core
      Após salvar:
      ```
      record_sensitive_action(
        action="update_config",
        resource_type="TenantConfig",
        resource_id=config.tenant_config_id,
        before_snapshot=config_before.dict(),
        after_snapshot=config_after.dict(),
      )
      ```

- [ ] `GET  /tenant/modules` — OWNER/ADMIN; view: +OPERATOR
- [ ] `POST /tenant/modules/{module}/activate` — OWNER/ADMIN
- [ ] `POST /tenant/modules/{module}/deactivate` — OWNER/ADMIN (dados preservados)

- [ ] `GET  /tenant/branding` — público (CLIENT vê no Link Público sem auth)
- [ ] `PUT  /tenant/branding` — OWNER/ADMIN; OPERATOR com `permission_overrides`

- [ ] `GET    /categories` — todos; filtro: `?entity_type=`
- [ ] `POST   /categories` — OWNER/ADMIN; OPERATOR com `permission_overrides`
- [ ] `PATCH  /categories/{id}` — OWNER/ADMIN
      ```
      Se category.is_default = true:
        Permitido:  is_active
        Bloqueado:  name, entity_type, sort_order → 422
                    "Categorias padrão só podem ser desativadas."
      Se category.is_default = false: todos os campos editáveis.
      ```
- [ ] `DELETE /categories/{id}` — OWNER/ADMIN; bloquear se `is_default=true` ou com entidades vinculadas

- [ ] **Hook de onboarding** — adicionar em `companies/service.py`, função `create_company`,
      após criar o registro de `company`:
      ```python
      # 1. TenantConfig com todos os defaults
      db.add(TenantConfig(company_id=company.id))

      # 2. ModuleActivation — um registro por módulo, todos inativos
      for module in ModuleName:
          db.add(ModuleActivation(company_id=company.id, module_name=module, is_active=False))

      # 3. TenantBranding vazio
      db.add(TenantBranding(company_id=company.id))

      # 4. Categories default por entity_type (is_default=True)
      DEFAULT_CATEGORIES = {
          EntityType.SERVICE:  ["Corte", "Barba", "Tratamento", "Combo", "Outros"],
          EntityType.PRODUCT:  ["Cuidado", "Finalização", "Ferramentas", "Outros"],
          EntityType.EXPENSE:  ["Aluguel", "Utilities", "Marketing", "Software",
                                "Contabilidade", "Limpeza", "Outros"],
      }
      for entity_type, names in DEFAULT_CATEGORIES.items():
          for i, name in enumerate(names):
              db.add(Category(company_id=company.id, name=name,
                              entity_type=entity_type, is_default=True, sort_order=i))
      ```
      Tudo na mesma transação do `create_company`.

- [ ] **Data migration para tenants existentes** — script Alembic one-shot
      (`migrations/versions/XXXX_seed_tenant_config_for_existing_companies.py`):
      ```python
      def upgrade():
          # Para cada company sem tenant_config: criar registros faltantes
          # usando os mesmos defaults do hook de onboarding acima
      ```
      Executar automaticamente via `alembic upgrade head`.

### Testes

- [ ] `PUT /tenant/config` com `accounting_mode=ACCRUAL` → 422 (e trigger também rejeita)
- [ ] `fee_routing_policy_id` não é alterável via `PUT /tenant/config` (ignorado ou 400)
- [ ] `PUT /tenant/config` alterando `default_commission_pct` → audit gravado com before/after
- [ ] Desativar módulo BOT_WHATSAPP: dados de bot preservados, is_active=false
- [ ] Category `is_default=true`: `DELETE` bloqueado; `PATCH is_active=false` permitido
- [ ] Category `is_default=true`: `PATCH name=...` → 422; `PATCH entity_type=...` → 422
- [ ] `GET /tenant/branding` sem autenticação → retorna dados públicos
- [ ] `create_company` → tenant_config, module_activations, branding e categories criados na mesma transação
- [ ] Company recém-criada: 7 categories de EXPENSE com is_default=true
- [ ] Data migration: company existente sem tenant_config recebe registros após `alembic upgrade head`

---

## Sprint 4 — Sistema de eventos e workers com garantia de entrega

**Objetivo:** event bus in-process com idempotência e workers migrados de asyncio para
Celery + Redis com retry, backoff exponencial e dead-letter.

### Infraestrutura

- [ ] Adicionar ao `requirements.txt`: `celery[redis]`, `redis`, `kombu`

- [ ] Criar `app/infrastructure/celery_app.py`
      ```python
      celery_app = Celery("paladino")
      celery_app.conf.update(
          broker_url=settings.REDIS_URL,
          result_backend=settings.REDIS_URL,
          task_serializer="json",
          accept_content=["json"],
          task_acks_late=True,
          task_reject_on_worker_lost=True,
          worker_prefetch_multiplier=1,
      )
      ```

- [ ] Criar `app/infrastructure/event_bus.py`
      ```python
      @dataclass
      class DomainEvent:
          event_id:        UUID
          event_type:      str
          occurred_at:     datetime
          company_id:      UUID | None
          idempotency_key: str
          actor:           dict   # { type: TENANT_USER|SYSTEM|CLIENT, id: UUID }
          payload:         dict

      class EventBus:
          def register(self, event_type: str, handler: Callable[[DomainEvent], None])
          def publish(self, event: DomainEvent) -> None
          # In-process no Estágio 0. Handlers chamados síncronos no mesmo request
          # para eventos rápidos; Celery task para eventos com side-effect pesado.
      ```

- [ ] Criar migration `processed_idempotency_keys`
      ```
      key            VARCHAR NOT NULL
      consumer       VARCHAR NOT NULL
      company_id     UUID
      processed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
      event_id       UUID NOT NULL
      result_summary VARCHAR
      PRIMARY KEY (key, consumer)
      INDEX ON processed_at (para cleanup worker)
      ```

- [ ] Criar `app/core/idempotency.py`
      ```python
      def is_processed(key: str, consumer: str, company_id: UUID | None, db: Session) -> bool
      def mark_processed(key: str, consumer: str, company_id: UUID | None,
                         event_id: UUID, db: Session) -> None
          # Executar em transação atômica com o processamento do evento
      ```

### Migrar workers para Celery

- [ ] `reminder_worker` → `@celery_app.task(bind=True, max_retries=5)`
      ```python
      autoretry_for=(Exception,)
      retry_backoff=True         # 1min, 2min, 4min, 8min, 16min
      retry_backoff_max=3600
      retry_jitter=True
      # Após max_retries: log ERROR + push para Redis list "dead_letter:{task_name}"
      ```
      Idempotência: campos `reminder_24h_sent` / `reminder_2h_sent` preservados.

- [ ] `session_cleanup_worker` → `@celery_app.task(bind=True, max_retries=3)`
      Retry backoff 5min entre tentativas.

- [ ] Remover `asyncio.create_task` do `lifespan` em `main.py`

- [ ] Criar `app/workers/beat_schedule.py`
      ```python
      beat_schedule = {
          "reminder-check":           { "task": "...", "schedule": crontab(minute="*/10") },
          "session-cleanup":          { "task": "...", "schedule": crontab(minute="*/5") },
          "idempotency-key-cleanup":  { "task": "...", "schedule": crontab(hour=3, minute=0) },
      }
      ```

- [ ] Atualizar `docker-compose.yml`: adicionar `redis`, `celery_worker`, `celery_beat`

### Primeiros handlers de eventos

**Atenção:** o modelo `Reservation` (SOFT/FIRME) só existe no Sprint 10 (Fase 3).
O que existe agora é `BookingSession` com TTL. Usar o nome correto:

- [ ] Handler: `booking_session.expired`
      ```
      Idempotency key: booking_session.expired:{booking_session_id}  (Padrão A)
      Ação: cancela BookingSession expirada, libera slot ocupado pelo TTL
      Consumer: "booking_session_cleanup"
      ```
      O evento `agenda.soft_reservation.expired` será registrado no Sprint 10
      quando o modelo `Reservation` existir.

- [ ] Handler: `appointment.reminder_due`
      ```
      Idempotency key: appointment.reminder_due:{appointment_id}:{interval}  (Padrão B)
      Ação: despacha para CommunicationService (criado no Sprint 5)
      Consumer: "appointment_reminder"
      ```

### Testes

- [ ] Worker falha na primeira tentativa → retry automático com backoff
- [ ] Worker falha 5 vezes → entra em dead-letter, processo não crasha
- [ ] Evento publicado duas vezes com mesma `idempotency_key` + consumer → executa uma vez
- [ ] `mark_processed` falha: processamento não grava a key (transação atômica)
- [ ] BookingSession expirada → slot liberado, não reaparece como disponível
- [ ] Celery Beat: tasks agendadas aparecem no worker log no intervalo correto

---

## Sprint 5 — Sistema de comunicação e credenciais de integração

**Objetivo:** substituir mensagens hardcoded por sistema de comunicação configurável;
criar modelo centralizado de credenciais que será reutilizado por Asaas (Sprint 8)
e demais integrações.

### Migrations

- [ ] Criar `integration_credentials` — modelo centralizado para todas as integrações
      ```
      credential_id     UUID PK
      company_id        UUID FK NOT NULL
      provider          Enum [WHATSAPP_EVOLUTION, WHATSAPP_META, SMTP, ASAAS]
        -- SUPABASE_STORAGE não entra: é credencial de plataforma (var de ambiente),
        -- não de tenant. ASAAS preparado aqui para o Sprint 8 (Fase 2) não exigir ALTER TYPE.
      label             VARCHAR   -- ex: "WhatsApp principal"
      secret_encrypted  TEXT NOT NULL   -- criptografado em repouso; NUNCA retornado em GET
      masked_preview    VARCHAR         -- ex: "***•••4Xy2" (últimos 4 chars)
      config            JSONB DEFAULT '{}'
        -- Configuração não-secreta, específica por provider. Retornada nas respostas de API.
        -- WHATSAPP_EVOLUTION: { "server_url": "https://...", "instance_name": "..." }
        -- WHATSAPP_META:      { "phone_number_id": "...", "waba_id": "..." }
        -- SMTP:               { "host": "smtp.gmail.com", "port": 587, "from_address": "noreply@..." }
        -- ASAAS:              { "environment": "sandbox" }  -- "production" em produção
      status            Enum [ACTIVE, REVOKED] DEFAULT 'ACTIVE'
      created_by        UUID FK users NOT NULL
      created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
      revoked_at        TIMESTAMPTZ
      revoked_by        UUID FK users
      ```
      RBAC-3: `secret_encrypted` nunca aparece em resposta de API.

      **Implementação obrigatória de encryption** (para consistência com Sprint 8/Asaas):
      ```
      Biblioteca: cryptography>=42.0 (adicionar ao requirements.txt)
      Algoritmo:  Fernet — AES-128-CBC + HMAC-SHA256

      Chave: env var CREDENTIAL_ENCRYPTION_KEY
        — 32 bytes URL-safe base64, gerada com: Fernet.generate_key()
        — obrigatória em produção; KeyError se ausente
        — nunca commitada no repositório

      Criar app/core/encryption.py:
        def encrypt_secret(plaintext: str) -> str:
            return Fernet(settings.CREDENTIAL_ENCRYPTION_KEY).encrypt(
                plaintext.encode()
            ).decode()

        def decrypt_secret(ciphertext: str) -> str:
            # Usado APENAS internamente em test_connection
            # Nunca retornar o resultado em resposta de API
            return Fernet(settings.CREDENTIAL_ENCRYPTION_KEY).decrypt(
                ciphertext.encode()
            ).decode()

        def make_masked_preview(plaintext: str) -> str:
            return f"***•••{plaintext[-4:]}"

      Escrita: secret_encrypted = encrypt_secret(secret)
               masked_preview   = make_masked_preview(secret)
      Leitura: apenas decrypt_secret() em test_connection, internamente
      ```

- [ ] Criar `communication_settings` — referencia credenciais por FK (sem armazenar segredo)
      ```
      settings_id              UUID PK
      company_id               UUID FK UNIQUE NOT NULL
      whatsapp_enabled         BOOLEAN DEFAULT false
      whatsapp_credential_id   UUID FK integration_credentials NULLABLE
      whatsapp_api_type        Enum [UNOFFICIAL_BAILEYS, OFFICIAL_META] DEFAULT 'UNOFFICIAL_BAILEYS'
      email_enabled            BOOLEAN DEFAULT false
      smtp_credential_id       UUID FK integration_credentials NULLABLE
      quiet_hours_enabled      BOOLEAN DEFAULT true
      quiet_hours_start        TIME DEFAULT '22:00'
      quiet_hours_end          TIME DEFAULT '08:00'
      updated_at               TIMESTAMPTZ
      ```

- [ ] Criar `communication_templates`
      ```
      template_id    UUID PK
      company_id     UUID FK NOT NULL
      event_type     VARCHAR NOT NULL
      channel        Enum [WHATSAPP, EMAIL, SMS]
      audience       Enum [CLIENT, PROFESSIONAL, OWNER]
      body_template  TEXT NOT NULL
        -- variáveis: {{cliente_nome}}, {{horario}}, {{servico}},
        --            {{profissional}}, {{link_gestao}}, {{empresa_nome}}
      is_active      BOOLEAN DEFAULT true
      is_default     BOOLEAN DEFAULT false
      UNIQUE(company_id, event_type, channel, audience)
      ```

- [ ] Criar `communication_logs`
      ```
      log_id             UUID PK
      company_id         UUID FK NOT NULL
      template_id        UUID FK NULLABLE
      event_type         VARCHAR NOT NULL
      channel            Enum [WHATSAPP, EMAIL, SMS]
      recipient_id       UUID NOT NULL
      recipient_type     Enum [CLIENT, PROFESSIONAL, OWNER]
      status             Enum [SENT, FAILED, SKIPPED_QUIET_HOURS,
                                SKIPPED_NO_CONSENT, SKIPPED_CHANNEL_DISABLED,
                                SKIPPED_NO_TEMPLATE, SCHEDULED]
      scheduled_send_at  TIMESTAMPTZ NULLABLE
        -- preenchido quando mensagem cai em quiet_hours mas deve ser entregue
        -- worker de drain processa registros com status=SCHEDULED e scheduled_send_at <= now()
      rendered_body      TEXT
      sent_at            TIMESTAMPTZ
      error_message      TEXT
      created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
      ```

### Service

- [ ] Criar `app/modules/communication/service.py`
      ```python
      class CommunicationService:
          def dispatch(
              self,
              event_type: str,
              company_id: UUID,
              context: dict,
              recipient_id: UUID,
              recipient_type: str,
              db: Session,
          ) -> CommunicationLog:
              """
              1. Busca CommunicationSettings — canal habilitado?
                 Se não: log SKIPPED_CHANNEL_DISABLED, retorna.
              2. Verifica quiet_hours:
                 Se quiet_hours_enabled e agora está no período:
                   — Para eventos de lembrete (appointment.reminder_*):
                       criar log com status=SCHEDULED e
                       scheduled_send_at = próximo quiet_hours_end
                   — Para outros eventos (confirmação, cancelamento):
                       criar log com status=SKIPPED_QUIET_HOURS e retornar
              3. Busca template ativo para (event_type, channel, audience).
                 Se não encontrado: log SKIPPED_NO_TEMPLATE, retorna.
              4. ConsentRecord: Sprint 20. Skip gracioso por ora.
              5. Renderiza template (substituição {{variavel}} → context[variavel]).
              6. Envia via canal.
              7. Log com status SENT ou FAILED.
              """

          def drain_scheduled(self, db: Session) -> int:
              """
              Chamado pelo Celery Beat a cada 5 min.
              Processa communication_logs com status=SCHEDULED
              e scheduled_send_at <= now().
              Retorna quantidade de mensagens enviadas.
              """
      ```

- [ ] Adicionar ao `beat_schedule`:
      ```python
      "communication-drain": {
          "task": "app.workers.communication.drain_scheduled",
          "schedule": crontab(minute="*/5"),
      }
      ```

- [ ] Registrar handlers no EventBus:
      ```
      appointment.confirmed     → dispatch CLIENT + PROFESSIONAL
      appointment.cancelled     → dispatch CLIENT
      appointment.reminder_24h  → dispatch CLIENT (lembrete → enfileirar se quiet_hours)
      appointment.reminder_2h   → dispatch CLIENT (lembrete → enfileirar se quiet_hours)
      appointment.no_show       → dispatch PROFESSIONAL + OWNER
      ```

- [ ] Substituir todas as chamadas diretas a `evolution_client.send_text()`
      em `notifications.py` e handlers do bot pelo `CommunicationService.dispatch()`

- [ ] **Seeds de templates default** — criar via hook de onboarding em `create_company`
      e via data migration para tenants existentes (mesmo padrão do Sprint 3).
      Lista mínima obrigatória (todos com `is_default=true`, `is_active=true`):
      ```
      event_type               channel    audience
      appointment.confirmed    WHATSAPP   CLIENT
      appointment.confirmed    WHATSAPP   PROFESSIONAL
      appointment.cancelled    WHATSAPP   CLIENT
      appointment.reminder_24h WHATSAPP   CLIENT
      appointment.reminder_2h  WHATSAPP   CLIENT
      appointment.no_show      WHATSAPP   PROFESSIONAL
      appointment.no_show      WHATSAPP   OWNER
      ```

- [ ] **Migração de `whatsapp_connection` → `integration_credentials`**

      A tabela `whatsapp_connection` existe no código atual e é lida pelos 13 handlers
      do bot. Após o Sprint 5, ambas as tabelas coexistiriam com credenciais duplicadas.
      Resolver neste sprint:

      ```
      Script de data migration (Alembic):
        Para cada registro em whatsapp_connection:
          1. encrypt_secret(whatsapp_connection.token)
          2. Criar integration_credentials com
               provider=WHATSAPP_EVOLUTION,
               label="WhatsApp (migrado)",
               secret_encrypted=<resultado>,
               masked_preview=make_masked_preview(token),
               config={
                 "server_url": whatsapp_connection.server_url,  -- campo equivalente
                 "instance_name": whatsapp_connection.instance_name
               },
               company_id=whatsapp_connection.company_id
          3. Criar communication_settings para o tenant com
               whatsapp_credential_id=<novo credential_id>,
               whatsapp_enabled=True
      ```

      Atualizar handlers do bot (`modules/whatsapp/`):
        - Ler credencial via `communication_settings → integration_credentials`
        - Usar `decrypt_secret()` internamente ao montar o client
        - Não ler mais de `whatsapp_connection` diretamente
        - Manter tabela `whatsapp_connection` como deprecated (não dropar neste sprint;
          remover apenas após validar que nenhum código a lê)

### Routers

- [ ] `POST   /integrations/credentials` — OWNER/ADMIN
      Body: `{ provider, label, secret, config? }` → grava secret criptografado
      Retorna: `{ credential_id, masked_preview, config }`  — config retornado; secret nunca
- [ ] `GET    /integrations/credentials` — OWNER/ADMIN
      Retorna lista com `masked_preview` — **nunca `secret_encrypted`** (RBAC-3)
- [ ] `POST   /integrations/credentials/{id}/rotate` — OWNER/ADMIN
      Body: `{ new_secret }` → revoga antiga, cria nova. record_sensitive_action.
- [ ] `POST   /integrations/credentials/{id}/revoke` — OWNER/ADMIN
      record_sensitive_action.
- [ ] `POST   /integrations/credentials/{id}/test` — OWNER/ADMIN
      ```
      → record_sensitive_action(action="test_connection",
                                resource_type="IntegrationCredential",
                                resource_id=id)
      → testa conectividade sem revelar secret
      → retorna { success: bool, latency_ms?, error_message? }
      ```

- [ ] `GET    /communication/settings` — OWNER/ADMIN
      Retorna settings com `masked_preview` das credenciais vinculadas (nunca secret)
- [ ] `PUT    /communication/settings` — OWNER/ADMIN
      Aceita `whatsapp_credential_id` e `smtp_credential_id` como FKs

- [ ] `GET    /communication/templates` — OWNER/ADMIN; OPERATOR (templates operacionais)
- [ ] `POST   /communication/templates` — OWNER/ADMIN
- [ ] `PUT    /communication/templates/{id}`
      ```
      OWNER/ADMIN: sempre
      OPERATOR: se permission_overrides["OPERATOR"]["update_operational_templates"] = true
                E template.is_default = false
                (OPERATOR não altera templates default)
      ```
- [ ] `DELETE /communication/templates/{id}` — OWNER/ADMIN
      `is_default=true`: apenas desativáveis, não deletáveis

- [ ] `GET    /communication/logs` — OWNER/ADMIN; OPERATOR config
      Filtros: `event_type`, `status`, `channel`, `date_range`

### Testes

- [ ] `appointment.reminder_2h` em quiet_hours → log `SCHEDULED`, `scheduled_send_at` definido
- [ ] `appointment.confirmed` em quiet_hours → log `SKIPPED_QUIET_HOURS` (não enfileirado)
- [ ] `drain_scheduled` processa logs `SCHEDULED` após fim do quiet_hours
- [ ] `appointment.reminder_*` fora de quiet_hours → log `SENT`
- [ ] `GET /integrations/credentials` → `secret_encrypted` ausente da resposta; `masked_preview` presente
- [ ] `encrypt_secret` + `decrypt_secret` round-trip: decrypt(encrypt(x)) == x
- [ ] `make_masked_preview("abcdef1234")` → `"***•••1234"`
- [ ] `CREDENTIAL_ENCRYPTION_KEY` ausente nas env vars → startup falha com erro claro
- [ ] `rotate` credential → antiga revogada, nova ativa, `record_sensitive_action` gravado
- [ ] `POST /integrations/credentials/{id}/test` → `record_sensitive_action` gravado com action=test_connection
- [ ] `GET /communication/settings` → retorna `masked_preview`, não secret
- [ ] Template `is_default=true`: `DELETE` bloqueado
- [ ] Canal desabilitado → log `SKIPPED_CHANNEL_DISABLED`
- [ ] Template ausente → log `SKIPPED_NO_TEMPLATE`, sem crash
- [ ] OPERATOR com `update_operational_templates=true` → `PUT /communication/templates/{id}` permitido para template não-default
- [ ] OPERATOR sem override → `PUT /communication/templates/{id}` → 403
- [ ] Data migration: tenant com `whatsapp_connection` existente → `integration_credentials` criado,
      `communication_settings.whatsapp_credential_id` apontando para ele
- [ ] Após migração: handlers do bot não leem mais de `whatsapp_connection` diretamente
- [ ] Company recém-criada: 7 templates de WHATSAPP criados com is_default=true

---

## Critérios de conclusão da Fase 1

```bash
pytest tests/test_sprint1_security.py -v
  ✓ EXCLUDE CONSTRAINT com company_id rejeita appointment sobreposto no banco
  ✓ CANCELLED/NO_SHOW não ativam a constraint
  ✓ POST /auth/login → 429 após 10 req/min com Retry-After
  ✓ Todos os endpoints retornam os 3 security headers
  ✓ Upload grava no Supabase, retorna URL válida

pytest tests/test_sprint2_rbac.py -v
  ✓ Enum tem 9 valores (incluindo PLATFORM_SUPPORT/BILLING/READONLY)
  ✓ POST /users/invite com role=PLATFORM_SUPPORT → 422
  ✓ POST /users/invite por OWNER do tenant com role=PLATFORM_OWNER → 403
  ✓ PATCH /users/{id}/role com role=PLATFORM_BILLING → 422
  ✓ PATCH /users/{id}/role por ADMIN com role=PLATFORM_OWNER → 403
  ✓ Ativação PLATFORM_OWNER → User com company_id=NULL
  ✓ Ativação OPERATOR → User com company_id do tenant
  ✓ company_id nullable em User
  ✓ ADMIN não convida ADMIN nem OWNER (403)
  ✓ Token ativação: segundo uso → 410; expirado → 410
  ✓ Ativação: User criado, JWT, token invalidado
  ✓ SensitiveAuditContext gravado para invite_user e assign_role
  ✓ record_sensitive_action sem reason para invite_user → sem erro
  ✓ record_sensitive_action sem reason para export_audit → ValueError
  ✓ PATCH /users/{id}/role → audit gravado com before/after
  ✓ GET /audit/logs com PROFESSIONAL → 403
  ✓ GET /audit/logs/export grava audit de export_audit
  ✓ POST /users/transfer-ownership por não-OWNER → 403
  ✓ Transfer bem-sucedida → audit com action=transfer_ownership e before/after

pytest tests/test_sprint3_config.py -v
  ✓ PUT TenantConfig accounting_mode=ACCRUAL → 422
  ✓ fee_routing_policy_id não é alterável via PUT /tenant/config
  ✓ PUT /tenant/config → audit gravado com before/after
  ✓ Desativar módulo: is_active=false, dados preservados
  ✓ Category is_default: DELETE bloqueado
  ✓ Category is_default: PATCH name → 422; PATCH is_active=false → permitido

pytest tests/test_sprint4_workers.py -v
  ✓ Worker: retry com backoff após falha
  ✓ Worker: dead-letter após 5 tentativas, processo estável
  ✓ Evento duplicado: handler executa exatamente uma vez
  ✓ BookingSession expirada: slot liberado
  ✓ Nenhum handler registrado como agenda.soft_reservation.expired (nome errado)

pytest tests/test_sprint5_communication.py -v
  ✓ reminder_2h em quiet_hours → SCHEDULED (não SKIPPED)
  ✓ confirmed em quiet_hours → SKIPPED_QUIET_HOURS (não SCHEDULED)
  ✓ drain_scheduled envia mensagens SCHEDULED após fim do período
  ✓ encrypt/decrypt round-trip; masked_preview formato correto
  ✓ CREDENTIAL_ENCRYPTION_KEY ausente → startup falha com erro claro
  ✓ GET /integrations/credentials → sem secret_encrypted; masked_preview presente
  ✓ test_connection → record_sensitive_action gravado
  ✓ appointment.confirmed → CommunicationLog SENT
  ✓ Template is_default: DELETE bloqueado
  ✓ OPERATOR com override → PUT /communication/templates permitido
  ✓ OPERATOR sem override → PUT /communication/templates → 403
  ✓ Data migration: whatsapp_connection → integration_credentials criado
  ✓ Bot handlers não leem whatsapp_connection diretamente após migração
```

**Estado de saída — contratos estáveis para a Fase 2:**

```
✓ EventBus funcional com idempotência (ProcessedIdempotencyKey)
✓ Celery + Redis com retry, backoff e dead-letter
✓ 9 papéis no enum; anti-escalonamento enforced
✓ ActionScope enum + require_action(action, scope) em deps.py
✓ SensitiveAuditContext compartilhado; audit_logs append-only com endpoints
✓ TenantConfig completo (sem fee_routing — FK placeholder para Fase 2)
✓ ModuleActivation, TenantBranding, Category criados
✓ integration_credentials como modelo centralizado (Asaas usará na Fase 2)
✓ integration_credentials com Fernet (CREDENTIAL_ENCRYPTION_KEY); sem secret em API
✓ whatsapp_connection migrada → integration_credentials; bot handlers atualizados
✓ CommunicationService substituindo chamadas diretas ao Evolution API
✓ quiet_hours: lembretes enfileirados (SCHEDULED), não descartados
✓ EXCLUDE CONSTRAINT com company_id ativo em appointments
✓ Supabase Storage para uploads
```

---

## Restrições desta fase

- **NÃO** criar `TenantFeeRoutingPolicy` — pertence ao Financial Core (Fase 2, Sprint 6).
- **NÃO** criar modelos financeiros (`Account`, `Movement`, `Entry`, `Payment`) — Fase 2.
- **NÃO** criar modelos de Operações (`Operation`, `CommissionRecord`) — Fase 3+.
- **NÃO** alterar a lógica do BookingEngine além do EXCLUDE CONSTRAINT.
- **NÃO** criar UI para os módulos desta fase — foco exclusivo em backend.
- **NÃO** usar `agenda.soft_reservation.expired` como nome de evento — modelo ainda não existe.
- Confirmar que os testes de cada sprint passam antes de avançar ao próximo.

---

## Notas para briefs das fases seguintes

- **Fase 2 / Sprint 6:** criar `TenantFeeRoutingPolicy` (modelo próprio do Financial Core)
  e atualizar FK `tenant_configs.fee_routing_policy_id`.

- **Fase 2 / Sprint 7:** adicionar `ExternalStatementEntry` + endpoint `import_statement`
  + eventos: `statement.imported`, `reconciliation.matched`,
  `reconciliation.orphan_flagged`, `reconciliation.orphan_dismissed`.

- **Fase 3 / Sprint 10:** registrar handler `agenda.soft_reservation.expired`
  quando modelo `Reservation` (SOFT/FIRME) for criado.

- **Fase 5 / Sprint 17:** adicionar `SupplierCredit` (modelo + service + 4 eventos);
  corrigir `Payable.payment_terms` para enum completo:
  `CASH | CREDIT | INSTALLMENTS | CONSIGNMENT | ADVANCE`
  (`CONSIGNMENT` e `ADVANCE`: [SCHEMA APENAS] no Estágio 0).

---

*Fonte: `visao-estagio-0.md` v23.0 · `plano-execucao-estagio-0.md`*
