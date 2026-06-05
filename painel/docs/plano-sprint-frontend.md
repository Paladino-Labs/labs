# Plano de Execução — Sprint Frontend
**Versão:** 1.0 · **Data:** 2026-06-04 · **Gerado por:** Planner (sessão de análise)
**Baseado em:** `brief-frontend-sprint-adaptacao.md` v1.1

> **Escopo:** Exclusivamente `painel/`. Nenhuma alteração em `agendamento_engine/`.
> O pré-requisito `User.name` já está implementado (commit 6947399).

---

## Pré-condição confirmada: User.name já existe

O pré-requisito do brief **já foi executado** antes desta sessão de planejamento:
- `User.name` presente no ORM (`users.name VARCHAR(100) nullable`)
- `GET /auth/me` retorna `"name": user.name`
- `POST /auth/activate` aceita `name: Optional[str]`
- `PATCH /auth/profile` aceita `name: Optional[str]`
- `POST /users/invite` aceita `name: Optional[str]`

O executor não precisa tocar no backend.

---

## Passo 3 — Mapeamento REQ por REQ

| REQ | O que existe | O que falta | Esforço |
|-----|-------------|-------------|---------|
| **REQ-01** Painel sem OVERVIEW | `dashboard/page.tsx`: eyebrow exibe "Overview · [data]", KPI strip, "Próximos da casa" (hoje), "ver agenda →" → `/appointments`, botão "Novo Agendamento" | Remover "Overview · " do eyebrow; trocar link "ver agenda" de `/appointments` para `/agenda`; limitar lista a max 8 itens; adicionar botão "Registrar pagamento" nas quick actions | **Baixo** |
| **REQ-02** Agenda calendário default | `appointments/page.tsx`: toggle lista/calendário existe, default é lista (`useState("list")`) | Mudar default para `"calendar"`; criar rota `/agenda` (renomear pasta); atualizar todos os links de `/appointments` → `/agenda` | **Baixo** |
| **REQ-03** Sidebar reorganização | `Sidebar.tsx`: label "Navegação", items: Início, Agendamentos, Clientes, Serviços, Barbeiros, Produtos, Pagamentos, Integrações, Usuários, Configurações | Mudar "Navegação" → "MENU"; "Início" → "Painel"; remover: Agendamentos, Usuários, Integrações, Pagamentos; adicionar: Financeiro (`/financeiro`) | **Baixo** |
| **REQ-04** Header com User.name | `AuthContext.tsx`: não armazena `name`; `Sidebar.tsx` usa email parseado como displayName | Adicionar `name: string \| null` ao `AuthContext`; capturar do response de `/auth/me` na hidratação (já chamado); usar no Sidebar | **Baixo** |
| **REQ-05** Logo maior | `Sidebar.tsx`: `width={120}` `className="h-8 w-auto"` | Aumentar para `width={160}` `className="h-10 w-auto"` (ou valores aprovados visualmente) | **Baixo** |
| **REQ-06** Registro de pagamento | Não existe (`/financeiro/pagamentos/novo`) | Nova página: autocomplete cliente, seletor de agendamento opcional, valor, método (Dinheiro/PIX/Crédito/Débito), POST /payments + POST confirm-manual, exibir fee_warning | **Alto** |
| **REQ-07** Movimentações financeiras | Não existe (`/financeiro/movimentacoes`) | Nova página: lista paginada de `GET /financial/movements`, filtros conta/tipo/período | **Médio** |
| **REQ-08** Lista de pagamentos | `payments/page.tsx` existe em `/payments`; sem cliente, sem confirm-manual, sem filtro de método | Nova página em `/financeiro/pagamentos`; adicionar coluna cliente (requires `GET /customers` para lookup ou incluir no response); adicionar ação confirm-manual; filtros status/método | **Médio** |
| **REQ-09** Config > Taxas | `/settings/financial/page.tsx`: mostra só status Asaas (consume `/financial/settings`) | Nova página `/settings/taxas`: tabela das 8 políticas via `GET /financial/fee-policies`, edição inline por método via `PATCH /financial/fee-policies/{fee_source}` | **Médio** |
| **REQ-10** Config > Integrações | `/integrations/page.tsx`: só WhatsApp + Agendamento Online | Migrar para `/settings/integracoes`; adicionar seção Asaas (status + formulário CPF/birthDate → `PATCH /companies/me`); adicionar seção PagSeguro (formulário credenciais → `POST /integrations/credentials`) | **Médio** |
| **REQ-11** Config > Comunicação | Não existe | Nova página `/settings/comunicacao`: toggles email/WhatsApp via `PUT /communication/settings`, status do serviço | **Baixo** |
| **REQ-12** Config > Usuários | `/users/page.tsx` existe, funcional; formulário de convite sem campo `name` | Migrar para `/settings/usuarios` (mover arquivo + redirecionar `/users`); adicionar campo `name` no InviteModal | **Baixo** |
| **REQ-13** Convite/ativação com nome | Formulário de convite sem `name`; **não existe** página `/activate` | Adicionar `name` no InviteModal (REQ-12); criar `app/activate/page.tsx` com campos nome + senha + confirmação | **Médio** |
| **REQ-14** Profissional sem CPF na UI | `professionals/[id]/page.tsx`: seção CPF/CNPJ existe (lines 349–375, state `editCpfCnpj`, validação, save logic) | Remover campo CPF/CNPJ do formulário; remover state e funções relacionadas; NÃO alterar backend | **Baixo** |

---

## Passo 4 — Componentes reutilizáveis existentes

| Componente | Arquivo | Reutilizável para |
|-----------|---------|------------------|
| `Button` | `components/ui/button.tsx` | Todos os REQs com ações |
| `Input`, `Label` | `components/ui/input.tsx`, `label.tsx` | REQ-06, REQ-09, REQ-10, REQ-11, REQ-13 |
| `Card`, `CardContent`, `CardHeader`, `CardTitle` | `components/ui/card.tsx` | REQ-07, REQ-08, REQ-09, REQ-10, REQ-11 |
| `Dialog`, `DialogContent`, ... | `components/ui/dialog.tsx` | REQ-06 (modal opcional), REQ-13 |
| `Badge` | `components/ui/badge.tsx` | REQ-08 (status de pagamento) |
| `Table`, `TableRow`, ... | `components/ui/table.tsx` | REQ-07, REQ-08, REQ-09 |
| `Select`, `SelectItem`, ... | `components/ui/select.tsx` | REQ-06, REQ-07, REQ-08 |
| `Tabs`, `TabsList`, ... | `components/ui/tabs.tsx` | REQ-10 (WhatsApp / Asaas / PagSeguro) |
| `api` (client HTTP) | `lib/api.ts` | Todos os novos endpoints |
| `formatBRL`, `formatDateTime`, `cn` | `lib/utils.ts` | Todos |
| `useAuth` (role, userId, companyId) | `hooks/useAuth.ts` | RBAC visual em todos |
| `AgendaCalendar` | `components/AgendaCalendar.tsx` | REQ-02 (já usado em appointments) |
| `empty-state.tsx` | `components/empty-state.tsx` | REQ-07, REQ-08 (empty states) |
| `status-badge.tsx` | `components/status-badge.tsx` | REQ-08 |

**Componentes a criar (novos):**
- `CustomerAutocomplete` — REQ-06: input com busca de cliente (usado em `GET /customers`)
- `FeeWarningBanner` — REQ-06: banner de aviso de taxa não configurada (reutilizável também em REQ-08 se confirm-manual for adicionado ali)
- `ToggleSwitch` — REQ-10, REQ-11: toggle booleano (pattern já existe inline em `integrations/page.tsx` mas pode ser extraído)

