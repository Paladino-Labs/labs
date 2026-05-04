# PALADINO LABS — PLANO DE EXECUÇÃO CONSOLIDADO v3.0

---

## PARTE 1 — ESTADO ATUAL DO PROJETO

### Stack implementada

| Camada | Tecnologia | Status |
|--------|-----------|--------|
| Backend | FastAPI 0.115 + SQLAlchemy + Alembic | ✅ Em produção |
| Banco | PostgreSQL via Supabase (us-west-2) | ✅ Em produção |
| Frontend | Next.js 16.2 + React 19 + TailwindCSS 4 | ✅ Em produção |
| WhatsApp | Evolution API + state machine própria | ✅ Em produção |
| Workers | asyncio loop (sem Celery/Redis) | ✅ Funcional, sem garantia de entrega |
| Uploads | Volume Docker local (`/app/static/uploads`) | ⚠️ Não persiste entre deploys |
| Testes | pytest, 1 arquivo (`test_conflito.py`) | ❌ Cobertura ~5% |

### Status por módulo

| Módulo | % | Problemas conhecidos |
|--------|---|----------------------|
| BookingEngine (FSM centralizado) | 90% | Estado `CONFIRMING` sem timeout de recovery; sem `EXCLUDE CONSTRAINT` no banco |
| Bot WhatsApp | 75% | Funcional; sem IA; notificações são placeholder |
| Link público (slug) | 80% | Backend completo; sem avaliações, fila, promoções, OG tags |
| Autenticação / perfis | 55% | 3 de 5 perfis (`ADMIN`, `PROFESSIONAL`, `CLIENT`); sem `OWNER`, sem `RECEPTIONIST`; sem permissões granulares por módulo |
| Painel admin | 50% | CRUD básico; sem dashboard KPI, sem relatórios, sem financeiro |
| Locations / unidades | 0% | Sem tabela, sem FK, sem UI |
| NPS / avaliações | 0% | Sem tabela `reviews`, sem trigger pós-COMPLETED |
| Fila de espera | 0% | Sem tabela `waitlist`, sem worker de notificação |
| Dashboard analítico | 10% | Página existe, sem dados reais |
| Módulo financeiro | 15% | Campos existem em `appointments`; sem módulo de gestão |
| Módulo contábil | 0% | Nada implementado |
| CRM (ficha do cliente) | 30% | Página de detalhe existe; sem histórico agregado, sem classificação |
| Relatório por profissional | 0% | Sem endpoint, sem UI |
| Lembretes (workers) | 70% | Worker funciona; sem template configurável, sem opt-out |
| Pagamentos | 0% | Flag `require_payment_upfront` existe; sem integração com PSP |
| Assinaturas | 0% | Nada |
| Portal self-service do tenant | 20% | Página de perfil existe; sem billing, sem changelog |
| Painel Proprietário (Owner) | 0% | Sem rota, sem autenticação Owner, sem visão de tenants |

---

## PARTE 2 — DECISÕES ARQUITETURAIS REGISTRADAS

### Perfil Owner
`User` com `role=OWNER` e `company_id=NULL`. Mesmo endpoint `/auth/login`. JWT sem `company_id`. Dependency `require_owner()` bloqueia qualquer outro perfil. Criado via script de seed.

### Payments — provider e schema
Provider escolhido: **Asaas** (split nativo, subcontas sem KYC separado por barbearia, recorrência compatível com split). Mercado Pago não será implementado.

**PRÉ-REQUISITO CONTRATUAL:** Ler o contrato Asaas antes do Sprint 5.0 — verificar cláusulas de responsabilidade sobre KYC e confirmação de que o Paladino opera como facilitador tecnológico, não como subadquirente.

Schema agnóstico de provider (nunca nomes de provider como nome de coluna):

```python
# Company
payment_provider: str | None          # "asaas" — fonte única de verdade
external_account_id: str | None
external_account_status: str | None   # "active" | "pending_verification" | "suspended"

# Professional
cpf_cnpj: str | None
external_wallet_id: str | None        # herda provider de Company — sem campo redundante

# PaymentOrder
provider: str  # snapshot imutável — enforçado por @validates no ORM + trigger no banco

# SplitEntry
basis: str  # "GROSS" | "NET" — sem lógica ativa até Sprint 5.2+
```

### Abstração de payments

```
payments/providers/
├── base.py           # PaymentProvider (ABC) — permanente
├── asaas.py          # AsaasProvider — implementação ativa
└── null_provider.py  # NullProvider — testes (configurable outcome + self.calls spy)
```

### IA no bot
`ChainClassifier`: regex primeiro → OpenAI como fallback quando `confidence < 0.7`. FSM permanece árbitro. Sprint 2.0 implementa o classificador isolado. Sprint 2.6 conecta ao `bot_service.py` (depende de 2.0 + bot estável após 2.5).

### Testes
- `db_sqlite`: SQLite em memória para lógica pura e estados do FSM
- `db_pg`: Postgres real via `testcontainers` com `engine.begin()` + rollback (nunca commita)
- Testes de violação de constraint: `SAVEPOINT` interno ao teste para limpar estado de erro
- Dispatcher implementado como `REGISTERED_HANDLERS: dict[str, Callable]` — permite teste bidirecional de contrato entre classificador e handlers

---

## PARTE 3 — RISCOS ATIVOS

| Risco | Severidade | Mitiga no Sprint |
|-------|-----------|-----------------|
| Sem `EXCLUDE CONSTRAINT` — proteção só na aplicação | Crítico | 0.1 |
| CORS aberto `allow_origins=["*"]` em produção | Alto | 0.0a |
| Workers async sem orquestrador — lembretes perdidos em restart | Alto | (workaround em 1.4; solução completa pós-Fase 7) |
| Uploads em volume Docker — não persiste entre deploys | Médio | 1.0 |
| Cobertura de testes em 5% | Médio | 0.4 (base), crescente |
| KYC via Asaas: responsabilidade dos dados enviados recai sobre o Paladino | Regulatório | Contrato antes de 5.0 |
| Estado `CONFIRMING` sem timeout — sessão pode travar | Médio | 0.1 |

---

## PARTE 4 — PLANO COMPLETO DE SPRINTS

---

## FASE 0 — FUNDAÇÃO TÉCNICA

---

### Sprint 0.0a — CORS restrito

**Objetivo:** Fechar o vetor de segurança mais simples antes de qualquer outra mudança.

**Arquivos:**
- `agendamento_engine/app/main.py`
- `agendamento_engine/.env`

**O que implementar:**
1. Variável `ALLOWED_ORIGINS` no `.env` (lista separada por vírgula)
2. Substituir `allow_origins=["*"]` pela lista lida do `.env`
3. Incluir origens do Vercel e do localhost de desenvolvimento

**DoD:**
- [ ] Request de origem não listada retorna 403
- [ ] Frontend em produção continua funcionando
- [ ] Nenhum `*` em `ALLOWED_ORIGINS` em qualquer ambiente

---

### Sprint 0.0b — Observabilidade: Sentry + logging estruturado

**Objetivo:** Ter visibilidade de erros em produção antes de mexer em qualquer estrutura do banco.

**Arquivos:**
- `agendamento_engine/requirements.txt`
- `agendamento_engine/app/main.py`
- `agendamento_engine/app/core/logging.py` (novo)
- `agendamento_engine/.env`

**O que implementar:**
1. `sentry-sdk[fastapi]` instalado e configurado — captura exceções não tratadas automaticamente
2. Middleware de `request_id`: UUID gerado por request, propagado em todos os logs daquele request
3. Logger estruturado em JSON com campos fixos: `timestamp`, `level`, `module`, `company_id`, `user_id`, `request_id`
4. CPF/CNPJ mascarados antes de qualquer log: `"***.456.789-**"`

**DoD:**
- [ ] Exceção não tratada aparece no Sentry com stack trace completo
- [ ] Logs em JSON estruturado (não texto livre)
- [ ] `company_id` presente em todo log de request autenticado
- [ ] Nenhum CPF/CNPJ em texto puro em nenhum log
- [ ] `CryptContext` em `security.py` com `rounds=12` explícito (não depender do default da biblioteca — pode mudar entre versões)

**Ajuste pendente:** `pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")` não configura rounds explicitamente. Corrigir para `CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)` antes do merge da ASC-1.

---

### Sprint 0.1 — EXCLUDE CONSTRAINT + recovery do CONFIRMING

**Objetivo:** Proteger o banco contra conflitos de horário e corrigir sessão travada no FSM.

