# Plano de execução — Fase 1
**Gerado em:** 2026-05-22
**Produto em produção:** SIM — Bot WhatsApp (13 handlers FSM), BookingEngine e Link Público ativos.
**Baseado em:** `brief-fase1-fundacao.md` v2 · `visao-estagio-0.md` v1 · varredura de código 2026-05-21/22

---

## Resumo executivo

A Fase 1 entrega cinco fundações: hardening de segurança, RBAC completo de 9 papéis (6 ativos + 3 schema-only), TenantConfig com onboarding consistente, workers com garantia de entrega (Celery+Redis) e CommunicationService com credenciais criptografadas. Nenhum dos cinco sprints muda o **comportamento** do BookingEngine, do bot ou do Link Público — todos são adições laterais ou refactors transparentes ao usuário final.

**Mudam comportamento (risco real):**
- Sprint 1: `EXCLUDE CONSTRAINT` em `appointments` **(requer verificação prévia de overlaps históricos)**; substituição de uploads locais por Supabase Storage **(URLs antigas em uso)**
- Sprint 2: `User.role` String → Enum **(ALTER TYPE em produção)**; refactor de `POST /users` para fluxo de convite **(quebra contrato antigo)**
- Sprint 4: migração de workers asyncio → Celery **(coexistência durante validação, depois remoção)**
- Sprint 5: `notifications.py` deixa de chamar `evolution_client` diretamente

**Não mudam, apesar de aparentarem:**
- Sprint 1 / `bcrypt__rounds=12` — passlib 1.7 + bcrypt 4.0.1 já usa rounds=12 como default. Hashes existentes continuam compatíveis. Apenas explicita o que já é o comportamento atual.
- Sprint 4 / EventBus — handlers são adicionados; chamadas síncronas existentes permanecem até o Sprint 5 substituir gradualmente

**Não cabem no Brief atual, marcado como ⛔ requer decisão:**
- **Migração `whatsapp_connection → integration_credentials`** (Sprint 5): o modelo `whatsapp_connection` real **não tem `token` nem `server_url`** — apenas `instance_name`, `status`, `qr_code`. A credencial Evolution API (URL e API key) está em `settings` global, não por tenant. A "migração" descrita no brief assume um schema que não existe. Detalhes na seção dedicada abaixo.

**Riscos principais e mitigações:**
1. Banco com appointment overlaps históricos → SQL de verificação antes do Sprint 1.
2. Frontend chamando `POST /users` com senha → expand-contract; manter endpoint antigo durante 1 sprint.
3. Workers de lembrete duplicados (asyncio + Celery em paralelo) → flags idempotentes `reminder_24h_sent`/`reminder_2h_sent` já protegem; sem dupla entrega.
4. Migração de URLs de upload em produção → dual-write + script de rollback testado em staging.

---

## Pré-requisitos antes de iniciar o Sprint 1

Antes de qualquer migration do Sprint 1, executar esta query no banco de produção e validar resultado:

```sql
-- Detecta appointments sobrepostos do mesmo profissional na mesma empresa
SELECT
  a.id AS id_a, b.id AS id_b,
  a.company_id, a.professional_id,
  a.start_at AS start_a, a.end_at AS end_a,
  b.start_at AS start_b, b.end_at AS end_b,
  a.status AS status_a, b.status AS status_b
FROM appointments a
JOIN appointments b
  ON a.company_id = b.company_id
 AND a.professional_id = b.professional_id
 AND a.id < b.id
 AND tsrange(a.start_at, a.end_at, '[)') && tsrange(b.start_at, b.end_at, '[)')
WHERE a.status NOT IN ('CANCELLED', 'NO_SHOW')
  AND b.status NOT IN ('CANCELLED', 'NO_SHOW');
```

**Resultado esperado:** 0 linhas. A proteção em camada de aplicação (`_assert_slot_available` + `SELECT FOR UPDATE NOWAIT`) deve ter prevenido qualquer overlap.

**Resultado em 2026-05-22:** ✅ **0 linhas retornadas.** Proteção aplicacional histórica funcionou. EXCLUDE CONSTRAINT pode ser aplicada sem necessidade de remediação prévia de dados.

**Se retornar ≥ 1 linha (não foi o caso aqui):** **PARAR**. Reportar ao usuário com o conjunto completo de linhas. A migration do Sprint 1 vai falhar e exige decisão de negócio (cancelar um dos appointments, mover horário, etc.) antes de prosseguir.

**Outros pré-requisitos:**
- Extensão `btree_gist` ativa no Postgres: `SELECT * FROM pg_extension WHERE extname = 'btree_gist';`
- Conta Supabase Storage com bucket público criado (`uploads`)
- Variável `CREDENTIAL_ENCRYPTION_KEY` gerada e armazenada em vault (Sprint 5)
- Acesso ao Railway com plano que suporta Redis + Celery worker como serviços separados (Sprint 4)

---

## Classificação de risco por sprint

Legenda: 🟢 Adição segura · 🟡 Extensão controlada · 🔴 Mudança de risco · ⛔ Requer decisão

### Sprint 1 — Segurança e infraestrutura crítica

