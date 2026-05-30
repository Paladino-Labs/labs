# Sprint F — Vitrine Pública

**Grupo:** G12
**Pré-requisito:** Sprint E ✅
**Risco:** Médio (mudança estrutural de layout; superfície pública visível a clientes finais)

---

## Antes de começar

- [ ] Sprint E marcado como ✅ no README
- [ ] Ler `painel/CLAUDE.md`
- [ ] Ler `painel/app/book/[slug]/page.tsx` **na íntegra**
- [ ] Ler referência: `barberflow-system/src/routes/b.$slug.index.tsx`
- [ ] Testar `/book/{slug}` no browser antes de começar (estado atual como baseline)
- [ ] `BookingFlow.tsx` fora do escopo — não tocar

## Escopo

```
painel/app/book/[slug]/page.tsx
```

---

## Layout 2 colunas

```tsx
<div className="mx-auto max-w-6xl px-6 py-10 grid gap-10 lg:grid-cols-[1fr_320px]">
  <main className="space-y-10">
    {/* Hero, galeria, tabs */}
  </main>
  <aside className="space-y-6 lg:sticky lg:top-6 lg:self-start">
    {/* InfoCards */}
  </aside>
</div>
```

## Componente InfoCard (inline na página)

```tsx
function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <h2 className="label-eyebrow mb-3">{title}</h2>
      {children}
    </section>
  )
}
```

## Aside — mover do body para o aside

Conteúdo já existe na página — reorganizar, não recriar dados:

- `InfoCard "Localização"`: `<MapPin className="h-4 w-4" />` + endereço (link Google Maps)
- `InfoCard "Horário de atendimento"`: lista de dias; hoje em destaque com `<Badge variant="outline">Hoje</Badge>`
- `InfoCard "Formas de pagamento"`: badges `variant="outline"`
- `InfoCard "Contato"`: `<Phone className="h-4 w-4" />` + número
- `InfoCard "Redes sociais"`: icon buttons `hover:border-primary hover:text-primary transition-colors`

## Tabs na seção main

```tsx
<Tabs defaultValue="services">
  <TabsList>
    <TabsTrigger value="services">Serviços</TabsTrigger>
    <TabsTrigger value="professionals">Barbeiros</TabsTrigger>
    <TabsTrigger value="reviews">Avaliações</TabsTrigger>
  </TabsList>
  <TabsContent value="services">
    {/* cards de serviço existentes */}
  </TabsContent>
  <TabsContent value="professionals">
    {/* cards de barbeiro */}
  </TabsContent>
  <TabsContent value="reviews">
    <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
      Avaliações em breve.
    </div>
  </TabsContent>
</Tabs>
```

## Galeria responsiva

```tsx
<section className="grid gap-3 sm:grid-cols-[2fr_1fr]">
  <img src={photos[0]} className="h-80 w-full rounded-lg object-cover border border-border" />
  <div className="grid grid-cols-3 gap-3 sm:grid-cols-1">
    {photos.slice(1, 4).map(src => (
      <img key={src} src={src}
        className="h-24 sm:h-[calc((20rem-0.75rem*2)/3)] w-full rounded-lg object-cover border border-border" />
    ))}
  </div>
</section>
```

## SVGs inline → Lucide

Substituir os 8 SVGs inline:
`<Instagram>` `<Facebook>` `<Music2>` (TikTok) `<MapPin>` `<Clock>` `<Star>` `<Phone>` `<MessageCircle>` (WhatsApp)

## Rating

Campo `rating` não existe na API (confirmado no relatório de contratos).
- Não renderizar bloco de rating
- Se `google_review_url` existir: link externo `<Star className="h-4 w-4" />` + "Ver avaliações no Google"

## Verificações de G6

G6 já cobriu `text-white` e `#25D366` neste arquivo — confirmar que as substituições estão aplicadas.

## Preservar

- Botão "Agendar agora" e integração com `BookingFlow`
- Lógica de `online_booking_enabled`
- Dados do `/booking/{slug}/profile`
- Fixed button mobile (scroll de agendamento)

---

## Checklist de validação

- [ ] Layout 2 colunas em desktop (main + aside sticky)
- [ ] 1 coluna em mobile
- [ ] Aside com 5 InfoCards renderizando
- [ ] Tabs Serviços / Barbeiros / Avaliações funcionando
- [ ] Galeria responsiva: hero grande + thumbs
- [ ] Zero SVGs inline
- [ ] Zero `text-white` ou cores hardcoded
- [ ] Botão "Agendar" abrindo BookingFlow normalmente
- [ ] `BookingFlow.tsx` não tocado
- [ ] Testar em viewport mobile (375px) — aside não aparece, layout não quebra
- [ ] `npx tsc --noEmit` sem erros

---

## Relatório de conclusão

**Status:** ⬜ Pendente

**Arquivos modificados:**

**Desvios e decisões:**

**`google_review_url` disponível na API?** __
