# RBAC — Controle de Acesso Baseado em Papéis

## Papéis do Sistema

```python
class UserRole(str, Enum):
    PLATFORM_OWNER    = "PLATFORM_OWNER"    # Paladino (sem company_id)
    PLATFORM_SUPPORT  = "PLATFORM_SUPPORT"  # [SCHEMA ONLY]
    PLATFORM_BILLING  = "PLATFORM_BILLING"  # [SCHEMA ONLY]
    PLATFORM_READONLY = "PLATFORM_READONLY" # [SCHEMA ONLY]
    OWNER             = "OWNER"             # Proprietário do tenant
    ADMIN             = "ADMIN"             # Gestor do tenant
    OPERATOR          = "OPERATOR"          # Operacional
    PROFESSIONAL      = "PROFESSIONAL"      # Profissional do estabelecimento
```

**Papéis de plataforma** (`PLATFORM_*`): pertencem à Paladino.
`company_id = NULL` no banco. Não podem ser atribuídos por tenants.

**Papéis de tenant** (`OWNER` a `PROFESSIONAL`): pertencem a um tenant.
`company_id` preenchido.

---

## Hierarquia de Papéis (do mais ao menos privilegiado)

```
PLATFORM_OWNER
  └── OWNER
        └── ADMIN
              └── OPERATOR
                    └── PROFESSIONAL
```

---

## Invariantes de Escalonamento (anti-privilege escalation)

**Invariante 1 — Ninguém se auto-promove**
Nenhum usuário pode alterar seu próprio papel.
Enforçado em `PATCH /users/{user_id}/role`.

**Invariante 2 — Só pode convidar papéis abaixo do seu**
| Quem convida | Pode convidar |
|-------------|---------------|
| PLATFORM_OWNER | Qualquer papel de tenant |
| OWNER | ADMIN, OPERATOR, PROFESSIONAL |
| ADMIN | OPERATOR, PROFESSIONAL |
| OPERATOR | Ninguém |
| PROFESSIONAL | Ninguém |

**Invariante 3 — Último OWNER é intocável**
Se o tenant tem apenas 1 OWNER, ele não pode ser removido, desativado
ou rebaixado. Verificado em `DELETE /users/{id}` e `PATCH /users/{id}/role`.

**Invariante 4 — Papéis de plataforma não são atribuíveis por tenants**
Tenants não podem convidar `PLATFORM_*` nem atribuir esses papéis.
Enforçado em `POST /users/invite` e `PATCH /users/{id}/role`.

---

## Matriz de Permissões

### Gestão de Usuários

| Endpoint | OWNER | ADMIN | OPERATOR | PROFESSIONAL |
|----------|-------|-------|----------|--------------|
| GET /users/ | ✅ | ✅ | ❌ | ❌ |
| POST /users/invite | ✅ | ✅ (papéis inferiores) | ❌ | ❌ |
| PATCH /users/{id}/role | ✅ | ✅ (papéis inferiores) | ❌ | ❌ |
| DELETE /users/{id} | ✅ | ✅ | ❌ | ❌ |
| POST /users/transfer-ownership | ✅ | ❌ | ❌ | ❌ |
| GET /users/invitations | ✅ | ✅ | ❌ | ❌ |
| DELETE /users/invitations/{id} | ✅ | ✅ | ❌ | ❌ |

### Dados Operacionais

| Endpoint | OWNER | ADMIN | OPERATOR | PROFESSIONAL |
|----------|-------|-------|----------|--------------|
| GET /appointments/ | ✅ | ✅ | ✅ | Próprios |
| POST /appointments/ | ✅ | ✅ | ✅ | ❌ |
| PATCH /appointments/{id}/cancel | ✅ | ✅ | ✅ | ❌ |
| PATCH /appointments/{id}/complete | ✅ | ✅ | ✅ | ❌ |
| GET /customers/ | ✅ | ✅ | ✅ | ❌ |
| POST /customers/ | ✅ | ✅ | ✅ | ❌ |
| GET /professionals/ | ✅ | ✅ | ✅ | ✅ |
| POST /professionals/ | ✅ | ✅ | ❌ | ❌ |
| GET /services/ | ✅ | ✅ | ✅ | ✅ |
| POST /services/ | ✅ | ✅ | ❌ | ❌ |
| POST /agenda/firme-direct | ✅ | ✅ | ✅ | ❌ |
| POST /agenda/direct-occupancy | ✅ | ✅ | ✅ | ❌ |

### Financeiro

