# BookingFlow — Fluxo Público de Agendamento

## Responsabilidade

O BookingFlow é o fluxo de agendamento acessível sem autenticação
pelo link público `[domínio]/book/[slug]`. Gerencia sessões de
checkout via FSM e cria agendamentos no sistema ao confirmar.

---

## FSM de Sessão (SrvState)

```python
class SrvState(str, Enum):
    IDLE                 = "IDLE"
    AWAITING_SERVICE     = "AWAITING_SERVICE"
    AWAITING_PROFESSIONAL= "AWAITING_PROFESSIONAL"
    AWAITING_DATE        = "AWAITING_DATE"
    AWAITING_TIME        = "AWAITING_TIME"
    AWAITING_CUSTOMER    = "AWAITING_CUSTOMER"
    AWAITING_CONFIRMATION= "AWAITING_CONFIRMATION"
    CONFIRMED            = "CONFIRMED"
    CANCELLED            = "CANCELLED"
```

**Estados removidos:** `AWAITING_SHIFT` e `SELECT_SHIFT` não existem
no FSM (removidos no Sprint Backend BookingFlow e G13).

### Transições

```
IDLE → AWAITING_SERVICE (start)
AWAITING_SERVICE → AWAITING_PROFESSIONAL (SELECT_SERVICE)
AWAITING_PROFESSIONAL → AWAITING_DATE (SELECT_PROFESSIONAL)
AWAITING_DATE → AWAITING_TIME (SELECT_DATE)
AWAITING_TIME → AWAITING_CUSTOMER (SELECT_TIME)
AWAITING_CUSTOMER → AWAITING_CONFIRMATION (SUBMIT_CUSTOMER)
AWAITING_CONFIRMATION → CONFIRMED (CONFIRM)
* → CANCELLED (CANCEL ou expiração)
```

---

## Endpoints Públicos (FSM)

```
POST /booking/{slug}/start
  → Cria WebBookingSession, retorna token + estado inicial
  → Estado: AWAITING_SERVICE

POST /booking/{slug}/update
  Body: { token, action, payload }
  → Avança o FSM conforme a ação
  → Retorna { state, options, session_data }

GET /booking/{slug}/session/{token}
  → Retorna estado atual da sessão

GET /booking/{slug}/info
GET /booking/{slug}/profile
GET /booking/{slug}/services
GET /booking/{slug}/professionals
GET /booking/{slug}/dates
GET /booking/{slug}/slots
POST /booking/{slug}/confirm
GET /booking/{slug}/appointments
PATCH /booking/{slug}/appointments/{id}/cancel
```

---

## WebBookingSession

```
token           VARCHAR(64) UNIQUE NOT NULL   # identificador da sessão
company_id      UUID FK → companies
state           VARCHAR NOT NULL              # estado atual do FSM
session_data    JSONB                         # dados acumulados
expires_at      TIMESTAMPTZ                   # TTL da sessão de checkout
created_at      TIMESTAMPTZ DEFAULT now()
updated_at      TIMESTAMPTZ
```

---

## Mapeamento FSM → Steps UI (Frontend)

| Estado FSM | Step UI | Rótulo |
|-----------|---------|--------|
| AWAITING_SERVICE | 1 | Serviço |
| AWAITING_PROFESSIONAL | 2 | Barbeiro |
| AWAITING_DATE | 3 | Horário |
| AWAITING_TIME | 3 | Horário |
| AWAITING_CUSTOMER | 4 | Confirmar |
| AWAITING_CONFIRMATION | 4 | Confirmar |
| IDLE, CONFIRMED, CANCELLED | — | Fora do stepper |

Date e Time compartilham o Step 3 (picker de 14 dias + slots na mesma tela).

---

## Comportamento do Frontend (BookingFlow.tsx)

### Pré-seleção de serviço
Na vitrine (`book/[slug]/page.tsx`), o botão "Agendar" ao lado de
cada serviço seta `initialServiceId` e abre o BookingFlow.

No BookingFlow, um `useEffect` monitora `session?.state === "AWAITING_SERVICE"`:
se `initialServiceId` está presente e ainda não foi auto-selecionado
(controlado por `useRef`), dispara `dispatch("SELECT_SERVICE", { service_id })`.
O ref garante que o auto-select ocorre apenas uma vez.

### Dias sem horários
Quando `session.state === "AWAITING_TIME"` e `session.options.length === 0`:
- `selectedDate` é resetado para `null`
- Mensagem: "Sem horários disponíveis neste dia. Escolha outra data."
- Cobre tanto dias fechados quanto dias com agenda cheia

### Dívida conhecida
`business_hours` retorna string livre — impossível filtrar dias fechados
visualmente antes da seleção. Solução definitiva: backend retornar
`business_hours_structured: [{weekday, open, close}]`.

---

## Vitrine (page.tsx)

Página pública sem autenticação. Exibe:
- Logo, nome, bio da barbearia
- Horários de funcionamento (string livre)
- Lista de serviços com preço, duração e botão "Agendar"
- Lista de profissionais
- Links para redes sociais (Instagram, Facebook, TikTok, website)
- CTA "Agendar agora" (botão hero — abre BookingFlow sem pré-seleção)

Usa `publicFetch` (sem Authorization header) para todos os endpoints.