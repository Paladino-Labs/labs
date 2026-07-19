# SPRINT-LOG — agendamento_engine

## Sprint de Integrações (APIs externas) — 2026-06-02 a 2026-06-04

**HEAD antes do sprint:** `d1e2f3g4h5i6` (align_orm_schema_gaps)
**HEAD após sprint (quando commitado):** `g3h4i5j6k7l8` (add_maquininha_pix_fee_source)
**Total de testes:** 338/338 (conforme commit 457d807)
**Commits do sprint:**

```
457d807  feat: taxa automatica de maquininha em confirm-manual (338/338)
a45fb65  feat: Bloco 1 — fluxo de convite de usuario validado
4a7d9e4  fix(auth): forgot_password para PLATFORM_OWNER (company_id=None)
10d1baa  fix(communication): header correto para Mailtrap producao vs sandbox
797fc99  fix(users): invitation_id ja e UUID no Postgres, nao requer conversao
f973a78  debug(users): logar excecao no envio de email de convite
6831021  fix(users): convite sempre usa audience=CLIENT no dispatch de email
48d8e91  docs: CLAUDE.md — dívida email produção (Railway bloqueia SMTP)
46a4f34  feat(users): envio de email de convite via CommunicationService
dac8341  feat: Bloco 1 — email recuperacao de senha via Mailtrap HTTP API
475e6a5  feat(communication): suporte a Mailtrap HTTP API como fallback ao SMTP bloqueado
5692541  feat: Bloco 1 — canal EMAIL no CommunicationService
720626b  fix(payments): validar CPF e CNPJ antes de enviar ao Asaas
6cc2697  fix(payments): mapear billingType interno para valores aceitos pelo Asaas
b581bad  fix(payments): adicionar dueDate e cpf_cnpj ao fluxo de cobranca Asaas
a9aef05  fix(payments): savepoint em _resolve_api_key para evitar InFailedSqlTransaction
4d1af3a  fix(payments): resolver Asaas customer ID antes de criar cobranca
ce69ab2  fix: Bloco 2 — Asaas bugs criticos de webhook e charge
3c21bd4  docs: CLAUDE.md — gap birthDate Asaas create_subaccount
31892ba  fix: Bloco 2 — Asaas bugs criticos (external_charge_id + value/fee parsing)
2063e58  feat: Bloco 4 — confirmação síncrona de pagamento CASH/manual
c2d5546  feat: Bloco 5 — Evolution API validação e hardening
```

**Pendências em aberto ao término do sprint:** ver `docs/pendencias-pos-sprint-integracoes.md`

---

## Sprint Frontend + Ajustes pós-sprint — 2026-06-04 a 2026-06-05

**HEAD backend antes do sprint:** g3h4i5j6k7l8 (sem alterações de backend neste sprint)
**HEAD frontend:** 38b8c66 (feat: dashboard financeiro com KPIs e gráfico de área)

### Pré-requisito backend executado
- Migration h2i3j4k5l6m7: ADD COLUMN users.name VARCHAR(100) nullable
- GET /auth/me, POST /users/invite, PATCH /auth/profile: campo name incluído

### Sprint frontend — Blocos A–F (14 requisitos)
**Bloco A:** Sidebar (MENU, Painel, Financeiro), AuthContext.name, logo maior
**Bloco B:** /agenda com calendário por padrão, dashboard sem OVERVIEW,
             lista de próximos agendamentos, botão registrar pagamento
**Bloco C:** Campo CPF removido do formulário de profissional (campo mantido no banco)
**Bloco D:** Módulo Financeiro (/financeiro, /pagamentos, /movimentacoes, /pagamentos/novo)
             CustomerAutocomplete, FeeWarningBanner, RBAC OWNER/ADMIN
**Bloco E:** Configurações expandidas: Taxas, Integrações (WhatsApp + Asaas),
             Comunicação (PUT), Usuários com campo nome no convite
**Bloco F:** /activate — página de ativação de conta com nome opcional

