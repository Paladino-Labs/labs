-**Sprint atual:** Sprint 2 em andamento (Fase 1 — Fundação técnica)
+**Sprint atual:** Sprint 3 em andamento (Fase 1 — Fundação técnica)

 ## Stack e infraestrutura
 
+- Tabelas criadas: `user_invitations`, `audit_logs` (append-only via triggers no banco)

 ## Convenções críticas
 
-`User.role`: `String(20)` com valores `ADMIN`, `PROFESSIONAL`, `CLIENT`
-  → vira Enum `userrole` (9 valores) no Sprint 2
+`User.role`: Enum `userrole` com 9 valores — OWNER|ADMIN|OPERATOR|PROFESSIONAL|CLIENT|PLATFORM_OWNER
+  ativos; PLATFORM_SUPPORT|PLATFORM_BILLING|PLATFORM_READONLY schema-only (Estágio 1+)
-`User.company_id`: `NOT NULL` → vira `nullable=True` no Sprint 2 (PLATFORM_OWNER terá NULL)
+`User.company_id`: nullable — PLATFORM_OWNER tem NULL; demais têm company_id preenchido
-Auth: `require_admin` em `core/deps.py:43` — binário → substituído no Sprint 2/3
+Auth: `require_role()` e `require_action()` disponíveis em `core/deps.py`
+  `require_admin` mantido para routers legados (removido no Sprint 3)
+  `is_admin` property: `role in ("ADMIN", "OWNER", "PLATFORM_OWNER")`

 ## Onde está o quê
 
+- `core/audit/sensitive_context.py` — `SensitiveAuditContext`, `record_sensitive_action`, `REASON_REQUIRED`
+- `domain/enums/action_scope.py` — `ActionScope` enum (re-export)
+- `infrastructure/db/models/user_invitation.py`
+- `infrastructure/db/models/audit_log.py`
+- `modules/audit/router.py` — `GET /audit/logs`, `GET /audit/logs/export`
+- `modules/auth/activate_service.py` — ativação de convite por token

 ## O que NÃO fazer
 
+- `POST /users` legado está deprecado (remover no Sprint 3 após validar logs de uso)
+- Não criar endpoints novos com `require_admin` — usar `require_role()` ou `require_action()`
+- Invitations em `/users/invitations` (não `/invitations` independente)