# PALADINO — PROMPT DO SPRINT VISUAL GAP (LOVABLE)

> Cole este prompt no Lovable. Ele especifica **10 telas** que precisam ficar no **mesmo padrão visual** do resto do produto. É um sprint de **consistência visual**: cada tela já tem um comportamento definido — aqui você só desenha o **visual** com **dados mockados**. **9 telas** são reskins de telas existentes; **1** é nova (Relatórios). Onde houver conflito com qualquer referência, **vença este documento**.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 0. CONTEXTO E O QUE JÁ EXISTE (NÃO REIMPLEMENTAR)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Paladino é um SaaS multi-tenant para barbearias (piloto). Stack: **React · TypeScript · shadcn/ui · TailwindCSS · Lucide**. Display **Cormorant Garamond**, corpo **Inter**. Petrol escuro (`primary`) + brass/ouro (`accent`), fundo creme.

O **shell já existe** — **não recriar**: sidebar, header, layout, guards, branding, tokens. Você produz **apenas o conteúdo das páginas**. Os componentes compartilhados **já existem** — **reaproveite, não recrie**: `PageHeader`, `EmptyState`, `ErrorState`, `Skeleton`, `ActiveBadge`, badges de status (`FsmBadge`), `toast` (sonner), e os utilitários de moeda/data.

**Natureza do sprint:** estas telas já existem com um visual antigo (alerts nativos, tabelas cruas, badges com cor "chapada", "Salvo ✓" inline, blocos de erro soltos). Sua tarefa é **redesenhá-las no padrão atual** — **sem inventar campos, colunas ou ações novas** além das listadas. Use dados mockados realistas.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 1. PADRÃO VISUAL A SEGUIR (vale para TODAS as telas)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- **Cabeçalho:** sempre `PageHeader` — título em `font-display text-3xl tracking-wide` + descrição opcional + slot de ações à direita (botões). Nunca um `<h1>` solto com tamanho arbitrário.
- **Tabelas:** sempre dentro de moldura `rounded-lg border` com cabeçalho `bg-muted/50 text-muted-foreground`, linhas com `hover:bg-muted/30`, valores monetários alinhados à direita. Nunca tabela "nua".
- **Inputs:** componente `Input`/`Select`/`Switch`/`Textarea` do kit — nunca `<input>` com classes manuais.
- **Estados (telas com carga):** **loading** = `Skeleton` no formato da tabela/grid; **erro** = `ErrorState` com botão "Tentar novamente"; **vazio** = `EmptyState` (ícone + título + descrição + ação opcional); **dados** = conteúdo.
- **Acesso restrito:** quando o papel não permite, use `EmptyState` (ícone cadeado, "Acesso restrito", "Disponível apenas para Proprietário e Administrador") — nunca um parágrafo solto.
- **Feedback de ação:** **toast** (sonner) após salvar/criar/excluir — sucesso e erro. Nunca "Salvo ✓" inline nem `alert()`/`confirm()` nativos. Confirmações destrutivas usam `AlertDialog`/`Dialog`.
- **Badges de status:** sempre o badge padrão `<Badge variant="outline">` com classe de cor por **token** (emerald/âmbar/sky/destructive/muted) — nunca `bg-green-100 text-green-800` chapado.
- **Cores:** só tokens (`bg-card`, `text-muted-foreground`, `text-success`, `text-destructive`, `bg-primary`). Nunca verde/vermelho/âmbar hexadecimais soltos.
- **Ícones:** Lucide 16px, `strokeWidth 1.5`. Nunca emojis.