### Ajustes pós-sprint (8 de 9 concluídos)
- Ajuste 1: guard hydrated em settings/taxas (Cenário C)
- Ajuste 2: api.ts parseDetailMessage() — erros 422 FastAPI legíveis
- Ajuste 3: Taxas movidas para /financeiro/taxas; /settings/taxas → redirect
- Ajuste 4: Aba PagSeguro escondida (componente mantido comentado)
- Ajuste 5: Link de agendamento online movido para Perfil da empresa
- Ajuste 6: /settings/perfil — editar nome, ver email/papel
- Ajuste 7: PaymentOnCompleteDialog — popup ao concluir agendamento
- Ajuste 8: Dashboard financeiro com KPIs + gráfico de área (Recharts)

### Pendente — próximo sprint
- **Ajuste 9 (subconta Asaas):** 5 campos obrigatórios ausentes no payload
  (mobilePhone, incomeValue, address, addressNumber, province, postalCode)
  Requer: migration backend + CompanyUpdate schema + AsaasProvider +
  formulário expandido em settings/integracoes aba Asaas
  Referência: docs/plano-ajustes-pos-sprint.md seção Ajuste 9

### O que foi implementado

**Bloco 1 — Email (CommunicationService)**
- Canal EMAIL em `dispatch()` com suporte a Mailtrap HTTP API e smtplib
- `forgot_password()` e `send_invite()` corrigidos para passar `recipient_email`
- Templates EMAIL criados: `auth.password_reset_requested` e `user.invitation_sent`
- Variáveis: MAILTRAP_API_TOKEN, MAILTRAP_SANDBOX_INBOX_ID, SMTP_*

**Bloco 2 — Asaas (correções críticas)**
- `create_payment()` agora chama `provider.create_charge()` → `external_charge_id` preenchido
- `confirm()` extrai value/fee do payload Asaas aninhado (`payment.value` e `payment.fee`)
- Lazy registration: `ensure_customer()` cria customer Asaas na primeira cobrança
- Validação de CPF/CNPJ: `validate_and_clean_cpf_cnpj()` antes de enviar ao Asaas

**Bloco 3 — PagSeguro (novo provider)**
- `PagSeguroProvider` implementado para terminais físicos (Point/SmartPOS)
- OAuth2 client_credentials para autenticação
- `create_charge()`, `handle_webhook()`, `get_status()` implementados (stubs documentados)
- Migration `psg1a2b3c4d5`: enum PAGSEGURO adicionado
- Factory atualizado: PAGSEGURO credential → PagSeguroProvider

**Bloco 4 — CASH / Pagamento Manual**
- `POST /payments/{id}/confirm-manual` implementado (OWNER/ADMIN)
- `confirm_manual()` retorna `tuple[Payment, Optional[fee_warning]]`
- `_calc_manual_fee()` calcula MDR via TenantFeeRoutingPolicy
- Idempotência via `event_id = f"manual-{payment.payment_id}"`

**Bloco 5 — Evolution API (hardening)**
- Validação de `EVOLUTION_WEBHOOK_SECRET` no webhook
- Log de diagnóstico adicionado (a remover após confirmação em produção)

**Taxes MDR (adicionado no sprint)**
- `GET /financial/fee-policies` e `PATCH /financial/fee-policies/{fee_source}`
- Migration `f2g3h4i5j6k7`: colunas fee_percentage, fee_flat, is_active
- Migration `g3h4i5j6k7l8`: fee_percentage nullable + seed MAQUININHA_PIX (**pendente de commit**)

### Decisões arquiteturais

- PagSeguro Point não tem REST API pública; stubs documentados até confirmação do time PagBank
- `fee_percentage=NULL` = não configurado; `fee_percentage=0` = zero configurado sem aviso
- Mailtrap HTTP API como substituto SMTP para Railway (SMTP bloqueado)
- `asyncio.create_task` removido do lifespan — Celery Beat exclusivo para workers

---

## Sessão de correções em produção — 2026-06-07

**Origem:** bugs encontrados após deploy do Sprint Frontend + Ajustes.
**Tipo:** hotfixes — sem novos sprints formais.

