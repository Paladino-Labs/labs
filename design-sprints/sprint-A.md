# Sprint A — Fundação

**Grupos:** G1 · G2 · G3
**Pré-requisito:** nenhum (primeiro sprint)
**Risco:** Médio (G1 toca `globals.css`; G3 toca código de produção)

---

## Antes de começar

- [ ] Ler `painel/CLAUDE.md` na íntegra
- [ ] Ler `painel/app/globals.css` na íntegra
- [ ] Ler `painel/lib/api.ts` na íntegra
- [ ] Ler `painel/app/book/[slug]/page.tsx` na íntegra
- [ ] Aplicar o patch `patch-painel-CLAUDE.md` ao final de `painel/CLAUDE.md`
- [ ] Nenhum arquivo fora do escopo será tocado

## Escopo

```
painel/app/globals.css
painel/lib/api.ts
painel/app/book/[slug]/page.tsx     ← só substituir apiFetch local
painel/components/empty-state.tsx   ← criar
painel/components/avatar-initials.tsx ← criar
painel/components/status-badge.tsx  ← criar
painel/components/ui/textarea.tsx   ← criar via shadcn CLI
painel/CLAUDE.md                    ← aplicar patch (append)
```

---

## G1 — Tokens CSS (`globals.css`)

Adicionar dentro do bloco `.book-page`:

```css
--book-gradient-gold: linear-gradient(135deg, oklch(0.70 0.080 80), oklch(0.55 0.070 70));
```

Depois, grep por variáveis usadas mas não declaradas:

```bash
grep -rn "var(--book-" painel/app/book/[slug]/
```

Cruzar com o que está em `.book-page`. Declarar qualquer ausente com valor OKLCH equivalente ao mais próximo do sistema.

---

## G2 — Componentes compartilhados (criar, não usar ainda)

**Textarea:**
```bash
cd painel && npx shadcn@latest add textarea
```

**`components/empty-state.tsx`:**
```tsx
import { cn } from "@/lib/utils"

export function EmptyState({ message, className }: { message: string; className?: string }) {
  return (
    <div className={cn("text-center text-sm italic text-muted-foreground py-10", className)}>
      {message}
    </div>
  )
}
```

**`components/avatar-initials.tsx`:**
```tsx
import { cn } from "@/lib/utils"

const sizes = { sm: "h-8 w-8 text-xs", md: "h-9 w-9 text-xs", lg: "h-14 w-14 text-sm" }

export function AvatarInitials({
  name, size = "md", className
}: { name: string; size?: "sm" | "md" | "lg"; className?: string }) {
  const initials = name.split(" ").map(n => n[0]).slice(0, 2).join("").toUpperCase()
  return (
    <div className={cn(
      "rounded-full bg-primary/15 text-primary font-medium flex items-center justify-center shrink-0",
      sizes[size], className
    )}>
      {initials}
    </div>
  )
}
```

**`components/status-badge.tsx`:**
```tsx
import { Badge } from "@/components/ui/badge"

export function StatusBadge({
  active, labelActive = "Ativo", labelInactive = "Inativo"
}: { active: boolean; labelActive?: string; labelInactive?: string }) {
  return (
    <Badge variant={active ? "default" : "secondary"}>
      {active ? labelActive : labelInactive}
    </Badge>
  )
}
```

---

## G3 — Consolidação `lib/api.ts`

Verificar se já existe função para chamadas sem JWT. Se não:

```ts
// Adicionar ao final de lib/api.ts
// Chamadas públicas (sem JWT) — usado em /book/[slug]/
export async function publicFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({}))
    throw new Error(error?.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}
```

Em `app/book/[slug]/page.tsx`: localizar `apiFetch` ou `fetch` raw locais e substituir por `publicFetch` de `@/lib/api`. Preservar toda lógica de dados e renderização.

**Não tocar em `BookingFlow.tsx`.**

---

## Checklist de validação

- [ ] `--book-gradient-gold` declarada em `.book-page`
- [ ] Nenhuma `var(--book-*)` sem declaração
- [ ] `components/ui/textarea.tsx` existe
- [ ] `components/empty-state.tsx` exporta `EmptyState`
- [ ] `components/avatar-initials.tsx` exporta `AvatarInitials`
- [ ] `components/status-badge.tsx` exporta `StatusBadge`
- [ ] `lib/api.ts` exporta `publicFetch`
- [ ] `book/[slug]/page.tsx` sem `apiFetch` local nem `fetch` raw
- [ ] `BookingFlow.tsx` não tocado
- [ ] `painel/CLAUDE.md` com o patch aplicado
- [ ] `npx tsc --noEmit` sem erros
- [ ] `/book/{slug}` respondendo sem erros de console

---

## Relatório de conclusão

**Status:** ⬜ Pendente

**Arquivos modificados:**

**Arquivos criados:**

**Desvios e decisões:**

**`var(--book-*)` ausentes encontrados:**