---

## Passo 5 — Dependências entre REQs

```
REQ-03 (sidebar)
  ├── REQ-07 (Financeiro entra no menu)
  ├── REQ-08 (Financeiro entra no menu)
  ├── REQ-06 (Financeiro entra no menu)
  ├── REQ-09 (Configurações > Taxas)
  ├── REQ-10 (Configurações > Integrações)
  ├── REQ-11 (Configurações > Comunicação)
  └── REQ-12 (Configurações > Usuários)
        └── REQ-13 (nome no convite + página activate)

REQ-04 (AuthContext name)
  └── (independente, mas o Sidebar deve ser atualizado junto)

REQ-02 (rota /agenda)
  └── REQ-01 (link "ver agenda" precisa da rota /agenda)

REQ-05, REQ-14 — totalmente independentes
```

**Ordem global de execução recomendada:**

```
Bloco A: REQ-03 + REQ-04 + REQ-05 (sidebar base, auth name, logo)
Bloco B: REQ-02 + REQ-01 (rota /agenda + dashboard)
Bloco C: REQ-14 (CPF profissional — isolado)
Bloco D: REQ-08 + REQ-07 + REQ-06 (módulo financeiro)
Bloco E: REQ-09 + REQ-10 + REQ-11 + REQ-12 (configurações)
Bloco F: REQ-13 (convite com nome + página activate)
```

Blocos B, C e D podem ser executados em paralelo após o Bloco A.
Bloco F depende do Bloco E (REQ-12).

---

## Passo 6 — Gaps de endpoint

| Endpoint | Necessário para | Status | Observação |
|---------|----------------|--------|-----------|
| `GET /auth/me` → retorna `name` | REQ-04 | ✅ **EXISTE** | Já retorna `name` (commit 6947399) |
| `POST /auth/activate` com `name` | REQ-13 | ✅ **EXISTE** | `ActivateRequest.name: Optional[str]` |
| `PATCH /auth/profile` com `name` | REQ-04 | ✅ **EXISTE** | `PATCH /auth/profile` aceita `name` |
| `POST /users/invite` com `name` | REQ-12, REQ-13 | ✅ **EXISTE** | Schema tem `name: Optional[str]` |
| `GET /financial/movements` | REQ-07 | ✅ **EXISTE** | `/financial/movements` no financial_core router |
| `GET /financial/fee-policies` | REQ-09 | ✅ **EXISTE** | `/financial/fee-policies` no financial_core router |
| `PATCH /financial/fee-policies/{fee_source}` | REQ-09 | ✅ **EXISTE** | Retorna `FeePolicyResponse` |
| `PATCH /companies/me` com `owner_cpf_cnpj` + `owner_birth_date` | REQ-10 | ✅ **EXISTE** | `CompanyUpdate` já tem esses campos; chama `create_subaccount` |
| `POST /integrations/credentials` | REQ-10 | ✅ **EXISTE** (doc) | Confirmado no brief; executor verifica schema |
| `GET /communication/settings` | REQ-11 | ✅ **EXISTE** | Retorna `CommunicationSettingsResponse` |
| `PUT /communication/settings` | REQ-11 | ✅ **EXISTE** | **ATENÇÃO: é PUT, não PATCH** — ver Divergências |
| `POST /payments` | REQ-06 | ✅ **EXISTE** | `PaymentCreate`: `gross_amount`, `payment_method`, `customer_id?`, `appointment_id?`, `payment_submethod?` |
| `POST /payments/{id}/confirm-manual` | REQ-06, REQ-08 | ✅ **EXISTE** | Retorna `ConfirmManualResponse` com `fee_warning?` |
| `GET /customers` | REQ-06 | ✅ **EXISTE** (uso atual) | Já consumido em `appointments/new/page.tsx` |
| `GET /appointments?customer_id=` | REQ-06 | ✅ **EXISTE** (doc) | Filtro por customer_id |
| `GET /financial/accounts` | REQ-07 (filtro por conta) | ✅ **EXISTE** | Lista contas disponíveis |

**Nenhum gap de endpoint encontrado.** Todos os endpoints necessários para os 14 REQs existem no backend.

---

## Passo 7 — Plano de execução por bloco

---

### Bloco A — Fundação: Sidebar + Auth + Logo
**REQs incluídos:** REQ-03, REQ-04, REQ-05
**Estimativa:** 45–60 min

#### Arquivos a alterar

| Arquivo | O que muda |
|---------|-----------|
| `components/Sidebar.tsx` | Label "Navegação" → "MENU"; "Início" → "Painel"; remover 4 itens; adicionar Financeiro; usar `name` do auth; logo maior |
| `context/AuthContext.tsx` | Adicionar `name: string \| null` ao contexto; capturar do response de `/auth/me` na hidratação |
| `hooks/useAuth.ts` | Re-export do contexto — sem alteração (já re-exporta tudo) |

#### Arquivos a criar

Nenhum.

#### Componentes reutilizados

- `useAuth` já existente — expandido com `name`
- Padrão de imagem do logo já existe (`Image` do Next.js)

#### Ordem de implementação dentro do bloco

1. **AuthContext.tsx** — adicionar `name` ao contexto antes de alterar o Sidebar
2. **Sidebar.tsx** — usar `name` e aplicar todas as mudanças estruturais

#### Prompt de execução — Bloco A

```
BLOCO A — Sidebar, Auth Name, Logo

Você vai alterar dois arquivos: context/AuthContext.tsx e components/Sidebar.tsx.
Leia ambos antes de começar.

--- PARTE 1: AuthContext.tsx ---

Adicione `name: string | null` à interface AuthContextValue (após companyId).
Adicione `name: null` no valor default do createContext.
Adicione `const [name, setName] = useState<string | null>(null)` após companyId.
Inclua `name` no retorno de `extractUserData` — NÃO está no JWT payload,
então NÃO extraia do payload. Deixe em branco por ora.

Na função `applyUserData(t: string, payload: JwtPayload)`: NÃO altere — ela
continua usando o payload do JWT que não tem name.

No bloco de hidratação (useEffect que chama fetch `/auth/me`, linhas ~116-142):
  - O response `data` é lido mas descartado: `applyUserData(stored, payload)` usa payload.
  - Altere para também capturar `name` de `data`:
    ```
    applyUserData(stored, payload)
    if (data?.name) setName(data.name)   // captura name do /auth/me
    ```
  - Faça o mesmo no bloco `.catch` (servidor indisponível — deixa name=null).

Na função `logout`: adicione `setName(null)`.

No AuthContext.Provider value: adicione `name`.

Exporte `name` na interface e no contexto.

--- PARTE 2: Sidebar.tsx ---

Arquivo: components/Sidebar.tsx

1. Importar `name` do useAuth:
   Altere: `const { email, role, logout } = useAuth()`
   Para:   `const { email, role, logout, name } = useAuth()`

2. Alterar NAV_LINKS — substituir o array inteiro:
   - REMOVER: Agendamentos (/appointments), Pagamentos (/payments),
               Integrações (/integrations), Usuários (/users)
   - MANTER: Clientes, Serviços, Barbeiros (Profissionais), Produtos,
              Configurações
   - RENOMEAR: href="/dashboard" label="Início" → label="Painel"
   - ADICIONAR após Barbeiros:
     { href: "/financeiro", label: "Financeiro", icon: Wallet, roles: null }
   - Importe Wallet de lucide-react (junto com os outros imports de ícones)
   - Remova imports de ícones que não são mais usados:
     CalendarDays, CreditCard, Link2, UserCog

3. Alterar label da seção nav (linha com "Navegação"):
   "Navegação" → "MENU"

4. Alterar displayName no SidebarContent:
   Linha atual: `const displayName = email?.split("@")[0]?.replace(/[._]/g, " ") ?? "Usuário"`
   Nova lógica:
   ```tsx
   const displayName = name
     ?? email?.split("@")[0]?.replace(/[._]/g, " ")
     ?? "Usuário"
   ```
   (use `name` do prop; adicione `name: string | null` nos props de SidebarContent)

5. Tamanho da logo:
   Altere width={120} → width={160}
   Altere className="h-8 w-auto" → className="h-10 w-auto"

--- VERIFICAÇÃO ---
- O sidebar deve mostrar: Painel, Clientes, Serviços, Barbeiros, Produtos,
  Financeiro, Configurações
- A seção deve ter label "MENU" (não "Navegação" nem "NAVIGATION")
- O nome/email no footer deve usar User.name se disponível
- A logo deve estar visivelmente maior
- Não há nenhuma alteração em agendamento_engine/
```

