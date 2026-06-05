# Brief — Sprint Frontend: Adaptação ao Estado Atual do Backend
**Versão:** 1.1 · **Data:** 2026-06-04 · **Encoding:** UTF-8

> **Escopo deste sprint:** Adaptar o frontend (`painel/`) ao estado atual do backend
> pós-Fase 2 + Sprint de Integrações. Corrigir problemas de UX identificados pelo
> produto. Reorganizar a arquitetura de informação. Não implementar funcionalidades
> da Fase 3 backend (Sprints 11–18).

---

## Pré-requisito backend (executar ANTES do sprint frontend)

### User.name — campo obrigatório para o frontend

O campo `name` não existe no modelo `User` nem no banco. O frontend precisa
dele desde a primeira tela (header, convite, ativação). Implementar como
task separada antes de iniciar o sprint frontend:

**Migration:**
```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(100);
```

**Alterações no backend (`agendamento_engine/`):**
- Modelo ORM `User`: adicionar `name = Column(String(100), nullable=True)`
- `GET /auth/me` → incluir `name` no response
- `POST /users/invite` → aceitar `name` como campo opcional
- `GET /users` → incluir `name` na listagem
- Tela de ativação de conta: endpoint de ativação deve aceitar `name`
  para que o usuário defina seu nome ao criar a senha

**Comportamento quando `name` é nulo:**
- Exibir email truncado como fallback (comportamento atual preservado)
- Não bloquear login nem convite se `name` não fornecido

O executor do pré-requisito deve commitar e fazer push antes de
qualquer trabalho no `painel/`.

---

## Decisão de fase

O sprint tem duas partes em sequência:
1. **Pré-requisito backend:** `User.name` (pequena task, ~1h)
2. **Sprint frontend:** tudo abaixo — exclusivamente em `painel/`

Nenhuma outra alteração no backend (`agendamento_engine/`) durante o
sprint frontend, salvo se o planner identificar gap bloqueante adicional.

---

## Contexto do backend atual

O backend passou por Fase 1, Fase 2 (Financial Core) e Sprint de Integrações.
O frontend foi construído paralelamente e não reflete várias funcionalidades
já disponíveis. Endpoints ativos que o frontend ainda não consome:

```
POST /payments                     → criar pagamento (CASH/PIX/MAQUININHA)
POST /payments/{id}/confirm-manual → confirmar pagamento manual com taxa automática
GET  /payments                     → lista de pagamentos
GET  /payments/{id}                → detalhe do pagamento
GET  /financial/movements          → extrato de movimentações
GET  /financial/entries            → lançamentos contábeis
GET  /financial/accounts           → contas financeiras
GET  /financial/fee-policies       → políticas de taxa MDR
PATCH /financial/fee-policies/{fee_source} → configurar taxa por método
GET  /whatsapp/qr                  → QR code de conexão WhatsApp
POST /whatsapp/webhook             → (entrada — não frontend)
GET  /payments/terminals           → terminais PagSeguro (stub)
POST /integrations/credentials     → configurar credenciais de integração
GET  /communication/settings       → configurações de comunicação
PATCH /communication/settings      → atualizar configurações de comunicação
```

---

## Problemas de UX identificados pelo produto

### 1. Página inicial — remover OVERVIEW
A seção "OVERVIEW" na primeira tela deve ser removida. Manter apenas
a exibição da data, que já existe logo em seguida.

### 2. Cadastro de usuário — campo nome
Exibir uma parte do email como identificador do usuário é inadequado.
Adicionar campo `name` no cadastro de usuário (convite e criação).
Exibir o nome do usuário logado no header/sidebar em vez do email.
O backend já tem `User.name` — verificar se o campo existe no modelo
ou se precisa ser adicionado (o planner verifica).

### 3. Logo Paladino — tamanho
A logo no canto superior esquerdo está muito pequena, praticamente
invisível. Ajustar tamanho e visibilidade.

### 4. Sidebar — nomenclatura
- Label `NAVEGAÇÃO` → `MENU`
- Item `Início` → `Painel`

### 5. Sidebar — reorganização de opções
O sidebar está crescendo demais. Reestruturar com a seguinte lógica:

**Remover do sidebar:**
- `Agendamentos` (acesso migra para o atalho 'Ver agenda' na página Painel)

**Migrar para dentro de Configurações:**
- `Usuários` → `Configurações > Usuários`
- `Integrações` → `Configurações > Integrações`

**Resultado do sidebar após reorganização:**
```
MENU
├── Painel          (era Início)
├── Clientes
├── Serviços
├── Profissionais
├── Financeiro      (nova entrada — ver abaixo)
└── Configurações   (expandido — ver abaixo)
```