**Badges de status usados neste sprint (cor por faixa):**
- **Comissão:** Pendente (âmbar) · Vence em breve (sky) · Paga (emerald) · Estornada (vermelho).
- **Pagamento de comissão (payout):** Pago (emerald) · Pendente (âmbar) · Falhou (vermelho).
- **Agendamento:** Rascunho (muted) · Solicitado (sky) · Agendado (emerald) · Em andamento (âmbar) · Concluído (muted) · Cancelado/Não compareceu/Falhou (vermelho).
- **Ativo/Inativo:** badge sólido (Ativo) / suave (Inativo).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 2. OPERAÇÃO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 2.1 — Agenda
Tela de agenda com duas visões (Lista e Calendário) e navegação por semana.
- **Topo:** título "Agenda" + intervalo da semana ("8 jun – 14 jun 2025"); à direita: setas ‹ ›, botão "Hoje", toggle **Lista / Calendário**, botão "+ Novo Agendamento".
- **Day picker:** 7 cartões (Dom…Sáb) com número do dia grande e contagem ("3 agend."); o dia ativo destacado com borda/realce primário.
- **Filtros:** `Select` barbeiro + `Select` status + contador "N resultados" à direita.
- **Tabela do dia:** Horário · Cliente (nome + telefone) · Serviço(s) · Barbeiro · **Status** (badge de agendamento) · Valor (à direita). Linha clicável abre **Dialog de detalhe** (status, cliente, barbeiro, serviços, horário, total) com ações **Remarcar** / **Concluir** / **Cancelar** (escondidas se o status for terminal).
- **Remarcar:** `Dialog` com `input` datetime + Confirmar.
- **Cancelar:** `AlertDialog` de confirmação → ao confirmar, **toast** "Agendamento cancelado".
- **Estados:** loading = `Skeleton` (day picker + tabela); erro = `ErrorState` (retry); dia sem agendamentos = `EmptyState` ("Nenhum agendamento para este dia").
- **Dados mockados:** 5–8 agendamentos no dia ativo variando status e barbeiro; 3 barbeiros; valores R$ 30–120.

### 2.2 — Novo agendamento
Formulário em um `Card` centralizado (coluna estreita).
- **Cabeçalho:** `PageHeader` "Novo Agendamento" + link "← Voltar".
- **Campos (em ordem):** `Select` Barbeiro · `Select` Serviço (rótulo "Corte — R$ 45 / 30min") · `input` Data · **grade de horários** disponíveis (botões "09:00", "09:30"… ; selecionado com borda primária) · **Cliente** (busca por nome/telefone com dropdown de resultados; alternância "+ Novo cliente" que revela sub-form Nome/Telefone/E-mail).
- **Ações:** "Voltar" + "Confirmar" (desabilitado até barbeiro+serviço+cliente+horário).
- **Feedback:** erro de carga inicial = `ErrorState`; erro ao confirmar ou ao cadastrar cliente = **toast.error**; sucesso = **toast.success** "Agendamento criado".
- **Dados mockados:** 3 barbeiros, 4 serviços, ~6 horários, 5 clientes na busca.

### 2.3 — Barbeiros
Grid de cards de barbeiros.
- **Cabeçalho:** `PageHeader` "Barbeiros" + botão "+ Novo Barbeiro" (abre `Dialog` com campo Nome).
- **Card:** avatar com iniciais + nome + horário de trabalho; chips de especialidades (ou "Especialidades em breve"); fileira de dias da semana (Dom…Sáb, ativos destacados); comissão ("45%" ou "Em breve"); botões "Editar" e "Ativar/Desativar"; opcional `ActiveBadge` no topo.
- **Estados:** loading = `Skeleton` (grid de cards); erro = `ErrorState` (retry); vazio = `EmptyState` ("Nenhum barbeiro cadastrado", ação "Novo Barbeiro").
- **Feedback:** criar → toast "Barbeiro criado"; ativar/desativar → toast; erro → toast.error.
- **Dados mockados:** 6 barbeiros, alguns com especialidades/comissão preenchidos e outros com "Em breve".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 3. COMISSÕES (4 telas)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 3.1 — Comissões (hub)
- **Cabeçalho:** `PageHeader` "Comissões" (descrição "Regras, histórico e pagamentos da equipe").
- **KPIs:** 3 cards — "A pagar" (R$), "Pago (30 dias)" (R$), "Profissionais com pendência" (número).
- **Acesso rápido:** 3 cards-link (ícone em quadro primário + título + descrição + chevron): **Regras**, **Histórico**, **Pagamentos**.
- **Estados:** loading = KPIs em `Skeleton`; erro = `ErrorState`.
- **Dados mockados:** A pagar R$ 1.240,00; Pago 30d R$ 3.880,00; 4 profissionais com pendência.

### 3.2 — Regras de comissão
- **Cabeçalho:** `PageHeader` "Regras de comissão" (descrição sobre cálculo por barbeiro/serviço).
- **Seção "Regra geral":** `Card` com form em linha — `Select` Base de cálculo ("Percentual sobre valor bruto" / "Valor fixo (R$)"), `Input` Taxa(%) ou Valor fixo, `Select` "Quem paga a taxa" ("Barbearia paga" / "Dividida 50/50" / "Barbeiro paga"), botão "Salvar". Sucesso → **toast** (nunca "Salvo ✓" inline).
- **Seção "Regras específicas":** `Card` com botão "+ Nova regra" e **tabela padrão**: Profissional · Serviço · Base · Taxa · Quando (quem paga) · Ações (Editar / Excluir). Excluir abre `AlertDialog` de confirmação → toast.
- **Dialog criar/editar:** `Select` Profissional ("Todos os barbeiros" + lista) · `Select` Serviço ("Todos os serviços" + lista) · `Select` Base · `Input` Taxa/Valor · `Select` Quem paga.
- **Estados:** acesso restrito = `EmptyState`; loading = `Skeleton`; erro = `ErrorState`; sem regras específicas = linha "Nenhuma regra específica cadastrada".
- **Dados mockados:** regra geral 40% / "Barbearia paga"; 3 regras específicas (ex.: "João · Barba · 50% · Dividida").

