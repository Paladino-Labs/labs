# Plano de Ajustes — Pós-Sprint Frontend
**Versão:** 1.0 · **Data:** 2026-06-05 · **Sessão:** análise exclusiva — sem alteração de código

> **Escopo:** 9 ajustes identificados após a execução dos Blocos A–F do sprint frontend.
> Todos os ajustes são em `painel/`. O ajuste 9 requer alterações no backend (`agendamento_engine/`),
> documentadas explicitamente.

---

## Pré-leitura: estado atual do codebase

### Arquivos lidos e estado verificado

| Arquivo | Estado |
|---------|--------|
| `financeiro/pagamentos/novo/page.tsx` | Implementado completo. Bug: origem em `lib/api.ts`, não nesta página |
| `settings/taxas/page.tsx` | Implementado. Bug "Failed to fetch": causa ambiental + possível CORS |
| `settings/integracoes/page.tsx` | 3 abas: WhatsApp, Asaas, PagSeguro. Link de agendamento na aba WhatsApp |
| `settings/page.tsx` | 6 cards. Falta card "Meu Perfil" |
| `settings/financial/page.tsx` | Existe — mostra apenas status Asaas. Orphan pós-sprint (sem link no hub) |
| `financeiro/page.tsx` | 3 cards. Falta card "Taxas de maquininha" |
| `settings/profile/page.tsx` | Destino do link de agendamento. Coleta dados da empresa (não tem campo slug/booking_url) |
| `lib/api.ts` | Bug na linha 36: `body.detail` pode ser array (FastAPI 422) |
| `context/AuthContext.tsx` | Completo: inclui `name`, envia token corretamente |
| `agenda/page.tsx` | Botão "Concluir" existe no modal de detalhe (linha ~541). Chama apenas PATCH /complete |
| `components/CustomerAutocomplete.tsx` | Implementado. Reutilizável no popup de pagamento |
| `components/FeeWarningBanner.tsx` | Implementado. Reutilizável no popup de pagamento |

### Consultas externas

**Barberflow (github.com/Silva-fin/barberflow-system):**
- Arquivo: `src/routes/_authenticated.app.financeiro.tsx`
- Biblioteca: **Recharts** — `AreaChart`, `ResponsiveContainer`, `Tooltip`, `XAxis`, `YAxis`
- Métricas: Receitas, Despesas, Resultado (líquido); gráfico de área por período
- Separação: abas Receitas/Despesas; filtro por tipo de entry
- **Status no painel/:** Recharts **não está** no `package.json` — precisaria ser instalado

**Asaas — campos obrigatórios para criar subconta:**

| Campo | Tipo | Obrigatório |
|-------|------|-------------|
| `name` | string | ✅ sim |
| `email` | string | ✅ sim |
| `cpfCnpj` | string | ✅ sim |
| `mobilePhone` | string | ✅ sim |
| `incomeValue` | number | ✅ sim (receita mensal) |
| `address` | string | ✅ sim (rua) |
| `addressNumber` | string | ✅ sim |
| `province` | string | ✅ sim (bairro) |
| `postalCode` | string | ✅ sim |
| `birthDate` | date (YYYY-MM-DD) | Opcional (obrigatório na prática para CPF) |
| `companyType` | string (MEI/LIMITED/etc.) | Opcional |

**O que o backend envia hoje** (`asaas.py:101–109`):
- `name`, `email`, `companyType: "MEI"` (hardcoded) — sempre
- `cpfCnpj` — se fornecido
- `birthDate` — se fornecido

**Lacuna crítica:** o backend não coleta nem envia `mobilePhone`, `incomeValue`, `address`,
`addressNumber`, `province`, `postalCode`. A criação de subconta Asaas em produção
provavelmente está falhando silenciosamente ou retornando erro que não é exibido ao usuário.

---

## Ajuste 1 — Bug: Failed to fetch nas taxas

**Prioridade:** CRÍTICO
**Esforço estimado:** 15–30 min (se for configuração) / 1h (se for CORS + backend)

### Causa raiz / Análise

O erro `TypeError: Failed to fetch` é lançado pelo browser quando a requisição de rede
falha **antes** de receber qualquer resposta. Ocorre em dois cenários principais:

**Cenário A — `NEXT_PUBLIC_API_URL` não configurado (mais provável):**
`lib/api.ts:1` — `const BASE = process.env.NEXT_PUBLIC_API_URL!`

Se a variável não está definida no ambiente de execução, `BASE` fica como a string literal
`"undefined"`. A chamada vira `fetch("undefined/financial/fee-policies", ...)`, que é
uma URL inválida → `TypeError: Failed to fetch`.

Sinal diagnóstico: se a página de Login e a Agenda funcionam mas só a de Taxas falha,
descarta Cenário A (pois todas as páginas usam o mesmo `BASE`).

**Cenário B — CORS (se URL está correta):**
O endpoint `GET /financial/fee-policies` pode não estar incluído na lista de
`allowed_origins` do FastAPI (se houver configuração por rota). O browser bloqueia a
resposta e o Fetch API lança `Failed to fetch`.

