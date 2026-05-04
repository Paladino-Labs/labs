# PALADINO LABS — PLANO DE AUDITORIA v2.0

---

## PARTE 1 — FILOSOFIA E CADÊNCIA

### Por que auditar

O plano de execução tem 40 sprints distribuídos em 10 fases. Sem verificação estruturada entre eles, dois problemas emergem inevitavelmente em projetos solo:

1. **Deriva silenciosa:** o código diverge do planejado sem que ninguém perceba, e a divergência se acumula
2. **Dívida técnica não documentada:** desvios acontecem por boas razões, mas sem registro viram decisões esquecidas que geram retrabalho meses depois

A auditoria não é burocracia — é o mecanismo que garante que o que foi executado é o que foi planejado, e que os desvios são decisões conscientes, não acidentes.

### Três tipos de auditoria

| Tipo | Sigla | Quando ocorre | Duração estimada |
|------|-------|---------------|-----------------|
| Auditoria de Sprint Crítico | **ASC** | Após sprints de alto risco específicos | 30–45 min |
| Auditoria de Fim de Fase | **AFF** | Ao concluir cada fase completa | 60–90 min |
| Auditoria Regulatória | **AReg** | Antes de qualquer funcionalidade financeira | 90–120 min |

### Regra de progressão

```
Sprint concluído
      ↓
Auditoria devida? ──NÃO──→ Próximo sprint pode iniciar
      ↓ SIM
  Auditoria executada
      ↓
  APROVADA? ──NÃO──→ Correção obrigatória → Nova auditoria
      ↓ SIM
  Merge para main
      ↓
  Próximo sprint pode iniciar
```

**Sem auditoria aprovada, nenhum merge para `main` e nenhum sprint subsequente inicia.**

Cada sprint é desenvolvido em branch própria (`sprint/0.1-exclude-constraint`). O merge só ocorre após o documento de auditoria ser criado, preenchido e arquivado.

### Localização dos documentos de auditoria

```
/audits/
├── asc-1-cors-observabilidade.md
├── asc-2-exclude-constraint.md
├── aff-1-fase-0.md
├── aff-2-fase-0.5.md
├── aff-3-fase-1.md
├── asc-4-intent-classifier.md
├── aff-4-fase-2.5-ia.md
├── aff-5-fase-3.md
├── aff-6-fase-4.md
├── areg-1-asaas-contrato.md
├── asc-5-pagamentos-live.md
├── aff-7-fase-5.md
├── aff-8-fase-6.md
└── aff-9-fase-7.md
```

Cada documento de auditoria é commitado junto com o merge do sprint ou fase correspondente.

---

## PARTE 2 — CALENDÁRIO DE AUDITORIAS

```
Sprints 0.0a + 0.0b ──→ ASC-1 (CORS + Observabilidade — combinada)
Sprint 0.1          ──→ ASC-2 (Constraint + FSM)
Sprint 0.2
Sprint 0.3
Sprint 0.4          ──→ ASC-3 (Testes baseline)
Sprint 0.4b         ──→ ASC-2b (Hardening de segurança)
                      → AFF-1 (Fase 0 completa)

Sprint 0.5
Sprint 0.6
Sprint 0.7
Sprint 0.8          ──→ AFF-2 (Fase 0.5 completa)

Sprint 1.0
Sprint 1.1
Sprint 1.2
Sprint 1.3
Sprint 1.4
Sprint 1.5
Sprint 1.6
Sprint 1.7          ──→ AFF-3 (Fase 1 completa + Smoke test)

Sprint 2.0          ──→ ASC-4 (Contrato IA/FSM)
Sprint 2.1
Sprint 2.2
Sprint 2.3
Sprint 2.4
Sprint 2.5
Sprint 2.6          ──→ AFF-4 (Fase 2.5 + IA integrada)

Sprint 3.1
Sprint 3.2
Sprint 3.3
Sprint 3.4          ──→ AFF-5 (Fase 3 completa)

Sprint 4.1
Sprint 4.2
Sprint 4.3          ──→ AFF-6 (Fase 4 completa)

────────────────────→  AReg-1 (Antes de Sprint 5.0 — Contrato Asaas)

Sprint 5.0
Sprint 5.1          ──→ ASC-5 (Pagamentos live)
Sprint 5.2          ──→ AFF-7 (Fase 5 completa)

Sprint 6.1
Sprint 6.2
Sprint 6.3          ──→ AFF-8 (Fase 6 completa)

Sprint 7.1
Sprint 7.2
Sprint 7.3          ──→ AFF-9 (Fase 7 completa)
```

**Total: 6 ASC + 9 AFF + 1 AReg = 16 eventos de auditoria**

---

## PARTE 3 — CHECKLIST UNIVERSAL

Aplicado em **toda** auditoria, independentemente do tipo. Itens `[BLOQUEANTE]` reprovam a auditoria se não atendidos.

### Multi-tenant
- [ ] `[BLOQUEANTE]` Toda query nova filtra por `company_id`
- [ ] `[BLOQUEANTE]` Nenhum endpoint retorna dados de outro tenant (testar com token de tenant diferente)
- [ ] Novos models têm `company_id` obrigatório (exceto models globais documentados)