| Tarefa | Class. | Estratégia de migração |
|--------|--------|------------------------|
| `EXCLUDE CONSTRAINT` em `appointments` (com `company_id`, usando `start_at`/`end_at`) | 🔴 | **Pré-requisito:** SQL de verificação acima retornando 0 linhas. **Migration:** `CREATE EXTENSION IF NOT EXISTS btree_gist` + `ALTER TABLE ... ADD CONSTRAINT`. Single transaction; lock breve. Sem rollback de dados — apenas drop da constraint se falhar. Tempo estimado: < 5s no banco atual. |
| `slowapi` + rate limit em `/auth/login` (10 req/min/IP) | 🟢 | Adição pura. Middleware novo. Sem impacto em comportamento existente. |
| Security headers (X-Content-Type-Options, X-Frame-Options, HSTS) | 🟢 | Adição pura. Middleware novo. Headers adicionais não quebram clientes existentes. Atenção: `HSTS` força HTTPS pelo período — confirmar que produção já está em HTTPS antes de habilitar `max-age` longo. |
| `bcrypt__rounds=12` explícito em `core/security.py` | 🟡 | Sem efeito prático — passlib + bcrypt 4.0.1 já usa rounds=12 como default. Hashes antigos `$2b$12$...` continuam válidos. Apenas blinda contra mudança futura de default da biblioteca. |
| Migrar uploads para Supabase Storage | 🔴 | **Estratégia expand-contract em 3 etapas:** (a) endpoint novo grava em Supabase + retorna URL nova; antigo grava local + retorna URL antiga, ainda servido; (b) script de migração copia arquivos existentes para Supabase e atualiza colunas `image_url`/`logo_url` etc. no banco; (c) remover endpoint antigo + `os.makedirs("static/uploads")` + montagem `/static` do `main.py` somente após confirmar 100% das URLs atualizadas. **Rollback:** restaurar volume + reverter colunas — script de rollback escrito ANTES do go-live. |

### Sprint 2 — RBAC: papéis, convite e auditoria

| Tarefa | Class. | Estratégia de migração |
|--------|--------|------------------------|
| `User.company_id` → `nullable=True` | 🟡 | `ALTER COLUMN ... DROP NOT NULL`. Sem impacto em dados. **Cuidado de código:** `core/deps.py:38-40` (`get_current_company_id`) precisa ser refatorado no mesmo PR para tratar `None` (PLATFORM_OWNER) sem retornar 500. Aplicar refactor da dep antes de fazer deploy da migration. |
| `User.role: String(20)` → Enum `userrole` com 9 valores | 🔴 | **Estratégia ALTER TYPE direto, pois valores atuais (`ADMIN`, `PROFESSIONAL`, `CLIENT`) estão presentes no enum novo:** `CREATE TYPE userrole AS ENUM (...)` + `ALTER TABLE users ALTER COLUMN role TYPE userrole USING role::userrole`. Postgres adquire `AccessExclusiveLock` brevemente; com 1 cliente, janela é < 1s. **Validação prévia:** `SELECT DISTINCT role FROM users` deve retornar somente `ADMIN`, `PROFESSIONAL`, `CLIENT` — qualquer valor fora disso faz a migration falhar. **Inclui PLATFORM_SUPPORT/BILLING/READONLY no enum já no Sprint 2** (visão deixa explícito `[SCHEMA APENAS]`) — evita `ALTER TYPE ADD VALUE` posterior. |
| Criar tabela `user_invitations` | 🟢 | Adição pura. |
| Criar tabela `audit_logs` (sem FKs cross-tabela) | 🟢 | Adição pura. Sem FK por design — audit não bloqueia cascade delete em outras tabelas. |
| Refactor `core/deps.py`: `require_role`, `require_action`, `get_current_company_id` PLATFORM_OWNER-aware | 🟡 | **Manter `require_admin` durante este sprint** (todos os routers existentes usam). Adicionar `require_role(*roles)` + `require_action(action, scope)` como novos. **Cuidado:** `require_action` consulta `tenant_configs.permission_overrides` que só existe no Sprint 3 — usar fallback `{}` gracioso enquanto a tabela não existir, conforme o brief já especifica. |
| `POST /users/invite` (novo) + `POST /auth/activate` (novo) | 🟢 | Adição pura. |
| `POST /users` (antigo — aceita senha no body) | 🔴 | **Manter funcionando durante este sprint** mesmo com fluxo novo disponível. Adicionar header `Deprecation: true` + log de uso. Remover no Sprint 3 após validar que nenhum cliente usa. **Validar no frontend atual antes de remover** — verificar se o painel chama essa rota em algum lugar (atualmente o painel não tem UI de criação de usuários, mas confirmar via grep no `painel/`). |
| Anti-escalonamento, `PATCH /users/{id}/role`, `DELETE /users/{id}`, `transfer-ownership` | 🟢 | Adição pura. Lógica nova em service novo. |
| `GET /audit/logs`, `GET /audit/logs/export` | 🟢 | Adição pura. |

### Sprint 3 — TenantConfig, módulos e branding

