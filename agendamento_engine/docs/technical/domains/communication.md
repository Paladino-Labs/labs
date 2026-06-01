# Communication — Domínio de Comunicação

## Responsabilidade

O domínio de Comunicação gerencia o envio de notificações para
clientes e funcionários. Opera como consumidor de eventos de outros
domínios — nunca é chamado diretamente dentro de transações.

---

## Princípio de Isolamento

```
PaymentsEngine.confirm() → COMMIT → EventBus.publish("payment.confirmed")
                                           ↓
                              CommunicationHandler (best-effort)
                                           ↓
                                CommunicationService.send_transactional()
```

Falha no envio de notificação não afeta o domínio de negócio.

---

## CommunicationService

`app/modules/communication/service.py`

Centraliza o envio de mensagens. Verifica:
1. Feature flag do canal (`use_communication_service`)
2. Quiet hours (não envia em horário silencioso — agenda para depois)
3. Template ativo para o evento
4. Canal disponível (WhatsApp, E-mail)

---

## CommunicationSetting

```
company_id          UUID FK → companies
canal               VARCHAR    # WHATSAPP | EMAIL
quiet_hours_start   TIME nullable
quiet_hours_end     TIME nullable
feature_flag        BOOLEAN DEFAULT false
  -- false = canal desabilitado; true = usa CommunicationService
use_communication_service BOOLEAN DEFAULT false
```

**Quiet hours:** mensagens agendadas fora do horário silencioso são
enfileiradas (status SCHEDULED) e enviadas quando o horário abre.
Não são descartadas.

---

## CommunicationTemplate

```
template_id     UUID PK
company_id      UUID FK → companies
event_type      VARCHAR NOT NULL    # ex: "appointment.confirmed"
channel         VARCHAR NOT NULL    # WHATSAPP | EMAIL
body_template   TEXT NOT NULL       # Jinja2 / mustache com variáveis
is_active       BOOLEAN DEFAULT true
is_default      BOOLEAN DEFAULT false
```

**Template default:** não pode ser deletado (HTTP 400).
**Override:** tenants podem criar templates customizados por event_type.

---

## CommunicationLog

```
log_id          UUID PK
company_id      UUID FK → companies
customer_id     UUID nullable FK → customers
event_type      VARCHAR
channel         VARCHAR
status          VARCHAR    # SENT | SCHEDULED | FAILED
sent_at         TIMESTAMPTZ nullable
scheduled_for   TIMESTAMPTZ nullable
error_message   TEXT nullable
created_at      TIMESTAMPTZ DEFAULT now()
```

---

## Eventos com Notificação

| Evento | Destinatário | Canal padrão |
|--------|-------------|--------------|
| `appointment.confirmed` | Cliente | WhatsApp + E-mail |
| `appointment.cancelled` | Cliente | WhatsApp |
| `appointment.reminder_24h` | Cliente | WhatsApp |
| `appointment.reminder_1h` | Cliente | WhatsApp |
| `payment.confirmed` | Cliente | WhatsApp + E-mail |
| `payment.refunded` | Cliente | E-mail |
| `auth.password_reset_requested` | Usuário | E-mail |

---

## Canais

**WhatsApp:** via Evolution API (self-hosted) ou WhatsApp Business API.
Configurado em `IntegrationCredential` (provider=WHATSAPP_EVOLUTION ou WHATSAPP_META).

**E-mail:** via SMTP. Configurado em `IntegrationCredential` (provider=SMTP).

---

## Workers Celery

| Task | Schedule | Função |
|------|----------|--------|
| `communication_worker` | sob demanda | Envio imediato de mensagens |
| `reminder_worker` | */30 min | Lembretes 24h e 1h antes |

Flags de idempotência em Appointment:
- `reminder_24h_sent BOOLEAN DEFAULT false`
- `reminder_1h_sent BOOLEAN DEFAULT false`

O worker seta o flag antes de enviar. Race condition entre dois workers:
quem chegar primeiro seta o flag; o segundo vê `True` e pula.