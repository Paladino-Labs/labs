# Brief — Auditoria de Design: Painel Paladino × barberflow-system

**Para:** Claude Code  
**Data:** 2026-05-29  
**Objetivo:** Verificar o estado atual do frontend do projeto Paladino, comparar com o design de referência (`barberflow-system/`) e espelhar a identidade visual desse protótipo no projeto Paladino.

---

## 1. Contexto do produto

O **Paladino** é uma plataforma SaaS multi-tenant de gestão para barbearias (Estágio 0), construída sobre:

- **Backend:** FastAPI + SQLAlchemy + Alembic (Sprint 6 em andamento — Financial Core)
- **Frontend:** Next.js 16.2.2 · React 19.2.4 · TailwindCSS v4 · shadcn/ui v4 · App Router
- **Design system próprio** com tokens semânticos (`bg-card`, `border-border`, `text-muted-foreground`, `bg-primary`) — nunca valores hardcoded
- **Identidade visual por tenant** via tokens (logo, cores, fonte, favicon) — estrutura da UI é única

O frontend atual tem **8 áreas no painel** (`app/(dashboard)/`):

```
appointments · customers · dashboard · integrations ·
products · professionals · services · settings/profile
```

E o **Link Público** em `app/book/[slug]/` (vitrine + BookingFlow FSM).

---

## 2. O protótipo de referência

O repositório `barberflow-system/` (gerado no Lovable) é a **referência de DESIGN/UX** oficial do projeto. Ele cobre as mesmas áreas do painel **e o Link Público de agendamento** em stack diferente (TanStack Start/Router + Vite + Tailwind v4 + Radix/shadcn).

**Escopo coberto pelo protótipo:**
- Painel do tenant (dashboard, agenda, clientes, profissionais, serviços, financeiro, configurações)
- **Link Público** (`b/$slug` no protótipo → `book/[slug]` no Paladino): vitrine da barbearia + fluxo de agendamento + confirmação

### O que USAR do barberflow-system
- Layout geral, navegação, look & feel
- Composição visual dos componentes (cards, tabelas, formulários, sidebar, header)
- Paleta de cores, tipografia aplicada, espaçamentos
- Estados visuais (hover, active, empty states, loading states)

### O que NÃO usar como referência
- Comportamento de negócio e fluxos (a fonte de verdade é a documentação do Paladino)
- Stack e estrutura de arquivos (o Paladino usa Next.js App Router)
- Dados mockados (o Paladino é API-first, sem mock no frontend)

> **Sobre labels e nomenclatura:** os nomes usados no protótipo ("Barbeiros", "Agenda", etc.) podem e devem ser adotados — o produto é focado em barbearia no Estágio 0 e a visão prevê que esses labels serão configuráveis por vertical no futuro. Não há problema em usar a nomenclatura do protótipo como está.

---

## 3. Limites invioláveis — o que protege o backend

O frontend do Paladino não tem design system estabelecido — o que existe hoje é uma tentativa incompleta de replicar o protótipo, sem direcionamento formal. **O Claude Code tem liberdade total para avaliar, propor e implementar o design system com base no barberflow-system**, incluindo refazer tokens, tipografia, componentes e estrutura visual do zero se necessário.

O que não pode ser alterado são os contratos com o backend:

| Restrição | Motivo |
|-----------|--------|
| Nunca usar `fetch` raw — sempre `lib/api.ts` | Centraliza autenticação JWT e tratamento de erros |
| Zero lógica de negócio no frontend | Cálculos, validações de disponibilidade, regras de negócio pertencem à API |
| Não quebrar o App Router nem a estrutura de autenticação | Login, sessão e rotas protegidas já funcionam em produção |
| Não criar chamadas a endpoints que não existem | O painel é cliente da API atual — não antecipar módulos futuros |
| Não referenciar `painel/painel/` | Diretório removido — não existe mais |
| Não copiar o stack do protótipo (TanStack/Vite) | O Paladino é Next.js App Router — adaptar, não portar |

---

## 4. O que fazer — passo a passo

### Passo 1 — Ler o estado atual do frontend Paladino

Percorrer os arquivos do frontend (Next.js App Router). Focar em:

```
app/(dashboard)/           ← 8 áreas do painel
app/book/[slug]/           ← link público
app/page.tsx               ← login / landing
components/                ← componentes compartilhados
components/ui/             ← shadcn/ui
lib/                       ← utils, api, theme
app/globals.css            ← tokens do design system
```