### Bugs corrigidos (8 total)

| # | Bug | Causa raiz | Commit |
|---|-----|-----------|--------|
| 1 | GET /financial/fee-policies → 500 | `fee_percentage: Decimal` não-opcional no schema de resposta; banco tem NULL | 7a4eb92 |
| 2 | Taxas exibem só PIX | `_DEFAULT_FEE_SOURCES` usava nomes antigos (ASAAS_PIX, ASAAS_CARD) incompatíveis com frontend | 85be662 |
| 3 | POST /payments → 422 "Field required" | `provider` e `target_account_id` obrigatórios no schema; frontend não enviava | 7cc476c |
| 4 | Notificação pós-pagamento → 500 | `audience: "customer"` (lowercase) inválido para enum PostgreSQL communicationaudience (espera "CLIENT") | bc4cf9c |
| 5 | Movimentações exibiam todas como OUTFLOW | Frontend usava `m.movement_type` (inexistente) → undefined → tudo filtrado como OUTFLOW | 882416f |
| 6 | Registro de pagamento crashava | ConfirmManualResponse é flat no backend; frontend acessava `confirmResult.payment.X` → TypeError | 56c45d1 |
| 7 | Lista de pagamentos vazia | `Promise.all([/payments, /customers])` falhava inteiramente se /customers falhasse | 56c45d1 |
| 8 | Dashboard sem gráficos | Mesmo bug do #5 no financeiro/page.tsx + `s + m.amount` (string + number = NaN) | 85376ad |

### Lições registradas
- Schemas Pydantic de resposta devem ter campos nullable como `Optional`
  quando a coluna do banco é nullable. ResponseValidationError é silencioso.
- Enums PostgreSQL requerem uppercase exato — normalizar no serviço antes de queries.
- `Promise.all` em fetches independentes deve ser substituído por fetches
  paralelos com tratamento de falha individual.
- Campos de response do backend devem ser verificados contra o schema real
  (não assumir estrutura nested quando a API retorna flat).
- Ao renomear fee_sources ou outros enums, verificar consistência entre:
  migration seed, _DEFAULT_FEE_SOURCES, _calc_manual_fee e frontend.

---

## Sprint 10 — Operations FSM + Agenda granular — [registrar retroativamente]

HEAD: `d1e2f3g4h5i6` (align_orm_schema_gaps)
Total testes: 142/142
[detalhes conforme CLAUDE.md seção "Operations FSM + Agenda granular"]

---

# Sprint Log — Fase 1
**Projeto:** Paladino · Fase 1 — Fundação técnica  
**Auditor:** Claude.ai (projeto Paladino — pré-planejamento)  
**Regra de escalonamento:**
- Ressalva de **segurança, dados em produção ou contrato de API** → bloqueia próximo sprint automaticamente
- Ressalva **cosmética ou de documentação** → dívida registrada, não bloqueia

---

## Tabela de estado

| Sprint | Nome | Status | Data | Próximo bloqueado? |
|--------|------|--------|------|--------------------|
| 1 | Segurança e infraestrutura crítica | ✅ Aprovado | 2026-05-26 | não |
| 2 | RBAC: papéis, convite e auditoria | ✅ Aprovado | 2026-05-26 | não |
| 3 | TenantConfig, módulos e branding | ✅ Aprovado | 2026-05-26 | não |
| 4 | Sistema de eventos e workers | ✅ COMPLETO | 2026-06-09 | não |
| 5 | Comunicação e credenciais | ✅ Aprovado | 2026-05-26 | não |
| Fechamento | Testes, password reset, correções | ✅ Aprovado | 2026-05-28 | não |
| RLS | Row Level Security | ✅ Aprovado | 2026-05-28 | não |
| Polish Visual | Design system Paladino | ✅ Aprovado | 2026-05-28 | não |
| Design | Transposição visual Navalha → Paladino | ✅ Aprovado | 2026-05-29 | não |
| A–F | Espelhamento design barberflow-system | ✅ Aprovado | 2026-05-29 | não |
| Correção Frontend | Pós-testes de produção | ✅ Aprovado | 2026-05-30 | não |

