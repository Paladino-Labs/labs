# Paladino — Documentação Técnica

Referência técnica completa do sistema Paladino.
Este conjunto de documentos é a fonte primária de verdade sobre
arquitetura, contratos, invariantes e comportamento do sistema.
Manuais de usuário, guias e docs públicas são derivados daqui.

**Versão do sistema:** 2.0 (Fase 2 concluída)
**Última atualização:** 2026-05-30
**HEAD das migrations:** `c2d3e4f5g6h7`

---

## Índice

| Documento | Conteúdo |
|-----------|----------|
| [architecture.md](architecture.md) | Stack, componentes, princípios de design, estrutura de diretórios |
| [security.md](security.md) | JWT, sessões, PII, criptografia, invalidação de sessão |
| [rbac.md](rbac.md) | Papéis, matriz de permissões, invariantes de escalonamento |
| [data-model.md](data-model.md) | Todas as entidades: campos, tipos, constraints, relações |
| [events.md](events.md) | Catálogo completo de eventos do sistema |
| [infrastructure.md](infrastructure.md) | Celery, Redis, EventBus, Alembic, RLS |
| [domains/agenda.md](domains/agenda.md) | FSM de agendamentos, reservas SOFT/FIRME, conflitos |
| [domains/financial-core.md](domains/financial-core.md) | Contas, Movements, Entries, invariantes de imutabilidade |
| [domains/payments.md](domains/payments.md) | PaymentsEngine FSM, webhook idempotente, DepositPolicy |
| [domains/communication.md](domains/communication.md) | Templates, canais, quiet hours, eventos de notificação |
| [domains/booking-flow.md](domains/booking-flow.md) | FSM público, 4 steps, reserva SOFT no checkout |
| [api-reference.md](api-reference.md) | Todos os endpoints: método, path, autenticação, contratos |
| [integrations.md](integrations.md) | Asaas, Evolution API (WhatsApp), SMTP |
| [roadmap.md](roadmap.md) | O que existe, o que está planejado por fase |

---

## Convenções deste documento

- **Invariante:** regra que nunca pode ser violada, enforçada no banco ou no ORM.
- **Contrato:** interface pública de um serviço ou endpoint.
- **Handler:** função registrada para reagir a um evento.
- **[SCHEMA ONLY]:** entidade existe no banco mas sem lógica de negócio ainda.
- **🔒 Auditado:** ação gera registro em `audit_logs`.
- **⚡ Crítico:** falha aqui tem impacto direto em dinheiro ou dados do cliente.

---

## Como manter este documento

Ao final de cada sprint, atualizar os arquivos afetados:
- Novos modelos → `data-model.md`
- Novos eventos → `events.md`
- Novos endpoints → `api-reference.md`
- Mudanças em domínio → arquivo do domínio correspondente
- Mudanças de infra → `infrastructure.md`

O prompt de execução de cada sprint deve incluir:
> "Ao emitir o sinal de conclusão, listar quais arquivos de docs/
> precisam ser atualizados e com qual conteúdo."