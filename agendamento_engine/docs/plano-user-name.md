# Plano de Implementação: campo `name` no modelo User

**Data:** 2026-06-04  
**Classificação:** SIMPLES

---

## Descoberta crítica: trabalho já está 80% feito

A análise revelou que o campo `name` **já existe em produção** nos seguintes lugares:

| Artefato | Status |
|---|---|
| `User.name` (ORM) | ✅ Coluna já existe no modelo |
| Migration `h2i3j4k5l6m7` | ✅ Arquivo criado — mas **não rastreado pelo git** |
| `GET /auth/me` retorna `name` | ✅ Já implementado (`router.py:28-34`) |
| `POST /auth/activate` aceita e salva `name` | ✅ Já implementado |
| `UserResponse.name` | ✅ Já no schema — exposto em GET /users |
| `InviteUserRequest.name` | ✅ Aceito no body (mas ignorado; intencional) |
| `forgot_password` usa `user.name` | ✅ Com fallback gracioso |
| `test_user_name.py` (7 testes) | ✅ Criado — mas **não rastreado pelo git** |

O que **não existe** e precisa ser criado: `PATCH /auth/profile`.

---

## Passo 2 — Mapa de dependências

### 2a. Schemas que serializam User para response

| Schema | Campos de User expostos | Endpoints que o retornam |
|---|---|---|
| `auth/router.py` dict literal | `id, email, name, company_id, role` | `GET /auth/me` |
| `users/schemas.UserResponse` | `id, company_id, email, name, role, active` | `GET /users/`, `PATCH /{id}/role`, `DELETE /{id}`, `POST /transfer-ownership` |
| `auth/schemas.TokenResponse` | `access_token, token_type, user_id, company_id, role` | `POST /auth/login`, `POST /auth/activate` |

**O token JWT não contém `name`** — apenas `sub`, `email`, `company_id`, `role` (verificado em `auth/service.py:74-79` e `activate_service.py:74-79`). Atualizar o nome não exige re-login.

### 2b. Onde User é criado ou atualizado

| Operação | Arquivo | Observação |
|---|---|---|
| Criar via convite | `activate_service.py:57-65` | `name=name` já passado ao `User()` |
| Criar legado (deprecado) | `users/service.py:77-102` | Sem `name` — não tem importância (fluxo removido) |
| `PATCH /{id}/role` | `users/service.py:196-238` | Não toca `name` — correto |
| `DELETE /{id}` (desativa) | `users/service.py:243-263` | Não toca `name` — correto |
| Transferência de ownership | `users/service.py:268-320` | Não toca `name` — correto |
| **`PATCH /auth/profile`** | **NÃO EXISTE** | **← gap a preencher** |

`POST /users/invite` aceita `name` no body (`InviteUserRequest.name`) mas o campo é guardado
na invitação apenas para exibição ao convidado. O `User` real só recebe o nome em `POST /auth/activate`.

### 2c. Testes que tocam User

| Arquivo | Testes com User | Rastreado pelo git |
|---|---|---|
| `tests/test_user_name.py` | 7 testes — cobrem GET /me, activate, invite, list | ❌ Untracked |
| `tests/test_sprint2_rbac.py` | Cria usuários; verifica role, email | ✅ |
| `tests/test_security_session_invalidation.py` | Cria usuários; verifica JWT/senha | ✅ |
| `tests/conftest.py` | Factory de User (`make_user`) | ✅ |

Os testes existentes rastreados **não verificam `name`** — usam apenas `id`, `email`, `role`.
O campo nullable não quebra nenhum deles.

### 2d. JWT inclui `name`?

**Não.** Verificado em dois lugares:
- `auth/service.py:74-79`: `{"sub", "email", "company_id", "role"}`  
- `activate_service.py:74-79`: idem

Conclusão: atualizar `name` via `PATCH /auth/profile` **não invalida nem exige re-emissão do token**.
O frontend busca o nome via `GET /auth/me` após o PATCH.

---

## Passo 3 — Avaliação da abordagem proposta

### Viabilidade: ✅ Totalmente viável

**Q: O frontend precisa de `name` em endpoints além de GET /auth/me?**  
`GET /users/` já retorna `UserResponse` que inclui `name` de todos os usuários do tenant.
OWNER/ADMIN que listam a equipe já veem os nomes. Sem lacuna.

