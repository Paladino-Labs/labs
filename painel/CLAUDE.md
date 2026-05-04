@../CLAUDE.md

# Frontend — painel/

> Contexto específico do Next.js. O contexto completo do monorepo está em `@../CLAUDE.md`.

---

## Next.js — LEIA ANTES DE ASSUMIR CONVENÇÕES

Esta versão tem breaking changes. Antes de escrever qualquer código Next.js,
leia o guia relevante em `node_modules/next/dist/docs/`. Respeite avisos de deprecação.

## Estrutura de rotas

```
app/
  (dashboard)/          ← grupo de rotas autenticadas (layout com sidebar)
    layout.tsx          ← verifica auth, renderiza Sidebar
    appointments/       ← lista de agendamentos + criação
    customers/          ← cadastro de clientes
    dashboard/          ← KPIs e próximos agendamentos
    integrations/       ← conexão WhatsApp (QR Code, status)
    products/           ← produtos/serviços extras
    professionals/      ← cadastro de profissionais
    services/           ← cardápio de serviços
    settings/           ← configurações da empresa
  book/[slug]/          ← fluxo público (sem auth) — agendamento online
    BookingFlow.tsx     ← FSM: IDLE→SERVICE→PROFESSIONAL→DATE→TIME→CUSTOMER→CONFIRM→CONFIRMED
  layout.tsx            ← root layout
  page.tsx              ← landing / redirect
```

## Utilitários obrigatórios

| O que | Onde importar | Observação |
|-------|--------------|------------|
| HTTP requests | `lib/api.ts` | **nunca** `fetch` raw |
| Formatação moeda | `formatBRL` de `lib/utils.ts` | |
| Formatação data | `formatDateTime` de `lib/utils.ts` | sempre passar `timeZone` |
| Status agendamento | `lib/constants.ts` | `APPOINTMENT_STATUS_LABELS`, `APPOINTMENT_STATUS_VARIANT` |
| Badge ativo/inativo | `components/ActiveBadge.tsx` | |
| Auth hook | `hooks/useAuth.ts` | re-export intencional — não remover |

## BookingFlow.tsx — regras críticas

- Timezone: sempre `timeZone: companyTimezone` em **todo** `toLocaleString` e `toLocaleDateString`
- O prop `companyTimezone` vem de `session.company_timezone` (snapshot imutável da sessão)
- Componentes `TimeStep`, `ConfirmStep`, `ConfirmedView` recebem `companyTimezone` como prop

## Componentes shadcn

Primitivos em `components/ui/`. Não modificar diretamente — extender via wrapper se necessário.

## Padrão de fetch em páginas

```typescript
// Preferir useFetch hook (quando disponível) em vez de useEffect + fetch manual
// Promise.all para múltiplos endpoints simultâneos (ex: appointments/new)
const [services, professionals] = await Promise.all([
  api.get<Service[]>("/services"),
  api.get<Professional[]>("/professionals"),
])
```