| Tarefa | Class. | Estratégia de migração |
|--------|--------|------------------------|
| Tabela `tenant_configs` + trigger `block_accrual_mode` | 🟢 | Adição pura. Trigger só impede `ACCRUAL`, default `CASH`. |
| Tabela `module_activations` | 🟢 | Adição pura. |
| Tabela `tenant_brandings` | 🟢 | Adição pura. |
| Tabela `categories` | 🟢 | Adição pura. |
| Hook de onboarding em `companies/service.create_company` — cria 4 registros na mesma transação | 🟡 | **Extensão controlada.** `companies/service.create_company` existe e cria Company hoje. Adicionar 4 inserts na mesma transação. Risco: se uma migration falhar parcialmente, `create_company` quebra em produção. **Mitigação:** ordem dos inserts dentro de transação; teste de integração antes do deploy. |
| Data migration: backfill para tenants existentes | 🔴 | **Estratégia idempotente.** Script Alembic com `ON CONFLICT (company_id) DO NOTHING` para cada tabela. Roda no `alembic upgrade head` automaticamente. **Validar antes:** quantas companies hoje? Listar IDs. **Após:** confirmar que cada company tem 1 tenant_config, 10 module_activations (uma por módulo), 1 tenant_branding, 16 categories default (5+4+7). |
| Endpoints `/tenant/config`, `/tenant/modules`, `/tenant/branding`, `/categories` | 🟢 | Adição pura. |
| **Migrar 15 routers existentes de `require_admin` → `require_role("ADMIN")` (e, onde fizer sentido, `require_action(action, scope)`)** | 🟡 | **Tarefa obrigatória do Sprint 3** — sem ela, o RBAC granular do Sprint 2/3 funciona **apenas para endpoints novos**. Endpoints existentes (`/appointments`, `/customers`, `/professionals`, `/services`, `/schedule`, `/whatsapp`, `/companies`, `/users`, `/products`, `/uploads`, `/profile`) continuariam com autorização binária ADMIN-ou-nada — bloqueando OPERATOR/PROFESSIONAL de tudo. **Ordem:** (1) substituir `require_admin` por `require_role("ADMIN")` em todos os routers (comportamento idêntico — refactor mecânico). (2) Refinar para `require_action(action, scope)` onde papéis OPERATOR/PROFESSIONAL devem ter acesso parcial (ex: PROFESSIONAL em `/appointments` com scope OWN). (3) Remover `require_admin` de `core/deps.py` quando `grep -r "require_admin" app/modules/` retornar 0 matches. |
| Remover `POST /users` antigo (deprecado no Sprint 2) | 🔴 | Verificar logs de uso do Sprint 2 antes de remover. Se zero chamadas em 2 semanas → remover. Senão → reportar quem está chamando e estender prazo. |

### Sprint 4 — Sistema de eventos e workers

| Tarefa | Class. | Estratégia de migração |
|--------|--------|------------------------|
| Adicionar `celery[redis]`, `redis`, `kombu` ao `requirements.txt` | 🟢 | Adição pura. |
| Criar `celery_app.py` + `event_bus.py` + `processed_idempotency_keys` + `idempotency.py` | 🟢 | Adição pura. |
| Migrar `reminder_worker` para Celery Beat | 🔴 | **Estratégia coexistência → flip.** (1) Sprint 4 sobe Celery worker + beat em paralelo aos workers asyncio existentes. (2) Validar em staging 1 semana com tráfego sintético. (3) Em produção: rodar ambos por 24h — flags `reminder_24h_sent`/`reminder_2h_sent` garantem que não há duplicata (quem chegar primeiro marca a flag). (4) Após 24h sem erros no Sentry: remover registro de workers do `lifespan` em `main.py`. **Rollback:** reativar `asyncio.create_task` no lifespan; Celery worker para de processar. |
| Migrar `session_cleanup_worker` para Celery Beat | 🔴 | Mesma estratégia que reminder_worker. Worker de cleanup é menos crítico (atraso na limpeza não afeta cliente final). |
| Remover `asyncio.create_task` do `lifespan` em `main.py` | 🔴 | **Última etapa do Sprint 4.** Só executar após 24h de coexistência sem erros. |
| Beat schedule (`reminder-check`, `session-cleanup`, `idempotency-key-cleanup`) | 🟢 | Adição pura. |
| `docker-compose.yml`: redis + celery_worker + celery_beat | 🟡 | Extensão controlada. Não afeta produção (Railway), apenas dev local. Railway: serviços adicionais configurados separadamente. |
| Handler `booking_session.expired` | 🟢 | Adição pura. Nota do brief sobre **não usar `agenda.soft_reservation.expired`** (modelo Reservation só vem na Fase 3) está correta — usar nome `booking_session.expired`. |
| Handler `appointment.reminder_due` | 🟡 | Substitui parte da lógica do `reminder_worker.py` atual. Coexistência durante migração: worker antigo chama `evolution_client.send_text` direto; worker Celery novo publica evento que é consumido pelo handler (que ainda chama o mesmo cliente HTTP até o Sprint 5 introduzir o CommunicationService). |

### Sprint 5 — Comunicação e credenciais

