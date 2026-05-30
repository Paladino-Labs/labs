# Design Sprints — Protocolo

> Espelhamento do design `barberflow-system` no painel Paladino.
> G13 (BookingFlow) é sprint separado, condicionado a sprint de backend.

---

## Visão geral

| Sprint | Grupos | Escopo | Risco |
|--------|--------|--------|-------|
| [A](./sprint-A.md) | G1 + G2 + G3 | Fundação: tokens, componentes, api | Médio |
| [B](./sprint-B.md) | G4 + G5 + G6 | Cross-cutting: font-display, ícones, cores | Baixo |
| [C](./sprint-C.md) | G7 + G8 | Login + Dashboard | Baixo |
| [D](./sprint-D.md) | G9 | Clientes, Serviços, Integrações, Configurações | Baixo |
| [D1](./sprint-D1.md) | - | Limpeza: emojis residuais em todo o projeto | Baixo |
| [E](./sprint-E.md) | G10 + G11 | Barbeiros + Agenda | Alto |
| [F](./sprint-F.md) | G12 | Vitrine pública | Médio |

---

## Dependências entre sprints

```
A → B → C → D → D1 → E → F
```

Cada sprint deve ser concluído e validado antes do próximo iniciar.
Dentro do Sprint E, G10 e G11 podem ser feitos em sequência (arquivos distintos).

---

## Protocolo obrigatório por sprint

### Antes de começar
- [ ] Sprint anterior marcado como ✅ Concluído neste README
- [ ] `painel/CLAUDE.md` lido na íntegra
- [ ] Arquivos de referência do `barberflow-system/` indicados no sprint lidos
- [ ] Nenhum arquivo fora do escopo do sprint será tocado

### Durante a execução
- Executar grupos na ordem indicada no arquivo do sprint
- Não avançar para o próximo grupo sem concluir o atual
- Registrar no relatório de conclusão qualquer desvio ou decisão tomada

### Ao concluir
- [ ] `npx tsc --noEmit` sem erros
- [ ] Servidor de dev respondendo nas rotas afetadas
- [ ] Relatório de conclusão preenchido no arquivo do sprint
- [ ] Status do sprint atualizado neste README

---

## Status dos sprints

| Sprint | Status | Data | Observações |
|--------|--------|------|-------------|
| A | ✅ Concluído | 2026-05-29 | Todos os artefatos já existiam corretamente |
| B | ✅ Concluído | 2026-05-29 | Escopo expandido para subpáginas ([id], /new, /users) com as mesmas violações |
| C | ✅ Concluído | 2026-05-29 | date-fns instalado como nova dependência; grid era [1fr_300px] → [2fr_1fr] |
| D | ✅ Concluído | 2026-05-29 | Campos condicionais omitidos (visit_count, total_spent, profissionais por serviço ausentes da API); 👤 → <Globe> em settings/profile — verificar semântica |
| D1 | ✅ Concluído | 2026-05-29 | 5 emojis residuais encontrados e substituídos; ◆ e © preservados intencionalmente |
| E | ✅ Concluído | 2026-05-29 | AvatarInitials.tsx (PascalCase) consolidado em avatar-initials.tsx (canônico) com font-display e flex-shrink-0 absorvidos; filtro por tabs removido em favor do day picker; color dinâmico preservado em AgendaCalendar |
| F | ✅ Concluído | 2026-05-29 | Brand icons removidos no lucide-react v1.8 — Camera/Globe como substitutos; business_hours como string livre (highlight "Hoje" requer estrutura da API); profissionais públicos exigem service_id obrigatório |

---

## Restrições globais (válidas em todos os sprints)

- Nunca tocar em `BookingFlow.tsx` — sprint G13 separado
- Nunca alterar `CLAUDE.md` (backend) nem `painel/CLAUDE.md` — responsabilidade do owner
- Nunca usar `fetch` raw — sempre `lib/api.ts`
- Nunca hardcodar cores — sempre tokens semânticos
- Nunca usar emojis como ícones — sempre Lucide
- Nunca criar lógica de negócio no frontend