**Q: O convite precisa passar `name` para o User?**  
Não — o fluxo atual é correto: `InviteUserRequest.name` é aceito no body mas ignorado no
`UserInvitation` (a tabela `user_invitations` não tem coluna `name`). O usuário define
o próprio nome em `POST /auth/activate`. Não é necessário alterar esse fluxo.

**Q: Há endpoint que retorna dados de User para outro usuário (profissional, agendamento)?**  
Verificado: `professionals/router`, `booking/router` não referenciam `User.name` diretamente.
O módulo `professionals` tem seu próprio campo de nome (`Professional.full_name` ou similar).
Sem cascata necessária.

---

## Passo 4 — Implementação mínima

### 4a. Migration

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(100);
```

**Arquivo já existe** em `migrations/versions/h2i3j4k5l6m7_add_name_to_users.py`.
Ação necessária: `git add` + aplicar no banco de produção.

### 4b. ORM

**Já existe** em `app/infrastructure/db/models/user.py:70`:
```python
name = Column(String(100), nullable=True)
```
Nenhuma alteração necessária.

### 4c. Schemas que precisam de alteração

| Arquivo | Schema | Campo | Status |
|---|---|---|---|
| `auth/schemas.py` | `ActivateRequest` | `name: Optional[str] = None` | ✅ Já existe |
| `users/schemas.py` | `UserResponse` | `name: Optional[str] = None` | ✅ Já existe |
| `users/schemas.py` | `InviteUserRequest` | `name: Optional[str] = None` | ✅ Já existe |
| `auth/schemas.py` | **`UpdateProfileRequest`** (novo) | `name: Optional[str]` | ❌ Criar |

**Novo schema a criar** em `auth/schemas.py`:
```python
class UpdateProfileRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
```

### 4d. Endpoints novos ou alterados

#### Novo: `PATCH /auth/profile`

| Atributo | Valor |
|---|---|
| Método | `PATCH` |
| Rota | `/auth/profile` |
| Auth | Qualquer usuário autenticado (`get_current_user`) |
| RBAC | Nenhum — o usuário só pode editar o próprio perfil |
| Request body | `{ "name": "João Silva" }` (campo opcional) |
| Response | Mesmo formato de `GET /auth/me` |

**Implementação no router** (`auth/router.py`):
```python
@router.patch("/profile")
def update_profile(
    body: schemas.UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.name is not None:
        user.name = body.name
        db.commit()
        db.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "company_id": str(user.company_id) if user.company_id else None,
        "role": user.role,
    }