| Tarefa | Class. | Estratégia de migração |
|--------|--------|------------------------|
| `cryptography` no `requirements.txt` | 🟢 | **Já presente** (`cryptography==46.0.7`) — confirmado no `requirements.txt` atual. Sem ação necessária. |
| `app/core/encryption.py` com Fernet | 🟢 | Adição pura. |
| Variável de ambiente `CREDENTIAL_ENCRYPTION_KEY` | 🔴 | **Decisão de operações.** Gerar com `Fernet.generate_key()`, armazenar em vault Railway. **Validação obrigatória no startup:** se ausente → startup falha com erro claro (`KeyError: CREDENTIAL_ENCRYPTION_KEY ausente`). Backup da chave em local seguro (perda = todas as credenciais ficam inutilizáveis). |
| Tabela `integration_credentials` + `communication_settings` + `communication_templates` + `communication_logs` | 🟢 | Adição pura. |
| Service `CommunicationService.dispatch` + `drain_scheduled` | 🟢 | Adição pura. |
| Beat schedule `communication-drain` | 🟢 | Adição pura. |
| Registrar handlers (`appointment.confirmed`, `appointment.cancelled`, `appointment.reminder_*`, `appointment.no_show`) | 🟡 | Extensão controlada. Handlers consomem eventos que precisam ser publicados pelos serviços de appointments. **Cuidado:** o appointments/service.py **atualmente não publica eventos** — apenas chama `send_booking_confirmation()` direto. Estratégia: nesse sprint, **publicar evento E manter chamada direta em paralelo**. Sprint 6+ removerá a chamada direta. |
| Substituir todas as chamadas a `evolution_client.send_text()` em `notifications.py` e handlers do bot pelo `CommunicationService.dispatch()` | 🔴 | **Estratégia gradual.** (1) Adicionar `dispatch` ao lado do `evolution_client.send_text` direto. (2) Validar em staging que `CommunicationLog` é criado e mensagem chega. (3) Em produção: feature flag por tenant via `TenantConfig.permission_overrides["use_communication_service"] = true` (JSONB do Sprint 3 — sem nova migration). (4) Após 1 semana ativo no cliente atual sem regressão → remover chamadas diretas + chave do JSONB. |
| **Migração `whatsapp_connection` → `integration_credentials`** | ✅ Decidido (Opção A) | **Não executar a migração no Estágio 0.** `WHATSAPP_EVOLUTION` permanece no enum `integration_credentials.provider` como `[SCHEMA APENAS]` — nenhum registro criado, código do bot lê de `settings` global como hoje. Detalhes na seção logo abaixo (mantida para referência histórica da decisão). |
| Seeds de templates default + `CommunicationSettings` default no onboarding (`whatsapp_enabled=False, email_enabled=False, quiet_hours_enabled=True`) + data migration para tenants existentes | 🟢 | Adição pura. **Sem `CommunicationSettings`, o `dispatch` falha no primeiro passo (busca de settings).** Hook em `create_company` insere o registro junto com os templates. Data migration usa `ON CONFLICT (company_id) DO NOTHING`. |
| Endpoints `/integrations/credentials/*`, `/communication/*` | 🟢 | Adição pura. |

---

## ✅ Decisão registrada (era ⛔ no draft anterior)

### Sprint 5 — Migração `whatsapp_connection` → `integration_credentials`

**Status:** Decidido — Opção A (Evolution API global no Estágio 0).
**Implicação:** o Sprint 5 não executa migração de credenciais WhatsApp. `WHATSAPP_EVOLUTION` permanece no enum `integration_credentials.provider` como schema-only (sem registros, sem uso ativo). O bot continua lendo `EVOLUTION_API_URL` e `EVOLUTION_API_KEY` de `settings` global. Critério de conclusão do brief sobre "migração whatsapp_connection" é considerado **não aplicável no Estágio 0** e não bloqueia a aprovação do sprint.

Quando, no Estágio 1+, surgir necessidade de Evolution API por tenant: o caminho (`integration_credentials` + `communication_settings.whatsapp_credential_id`) já estará pronto e a migração será incremental.

**Histórico da análise que levou à decisão:**

**O brief assume:**
```
whatsapp_connection.token         (não existe — modelo real não tem token)
whatsapp_connection.server_url    (não existe — modelo real não tem server_url)
```

**A realidade do código (`models/whatsapp_connection.py` linhas 28-72):**
```
WhatsAppConnection
  id, company_id (UNIQUE — 1 conexão por empresa),
  instance_name (UNIQUE),
  status, phone_number,
  qr_code, qr_generated_at,
  connected_at, disconnect_reason,
  created_at, updated_at
```

**Onde estão as credenciais reais hoje:**
- `EVOLUTION_API_URL` em `settings` (variável de ambiente global)
- `EVOLUTION_API_KEY` em `settings` (variável de ambiente global)
- Lidas em `app/modules/whatsapp/evolution_client.py`
- **Mesmas credenciais para todos os tenants** — Evolution API é compartilhada

**Implicação:** a migração descrita no brief (encriptar `whatsapp_connection.token` e copiar para `integration_credentials.secret_encrypted`) não é executável porque os campos de origem não existem.

**Opções de decisão:**

**Opção A — Aceitar Evolution API global no Estágio 0**
Manter `EVOLUTION_API_URL/KEY` em variáveis de ambiente. `integration_credentials` só armazena credenciais que **são realmente por tenant** no Estágio 0: SMTP (Sprint 5), Asaas (Sprint 8). `whatsapp_connection` permanece como está (gerencia apenas instance_name por tenant na Evolution API compartilhada).
- Vantagem: zero risco para produção
- Custo: o critério de conclusão "whatsapp_connection migrada → integration_credentials" do brief vira "não aplicável no Estágio 0"

**Opção B — Reinterpretar `provider=WHATSAPP_EVOLUTION` como configuração por tenant**
Para cada tenant existente, criar `integration_credentials` com:
- `secret_encrypted` = encriptar a `EVOLUTION_API_KEY` global (mesma chave para todos os tenants — perde valor por tenant)
- `config = { "server_url": settings.EVOLUTION_API_URL, "instance_name": <instance do tenant> }`

Quando, no futuro, um tenant quiser sua própria Evolution API: rotacionar via endpoint `/integrations/credentials/{id}/rotate`.
- Vantagem: padroniza modelo agora; suporta multi-Evolution no futuro sem refactor
- Custo: complexidade sem benefício imediato; encripta o mesmo segredo N vezes

