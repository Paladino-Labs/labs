# Sprint D — Páginas do painel + Hub de Configurações

**Grupo:** G9
**Pré-requisito:** Sprint C ✅
**Risco:** Baixo

---

## Antes de começar

- [ ] Sprint C marcado como ✅ no README
- [ ] Ler `painel/CLAUDE.md`
- [ ] Ler referência: `barberflow-system/src/routes/_authenticated.app.clientes.tsx`
- [ ] Ler referência: `barberflow-system/src/routes/_authenticated.app.servicos.tsx`
- [ ] Ler referência: `barberflow-system/src/routes/_authenticated.app.configuracoes.tsx`
- [ ] Verificar contratos de API antes de implementar campos condicionais (ver tabela em `painel/CLAUDE.md`)

## Escopo

```
painel/app/(dashboard)/customers/page.tsx
painel/app/(dashboard)/services/page.tsx
painel/app/(dashboard)/integrations/page.tsx
painel/app/(dashboard)/settings/page.tsx        ← criar (hub)
painel/app/(dashboard)/settings/profile/page.tsx
painel/components/Sidebar.tsx
```

---

## Customers

- Search bar no header: `<Input>` com `<Search className="h-4 w-4">` à esquerda, `w-72`; estado local `q` filtra por nome/telefone no frontend
- Coluna telefone: `font-mono text-sm`
- Textarea inline → `<Textarea>` shadcn
- Empty state inline → `<EmptyState message="Nenhum cliente encontrado." />`
- `ActiveBadge` → `<StatusBadge active={...} />`
- Verificar API: se `visit_count` e `total_spent` existirem → adicionar colunas; se não → omitir

## Services

- Coluna duração: `<Clock className="h-3 w-3 text-muted-foreground" />` + `"{n} min"`
- Preço: `font-display text-lg text-primary`
- Verificar API: se serviço retornar profissionais → badges `variant="secondary"`; se não → omitir
- Textarea inline → `<Textarea>` shadcn

## Integrations

- G4 já aplicou `font-display` nos títulos — confirmar
- QR code: `w-48 h-48` → `max-w-[12rem] w-full aspect-square`

## Settings — Hub page (criar `settings/page.tsx`)

```tsx
import Link from "next/link"
import { Building2, KeyRound, ChevronRight } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"

const sections = [
  {
    href: "/dashboard/settings/profile",
    icon: Building2,
    title: "Perfil da empresa",
    description: "Dados, identidade visual, galeria e informações de contato",
  },
  {
    href: "/dashboard/settings/security",
    icon: KeyRound,
    title: "Segurança",
    description: "Alterar senha e configurações de acesso",
  },
]

export default function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="font-display text-3xl tracking-wide">Configurações</h1>
        <p className="mt-1 text-sm text-muted-foreground">Gerencie as configurações da sua empresa</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {sections.map(s => (
          <Link key={s.href} href={s.href}>
            <Card className="h-full cursor-pointer transition-colors hover:border-primary">
              <CardContent className="flex items-start gap-4 p-6">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
                  <s.icon className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <p className="font-display text-lg">{s.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{s.description}</p>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
```

## Settings/Profile

- Emojis → Lucide (G5 já cobriu — confirmar)
- Success banner → tokens (G6 já cobriu — confirmar)
- Textareas inline → `<Textarea>` shadcn

## Sidebar

Atualizar item que aponta para `settings/profile`:
```tsx
{ title: "Configurações", url: "/dashboard/settings", icon: Settings }
```
Remover item "Segurança" separado se existir.

---

## Checklist de validação

- [ ] Search bar funcionando em Customers (filtro local)
- [ ] Campos condicionais verificados na API — decisão documentada no relatório
- [ ] `settings/page.tsx` criado e acessível em `/dashboard/settings`
- [ ] Sidebar aponta para `/dashboard/settings`
- [ ] `npx tsc --noEmit` sem erros

---

## Relatório de conclusão

**Status:** ⬜ Pendente

**Arquivos modificados:**

**Arquivos criados:**

**Campos condicionais verificados:**
- `visit_count` / `total_spent`: disponível? __ → decisão: __
- Profissionais por serviço: disponível? __ → decisão: __

**Desvios e decisões:**
