# Segurança — Paladino

## Autenticação (JWT)

### Estrutura do Token
```json
{
  "sub": "user_uuid",
  "company_id": "company_uuid_or_null",
  "role": "OWNER|ADMIN|OPERATOR|PROFESSIONAL|PLATFORM_OWNER",
  "iat": 1717000000,
  "exp": 1717086400
}
```

- `sub`: UUID do usuário
- `company_id`: UUID do tenant. `null` para `PLATFORM_OWNER`
- `role`: papel do usuário no tenant
- `iat`: issued-at (timestamp Unix, precisão de segundos)
- `exp`: expiration (iat + ACCESS_TOKEN_EXPIRE_MINUTES)

### Geração
`core/security.py → create_access_token(data: dict) → str`

`iat` é sempre incluído com `datetime.now(UTC)`.

### Verificação
`core/deps.py → get_current_user(token, db) → User`

Sequência de verificação:
1. Decodificar e verificar assinatura JWT (`SECRET_KEY`, `ALGORITHM`)
2. Verificar expiração (`exp`)
3. Extrair `sub` → buscar `User` no banco
4. Se `User.last_password_change_at` não é nulo:
   - Converter `iat` para `datetime` timezone-aware
   - Se `iat < last_password_change_at` → **HTTP 401** "Sessão expirada"
5. Se `User.active == False` → **HTTP 401**
6. Retornar `User`

---

## Invalidação de Sessão na Troca de Senha

### Problema
JWT é stateless: uma vez emitido, é válido até expirar. Se um usuário
troca de senha, tokens antigos continuam válidos — risco de segurança.

### Solução implementada
Campo `last_password_change_at TIMESTAMPTZ` no modelo `User`.
Atualizado sempre que a senha é alterada (via `change_password` ou
`reset_password`).

Na verificação do token: `iat < last_password_change_at → 401`.
Tokens emitidos antes da troca de senha são rejeitados.

### Compatibilidade retroativa
Tokens emitidos antes desta feature (sem campo `iat`) são aceitos.
O check só ocorre quando `iat` está presente e
`last_password_change_at` não é nulo.

### Cobertura
- `POST /auth/change-password`: atualiza `last_password_change_at`
- `POST /auth/reset-password`: atualiza `last_password_change_at`
- **NÃO cobre:** `POST /auth/login` (não invalida sessões, é o comportamento esperado)

---

## Recuperação de Senha

### Modelo: `PasswordResetToken`
```
token_hash      VARCHAR(255) NOT NULL UNIQUE   # SHA-256 do token enviado
expires_at      TIMESTAMPTZ NOT NULL           # now() + 48h
used            BOOLEAN DEFAULT false
user_id         UUID FK → users
```

### Fluxo
1. `POST /auth/forgot-password` com `{ email }`
2. Gerar token aleatório de 64 bytes
3. Armazenar `SHA-256(token)` no banco
4. Enviar e-mail com link contendo o token em plaintext
5. `POST /auth/reset-password` com `{ token, new_password }`
6. Verificar `SHA-256(token)` no banco + `expires_at` + `used == false`
7. Atualizar senha + marcar `used = true` + atualizar `last_password_change_at`

### Invariantes
- Token é de uso único (`used = true` após primeiro uso)
- Token expira em 48h
- Token em plaintext nunca é armazenado no banco

---

## PII — Dados Pessoais Sensíveis

### Escopo atual
CPF e CNPJ de profissionais são classificados como PII sensível.

### Armazenamento
```
cpf_cnpj_encrypted   TEXT         # Fernet(PII_ENCRYPTION_KEY, normalized_digits)
cpf_cnpj_hash        TEXT         # HMAC-SHA256(normalized_digits, PII_HASH_KEY)
cpf_cnpj_masked      VARCHAR(18)  # "***.***.***-12" / "**.***.***/****-34"
```

`normalized_digits`: string apenas com dígitos (sem pontuação).

### Chaves
- `PII_ENCRYPTION_KEY`: chave Fernet (base64url de 32 bytes aleatórios)
- `PII_HASH_KEY`: chave HMAC (string arbitrária, mínimo 32 bytes)
- Fallback: se ausentes, usam `CREDENTIAL_ENCRYPTION_KEY`
- **Separar as chaves antes do Estágio 1** (múltiplos tenants em produção)

### Permissões de acesso
| Operação | Quem pode |
|----------|-----------|
| Ler `masked` (UI, logs) | Qualquer autenticado do tenant |
| Descriptografar e enviar ao provider | Apenas `AsaasProvider` internamente |
| Descriptografar para exportação | OWNER com motivo, auditado |
| Buscar por hash (deduplicação) | Service layer (não exposto) |

### Validação
`payments/validators.py`:
- `normalize_cpf_cnpj(raw)`: remove pontuação, valida dígito verificador
- `validate_cpf(digits) → bool`
- `validate_cnpj(digits) → bool`
- `encrypt_pii(value) → str`
- `hash_pii(value) → str`
- `mask_cpf(digits) → str`
- `mask_cnpj(digits) → str`

---

## Criptografia de Credenciais de Integração

Credenciais externas (API keys, tokens) são armazenadas em
`integration_credentials.secret_encrypted` via Fernet com
`CREDENTIAL_ENCRYPTION_KEY`.

`masked_preview`: últimos 4 caracteres do valor decriptado.
Nunca retornar `secret_encrypted` em respostas de API.

Implementado em `integrations/credentials/service.py`.

---

## Row-Level Security (RLS)

PostgreSQL RLS enforça que cada query retorna apenas dados do tenant
correto. Ver detalhes em [infrastructure.md](infrastructure.md).

---

## Auditoria de Ações Sensíveis

### Modelo: `AuditLog`
```
audit_id        UUID PK
company_id      UUID nullable FK → companies
actor_id        UUID FK → users
actor_role      VARCHAR
action          VARCHAR                 # ex: "invite_user", "refund_payment"
resource_type   VARCHAR
resource_id     UUID nullable
before_snapshot JSONB nullable
after_snapshot  JSONB nullable
amount          NUMERIC nullable        # para ações financeiras
account_id      UUID nullable
ip_address      VARCHAR nullable
created_at      TIMESTAMPTZ DEFAULT now()
```

### Ações auditadas (obrigatório)
| Ação | `reason` obrigatório |
|------|---------------------|
| `invite_user` | Não |
| `assign_role` | Não |
| `transfer_ownership` | Não (mas registra before/after) |
| `export_audit` | **Sim** |
| `manual_adjustment` | **Sim** |
| `refund_payment` | **Sim** (via `RefundReason` enum) |
| `forced_overbooking` | **Sim** |

### Invariante
`audit_logs` é append-only. Não há endpoint de DELETE ou UPDATE.
Apenas `GET /audit/logs` (OWNER/ADMIN) e `GET /audit/logs/export` (OWNER).

---

## Validação de Força de Senha

Client-side (settings/security/page.tsx) e server-side (auth/service.py):
- Mínimo 8 caracteres
- Pelo menos 1 letra maiúscula
- Pelo menos 1 número

Sem restrição de reutilização de senha (por enquanto).

---

## Headers e CORS

A configuração de CORS deve ser revisada antes de deploy em produção.
Atualmente permissiva para desenvolvimento.