---

## Sprint 1 — Segurança e infraestrutura crítica

**Status:** ✅ Aprovado  
**Data de conclusão:** 2026-05-26  
**Veredicto do auditor:** Aprovado com ressalvas resolvidas  

**Sinal do executor recebido:** sim  
**Checklist do protocolo rodado:** sim  

**Desvios relatados pelo executor:**
- supabase==2.15.1 requereu downgrade de websockets 16.0→14.2 (sem conflito — pip check ok)
- gallery_urls tipo array corrigido durante a sessão

**Itens reprovados na auditoria:**
- nenhum

**Ressalvas aprovadas:**
- supabase==2.15.1: validado no PyPI ✅
- btree_gist v1.7: ativa ✅
- bucket uploads: criado ✅
- migrate_uploads_to_supabase.py --dry-run: 0 arquivos ✅
- rollback_uploads_to_volume.py: testado ✅

**Dívida técnica gerada:**
- nenhuma

**Dívida que bloqueia Sprint 2:** não  

**CLAUDE.md atualizado:** sim  
**Commit:** b70549f

---

## Sprint 2 — RBAC: papéis, convite e auditoria

**Status:** ✅ Aprovado  
**Data de conclusão:** 2026-05-26  
**Veredicto do auditor:** Aprovado com ressalvas resolvidas  

**Sinal do executor recebido:** sim  
**Checklist do protocolo rodado:** sim  

**Desvios relatados pelo executor:**
- Email no invite deferido para Sprint 5 (CommunicationService)
- Path `/users/invitations` em vez de `/invitations` independente
- `audit/logs/export` para ADMIN com permission_overrides deferido para Sprint 3
- Testes service-level em SQLite (triggers validar em produção)

**Itens reprovados na auditoria:**
- nenhum

**Ressalvas aprovadas:**
- SELECT DISTINCT role FROM users: apenas ADMIN e PROFESSIONAL ✅
- CLAUDE.md atualizado com Enum userrole, require_role/require_action, audit logs ✅

**Dívida técnica gerada:**
- `POST /users` legado deprecado — removido no Sprint 3 ✅
- `audit/logs/export` acesso ADMIN com permission_overrides — Sprint 3
- Path `/users/invitations` documentado como convenção

**Dívida que bloqueia Sprint 3:** não  

**CLAUDE.md atualizado:** sim  
**Commit:** 364e998

---

## Sprint 3 — TenantConfig, módulos e branding

**Status:** ✅ Aprovado  
**Data de conclusão:** 2026-05-26  
**Veredicto do auditor:** Aprovado com ressalvas resolvidas  

**Sinal do executor recebido:** sim  
**Checklist do protocolo rodado:** sim  

**Desvios relatados pelo executor:**
- `create_company` criada do zero (plano assumia existência — resultado idêntico)
- `GET /tenant/branding` com `company_id` como query param (correto para endpoint público)
- Apenas 5 de 15 routers tinham `require_admin` ativamente (10 já usavam `get_current_user`)
- `POST /users` removido por grep sem logs de produção (risco baixo — sistema single-tenant)
- Testes do Sprint 3 não escritos (PR separado)

**Itens reprovados na auditoria:**
- nenhum

**Ressalvas aprovadas:**
- nenhuma (sem ressalvas que bloqueiam Sprint 4)

**Dívida técnica gerada:**
- tests/test_sprint3_config.py não escritos — criados no Sprint de Fechamento ✅
- `audit/logs/export` acesso ADMIN com permission_overrides — pendente

**Dívida que bloqueia Sprint 4:** não  

**CLAUDE.md atualizado:** sim  
**Commit:** d9bc4c3

---

## Sprint 4 — Sistema de eventos e workers

**Status:** ✅ COMPLETO  
**Data de conclusão:** 2026-06-09  
**Veredicto do auditor:** Aprovado com ressalvas resolvidas — flip asyncio→Celery validado em produção  

