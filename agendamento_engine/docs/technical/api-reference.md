# API Reference — Paladino

**Base URL:** `[host]/`
**Autenticação:** `Authorization: Bearer {jwt_token}` (exceto endpoints marcados como público)
**Versão:** 2.0.0

---

## Auth (`/auth`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| POST | `/auth/login` | público | Login. Body: `{email, password}`. Retorna JWT. |
| POST | `/auth/activate` | público | Ativar convite. Body: `{token, password}`. Retorna JWT. |
| GET | `/auth/me` | ✅ | Retorna usuário autenticado. |
| POST | `/auth/forgot-password` | público | Solicita reset. Body: `{email}`. |
| POST | `/auth/reset-password` | público | Redefine senha. Body: `{token, new_password}`. |
| POST | `/auth/change-password` | ✅ | Troca senha. Body: `{current_password, new_password}`. Invalida sessões anteriores. |

---

## Users (`/users`)

| Método | Path | Papéis | Descrição |
|--------|------|--------|-----------|
| GET | `/users/` | OWNER, ADMIN | Lista usuários ativos do tenant. |
| POST | `/users/invite` | OWNER, ADMIN | Convida usuário. Body: `{email, role}`. |
| PATCH | `/users/{user_id}/role` | OWNER, ADMIN | Altera papel. Body: `{role}`. |
| DELETE | `/users/{user_id}` | OWNER, ADMIN | Desativa usuário. |
| POST | `/users/transfer-ownership` 🔒 | OWNER | Transfere titularidade. Body: `{new_owner_user_id, current_owner_new_role}`. |
| GET | `/users/invitations` | OWNER, ADMIN | Lista convites pendentes. |
| DELETE | `/users/invitations/{id}` | OWNER, ADMIN | Cancela convite. |

---

## Companies (`/companies`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/companies/me` | ✅ | Dados da empresa. |
| PATCH | `/companies/me` | OWNER, ADMIN | Atualiza dados básicos. |
| GET | `/companies/profile` | ✅ | Perfil público da empresa. |
| PATCH | `/companies/profile` | OWNER, ADMIN | Atualiza perfil. |

---

## Appointments (`/appointments`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/appointments/` | ✅ | Lista agendamentos (filtros: date, professional_id, status). |
| POST | `/appointments/` | OWNER, ADMIN, OPERATOR | Cria agendamento manual. |
| GET | `/appointments/{id}` | ✅ | Detalhe do agendamento. |
| PATCH | `/appointments/{id}/cancel` | OWNER, ADMIN, OPERATOR | Cancela. |
| PATCH | `/appointments/{id}/reschedule` | OWNER, ADMIN, OPERATOR | Reagenda. |
| PATCH | `/appointments/{id}/complete` | OWNER, ADMIN, OPERATOR | Marca como concluído. |

---

## Availability (`/availability`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/availability/slots` | ✅ | Slots disponíveis. Query: `professional_id, date, service_id`. |

---

## Customers (`/customers`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/customers/` | OWNER, ADMIN, OPERATOR | Lista clientes. |
| POST | `/customers/` | OWNER, ADMIN, OPERATOR | Cria cliente. |
| GET | `/customers/{id}` | OWNER, ADMIN, OPERATOR | Detalhe. |
| PATCH | `/customers/{id}` | OWNER, ADMIN, OPERATOR | Atualiza. |
| GET | `/customers/{id}/appointments` | OWNER, ADMIN, OPERATOR | Histórico do cliente. |

---

## Professionals (`/professionals`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/professionals/` | ✅ | Lista profissionais. |
| POST | `/professionals/` | OWNER, ADMIN | Cria. |
| GET | `/professionals/{id}` | ✅ | Detalhe. |
| PATCH | `/professionals/{id}` | OWNER, ADMIN | Atualiza (inclui CPF/CNPJ — sempre encrypted). |
| GET | `/professionals/{id}/services` | ✅ | Serviços vinculados. |
| POST | `/professionals/{id}/services` | OWNER, ADMIN | Vincula serviço. |
| DELETE | `/professionals/{id}/services/{sid}` | OWNER, ADMIN | Desvincula. |

---

## Schedule (`/schedule`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/schedule/working-hours/{professional_id}` | ✅ | Horários de trabalho. |
| POST | `/schedule/working-hours` | OWNER, ADMIN | Define horário. |
| GET | `/schedule/blocks/{professional_id}` | ✅ | Bloqueios. |
| POST | `/schedule/blocks` | OWNER, ADMIN | Cria bloqueio. |
| DELETE | `/schedule/blocks/{id}` | OWNER, ADMIN | Remove bloqueio. |
| GET | `/schedule/exceptions/{professional_id}` | ✅ | Exceções de horário. |
| POST | `/schedule/exceptions` | OWNER, ADMIN | Cria exceção. |
| DELETE | `/schedule/exceptions/{id}` | OWNER, ADMIN | Remove exceção. |

