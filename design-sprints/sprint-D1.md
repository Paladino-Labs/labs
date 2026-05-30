# Sprint D1 — Limpeza de Emojis Residuais

**Pré-requisito:** Sprint D ✅
**Risco:** Baixo
**Objetivo:** Garantir que nenhum emoji funcional sobrou no projeto antes do Sprint E.

---

## Antes de começar

- [ ] Sprint D marcado como ✅ no README
- [ ] Ler `painel/CLAUDE.md`
- [ ] `BookingFlow.tsx` fora do escopo — não tocar

## Escopo

Qualquer arquivo `.tsx` em `painel/app/` e `painel/components/`, exceto `BookingFlow.tsx`.

---

## Passo 1 — Inventário

Rodar o grep para encontrar todos os caracteres não-ASCII em arquivos TSX:

```bash
grep -Prn "[^\x00-\x7F]" painel/app/ painel/components/ --include="*.tsx" \
  | grep -v "BookingFlow"
```

Para cada ocorrência encontrada, classificar:

- **Emoji funcional** (ícone, label, botão) → substituir por Lucide
- **Texto legítimo** (português: ã, é, ê, ó, ç, etc.) → ignorar
- **String de dado** (nome de cidade, mensagem de erro, etc.) → ignorar

---

## Passo 2 — Substituições

Para cada emoji funcional encontrado, aplicar o mapeamento mais semântico:

| Contexto | Substituição sugerida |
|----------|-----------------------|
| Rede social / link externo | `<Globe>`, `<Link2>`, `<ExternalLink>` |
| Pessoa / usuário | `<User>` |
| Câmera / foto | `<Camera>` |
| Localização | `<MapPin>` |
| Telefone | `<Phone>` |
| Horário / tempo | `<Clock>` |
| Dinheiro / pagamento | `<CreditCard>` ou `<Banknote>` |
| Qualquer outro | escolher o Lucide mais semântico para o contexto |

Todos os ícones: `className="h-4 w-4"`. Em botões: `<Button variant="ghost" size="icon">`.

---

## Passo 3 — Verificação final

Rodar o grep novamente e confirmar que o resultado contém apenas texto legítimo em português:

```bash
grep -Prn "[^\x00-\x7F]" painel/app/ painel/components/ --include="*.tsx" \
  | grep -v "BookingFlow"
```

---

## Checklist de validação

- [ ] Zero emojis funcionais em qualquer arquivo do escopo
- [ ] `BookingFlow.tsx` não tocado
- [ ] `npx tsc --noEmit` sem erros

---

## Relatório de conclusão

**Status:** ⬜ Pendente

**Emojis encontrados e substituídos:**

| Arquivo | Emoji | Substituição | Contexto |
|---------|-------|-------------|----------|

**Texto legítimo ignorado (não-ASCII que não é emoji):**

**Desvios e decisões:**