### 3.3 — Histórico de comissões
- **Cabeçalho:** `PageHeader` "Histórico de Comissões".
- **Filtros (`Card`):** `Select` Profissional · `Select` Status (Todas/Pendentes/Pagas/Estornadas) · Data De · Data Até · botão "Filtrar".
- **Tabela padrão:** Data · Profissional · Tipo (Agendamento/Pacote/Assinatura) · Valor bruto (dir.) · Comissão (dir.) · **Status** (badge de comissão). Rodapé: "Total pendente: R$ …".
- **Estados:** loading = `Skeleton`; erro = `ErrorState`; vazio = `EmptyState` ("Nenhuma comissão encontrada para os filtros").
- **Dados mockados:** ~10 linhas variando status (Pendente/Vence em breve/Paga/Estornada) e tipo; total pendente R$ 620,00.

### 3.4 — Pagamentos de comissões
- **Cabeçalho:** `PageHeader` "Pagamentos de comissões".
- **Registrar pagamento (`Card`):** `Select` "Selecione um barbeiro" → ao escolher, mostra **lista compacta** das comissões pendentes (data + valor), "Total a pagar: R$ …", `Select` "Conta para débito" (se houver +1 conta), botão "Pagar R$ … em comissões". Sucesso → **toast** "Pagamento registrado" (nada de card verde inline com auto-dismiss).
- **Histórico de pagamentos:** **tabela padrão** — Data · Profissional · Comissões pagas · Valor total (dir.) · **Status** (badge de payout: Pago/Pendente/Falhou).
- **Estados:** acesso restrito = `EmptyState`; erro de carga = `ErrorState`; barbeiro sem pendências = texto "Nenhuma comissão pendente para …"; sem payouts = `EmptyState`.
- **Dados mockados:** 3 barbeiros; ao escolher um, 4 comissões pendentes (total R$ 380,00); histórico com 5 payouts (a maioria "Pago").

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 4. FINANCEIRO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 4.1 — Taxas de maquininha
- **Cabeçalho:** `PageHeader` "Taxas de maquininha" (descrição "Taxas de processamento por método de pagamento").
- **Tabela editável (`Card`):** Método · Taxa (%) · Fixa (R$) · Ações. Cada linha editável tem `Input` numérico para % e R$, e botão "Salvar" por linha → **toast** (nunca "Salvo ✓" verde inline). Método "Dinheiro" aparece como **não-editável** ("0% — sem taxa", "R$ 0,00", ação "—"). Linha sem taxa configurada: hint discreto "Não configurado" em `text-muted-foreground` (não âmbar chapado).
- **Estados:** acesso restrito = `EmptyState`; loading = `Skeleton`; erro = `ErrorState`.
- **Dados mockados:** ~8 métodos (Dinheiro, Chave PIX, PIX maquininha, Débito, Crédito Visa/Master/Elo, Crédito parcelado) com % entre 0–4,5 e fixa R$ 0,00–0,49.

### 4.2 — Registrar pagamento
Formulário em `Card` centralizado com 3 fases (form → registrando → confirmado).
- **Cabeçalho:** `PageHeader` "Registrar Pagamento" + link "← Voltar".
- **Form:** autocomplete de **Cliente** · `Select` "Agendamento (opcional)" (aparece após escolher cliente) · `Input` **Valor** (mostra "R$ 1.234,00" formatado abaixo) · **Método de pagamento** em grupos (Dinheiro / PIX / Maquininha), cada opção um botão com ícone (selecionado com borda primária) · botão "Confirmar pagamento".
- **Fase "registrando":** card com spinner/"Registrando pagamento…".
- **Fase "confirmado":** card de sucesso (ícone check em `text-success`, **não** verde hardcoded) com Valor líquido, Taxa aplicada, Método; abaixo, **banner de aviso de taxa** (se a maquininha não tiver taxa configurada) com ação "Configurar"; botões "Novo pagamento" / "Ver lista".
- **Feedback:** acesso restrito = `EmptyState`; erro ao submeter = **toast.error**.
- **Dados mockados:** 5 clientes; ao escolher, 2 agendamentos; métodos com ícones; sucesso → líquido R$ 96,30 / taxa R$ 3,70 / "Crédito Visa".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 5. CONTA E CONFIGURAÇÕES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 5.1 — Configurações (hub)
- **Cabeçalho:** `PageHeader` "Configurações" (descrição "Gerencie as configurações da sua empresa").
- **Grid de cards-link** (ícone em quadro primário + título `font-display` + descrição + chevron): **Meu Perfil**, **Perfil da empresa**, **Segurança**, **Usuários**, **Integrações**, **Comunicação**. (Opcional: card **Relatórios**.) Já está quase no padrão — só padronizar o cabeçalho. Sem estados de carga (estático).