| Endpoint | OWNER | ADMIN | OPERATOR | PROFESSIONAL |
|----------|-------|-------|----------|--------------|
| GET /financial/accounts | ✅ | ✅ | ❌ | ❌ |
| POST /financial/accounts | ✅ | ✅ | ❌ | ❌ |
| GET /financial/accounts/{id}/balance | ✅ | ✅ | ✅ | ❌ |
| GET /financial/movements | ✅ | ✅ | ❌ | ❌ |
| GET /financial/entries | ✅ | ✅ | ❌ | ❌ |
| GET /financial/dre | ✅ | ✅ | ❌ | ❌ |
| POST /financial/manual-adjustment 🔒 | ✅ | ✅ | ❌ | ❌ |
| GET /financial/transfers | ✅ | ✅ | ❌ | ❌ |
| POST /financial/transfers | ✅ | ✅ | ❌ | ❌ |
| POST /financial/cash-counts | ✅ | ✅ | ✅ | ❌ |
| GET /financial/cash-counts | ✅ | ✅ | ✅ | ❌ |
| POST /financial/reconciliation | ✅ | ✅ | ❌ | ❌ |
| GET /payments/ | ✅ | ✅ | ❌ | ❌ |
| POST /payments/{id}/refund 🔒 | ✅ | ✅ | ❌ | ❌ |
| GET /deposit-policies | ✅ | ✅ | ❌ | ❌ |
| POST /deposit-policies | ✅ | ✅ | ❌ | ❌ |
| GET /tenant/fee-routing | ✅ | ✅ | ❌ | ❌ |
| PUT /tenant/fee-routing/{fee_source} | ✅ | ✅ | ❌ | ❌ |

### Auditoria e Configurações

| Endpoint | OWNER | ADMIN | OPERATOR | PROFESSIONAL |
|----------|-------|-------|----------|--------------|
| GET /audit/logs | ✅ | ✅ | ❌ | ❌ |
| GET /audit/logs/export 🔒 | ✅ | ✅* | ❌ | ❌ |
| GET /tenant/config | ✅ | ✅ | ❌ | ❌ |
| PUT /tenant/config | ✅ | ✅ | ❌ | ❌ |
| GET /tenant/modules | ✅ | ✅ | ❌ | ❌ |
| GET /tenant/branding | público | público | público | público |
| PUT /tenant/branding | ✅ | ✅ | ❌ | ❌ |
| PATCH /companies/me | ✅ | ✅ | ❌ | ❌ |
| PATCH /companies/profile | ✅ | ✅ | ❌ | ❌ |

*ADMIN pode exportar audit com `permission_overrides`.

---

## Permission Overrides (TenantConfig)

`TenantConfig.permission_overrides JSONB` permite ao OWNER conceder
permissões granulares a papéis inferiores além do padrão.

Formato:
```json
{
  "OPERATOR": {
    "create_manual_adjustment": true,
    "max_adjustment_amount": 50.00
  },
  "ADMIN": {
    "export_audit": true
  }
}
```

Verificado em `core/deps.py → require_action(action, scope)`.

---

## Fluxo de Convite e Ativação

```
OWNER/ADMIN
  → POST /users/invite { email, role }
    → Cria UserInvitation (token_hash, expires_at = now()+48h, status=PENDING)
    → Envia e-mail com link de ativação (token plaintext)

Convidado
  → Clica no link → POST /auth/activate { token, password }
    → Verifica SHA-256(token) no banco
    → Verifica expires_at e status=PENDING
    → Cria User com senha hasheada
    → Marca invitation.status = ACCEPTED
    → Retorna JWT
```

### Modelo UserInvitation
```
invitation_id   UUID PK
company_id      UUID FK → companies
email           VARCHAR
role            UserRole
token_hash      VARCHAR(255)    # SHA-256 do token enviado
status          VARCHAR         # PENDING | ACCEPTED | CANCELLED
expires_at      TIMESTAMPTZ     # now() + 48h
invited_by      UUID FK → users
created_at      TIMESTAMPTZ
```

---

## Transferência de Titularidade

`POST /users/transfer-ownership { new_owner_user_id, current_owner_new_role }`

Apenas OWNER pode executar. Auditado.

Sequência:
1. Validar que `new_owner_user_id` é membro ativo do tenant
2. Atribuir `OWNER` ao usuário destino
3. Atribuir `current_owner_new_role` (default: ADMIN) ao OWNER atual
4. `record_sensitive_action(action="transfer_ownership", before/after)`

Invariante: após a transferência, o tenant sempre tem exatamente 1 OWNER.