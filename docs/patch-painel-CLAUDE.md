# Patch — `painel/CLAUDE.md`

> Instruções para o Claude Code: adicionar as seções abaixo ao final do
> arquivo `painel/CLAUDE.md` existente, sem remover nem alterar o conteúdo atual.

---

## Sprints de design (espelhamento barberflow-system)

Consultar `design-sprints/README.md` para o protocolo completo e status de cada sprint.

### Decisões registradas

| Decisão | Justificativa |
|---------|--------------|
| Adotar "Barbeiros" na UI em vez de "Profissionais" | Produto focado em barbearia no Estágio 0; labels serão configuráveis por vertical no Estágio 1 |
| Hub `/settings` com cards para profile e security | Extensível para futuras seções; zero impacto em rotas existentes |
| `publicFetch<T>()` em `lib/api.ts` | Centraliza chamadas sem JWT do link público — exigência do brief |
| BookingFlow G13 em sprint separado | Step `AWAITING_SHIFT` é entidade da API; eliminação requer sprint de backend antes |
| Abordagem B no BookingFlow aprovada condicionalmente | Após sprint de backend que remove `AWAITING_SHIFT` do engine e simplifica para 4 steps |

### Nomenclatura (Estágio 0)

| Entidade (API/código) | Label na UI |
|-----------------------|-------------|
| `professionals` | Barbeiros |
| `settings/profile` | Perfil da empresa |
| `settings` (raiz) | Configurações |

### Campos condicionais à API

Renderizar com fallback `"Em breve"` (`text-xs text-muted-foreground opacity-50`)
se o campo não existir na resposta atual. Não criar dados mockados.

| Campo | Endpoint | Superfície |
|-------|---------|-----------|
| `visit_count` | `GET /customers/` | Clientes — coluna "Visitas" |
| `total_spent` | `GET /customers/` | Clientes — coluna "Total gasto" |
| Profissionais por serviço | `GET /services/` | Serviços — "Realizado por" |
| `working_days` | `GET /professionals/` | Barbeiros — dias da semana |
| `commission_rate` | `GET /professionals/` | Barbeiros — comissão |
| `specialties` | `GET /professionals/` | Barbeiros — especialidades |
| `rating`, `review_count` | `GET /booking/{slug}/profile` | Vitrine — rating no hero |

### O que NÃO fazer (acréscimos ao design)

- Não alterar `BookingFlow.tsx` — sprint G13 separado
- Não hardcodar cores (`text-white`, `#25D366`, `bg-green-*`, etc.)
- Não usar emojis como ícones — sempre Lucide
- Não usar inline styles para hover/focus — sempre classes Tailwind