---

### Bloco B — Painel + Agenda
**REQs incluídos:** REQ-01, REQ-02
**Estimativa:** 45–60 min
**Pré-requisito:** Bloco A (para que /agenda seja a rota correta)

#### Arquivos a alterar

| Arquivo | O que muda |
|---------|-----------|
| `app/(dashboard)/appointments/page.tsx` | Mover para `/agenda/page.tsx`; mudar default viewMode para "calendar" |
| `app/(dashboard)/dashboard/page.tsx` | Remover "Overview · "; trocar link "/appointments" → "/agenda"; limitar lista a 8; adicionar botão "Registrar pagamento" |

#### Arquivos a criar

| Arquivo | O que é |
|---------|---------|
| `app/(dashboard)/agenda/page.tsx` | Conteúdo atual de `/appointments/page.tsx` com `viewMode = "calendar"` como default |
| `app/(dashboard)/appointments/page.tsx` (redirect) | Redirect simples para `/agenda` (opcional — manter URL antiga funcionando) |

**Nota:** A pasta `appointments/` deve ser mantida por causa de `appointments/new/page.tsx`. Apenas o `page.tsx` raiz de appointments muda.

#### Ordem de implementação

1. Criar `app/(dashboard)/agenda/` e copiar/mover `appointments/page.tsx`
2. Alterar `viewMode` default no novo `agenda/page.tsx`
3. Alterar `dashboard/page.tsx`
4. Adicionar redirect em `appointments/page.tsx` (opcional)

#### Prompt de execução — Bloco B

```
BLOCO B — Painel e Agenda

Você vai alterar/criar 3 arquivos. Leia ambos antes de começar:
- app/(dashboard)/dashboard/page.tsx
- app/(dashboard)/appointments/page.tsx

--- PARTE 1: Criar app/(dashboard)/agenda/page.tsx ---

Crie a pasta app/(dashboard)/agenda/ e um arquivo page.tsx.
Copie TODO o conteúdo de app/(dashboard)/appointments/page.tsx para o novo arquivo.

No novo arquivo (agenda/page.tsx), faça UMA mudança:
  Linha: `const [viewMode, setViewMode] = useState<"list" | "calendar">("list")`
  Nova:  `const [viewMode, setViewMode] = useState<"list" | "calendar">("calendar")`

Nenhuma outra alteração no arquivo de agenda.

--- PARTE 2: app/(dashboard)/appointments/page.tsx ---

Substitua TODO o conteúdo por um redirect simples:
```tsx
import { redirect } from "next/navigation"
export default function AppointmentsRedirect() {
  redirect("/agenda")
}
```
Isso garante que qualquer link antigo /appointments continua funcionando.
A pasta appointments/new/ NÃO é afetada (é subdiretório).

--- PARTE 3: app/(dashboard)/dashboard/page.tsx ---

Leia o arquivo. Faça as seguintes alterações:

3a. Remover "Overview · " do eyebrow (linha com "Overview ·"):
    Localize a string que contém "Overview ·" seguido da data.
    Altere para exibir APENAS a data:
    De: `Overview · {format(new Date(), "EEEE, d 'de' MMMM", { locale: ptBR })}`
    Para: `{format(new Date(), "EEEE, d 'de' MMMM 'de' yyyy", { locale: ptBR })}`
    Mantenha todo o container (divs, classes) — apenas remova "Overview · ".

3b. Atualizar link "ver agenda →":
    Localize `href="/appointments"` dentro do componente "Próximos da casa".
    Altere para `href="/agenda"`.
    Mantenha o texto "ver agenda →".

3c. Limitar a lista de próximos a 8 itens:
    Na derivação `upcomingToday`, adicione .slice(0, 8) no final:
    `upcomingToday.filter(...).sort(...).slice(0, 8)`
    (ou adicione slice na derivação existente)

3d. Adicionar botão "Registrar pagamento" nas quick actions:
    Localize o bloco da div com o Button "Novo Agendamento" (próximo ao final do JSX).
    Adicione um segundo Button ao lado:
    ```tsx
    <div className="flex justify-end gap-3">
      <Button variant="outline" onClick={() => router.push("/financeiro/pagamentos/novo")}>
        + Registrar pagamento
      </Button>
      <Button onClick={() => router.push("/appointments/new")}>
        + Novo Agendamento
      </Button>
    </div>
    ```

--- VERIFICAÇÃO ---
- Acessar /agenda deve abrir com o calendário visível (não a lista)
- Acessar /appointments deve redirecionar para /agenda
- No dashboard, "ver agenda →" deve ir para /agenda
- O eyebrow do dashboard não deve mais ter "Overview ·"
- A lista de "Próximos" não deve ter mais de 8 itens
- O botão "Registrar pagamento" deve aparecer nas quick actions
- appointments/new continua funcional (não é afetado)
```

---

### Bloco C — Profissional: remover CPF
**REQs incluídos:** REQ-14
**Estimativa:** 15 min
**Pré-requisito:** Nenhum (totalmente independente)

#### Arquivos a alterar

| Arquivo | O que muda |
|---------|-----------|
| `app/(dashboard)/professionals/[id]/page.tsx` | Remover estado, validação e campo CPF/CNPJ |

#### Arquivos a criar

Nenhum.

#### Prompt de execução — Bloco C

```
BLOCO C — Remover CPF/CNPJ do formulário do profissional

Leia app/(dashboard)/professionals/[id]/page.tsx antes de começar.

IMPORTANTE: NÃO alterar nada no backend (agendamento_engine/).
NÃO fazer DROP COLUMN. O campo permanece no banco.

Remova as seguintes partes do arquivo:

1. Estado: `const [editCpfCnpj, setEditCpfCnpj] = useState("")`
2. Estado: `const [cpfCnpjError, setCpfCnpjError] = useState<string | null>(null)`
3. Função inteira `validateCpfCnpjClient(raw: string)` (linhas ~140-172)
4. Função inteira `handleCpfCnpjChange(raw: string)` (linhas ~173-176)
5. No `fetchAll`: a linha `setEditCpfCnpj("")  // nunca pré-preencher com valor criptografado`
6. Em `handleSaveInfo`:
   - Remover: `if (cpfCnpjError) return`
   - Remover: as duas linhas que adicionam `cpf_cnpj` ao body:
     `const digits = editCpfCnpj.replace(/\D/g, "")`
     `if (digits.length > 0) body.cpf_cnpj = editCpfCnpj`
   - Remover da linha do Button disabled:
     `|| (editCpfCnpj.replace(/\D/g,"").length === 0) || !!cpfCnpjError`
     mantendo apenas: `disabled={savingInfo || (editName.trim() === prof.name && editSpecialty === (prof.specialty ?? ""))}`
