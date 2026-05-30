# Sprint E — Barbeiros + Agenda

**Grupos:** G10 · G11
**Pré-requisito:** Sprint D ✅
**Risco:** Alto (AgendaCalendar.tsx tem 760 linhas — ler antes de tocar)

---

## Antes de começar

- [ ] Sprint D marcado como ✅ no README
- [ ] Ler `painel/CLAUDE.md`
- [ ] Ler `painel/components/AgendaCalendar.tsx` **na íntegra** antes de qualquer edição
- [ ] Ler referência barbeiros: `barberflow-system/src/routes/_authenticated.app.barbeiros.tsx`
- [ ] Ler referência agenda: `barberflow-system/src/routes/_authenticated.app.agenda.tsx`
- [ ] Verificar contratos de API para campos condicionais de barbeiros (ver `painel/CLAUDE.md`)

## Escopo

```
painel/app/(dashboard)/professionals/page.tsx
painel/app/(dashboard)/appointments/page.tsx
painel/components/AgendaCalendar.tsx
```

---

## G10 — Barbeiros (`professionals/page.tsx`)

Label no sidebar e no header da página: **"Barbeiros"**.

Substituir tabela por grid de cards:

```tsx
<div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
  {professionals.map(p => (
    <Card key={p.id}>
      <CardContent className="p-6 space-y-4">

        {/* Avatar + nome + horário */}
        <div className="flex items-center gap-4">
          <AvatarInitials name={p.name} size="lg" />
          <div>
            <p className="font-semibold">{p.name}</p>
            <p className="text-xs text-muted-foreground">
              {p.work_start ?? "—"} – {p.work_end ?? "—"}
            </p>
          </div>
        </div>

        {/* Especialidades */}
        <div className="flex flex-wrap gap-1">
          {p.specialties?.length > 0
            ? p.specialties.map(s => (
                <Badge key={s} variant="secondary" className="text-[10px]">{s}</Badge>
              ))
            : <span className="text-[10px] text-muted-foreground opacity-50">Especialidades em breve</span>
          }
        </div>

        {/* Dias da semana */}
        <div className="flex flex-wrap gap-1">
          {p.working_days
            ? ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"].map((l, i) => (
                <span key={l} className={cn(
                  "flex h-6 w-8 items-center justify-center rounded text-[10px]",
                  p.working_days.includes(i) ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground"
                )}>{l}</span>
              ))
            : <span className="text-[10px] text-muted-foreground opacity-50">Horários em breve</span>
          }
        </div>

        {/* Comissão */}
        <div className="flex items-center justify-between border-t border-border pt-4">
          <span className="text-xs text-muted-foreground">Comissão</span>
          {p.commission_rate != null
            ? <span className="font-display text-xl text-primary">{p.commission_rate}%</span>
            : <span className="text-xs text-muted-foreground opacity-50">Em breve</span>
          }
        </div>

      </CardContent>
    </Card>
  ))}
</div>
```

Preservar ações de criar / ativar / desativar profissional.

---

## G11 — Agenda (refatorar, não reescrever)

### Header da página (`appointments/page.tsx`)

```tsx
<div className="flex items-center justify-between">
  <div>
    <h1 className="font-display text-3xl tracking-wide">Agenda</h1>
    <p className="text-sm text-muted-foreground">
      {format(weekStart, "d MMM", { locale: ptBR })} –{" "}
      {format(weekEnd, "d MMM yyyy", { locale: ptBR })}
    </p>
  </div>
  <div className="flex items-center gap-2">
    <Button variant="outline" size="icon" onClick={prev}><ChevronLeft className="h-4 w-4" /></Button>
    <Button variant="outline" onClick={goToToday}>Hoje</Button>
    <Button variant="outline" size="icon" onClick={next}><ChevronRight className="h-4 w-4" /></Button>
  </div>
</div>
```

### Day picker (substituir MiniCalendar)

```tsx
<div className="grid grid-cols-7 gap-2">
  {days.map(d => {
    const count = appts.filter(a => isSameDay(new Date(a.start_at), d)).length
    const active = isSameDay(d, selectedDay)
    return (
      <button key={d.toISOString()} onClick={() => setSelectedDay(d)}
        className={cn(
          "flex flex-col items-center rounded-lg border p-3 transition-colors",
          active ? "border-primary bg-primary/10" : "border-border hover:bg-accent"
        )}>
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
          {format(d, "EEE", { locale: ptBR })}
        </span>
        <span className="font-display text-2xl">{format(d, "d")}</span>
        <span className="text-[10px] text-muted-foreground">{count} agend.</span>
      </button>
    )
  })}
</div>
```

### `AgendaCalendar.tsx` — correções pontuais

- `fontSize: 11` (inline style) → `className="text-[11px]"`
- `fontSize: 10` (inline style) → `className="text-[10px]"`
- Botões emoji → Lucide (G5 já cobriu — confirmar aplicação aqui)
- **Não remover** WeekView / DayView / HourGrid / NowLine — preservar lógica intacta

---

## Checklist de validação

- [ ] Label "Barbeiros" no sidebar e no header da página
- [ ] Grid de cards renderizando (sem erros mesmo com campos condicionais ausentes)
- [ ] Ações de criar/ativar/desativar preservadas
- [ ] Agenda: day picker de 7 dias funcional
- [ ] Agenda: navegação entre semanas (prev/hoje/next) funcionando
- [ ] Agenda: agendamentos visíveis no grid
- [ ] Zero `fontSize` inline em `AgendaCalendar.tsx`
- [ ] `npx tsc --noEmit` sem erros

---

## Relatório de conclusão

**Status:** ⬜ Pendente

**Arquivos modificados:**

**Campos condicionais de barbeiros verificados:**
- `working_days`: disponível? __ → decisão: __
- `commission_rate`: disponível? __ → decisão: __
- `specialties`: disponível? __ → decisão: __

**Desvios e decisões:**