**Opção C — Antecipar Evolution API por tenant**
Cada tenant pode ter sua própria Evolution API. Pleitos do brief literais.
- Vantagem: padrão limpo
- Custo: muda escopo do Estágio 0 (cliente atual usa Evolution compartilhada); requer infra adicional

**Recomendação:** Opção A. Mais segura para produção, alinhada ao Estágio 0 ("estoque único, mesmo design simples por default"). Brief precisa de pequeno ajuste: remover a obrigatoriedade da migração `whatsapp_connection → integration_credentials` e tratar `WHATSAPP_EVOLUTION` em `integration_credentials.provider` enum como `[SCHEMA APENAS]` no Estágio 0 (sem registros). Quando vier a primeira Evolution dedicada (Estágio 1+), o caminho está pronto.

**Sem decisão sobre este ponto, o Sprint 5 não pode iniciar a parte de migração WhatsApp.** Os demais itens do Sprint 5 (Fernet, integration_credentials para SMTP, CommunicationService, templates) podem prosseguir.

---

## Dependências de ordem dentro dos sprints

### Sprint 1

```
1. SQL de verificação de overlaps           (pré-requisito)
2. CREATE EXTENSION btree_gist               (idempotente; ok se já existe)
3. ALTER TABLE appointments ADD CONSTRAINT  (rejeita se overlaps existirem)
4. Rate limiting + security headers          (independentes — paralelo)
5. bcrypt rounds explícito                   (independente — paralelo)
6. Supabase Storage:
   6a. SDK + função de upload no Supabase
   6b. Endpoint dual-write (Supabase + local)
   6c. Script de migração de arquivos existentes
   6d. Endpoint só-Supabase + remoção de `/static`
```

### Sprint 2

```
1. CRIAR enum userrole com 9 valores         (antes do ALTER TABLE)
2. CRIAR tabelas audit_logs e user_invitations
3. CRIAR app/core/audit/sensitive_context.py + app/domain/enums/action_scope.py
   (USADOS POR services do mesmo sprint — devem existir antes)
4. ALTER COLUMN users.company_id DROP NOT NULL
5. ALTER COLUMN users.role TYPE userrole USING role::userrole
6. Refactor core/deps.py:
   6a. get_current_company_id PLATFORM_OWNER-aware
       (precisa de company_id nullable já aplicado — passo 4)
   6b. require_role, require_action com fallback gracioso
7. Routers novos (invite, activate, role, transfer, audit)
   (precisam de sensitive_context, action_scope, require_action — passos 3 e 6)
8. Marcar POST /users antigo como deprecated (não remover ainda)
```

### Sprint 3

```
1. CREATE TYPE para enums (entity_type categories, module_name) ANTES das tabelas
2. CRIAR tabelas: tenant_configs, module_activations, tenant_brandings, categories
3. CRIAR trigger block_accrual_mode (depende de tenant_configs)
4. Estender companies/service.create_company com 4 inserts (NA MESMA TRANSAÇÃO)
   (precisa das 4 tabelas — passo 2)
5. Data migration backfill para companies existentes (idempotente, ON CONFLICT DO NOTHING)
6. Endpoints /tenant/config, /tenant/modules, /tenant/branding, /categories
7. Migrar 15 routers: require_admin → require_role("ADMIN") (router por router)
8. Refinar para require_action(action, scope) onde OPERATOR/PROFESSIONAL têm acesso
9. Remover require_admin de core/deps.py (após grep retornar 0 matches)
10. Remover POST /users antigo (se logs confirmarem zero uso)
```

### Sprint 4

```
1. requirements.txt + docker-compose dev
2. app/core/encryption.py NÃO ENTRA AQUI (é Sprint 5)
3. CRIAR processed_idempotency_keys (migration)
4. CRIAR app/core/idempotency.py (helpers — precisa da tabela do passo 3)
5. CRIAR app/infrastructure/event_bus.py + DomainEvent
6. CRIAR app/infrastructure/celery_app.py + beat_schedule
7. Refactor reminder_worker para task Celery (mantendo asyncio em paralelo)
8. Refactor session_cleanup_worker idem
9. Subir Celery worker + beat em staging
10. Validação 1 semana em staging
11. Deploy Celery em produção (coexistência)
12. Validação 24h em produção
13. Remover asyncio.create_task do lifespan (FLIP DEFINITIVO)
14. Handlers booking_session.expired + appointment.reminder_due
```

### Sprint 5

```
1. ✅ Decisão WhatsApp: Opção A adotada — sem migração. Bot lê `settings` global. Prosseguir.
2. CRIAR app/core/encryption.py + variável CREDENTIAL_ENCRYPTION_KEY no ambiente
3. CRIAR migration integration_credentials
   (precisa de encryption.py — passo 2 — para encrypt_secret funcionar em backfill se houver)
4. CRIAR migrations communication_settings, communication_templates, communication_logs
5. CRIAR CommunicationService.dispatch (precisa das 4 tabelas)
6. CRIAR CommunicationService.drain_scheduled + beat task
7. Estender create_company com seeds de templates default
8. Data migration de templates default para tenants existentes
9. Endpoints /integrations/credentials/* e /communication/*
10. Registrar handlers de evento (appointment.confirmed, etc.)
    (precisa de event_bus do Sprint 4 + CommunicationService)
11. Adicionar PUBLICAÇÃO de eventos no appointments/service.py
    (sem remover chamada direta — coexistência)
12. Feature flag por tenant: USE_COMMUNICATION_SERVICE
13. Validação 1 semana com cliente atual
14. Remover chamadas diretas a evolution_client.send_text em notifications.py
    (somente se passo 13 sem regressão)
```