### Segurança
- [ ] `[BLOQUEANTE]` CORS ainda restrito a origens listadas (não `*`)
- [ ] `[BLOQUEANTE]` Nenhuma rota nova sem autenticação (exceto rotas públicas intencionais documentadas)
- [ ] `[BLOQUEANTE]` Stack trace não exposto em nenhuma resposta de erro ao usuário
- [ ] `[BLOQUEANTE]` Rate limiting ativo em `/auth/login` (verificar após Sprint 0.4b — manter em toda auditoria subsequente)
- [ ] Nenhum endpoint novo sem autenticação sem comentário explícito de "rota pública intencional" no router
- [ ] Nenhum CPF/CNPJ em texto puro em logs de produção

### Qualidade de código
- [ ] `[BLOQUEANTE]` Todos os itens do DoD dos sprints cobertos estão marcados como concluídos
- [ ] Nenhum cálculo financeiro (`subtotal`, `total`, `discount`) no frontend
- [ ] Nenhuma regra de negócio de agendamento fora do `BookingEngine`

### Observabilidade
- [ ] Sentry sem novos erros introduzidos pelos sprints cobertos (verificar dashboard)
- [ ] Novos endpoints geram logs estruturados com `company_id` e `request_id`

### Banco de dados
- [ ] Novas migrations são reversíveis (têm `downgrade()` funcional)
- [ ] Nenhuma migration quebrou dados existentes (verificar em produção)
- [ ] Queries novas sem N+1 evidente

### Estados terminais
- [ ] `[BLOQUEANTE]` `COMPLETED` e `CANCELLED` continuam impossíveis de mover via API, bot e admin

---

## PARTE 4 — AUDITORIAS DE SPRINT CRÍTICO (ASC)

---

### ASC-1 — Sprints 0.0a + 0.0b (CORS + Observabilidade) — auditoria combinada

**Gatilho:** Sprints 0.0a e 0.0b executados e prontos para merge
**Contexto:** Ambos os sprints foram executados antes do plano de auditoria ser formalizado. Esta auditoria é o gate de merge para os dois simultaneamente.

**Procedimento de rollback:**
- 0.0a (CORS): reverter `main.py` para `allow_origins=["*"]` — sem migration, rollback imediato
- 0.0b (Sentry/logging): remover `sentry-sdk` do `requirements.txt` e reverter `logging.py` — sem migration, rollback imediato
- Dados: sem impacto em nenhum dos dois

**Checklist — CORS (Sprint 0.0a)**
- [ ] `[BLOQUEANTE]` `curl -H "Origin: https://origem-nao-listada.com" -I <API_URL>/health` retorna 403 ou sem header `Access-Control-Allow-Origin`
- [ ] `[BLOQUEANTE]` Frontend em produção carregando e fazendo requests sem erro de CORS
- [ ] `[BLOQUEANTE]` `allow_origins=["*"]` inexistente em qualquer arquivo do projeto (`grep -r "allow_origins" .` não retorna wildcard)
- [ ] `ALLOWED_ORIGINS` lido do `.env`, não hardcoded

**Checklist — Observabilidade (Sprint 0.0b)**
- [ ] `[BLOQUEANTE]` Sentry recebendo eventos do ambiente de produção — verificar com evento de teste deliberado: lançar exceção manual em rota protegida e confirmar que aparece no dashboard Sentry dentro de 60 segundos
- [ ] `[BLOQUEANTE]` Logs em JSON estruturado (não texto livre) — verificar output do container em produção
- [ ] `[BLOQUEANTE]` `CryptContext` em `security.py` configurado com `bcrypt__rounds=12` explícito — não depender de default da biblioteca
- [ ] `request_id` presente nos logs de ao menos um request autenticado
- [ ] `company_id` presente nos logs de requests autenticados
- [ ] Nenhum CPF/CNPJ em texto puro nos logs (grep nos logs recentes)

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação:** Todos os 6 bloqueantes atendidos. Após aprovação: merge de ambos os branches para `main`, seguido de início do Sprint 0.1.

---

### ASC-2 — Sprint 0.1 (EXCLUDE CONSTRAINT + CONFIRMING)

**Gatilho:** Sprint 0.1 concluído
**Por que é crítica:** A constraint de exclusão é a proteção definitiva da agenda. Se estiver mal configurada, dois agendamentos simultâneos passam silenciosamente — e agora há cliente real em produção.

**Procedimento de rollback:**
- Migration: `alembic downgrade -1` (remove EXCLUDE CONSTRAINT)
- Código: reverter `engine.py` e `session_cleanup_worker.py`
- Dados: sem impacto nos dados existentes, constraint simplesmente removida
- Estimativa: 10 minutos

**Checklist específico:**
- [ ] `[BLOQUEANTE]` Sentry recebendo eventos de produção antes da migration — checar dashboard por erros novos desde o último deploy (confirma que ASC-1 não regrediu)
- [ ] `[BLOQUEANTE]` Extensão `btree_gist` confirmada como ativa no Supabase antes da migration (verificar via `SELECT * FROM pg_extension WHERE extname = 'btree_gist'`)
- [ ] `[BLOQUEANTE]` Teste manual em produção: dois requests simultâneos para o mesmo slot → apenas um confirma
- [ ] `[BLOQUEANTE]` Insert direto via SQL com sobreposição falha com `ExclusionViolationError` (testar via Supabase SQL editor)
- [ ] `[BLOQUEANTE]` Agendamentos existentes não foram afetados pela migration (verificar contagem antes/depois)
- [ ] Teste (Postgres): mesmo slot, profissionais diferentes → ambos confirmados com sucesso
- [ ] Estado `CONFIRMING` com mais de 5 min retorna para `AWAITING_CONFIRMATION` com `retry=True`
- [ ] `session_cleanup_worker` inclui limpeza de sessões `CONFIRMING` expiradas
- [ ] `pytest -m pg` passando com testes de constraint

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação:** Todos os 5 bloqueantes atendidos + zero agendamentos duplicados no banco em produção.