**Sinal do executor recebido:** sim  
**Checklist do protocolo rodado:** sim  

**Desvios relatados pelo executor:**
- REDIS_URL adicionado ao config.py (gap óbvio — adição correta)
- Import circular resolvido via celery_beat_entrypoint.py (dois entrypoints distintos)
- appointment.reminder_due implementado como stub (correto — Sprint 5 substitui)

**Itens reprovados na auditoria:**
- nenhum

**Ressalvas aprovadas:**
- migration processed_idempotency_keys: aplicada ✅

**Dívida técnica gerada:**
- flip definitivo (remover asyncio.create_task do lifespan) — ✅ resolvido: asyncio.create_task removido do lifespan (commit anterior ao fechamento formal)
- commit CLAUDE.md final pós-flip — ✅ resolvido: Celery Beat exclusivo documentado em CLAUDE.md

**Nota de fechamento (2026-06-09):** Flip asyncio→Celery validado em produção. asyncio.create_task
removido do lifespan (commit anterior). Celery Beat operacional. Sprint formalmente fechado.

**Dívida que bloqueia Sprint 5:** não  

**CLAUDE.md atualizado:** sim  
**Commit:** ab7f404 (implementação) · fechamento formal: docs: fechar Sprint 4

---

## Sprint 5 — Comunicação e credenciais

**Status:** ✅ Aprovado  
**Data de conclusão:** 2026-05-26  
**Veredicto do auditor:** Aprovado com ressalvas resolvidas  

**Sinal do executor recebido:** sim  
**Checklist do protocolo rodado:** sim  

**Desvios relatados pelo executor:**
- test_connection com reason fixo "API connectivity test" (REASON_REQUIRED satisfeito)
- Parâmetro conn removido de notifications.py (cleanup correto)
- Quiet hours: transacionais bypass → SENT (alinhado com plano-fase1-v3.md)
- _validate_encryption_key leniente em dev/test (correto para DX local)
- Testes não escritos (3º sprint — criados no Sprint de Fechamento ✅)
- Chamadas diretas evolution_client mantidas em coexistência com feature flag

**Itens reprovados na auditoria:**
- nenhum

**Ressalvas aprovadas:**
- appointment.no_show em communication_worker.py: confirmado ✅ (linhas 8, 135, 136)
- CREDENTIAL_ENCRYPTION_KEY gerada e configurada no Railway ✅
- migrations Sprint 5 aplicadas: HEAD e2f6h3i4j5k6 ✅

**Dívida técnica gerada:**
- chamadas diretas evolution_client — remover após 1 semana de feature flag ativa em produção
- template auth.password_reset_requested ausente nos seeds — corrigido no Sprint de Fechamento ✅

**Dívida que bloqueia Fase 2:** não  

**CLAUDE.md atualizado:** sim  
**Commit:** 9eac1cc

---

## Sprint de Fechamento — Testes, password reset, correções

**Status:** ✅ Aprovado  
**Data de conclusão:** 2026-05-28  
**Veredicto do auditor:** Aprovado com ressalvas resolvidas  

**Sinal do executor recebido:** sim  
**Checklist do protocolo rodado:** sim  

**Desvios relatados pelo executor:**
- slowapi ausente no venv local (não afeta produção — testes usam mocks)
- Pydantic Config class deprecation (migrar para model_config no Sprint de RLS)
- Template auth.password_reset_requested ausente nos seeds (🔴 corrigido nesta sessão)

**Itens reprovados na auditoria:**
- template auth.password_reset_requested ausente nos seeds — corrigido ✅
  - create_company: agora 8 templates ✅
  - data migration g1h2i3j4k5l6 aplicada ✅

**Ressalvas aprovadas:**
- test_sprint3_config.py: 13 pass + 1 skip ✅
- test_sprint5_communication.py: 18 pass ✅
- migration g1h2i3j4k5l6 aplicada ✅

**Dívida técnica gerada:**
- Pydantic ConfigDict migration — Sprint de RLS
- flip asyncio→Celery — aguarda validação em produção
- remoção evolution_client — aguarda 1 semana de flag ativa em produção