7. No JSX, remover a seção inteira "CPF / CNPJ":
   Da `<div className="space-y-1">` com `<Label>CPF / CNPJ</Label>` até o fechamento
   do div pai (inclui o texto sobre mascaramento).

Após remover, o formulário de informações deve ter apenas:
- Campo Nome
- Campo Especialidade
- Botão Salvar informações
- Toggle Ativar/Desativar

--- VERIFICAÇÃO ---
- O formulário do profissional não deve ter nenhum campo CPF/CNPJ
- O botão Salvar deve habilitar/desabilitar apenas baseado em nome e especialidade
- Não há erros de TypeScript (todas as referências a editCpfCnpj/cpfCnpjError removidas)
```

---

### Bloco D — Módulo Financeiro
**REQs incluídos:** REQ-08, REQ-07, REQ-06
**Estimativa:** 3–4 horas
**Pré-requisito:** Bloco A (rota /financeiro no sidebar)

#### Arquivos a criar

| Arquivo | O que é |
|---------|---------|
| `app/(dashboard)/financeiro/page.tsx` | Hub da seção financeiro (cards de navegação) |
| `app/(dashboard)/financeiro/pagamentos/page.tsx` | Lista de pagamentos (REQ-08) |
| `app/(dashboard)/financeiro/pagamentos/novo/page.tsx` | Formulário de registro de pagamento (REQ-06) |
| `app/(dashboard)/financeiro/movimentacoes/page.tsx` | Lista de movimentações (REQ-07) |
| `components/FeeWarningBanner.tsx` | Componente de aviso de taxa não configurada |
| `components/CustomerAutocomplete.tsx` | Input com busca de cliente por nome |

#### Componentes reutilizados

- `Table`, `Badge`, `Card`, `Button`, `Select`, `Input`, `Label`, `Dialog`
- `formatBRL`, `formatDateTime` de `lib/utils.ts`
- `api` de `lib/api.ts`
- `useAuth` para RBAC visual

#### Ordem de implementação dentro do bloco

1. `financeiro/page.tsx` (hub simples — 10 min)
2. `financeiro/pagamentos/page.tsx` (REQ-08 — lista melhorada)
3. `financeiro/movimentacoes/page.tsx` (REQ-07)
4. `CustomerAutocomplete.tsx` (componente para REQ-06)
5. `FeeWarningBanner.tsx` (componente para REQ-06)
6. `financeiro/pagamentos/novo/page.tsx` (REQ-06 — mais complexo)

#### Prompt de execução — Bloco D (parte 1: estrutura + REQ-08 + REQ-07)

```
BLOCO D — Módulo Financeiro (Parte 1: Hub + Lista de Pagamentos + Movimentações)

Crie os seguintes arquivos. NÃO altere nenhum arquivo existente nesta parte.

Padrões obrigatórios de código:
- Imports de `lib/api.ts` sempre — nunca fetch raw
- Tokens semânticos: bg-card, border-border, text-muted-foreground, bg-primary
  nunca hardcode (bg-white, text-gray-*)
- formatBRL() de lib/utils.ts para valores monetários
- formatDateTime() de lib/utils.ts para datas
- Todos os arquivos com "use client" no topo

--- ARQUIVO 1: app/(dashboard)/financeiro/page.tsx ---

Hub da seção financeiro. Segue o mesmo padrão de app/(dashboard)/settings/page.tsx
(cards de navegação). Cards para:
- Pagamentos (href: /financeiro/pagamentos, ícone: CreditCard)
- Movimentações (href: /financeiro/movimentacoes, ícone: ArrowLeftRight)
- Registrar pagamento (href: /financeiro/pagamentos/novo, ícone: Plus)

Título da página: "Financeiro" (font-display text-3xl)
Subtítulo: "Gerencie pagamentos e movimentações financeiras"

--- ARQUIVO 2: app/(dashboard)/financeiro/pagamentos/page.tsx (REQ-08) ---

Lista de pagamentos melhorada. Referência de estrutura: app/(dashboard)/payments/page.tsx
(leia-o antes de criar).

DIFERENÇAS em relação ao arquivo original:
1. Buscar clientes para lookup de nome:
   - Fazer `GET /customers` em paralelo com `GET /payments`
   - Criar mapa `customerMap: Map<string, string>` de customer_id → name
   - Exibir nome do cliente na coluna em vez do customer_id

2. Adicionar filtros: status (select), método (select), período (date inputs existentes)

3. Adicionar ação "Confirmar" para pagamentos PENDING + provider manual:
   - Ícone/botão pequeno na linha da tabela
   - Ao clicar: `POST /payments/{id}/confirm-manual`
   - Verificar role antes: só OWNER/ADMIN veem o botão (use useAuth().role)
   - Após confirmação: exibir FeeWarningBanner se fee_warning presente no response
   - Recarregar lista após confirmação

4. Colunas: Data | Cliente | Método | Valor líquido | Status | Ações

5. Rota: /financeiro/pagamentos (não /payments)

6. Adicionar link "+ Registrar pagamento" no canto superior direito da página
   → redireciona para /financeiro/pagamentos/novo

Schema do endpoint GET /payments:
```
payment_id: string
customer_id: string | null
appointment_id: string | null
gross_catalog_amount: number
net_charged_amount: number
provider_fee: number
payment_method: string
provider: string
status: string  — PENDING | CONFIRMED | FAILED | CANCELLED | REFUNDED
created_at: string (ISO)
paid_at: string | null
refunded_at: string | null
```

Schema do response POST /payments/{id}/confirm-manual (ConfirmManualResponse):
```
payment: { ...campos do Payment... }
fee_warning: {
  fee_source: string
  message: string
} | null
```

--- ARQUIVO 3: app/(dashboard)/financeiro/movimentacoes/page.tsx (REQ-07) ---

Lista paginada de movimentações. NÃO existe referência existente — criar do zero.

Endpoint: GET /financial/movements
Parâmetros de query: account_id (opcional), movement_type (opcional), date_from, date_to

Schema de MovementResponse:
```
id: UUID
account_id: UUID
movement_type: string  — INFLOW | OUTFLOW
amount: Decimal
description: string | null
source_type: string
source_id: UUID
created_at: string (ISO)
```

Também buscar GET /financial/accounts para exibir nome da conta em vez de UUID.

UI:
- Título "Movimentações" (font-display text-3xl)
- Filtros no topo: select de conta, select de tipo (Entrada/Saída/Todos), date de/até
- Tabela: Data | Conta | Tipo | Descrição | Valor
  - INFLOW em verde (text-success ou similar), OUTFLOW em vermelho
  - Valor sempre positivo; tipo indicado pela cor/badge
- Empty state: "Nenhuma movimentação encontrada para os filtros selecionados."
- Loading state: "Carregando movimentações..."
- Erro state: "Não foi possível carregar as movimentações."

--- VERIFICAÇÃO ---
- /financeiro mostra os três cards de navegação
- /financeiro/pagamentos lista pagamentos com nome do cliente quando disponível
- Pagamentos PENDING+manual mostram botão "Confirmar" para OWNER/ADMIN
- /financeiro/movimentacoes lista movimentações com filtros funcionais
- Nenhum dado mockado — todos os dados vêm dos endpoints reais
```

#### Prompt de execução — Bloco D (parte 2: REQ-06 — Registro de Pagamento)

```
BLOCO D — Módulo Financeiro (Parte 2: Formulário de Registro de Pagamento)