---

## Ordem de implementação recomendada dentro de cada sprint

### Sprint 1

| Ordem | Tarefa | Observação |
|-------|--------|------------|
| 1 | SQL de verificação de overlaps em produção | Bloqueante. Pare se retornar linhas. |
| 2 | `bcrypt__rounds=12` em `security.py` | Não afeta produção. Pode ser feito por último, mas é trivial — incluir cedo evita ficar pendente. |
| 3 | Middleware de security headers | Adição pura. Validar com `curl -I` em staging primeiro. |
| 4 | Rate limit em `/auth/login` | Adição pura. Testar com loop em staging antes de produção. |
| 5 | Supabase Storage — endpoint dual-write | Sem migrar arquivos ainda. |
| 6 | Script de migração de arquivos + update de URLs no banco | Rodar em staging primeiro com snapshot do banco de produção. |
| 7 | EXCLUDE CONSTRAINT migration | Por último neste sprint — em caso de problema, rollback isolado da constraint. |
| 8 | Remoção do volume `/static/uploads` e endpoint antigo | Só após validar 1 semana sem regressão no upload. |

### Sprint 2

| Ordem | Tarefa | Observação |
|-------|--------|------------|
| 1 | CREATE TYPE `userrole` (enum sem ALTER ainda) | Migration separada da alteração da coluna. |
| 2 | `ALTER COLUMN users.company_id DROP NOT NULL` | Não esquecer de atualizar `get_current_company_id` no mesmo PR. |
| 3 | Refactor `get_current_company_id` PLATFORM_OWNER-aware | Validar com unit test antes de merge. |
| 4 | `ALTER COLUMN users.role TYPE userrole USING role::userrole` | **Janela curta** (< 5s). Comunicar deploy planejado se atende clientes em horário comercial. |
| 5 | Criar `audit_logs`, `user_invitations` | Adição pura. |
| 6 | Criar `sensitive_context.py` + `action_scope.py` | Pré-requisito para os routers. |
| 7 | Implementar `require_role` e `require_action` | Manter `require_admin` em paralelo. |
| 8 | Endpoints novos (`invite`, `activate`, `transfer-ownership`, role mgmt, audit) | Adição pura. |
| 9 | Marcar `POST /users` antigo como deprecated + log de uso | Não remover. |

### Sprint 3

| Ordem | Tarefa | Observação |
|-------|--------|------------|
| 1 | Migrations das 4 tabelas + trigger ACCRUAL | Numa única feature branch. |
| 2 | Estender `companies/service.create_company` | Test de integração validando que onboarding cria todos os registros na mesma transação. |
| 3 | Data migration de backfill | Idempotente. Rodar em staging com dump da produção primeiro. |
| 4 | Endpoints `/tenant/*` e `/categories` | Adição pura. |
| 5 | **Migrar 15 routers de `require_admin` → `require_role("ADMIN")` (router por router, com testes de regressão)** | Refactor mecânico — preserva comportamento. Critério: `grep require_admin app/modules/` retorna 0 matches. |
| 6 | **Refinar `require_role("ADMIN")` para `require_action(action, scope)` onde OPERATOR/PROFESSIONAL devem ter acesso** | Ex: `/appointments` aceita PROFESSIONAL com `scope=OWN`, `/categories` aceita OPERATOR com override. Opcional onde ADMIN-only ainda é apropriado. |
| 7 | Remover `require_admin` de `core/deps.py` | Somente após passo 5. |
| 8 | Revisar logs do Sprint 2 — `POST /users` deprecated tem uso? | Decisão: remover ou estender prazo. |

### Sprint 4

| Ordem | Tarefa | Observação |
|-------|--------|------------|
| 1 | Adicionar dependências + Redis no docker-compose | Apenas dev. |
| 2 | `processed_idempotency_keys` + `idempotency.py` + `event_bus.py` + `celery_app.py` | Adição pura. |
| 3 | Tasks Celery em paralelo (sem desativar asyncio) | Subir worker + beat. |
| 4 | Staging: validar 1 semana com tráfego sintético | Métricas no Sentry/dashboard. |
| 5 | Produção: deploy Celery worker + beat junto com asyncio | Coexistência. |
| 6 | Produção: monitorar 24h | Verificar zero erros + zero duplicatas (flags de reminder protegem). |
| 7 | Remover `asyncio.create_task` do `lifespan` | Flip definitivo. |
| 8 | Handlers `booking_session.expired` e `appointment.reminder_due` | Substituem lógica antiga. |

### Sprint 5