**Dívida que bloqueia Sprint de RLS:** não  

**CLAUDE.md atualizado:** sim  
**Commit:** db0343f

---

## Sprint de RLS — Row Level Security

**Status:** ✅ Aprovado  
**Data de conclusão:** 2026-05-28  
**Veredicto do auditor:** Aprovado com ressalvas resolvidas  

**Sinal do executor recebido:** sim  
**Checklist do protocolo rodado:** sim  

**Desvios relatados pelo executor:**
- appointment_status_log com RLS ativo mas sem política (🔴 corrigido nesta sessão)
  - política tenant_isolation criada e versionada em migration 22bfd8bf16b3 ✅
- working_hours e schedule_blocks sem cobertura RLS (dívida — PR antes do 2º tenant)

**Itens reprovados na auditoria:**
- appointment_status_log sem política — corrigido ✅

**Ressalvas aprovadas:**
- company_id_ctx: Opção A confirmada (middleware seta antes das deps) ✅
- RLS ativo em 26 tabelas com tenant_isolation ✅
- migrations h1i2j3k4l5m6 e 22bfd8bf16b3 aplicadas ✅

**Dívida técnica gerada:**
- working_hours, schedule_blocks, appointment_services, professional_services sem política
  — resolvido no Sprint de Polish Visual ✅ (migration 3f03c84)
- smoke test HTTP pendente de deploy

**Dívida que bloqueia Sprint de Polish Visual:** não  

**CLAUDE.md atualizado:** sim  
**Commit:** 7316eff

---

## Sprint de Polish Visual — Design system Paladino

**Status:** ✅ Aprovado  
**Data de conclusão:** 2026-05-28  
**Veredicto do auditor:** Aprovado  

**Sinal do executor recebido:** sim  
**Checklist do protocolo rodado:** sim  

**Desvios relatados pelo executor:**
- CSS de referência era do barberflow-system, não do projeto — executor identificou e usou tokens semânticos shadcn (correto)
- font-display workaround com arbitrary class até globals.css ser atualizado — resolvido nesta sessão
- .book-page migrado para seguir paleta do sistema por padrão (tenant-customizável)
- RLS tabelas restantes cobertos: working_hours, schedule_blocks, appointment_services, professional_services

**Itens reprovados na auditoria:**
- nenhum

**Ressalvas aprovadas:**
- globals.css: paleta Paladino aplicada (petrol blue + antique brass) ✅
- .book-page: tokens do sistema por padrão ✅
- RLS dívida zerada: todas as tabelas cobertas ✅

**Dívida técnica gerada:**
- smoke test HTTP pendente de deploy (push ainda não realizado)
- flip asyncio→Celery (Sprint 4) — aguarda validação em produção

**Dívida que bloqueia Sprint 6:** não  

**CLAUDE.md atualizado:** sim  
**Commits:**
- 3f03c84 — RLS tabelas restantes
- 15ad34d — .gitignore __pycache__
- 0f1cd70 — design system Paladino
- 445bb29 — painel/CLAUDE.md
- 04a0b53 — agendamento_engine/CLAUDE.md

---

## Como usar este arquivo

**Início de sessão do auditor:**  
Leia a tabela de estado → localize o sprint em andamento → leia a seção correspondente.  
A primeira mensagem pode ser: *"retomando — sprint [N] pronto para auditoria, outputs abaixo."*

**Ao receber o sinal do executor:**  
1. Cole o bloco "Sinal de conclusão" na sessão do auditor  
2. Rode o checklist de `protocolo-claudemd.md § Sprint [N]`  
3. Preencha os campos desta seção  
4. Emita veredicto e, se aprovado, gere o diff do CLAUDE.md + commit message  
5. Atualize a tabela de estado no topo

**Regra de escalonamento — decisão agora, não caso a caso:**  
Qualquer ressalva classificada abaixo como 🔴 bloqueia o próximo sprint automaticamente.  
Ressalvas 🟡 viram dívida registrada aqui, sprint continua.