Crie dois componentes e a página de registro.
Leia antes: app/(dashboard)/financeiro/pagamentos/page.tsx (criado na parte 1)

--- COMPONENTE 1: components/CustomerAutocomplete.tsx ---

Input com busca de cliente por nome. Props:
```tsx
interface Props {
  value: string | null          // customer_id selecionado
  onChange: (id: string, name: string) => void
  placeholder?: string
}
```
Comportamento:
- Input de texto controlado
- Ao digitar 2+ chars: busca GET /customers (usa ?search=... se disponível, ou filtra client-side)
- Exibe dropdown com resultados (nome + telefone)
- Ao selecionar: chama onChange(id, name) e exibe o nome no input
- Ícone X para limpar
- Usa tokens do design system, não cores hardcoded
- Se /customers retorna array simples (sem paginação), buscar uma vez e filtrar client-side

Nota: GET /customers já está em uso em appointments/new/page.tsx — consulte esse arquivo
para ver como a API é chamada.

--- COMPONENTE 2: components/FeeWarningBanner.tsx ---

Banner/aviso de taxa não configurada. Props:
```tsx
interface Props {
  feeSource: string            // "CASH" | "PIX" | "MAQUININHA_CREDIT" | etc.
  message?: string             // mensagem do backend
  onDismiss: () => void
  onConfigureClick: () => void // navega para /settings/taxas
}
```
Visual: banner amarelo/âmbar (border-warning ou bg-amber-50) com:
- Texto: "Nenhuma taxa configurada para [label do método]. [Configurar agora →]"
- O link "Configurar agora" chama onConfigureClick (router.push("/settings/taxas"))
- Botão X para fechar (chama onDismiss)
- Use tokens: border-yellow-200 bg-yellow-50 text-yellow-800 (ou equivalente semântico)

Mapeamento fee_source → label legível:
```
CASH              → Dinheiro
PIX               → PIX online
MAQUININHA_PIX    → PIX na maquininha
MAQUININHA_CREDIT → Cartão de crédito
MAQUININHA_DEBIT  → Cartão de débito
CARD_CREDIT       → Crédito online
CARD_DEBIT        → Débito online
BOLETO            → Boleto
```

--- ARQUIVO: app/(dashboard)/financeiro/pagamentos/novo/page.tsx (REQ-06) ---

Formulário de registro de pagamento manual.

FLUXO DA UI:
1. Selecionar cliente (CustomerAutocomplete — obrigatório)
2. Selecionar agendamento (opcional — após cliente selecionado, busca GET /appointments?customer_id={id})
3. Informar valor (input numérico, formatado em BRL)
4. Selecionar método de pagamento (4 opções como cards clicáveis ou radio buttons):
   - 💵 Dinheiro
   - ◈ PIX (maquininha)
   - 💳 Crédito
   - 💳 Débito
5. Botão "Confirmar pagamento" → executa fluxo de dois passos

MAPEAMENTO DE MÉTODO → API:
```
Dinheiro  → payment_method: "CASH"
PIX       → payment_method: "PIX"
Crédito   → payment_method: "MAQUININHA", payment_submethod: "CREDIT"
Débito    → payment_method: "MAQUININHA", payment_submethod: "DEBIT"
```

FLUXO DE API (2 passos):
1. `POST /payments` com body:
   ```json
   {
     "customer_id": "<uuid>",
     "appointment_id": "<uuid ou null>",
     "gross_amount": <number>,
     "payment_method": "<CASH|PIX|MAQUININHA>",
     "payment_submethod": "<CREDIT|DEBIT|null>"
   }
   ```
   Response: PaymentResponse com `payment_id`

2. `POST /payments/{payment_id}/confirm-manual`
   Response: `{ payment: {...}, fee_warning: { fee_source, message } | null }`

ESTADOS DA UI:
- Formulário: estado inicial
- Loading: "Registrando pagamento..."
- Sucesso: exibir card de confirmação com:
  - "Pagamento confirmado ✓"
  - Valor líquido (net_charged_amount)
  - Taxa aplicada (provider_fee — formatar como BRL)
  - Método
  - Se fee_warning: exibir FeeWarningBanner abaixo do card de sucesso
  - Botão "Novo pagamento" (limpa form) e "Ver lista" (→ /financeiro/pagamentos)
- Erro: exibir mensagem do backend em texto vermelho

RBAC:
- Esta página deve ser acessível apenas para OWNER e ADMIN
- Se role for OPERATOR ou PROFESSIONAL: exibir mensagem "Acesso restrito"
  ou redirecionar para /financeiro/pagamentos
- Verificar via useAuth().role

NAVEGAÇÃO:
- Link "← Voltar" → /financeiro/pagamentos
- Título: "Registrar Pagamento" (font-display text-3xl)

--- VERIFICAÇÃO ---
- CustomerAutocomplete filtra clientes ao digitar
- Seleção de método está clara (visual de selecionado vs não-selecionado)
- POST /payments é chamado antes do confirm-manual
- fee_warning exibe FeeWarningBanner com link para /settings/taxas
- OPERATOR/PROFESSIONAL não conseguem acessar a página
- Sucesso mostra valor líquido e taxa aplicada
```

---

### Bloco E — Configurações expandidas
**REQs incluídos:** REQ-09, REQ-10, REQ-11, REQ-12
**Estimativa:** 3–4 horas
**Pré-requisito:** Bloco A (sidebar deve apontar para /settings)

#### Arquivos a alterar

| Arquivo | O que muda |
|---------|-----------|
| `app/(dashboard)/settings/page.tsx` | Adicionar 4 cards novos (Taxas, Integrações, Comunicação, Usuários) |

#### Arquivos a criar

| Arquivo | O que é |
|---------|---------|
| `app/(dashboard)/settings/taxas/page.tsx` | Tabela de 8 políticas de taxa MDR (REQ-09) |
| `app/(dashboard)/settings/integracoes/page.tsx` | WhatsApp + Asaas + PagSeguro (REQ-10) |
| `app/(dashboard)/settings/comunicacao/page.tsx` | Toggles de canal de comunicação (REQ-11) |
| `app/(dashboard)/settings/usuarios/page.tsx` | Migração da lista de usuários + convite (REQ-12) |
| `app/(dashboard)/users/page.tsx` (redirect) | Redirect simples para /settings/usuarios |

#### Prompt de execução — Bloco E (parte 1: Hub + REQ-09 + REQ-11)

```
BLOCO E — Configurações Expandidas (Parte 1: Hub + Taxas + Comunicação)

Leia antes:
- app/(dashboard)/settings/page.tsx
- app/(dashboard)/settings/financial/page.tsx

Padrões obrigatórios: mesmos do Bloco D.

CORREÇÃO OBRIGATÓRIA ANTES DE QUALQUER OUTRA COISA — api.ts:
Leia lib/api.ts. Localize o objeto `api` (ou similar) que expõe os
métodos HTTP (get, post, patch, delete).
Adicione o método `put` ao mesmo objeto, seguindo o mesmo padrão dos
outros métodos:

```ts
put: <T>(path: string, body: unknown) =>
  apiFetch<T>(path, { method: "PUT", body: JSON.stringify(body) }),
```

Sem esse método, o REQ-11 (Comunicação) retornará 405 Method Not Allowed
ao tentar PATCH /communication/settings — o endpoint real aceita apenas PUT.
Commitar este fix antes de criar qualquer página de configurações.