**Cenário C — Race condition com hydration:**
O `useEffect` em `settings/taxas/page.tsx:56` tem `[canAccess]` como dependência.
Durante hydration, `role = null` → `canAccess = false` → early return sem chamar API.
Após hydration, `canAccess = true` → useEffect re-executa → chamada é feita.
Este fluxo é correto, **mas** `loading` começa como `true` no `useState(true)`.
Se por algum motivo o `role` nunca é populado (ex: `/auth/me` falhou no hydration),
a página fica presa em "Carregando…" para sempre. Esse caso não exibe "Failed to fetch".

### Solução proposta

**Passo 1 — Diagnóstico rápido (sem código):**
Abrir DevTools → aba Network → navegar para `/settings/taxas` → observar:
- Qual URL está sendo chamada? Se for `undefined/financial/...` → Cenário A
- O request existe mas falha? → Checar `Status` e `CORS error` no console → Cenário B
- O request não aparece? → Cenário C

**Passo 2 — Correção A (se for URL):**
Verificar/criar `painel/.env.local`:
```
NEXT_PUBLIC_API_URL=https://seu-backend.railway.app
```
Reiniciar o servidor de desenvolvimento.

**Passo 3 — Correção B (se for CORS):**
Verificar `agendamento_engine/app/main.py` — confirmar que `CORSMiddleware` está configurado
com o origin do frontend. Não é uma mudança de código do sprint — é infra.

**Passo 4 — Melhoria de código defensiva (`settings/taxas/page.tsx`):**
Adicionar `hydrated` ao guard para evitar o estado de loading eterno:
```tsx
// Importar do AuthContext
const { role, hydrated } = useAuth()

useEffect(() => {
  if (!hydrated || !canAccess) return   // aguarda hydration antes de concluir
  api.get<FeePolicy[]>("/financial/fee-policies")...
}, [canAccess, hydrated])   // adicionar hydrated às dependências
```

### Arquivos afetados
- `painel/.env.local` (verificar/criar — não versionar)
- `painel/app/(dashboard)/settings/taxas/page.tsx` (melhoria defensiva — baixo risco)

### Depende de
Nenhum ajuste. Bloqueador para Ajuste 3 (mover taxas para financeiro).

---

## Ajuste 2 — Bug: [object Object],[object Object] no registro de pagamento

**Prioridade:** CRÍTICO
**Esforço estimado:** 10 min

### Causa raiz / Análise

O bug está em `lib/api.ts:36`:

```ts
const err = Object.assign(new Error(body.detail ?? "Erro desconhecido"), {
  status: res.status,
}) as ApiError
```

O FastAPI retorna erros de validação (HTTP 422) no formato:
```json
{
  "detail": [
    { "loc": ["body", "customer_id"], "msg": "field required", "type": "value_error.missing" },
    { "loc": ["body", "gross_amount"], "msg": "value is not a valid float", "type": "type_error.float" }
  ]
}
```

`body.detail` é um **array de objetos**. `new Error([{...}, {...}])` converte o array
para string via `.toString()`, que resulta em `"[object Object],[object Object]"`.

Na página `financeiro/pagamentos/novo/page.tsx:174`:
```ts
} catch (err: unknown) {
  setError(err instanceof Error ? err.message : "Erro ao registrar pagamento.")
}
```
`err.message` já carrega o `"[object Object],[object Object]"` que vem de `api.ts`.

### Solução proposta

Correção cirúrgica em **`lib/api.ts`, linhas 35–39** — substituir:
```ts
const err = Object.assign(new Error(body.detail ?? "Erro desconhecido"), {
  status: res.status,
}) as ApiError
```
Por:
```ts
let errorMessage: string
if (Array.isArray(body.detail)) {
  // FastAPI 422: detail é [{loc, msg, type}]
  errorMessage = body.detail.map((d: { msg?: string }) => d.msg ?? "Erro de validação").join("; ")
} else {
  errorMessage = typeof body.detail === "string" ? body.detail : "Erro desconhecido"
}
const err = Object.assign(new Error(errorMessage), { status: res.status }) as ApiError
```

Essa correção beneficia **todas** as páginas que usam `api.ts`, não só o registro de pagamento.

### Arquivos afetados
- `painel/lib/api.ts` (linhas 35–39)

### Depende de
Nenhum.

---

## Ajuste 3 — Mover Taxas para Financeiro e renomear

**Prioridade:** MÉDIO
**Esforço estimado:** 30 min

### Causa raiz / Análise

As taxas MDR são uma funcionalidade financeira operacional, não uma configuração administrativa.
O usuário navega em Financeiro para operar pagamentos e deveria acessar as taxas de lá.
Manter em Configurações cria um fluxo incongruente: o `FeeWarningBanner` aponta para
`/settings/taxas` mas o contexto do usuário ao ver o aviso é o módulo Financeiro.

**Estado atual:**
- `settings/page.tsx`: card "Taxas MDR" aponta para `/settings/taxas` (linha 36–42)
- `financeiro/page.tsx`: 3 cards, sem Taxas
- `FeeWarningBanner.tsx`: `onConfigureClick` é chamado com `router.push("/settings/taxas")` pelo componente pai (`financeiro/pagamentos/novo/page.tsx:258`)

