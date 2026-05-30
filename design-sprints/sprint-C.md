# Sprint C — Login + Dashboard

**Grupos:** G7 · G8
**Pré-requisito:** Sprint B ✅
**Risco:** Baixo

---

## Antes de começar

- [ ] Sprint B marcado como ✅ no README
- [ ] Ler `painel/CLAUDE.md`
- [ ] Ler referência login: `barberflow-system/src/routes/login.tsx`
- [ ] Ler referência dashboard: `barberflow-system/src/routes/_authenticated.app.index.tsx`

## Escopo

```
painel/app/page.tsx
painel/app/(dashboard)/dashboard/page.tsx
```

---

## G7 — Login (`app/page.tsx`)

Layout 2 colunas. **Preservar toda lógica de auth** — apenas redesenhar a UI.

```tsx
<div className="grid min-h-screen lg:grid-cols-2">

  {/* Esquerda — só desktop */}
  <div className="hidden flex-col justify-between bg-sidebar p-12 lg:flex">
    <div className="flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
        <Sparkles className="h-4 w-4" />
      </div>
      <span className="font-display text-2xl tracking-wider">PALADINO</span>
    </div>
    <div>
      <h1 className="font-display text-5xl leading-tight">
        Sua agenda,<br />sua equipe,<br />seu caixa.
      </h1>
      <p className="mt-4 max-w-sm text-muted-foreground">
        Tudo em um painel feito para barbearias. Sem planilhas, sem atrito.
      </p>
    </div>
    <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} Paladino</p>
  </div>

  {/* Direita — form */}
  <div className="flex items-center justify-center p-6">
    <div className="w-full max-w-sm space-y-6">
      <div>
        <h2 className="font-display text-3xl">Entrar</h2>
        <p className="mt-1 text-sm text-muted-foreground">Acesse o painel da sua barbearia</p>
      </div>
      {/* form com Label + Input shadcn + Button shadcn type="submit" */}
      {/* preservar: handleSubmit, loading state, error message, redirect */}
    </div>
  </div>

</div>
```

`<button>` nativo → `<Button type="submit" className="w-full">` shadcn.

---

## G8 — Dashboard (3 ajustes pontuais, não recriar)

**1. Eyebrow com data** (importar `format` de `date-fns` e `ptBR`):
```tsx
<div className="flex items-center gap-3 text-[11px] uppercase tracking-[0.32em] text-primary/85">
  <span className="h-px w-8 bg-primary/50" />
  <span>Overview · {format(new Date(), "EEEE, d 'de' MMMM", { locale: ptBR })}</span>
  <span className="h-px w-8 bg-primary/50" />
</div>
```

**2. Nome em itálico no greeting:**
```tsx
<h1 className="font-display text-5xl md:text-6xl tracking-tight">
  {greeting}, <em>{firstName}.</em>
</h1>
```

**3. Grid corpo:**
```tsx
<section className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
```

---

## Checklist de validação

- [ ] Login: layout 2 colunas em desktop, 1 em mobile
- [ ] Login: coluna esquerda com `bg-sidebar`
- [ ] Login: `<Button>` shadcn (não `<button>` nativo)
- [ ] Login: fluxo de auth funcionando de ponta a ponta
- [ ] Dashboard: eyebrow com data em ptBR
- [ ] Dashboard: nome do usuário em itálico
- [ ] Dashboard: grid `lg:grid-cols-[2fr_1fr]`
- [ ] `npx tsc --noEmit` sem erros

---

## Relatório de conclusão

**Status:** ⬜ Pendente

**Arquivos modificados:**

**Desvios e decisões:**