---

### ASC-2b — Após Sprint 0.4b (Hardening de segurança)

**Gatilho:** Sprint 0.4b concluído
**Por que é crítica:** Fecha vetores de ataque antes de adicionar novos perfis e rotas na Fase 0.5. Rate limiting ausente em `/auth/login` é o risco mais imediato — sem ele, o endpoint Owner (criado no Sprint 0.5) fica exposto a força bruta.

**Procedimento de rollback:**
- Código: remover middleware de headers + slowapi decorator — sem migration
- Dados: sem impacto
- Estimativa: 15 minutos

**Checklist específico:**

- [ ] `[BLOQUEANTE]` `/auth/login` retorna 429 após 5 tentativas em 1 minuto pelo mesmo IP (verificar com curl em loop)
- [ ] `[BLOQUEANTE]` Headers de segurança presentes em toda resposta da API — verificar via `curl -I <API_URL>/health`:
  - `X-Content-Type-Options: nosniff` presente
  - `X-Frame-Options: DENY` presente
  - `Strict-Transport-Security` presente
- [ ] `[BLOQUEANTE]` Nenhum endpoint existente quebrado pelos novos middlewares (smoke rápido: login, agendamento, bot webhook)
- [ ] `Retry-After` header presente na resposta 429
- [ ] `slowapi` adicionado ao `requirements.txt` e commitado
- [ ] Endpoints públicos intencionais documentados com comentário explícito nos routers `/public` e `/booking`

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação:** Todos os 3 bloqueantes atendidos + nenhum erro novo no Sentry pós-deploy.

---

### ASC-3 — Sprint 0.4 (Testes baseline)

**Gatilho:** Sprint 0.4 concluído
**Por que é crítica:** O Sprint 0.4 estabelece a linha de base de testes. Tudo que vem depois assume que essa base existe e é confiável.

**Procedimento de rollback:**
- Sem migration, sem impacto em produção
- Rollback: remover arquivos de teste — sem consequências para o sistema

**Checklist específico:**
- [ ] `[BLOQUEANTE]` `pytest -m "not pg"` passa em menos de 10 segundos
- [ ] `[BLOQUEANTE]` `pytest -m pg` passa com banco Postgres real via testcontainers
- [ ] `[BLOQUEANTE]` 7 testes implementados e passando (listados no DoD do Sprint 0.4)
- [ ] Fixture `db_pg` usa `engine.begin()` com rollback (nunca commita)
- [ ] Testes de violação de constraint usam `SAVEPOINT` interno ao teste
- [ ] Testes SQLite sem nenhuma chamada de rede ou banco externo
- [ ] CI configurado: `pytest -m "not pg"` roda em todo PR
- [ ] Workers asyncio documentados como temporários — comentário em `main.py` indicando que serão migrados no Sprint 1.7 (não é bloqueante, mas deve estar registrado antes de avançar)

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação:** Todos os 3 bloqueantes + CI verde.

---

### ASC-4 — Sprint 2.0 (IntentClassifier)

**Gatilho:** Sprint 2.0 concluído
**Por que é crítica:** O classificador foi implementado isolado. Antes de qualquer integração com o bot, verificar que o contrato está correto e que o bot atual não foi tocado.

**Procedimento de rollback:**
- Sem migration, sem impacto em produção
- Rollback: remover diretório `intent/` — bot continua funcionando como antes

**Checklist específico:**
- [ ] `[BLOQUEANTE]` Teste bidirecional passando: todo intent do classificador tem handler registrado; todo handler registrado tem intent correspondente no classificador
- [ ] `[BLOQUEANTE]` `REGISTERED_HANDLERS` implementado como `dict` no dispatcher (não `if/elif`)
- [ ] `[BLOQUEANTE]` Zero modificação em `bot_service.py` ou handlers existentes (verificar diff completo dos arquivos)
- [ ] `ChainClassifier.known_intents` exposto como propriedade com conjunto completo
- [ ] Mensagem óbvia (`"quero agendar"`) não chama OpenAI (verificar logs de custo)
- [ ] Custo por chamada OpenAI sendo logado quando acionado
- [ ] Bot em produção com comportamento idêntico ao pré-sprint (verificar com cliente atual)

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação:** Todos os 3 bloqueantes + bot em produção inalterado.

---

### ASC-5 — Sprint 5.1 (Pagamentos live)

**Gatilho:** Sprint 5.1 concluído
**Por que é crítica:** Primeiro sprint com dinheiro real em trânsito. Qualquer bug aqui tem impacto financeiro direto e não tem rollback simples.

**Procedimento de rollback:**
- Migration: `alembic downgrade` (remove tabelas de payments) — **executar apenas se zero transações reais registradas**
- Código: reverter módulo payments, desativar webhook endpoint
- Dados: transações já processadas são **irreversíveis** sem procedimento manual de estorno no Asaas — documentar cada transação real antes de qualquer rollback
- Estimativa para rollback limpo (sem transações): 30 minutos
- Estimativa para rollback com transações: requer contato com Asaas — sem estimativa garantida