**Decisão de rota:**
Criar `/financeiro/taxas` como nova rota canônica.
Manter `/settings/taxas` como redirect (sem deletar) para não quebrar bookmarks.

### Solução proposta

1. **Criar** `app/(dashboard)/financeiro/taxas/page.tsx`
   - Copiar todo o conteúdo de `settings/taxas/page.tsx`
   - Sem alteração de código — apenas mover o arquivo

2. **Adicionar redirect** em `settings/taxas/page.tsx` (substituir todo o conteúdo):
   ```tsx
   import { redirect } from "next/navigation"
   export default function TaxasRedirect() { redirect("/financeiro/taxas") }
   ```

3. **Adicionar card** em `financeiro/page.tsx` (após os 3 cards existentes):
   ```tsx
   {
     href: "/financeiro/taxas",
     icon: Percent,       // importar de lucide-react
     title: "Taxas de maquininha",
     description: "Configure as taxas por método de pagamento",
   }
   ```

4. **Remover card** "Taxas MDR" de `settings/page.tsx`
   - Remover o objeto `{ href: "/settings/taxas", icon: Percent, title: "Taxas MDR", ... }` do array `sections`
   - O ícone `Percent` pode ser removido do import se não usado em outro lugar

5. **Atualizar FeeWarningBanner** — o link agora aponta para `/financeiro/taxas`:
   Em `financeiro/pagamentos/novo/page.tsx:258`:
   ```tsx
   onConfigureClick={() => router.push("/financeiro/taxas")}
   ```

### Arquivos afetados
- `painel/app/(dashboard)/financeiro/taxas/page.tsx` (CRIAR — copiar de settings/taxas)
- `painel/app/(dashboard)/settings/taxas/page.tsx` (substituir por redirect)
- `painel/app/(dashboard)/financeiro/page.tsx` (adicionar card)
- `painel/app/(dashboard)/settings/page.tsx` (remover card Taxas MDR)
- `painel/app/(dashboard)/financeiro/pagamentos/novo/page.tsx` (atualizar link FeeWarningBanner)

### Depende de
Ajuste 1 (o bug de "Failed to fetch" deve ser resolvido antes de mover a página, pois
o redirect mascara erros — o usuário chegaria em `/financeiro/taxas` mas o bug ainda existiria).

---

## Ajuste 4 — Esconder PagSeguro

**Prioridade:** BAIXO
**Esforço estimado:** 15 min

### Causa raiz / Análise

O PagSeguro está em sandbox pendente sem previsão de ativação (`CLAUDE.md` — decisão
arquitetural: não ativar PagSeguro Point em produção até confirmação do endpoint com PagBank).
Exibir a aba para o usuário final gera confusão e expectativa não gerenciável.

**Estado atual em `settings/integracoes/page.tsx`:**
- Linha 628: `<TabsTrigger value="pagseguro">PagSeguro</TabsTrigger>`
- Linha 643: `<TabsContent value="pagseguro"><TabPagSeguro /></TabsContent>`
- O componente `TabPagSeguro` (linhas 522–619) está implementado e funcional

**Com 2 abas restantes (WhatsApp + Asaas):** avaliar se `Tabs` ainda faz sentido.
Com apenas 2 itens, Tabs é válido. Manter a estrutura `Tabs` para facilitar
reintrodução do PagSeguro quando sandbox for validado.

### Solução proposta

Remover a aba PagSeguro **sem deletar o componente** `TabPagSeguro`:

1. Em `settings/integracoes/page.tsx`, remover:
   - `<TabsTrigger value="pagseguro">PagSeguro</TabsTrigger>` (linha ~628)
   - `<TabsContent value="pagseguro"><TabPagSeguro /></TabsContent>` (linhas ~643-645)

2. **Manter** o componente `TabPagSeguro` no arquivo (comentado ou simplesmente não renderizado)
   para facilitar reativação futura sem precisar reescrever.

3. **NÃO alterar** nenhuma lógica backend (`POST /integrations/credentials` com PAGSEGURO).

### Arquivos afetados
- `painel/app/(dashboard)/settings/integracoes/page.tsx` (remoção das 2 linhas de Tabs)

### Depende de
Nenhum. Independente — pode ser feito a qualquer momento.

---

## Ajuste 5 — Mover link de agendamento para Perfil da empresa

**Prioridade:** MÉDIO
**Esforço estimado:** 45 min

### Causa raiz / Análise

O link de agendamento online (slug + booking URL) está atualmente dentro da aba
"WhatsApp" em `settings/integracoes/page.tsx` (linhas 227–293), dentro do componente
`TabWhatsApp`. Essa seção "Agendamento Online" tem:
- Input para configurar o slug (`PATCH /companies/me` com `{ company: { slug } }`)
- Toggle de habilitar/desabilitar agendamento online
- Exibição + botão de copiar da booking URL

