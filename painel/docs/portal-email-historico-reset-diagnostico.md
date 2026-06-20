# Diagnóstico — E-mail, histórico por telefone (Portal) e reset de senha

**Status:** diagnóstico/handoff (não implementado nesta sessão).
**Data:** 2026-06-19.

Três pontos levantados em teste do Portal do Cliente. Naturezas diferentes:
config, gap de backend e bug de frontend.

---

## #1 — E-mail de confirmação/reset não chega → AMBIENTAL (não é bug)

Em dev, **nenhum provedor de e-mail está configurado**: `.env` local não tem
`MAILTRAP_API_TOKEN` nem `SMTP_HOST`; os defaults em `config.py` são vazios
(`MAILTRAP_API_TOKEN=""`, `SMTP_HOST=""`, `EMAIL_PROVIDER="mailtrap"`).

- `_send_portal_email` (registro do portal) e o envio de reset levantam
  `RuntimeError("Email não configurado…")`, capturado como **best-effort** →
  nada é enviado, mas o fluxo segue e a UI mostra "enviamos um e-mail" (intencional —
  não revela se o e-mail existe).
- **Ação:** nenhuma de código. Em produção, configurar `EMAIL_PROVIDER` + chave
  (Mailtrap HTTP ou SendGrid; Railway bloqueia SMTP) — já consta no checklist de
  deploy (`agendamento_engine/docs/conformidade-estagio-0.md` §8). Para testar local,
  setar `MAILTRAP_API_TOKEN` (+ `MAILTRAP_SANDBOX_INBOX_ID`) e checar a inbox do Mailtrap.

---

## #2 — Histórico/agendamentos não aparecem por telefone no Portal → GAP de backend

O portal resolve TODO o histórico por `customers.identity_id == identity`
(`portal/service.py::_customers_for_identity`). Mas:

- `register` (`portal/auth_service.py`) só chama `resolver.resolve(...)`, que cria/acha
  a **PaladinoIdentity global** — **não vincula** os `Customer` já existentes.
- O vínculo `Customer.identity_id` só ocorre em (a) operações do tenant via
  `resolver.resolve_for_tenant` (criar cliente, booking, bot — lazy backfill) ou
  (b) `scripts/backfill_identity.py`, que **nunca foi executado**.

**Consequência:** cliente que já tinha agendamentos (Customer com `identity_id=NULL`)
e se registra no Portal **não vê** o histórico até o backfill rodar ou até uma nova
operação no tenant religar o `identity_id`.

**Resolução (duas frentes):**
1. **Backfill pós-deploy:** rodar `scripts/backfill_identity.py` (operação de
   manutenção já prevista desde o Sprint 25). Resolve os clientes existentes.
2. **Vínculo no registro (Estágio 1+, não-trivial):** fazer `register` ligar
   `Customer` por telefone (E.164) à identidade no cadastro. É **cross-tenant** e
   esbarra em **RLS** (`app.current_company_id` não está setado no contexto do portal,
   que é sem company) — exige bypass controlado de RLS ou varredura por tenant.
   **Não entra pré-push.**

---

## #3 — Reset de senha não funciona → BUG de frontend (`/reset-password`) — ✅ CORRIGIDO (2026-06-19)

> **Implementado nesta sessão:** `/reset-password` agora exibe campo de código de 6
> dígitos quando não há `?token=` na URL, envia os 3 campos obrigatórios
> (`token`, `new_password`, `new_password_confirm`) e trata 400/404/410 e 422. O texto
> abaixo é o diagnóstico original que motivou o fix.

O backend está correto: `forgot_password` gera um **código de 6 dígitos** (token de
redefinição, `random.choices(string.digits, k=6)`) e o endpoint
`POST /auth/reset-password` espera o schema:

```
ResetPasswordRequest { token: str, new_password: str, new_password_confirm: str }
```

A tela `painel/app/reset-password/page.tsx` tem **dois defeitos**:

1. **Não há campo para o código.** A página lê o token só da URL
   (`searchParams.get("token")`); sem `?token=` mostra "Link inválido". Mas o e-mail
   entrega um **código avulso de 6 dígitos** (contexto `{"token": raw_token}`), **sem
   link** — então não há onde digitá-lo. (A página foi feita para um fluxo de link
   mágico que o backend não usa.)
2. **Payload incompleto.** O submit envia `{ token, new_password }` e **omite**
   `new_password_confirm`, que é **obrigatório** no schema → **422 mesmo com token
   válido** (a página interpreta o 422 como "token inválido").

**Fluxo correto (duas páginas):**
- `/forgot-password` (já existe) — pede o e-mail, dispara o código.
- `/reset-password` — deve aceitar **código (6 dígitos) + nova senha + confirmar**.

**Tarefa para o executor:**
- Em `/reset-password`, adicionar um **input de código de 6 dígitos** usado quando não
  houver `?token=` na URL (entrada manual; o e-mail manda código, não link). O valor do
  código vira o campo `token` do payload.
- Incluir `new_password_confirm` no `POST /auth/reset-password` (hoje ausente).
- Manter a validação client-side de senha (8+ chars, 1 maiúscula, 1 número) — espelha
  o `field_validator` do `ResetPasswordRequest`.
- Confirmar o shape no `openapi.json` antes (campos: `token`, `new_password`,
  `new_password_confirm`).
- Erros: 400/404/410 → "código inválido ou expirado"; 422 → mensagem de validação.