| Categoria | Classificação |
|-----------|--------------|
| Segurança (auth, rate limit, headers, bcrypt rounds) | 🔴 bloqueia |
| Dados em produção (migration com risco, rollback não testado) | 🔴 bloqueia |
| Contrato de API (endpoint removido antes do prazo, breaking change) | 🔴 bloqueia |
| `audit_logs` sem append-only | 🔴 bloqueia |
| `CLAUDE.md` não atualizado | 🔴 bloqueia |
| Commit message errada | 🟡 dívida |
| Arquivo criado com nome diferente do planejado (sem impacto funcional) | 🟡 dívida |
| Test coverage abaixo do esperado (sem falha de DoD) | 🟡 dívida |
| Documentação interna incompleta | 🟡 dívida |

---

## Sprint de Design — Transposição visual Navalha → Paladino

**Status:** ✅ Aprovado  
**Data de conclusão:** 2026-05-29  
**Veredicto do auditor:** Aprovado com ressalvas resolvidas  

**Sinal do executor recebido:** sim  
**Checklist do protocolo rodado:** sim  

**Desvios relatados pelo executor:**
- `paladino-wordmark.png` ausente inicialmente — adicionado na mesma sessão ✅
- Dark/light toggle decorativo sem ThemeProvider — criado na mesma sessão ✅
- Grupo "Unidade" não portado (correto — depende de company context no JWT)
- Ocupação e NPS como `—` (correto — módulos não existem ainda)

**Itens reprovados na auditoria:**
- ThemeProvider ausente (🔴) — corrigido na mesma sessão ✅

**Ressalvas aprovadas:**
- lib/theme.tsx: ThemeProvider + useTheme (localStorage, .light class) ✅
- paladino-wordmark.png em painel/public/ ✅
- Sidebar: toggle Sun/Moon funcional ✅

**Dívida técnica gerada:**
- grupo Unidade no sidebar — depende de company context no JWT

**Dívida que bloqueia Sprint 6:** não  

**painel/CLAUDE.md atualizado:** sim  
**Commits:**
- 84eff71 — feat: Sprint de Design
- 290dfdf — docs: painel/CLAUDE.md pós-Sprint de Design
- ca5a53d — docs: ThemeProvider e wordmark concluídos

---

## Sprints A–F — Espelhamento design barberflow-system

**Status:** ✅ Aprovado  
**Data de conclusão:** 2026-05-29  
**Veredicto do auditor:** Aprovado  

**Sinal do executor recebido:** sim  
**Checklist do protocolo rodado:** sim  

**Desvios relatados pelo executor:**
- settings/profile: ícone 👤 trocado por <Globe> — verificar semântica
- Vitrine: brand icons (Instagram/Facebook/TikTok) sem substituto semântico
- Vitrine: business_hours como string livre — highlight "Hoje" não implementado
- Vitrine: tab Barbeiros requer service_id — verificar estado atual

**Itens reprovados na auditoria:**
- nenhum

**Ressalvas aprovadas:**
- nenhuma

**Dívida técnica gerada:**
- brand icons Vitrine — sem substituto semântico Lucide
- business_hours highlight "Hoje" — não implementado
- tab Barbeiros requer service_id — verificar estado atual
- G13 (BookingFlow): aguarda sprint de backend (remoção AWAITING_SHIFT)

**Dívida que bloqueia Sprint de Backend BookingFlow:** não  

**painel/CLAUDE.md atualizado:** sim  
**Commits:**
- 61de835 — feat: Sprints A–F
- c85128d — docs: painel/CLAUDE.md pós-Sprints A–F

---

## Sprint de Correção de Frontend — Pós-testes de produção

**Status:** ✅ Aprovado  
**Data de conclusão:** 2026-05-30  
**Veredicto do auditor:** Aprovado com pendências backend documentadas  

**Sinal do executor recebido:** sim  
**Checklist do protocolo rodado:** sim  