O slug e a URL de agendamento fazem parte da **identidade da empresa**, não da
configuração de integrações de comunicação. O destino natural é a página de
`settings/profile/page.tsx` (Perfil da empresa).

**Estado de `settings/profile/page.tsx`:**
- Não tem campo `slug` nem `booking_url` (o tipo `CompanyProfile` não os inclui)
- Usa endpoint `GET /company/profile` (não `GET /companies/me`)
- O `CompanyData` em `TabWhatsApp` usa `GET /companies/me` (endpoint diferente!)

**Discrepância de endpoint:**
- Perfil: `GET /company/profile` + `PATCH /company/profile`
- Agendamento: `GET /companies/me` (com `settings.online_booking_enabled`, `slug`)
- São endpoints distintos com schemas distintos

**O que fica na aba "WhatsApp" após a mudança:**
Apenas o bloco de conexão WhatsApp Business (status, QR code, bot toggle, desconectar).
A aba pode ser renomeada de "WhatsApp" para algo mais preciso, mas essa decisão
é cosmética — deixar para o executor decidir.

### Solução proposta

1. **Em `settings/profile/page.tsx`:**
   Adicionar novo Card "Agendamento Online" (abaixo do card de Localização, antes de Redes sociais):
   - Fetch adicional: `api.get<{ slug, settings: { online_booking_enabled } }>("/companies/me")`
   - Campo slug com salvamento via `api.patch("/companies/me", { company: { slug } })`
   - Fetch da booking URL via `api.get<{ booking_url }>(`/booking/${slug}/info`)`
   - Toggle de habilitar/desabilitar agendamento
   - Exibição + botão copiar do link

   O código dessa seção é extrato direto do componente `TabWhatsApp` (linhas 160–293).
   A lógica de state (`isBotEnabled`, `isOnlineBookingEnabled`, `slugInput`, etc.) é reutilizável.
   **Separar o fetch de `/companies/me`** do fetch atual de `/company/profile` para evitar
   conflito de schemas.

2. **Em `settings/integracoes/page.tsx` — componente `TabWhatsApp`:**
   - Remover todo o card "Agendamento Online" (linhas 227–293)
   - Remover os estados associados: `company`, `isBotEnabled`, `isOnlineBookingEnabled`,
     `slugInput`, `savingSlug`, `copied`, `bookingUrl` (linhas 160–174)
   - Remover o `useEffect` que faz `api.get("/companies/me")` (linhas 176–190)
   - Remover as funções: `handleSaveSlug`, `handleToggleOnlineBooking`, `handleCopyLink` (linhas 192–224)
   - Manter: todo o bloco de status/QR/bot WhatsApp (linhas 295–397)
   - **Manter** `isBotEnabled` e `handleToggleBot` — são específicos do WhatsApp

3. **Imports:** Remover os ícones e utilitários não mais usados em `TabWhatsApp`
   depois das remoções (ex: `Link2`, `Check`).

### Arquivos afetados
- `painel/app/(dashboard)/settings/profile/page.tsx` (adicionar card Agendamento Online)
- `painel/app/(dashboard)/settings/integracoes/page.tsx` (remover seção do TabWhatsApp)

### Depende de
Ajuste 4 (não é bloqueante, mas conveniente executar junto para reduzir toques no mesmo arquivo).

---

## Ajuste 6 — Meu Perfil em Configurações

**Prioridade:** ALTO
**Esforço estimado:** 45 min

### Causa raiz / Análise

O usuário logado não tem como visualizar ou editar seu próprio perfil (nome, email) pelo painel.
O `settings/page.tsx` tem cards para Perfil da empresa e Segurança, mas não tem "Meu Perfil"
(dados do usuário logado, distintos dos dados da empresa).

**Endpoints disponíveis (confirmados no plano de sprint):**
- `GET /auth/me` → retorna `{ sub, email, role, name, company_id }`
- `PATCH /auth/profile` → aceita `{ name: string }`, retorna usuário atualizado

**Campo `phone` em `User`:** o modelo `User` do backend não tem `phone` (verificado no CLAUDE.md
e no AuthContext — apenas `name`, `email`, `role`, `userId`, `companyId`).

**Campos disponíveis para o formulário:**
| Campo | Editável | Endpoint |
|-------|----------|----------|
| `name` | ✅ sim | `PATCH /auth/profile` |
| `email` | 🔒 leitura | (mudança de email requer fluxo separado — fora do escopo) |
| `role` | 🔒 leitura | (somente OWNER pode mudar roles — outro fluxo) |
| `phone` | ❌ não existe | (campo não existe no modelo User) |

### Solução proposta