**Arquivos:**
- `agendamento_engine/migrations/` (nova migration)
- `agendamento_engine/app/modules/booking/engine.py`
- `agendamento_engine/app/workers/session_cleanup_worker.py`

**O que implementar:**
1. Verificar que extensão `btree_gist` está ativa no Supabase antes da migration
2. Migration com `EXCLUDE CONSTRAINT`:
```sql
ALTER TABLE appointments
ADD CONSTRAINT no_overlap
EXCLUDE USING gist (
  company_id WITH =,
  professional_id WITH =,
  tsrange(start_at, end_at, '[)') WITH &&
)
WHERE (status NOT IN ('CANCELLED', 'NO_SHOW'));
```
3. Timeout de 5 minutos para estado `CONFIRMING`: sessão retorna para `AWAITING_CONFIRMATION` com flag `retry=True`
4. Incluir limpeza de sessões `CONFIRMING` expiradas no `session_cleanup_worker` existente

**DoD:**
- [ ] Insert conflitante via SQL direto falha com `ExclusionViolationError`
- [ ] Insert conflitante via engine retorna mensagem clara ao usuário
- [ ] Sessão em `CONFIRMING` por mais de 5 min retorna para `AWAITING_CONFIRMATION`
- [ ] Teste manual: dois browsers tentando o mesmo slot — apenas um confirma

---

### Sprint 0.2 — Locations: migration + backend

**Objetivo:** Criar estrutura de banco para múltiplas unidades sem quebrar dados existentes.

**Arquivos:**
- `agendamento_engine/migrations/` (nova migration)
- `agendamento_engine/app/infrastructure/db/models/location.py` (novo)
- `agendamento_engine/app/infrastructure/db/models/professional.py`
- `agendamento_engine/app/infrastructure/db/models/appointment.py`
- `agendamento_engine/app/modules/locations/router.py` (novo)
- `agendamento_engine/app/modules/locations/service.py` (novo)

**O que implementar:**
1. Model `Location`: `id, company_id, name, address, timezone, is_active, created_at`
2. FK nullable `location_id` em `professionals` e `appointments` — sem `NOT NULL`, dados existentes ficam com `NULL`
3. CRUD: `GET /locations/`, `POST /locations/`, `PATCH /locations/{id}`, `DELETE /locations/{id}` (soft delete via `is_active=False`)
4. Todas as queries filtram por `company_id`

**DoD:**
- [ ] Tabela `locations` criada em produção
- [ ] FK nullable em `professionals` e `appointments` sem quebrar dados existentes
- [ ] CRUD funcionando com isolamento multi-tenant
- [ ] Nenhum appointment ou professional existente quebrado

---

### Sprint 0.3 — Locations: UI de gestão no painel

**Objetivo:** Admin cria, edita e desativa unidades sem intervenção técnica.

**Arquivos:**
- `painel/app/(dashboard)/settings/locations/page.tsx` (novo)
- `painel/components/LocationForm.tsx` (novo)
- `painel/lib/api.ts`

**O que implementar:**
1. Página `/dashboard/settings/locations` com lista de unidades ativas e inativas
2. Modal de criação/edição: nome, endereço, fuso horário, status
3. Desativação com confirmação explícita
4. Unidade inativa: badge visual distinto, ausente em filtros de agenda

**DoD:**
- [ ] Admin cria unidade e aparece na lista imediatamente
- [ ] Edição salva sem reload completo
- [ ] Unidade inativa ausente no seletor de filtros de agenda
- [ ] Erro de API exibe mensagem descritiva
- [ ] Token expirado durante operação redireciona para login sem perder contexto

---

### Sprint 0.4 — Testes críticos do BookingEngine

**Objetivo:** Cobertura mínima dos fluxos críticos antes de avançar nas fases.

**Arquivos:**
- `agendamento_engine/tests/conftest.py`
- `agendamento_engine/tests/test_booking_fsm.py` (novo)
- `agendamento_engine/tests/test_appointment_constraints.py` (novo)

**Arquitetura das fixtures:**

```python
# conftest.py

# Fixture rápida — SQLite em memória
# Para: lógica de FSM, validações de domínio, estados terminais
@pytest.fixture
def db_sqlite():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

# Fixture Postgres real via testcontainers
# Para: EXCLUDE CONSTRAINT, tsrange, btree_gist
@pytest.fixture(scope="session")
def pg_engine():
    with PostgresContainer("postgres:16") as pg:
        engine = create_engine(pg.get_connection_url())
        Base.metadata.create_all(engine)  # DDL aplicado uma vez, persiste no scope
        yield engine

@pytest.fixture
def db_pg(pg_engine):
    with pg_engine.begin() as conn:  # transação que nunca commita
        yield conn
        conn.rollback()
```

Para testes que verificam **violação de constraint** (onde a exceção aborta a transação), usar `SAVEPOINT` interno:

```python
@pytest.mark.pg
def test_exclusion_constraint_blocks_overlap(db_pg):
    db_pg.execute(insert_appointment_1)
    db_pg.execute(text("SAVEPOINT before_conflict"))
    with pytest.raises(Exception, match="no_overlap"):
        db_pg.execute(insert_appointment_conflitante)
    db_pg.execute(text("ROLLBACK TO SAVEPOINT before_conflict"))
```

**O que implementar:**
1. Teste (SQLite): cancelar `COMPLETED` → falha com estado terminal
2. Teste (SQLite): cancelar `CANCELLED` → falha com estado terminal
3. Teste (SQLite): sessão `CONFIRMING` após 5 min → `AWAITING_CONFIRMATION`
4. Teste (SQLite): `company_id` inválido → `NotFoundError`
5. Teste (Postgres): conflito via engine → `SlotUnavailableError`
6. Teste (Postgres): conflito via constraint SQL → `ExclusionViolationError`
7. Teste (Postgres): mesmo slot, profissionais diferentes → ambos confirmados

**DoD:**
- [ ] 7 testes passando com `pytest`
- [ ] Testes SQLite não dependem de banco externo
- [ ] Testes Postgres marcados com `@pytest.mark.pg`
- [ ] `pytest -m "not pg"` roda em menos de 10 segundos

---

### Sprint 0.4b — Hardening de segurança

**Objetivo:** Fechar vetores de segurança identificados no levantamento antes de adicionar novos perfis e rotas na Fase 0.5.

**Arquivos:**
- `agendamento_engine/requirements.txt`
- `agendamento_engine/app/main.py`
- `agendamento_engine/app/middleware/security_headers.py` (novo)
- `agendamento_engine/app/modules/auth/router.py`

**O que implementar:**

1. Rate limiting em `/auth/login`:
   - Instalar `slowapi`
   - Máximo 5 tentativas por IP por minuto
   - Após 5 falhas: lockout de 15 minutos para aquele IP
   - Resposta 429 com `Retry-After` header