| Ordem | Tarefa | Observação |
|-------|--------|------------|
| 1 | ⛔ **Resolver decisão sobre migração WhatsApp** | Bloqueante para a parte WhatsApp. |
| 2 | `CREDENTIAL_ENCRYPTION_KEY` no Railway + `app/core/encryption.py` | Sem chave, startup falha — validar localmente primeiro. |
| 3 | Tabelas: `integration_credentials`, `communication_*` | Adição pura. |
| 4 | `CommunicationService.dispatch` + `drain_scheduled` + beat task | Sem ainda substituir calls existentes. |
| 5 | Endpoints `/integrations/credentials/*` e `/communication/*` | Adição pura. |
| 6 | Seeds de templates default **+ `CommunicationSettings` (whatsapp_enabled=False, email_enabled=False, quiet_hours_enabled=True)** no onboarding | Hook em `create_company` (estendido no Sprint 3). **Sem `CommunicationSettings`, `CommunicationService.dispatch` falha no primeiro passo.** |
| 7 | Data migration de templates **+ `CommunicationSettings`** para tenants existentes | Idempotente. `ON CONFLICT (company_id) DO NOTHING` para `communication_settings`. |
| 8 | Publicar eventos no `appointments/service.py` (em paralelo com chamadas diretas) | Coexistência. |
| 9 | Feature flag `use_communication_service` em `TenantConfig.permission_overrides` (JSONB) | Localização exata: `TenantConfig.permission_overrides["use_communication_service"] = true`. JSONB já existe desde Sprint 3. `notifications.py` consulta a flag e decide entre `evolution_client.send_text` direto (default `False`) ou `CommunicationService.dispatch`. Default mantido como `False` durante rollout. |
| 10 | Validação 1 semana | Cliente atual com flag ativada. |
| 11 | Remover chamadas diretas a `evolution_client.send_text` em `notifications.py` | Só após 10 sem regressão. |

---

## Checklist de validação pós-sprint

Cada sprint **só está concluído** quando o checklist abaixo passar **em produção** (não apenas em staging). Testes unitários do brief são pré-condição, não conclusão.

### Pós-Sprint 1 — produto continua operacional

- [ ] Cliente atual consegue agendar via Link Público (fluxo completo até `appointment.created`)
- [ ] Cliente atual consegue agendar via Bot WhatsApp (mensagem chega ao Evolution API, FSM completa)
- [ ] `BookingEngine.create` ainda funciona quando dois requests simultâneos batem o mesmo slot (apenas 1 sucesso, outro recebe 409 — comportamento antigo) **+ confirmação adicional:** SQL direto com `INSERT` sobreposto agora também falha com `ExclusionViolationError` (novo)
- [ ] Login no painel funciona normalmente; 11ª tentativa em 1 minuto retorna 429
- [ ] Upload de foto de profissional no painel grava em Supabase Storage e exibe corretamente
- [ ] `curl -I https://api.../health` retorna `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`
- [ ] Sentry sem novos erros nas 24h pós-deploy
- [ ] Volume Docker `/app/static/uploads` ainda servindo URLs antigas (até remoção planejada no fim do sprint)

### Pós-Sprint 2 — RBAC sem regressão de produção

- [ ] Login do ADMIN existente funciona normalmente
- [ ] `GET /auth/me` retorna `role=ADMIN` (string) como hoje (compat de contrato)
- [ ] Painel exibe usuário logado normalmente — não quebrou com mudança de coluna
- [ ] Bot WhatsApp não autentica via JWT — não afetado
- [ ] Convite por e-mail funciona end-to-end: `invite` → e-mail → `activate` → JWT válido
- [ ] ADMIN tentando convidar OWNER retorna 403 com mensagem clara
- [ ] `POST /users` antigo ainda funciona (deprecated, mas operacional)
- [ ] `GET /audit/logs` retorna logs de `invite_user`, `assign_role`, `transfer_ownership`
- [ ] Migration `ALTER COLUMN role TYPE userrole` aplicada sem perda de dados (`SELECT COUNT(*) FROM users` antes/depois confere)

### Pós-Sprint 3 — TenantConfig consistente sem afetar uso atual

- [ ] Cliente atual recebeu seu `TenantConfig`, `ModuleActivation` (todos inativos), `TenantBranding` vazio e 16 categories default pelo backfill
- [ ] `GET /tenant/config` para o cliente atual retorna valores default
- [ ] Tentativa de `PUT /tenant/config` com `accounting_mode=ACCRUAL` retorna 422 + trigger no banco também rejeita
- [ ] Bot e Link Público continuam funcionando — não consomem `TenantConfig` ainda
- [ ] Criação de novo tenant (mesmo manualmente em staging) cria os 4 registros na mesma transação
- [ ] `POST /users` antigo removido (se logs do Sprint 2 confirmaram zero uso)

### Pós-Sprint 4 — workers migrados sem perder lembrete

- [ ] Pelo menos 1 lembrete real (24h) entregue via Celery, com `reminder_24h_sent=true` setado depois da entrega
- [ ] Pelo menos 1 lembrete real (2h) entregue via Celery, com `reminder_2h_sent=true` setado depois da entrega
- [ ] `bot_sessions` expiradas continuam sendo limpas (verificar contagem `WHERE expires_at < now()` antes/depois de janelas)
- [ ] Sentry sem novos erros relacionados a Celery worker
- [ ] `docker ps` em produção mostra serviços `redis`, `celery_worker`, `celery_beat`
- [ ] `asyncio.create_task` removido de `main.py:lifespan` (verificar por grep)
- [ ] BookingSession expirada → slot volta a aparecer como disponível na agenda (Link Público)

### Pós-Sprint 5 — comunicação configurável sem quebrar canal