**Checklist específico:**
- [ ] `[BLOQUEANTE]` Pix gerado e confirmado em ambiente de produção Asaas (não sandbox) com transação real de valor mínimo (R$ 0,01 se permitido, ou valor real acordado com cliente)
- [ ] `[BLOQUEANTE]` Webhook idempotente verificado: enviar o mesmo evento duas vezes via replay do Asaas não cria duas `PaymentTransaction`
- [ ] `[BLOQUEANTE]` `PaymentOrder.provider` imutável: tentativa de update via request direto retorna erro tanto no ORM quanto no banco (testar ambas as camadas separadamente)
- [ ] `[BLOQUEANTE]` `total_amount` não presente em nenhum request do frontend (inspecionar network tab durante fluxo completo)
- [ ] `[BLOQUEANTE]` Appointment não confirmado quando `require_payment_upfront=True` e pagamento não realizado
- [ ] `NullProvider` passa em todos os testes do módulo com `payment_outcome="PAID"` e `payment_outcome="FAILED"`
- [ ] Webhook handler registra log de cada evento recebido com `external_reference`
- [ ] Nenhuma chave de API do Asaas em código ou log (apenas em `.env`)
- [ ] Trigger de imutabilidade ativo no banco (verificar via `\d payment_orders` no Supabase — trigger deve aparecer na listagem)

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação:** Todos os 5 bloqueantes atendidos + transação real registrada corretamente no banco com `provider="asaas"` imutável.

---

## PARTE 5 — AUDITORIAS DE FIM DE FASE (AFF)

---

### AFF-1 — Fase 0 completa (após Sprint 0.4)

**Procedimento de rollback da fase:**
- Migrations: `alembic downgrade -3` reverte locations + FKs nullable
- Dados de locations: irreversíveis se já populados — exportar antes do rollback
- Constraint: `alembic downgrade -1` remove EXCLUDE CONSTRAINT
- Estimativa para rollback completo da fase: 45 minutos (sem dados em locations)

**Checklist — Fundação de segurança**
- [ ] `[BLOQUEANTE]` ASC-1, ASC-2, ASC-2b e ASC-3 aprovadas e documentadas em `/audits/`
- [ ] `[BLOQUEANTE]` CORS restrito verificado em produção (repetir teste do ASC-1)
- [ ] `[BLOQUEANTE]` EXCLUDE CONSTRAINT ativo e testado em produção (repetir teste do ASC-2)
- [ ] `[BLOQUEANTE]` Sentry ativo com alertas configurados (repetir verificação do ASC-1)
- [ ] `[BLOQUEANTE]` Rate limiting ativo em `/auth/login`
- [ ] `[BLOQUEANTE]` Security headers presentes em toda resposta da API
- [ ] bcrypt com rounds=12 configurado explicitamente em `security.py`

**Checklist — Banco de dados**
- [ ] Tabela `locations` criada e migrada sem perda de dados
- [ ] FK nullable `location_id` em `appointments` e `professionals` sem impacto nos dados existentes
- [ ] Todas as migrations têm `downgrade()` funcional

**Checklist — Qualidade**
- [ ] 7 testes do Sprint 0.4 passando
- [ ] CI configurado e verde

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação para avançar para Fase 0.5:** Todos os 6 bloqueantes + banco sem migrations pendentes.

---

### AFF-2 — Fase 0.5 completa (após Sprint 0.8)

**Procedimento de rollback da fase:**
- Sem migrations novas nesta fase
- Código: reverter mudanças em `deps.py`, `user.py`, módulo `owner/`
- Dados: `UserRole` enum alterado — reverter requer migration manual
- Estimativa: 20 minutos (sem dados de Owner criados em produção)

**Checklist — Dependências de auditorias anteriores**
- [ ] `[BLOQUEANTE]` AFF-1 aprovada sem ressalvas pendentes (aprovada em: ____/____/____)

**Checklist — Perfis e autenticação**
- [ ] `[BLOQUEANTE]` 5 perfis ativos: `OWNER`, `ADMIN`, `RECEPTIONIST`, `PROFESSIONAL`, `CLIENT`
- [ ] `[BLOQUEANTE]` Teste cruzado: token de Admin do Tenant A não acessa dados do Tenant B (testar em produção com dois tenants reais ou simulados)
- [ ] `[BLOQUEANTE]` Owner sem `company_id` não quebra nenhuma query existente (verificar logs de erro no Sentry após login do Owner)
- [ ] `[BLOQUEANTE]` Recepção recebe 403 em rotas financeiras e de configuração (testar pelo menos 3 rotas bloqueadas)
- [ ] Profissional só vê os próprios appointments (testar com login de profissional real)
- [ ] UI condicional funcionando para todos os perfis sem flash de conteúdo indevido

**Checklist — Painel Owner**
- [ ] Owner vê lista real de tenants com métricas do banco
- [ ] Nenhum outro perfil acessa `/owner/*` (testar com token Admin)

**Checklist — Gestão de senha**
- [ ] `[BLOQUEANTE]` Troca de senha autenticada funcionando para todos os perfis (Admin, Recepção, Profissional, Owner)
- [ ] `[BLOQUEANTE]` Usuário com `must_change_password=True` não acessa nenhuma rota antes de trocar a senha
- [ ] `[BLOQUEANTE]` Token de recuperação invalidado após uso (testar: usar o mesmo token duas vezes → segundo uso retorna erro)
- [ ] Recuperação de senha via WhatsApp: mensagem entregue com código de 6 dígitos
- [ ] Token de recuperação expira após 15 minutos (testar com token gerado há 16 minutos)
- [ ] Senha fraca rejeitada com mensagem específica em todos os fluxos: troca, recuperação e criação de usuário
- [ ] Novo usuário criado pelo Admin recebe senha temporária via WhatsApp
- [ ] Após troca de senha: todas as sessões anteriores invalidadas

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação para avançar para Fase 1:** Todos os 8 bloqueantes + cada perfil testado manualmente com login real.