2. Middleware de security headers:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Permissions-Policy: geolocation=(), microphone=(), camera=()`
   - `Content-Security-Policy: default-src 'self'` (apenas para a API — não bloqueia o frontend)

3. Documentar endpoints públicos intencionais em `main.py`:
   - Adicionar comentário explícito nas rotas sem autenticação: `/public/{slug}/*`, `/booking/{slug}/*`
   - Quando `/reviews/` e `/promotions/` forem criados (Fase 3), incluir o mesmo comentário

**DoD:**
- [ ] `/auth/login` retorna 429 após 5 tentativas em 1 minuto
- [ ] Headers de segurança presentes em toda resposta da API (verificar via `curl -I`)
- [ ] Endpoints públicos documentados com comentário explícito no router
- [ ] `slowapi` adicionado ao `requirements.txt`
- [ ] Nenhum endpoint existente quebrado pelos novos middlewares

**Procedimento de rollback:**
- Código: remover middleware + slowapi decorator — sem migration
- Dados: sem impacto

---

## FASE 0.5 — HIERARQUIA DE ACESSOS

---

### Sprint 0.5 — Perfil Owner: autenticação e rota protegida

**Objetivo:** Implementar como o Proprietário se autentica e acessa rotas exclusivas.

**Decisão registrada:** Owner é `User` com `role=OWNER` e `company_id=NULL`. Mesmo endpoint `/auth/login`. JWT contém `role=OWNER` sem `company_id`.

**Arquivos:**
- `agendamento_engine/app/infrastructure/db/models/user.py`
- `agendamento_engine/app/core/deps.py`
- `agendamento_engine/app/modules/owner/router.py` (novo)
- `agendamento_engine/scripts/create_owner.py` (novo)

**O que implementar:**
1. Enum `UserRole`: `OWNER, ADMIN, RECEPTIONIST, PROFESSIONAL, CLIENT`
2. `User.company_id` nullable (migration sem quebrar dados existentes)
3. Dependency `require_owner()`: valida `role=OWNER`, retorna 403 para qualquer outro
4. Rota de validação: `GET /owner/ping` → `{"status": "ok"}`
5. Script: `python scripts/create_owner.py --email X --password Y`

6. Recuperação de senha via WhatsApp:
   - `POST /auth/forgot-password` — recebe `{email_or_phone}`, gera token de 6 dígitos com TTL de 15 minutos, envia via Evolution API, armazena hash do token em `PasswordResetToken(user_id, token_hash, expires_at, used)`
   - `POST /auth/reset-password` — recebe `{token, new_password}`, valida TTL, valida que não foi usado, atualiza hash, marca token como usado (nunca deletar — manter histórico)
   - Link "Esqueci minha senha" na tela de login do painel

**DoD:**
- [ ] Owner faz login e recebe JWT com `role=OWNER` e sem `company_id`
- [ ] `GET /owner/ping` → 200 para Owner, 403 para Admin
- [ ] User sem `company_id` não quebra queries que assumem company_id presente
- [ ] Script de seed funciona em produção
- [ ] Token de recuperação inválido após uso (não reutilizável)
- [ ] Token expirado após 15 minutos
- [ ] Mensagem de WhatsApp enviada com código de recuperação
- [ ] Link "Esqueci minha senha" visível na tela de login

---

### Sprint 0.6 — Perfis Recepção e Profissional no backend

**Objetivo:** 5 perfis com permissões granulares funcionando via API.

**Arquivos:**
- `agendamento_engine/app/core/deps.py`
- `agendamento_engine/app/modules/appointments/router.py`
- `agendamento_engine/app/modules/services/router.py`
- `agendamento_engine/app/modules/professionals/router.py`

**O que implementar:**
1. Dependency `require_roles(allowed: list[UserRole])` — retorna 403 se role ausente
2. `RECEPTIONIST`: acessa agenda e customers; bloqueado em `/reports`, `/financial`, `/settings`
3. `PROFESSIONAL`: appointments filtrados automaticamente por `professional_id` do user logado
4. Aplicar `require_roles` em todos os routers existentes

5. Senha temporária para novos usuários criados pelo Admin:
   - Campo `must_change_password (bool, default False)` em `User`
   - Migration: adicionar coluna nullable com default False
   - Quando Admin cria Recepcionista ou Profissional: `must_change_password=True` + senha gerada aleatoriamente (12 caracteres, enviada via WhatsApp)
   - Backend: JWT de usuário com `must_change_password=True` retorna flag no payload

**DoD:**
- [ ] Recepção recebe 403 em rotas de relatório e configuração
- [ ] Profissional só vê appointments onde `professional_id = user.professional_id`
- [ ] Admin continua com acesso total ao tenant
- [ ] Teste: Recepção em rota financeira → 403
- [ ] Teste: Profissional em agenda de outro → 403
- [ ] Novo usuário criado pelo Admin recebe senha temporária via WhatsApp
- [ ] `must_change_password=True` no JWT bloqueia acesso a outras rotas até a troca ser realizada

---

### Sprint 0.7 — UI condicional por perfil no painel

**Objetivo:** Frontend adapta navegação e restringe acesso visual ao role logado.

**Arquivos:**
- `painel/hooks/useAuth.ts`
- `painel/components/Sidebar.tsx`
- `painel/app/(dashboard)/layout.tsx`
- `painel/app/(dashboard)/forbidden/page.tsx` (novo)

**O que implementar:**
1. `useAuth` decodifica JWT e expõe `user.role`
2. Sidebar com itens condicionais por role: Recepção vê Agenda e Clientes; Profissional vê apenas Minha Agenda; Admin vê tudo
3. Middleware Next.js: rota bloqueada por role → redirect para `/dashboard/forbidden`
4. Página `/dashboard/forbidden` com mensagem clara e link de retorno

5. Troca de senha autenticada no painel:
   - `POST /auth/change-password` — requer `{current_password, new_password, confirm_password}`; valida senha atual antes de atualizar; invalida todas as sessões ativas após troca
   - Página `/dashboard/settings/security` com formulário de troca
   - Redirect obrigatório para `/dashboard/settings/security` quando JWT contém `must_change_password=True`
   - Padrão de senha obrigatório: mínimo 8 caracteres, 1 maiúscula, 1 número — validado no frontend E no backend

6. Regras de senha no backend (centralizar em `security.py`):
   - `validate_password_strength(password: str) -> None`
   - Lança `WeakPasswordError` se não atender ao padrão
   - Chamado em `change-password`, `reset-password` e criação de usuário

**DoD:**
- [ ] Login como Recepção: menu exibe apenas Agenda e Clientes
- [ ] Login como Profissional: menu exibe apenas Minha Agenda
- [ ] Acesso direto via URL a rota bloqueada → `/dashboard/forbidden`
- [ ] Sem flash do menu completo antes do redirect
- [ ] Troca de senha funciona para todos os perfis autenticados
- [ ] Senha fraca rejeitada com mensagem específica (não "erro de validação" genérico)
- [ ] Após troca: todas as sessões anteriores invalidadas
- [ ] Usuário com `must_change_password=True` não acessa nenhuma outra rota antes de trocar a senha
- [ ] Redirect automático para `/security` ao logar com senha temporária

---

### Sprint 0.8 — Painel Proprietário: lista de tenants

**Objetivo:** Owner vê todos os tenants com status e métricas básicas de uso.

**Arquivos:**
- `agendamento_engine/app/modules/owner/router.py`
- `agendamento_engine/app/modules/owner/service.py` (novo)
- `painel/app/owner/page.tsx` (novo — fora do `/dashboard`)
- `painel/app/owner/layout.tsx` (novo — layout separado do tenant)

**O que implementar:**
1. `GET /owner/tenants` — lista companies com: `name`, `slug`, `is_active`, `created_at`, `total_appointments_last_30d`, `last_appointment_at`
2. Agregação em uma query (sem N+1)
3. Página `/owner` com lista e badges de status
4. Layout próprio do Owner, sem sidebar de tenant

**DoD:**
- [ ] Owner vê dados reais de todos os tenants
- [ ] Admin não acessa `/owner/tenants` (403)
- [ ] Métricas agregadas sem N+1 queries
- [ ] Tenant inativo com badge visual distinto

---

## FASE 1 — PAINEL PROFISSIONAL

---

### Sprint 1.0 — Uploads para Supabase Storage

**Objetivo:** Eliminar dependência de volume Docker antes de qualquer upload de foto em produção.

**Arquivos:**
- `agendamento_engine/requirements.txt`
- `agendamento_engine/app/modules/uploads/router.py`
- `agendamento_engine/app/modules/uploads/service.py`
- `agendamento_engine/.env`
- `agendamento_engine/scripts/migrate_uploads.py` (novo)

**O que implementar:**
1. Bucket `uploads` no Supabase Storage com ACL pública para leitura
2. Substituir `save to /app/static/uploads/` por `supabase.storage.upload()`
3. Retornar URL pública do Supabase em vez de URL local
4. Script único de migração: mover arquivos existentes do volume para o bucket e atualizar URLs no banco

**DoD:**
- [ ] Upload retorna URL do Supabase Storage (não `/static/uploads/`)
- [ ] Arquivos existentes migrados com URLs atualizadas no banco
- [ ] Deploy sem volume Docker não perde nenhum arquivo
- [ ] URL pública acessível sem autenticação

---

### Sprint 1.1 — Dashboard operacional com KPIs reais

**Objetivo:** Página inicial do painel com métricas reais do dia.

**Arquivos:**
- `agendamento_engine/app/modules/dashboard/router.py` (novo)
- `agendamento_engine/app/modules/dashboard/service.py` (novo)
- `painel/app/(dashboard)/dashboard/page.tsx`

**O que implementar:**
1. `GET /dashboard/summary?date=YYYY-MM-DD`:
   - Total agendamentos do dia
   - Taxa de ocupação: `(confirmados / slots_disponíveis) × 100` usando `slot_interval_minutes` de `CompanySettings`
   - Faturamento previsto: `SUM(total_amount)` de `SCHEDULED` + `IN_PROGRESS`
   - No-shows do dia
2. `GET /dashboard/upcoming?limit=5` — próximos agendamentos das próximas 3h
3. Frontend: 4 cards KPI + lista de próximos agendamentos

**DoD:**
- [ ] KPIs com dados reais (não mock)
- [ ] Filtrado por `company_id` do token
- [ ] Profissional vê apenas dados dos seus próprios agendamentos
- [ ] Taxa de ocupação usa `slot_interval_minutes` configurado

---

### Sprint 1.2 — Fluxo de agendamento completo no painel

**Objetivo:** Admin e Recepção criam agendamentos com validação completa via painel.

**Arquivos:**
- `painel/app/(dashboard)/appointments/new/page.tsx`
- `painel/components/AppointmentWizard.tsx` (novo)

**O que implementar:**
1. Wizard 5 passos: Cliente (busca por nome/telefone) → Serviço → Profissional → Data/Hora → Confirmação
2. Campo de desconto em reais — backend calcula, frontend exibe resultado
3. Slot indisponível → mensagem específica: "Horário ocupado — escolha outro"
4. Confirmação exibe subtotal, desconto, total (sempre calculado pelo backend)

**DoD:**
- [ ] Agendamento criado com `channel=admin`
- [ ] `total_amount` nunca calculado no frontend
- [ ] Conflito de horário com mensagem clara (não erro genérico)
- [ ] Token expirado durante o wizard: mensagem de sessão expirada sem perder estado do formulário

---

### Sprint 1.3 — CRUD profissional completo

**Objetivo:** Admin gerencia profissionais com foto, serviços e horários de trabalho.

**Arquivos:**
- `painel/app/(dashboard)/professionals/[id]/page.tsx`
- `painel/app/(dashboard)/professionals/new/page.tsx` (novo)
- `agendamento_engine/app/modules/professionals/router.py`
- `agendamento_engine/app/modules/schedule/router.py`

**O que implementar:**
1. Upload de foto via Supabase Storage (infra do Sprint 1.0)
2. Vinculação de serviços: checkbox com lista de serviços ativos — salva em `ProfessionalService`
3. Configuração de horários por dia da semana (7 linhas: abertura/fechamento, ativo/inativo)
4. Vinculação com unidade (dropdown de `locations` ativas)
5. Profissional inativo ausente em todos os fluxos de booking

**DoD:**
- [ ] Foto salva no Supabase e exibida no link público
- [ ] Serviços vinculados filtram disponíveis para agendamento deste profissional
- [ ] Horários salvos em `working_hours` (7 registros por profissional)
- [ ] Profissional `is_active=False` ausente no bot, link e seletor de agenda

---

### Sprint 1.4 — Lembretes configuráveis + opt-out

**Objetivo:** Tenant configura antecedência dos lembretes; cliente pode recusar.

**Arquivos:**
- `agendamento_engine/app/infrastructure/db/models/company_settings.py`
- `agendamento_engine/app/infrastructure/db/models/customer.py`
- `agendamento_engine/app/workers/reminder_worker.py`
- `painel/app/(dashboard)/settings/reminders/page.tsx` (novo)

**O que implementar:**
1. Campos em `CompanySettings`: `reminder_24h_enabled (bool)`, `reminder_2h_enabled (bool)`, `reminder_advance_hours (int, default 24)`
2. Campo em `Customer`: `reminder_opt_out (bool, default False)`
3. Worker verifica ambos os flags antes de enviar
4. "PARE" ou "CANCELAR" no bot registra `reminder_opt_out=True` automaticamente
5. UI: toggle de lembretes + configuração de antecedência

**DoD:**
- [ ] Tenant desativa lembrete de 24h → worker não envia
- [ ] Cliente com `opt_out=True` não recebe nenhum lembrete
- [ ] Log de lembrete enviado visível no painel
- [ ] "PARE" no bot registra opt-out sem intervenção manual

---

### Sprint 1.5 — Relatório básico por profissional

**Objetivo:** Admin vê desempenho individual; Profissional vê apenas os próprios dados.

**Arquivos:**
- `agendamento_engine/app/modules/reports/router.py` (novo)
- `agendamento_engine/app/modules/reports/service.py` (novo)
- `painel/app/(dashboard)/reports/page.tsx` (novo)

**O que implementar:**
1. `GET /reports/professional?start=&end=&professional_id=`:
   - Total atendimentos no período
   - Receita gerada: `SUM(total_amount)` de `COMPLETED`
   - Taxa de no-show: `NO_SHOW / (COMPLETED + NO_SHOW + CANCELLED)`
   - Taxa de retorno: clientes com 2+ atendimentos / total clientes únicos no período
2. Tabela comparativa (Admin) ou individual (Profissional)
3. Exportação CSV via `StreamingResponse`

**DoD:**
- [ ] Dados reais do banco
- [ ] Profissional logado recebe apenas seus dados pelo mesmo endpoint
- [ ] Admin filtra por profissional específico ou vê todos
- [ ] CSV exportável com os mesmos dados da tabela
- [ ] Filtro de período aplicado em todas as métricas

---

### Sprint 1.6 — Smoke test: validação com cliente atual

**Objetivo:** Checklist formal de estabilidade antes de abrir para segundo tenant.

**Formato:** Executado manualmente em produção, resultado documentado.

**Cenários a validar:**
1. Agendamento completo via bot (início ao fim)
2. Agendamento completo via link público
3. Agendamento via painel (Admin e Recepção)
4. Cancelamento via bot e via painel
5. Lembrete enviado para agendamento criado com 25h de antecedência
6. Login com cada perfil (Owner, Admin, Recepção, Profissional)
7. Tentativa de acesso cruzado entre perfis (Admin de tenant diferente)
8. Dois browsers, mesmo slot simultaneamente → apenas um confirma

**DoD:**
- [ ] Todos os 8 cenários executados e aprovados
- [ ] Nenhum erro no Sentry durante o smoke test
- [ ] Nenhum dado de um perfil visível para outro
- [ ] Checklist documentado, datado e arquivado

---

### Sprint 1.7 — Migração de workers para Celery + Redis

**Objetivo:** Substituir workers asyncio in-process por jobs Celery com Redis como broker — garantia de entrega para lembretes e base para a fila de espera (Fase 2.5).

**Motivação:** `reminder_worker` atual tem janela de detecção de ±10 minutos. Se a Evolution API estiver instável durante um ciclo, o lembrete daquele agendamento é perdido permanentemente — o flag `reminder_sent` não é setado e a janela de tempo já passou. Com Celery, cada lembrete é um job com retry automático e dead letter queue para falhas persistentes.

**Arquivos:**
- `agendamento_engine/requirements.txt`
- `agendamento_engine/app/workers/reminder_worker.py` (refactor)
- `agendamento_engine/app/workers/session_cleanup_worker.py` (refactor)
- `agendamento_engine/app/celery_app.py` (novo)
- `agendamento_engine/.env` (REDIS_URL)
- `railway.toml` ou configuração Railway (novo serviço Redis)

**O que implementar:**

1. Celery app com Redis como broker e backend:
   - `celery_app.py`: configuração com `REDIS_URL` do env
   - Beat scheduler para tarefas periódicas (substitui os loops)

2. Migrar `session_cleanup_worker` para Celery Beat:
   - Task periódica a cada 15 minutos
   - Retry: 3 tentativas com backoff exponencial

3. Migrar `reminder_worker` para Celery Beat + tasks individuais:
   - Task periódica a cada 10 minutos verifica agendamentos pendentes
   - Para cada lembrete a enviar: cria task individual `send_reminder.delay(appointment_id, reminder_type)`
   - Task individual: retry 3x com backoff de 5 min entre tentativas
   - Após 3 falhas: move para dead letter queue + log de erro no Sentry
   - `reminder_sent` flag só setado após confirmação de entrega

4. Redis como serviço adicional no Railway (Railway tem Redis como plugin nativo — sem infraestrutura externa)

**DoD:**
- [ ] Celery worker rodando como serviço separado no Railway
- [ ] Redis adicionado como serviço no Railway
- [ ] Lembretes enviados com retry automático em caso de falha da Evolution API
- [ ] Falha persistente (3 tentativas) aparece no Sentry com `appointment_id` e tipo de lembrete
- [ ] `reminder_sent` flag setado apenas após confirmação de entrega
- [ ] Workers asyncio antigos removidos do `main.py`
- [ ] Smoke test: criar agendamento com 25h de antecedência → verificar lembrete de 24h entregue mesmo simulando falha temporária da Evolution API

**Procedimento de rollback:**
- Código: reverter para workers asyncio no lifespan — sem migration
- Dados: sem impacto nos agendamentos existentes
- Redis: pode ser desligado sem perda de dados de negócio
- Estimativa de rollback: 30 minutos

**Impacto no plano:**
- Fase 2.5 (fila de espera) passa a ter base confiável para notificações — Sprint 2.4 assume Celery disponível
- Adicionar ao Sprint 2.4: usar `notify_next_in_waitlist.delay()` em vez de chamada síncrona

---

## FASE 2 — IA NO BOT

*Pode ser executada após Fase 1. Sprints 2.1–2.5 não dependem deste bloco. Sprint 2.6 depende de 2.0 + 2.5.*

---

### Sprint 2.0 — IntentClassifier: interface + testes de contrato

**Objetivo:** Implementar o classificador de intenções isolado, sem conectar ao bot ainda.

**Arquivos:**
- `agendamento_engine/app/modules/whatsapp/intent/base.py` (novo)
- `agendamento_engine/app/modules/whatsapp/intent/regex_classifier.py` (novo)
- `agendamento_engine/app/modules/whatsapp/intent/openai_classifier.py` (novo)
- `agendamento_engine/app/modules/whatsapp/intent/chain_classifier.py` (novo)
- `agendamento_engine/tests/test_intent_contract.py` (novo)

**O que implementar:**
1. `IntentClassifier` ABC: `classify(message: str) -> IntentResult`
2. `IntentResult`: `{intent: str, entities: dict, confidence: float}`
3. `RegexClassifier`: mapeia padrões → intenções (`agendar`, `cancelar`, `reagendar`, `ver_agendamentos`, `saudacao`)
4. `OpenAIClassifier`: chamado apenas quando `confidence < 0.7`
5. `ChainClassifier`: regex primeiro, OpenAI como fallback
6. Propriedade `ChainClassifier.known_intents: set[str]` — conjunto de intenções detectáveis

**Testes de contrato:**

```python
def test_intent_result_shape_matches_dispatcher_contract():
    result = ChainClassifier().classify("quero agendar um corte amanhã")
    assert isinstance(result.intent, str)
    assert isinstance(result.confidence, float)
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.entities, dict)

def test_intent_result_does_not_mutate_session():
    classifier = ChainClassifier()
    session = BotSession(state="MENU_PRINCIPAL", context={})
    state_before = session.state
    classifier.classify("cancelar meu horário")
    assert session.state == state_before

def test_intent_contract_is_bidirectional():
    from app.modules.whatsapp.dispatcher import REGISTERED_HANDLERS
    classifier = ChainClassifier()
    dispatcher_intents = set(REGISTERED_HANDLERS.keys())
    classifier_intents = classifier.known_intents

    # Sentido 1: todo intent que o classificador produz tem handler
    for msg in TEST_MESSAGES:
        result = classifier.classify(msg)
        assert result.intent in dispatcher_intents

    # Sentido 2: todo handler registrado é reconhecível pelo classificador
    for intent in dispatcher_intents - {"unknown"}:
        assert intent in classifier_intents
```

**DoD:**
- [ ] Classificador funciona isolado (sem tocar no bot)
- [ ] `classify("quero agendar")` → `intent="agendar"` sem chamar OpenAI
- [ ] Mensagem ambígua → OpenAI chamado com custo logado
- [ ] Testes de contrato passando
- [ ] Dispatcher implementado como `REGISTERED_HANDLERS: dict` (pré-requisito do teste bidirecional)
- [ ] Zero modificação no comportamento atual do bot

---

## FASE 2.5 — NPS + AVALIAÇÕES + FILA DE ESPERA

---

### Sprint 2.1 — NPS: modelo + trigger pós-COMPLETED

**Objetivo:** Estrutura de dados para avaliações e disparo automático após atendimento.

**Arquivos:**
- `agendamento_engine/migrations/` (nova migration)
- `agendamento_engine/app/infrastructure/db/models/review.py` (novo)
- `agendamento_engine/app/modules/appointments/service.py`
- `agendamento_engine/app/modules/reviews/router.py` (novo)

**O que implementar:**
1. Model `Review`: `id, company_id, appointment_id, customer_id, professional_id, service_id, rating (1-5), comment, google_suggestion_sent (bool), created_at`
2. Flag `nps_requested_at` em `appointments`
3. Hook em `complete_appointment()`: agenda envio de NPS em 30 min
4. Handler no bot: envia "Como foi o atendimento? Responda de 1 a 5" ~30 min após COMPLETED
5. `POST /reviews/`: recebe `{appointment_id, rating, comment}`, valida que appointment é COMPLETED e pertence ao `company_id`
6. Idempotente: segundo POST para o mesmo `appointment_id` retorna o registro existente

**DoD:**
- [ ] Tabela `reviews` criada em produção
- [ ] Bot envia solicitação ~30 min após COMPLETED
- [ ] Rating salvo com `company_id` validado
- [ ] Segundo envio para mesmo appointment não cria duplicata

---

### Sprint 2.2 — NPS: painel de avaliações

**Objetivo:** Admin vê avaliações agregadas e feed de comentários.

**Arquivos:**
- `agendamento_engine/app/modules/reviews/router.py`
- `painel/app/(dashboard)/reviews/page.tsx` (novo)

**O que implementar:**
1. `GET /reviews/summary` — média geral, média por profissional, média por serviço, total de avaliações
2. `GET /reviews/feed?page=&professional_id=` — lista paginada (20 por página)
3. Página: card de média geral + breakdown por profissional + feed paginado

**DoD:**
- [ ] Médias calculadas com dados reais
- [ ] Feed paginado (20 por página)
- [ ] Filtro por profissional funciona no feed
- [ ] Profissional logado vê apenas avaliações dos seus atendimentos

---

### Sprint 2.3 — Google review gerenciado

**Objetivo:** Sugestão de review no Google apenas para clientes satisfeitos, com frequência controlada.

**Arquivos:**
- `agendamento_engine/app/infrastructure/db/models/customer.py`
- `agendamento_engine/app/modules/reviews/service.py`
- `agendamento_engine/app/modules/whatsapp/bot_service.py`

**O que implementar:**
1. Campo `last_google_suggestion_at` em `Customer`
2. Regra pós-avaliação ≥ 4: verificar se cliente tem 3+ atendimentos COMPLETED + `last_google_suggestion_at` NULL ou > 90 dias
3. Se regra satisfeita: bot envia link de `CompanyProfile.google_review_url` + registra `last_google_suggestion_at = now()`

**DoD:**
- [ ] Nota < 4 → nunca recebe sugestão
- [ ] Nota ≥ 4 com < 3 atendimentos → não recebe sugestão
- [ ] Máximo 1 sugestão por 90 dias por cliente por empresa
- [ ] Link vem do perfil da empresa (não hardcoded)

---

### Sprint 2.4 — Fila de espera: modelo + backend

**Objetivo:** Estrutura de dados e endpoints para gerenciar clientes aguardando slots.

**Arquivos:**
- `agendamento_engine/migrations/` (nova migration)
- `agendamento_engine/app/infrastructure/db/models/waitlist.py` (novo)
- `agendamento_engine/app/modules/waitlist/router.py` (novo)
- `agendamento_engine/app/modules/waitlist/service.py` (novo)
- `agendamento_engine/app/modules/appointments/service.py`

**O que implementar:**
1. Model `WaitlistEntry`: `id, company_id, customer_id, preferred_service_id, preferred_professional_id (nullable), preferred_period (AM/PM/ANY), status (WAITING/NOTIFIED/CONFIRMED/EXPIRED), notified_at, expires_at`
2. `POST /waitlist/`, `GET /waitlist/?status=`, `DELETE /waitlist/{id}`
3. Hook em `cancel_appointment()`: chamar `notify_next_in_waitlist()` após cancelamento confirmado
4. `notify_next_in_waitlist()`: primeiro `WAITING` com matching → status `NOTIFIED`, `notified_at = now()`, `expires_at = now() + 24h`

**DoD:**
- [ ] Tabela `waitlist` criada em produção
- [ ] Cancelamento dispara notificação para próximo da fila com match
- [ ] Admin vê fila completa com status por entrada
- [ ] Fila filtrada por `company_id`
- [ ] Teste: dois clientes na fila, um slot abre → apenas o primeiro recebe notificação

---

### Sprint 2.5 — Fila de espera: bot + link público

**Objetivo:** Cliente entra na fila via bot e via link público.

**Arquivos:**
- `agendamento_engine/app/modules/whatsapp/handlers/fila_espera.py` (novo)
- `agendamento_engine/app/modules/whatsapp/bot_service.py`
- `painel/app/book/[slug]/BookingFlow.tsx`
- `agendamento_engine/app/modules/booking/router.py`

**O que implementar:**
1. Bot: `list_slots()` vazio → oferecer fila ("Sem horários. Deseja entrar na fila de espera?")
2. Handler `fila_espera.py`: coleta preferências e cria `WaitlistEntry`
3. Notificação quando slot abre: link de confirmação com token de 24h
4. Link público: formulário de fila exibido quando sem slots disponíveis
5. Expiração: `expires_at` vencido → status `EXPIRED`, slot liberado para próximo

**DoD:**
- [ ] Bot oferece fila quando agenda sem slots
- [ ] Link público exibe formulário de fila quando sem slots
- [ ] Cliente recebe notificação quando slot compatível abre
- [ ] Entrada com `expires_at` vencido não bloqueia o slot

---

### Sprint 2.6 — Conectar IntentClassifier ao bot

**Objetivo:** Classificador de intenções integrado ao `bot_service.py` no fluxo de menu.

**Pré-requisito:** Sprint 2.0 concluído + bot estável após 2.5.

**Arquivos:**
- `agendamento_engine/app/modules/whatsapp/bot_service.py`
- `agendamento_engine/app/modules/whatsapp/handlers/*.py`

**O que implementar:**
1. Chamar `ChainClassifier.classify()` antes de despachar para handler quando estado = `MENU_PRINCIPAL`
2. Resultado usado para roteamento — estados de booking (`ESCOLHENDO_SERVICO`, `CONFIRMANDO` etc.) ignoram classificador
3. Nenhum handler recebe `IntentResult` diretamente — apenas `bot_service` decide o roteamento
4. Log de intenção detectada + confidence + custo por chamada OpenAI

**DoD:**
- [ ] Mensagem livre no menu principal roteada pelo classificador
- [ ] Estados de booking não afetados (FSM permanece árbitro)
- [ ] Nenhum handler recebe `IntentResult` diretamente
- [ ] Custo por chamada OpenAI logado e monitorável

---

## FASE 3 — LINK PÚBLICO PROFISSIONAL

---

### Sprint 3.1 — Aba de avaliações no link público

**Objetivo:** Visitantes do link público veem avaliações reais, anonimizadas.

**Arquivos:**
- `agendamento_engine/app/modules/booking/router.py`
- `painel/app/book/[slug]/ReviewsSection.tsx` (novo)
- `painel/app/book/[slug]/page.tsx`

**O que implementar:**
1. `GET /booking/{slug}/reviews` — média + últimas 10 avaliações; anonimizado: primeiro nome + inicial do sobrenome (`"João S."`)
2. Seção de avaliações na página do link após o botão "Agendar"
3. Stars visuais com média e contagem total
4. Botão "Avaliar no Google" — visível apenas se `CompanyProfile.google_review_url` preenchido; visualmente secundário
5. Seção não renderiza sem nenhuma avaliação

**DoD:**
- [ ] Avaliações acessíveis sem login
- [ ] Anonimização: "João S." (nunca nome completo ou telefone)
- [ ] Seção ausente para empresa sem avaliações
- [ ] Botão Google review presente mas não é o CTA primário

---

### Sprint 3.2 — OG tags + SEO no link público

**Objetivo:** Compartilhamento em WhatsApp/Instagram gera preview correto.

**Arquivos:**
- `painel/app/book/[slug]/page.tsx`
- `painel/next.config.ts`

**O que implementar:**
1. `generateMetadata()` server-side buscando `CompanyProfile` antes de renderizar
2. OG tags: `og:title`, `og:description` (tagline), `og:image` (cover_url), `og:url`
3. Twitter card tags (usadas também pelo TikTok)
4. `canonical` URL por slug sem parâmetros de query
5. Slug inválido: retorna HTTP 404 real (não página em branco com erro JS)

**DoD:**
- [ ] Link no WhatsApp gera preview com foto e nome do estabelecimento
- [ ] `og:image` usa `cover_url` do perfil (não placeholder)
- [ ] Slug inválido retorna 404 confirmado via `curl -I`
- [ ] Preview correto no WhatsApp, Instagram e TikTok (verificado com ferramenta de debug de OG)

---

### Sprint 3.3 — Promoções: backend + painel

**Objetivo:** Admin cria promoções com prazo, limite de uso e código de cupom.

**Arquivos:**
- `agendamento_engine/migrations/` (nova migration)
- `agendamento_engine/app/infrastructure/db/models/promotion.py` (novo)
- `agendamento_engine/app/modules/promotions/router.py` (novo)
- `painel/app/(dashboard)/promotions/page.tsx` (novo)

**O que implementar:**
1. Model `Promotion`: `id, company_id, name, discount_type (PERCENT/FIXED), discount_value, code (nullable, único por empresa), valid_from, valid_until (nullable), max_uses (nullable), uses_count, is_active`
2. CRUD de promoções no painel
3. `POST /promotions/validate`: recebe `{code, company_id}`, retorna `{discount_type, discount_value}` ou erro descritivo
4. `uses_count` incrementado atomicamente: `UPDATE ... WHERE uses_count < max_uses RETURNING id`

**DoD:**
- [ ] Admin cria promoção com validade e limite
- [ ] Código expirado → "Promoção encerrada"
- [ ] Código com limite atingido → "Limite de usos esgotado"
- [ ] `discount_amount` sempre calculado pelo backend
- [ ] `uses_count` não ultrapassa `max_uses` com requests simultâneos

---

### Sprint 3.4 — Promoções: link público e bot

**Objetivo:** Cliente aplica cupom no fluxo de agendamento e vê promoções ativas.

**Arquivos:**
- `agendamento_engine/app/modules/booking/router.py`
- `painel/app/book/[slug]/BookingFlow.tsx`
- `agendamento_engine/app/modules/whatsapp/handlers/confirmando.py`

**O que implementar:**
1. `GET /booking/{slug}/promotions` — promoções ativas sem código (vitrines)
2. Link público: badge "Promoção" nos serviços elegíveis; campo de cupom no passo de confirmação
3. Aplicar cupom: frontend envia código → backend valida → retorna total atualizado
4. Bot: menciona promoções ativas no menu principal se houver pelo menos uma

**DoD:**
- [ ] Promoção ativa exibida no link sem código (quando aplicável)
- [ ] Cupom válido aplicado com total atualizado no frontend
- [ ] Sem promoção ativa: nenhuma menção no bot
- [ ] Desconto sempre calculado pelo backend

---

## FASE 4 — GESTÃO E INDICADORES

---

### Sprint 4.1 — Dashboard financeiro básico

**Objetivo:** Admin vê faturamento realizado e previsto com filtro mensal.

**Arquivos:**
- `agendamento_engine/app/modules/dashboard/service.py`
- `agendamento_engine/app/modules/dashboard/router.py`
- `painel/app/(dashboard)/financial/page.tsx` (novo)

**O que implementar:**
1. `GET /dashboard/financial?month=YYYY-MM`:
   - Faturamento realizado: `SUM(total_amount)` onde `status=COMPLETED AND financial_status=PAID`
   - Faturamento previsto: `SUM(total_amount)` onde `status=SCHEDULED`
   - Ticket médio do mês (excluindo cancelados)
   - Receita por profissional (ranking)
2. Página: cards de realizado/previsto + tabela por profissional

**DoD:**
- [ ] Dados calculados de `appointments` (sem tabela intermediária)
- [ ] Filtro por mês funciona para qualquer mês histórico
- [ ] Recepção não acessa a página (403)
- [ ] Ticket médio exclui agendamentos cancelados

---

### Sprint 4.2 — Ficha completa do cliente (CRM)

**Objetivo:** Página do cliente com histórico agregado, classificação e observações.

**Arquivos:**
- `agendamento_engine/app/modules/customers/router.py`
- `agendamento_engine/app/modules/customers/service.py`
- `painel/app/(dashboard)/customers/[id]/page.tsx`

**O que implementar:**
1. `GET /customers/{id}/summary` — em uma query agregada:
   - Histórico completo paginado, serviço mais frequente, profissional favorito, ticket médio, total gasto, avaliações dadas
   - Status calculado pelo backend: `recorrente` (3+ atendimentos), `eventual` (1-2), `em_risco` (último > 60 dias)
2. Campo de observações editável diretamente na ficha

**DoD:**
- [ ] Dados reais sem N+1 queries
- [ ] Status `em_risco` com alerta visual
- [ ] Observação salva sem apagar conteúdo anterior
- [ ] Profissional vê apenas fichas dos seus clientes

---

### Sprint 4.3 — Módulo contábil básico (DRE simplificado)

**Objetivo:** Admin registra despesas e gera DRE mensal.

**Arquivos:**
- `agendamento_engine/migrations/` (nova migration)
- `agendamento_engine/app/infrastructure/db/models/expense.py` (novo)
- `agendamento_engine/app/modules/accounting/router.py` (novo)
- `painel/app/(dashboard)/accounting/page.tsx` (novo)

**O que implementar:**
1. Model `Expense`: `id, company_id, description, amount, category (FIXED/VARIABLE/INVESTMENT), reference_month (YYYY-MM), created_by`
2. CRUD de despesas no painel
3. `GET /accounting/dre?month=`: receitas por serviço (de `appointments`) + despesas por categoria + lucro estimado
4. Exportação CSV via `StreamingResponse`

**DoD:**
- [ ] Admin registra despesa com categoria e mês de referência
- [ ] DRE mensal com dados reais de receitas e despesas
- [ ] CSV exportável compatível com Excel
- [ ] Receitas exclusivamente de `appointments` (não entrada manual)

---

## FASE 5 — PAGAMENTOS

> **PRÉ-REQUISITO:** Ler contrato Asaas antes de qualquer sprint desta fase — verificar cláusulas de responsabilidade sobre KYC, modelo de taxas por subconta e confirmação de que o Paladino opera como facilitador tecnológico (não subadquirente).

---

### Sprint 5.0 — Onboarding financeiro: subcontas Asaas

**Objetivo:** Cada tenant e profissional com CPF tem subconta no Asaas antes do primeiro pagamento.

**Arquivos:**
- `agendamento_engine/migrations/` (nova migration)
- `agendamento_engine/app/infrastructure/db/models/company.py`
- `agendamento_engine/app/infrastructure/db/models/professional.py`
- `agendamento_engine/app/modules/payments/providers/asaas.py` (parcial — só subcontas)
- `painel/app/(dashboard)/professionals/[id]/page.tsx`
- `painel/app/(dashboard)/settings/financial/page.tsx` (novo)

**Schema a adicionar:**

```python
# Company
payment_provider: str | None          # "asaas" — fonte única de verdade
external_account_id: str | None
external_account_status: str | None   # "active" | "pending_verification" | "suspended"

# Professional
cpf_cnpj: str | None
external_wallet_id: str | None        # herda provider de Company — sem campo redundante
```

**O que implementar:**
1. Migration com as 5 colunas (todas nullable)
2. `AsaasProvider.create_subaccount(name, cpf_cnpj, email)` → retorna `accountId`
3. Hook no cadastro do tenant: criar subconta Asaas automaticamente
4. Validação de CPF/CNPJ com **algoritmo de dígito verificador** antes de enviar à API (não apenas formato — `"111.111.111-11"` passa na regex mas é inválido)
5. Webhook de ativação → atualiza `external_account_status` para `"active"`
6. Banner no painel quando `status=pending_verification`: instruções sobre o que fazer
7. CPF mascarado em todos os logs: `"***.456.789-**"`

**DoD:**
- [ ] Tenant criado → subconta Asaas criada automaticamente
- [ ] CPF com dígito verificador inválido → erro no frontend antes de chamar API
- [ ] `pending_verification` → banner com próximos passos visível no painel
- [ ] Webhook de ativação atualiza status corretamente
- [ ] Profissional sem `external_wallet_id` → split inativo, agendamento não bloqueado
- [ ] Nenhum CPF/CNPJ em texto puro em logs

---

### Sprint 5.1 — PaymentProvider ABC + AsaasProvider + Pix *(2 dias)*

**Objetivo:** Infraestrutura de pagamentos desacoplada com Pix funcionando via Asaas.

**Estrutura do módulo:**

```
agendamento_engine/app/modules/payments/
├── domain.py
├── providers/
│   ├── base.py           # PaymentProvider (ABC)
│   ├── asaas.py          # implementação ativa
│   └── null_provider.py  # testes + referência de contrato
├── service.py
├── router.py
└── schemas.py
```

**Modelos de dados:**

```python
# PaymentOrder
id, company_id, appointment_id, amount, status (PENDING/PAID/FAILED/REFUNDED),
provider (str — snapshot imutável), external_reference, created_at

# PaymentTransaction
id, order_id, provider_transaction_id, amount, status,
raw_response (JSONB — sem dados sensíveis), created_at

# SplitEntry
id, order_id, recipient_type (COMPANY/PROFESSIONAL), recipient_id,
amount, percentage, basis (GROSS/NET)  # sem lógica ativa até 5.2+
```

**Imutabilidade de `PaymentOrder.provider`:**

```python
# models/payment_order.py
@validates("provider")
def _provider_is_immutable(self, key, value):
    if self.provider is not None and self.provider != value:
        raise ValueError("PaymentOrder.provider is immutable after creation")
    return value
```

```sql
-- migration Sprint 5.1
CREATE OR REPLACE FUNCTION prevent_payment_order_provider_update()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.provider IS NOT NULL AND NEW.provider != OLD.provider THEN
        RAISE EXCEPTION 'PaymentOrder.provider is immutable after creation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER enforce_provider_immutability
    BEFORE UPDATE ON payment_orders
    FOR EACH ROW EXECUTE FUNCTION prevent_payment_order_provider_update();
```

**NullProvider:**

```python
class NullProvider(PaymentProvider):
    def __init__(self, payment_outcome: str = "PAID"):
        self._outcome = payment_outcome
        self.calls: list[dict] = []  # spy para assertions em testes

    async def create_payment(self, order) -> PaymentResult:
        self.calls.append({"method": "create_payment", "order_id": order.id})
        return PaymentResult(external_id=f"null-{order.id}", status=self._outcome, qr_code=None)

    async def handle_webhook(self, payload: dict) -> WebhookEvent: ...
    async def refund(self, transaction_id: str, amount: Decimal) -> RefundResult: ...
    async def get_status(self, external_id: str) -> str:
        return self._outcome
```

**O que implementar:**
1. `PaymentProvider` ABC com 4 métodos
2. `AsaasProvider`: Pix com QR Code
3. `NullProvider` configurável com spy
4. `PaymentService` com injeção de dependência (nunca instancia provider diretamente)
5. Webhook genérico idempotente: `POST /payments/webhook/{provider}`
6. Link público: QR Code exibido após confirmação quando `require_payment_upfront=True`

**DoD:**
- [ ] Pix gerado e exibido no link público via AsaasProvider
- [ ] Webhook confirma pagamento → `PaymentOrder.status=PAID` + `Appointment.financial_status=PAID`
- [ ] Webhook idempotente: segundo disparo não cria segunda `PaymentTransaction`
- [ ] `PaymentOrder.provider` imutável (ORM + trigger)
- [ ] Trocar provider = mudança de 1 linha na injeção
- [ ] `NullProvider` passa em todos os testes do módulo
- [ ] `total_amount` nunca calculado no frontend

---

### Sprint 5.2 — Sinal opcional + pacotes de crédito

**Objetivo:** Admin configura percentual de sinal; clientes podem ter saldo de créditos.

**Arquivos:**
- `agendamento_engine/app/infrastructure/db/models/company_settings.py`
- `agendamento_engine/migrations/` (nova migration)
- `agendamento_engine/app/infrastructure/db/models/credit_package.py` (novo)
- `agendamento_engine/app/modules/payments/service.py`

**O que implementar:**
1. Campo `upfront_percentage (int, 0-100, default 0)` em `CompanySettings`
2. Model `CreditPackage`: `id, company_id, name, credits, price, valid_days, is_active`
3. Model `CustomerCredits`: `id, company_id, customer_id, package_id, credits_remaining, expires_at`
4. Débito de crédito atomicamente ao confirmar agendamento
5. Crédito com `expires_at < now()` não é usado

**DoD:**
- [ ] Sinal configurável por percentual (0 = desativado)
- [ ] Slot não confirmado se sinal não pago (quando `upfront_percentage > 0`)
- [ ] Débito automático de crédito válido ao confirmar
- [ ] Crédito expirado não debitado
- [ ] Histórico de uso visível na ficha do cliente

---

## FASE 6 — ASSINATURAS E RECORRÊNCIA

---

### Sprint 6.1 — Modelo de assinaturas + planos

**Objetivo:** Tenant cria planos; estrutura completa antes de cobrar.

**Arquivos:**
- `agendamento_engine/migrations/` (nova migration)
- `agendamento_engine/app/infrastructure/db/models/subscription.py` (novo)
- `agendamento_engine/app/modules/subscriptions/router.py` (novo)
- `painel/app/(dashboard)/subscriptions/page.tsx` (novo)

**O que implementar:**
1. Model `SubscriptionPlan`: `id, company_id, name, credits_per_cycle, price, cycle_days, rollover_enabled (bool), is_active`
2. Model `CustomerSubscription`: `id, company_id, customer_id, plan_id, status (ACTIVE/SUSPENDED/CANCELLED), credits_balance, next_billing_at, cancelled_at`
3. CRUD de planos no painel
4. Vinculação manual de cliente a plano pelo admin
5. Lista de assinantes com status

**DoD:**
- [ ] Admin cria plano com créditos, preço e ciclo
- [ ] Cliente vinculado a plano visível na lista de assinantes
- [ ] Plano inativo não aparece para novos assinantes

---

### Sprint 6.2 — Cobrança recorrente via Asaas

**Objetivo:** Cobranças automáticas geradas na data de renovação.

**Arquivos:**
- `agendamento_engine/app/workers/billing_worker.py` (novo)
- `agendamento_engine/app/modules/subscriptions/service.py` (novo)
- `agendamento_engine/app/modules/payments/providers/asaas.py`

**O que implementar:**
1. Worker diário: seleciona `CustomerSubscription` com `status=ACTIVE AND next_billing_at <= now()`
2. Para cada assinatura: cria `PaymentOrder` + chama `AsaasProvider.create_payment()`
3. Webhook de confirmação: renova créditos + atualiza `next_billing_at = now() + cycle_days`
4. Rollover: `credits_balance += credits_per_cycle` (+ saldo anterior se `rollover_enabled`)

**DoD:**
- [ ] Worker roda diariamente sem intervenção manual
- [ ] Cobrança gerada apenas para assinaturas com `next_billing_at` vencido
- [ ] Créditos renovados apenas após confirmação de pagamento
- [ ] Falha na cobrança: assinatura permanece `ACTIVE` por 3 dias de carência

---

### Sprint 6.3 — Worker de inadimplência + gestão no painel

**Objetivo:** Assinatura suspensa após inadimplência; MRR no dashboard.

**Arquivos:**
- `agendamento_engine/app/workers/billing_worker.py`
- `agendamento_engine/app/modules/dashboard/service.py`
- `painel/app/(dashboard)/subscriptions/page.tsx`

**O que implementar:**
1. Worker: após 3 dias de carência sem pagamento → `status=SUSPENDED`
2. `SUSPENDED`: créditos bloqueados, agendamento não usa saldo
3. Reativação: pagamento confirmado → `status=ACTIVE`, créditos renovados
4. Cancelamento: `status=CANCELLED` com `cancelled_at` — créditos válidos até fim do ciclo pago
5. MRR integrado em `GET /dashboard/financial`: `SUM(plan.price)` de assinaturas `ACTIVE`

**DoD:**
- [ ] Suspensão após 3 dias sem pagamento
- [ ] Créditos de assinatura suspensa bloqueados
- [ ] Cancelamento preserva créditos até fim do ciclo
- [ ] MRR no dashboard financeiro com cálculo real

---

## FASE 7 — PORTAL DO TENANT + BILLING + SUPORTE

---

### Sprint 7.1 — Portal de configurações self-service

**Objetivo:** Tenant configura o produto sem precisar da sua intervenção.

**Arquivos:**
- `painel/app/(dashboard)/settings/` (expansão)
- `agendamento_engine/app/modules/settings/router.py` (expansão)
- `agendamento_engine/migrations/` (tabela `settings_audit`)

**O que implementar:**
1. Identidade visual configurável: logo, cor primária, nome exibido
2. Canais: toggle WhatsApp, toggle link público — aplicado imediatamente
3. Configurações de agendamento: `slot_interval_minutes`, `min_advance_hours`, `max_advance_days`
4. Gestão completa de unidades (evolução do Sprint 0.3)
5. Model `SettingsAudit`: `id, company_id, changed_by, field, old_value, new_value, changed_at`

**DoD:**
- [ ] Tenant muda cor do link público e aplica sem deploy
- [ ] Toggle de canal aplicado em tempo real
- [ ] Audit log: quem alterou o quê e quando
- [ ] Nenhuma configuração requer intervenção técnica sua

---

### Sprint 7.2 — Billing da plataforma + painel Owner completo

**Objetivo:** Você cobra os tenants automaticamente; painel Owner com MRR real.

**Arquivos:**
- `agendamento_engine/migrations/` (nova migration — `platform_plans`)
- `agendamento_engine/app/modules/owner/billing_service.py` (novo)
- `agendamento_engine/app/modules/owner/router.py` (expansão)
- `painel/app/owner/billing/page.tsx` (novo)

**O que implementar:**
1. Model `PlatformPlan`: `id, name, price, max_professionals, max_bookings_per_month`
2. FK `Company.platform_plan_id` + `Company.platform_billing_status`
3. Worker mensal: cobra tenant via Asaas
4. Trial: `Company.trial_ends_at` — suspenso automaticamente ao vencer sem plano
5. Painel Owner: MRR total, churn do mês, novos tenants, tenants por plano

**DoD:**
- [ ] Trial expira e suspende o tenant automaticamente
- [ ] Cobrança mensal gerada para tenants com plano ativo
- [ ] Inadimplência suspende após prazo configurável
- [ ] MRR no painel Owner calculado em tempo real

---

### Sprint 7.3 — Suporte in-app

**Objetivo:** Tenant abre tickets no painel; você responde no painel Owner.

**Arquivos:**
- `agendamento_engine/migrations/` (nova migration — `support_tickets`)
- `agendamento_engine/app/modules/support/router.py` (novo)
- `painel/app/(dashboard)/support/page.tsx` (novo)
- `painel/app/owner/support/page.tsx` (novo)

**O que implementar:**
1. Model `SupportTicket`: `id, company_id, subject, message, status (OPEN/IN_PROGRESS/RESOLVED), created_at, resolved_at`
2. Tenant: `POST /support/tickets/`, `GET /support/tickets/` (próprios)
3. Owner: `GET /owner/support/tickets?status=OPEN`, `PATCH /owner/support/tickets/{id}`
4. Notificação no WhatsApp do Owner para cada novo ticket
5. Changelog: `GET /changelog/` — últimas 5 novidades exibidas no painel do tenant

**DoD:**
- [ ] Tenant abre ticket sem sair do painel
- [ ] Owner recebe notificação no WhatsApp com assunto e nome do tenant
- [ ] Tickets gerenciáveis por status no painel Owner
- [ ] Changelog com pelo menos 3 itens reais

---

## PARTE 5 — ÍNDICE DE PRIORIDADES

**Fazer agora:**
`0.0a` (CORS) → `0.0b` (Sentry) → `0.1` (EXCLUDE CONSTRAINT + CONFIRMING)

**Antes de onboarding do 2º tenant:**
Sprints `0.2` → `1.6` completos + smoke test aprovado

**Antes de cobrar por pagamentos:**
Contrato Asaas lido → `5.0` → `5.1`

**Pode rodar em qualquer janela após Fase 1:**
Sprint `2.0` (IntentClassifier isolado)

**Não fazer ainda:**
Fases 6, 7 e expansão multi-vertical — dependem de validação das fases anteriores com cliente real

---

## PARTE 6 — CONTAGEM E REFERÊNCIA RÁPIDA

| Fase | Sprints | Dias úteis |
|------|---------|-----------|
| 0 — Fundação | 0.0a → 0.4b | 7 |
| 0.5 — Acessos | 0.5 → 0.8 | 4 |
| 1 — Painel | 1.0 → 1.7 | 8 |
| 2 — IA (isolado + integração) | 2.0, 2.6 | 2 |
| 2.5 — NPS + Fila | 2.1, 2.2, 2.3, 2.4, 2.5 | 5 |
| 3 — Link público | 3.1, 3.2, 3.3, 3.4 | 4 |
| 4 — Gestão | 4.1, 4.2, 4.3 | 3 |
| 5 — Pagamentos | 5.0, 5.1 *(2 dias)*, 5.2 | 4 |
| 6 — Assinaturas | 6.1, 6.2, 6.3 | 3 |
| 7 — Portal + billing | 7.1, 7.2, 7.3 | 3 |
| **Total** | **42 sprints** | **~43 dias úteis** |
