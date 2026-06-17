# PROMPT — FASE 5A · SUPERFÍCIES PÚBLICAS (PASTE-READY)

> Cole o bloco abaixo no Lovable. Ele descreve **comportamentos e dados mockados** —
> sem endpoints, sem caminhos de arquivo. A fiação real (API) é feita depois.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PALADINO — FASE 5A: PÁGINAS PÚBLICAS DO CLIENTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Você vai construir **três páginas públicas** acessadas pelo **cliente final**, sem
nenhum login. Elas chegam por um **link no WhatsApp** e abrem quase sempre no
**celular**. São páginas **mobile-first**, minimalistas, e vivem **fora** da área
administrativa do produto.

Stack: **React + TypeScript + shadcn/ui + TailwindCSS + ícones Lucide**. Tipografia:
**Cormorant Garamond** nos títulos (classe `font-display`) e **Inter** no corpo.
Use **tokens semânticos** (`bg-background`, `bg-card`, `text-muted-foreground`,
`text-primary`, `border-border`) — **nunca** cores fixas (`bg-white`, `text-gray-*`,
hex soltos). Ícones Lucide a 16px, `strokeWidth 1.5` — **sem emojis**. Moeda em
formato BRL (R$ 1.234,56). Datas em pt-BR.

## REGRA DE OURO — SHELL PÚBLICO ≠ SHELL DO PAINEL

Estas páginas **NÃO** têm a barra lateral, o cabeçalho nem os menus da área
administrativa. Elas usam um **shell público próprio e separado**:

- **Cabeçalho mínimo:** apenas a **marca**. Se a página tiver o logo/nome do
  estabelecimento, mostre-os; senão, mostre o wordmark **"PALADINO"** centralizado
  (use a fonte de títulos, com bastante espaçamento entre letras).
- **Sem** navegação, sem avatar, sem alternador de tema, sem "voltar ao painel".
- **Fundo** `bg-background`; conteúdo **centralizado** e **estreito**
  (`max-w-md`/`max-w-xl`), confortável no celular.
- **Rodapé discreto:** `© PALADINO` em texto pequeno e esmaecido.
- **Em NENHUMA hipótese** redirecione para tela de login ou de cadastro — nem em
  caso de erro. O cliente não tem conta.

Crie esse shell como um **layout compartilhado** para as páginas **P2 (`/manage`)**
e **P3 (`/nps/respond`)**. A **P1 (`/book/[slug]`) já tem o seu próprio chrome** —
**não a coloque dentro deste layout e não altere o cabeçalho/rodapé dela.**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## PÁGINA 1 — ABA "PRODUTOS" NA VITRINE DE AGENDAMENTO  ·  rota: /book/[slug]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A página pública de agendamento **já existe** (uma vitrine do estabelecimento com
abas **Serviços · Profissionais · Avaliações** e um fluxo de agendamento). **Não
recrie** o resto — você só **acrescenta uma nova aba "Produtos"** ao conjunto de
abas existente.

**Aba Produtos (vitrine, não loja):**
- Um **grid de cartões de produto**, no mesmo estilo visual dos cartões de serviço.
- Cada cartão: imagem (ou ícone de marcador se sem imagem), **nome**, **descrição
  curta** (1 linha, com reticências), **preço** em BRL, e um selo **"Esgotado"**
  quando indisponível.
- **Sem** botão de comprar/agendar (é apenas exibição). Opcionalmente, um link
  discreto **"Falar no WhatsApp"** por produto.
- **Vazio:** se não houver produtos, mostre um estado vazio gentil
  ("Nenhum produto disponível" ou "Em breve").
- **Responsivo:** 1 coluna no celular, 2–3 colunas em telas maiores.