---

### AFF-3 — Fase 1 completa (após Sprint 1.6 — Smoke Test)

**Nota:** O Sprint 1.6 é o smoke test operacional. A AFF-3 é a formalização documental dos resultados.

**Procedimento de rollback da fase:**
- Uploads (Sprint 1.0): reverter para volume Docker + executar script de reversão de URLs — **script deve existir e ter sido testado antes do deploy para Supabase** (DoD do Sprint 1.0 inclui `[ ] Script de rollback de URLs testado antes de executar a migração de arquivos`)
- Demais sprints: sem migrations críticas — reverter via código
- Estimativa: 60 minutos (dominado pelo tempo de reverter URLs de arquivos no banco)

**Checklist — Dependências de auditorias anteriores**
- [ ] `[BLOQUEANTE]` AFF-1 aprovada sem ressalvas pendentes (aprovada em: ____/____/____)
- [ ] `[BLOQUEANTE]` AFF-2 aprovada sem ressalvas pendentes (aprovada em: ____/____/____)

**Checklist — Infraestrutura**
- [ ] `[BLOQUEANTE]` Uploads em Supabase Storage — nenhuma foto em volume Docker
- [ ] `[BLOQUEANTE]` Sprint 1.7 concluído — workers Celery + Redis ativos no Railway antes de avançar para Fase 2.5
- [ ] `[BLOQUEANTE]` Deploy sem volume Docker confirmado sem perda de arquivos (verificar após próximo deploy)
- [ ] Script de rollback de URLs existe em `/scripts/rollback-uploads.py` e foi testado antes do deploy

**Checklist — Painel profissional**
- [ ] `[BLOQUEANTE]` Agendamento completo via painel (Admin e Recepção) funcionando em produção
- [ ] `[BLOQUEANTE]` Profissional inativo ausente em bot, link e painel (testar desativando profissional real)
- [ ] CRUD de profissional com foto, serviços e horários funcionando
- [ ] Lembretes com opt-out funcionando (testar com "PARE" no bot)
- [ ] Relatório por profissional com CSV exportável

**Checklist — Smoke test (8 cenários do Sprint 1.6)**
- [ ] `[BLOQUEANTE]` Todos os 8 cenários aprovados e documentados
- [ ] `[BLOQUEANTE]` Nenhum erro no Sentry durante os 8 cenários
- [ ] Checklist do smoke test arquivado com data e resultado por cenário

**Checklist — Workers e confiabilidade**
- [ ] `[BLOQUEANTE]` Celery worker rodando como serviço separado no Railway (verificar no dashboard)
- [ ] `[BLOQUEANTE]` Lembrete entregue com retry: simular falha temporária da Evolution API → verificar que lembrete é re-tentado e entregue na tentativa seguinte
- [ ] Workers asyncio antigos removidos do `main.py`
- [ ] Falha persistente (3 tentativas) aparece no Sentry com `appointment_id` e tipo de lembrete
- [ ] `reminder_sent` flag setado apenas após confirmação de entrega (não antes da tentativa)

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação para avançar para Fase 2.5:** Todos os 9 bloqueantes + smoke test arquivado. **Esta é a porta de entrada para onboarding do 2º tenant.**

---

### AFF-4 — Fase 2.5 + IA integrada (após Sprint 2.6)

**Procedimento de rollback da fase:**
- Migrations: `alembic downgrade -2` reverte tabelas `reviews` e `waitlist`
- Dados de reviews e waitlist: irreversíveis se já populados — exportar antes
- IA (Sprint 2.6): reverter `bot_service.py` — bot volta ao comportamento anterior sem impacto em dados
- Estimativa: 30 minutos

**Checklist — Dependências de auditorias anteriores**
- [ ] `[BLOQUEANTE]` AFF-3 aprovada sem ressalvas pendentes (aprovada em: ____/____/____)

**Checklist — NPS e avaliações**
- [ ] `[BLOQUEANTE]` Trigger pós-COMPLETED enviando solicitação de NPS em produção (verificar com agendamento real marcado como COMPLETED)
- [ ] Avaliação duplicada para o mesmo appointment retorna registro existente (não cria novo)
- [ ] Média de NPS por profissional no painel com dados reais
- [ ] Sugestão de Google review respeitando regra completa: nota ≥ 4, 3+ atendimentos, 90 dias de intervalo

**Checklist — Fila de espera**
- [ ] `[BLOQUEANTE]` Cancelamento de agendamento dispara notificação para próximo da fila com match (testar em produção)
- [ ] Expiração de posição na fila funcionando — entrada expirada não bloqueia slot
- [ ] Fila disponível no bot e no link público quando sem slots

**Checklist — IA no bot**
- [ ] `[BLOQUEANTE]` Bot em produção com comportamento idêntico ao pré-Sprint 2.6 para todos os estados de booking (apenas `MENU_PRINCIPAL` usa classificador)
- [ ] ASC-4 aprovada e documentada
- [ ] Classificador não altera estado de nenhuma sessão (verificar logs de estado antes e depois)

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação para avançar para Fase 3:** Todos os 4 bloqueantes + pelo menos 1 avaliação real registrada em produção.

---

### AFF-5 — Fase 3 completa (após Sprint 3.4)