### 6. Página Painel — lista de próximos agendamentos
A lista de agendamentos deve aparecer diretamente na página Painel,
na seção "Próximos" ou similar. O atalho "Ver agenda" permanece,
mas ao clicar, abre a tela de calendário (não a lista).

### 7. Tela de Agenda — calendário por padrão
Ao acessar a agenda (via atalho "Ver agenda" ou qualquer link direto):
- Exibir calendário por padrão
- Oferecer opção de alternar para visualização em lista
- Layout atual (lista por padrão com opção de calendário) inverte

---

## Arquitetura de informação — estado proposto

### Painel (página inicial)
```
Painel
├── Saudação + Data (sem OVERVIEW)
├── Cards de resumo (agendamentos hoje, receita do dia, etc.)
├── Próximos agendamentos (lista compacta — 5 a 10 itens)
│   └── [atalho: Ver agenda completa → abre calendário]
└── Ações rápidas (Novo agendamento, Novo cliente, Registrar pagamento)
```

### Agenda (acessível via atalho "Ver agenda")
```
Agenda
├── Calendário (padrão)
│   └── [alternar: Exibição em lista]
├── Filtros: profissional, status, data
└── Ações: novo agendamento, confirmar, cancelar
```

### Financeiro (nova entrada no sidebar)
```
Financeiro
├── Resumo (saldo das contas, receita do período)
├── Movimentações (GET /financial/movements)
│   └── Filtros: conta, tipo, período
├── Pagamentos
│   ├── Lista (GET /payments)
│   ├── Registrar pagamento (POST /payments → confirm-manual)
│   │   └── Seletor de método: Dinheiro | PIX | Crédito | Débito
│   │   └── Aviso quando taxa não configurada (fee_warning do backend)
│   └── Detalhe do pagamento
└── [atalho para Configurações > Taxas quando fee_warning presente]
```

### Configurações (expandido)
```
Configurações
├── Empresa
│   ├── Dados gerais (nome, endereço, horários)
│   ├── Horários de funcionamento (business_hours_structured)
│   └── Onboarding Asaas (CPF, data de nascimento do responsável)
├── Usuários               ← migrado do sidebar
│   ├── Lista de usuários
│   ├── Convidar usuário
│   └── Editar perfil / roles
├── Integrações            ← migrado do sidebar
│   ├── WhatsApp (Evolution API — QR code, status de conexão)
│   ├── Asaas (status da subconta, configurar CPF/birthDate)
│   └── PagSeguro (configurar credenciais — aguarda sandbox)
├── Comunicação
│   ├── Email (habilitar/desabilitar — PATCH /communication/settings)
│   └── WhatsApp (habilitar/desabilitar)
└── Financeiro > Taxas
    ├── Lista das 8 políticas de taxa MDR
    │   (Dinheiro 0%, PIX ?, Crédito ?, Débito ?, PIX Maquininha ?, ...)
    └── Editar taxa por método (PATCH /financial/fee-policies/{fee_source})
        └── Aviso: Dinheiro sempre 0%, não editável
```

---

## Requisitos por tela

### REQ-01 — Painel (Home)

**Remover:**
- Bloco OVERVIEW

**Manter:**
- Exibição de data

**Adicionar:**
- Seção "Próximos agendamentos": lista compacta com nome do cliente,
  serviço, profissional, horário — ordenada por hora, máximo 8 itens
- Atalho "Ver agenda completa" → redireciona para `/agenda` (calendário)
- Card "Registrar pagamento" nas ações rápidas → abre modal ou redireciona
  para `/financeiro/pagamentos/novo`

---

### REQ-02 — Agenda

**Alterar:**
- Padrão de exibição: calendário (não lista)
- Toggle visível: "Calendário | Lista"

**Manter:**
- Toda a funcionalidade atual de calendário
- Filtros existentes

---

### REQ-03 — Sidebar

**Alterar:**
- Label `NAVEGAÇÃO` → `MENU`
- Item `Início` → `Painel`

**Remover:**
- Entrada `Agendamentos`
- Entrada `Usuários` (migra para Configurações)
- Entrada `Integrações` (migra para Configurações)

**Adicionar:**
- Entrada `Financeiro` (nova)

---

### REQ-04 — Header / perfil do usuário

**Alterar:**
- Exibir `User.name` no lugar de parte do email
- Se `User.name` estiver vazio: exibir email truncado (fallback)

**Nota:** `User.name` será implementado no pré-requisito backend antes
deste sprint. O planner não precisa investigar — o campo estará disponível
em `GET /auth/me`, `POST /users/invite` e na tela de ativação de conta.

---