1. **Criar** `app/(dashboard)/settings/perfil/page.tsx` (nova página):

   ```
   Estrutura:
   - Título: "Meu Perfil" (font-display text-3xl)
   - Subtítulo: "Seus dados pessoais de acesso"
   - Card "Informações pessoais":
     - Campo "Nome" (input text, editável via PATCH /auth/profile)
     - Campo "Email" (somente leitura, text-muted-foreground com badge "Não editável")
     - Campo "Papel/Role" (somente leitura, Badge com o role traduzido)
     - Botão "Salvar" — habilita apenas quando nome foi alterado
   - Feedback inline: "Salvo ✓" por 2s ou erro em texto vermelho
   ```

   Fluxo de dados:
   - `useEffect`: `GET /auth/me` → popular campos
   - `onSubmit`: `PATCH /auth/profile` → `{ name: novoNome }`
   - Sucesso: chamar `setName(novoNome)` do AuthContext para atualizar o header sem reload

   **Nota sobre o AuthContext:** `setName` não é exposto pelo contexto atual.
   Alternativa: após salvar, refazer o fetch `/auth/me` e atualizar o contexto via
   um hook ou forçar reload da página. Para Stage 0, reload aceitável.
   Para melhor UX: exportar `setName` do AuthContext (1 linha de mudança).

2. **Adicionar card** em `settings/page.tsx`:
   ```tsx
   {
     href: "/settings/perfil",
     icon: UserCircle,    // importar de lucide-react
     title: "Meu Perfil",
     description: "Nome e informações da sua conta",
   }
   ```
   Inserir como **primeiro card** do array (antes de Perfil da empresa).

### Arquivos afetados
- `painel/app/(dashboard)/settings/perfil/page.tsx` (CRIAR)
- `painel/app/(dashboard)/settings/page.tsx` (adicionar card)
- `painel/context/AuthContext.tsx` (opcional: exportar `setName` para UX sem reload)

### Depende de
Nenhum. Independente.

---

## Ajuste 7 — Popup de pagamento ao concluir agendamento

**Prioridade:** ALTO
**Esforço estimado:** 2–3 horas

### Causa raiz / Análise

O botão "Concluir" no modal de detalhe do agendamento (`agenda/page.tsx:541–548`) faz:
```tsx
<Button variant="outline" size="sm" onClick={() => handleComplete(detailAppt.id)}>
  <CheckCircle2 className="h-4 w-4 mr-1" />
  Concluir
</Button>
```

E `handleComplete` (linhas 191–199):
```ts
async function handleComplete(id: string) {
  if (!confirm("Marcar como concluído?")) return
  await api.patch(`/appointments/${id}/complete`, {})
  setDetailAppt(null)
  fetchAll()
}
```

O fluxo **marca o agendamento como concluído sem processar o pagamento**. O pagamento
existe como fluxo separado em `/financeiro/pagamentos/novo`, mas não há integração.
Na prática, o barbeiro conclui o atendimento e o pagamento fica pendente ou nunca é registrado.

**O que o popup deve fazer:**
1. Interceptar o clique em "Concluir" — em vez de chamar diretamente `/complete`, abrir um Dialog
2. Pré-preencher com dados do agendamento:
   - `customer_id` + nome (de `detailAppt.customer`)
   - `appointment_id` (de `detailAppt.id`)
   - `gross_amount` (de `detailAppt.total_amount` — já existe no objeto)
3. Permitir seleção do método de pagamento (mesmo UI dos 4 cards em `pagamentos/novo`)
4. Ao confirmar:
   a. `POST /payments` com `customer_id`, `appointment_id`, `gross_amount`, `payment_method`, `payment_submethod`
   b. `POST /payments/{id}/confirm-manual`
   c. `PATCH /appointments/${id}/complete` — marca como concluído após pagamento
5. Exibir `FeeWarningBanner` se `fee_warning` presente
6. Se o usuário não quiser registrar pagamento: botão "Concluir sem pagamento" → apenas `/complete`

**Reaproveitamento de componentes existentes:**
- `CustomerAutocomplete` — NÃO necessário (cliente já está pré-definido pelo agendamento)
- `FeeWarningBanner` — reutilizável diretamente
- Os 4 cards de método de pagamento do `pagamentos/novo` — extrair como sub-componente ou duplicar

### Solução proposta

**Opção A — Componente `PaymentOnCompleteDialog` local no `agenda/page.tsx`:**
Adicionar um Dialog dentro do componente da página de agenda. Mais simples, sem novo arquivo.

**Opção B — Componente reutilizável `PaymentOnCompleteDialog.tsx`:**
Extrair para `components/PaymentOnCompleteDialog.tsx`. Reutilizável no futuro em
outras páginas que tenham o conceito de "concluir agendamento".

**Recomendação: Opção B** — o componente tem lógica de API não trivial e será
provavelmente reutilizado quando houver outras superfícies de conclusão.

**Props do componente:**
```tsx
interface Props {
  open: boolean
  appointment: {
    id: string
    total_amount: number
    customer?: { id: string; name: string } | null
    services: Array<{ service_name: string }>
  }
  onSuccess: () => void   // recarrega lista de agendamentos
  onClose: () => void
}
```

**Fluxo interno do componente:**
```
1. Exibe dados do agendamento (cliente, serviço, valor pré-preenchido)
2. Mostra os 4 cards de método (Dinheiro, PIX, Crédito, Débito)
3. Botão "Confirmar pagamento e concluir"
   → POST /payments → POST /confirm-manual → PATCH /complete → onSuccess()
4. Botão "Concluir sem registrar pagamento" (variant ghost)
   → PATCH /complete → onSuccess()
5. Fee warning após confirmação (FeeWarningBanner)
```