- [ ] Pelo menos 1 lembrete real (24h) entregue via `CommunicationService.dispatch` + `CommunicationLog` com status `SENT`
- [ ] Mensagem de confirmação de agendamento (real) entregue via `CommunicationService` e visível em `/communication/logs`
- [ ] Bot WhatsApp continua funcionando — handlers do bot fazem dispatch via CommunicationService sem perder mensagens
- [ ] `GET /integrations/credentials` nunca retorna `secret_encrypted` (verificar via dev tools no painel)
- [ ] Reiniciar app sem `CREDENTIAL_ENCRYPTION_KEY` → startup falha com erro claro (testar em staging)
- [ ] Quiet hours: simular envio às 23h → CommunicationLog com `SCHEDULED`, `scheduled_send_at` no dia seguinte 08:00
- [ ] Sentry sem novos erros de decrypt
- [ ] ✅ WhatsApp permanece em `settings` global (Opção A) — nenhuma ação de migração necessária neste sprint

---

## Restrições aplicadas ao plano

Reafirmadas do prompt + interpretação do brief:

- **NÃO criar** `TenantFeeRoutingPolicy` na Fase 1 — pertence ao Sprint 6 (Financial Core, Fase 2). `tenant_configs.fee_routing_policy_id` permanece como FK NULL placeholder.
- **NÃO criar** modelos financeiros (`Account`, `Movement`, `Entry`, `Payment`, `Commission`) na Fase 1.
- **NÃO criar** modelo `Reservation` (SOFT/FIRME) na Fase 1 — pertence ao Sprint 10 (Fase 3). Usar `BookingSession` (já existe) para evento `booking_session.expired`.
- **NÃO usar** o nome de evento `agenda.soft_reservation.expired` na Fase 1 — modelo subjacente não existe ainda.
- **NÃO criar** UI no painel para os módulos desta fase (apenas backend).
- **NÃO alterar** lógica de cálculo de slots no `BookingEngine` (somente adicionar EXCLUDE CONSTRAINT como rede de segurança extra).

---

## Pontos de atenção que não bloqueiam, mas precisam ser registrados

1. **`POST /users` atual aceita senha no body** (`users/router.py:23-29`). Verificar via grep no `painel/` se algum lugar do frontend usa essa rota antes de remover. Se sim, atualizar o frontend antes ou em paralelo ao Sprint 2.

2. **`get_current_user` em `core/deps.py:18`** usa `HTTPBearer(auto_error=False)` e levanta 401 quando ausente. Comportamento correto para o convite/ativação — endpoints novos `/auth/activate` precisam ser **públicos** (sem `Depends(get_current_user)`).

3. **`whatsapp/connection_service.py`** chama `evolution_client` em vários pontos com URL e API key globais. Não afetado pela Fase 1 (decisão A da migração mantém comportamento), mas vale lembrar para a Fase 2 quando Painel Owner começar a inspecionar status de integrações por tenant.

4. **`bot_sessions` vs `booking_sessions` — divisão fechada no plano:**
   - `session_cleanup_worker` (Celery Beat a cada 5 min): cobre **apenas `bot_sessions`** (contexto do bot WhatsApp). Preserva comportamento atual do código.
   - Handler `booking_session.expired` (Sprint 4): cobre **apenas `booking_sessions`** (checkout web do Link Público). Idempotency key: `booking_session.expired:{booking_session_id}`. Consumer: `booking_session_cleanup`.
   - **Disparador do evento `booking_session.expired`:** Celery Beat task adicional a cada 5 min escaneia `SELECT id FROM booking_sessions WHERE expires_at < now() AND status NOT IN ('CONFIRMED','EXPIRED')` e publica um evento por sessão; o handler marca como `EXPIRED` e libera quaisquer slots associados.
   - São tabelas, propósitos e workers distintos. **Não unificar.** Se Claude Code propor unificação durante implementação, recusar.

5. **Aviso sobre dependência de `tenant_configs` no Sprint 2** — o brief instrui `require_action` a usar fallback gracioso (`{}`) quando a tabela não existe. Confirmar que esse fallback é desligado **após** Sprint 3 + backfill, para evitar bypass silencioso de permission_overrides em produção.

---

## Resumo do que aguarda decisão antes do início

**Sequência recomendada pelo revisor:**

| Ordem | Item | Sprint | Impacto se não decidido | Status |
|-------|------|--------|-------------------------|--------|
| 1 | Rodar SQL de verificação de overlaps em produção e reportar resultado | Sprint 1 | **Bloqueia início do Sprint 1.** Migration EXCLUDE CONSTRAINT pode falhar; pode revelar bug histórico que exige decisão de negócio. | ✅ Executado em 2026-05-22 — 0 linhas |
| 2 | Confirmar Opção A para WhatsApp (mantém Evolution API global) | Sprint 5 | Bloqueia escopo real do Sprint 5 (parte WhatsApp). | ✅ Decidido |
| 3 | `CREDENTIAL_ENCRYPTION_KEY` gerada e armazenada em vault Railway | Sprint 5 | Startup do app falha; bloqueia Sprint 5 inteiro. | 🔵 Pode ser feito esta semana sem urgência |
| 4 | Acesso ao Railway para criar serviços Redis + Celery worker + Celery beat | Sprint 4 | Sem infraestrutura, migração para Celery é inviável. | 🔵 Pode ser feito em paralelo |
| 5 | Frontend atual usa `POST /users`? (grep no `painel/`) | Sprint 2 (e 3) | Define se remoção em Sprint 3 é segura ou exige reescrita do painel. | 🔵 Verificar antes do Sprint 2 |

---

*Plano gerado a partir de `brief-fase1-fundacao.md` v2 e `visao-estagio-0.md` v1. Sem implementação até instrução explícita.*