### REQ-05 — Logo Paladino

**Alterar:**
- Aumentar tamanho e visibilidade da logo no canto superior esquerdo
- Manter proporção correta sem distorção

---

### REQ-14 — Formulário do profissional — remover CPF da UI

**Contexto:**
O formulário de cadastro/edição de profissional exibe um campo CPF/CNPJ.
O campo existe no modelo `Professional.cpf_cnpj` e continuará no banco
(necessário na Fase 3 para comissões e dados fiscais). Para Stage 0 não
tem utilidade visível e gera confusão com o CPF do responsável da empresa
(que o Asaas exige para criar a subconta — campo diferente).

**Alterar:**
- Remover o campo CPF/CNPJ do formulário de cadastro e edição de profissional

**NÃO fazer:**
- Não criar migration DROP COLUMN — campo permanece no banco
- Não alterar o modelo `Professional` no backend
- O campo voltará ao formulário na Fase 3 como seção "Dados fiscais"

**CPF do responsável da empresa** (diferente do CPF do profissional):
- Permanece em `Configurações > Integrações > Asaas` conforme REQ-10

---

### REQ-06 — Novo: tela de registro de pagamento

**Rota:** `/financeiro/pagamentos/novo` ou modal

**Fluxo:**
1. Selecionar cliente (autocomplete → `GET /customers`)
2. Selecionar agendamento (opcional — `GET /appointments?customer_id=`)
3. Informar valor
4. Selecionar método:
   - 💵 Dinheiro
   - ⬡ PIX (maquininha)
   - 💳 Crédito
   - 💳 Débito
5. Confirmar → `POST /payments` + `POST /payments/{id}/confirm-manual`
6. Se `fee_warning` no response:
   - Exibir aviso: "Nenhuma taxa configurada para [método].
     [Configurar agora →] ou [Continuar sem taxa]"
   - Link leva para `Configurações > Taxas`

**Estados:**
- Sucesso: exibir resumo (pagamento confirmado, valor líquido, taxa aplicada)
- Erro: exibir mensagem do backend

---

### REQ-07 — Novo: tela de movimentações financeiras

**Rota:** `/financeiro/movimentacoes`

**Conteúdo:**
- Lista paginada de `GET /financial/movements`
- Filtros: conta, tipo (INFLOW/OUTFLOW), período
- Para cada movimento: data, tipo, valor, conta, origem (source_type + source_id)
- Saldo calculado por conta

---

### REQ-08 — Novo: tela de pagamentos (lista)

**Rota:** `/financeiro/pagamentos`

**Conteúdo:**
- Lista paginada de `GET /payments`
- Filtros: status, método, período, cliente
- Para cada pagamento: data, cliente, valor, método, status
- Ação: confirmar manual (se PENDING + provider=manual)
- Ação: ver detalhe

---

### REQ-09 — Configurações > Taxas

**Rota:** `/configuracoes/taxas`

**Conteúdo:**
- Lista dos 8 fee_sources via `GET /financial/fee-policies`
- Para cada taxa: nome legível, valor atual em %, editar inline
  - Dinheiro: sempre 0%, não editável (exibir como somente leitura)
  - Demais: input numérico (0.00 a 99.99%)
- Salvar via `PATCH /financial/fee-policies/{fee_source}`
- Aviso informativo quando taxa = 0% para métodos que tipicamente têm taxa

**Nomes legíveis por fee_source:**
```
CASH              → Dinheiro (sem taxa)
PIX               → PIX online (Asaas)
MAQUININHA_PIX    → PIX na maquininha
MAQUININHA_CREDIT → Cartão de crédito
MAQUININHA_DEBIT  → Cartão de débito
CARD_CREDIT       → Crédito online
CARD_DEBIT        → Débito online
BOLETO            → Boleto
```

---

### REQ-10 — Configurações > Integrações

**Rota:** `/configuracoes/integracoes`

**Seções:**

**WhatsApp (Evolution API):**
- Status de conexão (GET /whatsapp/connection)
- QR code para conectar (GET /whatsapp/qr)
- Botão desconectar
- Habilitar/desabilitar canal WhatsApp (PATCH /communication/settings)

**Asaas:**
- Status da subconta (external_account_id + external_account_status)
- Se subconta sem CPF/birthDate: formulário para completar
  (campos: CPF/CNPJ do responsável, data de nascimento)
  → endpoint a definir com planner (PATCH /companies/payment-provider ou similar)
- Habilitar/desabilitar Asaas como provider de pagamento

**PagSeguro:**
- Formulário para configurar credenciais (client_id, client_secret)
  → `POST /integrations/credentials` com provider=PAGSEGURO