**Modificação em `agenda/page.tsx`:**
- Adicionar estado `paymentDialogOpen: boolean`
- Substituir `handleComplete` por:
  ```ts
  function handleComplete(appt: Appointment) {
    setDetailAppt(null)          // fecha modal de detalhe
    setPaymentTarget(appt)       // define o agendamento alvo
    setPaymentDialogOpen(true)   // abre o dialog de pagamento
  }
  ```
- Adicionar no JSX: `<PaymentOnCompleteDialog ... />`
- O Dialog de detalhe existente precisa passar o objeto `Appointment` completo, não só o ID

### Arquivos afetados
- `painel/components/PaymentOnCompleteDialog.tsx` (CRIAR)
- `painel/app/(dashboard)/agenda/page.tsx` (modificar handleComplete + adicionar dialog)

### Depende de
Ajuste 2 (o bug de `[object Object]` deve ser corrigido antes — o popup de pagamento
pode disparar erros 422 que precisam ser exibidos corretamente).

---

## Ajuste 8 — Dashboard financeiro com gráficos

**Prioridade:** MÉDIO
**Esforço estimado:** 3–4 horas

### Causa raiz / Análise

A página `financeiro/page.tsx` é um hub de navegação com 3 cards. Não há visualização
de dados financeiros na própria página. O usuário precisa entrar em sub-páginas para
ver qualquer dado.

**Referência Barberflow:**
- Usa Recharts (`AreaChart`, `ResponsiveContainer`, `Tooltip`, `XAxis`, `YAxis`)
- Métricas: Receitas, Despesas, Resultado
- Gráfico de área mostrando receita por período
- Separação por abas Receita/Despesa

**Endpoints disponíveis:**

| Endpoint | Dados | Uso para gráfico |
|----------|-------|-----------------|
| `GET /financial/movements` | `movement_type: INFLOW/OUTFLOW`, `amount`, `created_at` | Gráfico de linha/área receita vs saída por período |
| `GET /payments` | `payment_method`, `net_charged_amount`, `status`, `created_at` | Pizza de métodos de pagamento; barra de receita diária |
| `GET /financial/accounts` | Contas com saldo | Cards de saldo por conta |

**O que é viável com os dados atuais:**
1. **Cards de KPI:** Total de entradas, Total de saídas, Resultado líquido (calculados de `/financial/movements`)
2. **Gráfico de área:** Receita por dia/semana (de `/financial/movements` filtrado por INFLOW)
3. **Gráfico de pizza ou barras:** Métodos de pagamento (de `/payments` — contar por `payment_method`)
4. **Cards de saldo:** Saldo por conta (de `/financial/accounts`)

**Biblioteca:** Recharts não está no `package.json` do painel. Precisa ser instalada:
```
npm install recharts
```
Alternativa sem nova dependência: CSS puro para gráficos simples (barras com `div` + `width: %`)
→ viable para gráfico de pizza de métodos, mas não para gráfico de linha temporal.

**Recomendação:** Instalar Recharts. É a biblioteca usada pelo protótipo de referência,
amplamente usada com Next.js/React, e não conflita com a stack atual.

### Solução proposta

**Estrutura proposta para `financeiro/page.tsx` (transformar hub em dashboard com hub):**

```
financeiro/page.tsx — nova estrutura:
├── Seção de KPIs (Cards): Total Receitas | Total Saídas | Resultado | Período seletor
├── Gráfico de área: Receita por período (filtro: 7d / 30d / 90d)
├── Gráfico de métodos: Pizza ou barras horizontais (Dinheiro, PIX, Crédito, Débito)
└── Seção de navegação (os 3 cards existentes — manter em formato menor)
```

**Implementação em 2 fases:**

Fase 1 — KPIs sem gráfico (evitar a dependência do Recharts):
- Fetch `GET /financial/movements?date_from=<30d>` → calcular totais INFLOW/OUTFLOW
- Exibir 3 cards: Receitas | Saídas | Resultado
- Tempo estimado: 45 min

Fase 2 — Gráficos com Recharts:
- Instalar recharts: `npm install recharts`
- Gráfico de área: agrupar movements por data, plotar INFLOW/OUTFLOW
- Gráfico de métodos: contar payments por payment_method
- Tempo estimado: 2–3h

### Arquivos afetados
- `painel/package.json` (adicionar recharts)
- `painel/app/(dashboard)/financeiro/page.tsx` (transformar hub em dashboard)

### Depende de
Nenhum bloqueante. Recomendado após Ajustes 1–3 para não modificar `financeiro/page.tsx`
múltiplas vezes.

---

## Ajuste 9 — Subconta Asaas com todos os campos obrigatórios

**Prioridade:** ALTO
**Esforço estimado:** 4–6 horas (backend + frontend)

### Causa raiz / Análise

**ATENÇÃO: Este ajuste requer alterações no backend (`agendamento_engine/`),
diferente de todos os outros ajustes desta sessão.**