**Procedimento de rollback da fase:**
- Migration: `alembic downgrade -1` reverte tabela `promotions`
- Dados de promoções: irreversíveis se já usadas em agendamentos reais
- OG tags e SEO: reverter `page.tsx` — sem impacto em dados
- Estimativa: 20 minutos

**Checklist — Dependências de auditorias anteriores**
- [ ] `[BLOQUEANTE]` AFF-4 aprovada sem ressalvas pendentes (aprovada em: ____/____/____)

**Checklist — Link público**
- [ ] `[BLOQUEANTE]` OG tags corretos verificados com dispositivo real: compartilhar link no WhatsApp e confirmar preview com foto e nome do estabelecimento
- [ ] `[BLOQUEANTE]` Slug inválido retorna HTTP 404 real (verificar via `curl -I <URL>/book/slug-invalido`)
- [ ] Avaliações anonimizadas no link público (confirmar: nunca nome completo ou telefone visível)
- [ ] Seção de avaliações ausente para empresa sem avaliações

**Checklist — Promoções**
- [ ] `[BLOQUEANTE]` Cupom com `max_uses=1` recusado no segundo uso mesmo com requests simultâneos
- [ ] `discount_amount` calculado pelo backend em todos os fluxos: web, bot e admin (inspecionar network tab nos três)
- [ ] `uses_count` atômico (verificar que não ultrapassa `max_uses` em teste de concorrência)

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação para avançar para Fase 4:** Todos os 3 bloqueantes + link público testado em dispositivo móvel real.

---

### AFF-6 — Fase 4 completa (após Sprint 4.3)

**Procedimento de rollback da fase:**
- Migration: `alembic downgrade -1` reverte tabela `expenses`
- Dados: receitas no dashboard vêm de `appointments` (sem dados próprios a perder); despesas irreversíveis se já registradas
- Estimativa: 15 minutos

**Checklist — Dependências de auditorias anteriores**
- [ ] `[BLOQUEANTE]` AFF-5 aprovada sem ressalvas pendentes (aprovada em: ____/____/____)

**Checklist — Dashboard e financeiro**
- [ ] `[BLOQUEANTE]` KPIs do dashboard com dados reais — verificar comparando valores do dashboard com query direta no Supabase
- [ ] `[BLOQUEANTE]` Recepção não acessa página financeira (403 verificado com login real de Recepção)
- [ ] Ticket médio exclui cancelamentos do cálculo (verificar com agendamento cancelado na base)

**Checklist — CRM**
- [ ] `[BLOQUEANTE]` Ficha do cliente sem N+1 queries — verificar com query logging ativo no SQLAlchemy (`echo=True`) durante acesso à ficha
- [ ] Status `em_risco` calculado pelo backend (não frontend) — verificar via resposta da API diretamente
- [ ] Observações salvas sem apagar conteúdo anterior (testar duas edições consecutivas)

**Checklist — Contábil**
- [ ] DRE mensal com receitas exclusivamente de `appointments` (nunca entrada manual de receita)
- [ ] CSV exportável abrindo corretamente no Excel ou Google Sheets

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação para avançar para AReg-1:** Todos os 4 bloqueantes + DRE de pelo menos 1 mês real gerado e verificado.

---

### AReg-1 — Auditoria Regulatória (antes do Sprint 5.0)

**Tipo especial:** Esta auditoria não verifica código — verifica decisões contratuais e regulatórias antes de qualquer dinheiro real passar pelo sistema.

**Procedimento de rollback:** Não aplicável — nenhum código foi escrito ainda neste ponto.

**Checklist regulatório:**
- [ ] `[BLOQUEANTE]` Contrato Asaas lido na íntegra — cláusula de responsabilidade de KYC identificada e transcrita no documento de auditoria
- [ ] `[BLOQUEANTE]` Confirmação **escrita do suporte Asaas** (email, ticket ou documento oficial) de que o Paladino opera como facilitador tecnológico, não como subadquirente ou agente de liquidação — transcrição ou screenshot no documento de auditoria com data, canal e ID do atendente
- [ ] `[BLOQUEANTE]` Entendimento documentado com **resposta escrita do Asaas**: quem é responsável se dados de KYC enviados via API estiverem incorretos ou incompletos
- [ ] `[BLOQUEANTE]` Modelo de pricing documentado com valores reais: taxa percentual por transação, custo por subconta, custo de criação de subconta — obtido por escrito do Asaas ou da documentação oficial
- [ ] Confirmado se subcontas de profissionais PF precisam de processo diferente de subcontas de empresa PJ
- [ ] Processo de `pending_verification` → `active` documentado: prazo, documentos necessários, canal de suporte para bloqueios
- [ ] Contato de suporte técnico do Asaas identificado e registrado

**Nota sobre validação:** Interpretação própria de cláusula contratual sem confirmação escrita do Asaas = item não atendido = auditoria REPROVADA. O documento `areg-1-asaas-contrato.md` deve conter respostas escritas, não paráfrases.

**Critério de aprovação:** Todos os 4 bloqueantes com respostas escritas do Asaas documentadas. **Sprint 5.0 não inicia sem AReg-1 aprovada.**

---

### AFF-7 — Fase 5 completa (após Sprint 5.2)

**Procedimento de rollback da fase:**
- Migrations: `alembic downgrade -3` (remove credit_packages, customer_credits, payment_orders, payment_transactions, split_entries)
- Dados financeiros: **irreversíveis** — transações processadas requerem estorno manual no Asaas; documentar toda transação real antes de qualquer rollback
- Estimativa para rollback sem transações reais: 30 minutos
- Estimativa com transações reais: contato com Asaas obrigatório, sem estimativa garantida