- Status: "Aguardando confirmação do endpoint de terminal (sandbox pendente)"
- Desabilitar funcionalidades que dependem de terminal até sandbox validado

---

### REQ-11 — Configurações > Comunicação

**Rota:** `/configuracoes/comunicacao`

**Conteúdo:**
- Toggle: Email habilitado (PATCH /communication/settings → email_enabled)
- Toggle: WhatsApp habilitado (PATCH /communication/settings → whatsapp_enabled)
- Status do serviço de email (MAILTRAP_API_URL configurado?)
- Aviso quando email desabilitado: "Recuperação de senha e convites
  não serão enviados por email."

---

### REQ-12 — Configurações > Usuários (migrado)

**Rota:** `/configuracoes/usuarios`

**Conteúdo:**
- Lista de usuários (GET /users)
- Convidar usuário (POST /users/invite)
  - Formulário: email, nome, role (ADMIN/OPERATOR/PROFESSIONAL)
- Editar usuário: role, ativo/inativo
- Perfil próprio: alterar nome, alterar senha

---

### REQ-13 — Cadastro / convite de usuário — campo nome

**Alterar:**
- Formulário de convite: exibir campo `name` (backend já aceita após pré-requisito)
- Tela de ativação de conta (link do email): exibir campo para o usuário
  definir seu nome ao ativar a conta
- Header: exibir `User.name` retornado por `GET /auth/me`

**Nota:** toda a parte backend (migration, endpoints) já estará feita
no pré-requisito. Este REQ é puramente frontend.

---

## Comportamentos transversais

### Fee warning (aviso de taxa não configurada)
Qualquer tela que registre um pagamento manual deve:
1. Verificar `fee_warning` no response de `confirm-manual`
2. Se presente: exibir banner/toast com aviso e link para configuração
3. O pagamento já foi confirmado — o aviso é informativo, não bloqueante

### Estados de carregamento
Todas as novas telas devem ter estados de loading, empty state e erro.

### RBAC visual
Botões e ações que requerem OWNER/ADMIN devem ser ocultos ou desabilitados
para usuários com role OPERATOR ou PROFESSIONAL.
Verificar permissões via `GET /auth/me` → `role`.

---

## Fora de escopo deste sprint

- Telas da Fase 3 backend (catálogo avançado, comissões, crédito, pacotes,
  assinaturas, promoções, estoque, despesas)
- Portal do cliente
- NPS / fila de espera
- CRM
- Relatórios avançados (DRE, reconciliação)
- Identidade Paladino multi-tenant
- Painel PLATFORM_OWNER
- Campo CPF no formulário do profissional (removido da UI, retorna na Fase 3)

---

## Restrições técnicas

- Stack: Next.js (`painel/`)
- Protótipo Lovable em `github.com/Silva-fin/barberflow-system` como referência
  visual — não é spec de comportamento
- Modelos de domínio e RBAC nos docs de planejamento são autoritativos
- Nenhuma alteração em `agendamento_engine/` durante o sprint frontend
  (pré-requisito User.name já será aplicado antes)
- Zero mock data — consumir apenas endpoints reais do Railway

---

## Instrução para o planner

O planner deve:
1. Ler este brief na íntegra
2. Varrer o estado atual de `painel/` — páginas existentes, componentes,
   rotas configuradas, chamadas de API já implementadas
3. Identificar o que já existe vs. o que precisa ser criado ou alterado
4. Verificar se existe endpoint para completar dados Asaas após onboarding
   (`PATCH /companies/payment-provider` ou similar) — reportar como gap
   se ausente, pois REQ-10 depende disso
5. Verificar no formulário de profissional quais campos existem atualmente
   e confirmar que CPF/CNPJ está presente para ser removido (REQ-14)
6. Confirmar que `GET /auth/me` retorna `name` (pré-requisito já aplicado)
7. Gerar plano de execução detalhado por requisito, com:
   - Arquivos a criar ou alterar
   - Componentes reutilizáveis vs. novos
   - Ordem de implementação (dependências entre requisitos)
   - Prompt de execução por bloco de trabalho

**Premissas confirmadas (não verificar):**
- `User.name` existe no backend após pré-requisito — disponível em
  `GET /auth/me`, `POST /users/invite` e endpoint de ativação
- `Professional.cpf_cnpj` existe no banco mas deve sair da UI (REQ-14)
- Todos os endpoints listados em "Contexto do backend atual" estão ativos

---

*Brief v1.1 gerado em 2026-06-04.
Fonte das observações de UX: produto (Silva).
Fonte dos requisitos de backend: docs/pendencias-pos-sprint-integracoes.md
e estado atual do backend pós-Sprint de Integrações.*