```

Não há service dedicado necessário — a lógica é trivial e não envolve regras de negócio.

### 4e. Endpoints que NÃO precisam ser alterados

| Endpoint | Justificativa |
|---|---|
| `POST /auth/login` | `TokenResponse` não inclui `name` — intencional; frontend usa GET /me |
| `POST /auth/activate` | Já aceita e salva `name` |
| `GET /users/` | `UserResponse` já inclui `name` |
| `PATCH /{id}/role` | Altera role, não perfil |
| `DELETE /{id}` | Desativa usuário, não altera campos |
| `POST /users/invite` | Cria convite, não User |
| `POST /auth/forgot-password` | Já usa `user.name` com fallback |
| `POST /auth/change-password` | Altera senha, não perfil |

### 4f. Testes

| Arquivo | Ação |
|---|---|
| `tests/test_user_name.py` | `git add` — 7 testes já prontos |
| `tests/test_user_name.py` | **Adicionar** `test_patch_profile_updates_name` e `test_patch_profile_name_none_ignored` |

**Novos testes a adicionar** em `test_user_name.py`:

```python
def test_patch_profile_updates_name(client, db_session):
    """PATCH /auth/profile → name atualizado; resposta inclui novo name."""
    company = make_company(db_session)
    user = make_user(db_session, company.id, name="Nome Antigo")
    db_session.commit()

    resp = client.patch(
        "/auth/profile",
        json={"name": "Nome Novo"},
        headers=auth_header(user),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Nome Novo"


def test_patch_profile_without_name_leaves_name_unchanged(client, db_session):
    """PATCH /auth/profile sem name → name existente não é apagado."""
    company = make_company(db_session)
    user = make_user(db_session, company.id, name="Persistente")
    db_session.commit()

    resp = client.patch(
        "/auth/profile",
        json={},
        headers=auth_header(user),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Persistente"
```

### 4g. O que o frontend recebe

**`GET /auth/me`** (sem alteração):
```json
{
  "id": "uuid",
  "email": "usuario@empresa.com",
  "name": "João Silva",
  "company_id": "uuid",
  "role": "ADMIN"
}
```

**`PATCH /auth/profile`** (novo endpoint):

Request:
```json
{ "name": "João Silva" }
```

Response (200):
```json
{
  "id": "uuid",
  "email": "usuario@empresa.com",
  "name": "João Silva",
  "company_id": "uuid",
  "role": "ADMIN"
}
```

---

## Passo 5 — Riscos e ordem de execução

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Migration quebra dados existentes | Zero | — | `ADD COLUMN IF NOT EXISTS` + nullable; sem DEFAULT obrigatório |
| Testes existentes quebram | Zero | — | Campo nullable; nenhum teste verifica ausência do campo |
| JWT invalidado ao salvar nome | Zero | — | Token não inclui `name` |
| PATCH /profile edita perfil de outro usuário | Prevenido por design | Alto | Endpoint usa `get_current_user` — sempre o usuário do token |

### Ordem de execução

```
1. git add migrations/versions/h2i3j4k5l6m7_add_name_to_users.py
2. git add tests/test_user_name.py
3. Criar UpdateProfileRequest em auth/schemas.py
4. Criar PATCH /auth/profile em auth/router.py
5. Adicionar 2 novos testes em test_user_name.py
6. Rodar suite: pytest tests/test_user_name.py -v
7. Rodar suite completa: pytest --tb=short
8. Aplicar migration no banco: alembic upgrade head
```

---

## Prompt de execução para o implementador

```
Sessão de implementação: campo name no User (trabalho quase completo).

ESTADO ATUAL:
- User.name já existe no ORM (user.py:70)
- Migration h2i3j4k5l6m7_add_name_to_users.py já existe (untracked)
- GET /auth/me já retorna name (auth/router.py:28-34)
- POST /auth/activate já aceita e salva name
- UserResponse já inclui name
- test_user_name.py (7 testes) já existe (untracked)

O QUE FALTA FAZER (em ordem):

1. git add agendamento_engine/migrations/versions/h2i3j4k5l6m7_add_name_to_users.py
   git add agendamento_engine/tests/test_user_name.py

2. Em agendamento_engine/app/modules/auth/schemas.py, adicionar ANTES de MessageResponse:
   
   class UpdateProfileRequest(BaseModel):
       name: Optional[str] = Field(None, max_length=100)

3. Em agendamento_engine/app/modules/auth/router.py, adicionar após o endpoint /change-password:

   @router.patch("/profile")
   def update_profile(
       body: schemas.UpdateProfileRequest,
       user: User = Depends(get_current_user),
       db: Session = Depends(get_db),
   ):
       if body.name is not None:
           user.name = body.name
           db.commit()
           db.refresh(user)
       return {
           "id": str(user.id),
           "email": user.email,
           "name": user.name,
           "company_id": str(user.company_id) if user.company_id else None,
           "role": user.role,
       }

4. Em agendamento_engine/tests/test_user_name.py, adicionar os 2 testes:
   test_patch_profile_updates_name
   test_patch_profile_without_name_leaves_name_unchanged
   (ver plano: agendamento_engine/docs/plano-user-name.md §4f)

5. Rodar: pytest agendamento_engine/tests/test_user_name.py -v
6. Rodar: pytest agendamento_engine/tests/ --tb=short
7. Fazer commit.

NÃO ALTERAR:
- Nenhum outro módulo (booking, professionals, payments)
- Token JWT (não inclui name — intencional)
- Demais schemas (UserResponse, ActivateRequest já prontos)
```

---

## Estimativa de testes afetados

| Categoria | Quantidade |
|---|---|
| Testes já prontos a rastrear | 7 (test_user_name.py) |
| Testes novos a escrever | 2 (PATCH /auth/profile) |
| Testes existentes que quebram | 0 |
| **Total testes após implementação** | **9 novos + 142 existentes = 151** |

---

## Classificação final

**SIMPLES** — o campo já existe em ORM, migration, schemas e endpoints principais.
O único gap real é 1 endpoint (`PATCH /auth/profile`) + 2 testes + registrar 2 arquivos no git.
Executável em uma única sessão curta (< 30 min).