**Checklist — Dependências de auditorias anteriores**
- [ ] `[BLOQUEANTE]` AReg-1 aprovada (aprovada em: ____/____/____)
- [ ] `[BLOQUEANTE]` AFF-6 aprovada sem ressalvas pendentes (aprovada em: ____/____/____)

**Checklist — Pagamentos**
- [ ] `[BLOQUEANTE]` ASC-5 aprovada e documentada
- [ ] `[BLOQUEANTE]` Transação real de Pix processada e registrada corretamente (provider="asaas", status transicionando corretamente)
- [ ] `[BLOQUEANTE]` Webhook idempotente verificado em produção: replay de evento não cria transação duplicada
- [ ] `[BLOQUEANTE]` `PaymentOrder.provider` imutável confirmado via ORM e via trigger no banco (ambos testados independentemente)

**Checklist — Subcontas**
- [ ] Pelo menos 1 subconta de tenant criada e com `external_account_status=active`
- [ ] CPF com dígito verificador inválido rejeitado no frontend antes de chamar API (testar manualmente)
- [ ] Banner `pending_verification` exibido e instruções corretas

**Checklist — Sinal e créditos**
- [ ] Sinal percentual configurável funcionando (testar com `upfront_percentage=50`)
- [ ] Crédito com `expires_at` no passado não debitado (testar com data forçada)

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação para avançar para Fase 6:** Todos os 4 bloqueantes + nenhuma transação duplicada no banco em produção.

---

### AFF-8 — Fase 6 completa (após Sprint 6.3)

**Procedimento de rollback da fase:**
- Migrations: `alembic downgrade -2` (remove subscription_plans, customer_subscriptions)
- Dados de assinaturas: irreversíveis se cobranças reais realizadas — documentar assinantes ativos antes do rollback
- Worker de billing: desativar antes de reverter migrations
- Estimativa sem cobranças reais: 20 minutos

**Checklist — Dependências de auditorias anteriores**
- [ ] `[BLOQUEANTE]` AFF-7 aprovada sem ressalvas pendentes (aprovada em: ____/____/____)

**Checklist de fase:**
- [ ] `[BLOQUEANTE]` Cobrança recorrente executada para pelo menos 1 assinatura real — não simular, executar ciclo real
- [ ] `[BLOQUEANTE]` Suspensão após inadimplência verificada: forçar falha de pagamento → aguardar carência → confirmar `status=SUSPENDED` no banco
- [ ] `[BLOQUEANTE]` Créditos de assinatura suspensa bloqueados: tentativa de uso → recusado com mensagem clara
- [ ] Rollover de créditos funcionando quando `rollover_enabled=True`
- [ ] MRR no dashboard refletindo assinaturas ativas com cálculo verificado contra banco

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação para avançar para Fase 7:** Todos os 3 bloqueantes + 1 ciclo completo documentado: cobrança → créditos → uso → renovação.

---

### AFF-9 — Fase 7 completa (após Sprint 7.3)

**Procedimento de rollback da fase:**
- Migrations: `alembic downgrade -3` (remove platform_plans, support_tickets, settings_audit)
- Dados: tickets de suporte e audit log irreversíveis se já criados — exportar antes
- Billing de plataforma: desativar worker antes de reverter
- Estimativa: 30 minutos

**Checklist — Dependências de auditorias anteriores**
- [ ] `[BLOQUEANTE]` AFF-8 aprovada sem ressalvas pendentes (aprovada em: ____/____/____)

**Checklist de fase:**
- [ ] `[BLOQUEANTE]` Tenant configura identidade visual sem intervenção técnica (testar com tenant real: mudar cor e confirmar que o link público reflete em menos de 60 segundos)
- [ ] `[BLOQUEANTE]` Toggle de canal aplica em tempo real: desativar link público → link retorna 404 imediatamente; reativar → volta a funcionar
- [ ] `[BLOQUEANTE]` Cobrança de plataforma gerada para tenant com plano ativo (verificar registro no banco)
- [ ] Audit log de configurações registrando alterações com autor e timestamp (fazer alteração e verificar log)
- [ ] Ticket de suporte aberto pelo tenant → notificação recebida no WhatsApp do Owner dentro de 2 minutos
- [ ] Trial expirado: `trial_ends_at` no passado → tenant suspenso automaticamente (testar com data forçada)

**Checklist universal:** aplicar conforme Parte 3

**Critério de aprovação:** Todos os 3 bloqueantes. Esta auditoria marca o fim do roadmap definido até a Fase 7. Expansão multi-vertical e app mobile são avaliados em planejamento separado.

---

## PARTE 6 — PROTOCOLO DE DESVIOS

### Definição

Qualquer diferença entre o planejado e o implementado. Inclui funcionalidade não implementada, implementação diferente da planejada, decisão arquitetural alterada, item do DoD não atendido, sprint dividido ou fundido.

### Classificação

| Severidade | Definição | Obrigação |
|-----------|-----------|-----------|
| **Crítico** | Afeta segurança, multi-tenant ou integridade financeira | Corrigir antes do merge. Sem exceção. |
| **Médio** | Afeta funcionalidade planejada mas tem workaround | Documentar + decidir: corrigir agora ou criar sprint de correção explícito |
| **Baixo** | Variação de implementação sem impacto funcional | Documentar e registrar como decisão técnica |

### Registro obrigatório

