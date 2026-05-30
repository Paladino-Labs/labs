# Sprint B — Correções Transversais

**Grupos:** G4 · G5 · G6
**Pré-requisito:** Sprint A ✅
**Risco:** Baixo

---

## Antes de começar

- [ ] Sprint A marcado como ✅ no README
- [ ] Ler `painel/CLAUDE.md`
- [ ] `BookingFlow.tsx` fora do escopo — não tocar

## Escopo

```
painel/app/page.tsx
painel/app/(dashboard)/**/*.tsx     ← todas as páginas do painel
painel/components/AgendaCalendar.tsx
painel/app/book/[slug]/page.tsx
```

---

## G4 — `.font-display` em todos os headings

```bash
grep -rn "text-2xl font-bold\|text-3xl tracking-wide\|text-4xl\|text-5xl\|text-6xl" \
  painel/app/\(dashboard\)/ painel/app/page.tsx
```

Para cada ocorrência em `<div>` ou `<p>` sem `font-display`, adicionar a classe.
Não remover `tracking-*` existente.

| Antes | Depois |
|-------|--------|
| `"text-2xl font-bold"` | `"font-display text-2xl"` |
| `"text-3xl tracking-wide"` | `"font-display text-3xl tracking-wide"` |
| `"text-5xl ..."` | `"font-display text-5xl ..."` |

---

## G5 — Emojis → Lucide (exceto `BookingFlow.tsx`)

| Emoji | Lucide | Arquivo |
|-------|--------|---------|
| ✅ | `<CheckCircle2 className="h-4 w-4" />` | appointments |
| 🔄 | `<RefreshCw className="h-4 w-4" />` | appointments |
| ✕ | `<X className="h-4 w-4" />` | appointments |
| 📸 | `<Camera className="h-4 w-4" />` | settings/profile |
| 📅 | `<Calendar className="h-4 w-4" />` | settings/profile |
| 🎵 | `<Music2 className="h-4 w-4" />` | settings/profile |
| ⭐ | `<Star className="h-4 w-4" />` | settings/profile |

Botões de ação em tabelas: `<Button variant="ghost" size="icon">` envolvendo o ícone.

---

## G6 — Hardcoded colors → tokens (exceto `BookingFlow.tsx`)

**settings/profile — success banner:**
```
border-green-200 bg-green-50 text-green-700
→ border-success/40 bg-success/15 text-success
```

**book/[slug]/page.tsx — hero:**
```
text-white           → text-[color:var(--book-text)]
text-white/80        → text-[color:var(--book-text-secondary)]
text-white/60        → text-[color:var(--book-text-muted)]
#25D366 (WhatsApp)   → className="text-foreground hover:text-primary transition-colors"
```

**book/[slug]/page.tsx — inline styles de hover:**
```
onMouseEnter={e => { e.currentTarget.style.borderColor = "..." }}
→ remover handler; substituir por hover:border-primary na className
```

---

## Checklist de validação

- [ ] Zero headings `<div>`/`<p>` sem `font-display` nas páginas do painel
- [ ] Zero emojis funcionais fora de `BookingFlow.tsx`
- [ ] Zero `bg-green-*` / `text-green-*` em settings
- [ ] Zero `text-white` ou `#25D366` em `book/[slug]/page.tsx`
- [ ] Zero `onMouseEnter` manipulando `.style` diretamente
- [ ] `BookingFlow.tsx` não tocado
- [ ] `npx tsc --noEmit` sem erros

---

## Relatório de conclusão

**Status:** ⬜ Pendente

**Arquivos modificados:**

**Desvios e decisões:**

**Contagem de correções:**
- G4 font-display: _ instâncias
- G5 emojis: _ substituições
- G6 cores hardcoded: _ substituições