O backend atualmente envia para `/accounts` da Asaas apenas:
```python
payload = {
  "name": company.name,
  "email": owner.email,
  "companyType": "MEI",     # hardcoded
  "cpfCnpj": cpf_cnpj,      # se fornecido
  "birthDate": birth_date,  # se fornecido
}
```

A API Asaas requer **obrigatoriamente**: `name`, `email`, `cpfCnpj`, `mobilePhone`,
`incomeValue`, `address`, `addressNumber`, `province`, `postalCode`.

Isso explica a "dívida ativa" registrada no `CLAUDE.md`:
> "Asaas create_subaccount: campo birthDate obrigatório para CPF; onboarding atual não
> coleta o campo; novos tenants ficam sem external_account_id até ser corrigido"

O problema é ainda maior do que o registrado: **não é só o birthDate** — são 5 campos
obrigatórios completamente ausentes.

**Análise de dados já disponíveis no sistema:**

| Campo Asaas obrigatório | Disponível? | Fonte |
|-------------------------|-------------|-------|
| `name` | ✅ sim | `Company.name` |
| `email` | ✅ sim | `User.email` (owner) |
| `cpfCnpj` | 🔶 parcial | `Company.owner_cpf_cnpj` (coletado no form Asaas) |
| `birthDate` | 🔶 parcial | `Company.owner_birth_date` (coletado no form Asaas) |
| `mobilePhone` | ❌ não | `Company.whatsapp` existe mas é o telefone público, não obrigatoriamente o do responsável |
| `incomeValue` | ❌ não | Não coletado em nenhum lugar |
| `address` | ❌ parcial | `Company.address` é string livre (ex: "Rua das Flores, 123 – Setor Central") — Asaas precisa do campo separado |
| `addressNumber` | ❌ não | Embutido na string de address — campo separado não existe |
| `province` | ❌ não | Asaas chama de bairro — não coletado |
| `postalCode` | ❌ não | Não coletado |

**Impacto:** A criação de subconta Asaas em produção **está falhando** para todos os
tenants pois os campos obrigatórios não são enviados. O backend loga o warning
`asaas_subaccount_missing_cpf_or_birthdate` mas o problema real é mais amplo.

### Solução proposta

**Backend (`agendamento_engine/`):**

1. **`modules/companies/schemas.py`** — adicionar campos ao `CompanyUpdate`:
   ```python
   owner_mobile_phone: Optional[str] = None    # mobilePhone para Asaas
   owner_income_value: Optional[float] = None  # incomeValue para Asaas
   owner_address: Optional[str] = None         # rua (separado de address da empresa)
   owner_address_number: Optional[str] = None  # número
   owner_province: Optional[str] = None        # bairro
   owner_postal_code: Optional[str] = None     # CEP
   ```

2. **Migration** — adicionar colunas à tabela `companies`:
   ```sql
   ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_mobile_phone VARCHAR(20);
   ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_income_value DECIMAL(12,2);
   ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_address VARCHAR(200);
   ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_address_number VARCHAR(20);
   ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_province VARCHAR(100);
   ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_postal_code VARCHAR(10);
   ```

3. **`modules/payments/providers/asaas.py`** — atualizar `create_subaccount`:
   ```python
   def create_subaccount(
       self, name, cpf_cnpj, email, birth_date="",
       mobile_phone="", income_value=None,
       address="", address_number="", province="", postal_code=""
   ) -> dict:
       payload = {
           "name": name,
           "email": email,
           "cpfCnpj": cpf_cnpj,
           "companyType": "MEI",
       }
       if birth_date: payload["birthDate"] = birth_date
       if mobile_phone: payload["mobilePhone"] = mobile_phone
       if income_value: payload["incomeValue"] = income_value
       if address: payload["address"] = address
       if address_number: payload["addressNumber"] = address_number
       if province: payload["province"] = province
       if postal_code: payload["postalCode"] = postal_code
       ...
   ```

4. **`modules/companies/service.py`** — passar novos campos para `create_subaccount`

**Frontend (`painel/`):**

5. **`settings/integracoes/page.tsx` — `TabAsaas`** — expandir formulário com os novos campos:

   ```
   Formulário de configuração Asaas (quando external_account_id é null):
   Seção "Responsável":
   - CPF ou CNPJ do responsável (já existe)
   - Data de nascimento (já existe)
   - Telefone celular do responsável (mobilePhone)
   - Receita mensal estimada (R$) (incomeValue)

   Seção "Endereço do responsável":
   - Rua / Logradouro
   - Número
   - Bairro
   - CEP
   ```

   O payload do PATCH `/companies/me` expandido:
   ```json
   {
     "owner_cpf_cnpj": "...",
     "owner_birth_date": "YYYY-MM-DD",
     "owner_mobile_phone": "5562999999999",
     "owner_income_value": 5000.00,
     "owner_address": "Rua das Flores",
     "owner_address_number": "123",
     "owner_province": "Setor Central",
     "owner_postal_code": "74000000"
   }
   ```