```markdown
## Desvio #N

**Sprint:** X.Y
**Severidade:** Crítico / Médio / Baixo

**Planejado:**
[Descrição exata do que estava no plano de execução]

**Implementado:**
[Descrição do que foi realmente feito]

**Justificativa:**
[Por que o desvio aconteceu — técnica, temporal, descoberta nova]

**Impacto em sprints futuros:**
[Nenhum / Lista de sprints afetados e como]

**Decisão:**
[ ] Aceito como está — sem ação necessária
[ ] Requer sprint de correção → criar Sprint X.Y-fix antes de avançar
[ ] Requer ajuste no plano de execução → atualizar documento

**Ajuste no plano de execução:**
[Se aplicável: qual seção foi atualizada e como]
```

---

## PARTE 7 — TEMPLATE DO DOCUMENTO DE AUDITORIA

Nomenclatura do arquivo: `{tipo}-{identificador}-{YYYY-MM-DD}.md`

```markdown
# Auditoria {TIPO} — {Identificador}
**Data:** YYYY-MM-DD
**Sprints cobertos:** X.Y → X.Z
**Auditor:** [nome]
**Status final:** APROVADA | APROVADA COM RESSALVAS | REPROVADA

**Procedimento de rollback:**
- Migrations: [nenhuma / comando específico / irreversível — ver nota]
- Código: [reverter branch / feature flag / sem rollback necessário]
- Dados: [sem impacto / script em `/scripts/rollback-X.Y.py` / irreversível — documentar]
- Estimativa de tempo para rollback completo: ____

---

## Checklist universal

### Multi-tenant
- [ ] [BLOQUEANTE] Toda query nova filtra por company_id
- [ ] [BLOQUEANTE] Nenhum endpoint retorna dados de outro tenant
- [ ] Novos models têm company_id obrigatório (ou ausência documentada)

### Segurança
- [ ] [BLOQUEANTE] CORS restrito (não *)
- [ ] [BLOQUEANTE] Nenhuma rota nova sem autenticação indevida
- [ ] [BLOQUEANTE] Stack trace não exposto ao usuário
- [ ] Nenhum CPF/CNPJ em logs

### Qualidade
- [ ] [BLOQUEANTE] Todos os DoD dos sprints cobertos completos
- [ ] Nenhum cálculo financeiro no frontend
- [ ] Nenhuma regra de agendamento fora do BookingEngine

### Observabilidade
- [ ] Sentry sem novos erros introduzidos
- [ ] Novos endpoints com logs estruturados

### Banco
- [ ] Migrations reversíveis
- [ ] Dados existentes intactos
- [ ] Sem N+1 evidente

### Estados terminais
- [ ] [BLOQUEANTE] COMPLETED e CANCELLED imóveis via API, bot e admin

---

## Checklist específico

[Itens da seção correspondente nas Partes 4 e 5]

---

## Resultado dos DoDs

| Sprint | Todos os itens concluídos? | Observações |
|--------|---------------------------|-------------|
| X.Y    | Sim / Não                 |             |

---

## Desvios identificados

[Preencher com template da Parte 6 para cada desvio]
Se nenhum: "Nenhum desvio identificado."

---

## Decisão final

**Status:** APROVADA | APROVADA COM RESSALVAS | REPROVADA

**Se APROVADA COM RESSALVAS:**
- Ressalva 1: [descrição + prazo de correção + sprint responsável]

**Se REPROVADA:**
- Motivo: [bloqueante não atendido]
- Ação requerida: [o que precisa acontecer para nova auditoria]

**Próximo passo autorizado:**
[ ] Sprint X+1 pode iniciar
[ ] Correção obrigatória antes de avançar
[ ] Nova auditoria agendada após correção
```

---

## PARTE 8 — REFERÊNCIA RÁPIDA

### Calendário completo

| Evento | Auditoria | Bloqueia |
|--------|-----------|---------|
| Sprints 0.0a + 0.0b executados | **ASC-1** (combinada) | Merge de 0.0a e 0.0b + Sprint 0.1 |
| Sprint 0.1 concluído | **ASC-2** | Sprint 0.2 |
| Sprint 0.4 concluído | **ASC-3** | Sprint 0.4b |
| Sprint 0.4b concluído | **ASC-2b + AFF-1** | Fase 0.5 |
| Sprint 0.8 concluído | **AFF-2** | Fase 1 |
| Sprint 1.6 concluído | **AFF-3** | Fase 2.5 + onboarding 2º tenant |
| Sprint 1.7 concluído | (coberto AFF-3) | Fase 2.5 liberada |
| Sprint 2.0 concluído | **ASC-4** | Sprint 2.6 |
| Sprint 2.6 concluído | **AFF-4** | Fase 3 |
| Sprint 3.4 concluído | **AFF-5** | Fase 4 |
| Sprint 4.3 concluído | **AFF-6** | AReg-1 |
| Antes do Sprint 5.0 | **AReg-1** | Sprint 5.0 |
| Sprint 5.1 concluído | **ASC-5** | Sprint 5.2 |
| Sprint 5.2 concluído | **AFF-7** | Fase 6 |
| Sprint 6.3 concluído | **AFF-8** | Fase 7 |
| Sprint 7.3 concluído | **AFF-9** | Expansão |

### Regra dos bloqueantes

> Qualquer item marcado `[BLOQUEANTE]` não atendido = auditoria **REPROVADA**.
> Auditoria reprovada = merge bloqueado = próximo sprint não inicia.
> Não há exceções para bloqueantes. Só há correção.