Documentar por área — **incluindo o Link Público** (`app/book/[slug]/page.tsx` + `BookingFlow.tsx`):
- Estrutura atual de layout
- Componentes em uso
- Gaps visuais evidentes (ex: ausência de estados vazios, headers inconsistentes, responsividade do link público, etc.)

### Passo 2 — Ler o design de referência no barberflow-system

Percorrer o `barberflow-system/` e mapear:

```
src/routes/                ← páginas
src/components/            ← componentes
src/lib/                   ← utils e mocks
```

Para cada área equivalente (dashboard, agenda, clientes, profissionais, serviços, configurações, login, **link público de agendamento**), documentar:
- Layout adotado
- Padrões visuais aplicados
- Componentes e composições reutilizáveis

> **Nota sobre o Link Público no protótipo:** localizado em `src/routes/b.$slug/` (ou equivalente). Cobrir vitrine da barbearia, seleção de serviço/profissional/horário, e tela de confirmação.

### Passo 3 — Comparar e mapear gaps de design

Criar uma tabela de comparação área por área, identificando o que está faltando ou divergente no Paladino em termos de design/UX (não de comportamento de negócio).

### Passo 4 — Propor plano de implementação

Com base na comparação do Passo 3, propor um plano de implementação **antes de escrever qualquer código**. O plano deve:

- Listar as mudanças necessárias agrupadas por superfície (dashboard, agenda, link público, etc.)
- Indicar a ordem sugerida de execução e eventuais dependências entre mudanças (ex: tokens globais antes de componentes)
- Sinalizar o que é refatoração de código existente vs. criação do zero
- Estimar o impacto de cada grupo (baixo / médio / alto) em termos de risco para o que já está em produção

O plano deve ser apresentado para aprovação. **Nenhum código deve ser alterado neste passo.**

### Passo 5 — Espelhar o design no Paladino

Após aprovação do plano, implementar as mudanças conforme o que foi acordado, respeitando:

1. A stack do Paladino (Next.js App Router + shadcn/ui v4 + Tailwind v4)
2. Os limites invioláveis da Seção 3 (contratos com o backend)
3. A estrutura de rotas e componentes já existente (adaptar, não reescrever do zero quando possível)
4. Zero lógica de negócio no frontend — o painel é cliente da API

---

## 5. Restrições adicionais

- Não criar layouts distintos por tenant — a personalização é via tokens visuais (logo, cores, fonte), não layouts paralelos
- Não implementar features novas de negócio — o escopo desta tarefa é exclusivamente design; a Fase 1 atual foca no backend

---

## 6. Output esperado

1. **Relatório de auditoria** com o estado atual do frontend por área (Passo 1)
2. **Mapeamento do protótipo** com os padrões visuais de referência por área (Passo 2)
3. **Tabela de gaps** comparando estado atual × referência (Passo 3)
4. **Plano de implementação aprovado** com mudanças priorizadas e agrupadas (Passo 4)
5. **Código implementado** com o design espelhado nas áreas existentes (Passo 5)
6. **Sem quebras** nos contratos com o backend (autenticação, rotas, chamadas de API)

---

## 7. Referências de localização

| Artefato | Caminho |
|----------|---------|
| Frontend Paladino — painel | `painel/app/(dashboard)/` |
| Frontend Paladino — link público | `painel/app/book/[slug]/` (`page.tsx` + `BookingFlow.tsx`) |
| Protótipo de referência — painel | `barberflow-system/src/routes/` (áreas do painel) |
| Protótipo de referência — link público | `barberflow-system/src/routes/b.$slug/` (ou equivalente) |
| Tokens / design system | `painel/app/globals.css` |
| Theme provider | `painel/lib/theme.tsx` |
| API client | `painel/lib/api.ts` |
| Utilitários (`formatBRL`, `formatDateTime`) | `painel/lib/utils.ts` |
| Componentes shadcn/ui | `painel/components/ui/` |
| Wordmark Paladino | `painel/public/paladino-wordmark.png` |

---

*Este brief é derivado de `visao-produto-paladino.md` v23.0, `visao-estagio-0.md` e `CLAUDE.md`. Qualquer conflito de comportamento deve ser resolvido nesses documentos — não no código.*