---

## Agenda (`/agenda`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| POST | `/agenda/soft-reservation` | ✅ | Cria reserva SOFT. Pode retornar 409. |
| POST | `/agenda/soft-reservation/{id}/promote` | ✅ | Promove SOFT → FIRME (atômico). |
| POST | `/agenda/soft-reservation/{id}/release` | ✅ | Libera reserva SOFT. |
| POST | `/agenda/firme-direct` | OWNER, ADMIN, OPERATOR | Cria FIRME direta (walk-in). |
| POST | `/agenda/direct-occupancy` | OWNER, ADMIN, OPERATOR | Abre ocupação direta. |
| PUT | `/agenda/direct-occupancy/{id}/close` | OWNER, ADMIN, OPERATOR | Fecha ocupação. |

---

## Services e Products

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/services/` | ✅ | Lista serviços. |
| POST | `/services/` | OWNER, ADMIN | Cria serviço. |
| GET | `/services/{id}` | ✅ | Detalhe. |
| PATCH | `/services/{id}` | OWNER, ADMIN | Atualiza. |
| GET | `/products/` | ✅ | Lista produtos. |
| POST | `/products/` | OWNER, ADMIN | Cria produto. |
| GET | `/products/{id}` | ✅ | Detalhe. |
| PATCH | `/products/{id}` | OWNER, ADMIN | Atualiza. |

---

## Financial Core (`/financial`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/financial/accounts` | OWNER, ADMIN | Lista contas. |
| POST | `/financial/accounts` | OWNER, ADMIN | Cria conta. |
| GET | `/financial/accounts/{id}/balance` | OWNER, ADMIN, OPERATOR | Saldo atual. Query: `as_of` (opcional). |
| GET | `/financial/movements` | OWNER, ADMIN | Lista movimentações. |
| GET | `/financial/entries` | OWNER, ADMIN | Lista lançamentos. |
| GET | `/financial/dre` | OWNER, ADMIN | DRE. Query: `date_from, date_to`. |
| POST | `/financial/manual-adjustment` 🔒 | OWNER, ADMIN | Ajuste manual (reason obrigatório). |
| GET | `/financial/transfers` | OWNER, ADMIN | Lista transferências. |
| POST | `/financial/transfers` | OWNER, ADMIN | Cria transferência entre contas. |
| POST | `/financial/reconciliation` | OWNER, ADMIN | Abre reconciliação. |
| PUT | `/financial/reconciliation/{id}/close` | OWNER, ADMIN | Fecha reconciliação. |
| GET | `/financial/movements/unreconciled` | OWNER, ADMIN | Movimentações não reconciliadas. |
| POST | `/financial/movements/{id}/reconcile` | OWNER, ADMIN | Marca como reconciliado. |
| GET | `/financial/cash-counts` | OWNER, ADMIN, OPERATOR | Lista contagens. |
| POST | `/financial/cash-counts` | OWNER, ADMIN, OPERATOR | Registra contagem. |
| GET | `/financial/settings` | OWNER, ADMIN | Status financeiro (subconta Asaas, contas). |

---

## Tenant Fee Routing (`/tenant`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/tenant/fee-routing` | OWNER, ADMIN | Lista 7 políticas de taxa. |
| PUT | `/tenant/fee-routing/{fee_source}` | OWNER, ADMIN | Atualiza política. Valida soma=100. |
| GET | `/tenant/config` | OWNER, ADMIN | Configuração do tenant. |
| PUT | `/tenant/config` | OWNER, ADMIN | Atualiza configuração. |
| GET | `/tenant/modules` | OWNER, ADMIN | Lista módulos e status. |
| POST | `/tenant/modules/{name}/activate` | OWNER, ADMIN | Ativa módulo. |
| POST | `/tenant/modules/{name}/deactivate` | OWNER, ADMIN | Desativa módulo. |
| GET | `/tenant/branding` | público | Branding do tenant (query: `company_id`). |
| PUT | `/tenant/branding` | OWNER, ADMIN | Atualiza branding. |

---