RBAC: páginas de Taxas e Comunicação devem verificar role OWNER/ADMIN
      via useAuth().role; se OPERATOR/PROFESSIONAL, exibir "Acesso restrito".

--- PARTE 1: Expandir app/(dashboard)/settings/page.tsx ---

Adicione 4 novos itens ao array `sections`, mantendo os 2 existentes:

```tsx
{
  href: "/settings/usuarios",
  icon: UserCog,           // importar de lucide-react
  title: "Usuários",
  description: "Gerenciar membros da equipe e convites",
},
{
  href: "/settings/integracoes",
  icon: Link2,             // já importado
  title: "Integrações",
  description: "WhatsApp, Asaas e gateways de pagamento",
},
{
  href: "/settings/comunicacao",
  icon: MessageSquare,     // importar de lucide-react
  title: "Comunicação",
  description: "Configurações de email e WhatsApp",
},
{
  href: "/settings/taxas",
  icon: Percent,           // importar de lucide-react
  title: "Taxas MDR",
  description: "Políticas de taxa por método de pagamento",
},
```

Importe os ícones necessários de lucide-react.
Mantenha os cards existentes (Perfil da empresa, Segurança).
NÃO remova o link /settings/financial — apenas adicione os novos.

--- PARTE 2: app/(dashboard)/settings/taxas/page.tsx (REQ-09) ---

Página de gestão de taxas MDR. Acesso: OWNER/ADMIN apenas.

Endpoint GET: `GET /financial/fee-policies`
Endpoint PATCH: `PATCH /financial/fee-policies/{fee_source}`

Schema FeePolicyResponse:
```
fee_source: string
fee_percentage: number | null  (null = não configurado → exibir aviso)
fee_flat: number
is_active: boolean
```

Mapeamento fee_source → nome legível e editabilidade:
```
CASH              → "Dinheiro"           → NÃO editável (sempre 0%)
PIX               → "PIX online (Asaas)" → editável
MAQUININHA_PIX    → "PIX na maquininha"  → editável
MAQUININHA_CREDIT → "Cartão de crédito"  → editável
MAQUININHA_DEBIT  → "Cartão de débito"   → editável
CARD_CREDIT       → "Crédito online"     → editável
CARD_DEBIT        → "Débito online"      → editável
BOLETO            → "Boleto"             → editável
```

UI:
- Título "Taxas MDR" (font-display text-3xl)
- Descrição: "Configure as taxas de processamento por método de pagamento."
- Tabela com colunas: Método | Taxa (%) | Fixa (R$) | Ações
- Para cada linha editável: input numérico inline (step=0.01, min=0, max=100)
  + botão "Salvar" por linha (PATCH individual)
- Para CASH: exibir "0%" em texto cinza com "(sem taxa)" — input desabilitado
- Se fee_percentage é null: exibir "—" em texto âmbar com badge "Não configurado"
  e aviso no tooltip/texto pequeno: "Taxa não configurada. Pagamentos com este
  método não terão taxa automática calculada."
- Feedback de save: "Salvo ✓" inline por linha (exibe 2s, depois some)
- Erro de save: exibir inline em vermelho

--- PARTE 3: app/(dashboard)/settings/comunicacao/page.tsx (REQ-11) ---

Página de configurações de comunicação. Acesso: OWNER/ADMIN.

Endpoint GET: `GET /communication/settings`
Endpoint PUT: `PUT /communication/settings`  ← ATENÇÃO: é PUT, não PATCH

Schema CommunicationSettingsResponse:
```
whatsapp_enabled: boolean
email_enabled: boolean
(pode ter outros campos — ignorar os extras)
```

Schema CommunicationSettingsUpdate (body do PUT):
```
whatsapp_enabled?: boolean
email_enabled?: boolean
```

UI:
- Título "Comunicação" (font-display text-3xl)
- Card "Canais de comunicação" com dois toggles:
  1. Toggle "WhatsApp habilitado" — PUT {whatsapp_enabled: !atual}
  2. Toggle "Email habilitado" — PUT {email_enabled: !atual}
  
- Use o padrão de toggle inline já existente em integrations/page.tsx:
  ```tsx
  <button
    onClick={handleToggle}
    className={`relative inline-flex h-6 w-11 items-center rounded-full
      transition-colors ${enabled ? "bg-primary" : "bg-muted"}`}
  >
    <span className={`inline-block h-4 w-4 transform rounded-full bg-white
      shadow transition-transform ${enabled ? "translate-x-6" : "translate-x-1"}`} />
  </button>
  ```

- Quando email desabilitado: exibir aviso abaixo do toggle:
  "⚠ Recuperação de senha e convites não serão enviados por email."
  (text-xs text-muted-foreground com ícone AlertTriangle)

- Loading/error states obrigatórios.

--- VERIFICAÇÃO ---
- /settings mostra 6 cards (Perfil, Segurança, Usuários, Integrações, Comunicação, Taxas)
- /settings/taxas lista 8 métodos com edição inline (CASH não editável)
- /settings/comunicacao tem toggles funcionais via PUT (não PATCH)
- OPERATOR/PROFESSIONAL veem "Acesso restrito" nas páginas de Taxas e Comunicação
```

#### Prompt de execução — Bloco E (parte 2: REQ-10 + REQ-12)

```
BLOCO E — Configurações Expandidas (Parte 2: Integrações + Usuários)

Leia antes:
- app/(dashboard)/integrations/page.tsx (vai ser migrado/expandido)
- app/(dashboard)/users/page.tsx (vai ser migrado)

--- PARTE 1: app/(dashboard)/settings/integracoes/page.tsx (REQ-10) ---

Migração e expansão da página de integrações.
O conteúdo existente de /integrations (WhatsApp + Agendamento Online) deve ser
COPIADO e mantido intacto. Adicione duas novas seções:

SEÇÃO NOVA: Asaas
Busca do status: `GET /financial/settings` (já usado em settings/financial/page.tsx)
Campos relevantes do response: external_account_id, external_account_status

Sub-estados e UI:
a) Se external_account_id existe e status = "active":
   Card verde: "Subconta Asaas ativa" — sem formulário

b) Se external_account_id existe e status ≠ "active":
   Card amarelo: "Subconta em análise/suspensa" — exibir status

c) Se external_account_id é null:
   Card neutro: "Subconta Asaas não configurada"
   + Formulário para completar dados:
     - Campo "CPF ou CNPJ do responsável" (input texto, apenas dígitos)
     - Campo "Data de nascimento do responsável" (input date, formato YYYY-MM-DD)
     - Botão "Configurar subconta Asaas"
     - Ao submeter: `PATCH /companies/me` com:
       { "owner_cpf_cnpj": "<apenas dígitos>", "owner_birth_date": "<YYYY-MM-DD>" }
     - Sucesso: recarregar status
     - Erro: exibir mensagem do backend

SEÇÃO NOVA: PagSeguro
Estado: sempre "Aguardando validação"
UI:
- Card com ícone de informação
- Título: "PagSeguro"
- Status badge: "Sandbox pendente" (variant secondary)
- Texto: "Integração com terminais PagSeguro em validação.
  Configure as credenciais abaixo para preparar o ambiente."