### 5.2 — Meu Perfil
- **Cabeçalho:** `PageHeader` "Meu Perfil" (descrição "Suas informações de acesso").
- **`Card` "Informações pessoais":** `Input` Nome (editável) · `Input` E-mail (read-only, com nota "não editável") · **Papel** como `Badge` ("Proprietário"/"Administrador"/"Operador"/"Profissional") · botão "Salvar" (desabilitado se nada mudou).
- **Feedback:** salvar → **toast.success** (nunca "Salvo ✓" inline); erro → toast.error. Loading inicial opcional = `Skeleton`.
- **Dados mockados:** Nome "Carlos Mendes", e-mail "carlos@barbearia.com", papel "Proprietário".

### 5.3 — Segurança
- **Cabeçalho:** `PageHeader` "Segurança" (descrição "Altere sua senha de acesso").
- **`Card` "Trocar senha":** `Input` Senha atual · `Input` Nova senha (hint "Mínimo 8 caracteres, 1 maiúscula e 1 número") · `Input` Confirmar nova senha. Validação de campo continua **inline** (mensagem por campo). Botão "Alterar senha".
- **Feedback:** sucesso → **toast.success** (ou box em token `border-success/40 bg-success/15`); erro de submit → **toast.error**.
- **Dados mockados:** campos vazios; demonstrar 1 erro de validação ("As senhas não coincidem").

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 6. TELA NOVA — RELATÓRIOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Hub de acesso rápido a relatórios (OWNER/ADMIN). **Desenhar do zero** no mesmo molde do hub de Comissões.
- **Cabeçalho:** `PageHeader` "Relatórios" (descrição "Acesso rápido a indicadores e relatórios").
- **Grid de cards ativos** (cada um navega para uma tela existente; ícone em quadro `bg-primary/15 text-primary` + título `font-display` + descrição + chevron):
  - **DRE** (ícone barras) — "Demonstrativo de resultados do mês"
  - **Comissões** (ícone cifrão) — "A pagar, pagas e por profissional"
  - **NPS** (ícone estrela) — "Satisfação e pesquisas respondidas"
  - **Estoque** (ícone caixas) — "Quantidades e custo médio"
  - **Auditoria** (ícone escudo) — "Trilha de ações sensíveis"
  - **CRM** (ícone pessoas) — "Clientes em risco e classificações"
- **Grid de cards "Em breve"** (visual muted, `opacity` reduzida, `cursor-default`, `Badge` "Em breve", **sem** link):
  - **Fluxo de caixa**
  - **Performance por profissional**
  - **Agendamentos por período**
- **Estados:** estático (sem carga) — só os cards.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 7. REGRAS ABSOLUTAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- **Só visual.** Não invente campos, colunas, filtros ou ações além dos listados aqui. Use dados mockados.
- **Cabeçalho** sempre `PageHeader`; **tabela** sempre com moldura + cabeçalho muted; **inputs** sempre do kit.
- **Estados obrigatórios** em telas com carga: loading (`Skeleton`), erro (`ErrorState` + retry), vazio (`EmptyState`), dados.
- **Feedback** sempre por **toast** — nunca `alert()`/`confirm()`, nunca "Salvo ✓" inline. Confirmação destrutiva = `AlertDialog`.
- **Acesso restrito** = `EmptyState`, nunca parágrafo solto.
- **Cores** só por **token**; **badges** sempre o padrão por faixa de cor — nunca cor hexadecimal chapada.
- **Ícones** Lucide 16px/1.5; nunca emojis.
- **Relatórios** é a única tela nova; o resto é reskin de telas existentes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTA DE IMPLEMENTAÇÃO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Protótipo em TanStack Start.
Claude Code traduz para Next.js App Router (painel/).
Referência de estrutura:
https://github.com/Silva-fin/barberflow-system.git