### Arquivos afetados
**Backend:**
- `agendamento_engine/app/modules/companies/schemas.py`
- `agendamento_engine/app/modules/companies/service.py`
- `agendamento_engine/app/modules/payments/providers/asaas.py`
- `agendamento_engine/app/infrastructure/db/models/company.py` (novos campos ORM)
- `agendamento_engine/alembic/versions/<nova_migration>.py` (CRIAR)

**Frontend:**
- `painel/app/(dashboard)/settings/integracoes/page.tsx` (expandir TabAsaas)

### Depende de
Backend deve ser implementado antes do frontend. A migration deve ser aplicada antes
de qualquer PATCH com os novos campos.

---

## Passo 6 — Sumário Executivo

### 6a — Tabela de ajustes com esforço e prioridade

| # | Ajuste | Prioridade | Esforço est. | Tipo |
|---|--------|------------|--------------|------|
| 1 | Bug: Failed to fetch nas taxas | **CRÍTICO** | 15–60 min | Bug (ambiental/CORS) |
| 2 | Bug: [object Object] no registro de pagamento | **CRÍTICO** | 10 min | Bug (código) |
| 3 | Mover Taxas → Financeiro + renomear | **MÉDIO** | 30 min | Reestruturação |
| 4 | Esconder PagSeguro | **BAIXO** | 15 min | Cosmético |
| 5 | Mover link de agendamento → Perfil da empresa | **MÉDIO** | 45 min | Reestruturação |
| 6 | Meu Perfil em Configurações | **ALTO** | 45 min | Feature nova |
| 7 | Popup de pagamento ao concluir agendamento | **ALTO** | 2–3 h | Feature nova |
| 8 | Dashboard financeiro com gráficos | **MÉDIO** | 3–4 h | Feature nova |
| 9 | Subconta Asaas com todos os campos | **ALTO** | 4–6 h | Feature nova (cross-stack) |

**Total estimado:** ~12–16 horas

### 6b — Ordem de execução recomendada

```
FASE 1 — Bugs críticos (executar primeiro, independentes entre si):
  → Ajuste 2: Bug api.ts [object Object]          (~10 min)
  → Ajuste 1: Bug Failed to fetch taxas            (~30 min)

FASE 2 — Reestruturações (após fase 1):
  → Ajuste 4: Esconder PagSeguro                   (~15 min)
  → Ajuste 3: Mover Taxas → Financeiro             (~30 min)  [requer Ajuste 1 resolvido]
  → Ajuste 5: Mover link agendamento → Perfil      (~45 min)

FASE 3 — Features novas (podem ser paralelas):
  → Ajuste 6: Meu Perfil em Configurações          (~45 min)
  → Ajuste 7: Popup de pagamento ao concluir       (~2–3h)    [requer Ajuste 2 resolvido]
  → Ajuste 8: Dashboard financeiro com gráficos    (~3–4h)

FASE 4 — Cross-stack (requer coordenação backend+frontend):
  → Ajuste 9: Subconta Asaas completa              (~4–6h)
```

### 6c — Dependências entre ajustes

```
Ajuste 1 ──→ Ajuste 3  (mover taxas sem resolver o bug mascara o problema)
Ajuste 2 ──→ Ajuste 7  (popup de pagamento exibiria [object Object] em erros de validação)
Ajuste 4 ──→ (sem dependentes)  [pode ser feito a qualquer momento]
Ajuste 5 ──→ (sem dependentes após Ajuste 4)
Ajuste 6 ──→ (sem dependentes)
Ajuste 9 backend ──→ Ajuste 9 frontend
```

### 6d — O que NÃO será feito neste ciclo (deferred)

- **Visual genérico das novas seções:** explicitamente deferido conforme escopo original
- **Paginação server-side de `/financial/movements`:** aceitável filtrar client-side no Stage 0
- **Mudança de email no Meu Perfil:** requer fluxo de verificação separado — fora do escopo
- **Campo `phone` no Meu Perfil:** campo não existe no modelo `User` — requereria migration
- **Reativar aba PagSeguro:** bloqueado por falta de confirmação do endpoint com PagBank
- **Gráfico de barras diário de pagamentos:** Fase 1 do Ajuste 8 (KPIs) cobre a necessidade imediata
- **`settings/financial/page.tsx` (orphan):** manter como está ou adicionar redirect para
  `/settings/integracoes` em ciclo de manutenção separado

---

## Apêndice: Estado do `settings/financial/page.tsx`

Esta página existe em `app/(dashboard)/settings/financial/page.tsx` mas não tem
entrada no hub de configurações (`settings/page.tsx`) após o sprint. Ela mostra o
status da subconta Asaas com mais detalhes (ID, data de criação, número de contas)
do que a `TabAsaas` em integrações.

**Recomendação:** Não deletar agora. Adicionar em ciclo de manutenção um redirect para
`/settings/integracoes?tab=asaas` ou simplesmente manter como URL de acesso direto para
debug. Não é bloqueante para nenhum dos 9 ajustes.

---

*Plano gerado em 2026-06-05. Sessão exclusiva de análise — nenhum arquivo de código foi criado ou modificado.*
*Próxima ação: executar Fase 1 (Ajustes 1 e 2), depois Fase 2 e 3 em paralelo onde possível.*
