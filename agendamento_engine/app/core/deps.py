from uuid import UUID
from typing import Callable, Optional
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.audit.sensitive_context import ActionScope
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models import User

# auto_error=False: sem token → credentials=None → levantamos 401 manualmente.
# O padrão (True) levantaria 403, que semanticamente significa "proibido"
# (autenticado mas sem permissão), não "não autenticado".
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Não autenticado")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Não autenticado")

    # JWT portal (Sprint D, type="portal", sub=identity_id) NUNCA autentica
    # em endpoints de tenant — rejeição explícita, não dependa do lookup falhar.
    if payload.get("type") is not None:
        raise HTTPException(status_code=401, detail="Não autenticado")

    user = db.query(User).filter(User.id == user_id, User.active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")

    # Invalida tokens emitidos antes da última troca de senha.
    if user.last_password_change_at is not None:
        iat_raw = payload.get("iat")
        if iat_raw is not None:
            token_issued_at = datetime.fromtimestamp(float(iat_raw), tz=timezone.utc)
            if token_issued_at < user.last_password_change_at:
                raise HTTPException(
                    status_code=401,
                    detail="Sessão expirada — senha alterada.",
                )

    return user


def get_current_portal_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
):
    """Autentica o cliente final do Portal (Sprint D).

    Exige JWT com type="portal" (claims distintos do JWT de tenant — sem
    company_id). JWT de tenant → 401. Retorna a PaladinoIdentity.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Não autenticado")

    from app.infrastructure.db.models import PaladinoIdentity
    from app.modules.portal.auth_service import verify_portal_token

    identity_id = verify_portal_token(credentials.credentials)
    identity = (
        db.query(PaladinoIdentity)
        .filter(PaladinoIdentity.id == identity_id)
        .first()
    )
    if not identity:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return identity


def get_current_company_id(user: User = Depends(get_current_user)) -> Optional[UUID]:
    """Extrai o company_id do usuário autenticado.

    - PLATFORM_OWNER: retorna None (sem tenant).
    - Demais papéis: retorna user.company_id; levanta 403 se NULL inesperado.
    """
    if user.role == "PLATFORM_OWNER":
        return None
    if not user.company_id:
        raise HTTPException(status_code=403, detail="Usuário sem tenant associado")
    return user.company_id


def require_role(*roles: str) -> Callable:
    """Dependency factory: exige que o usuário tenha um dos papéis informados.

    Uso: Depends(require_role("OWNER", "ADMIN"))
    """
    role_set = set(roles)

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in role_set:
            raise HTTPException(
                status_code=403,
                detail=f"Acesso restrito aos papéis: {sorted(role_set)}",
            )
        return user

    return _dep


def require_action(action: str, scope: ActionScope = ActionScope.TENANT) -> Callable:
    """Dependency factory: verifica se o papel do usuário tem permissão para a ação.

    Scope CROSS_TENANT: apenas PLATFORM_OWNER.
    Scope OWN: PROFESSIONAL acessando recursos próprios.
    Consulta permission_overrides de TenantConfig quando disponível.

    Atenção: tenant_configs só existe a partir do Sprint 3. Implementado com
    fallback gracioso para {} enquanto a tabela não existe.
    """
    def _dep(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if scope == ActionScope.CROSS_TENANT and user.role != "PLATFORM_OWNER":
            raise HTTPException(status_code=403, detail="Acesso exclusivo ao PLATFORM_OWNER")

        # Fallback gracioso enquanto tenant_configs ainda não existe (Sprint 3)
        overrides: dict = {}
        try:
            from app.infrastructure.db.models.tenant_config import TenantConfig  # type: ignore
            if user.company_id:
                config = (
                    db.query(TenantConfig)
                    .filter(TenantConfig.company_id == user.company_id)
                    .first()
                )
                overrides = (config.permission_overrides or {}) if config else {}
        except Exception:
            overrides = {}

        # Verifica override granular por papel
        role_overrides = overrides.get(user.role, {})
        if role_overrides.get(action):
            return user

        # Papéis com acesso padrão a tudo no tenant
        if user.role in ("OWNER", "ADMIN", "PLATFORM_OWNER"):
            return user

        # OPERATOR: acesso a ações operacionais (sem financeiro)
        if user.role == "OPERATOR":
            raise HTTPException(
                status_code=403,
                detail=f"OPERATOR não tem permissão para '{action}'. "
                       f"Solicite ao OWNER/ADMIN via permission_overrides.",
            )

        # PROFESSIONAL com scope OWN: acesso aos próprios recursos
        if user.role == "PROFESSIONAL" and scope == ActionScope.OWN:
            return user

        raise HTTPException(
            status_code=403,
            detail=f"Sem permissão para executar '{action}'",
        )

    return _dep
