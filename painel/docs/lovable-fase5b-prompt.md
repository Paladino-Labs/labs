PROMPT — PALADINO · FASE 5B · PORTAL DO CLIENTE (LOVABLE)

Cole o bloco abaixo no Lovable. Protótipo visual com dados mockados — sem backend.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PALADINO — PORTAL DO CLIENTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Construa o **Portal do Cliente** do Paladino: a área web onde o **cliente final**
(quem é atendido, não quem opera o estabelecimento) acompanha sua relação com
**todos os estabelecimentos** que frequenta — agendamentos, cotas, assinaturas,
consentimentos e perfil.

Referência visual de consistência: o sistema barberflow
(https://github.com/Silva-fin/barberflow-system.git). Mantenha a mesma linguagem
visual sóbria das fases anteriores: paleta petrol escuro + dourado, tipografia
serifada (estilo Cormorant Garamond) para títulos e marca, Inter para corpo,
ícones de traço fino (16px), cantos arredondados, cards com sombra leve. Tudo via
tokens de tema — nada de cores fixas.

━━━ PRINCÍPIOS (leia antes de tudo) ━━━

1. **Shell totalmente separado.** Este Portal **não** é o painel do
   estabelecimento e **não** é uma página pública. Não tem a barra lateral do
   operador, não tem o cabeçalho de operador, não tem menus de administração
   (nada de "barbeiros", financeiro do negócio, configurações do tenant). O
   cliente vê **a relação dele com os estabelecimentos**.
2. **Autenticação própria.** Entrada por **magic link (padrão)** ou
   **e-mail + senha**. Sessão de cliente, separada de qualquer outra.
3. **Guard de autenticação.** Diferente das páginas públicas: se a sessão
   expira/é inválida (simule um "401"), **redirecione para a tela de login** do
   portal. Páginas autenticadas nunca aparecem sem sessão.
4. **Dados completamente mockados.** Sem chamadas reais. Use mocks determinísticos
   (regras abaixo) para exercitar todos os estados.
5. **Foco:** layout, estados (carregando/vazio/erro/dados), interações e fluxos.
6. **Mobile-first.** O cliente abre no celular. Navegação **lateral em telas
   médias/grandes** e **barra inferior (bottom nav) no mobile**. Alvos de toque
   confortáveis. Desktop centraliza, não alarga demais.
7. **Multi-tenant visível.** Todo item (agendamento, cota, assinatura, operação)
   **destaca o estabelecimento** a que pertence.

━━━ AUTENTICAÇÃO (fora da navegação autenticada) ━━━

▸ **Login** — `/portal/login`
  Card central estreito, logo/marca no topo. Alterne entre dois modos com um
  seletor (tabs ou botões segmentados):
  • **Magic link (padrão):** campo de e-mail + botão "Enviar link". Estados:
    parado → enviando (spinner) → **enviado** (mensagem genérica: "Se houver uma
    conta com esse e-mail, enviamos um link de acesso.") → erro de rede (inline).
  • **E-mail + senha:** campos de e-mail e senha + botão "Entrar". Credencial
    inválida → **erro inline** "E-mail ou senha incorretos".
  Sem "Criar conta" e sem "Esqueci a senha" — o magic link cobre a recuperação.

▸ **Landing do magic link** — `/portal/magic/<token>`
  Lê o token do endereço ao montar e "consome" automaticamente. Estados:
  • **verificando** (spinner + "Validando seu acesso…")
  • **sucesso** → redireciona para o painel do cliente
  • **erro** → ícone neutro + "Este link expirou ou já foi utilizado." + botão
    "Pedir novo link" (volta ao login).

━━━ ÁREA AUTENTICADA (com navegação + guard) ━━━

Layout com navegação persistente (lateral em md+, bottom nav no mobile) e estas
seções: **Início · Histórico · Cotas · Assinaturas · Consentimentos · Pagamentos ·
Perfil**. Rodapé/menu com nome do cliente e ação "Sair".

▸ **Início (dashboard)** — `/portal/dashboard`
  Duas seções:
  • **"Próximos agendamentos"** — lista compacta (máx 5): serviço, profissional,
    **estabelecimento (em destaque)**, data/hora e selo de status (em português).
    Link "Ver histórico".
  • **"Cotas ativas"** — lista compacta (máx 3): serviço, estabelecimento, **cotas
    restantes (ex.: "3 de 10")** com **barra de progresso colorida**, validade.
    Link "Ver todas".
  • (Opcional) banner discreto convidando a completar o perfil, quando faltarem
    dados (nome/e-mail). Pode ocultar se tudo estiver preenchido.
  Estados: esqueleto de carregamento por seção; vazio por seção ("Você ainda não
  tem agendamentos." / "Nenhuma cota ativa."); erro com botão "Tentar novamente".

▸ **Histórico** — `/portal/historico`
  Tabela (vira cards empilhados no mobile): serviço, profissional, **estabelecimento
  (destaque)**, data, selo de status, valor. **Filtros** por status e por
  estabelecimento. **Paginação**. Estados: esqueleto; vazio (com e sem filtro);
  erro com retry.

▸ **Cotas** — `/portal/cotas`
  Cards por cota: serviço, estabelecimento, **barra de progresso (usos x de y)**,
  validade (**vermelha se expirada**), selo de status. Cada card é **expansível**
  para mostrar o histórico de consumo (carregue só ao expandir). Estados: esqueleto;
  vazio ("Você não tem cotas."); erro.

▸ **Assinaturas** — `/portal/assinaturas`
  Lista: plano, estabelecimento, selo de status, próxima renovação, valor. Ações
  **Pausar** e **Cancelar** abrem um **diálogo de confirmação** (modal com botões —
  não use um "alert dialog" dedicado). Após confirmar, **o resultado aparece na
  própria tela** (o status muda) — não use toast para uma ação permanente como
  cancelar. Algumas assinaturas podem **não permitir pausa** (desabilite a ação
  nesses casos). Estado vazio gracioso ("Você não tem assinaturas.").

▸ **Pagamentos** — `/portal/pagamentos`
  Esta tela está **em desenvolvimento** no produto real (depende de integração de
  pagamentos ainda pendente). Para o protótipo, **mostre um layout de exemplo com
  1–2 cartões mockados** (bandeira + "•••• 4242" + selo de cartão padrão) e uma
  ação "Remover". Ao "Adicionar forma de pagamento", abra um formulário com o
  **modelo de autorização em opções de rádio**: **"Apenas esta vez" · "Permitir
  sempre" · "Cancelar"**. Deixe claro, num aviso discreto, que a funcionalidade
  estará disponível em breve.

▸ **Consentimentos** — `/portal/consentimentos`
  Lista de **interruptores (toggles)** agrupados por tipo: **Comunicação ·
  Tratamento de dados · Armazenamento de pagamento · Marketing**. Quando fizer
  sentido, mostre **subitens por canal** (WhatsApp / E-mail / SMS). O toggle é
  **otimista**: muda na hora e (no mock) confirma; se "falhar", **reverte**. Ao
  **desligar "Tratamento de dados"**, mostre um **aviso em card** (não um modal
  que trava a tela) explicando a consequência. Estados: esqueleto; erro de carga.

▸ **Perfil** — `/portal/perfil`
  Formulário: nome, e-mail e telefone (com máscara brasileira). Botão "Salvar".
  Estados **inline** sob o botão: parado → salvando → salvo / erro. Não use toast.
  (CPF não aparece nesta tela.)

━━━ MOCKS DETERMINÍSTICOS (para exercitar todos os estados) ━━━

Use estas regras fixas no protótipo, para que cada estado seja demonstrável sem
backend:

• **Login por magic link** com e-mail terminando em **"x@…"** (ex.: alex@…) →
  simule **link inválido/expirado**: a tela de envio mostra erro, e/ou ao abrir a
  landing o resultado é de erro.
• **Landing do magic link** com token terminando em **"x"** → **estado de erro**
  ("link expirou ou já foi utilizado").
• **Login por e-mail + senha** com credencial inválida (ex.: senha "errada") →
  **erro 401 inline** "E-mail ou senha incorretos".
• **Qualquer outro caso** → **login bem-sucedido** → entra no painel do cliente
  com **dados de exemplo** (alguns agendamentos em estabelecimentos diferentes,
  2–3 cotas em estágios variados — uma quase no fim, uma expirada —, 1–2
  assinaturas com status distintos, consentimentos mistos, e um perfil preenchido).
• Inclua também, nos mocks, **listas vazias** acessíveis (ex.: um filtro de
  histórico que não retorna nada) para mostrar os estados vazios.

━━━ DETALHES VISUAIS ━━━

• Selos de status sempre em **português** (ex.: Agendado, Concluído, Cancelado,
  Não compareceu, Ativo, Pausada, Cancelada). Cor por significado, via tokens
  (sucesso/neutro/atenção/erro), nunca cor fixa.
• **Barra de progresso de cota colorida:** acima de ~50% normal; abaixo de ~25%
  âmbar/atenção; zero em cinza/neutro.
• Datas em formato brasileiro; valores em Reais (R$).
• Ícones de traço fino (Lucide-style, 16px). Nada de emojis como ícone.
• Vazio = ilustração/ícone neutro + frase curta + (quando fizer sentido) uma ação.
  Erro = ícone + frase + botão "Tentar novamente".
• Carregamento = esqueletos (skeletons), não spinners de tela cheia (exceto na
  landing do magic link).

━━━ NOTA DE IMPLEMENTAÇÃO ━━━
Este protótipo está em TanStack Start/React.
O Claude Code traduzirá para Next.js App Router (painel/).
Shell do portal: app/(portal)/ — grupo de rota separado de (dashboard)/ e (public)/.
Helper portalFetch a criar em lib/portal-api.ts com JWT separado do tenant.
Consultar: https://github.com/Silva-fin/barberflow-system.git