- Formulário de credenciais (sempre visível):
  - Input "Client ID" (text)
  - Input "Client Secret" (password, com toggle mostrar/ocultar)
  - Botão "Salvar credenciais"
  - Ao submeter: `POST /integrations/credentials` com:
    ```json
    {
      "provider": "PAGSEGURO",
      "client_id": "<valor>",
      "client_secret": "<valor>"
    }
    ```
    Verificar o schema exato consultando o arquivo do router de integrações:
    agendamento_engine/app/modules/integrations/router.py
  - Aviso abaixo do formulário: text-xs text-muted-foreground:
    "Terminal físico aguarda confirmação de endpoint pela equipe PagBank.
     As credenciais serão usadas quando o sandbox for validado."

Organização da página:
- Usar Tabs (import de components/ui/tabs.tsx) ou seções com h2:
  Aba 1: WhatsApp + Agendamento Online (conteúdo atual de integrations/page.tsx)
  Aba 2: Asaas
  Aba 3: PagSeguro

Copie TODA a lógica de integrations/page.tsx para a aba WhatsApp.
Depois de criar esta página, adicione redirect em app/(dashboard)/integrations/page.tsx:
```tsx
import { redirect } from "next/navigation"
export default function IntegrationsRedirect() { redirect("/settings/integracoes") }
```

--- PARTE 2: app/(dashboard)/settings/usuarios/page.tsx (REQ-12) ---

Migração de /users para /settings/usuarios COM adição do campo `name` no convite.

Copie TODO o conteúdo de app/(dashboard)/users/page.tsx para o novo arquivo.

Depois, faça as seguintes alterações no arquivo COPIADO:

1. No InviteModal, adicionar campo `name`:
   - Adicionar `const [name, setName] = useState("")` ao estado
   - Adicionar campo no formulário (ANTES do campo de papel):
     ```tsx
     <div className="space-y-1.5">
       <Label htmlFor="invite-name">Nome (opcional)</Label>
       <Input
         id="invite-name"
         type="text"
         value={name}
         onChange={(e) => setName(e.target.value)}
         placeholder="Ex: João Silva"
       />
     </div>
     ```
   - Alterar o body do POST /users/invite:
     De: `await api.post("/users/invite", { email, role })`
     Para: `await api.post("/users/invite", { email, role, ...(name ? { name } : {}) })`

2. Alterar o título da página de "Usuários" (mantém o mesmo — sem mudança necessária)

3. Redirecionar /users para /settings/usuarios:
   Em app/(dashboard)/users/page.tsx, substituir tudo por:
   ```tsx
   import { redirect } from "next/navigation"
   export default function UsersRedirect() { redirect("/settings/usuarios") }
   ```

--- VERIFICAÇÃO ---
- /settings/integracoes tem 3 abas: WhatsApp, Asaas, PagSeguro
- Aba WhatsApp funciona exatamente como /integrations funcionava
- Aba Asaas mostra formulário quando external_account_id é null
- /integrations redireciona para /settings/integracoes
- /settings/usuarios tem o formulário de convite com campo nome
- Campo nome é opcional (convite funciona sem ele)
- /users redireciona para /settings/usuarios
```

---

### Bloco F — Convite e ativação com nome
**REQs incluídos:** REQ-13
**Estimativa:** 45–60 min
**Pré-requisito:** Bloco E (REQ-12 — settings/usuarios com invite form)

#### Arquivos a criar

| Arquivo | O que é |
|---------|---------|
| `app/activate/page.tsx` | Tela de ativação de conta via token de convite |

#### Arquivos a alterar

Nenhum (o campo `name` no InviteModal já foi adicionado no Bloco E).

#### Prompt de execução — Bloco F

```
BLOCO F — Página de Ativação de Conta

Leia antes: app/reset-password/page.tsx (padrão de formulário de token)

Crie app/activate/page.tsx — página fora do (dashboard), não precisa de auth.
Segue o mesmo padrão de /reset-password: Suspense wrapper + conteúdo interno.

CONTEXTO:
- O usuário recebe email com link: /activate?token=<UUID>
- A página coleta: nome (opcional), senha, confirmação de senha
- Chama POST /auth/activate com { token, password, password_confirm, name? }
- Retorna { access_token, token_type } — faz login automático após ativação

ENDPOINT: POST /auth/activate
Body:
```json
{
  "token": "<UUID do convite>",
  "password": "<nova senha>",
  "password_confirm": "<confirmação>",
  "name": "<nome opcional>"
}
```
Response: `{ access_token: string, token_type: "bearer" }`
Erros: 400 (token inválido/expirado), 422 (validação)

REGRAS DE SENHA (mesmas de reset-password):
- Mínimo 8 caracteres
- Ao menos 1 letra maiúscula
- Ao menos 1 número

FUNÇÃO validatePassword já existe em reset-password/page.tsx — copie-a.

UI (dentro de ActivateContent — com Suspense wrapper como reset-password):

1. Ler `token` de searchParams.get("token")
2. Se token ausente: exibir "Link de convite inválido." + link "← Voltar ao login"

3. Formulário de ativação:
   - Título: "Criar sua conta" (font-display text-3xl)
   - Subtítulo: "Você foi convidado. Configure sua senha para começar."
   - Campo "Seu nome" (opcional):
     - Input text, placeholder "Como prefere ser chamado"
   - Campo "Senha" (obrigatório):
     - Input password, placeholder "Mínimo 8 caracteres, 1 maiúscula, 1 número"
     - Validação: validatePassword()
   - Campo "Confirmar senha" (obrigatório)
   - Botão "Ativar conta"

4. Após submissão bem-sucedida:
   - Guardar token no localStorage: `localStorage.setItem("token", access_token)`
   - Chamar `login(access_token)` do useAuth (importar useAuth de @/hooks/useAuth)
   - Redirecionar para /dashboard com `router.replace("/dashboard")`

5. Estados de erro:
   - Senha inválida: exibir mensagem inline
   - Token expirado/inválido (400/404/410):
     ```
     "Este convite é inválido ou já foi utilizado."
     [← Voltar ao login]
     ```
   - Outros erros: exibir mensagem do backend

6. Layout: mesmo estilo de reset-password.page.tsx
   (min-h-screen flex items-center justify-center, max-w-sm, espaçamento)

NOTA IMPORTANTE:
A função `login` do AuthContext atualiza localStorage e aplica os dados do payload JWT.
Como `name` não está no JWT, o nome no header só atualizará após recarregar a página
ou após um novo fetch de /auth/me. Isso é aceitável para Stage 0 — não requer
solução especial agora.