**Dados mockados** (use ~6 produtos variados, alguns "esgotado"):
```
[
  { id:"p1", name:"Pomada Modeladora Matte",  price:4990, description:"Fixação forte, efeito seco", image:null, available:true },
  { id:"p2", name:"Óleo para Barba 30ml",     price:3590, description:"Hidrata e amacia os fios",   image:null, available:true },
  { id:"p3", name:"Shampoo Anticaspa 250ml",  price:2990, description:"Uso diário",                 image:null, available:false },
  { id:"p4", name:"Kit Navalha + Lâminas",    price:7900, description:"Acabamento profissional",    image:null, available:true },
  { id:"p5", name:"Talco Pós-Barba",          price:1990, description:"Sensação refrescante",       image:null, available:true },
  { id:"p6", name:"Cera Capilar 100g",        price:4290, description:"Brilho leve, reaplicável",   image:null, available:false }
]
```
(preços em centavos → exiba dividido por 100, formato BRL.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## PÁGINA 2 — GESTÃO DE AGENDAMENTO POR LINK  ·  rota: /manage/[token]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

O cliente recebe pelo WhatsApp um **link único** para **ver, cancelar ou remarcar**
o agendamento, **sem login**. O `token` da URL é opaco (não significa nada para o
usuário). Página standalone, sob o shell público, **um único cartão centralizado**.

### Estados da página

**1) Carregando** — enquanto busca os dados: um "Carregando…" simples / skeleton do
cartão.

**2) Link inválido ou expirado** — se o link não vale mais (expirou, já foi usado,
ou o agendamento já foi finalizado): uma **página de erro clara** — ícone neutro,
título **"Link inválido ou expirado"**, e o texto *"Este link de gestão não está
mais disponível. Fale com o estabelecimento para reagendar."* **Sem** botão de
login, **sem** voltar ao painel.

**3) Agendamento ativo** — cartão com:
- **Serviço**, **Profissional**, **Data e hora** (formatada em pt-BR), e um **badge
  de status** ("Agendado").
- Dois botões: **Cancelar** e **Remarcar** (desabilite cada um conforme as flags
  `canCancel` / `canReschedule` do mock).

### Ação CANCELAR
- Abre um **diálogo de confirmação** ("Tem certeza que deseja cancelar este
  agendamento?", com "Voltar" e "Sim, cancelar"). *(O projeto **não** usa
  `AlertDialog` — use um `Dialog` comum com dois botões.)*
- Ao confirmar → estado **enviando** (botão com spinner) → **tela de resultado**:
  exiba a **mensagem retornada** (mock abaixo). Quando o cancelamento ocorrer **fora
  do prazo e houver sinal pago**, a mensagem avisa que **o sinal foi retido** —
  destaque esse aviso visualmente (cartão de atenção, ícone de alerta). Depois do
  cancelamento, **não** volte ao formulário — o link encerrou.

### Ação REMARCAR
- Abre um **seletor de data e hora** (date + time picker). **Não** há lista de
  horários disponíveis nesta tela — o cliente escolhe livremente um momento e
  confirma.
- Botão **"Confirmar remarcação"** → estado **enviando** →
  - **Sucesso:** tela de resultado com a nova data/hora e o aviso de que **um novo
    link de confirmação foi enviado** (o link atual deixa de funcionar).
  - **Horário indisponível:** mensagem inline *"Esse horário não está disponível.
    Escolha outro."* — mantenha o seletor aberto para nova tentativa.

**Mocks determinísticos para o preview** (simule por sufixo do token):
- token terminando em **`x`** → estado **link inválido/expirado**.
- token terminando em **`r`** → ao remarcar, simule **horário indisponível**.
- token terminando em **`d`** → ao cancelar, simule **`deposit_retained=true`**
  (mostre o aviso de retenção do sinal).
- qualquer outro caractere → ao cancelar, simule **`deposit_retained=false`**
  (mensagem simples de cancelamento).
- caso contrário (token válido) → agendamento ativo:
```
{ serviceName:"Corte + Barba", professionalName:"Rafael", scheduledAt:"2026-06-20T15:30:00", status:"Agendado", canCancel:true, canReschedule:true }
```
- mensagem de cancelamento (com retenção): *"Agendamento cancelado. Como o
  cancelamento foi fora do prazo, o sinal pago foi retido conforme a política do
  estabelecimento."*
- mensagem de cancelamento (sem retenção): *"Agendamento cancelado com sucesso."*
- mensagem de remarcação: *"Agendamento remarcado com sucesso. Enviamos uma nova
  confirmação com o link atualizado."*