**Causa raiz identificada:**
- `NEXT_PUBLIC_API_URL=localhost` em produção — causa de todos os "Failed to fetch"
- Corrigido via Vercel Environment Variables: `NEXT_PUBLIC_API_URL=https://labs-production-86f9.up.railway.app`
- Railway: `ALLOWED_ORIGINS=https://app.meupaladino.com.br,https://api.meupaladino.com.br`
- Railway: `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` adicionados (upload estava quebrando)

**Itens corrigidos:**
- company_profile router: User object passado em vez de company_id (9fed210)
- professionals/schemas: specialty adicionado (bbb5632)
- products/schemas: stock adicionado (bbb5632)
- schedule/service: upsert_working_hour suporta múltiplos períodos/dia (bbb5632)
- booking FSM: SELECT_DATE e NAVIGATE_DATES liberados em AWAITING_TIME (ddb52c9)
- Login: link "Esqueci minha senha" + páginas forgot/reset-password (483fb08)
- Sidebar: item "Usuários" para OWNER/ADMIN (483fb08)
- Agenda: calendário semanal + modal de detalhe (483fb08)
- Agendamento manual: date picker + grade de slots (483fb08)
- Vitrine: profissionais na aba Barbeiros (483fb08)
- useSearchParams sem Suspense em 4 páginas (8af2769 + e4983ee)
- settings/profile: normalizeProfile() corrige nulls da API (124a3c9)
- payments/page.tsx: api() → api.get() (eeb494d)
- refundReason tipo incompatível com Select (e804949)

**Dívida técnica remanescente:**
- Múltiplos períodos por dia: frontend ainda envia período único (UI pendente)
- specialty no form de profissional: campo existe no backend, falta no form
- stock no form de produto: campo existe no backend, falta no form

**Dívida que bloqueia próximo sprint:** não  

**CLAUDE.md atualizado:** sim  
**Commits:**
- 483fb08 — feat: correções frontend
- 9fed210 — fix: company_profile router
- bbb5632 — fix: schemas e working_hours
- 6bf4afe — fix: frontend tipos
- ddb52c9 — fix: booking FSM
- e804949 — fix: refundReason
- eeb494d — fix: api.get()
- 8af2769 — fix: Suspense login
- e4983ee — fix: Suspense 3 páginas
- 124a3c9 — fix: normalizeProfile
- de3dfb8 — docs: CLAUDE.md

---

## Sprint S0.2 — Vazamentos cross-tenant do módulo `users` — 2026-07-19

**Branch:** `fix/s02-cross-tenant-users` · **Suíte:** 1294 passed / 12 failed (pré-existentes, ver item 1) / 6 skipped / 1 xfailed
**Escopo:** filtros de posse em `assign_role` e `deactivate_user` (auditoria A-ISO) + 15 testes.

### Itens para a fila

1. ⬆️ **PROMOVIDO** — isolar o monkey-patch de `test_sprint2_rbac.py`. Não é
   housekeeping de testes: são 12 testes de RBAC que não rodam na suíte completa,
   incluindo os dois endpoints deste sprint. É cobertura de segurança desligada e
   normalizada como "falha conhecida". Candidato ao Bloco 0, junto do S0.3.
2. **Trilha de auditoria do módulo `users`** (agrupar): `deactivate_user` sem
   `record_sensitive_action`; revisar a semântica de `company_id` registrada nas
   ações sensíveis do módulo.
3. **`transfer_ownership` — ternário sem parênteses** (`service.py:~297` após o
   diff). Ocorrência única, inalcançável hoje, armada se o gate de entrada for
   flexibilizado.
4. **Wiring de `effective_company_id` no módulo `users`** — se a plataforma
   precisar administrar usuários de tenants via impersonação ELEVATED. Hoje
   inexistente por desenho.
5. **Inconsistência de estilo** (menor, sem efeito): `cancel_invitation` compara
   `company_id` com o valor cru; `transfer_ownership` e os fixes do S0.2 usam
   `str(...)`. Ambos funcionam (o SQLAlchemy coage). Só padronizar se alguém
   tocar o arquivo.

**CLAUDE.md atualizado:** sim (seção "Isolamento multi-tenant no módulo `users` (S0.2)")