--- VERIFICAÇÃO ---
- /activate?token=<uuid-valido> exibe o formulário
- /activate (sem token) exibe mensagem de link inválido
- Submissão bem-sucedida faz login e redireciona para /dashboard
- Token inválido mostra mensagem de erro apropriada
- Senha fraca (sem maiúscula, sem número, curta demais) bloqueia submit com mensagem
```

---

## Passo 8 — Sumário executivo

### 8a — Tabela de blocos

| Bloco | REQs | Estimativa | Depende de | Pode ser paralelo com |
|-------|------|-----------|-----------|----------------------|
| **A** — Sidebar + Auth + Logo | REQ-03, REQ-04, REQ-05 | 1h | — | — |
| **B** — Painel + Agenda | REQ-01, REQ-02 | 1h | Bloco A | C, D |
| **C** — CPF Profissional | REQ-14 | 15min | — | B, D |
| **D** — Módulo Financeiro | REQ-06, REQ-07, REQ-08 | 4h | Bloco A | B, C |
| **E** — Configurações | REQ-09, REQ-10, REQ-11, REQ-12 | 4h | Bloco A | B, C |
| **F** — Ativação de conta | REQ-13 | 1h | Bloco E | — |

**Estimativa total:** 11–12 horas de execução

### 8b — Gaps de endpoint

**Nenhum gap encontrado.** Todos os 14 endpoints necessários existem no backend.

### 8c — Componentes novos a criar

| Componente | REQ | Arquivo |
|-----------|-----|---------|
| `CustomerAutocomplete` | REQ-06 | `components/CustomerAutocomplete.tsx` |
| `FeeWarningBanner` | REQ-06 | `components/FeeWarningBanner.tsx` |
| (ToggleSwitch inline) | REQ-10, REQ-11 | padrão copiado de integrations/page.tsx |

### 8d — Novas rotas criadas

| Rota | REQ | Arquivo |
|------|-----|---------|
| `/agenda` | REQ-02 | `app/(dashboard)/agenda/page.tsx` |
| `/financeiro` | REQ-03 | `app/(dashboard)/financeiro/page.tsx` |
| `/financeiro/pagamentos` | REQ-08 | `app/(dashboard)/financeiro/pagamentos/page.tsx` |
| `/financeiro/pagamentos/novo` | REQ-06 | `app/(dashboard)/financeiro/pagamentos/novo/page.tsx` |
| `/financeiro/movimentacoes` | REQ-07 | `app/(dashboard)/financeiro/movimentacoes/page.tsx` |
| `/settings/taxas` | REQ-09 | `app/(dashboard)/settings/taxas/page.tsx` |
| `/settings/integracoes` | REQ-10 | `app/(dashboard)/settings/integracoes/page.tsx` |
| `/settings/comunicacao` | REQ-11 | `app/(dashboard)/settings/comunicacao/page.tsx` |
| `/settings/usuarios` | REQ-12 | `app/(dashboard)/settings/usuarios/page.tsx` |
| `/activate` | REQ-13 | `app/activate/page.tsx` |

### 8e — Rotas com redirect

| Rota antiga | Redirect para | Motivo |
|-------------|---------------|--------|
| `/appointments` | `/agenda` | REQ-02/REQ-03 |
| `/users` | `/settings/usuarios` | REQ-12 |
| `/integrations` | `/settings/integracoes` | REQ-10 |

### 8f — Ordem global de execução recomendada

```
FASE 1 (fundação — obrigatória primeiro):
  → Bloco A: Sidebar + AuthContext + Logo

FASE 2 (paralela — iniciar após Bloco A):
  → Bloco B: Painel + Agenda
  → Bloco C: CPF Profissional (pode ser feito a qualquer momento)
  → Bloco D (parte 1): Hub Financeiro + Lista Pagamentos + Movimentações
  → Bloco E (parte 1): Hub Settings + Taxas + Comunicação

FASE 3 (após D/E parte 1 concluídos):
  → Bloco D (parte 2): Formulário de Registro de Pagamento
  → Bloco E (parte 2): Integrações + Usuários

FASE 4 (após Bloco E completo):
  → Bloco F: Página Activate
```

### 8g — Riscos identificados

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Sidebar refatorada pode perder estado mobile (open/close) | Médio — UX quebrada no mobile | Testar toggle mobile após Bloco A |
| Redirect `/appointments → /agenda` pode quebrar links internos | Baixo — Next.js redirect é transparente | Buscar todas as ocorrências de `/appointments` no codebase antes do Bloco B |
| `PATCH /communication/settings` na UI real é `PUT` | Alto — 405 Method Not Allowed | **Usar `api.put` (adicionar ao api.ts) ou verificar se `api.patch` funciona** — ver Divergências |
| `GET /payments` não retorna nome do cliente | Médio — coluna cliente vazia | Fazer GET /customers em paralelo e criar mapa de lookup por customer_id |
| CustomerAutocomplete com muitos clientes | Baixo — performance | Buscar /customers uma vez e filtrar client-side para Stage 0 |
| Formulário Asaas (REQ-10): `PATCH /companies/me` pode ter validação de CPF no backend | Baixo | Backend já tem `validate_and_clean_cpf_cnpj()` — erro do backend é tratado pelo frontend |
| Token de ativação expirado antes do usuário abrir o email | Baixo — fora do escopo do sprint | Página de erro com link para suporte |

---

## Divergências encontradas: brief vs estado atual

### BLOQUEADOR

*Nenhum bloqueador identificado.* Todos os endpoints necessários existem.

### AJUSTE

| ID | Descrição | REQ afetado |
|----|-----------|-------------|
| **AJ-01** | ~~`PATCH /communication/settings` real é `PUT` — `api.ts` não tem método `put`~~. RESOLVIDO — fix incorporado no início do Bloco E Parte 1: adicionar método `put` ao objeto `api` em `lib/api.ts` antes de criar qualquer página de Configurações. | REQ-11 |
| **AJ-02** | ~~Brief diz rotas `/configuracoes/...`; este plano usa `/settings/...` por consistência com o codebase existente. Labels da UI permanecem "Configurações". Se a URL canônica importar para SEO/bookmarks, renomear as pastas de `settings/` para `configuracoes/` — mas implica atualizar links em todo o codebase.~~ RESOLVIDO — decisão confirmada: manter `/settings/` por consistência com o codebase existente. Labels da UI permanecem em português ("Configurações", "Taxas", etc.). | REQ-09 a REQ-12 |
| **AJ-03** | `GET /payments` não retorna o nome do cliente (retorna `customer_id`). Para REQ-08, será necessário fazer dois fetches (`GET /payments` + `GET /customers`) e fazer o mapeamento client-side. | REQ-08 |
| **AJ-04** | `FeePolicyResponse.fee_percentage` pode ser `null` (nullable DB) mas o schema Pydantic declara `Decimal` (non-optional). Tratar como `number | null` no tipo TypeScript da tela de taxas. | REQ-09 |
| **AJ-05** | A lógica de `POST /integrations/credentials` para PagSeguro precisa do schema correto. O executor deve ler `agendamento_engine/app/modules/integrations/router.py` para verificar o body esperado antes de implementar. | REQ-10 |

### OBSERVAÇÃO

| ID | Descrição | REQ afetado |
|----|-----------|-------------|
| **OBS-01** | O `/payments` existente no sidebar será removido (REQ-03) e substituído por `/financeiro/pagamentos`. O arquivo `app/(dashboard)/payments/page.tsx` pode ser mantido com redirect ou deletado — este plano mantém com redirect para não quebrar links existentes. | REQ-03, REQ-08 |
| **OBS-02** | `User.name` não está no JWT payload; após login/activate, o nome aparecerá no header apenas após o próximo fetch de `/auth/me` (que ocorre na hidratação do AuthContext). Na prática: após activate + redirect, o refresh de página carregará o nome. Acceptable for Stage 0. | REQ-04, REQ-13 |
| **OBS-03** | A seção `/settings/financial` existente (status Asaas) ficará sem entrada direta no hub após o sprint. O status Asaas estará na aba Asaas de `/settings/integracoes`. Recomenda-se manter o link `/settings/financial` por agora ou adicionar redirect para `/settings/integracoes`. | REQ-10 |
| **OBS-04** | `GET /financial/movements` pode retornar um array grande para tenants com muito histórico. Para Stage 0, filtrar client-side com os filtros de data é aceitável. Paginação server-side pode ser necessária em produção. | REQ-07 |
| **OBS-05** | A seção "Produtos" permanece no sidebar mesmo sem REQ correspondente. O brief não pede remoção. Mantida. | — |

---

*Plano gerado em 2026-06-04. Sessão exclusiva de análise — nenhum arquivo de código foi criado ou modificado.*
*Próxima ação: executar Bloco A, depois Blocos B/C/D/E em paralelo onde possível, finalizar com Bloco F.*