## Payments (`/payments`, `/payment-sources`, `/deposit-policies`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/payments` | OWNER, ADMIN | Lista pagamentos. |
| POST | `/payments` | OWNER, ADMIN, OPERATOR | Cria pagamento. |
| GET | `/payments/{id}` | OWNER, ADMIN | Detalhe. |
| POST | `/payments/{id}/refund` 🔒 | OWNER, ADMIN | Reembolsa. Body: `{reason}`. |
| POST | `/payments/webhook/asaas/transaction` | público | Webhook de confirmação Asaas (idempotente). |
| POST | `/payments/webhook/asaas/account_status` | público | Webhook de ativação de subconta. |
| GET | `/payment-sources` | OWNER, ADMIN | Lista fontes de pagamento salvas. |
| POST | `/payment-sources` | OWNER, ADMIN | Registra fonte. |
| DELETE | `/payment-sources/{id}` | OWNER, ADMIN | Desativa fonte. |
| GET | `/deposit-policies` | OWNER, ADMIN | Lista políticas de depósito. |
| POST | `/deposit-policies` | OWNER, ADMIN | Cria política. |
| PUT | `/deposit-policies/{id}` | OWNER, ADMIN | Atualiza política. |

---

## Audit, Communication, Integrations

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/audit/logs` | OWNER, ADMIN | Lista logs. Query: `action, actor_id, date_from, date_to`. |
| GET | `/audit/logs/export` 🔒 | OWNER, ADMIN* | Exporta CSV. |
| GET | `/communication/settings` | OWNER, ADMIN | Configurações de comunicação. |
| PUT | `/communication/settings` | OWNER, ADMIN | Atualiza. |
| GET | `/communication/templates` | OWNER, ADMIN | Lista templates. |
| POST | `/communication/templates` | OWNER, ADMIN | Cria template. |
| PUT | `/communication/templates/{id}` | OWNER, ADMIN | Atualiza. |
| DELETE | `/communication/templates/{id}` | OWNER, ADMIN | Remove (não pode ser default). |
| GET | `/communication/logs` | OWNER, ADMIN | Logs de envio. |
| POST | `/integrations/credentials` | OWNER, ADMIN | Adiciona credencial. |
| GET | `/integrations/credentials` | OWNER, ADMIN | Lista credenciais (sem secret). |
| POST | `/integrations/credentials/{id}/rotate` | OWNER, ADMIN | Rotaciona chave. |
| POST | `/integrations/credentials/{id}/revoke` | OWNER, ADMIN | Revoga. |
| POST | `/integrations/credentials/{id}/test` | OWNER, ADMIN | Testa conectividade. |

---

## WhatsApp (`/whatsapp`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| POST | `/whatsapp/connection` | OWNER, ADMIN | Inicia conexão. |
| GET | `/whatsapp/connection` | OWNER, ADMIN | Status da conexão. |
| DELETE | `/whatsapp/connection` | OWNER, ADMIN | Desconecta. |
| GET | `/whatsapp/qr` | OWNER, ADMIN | QR code para vinculação. |
| POST | `/whatsapp/webhook` | público | Recebe mensagens do WhatsApp. |

---

## Booking Público (`/booking/{slug}`)

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/booking/{slug}/info` | público | Informações básicas da barbearia. |
| GET | `/booking/{slug}/profile` | público | Perfil completo. |
| GET | `/booking/{slug}/services` | público | Serviços disponíveis. |
| GET | `/booking/{slug}/professionals` | público | Profissionais disponíveis. |
| GET | `/booking/{slug}/dates` | público | Datas com disponibilidade. |
| GET | `/booking/{slug}/slots` | público | Slots de horário. |
| POST | `/booking/{slug}/start` | público | Inicia sessão de checkout (FSM). |
| POST | `/booking/{slug}/update` | público | Avança FSM. Body: `{token, action, payload}`. |
| GET | `/booking/{slug}/session/{token}` | público | Estado atual da sessão. |
| POST | `/booking/{slug}/confirm` | público | Confirma agendamento. |
| GET | `/booking/{slug}/appointments` | público | Agendamentos do cliente (por token). |
| PATCH | `/booking/{slug}/appointments/{id}/cancel` | público | Cancela (por token). |

---

## Uploads e Outros

| Método | Path | Auth | Descrição |
|--------|------|------|-----------|
| POST | `/uploads/` | ✅ | Upload de imagem para Supabase Storage. Retorna URL. |
| GET | `/categories/` | ✅ | Lista categorias. |
| POST | `/categories/` | OWNER, ADMIN | Cria categoria. |
| PATCH | `/categories/{id}` | OWNER, ADMIN | Atualiza. |
| DELETE | `/categories/{id}` | OWNER, ADMIN | Remove. |

---

## Códigos de Erro Padrão

| Código | Significado |
|--------|-------------|
| 400 | Bad Request — violação de regra de negócio (ex: deletar template default) |
| 401 | Unauthorized — token inválido, expirado ou sessão invalidada |
| 403 | Forbidden — papel sem permissão para a operação |
| 404 | Not Found — recurso não encontrado no tenant do usuário |
| 409 | Conflict — sobreposição de horário, CPF duplicado, slot indisponível |
| 422 | Unprocessable Entity — validação de dados falhou (Pydantic) |
| 500 | Internal Server Error — erro não tratado |