> **Excesso de tentativas:** se o cliente repetir muitas ações em pouco tempo,
> mostre um aviso *"Muitas tentativas, tente novamente em instantes."* (apenas
> simule o estado; não precisa de lógica de contagem real.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## PÁGINA 3 — AVALIAÇÃO (NPS) PÚBLICA  ·  rota: /nps/respond/[survey_id]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Página de **uma pergunta** que o cliente abre por link após um atendimento. Cega:
**não** carrega dados prévios. Card centralizado sob o shell público.

- Título **"Como foi sua experiência?"** + subtítulo *"De 0 a 10, o quanto você
  recomendaria nosso atendimento?"*.
- **Seletor de nota 0–10**: 11 botões/segmentos. Faixas de cor (apenas visual):
  **0–6 vermelho (detrator) · 7–8 âmbar (neutro) · 9–10 verde (promotor)**. O botão
  selecionado fica realçado (anel/realce na cor da faixa). Legendas nas pontas:
  "Pouco provável" … "Muito provável".
- **Comentário (opcional):** `Textarea`, até 2000 caracteres.
- Botão **"Enviar"** (desabilitado enquanto nenhuma nota for escolhida).

### Estados
- **idle** — formulário.
- **enviando** — botão desabilitado + spinner.
- **sucesso** — substitui o formulário por um agradecimento: ícone de check,
  **"Obrigado pelo seu feedback!"** + *"Sua avaliação foi registrada com sucesso."*
  Não há volta ao formulário.
- **erro / indisponível** — se a pesquisa já foi respondida ou expirou:
  *"Esta pesquisa não está mais disponível."*; qualquer outro erro:
  *"Não foi possível enviar, tente novamente."*

**Mock determinístico:** `survey_id` terminando em **`x`** → estado
**indisponível**; caso contrário → **sucesso** após ~700ms.

> Observação: esta página **já existe** numa versão anterior. Mantenha o mesmo
> comportamento do seletor de nota e dos estados; o objetivo aqui é **encaixá-la no
> shell público compartilhado** (cabeçalho/rodapé descritos na Regra de Ouro).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## CHECKLIST DE QUALIDADE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- [ ] **Mobile-first**: tudo legível e tocável no celular (alvos ≥ 44px, sem scroll
      horizontal, seletor de nota e date/time picker confortáveis no dedo).
- [ ] **Shell público** separado: marca + rodapé, **sem** sidebar/header/menus do
      painel; **nunca** redireciona para login.
- [ ] **Erros claros**: link inválido (P2) e pesquisa indisponível (P3) viram
      páginas/estados explicativos, não telas em branco nem 401.
- [ ] **P2**: cancelar (com aviso de retenção de sinal quando aplicável) **e**
      remarcar (date+time picker, sem lista de horários) completos, com tela de
      resultado final.
- [ ] **P1**: aba Produtos adicionada **sem** alterar as abas existentes da vitrine.
- [ ] **Tokens semânticos** e **Lucide** em tudo; faixas de cor do NPS aplicadas;
      BRL e datas em pt-BR.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## NOTA DE TRADUÇÃO — TanStack Router → Next.js (App Router)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

O destino é **Next.js (App Router)**, não TanStack Router. Ao portar:
- Rotas viram **pastas** com `page.tsx`. Parâmetros dinâmicos são `[token]` /
  `[survey_id]` / `[slug]` (não `$token`). O **shell público** é um
  **layout de grupo** (ex.: pasta `(public)/layout.tsx`) que **não** carrega o
  layout autenticado.
- Páginas com interação (seleção, envio, estados) são **Client Components**
  (`"use client"`). Leia o parâmetro de rota via `useParams()`.
- **Sem** `createFileRoute`, `useNavigate`, `@tanstack/react-query` específicos —
  use estado local (`useState`) para os mocks; a fiação de dados real entra depois.
- Mantenha tudo **sem autenticação**: nenhuma chamada destas páginas deve enviar
  cabeçalho de autorização. Os dados acima são **mock**; substitua por chamadas
  públicas reais somente na etapa de integração.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
</content>
