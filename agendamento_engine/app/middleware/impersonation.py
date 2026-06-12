"""
ImpersonationMiddleware — Sprint C (PlatformSecurity-1).

Detecta o header `X-Impersonate-Grant: {grant_id}`. Se presente:
  1. Verifica que o JWT é de PLATFORM_OWNER.
  2. Busca o ImpersonationGrant por grant_id.
  3. Valida: grant ativo (não expirado, não revogado).
  4. Valida: grant.platform_user_id == JWT.sub.
  5. Injeta no request.state:
       impersonating=True, impersonation_grant=grant,
       effective_company_id=grant.company_id
  6. Audita o acesso (append em audit_logs com o grant_id em resource_id —
     audit_logs não tem coluna própria; action="impersonated_request" +
     resource_type="ImpersonationGrant" identificam o registro, e
     company_id=grant.company_id torna o acesso visível ao tenant).
Se ausente: comportamento normal.

Escrita em modo READ_ONLY é bloqueada pela dependency require_not_read_only
(endpoints de escrita) e, em profundidade, pelo bloqueio de métodos mutantes
aqui no middleware (defesa dupla: qualquer método != GET/HEAD/OPTIONS com
grant READ_ONLY → 403).
"""
import logging
from uuid import UUID

from fastapi import HTTPException, Request
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import settings

logger = logging.getLogger(__name__)

IMPERSONATE_HEADER = "X-Impersonate-Grant"

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def validate_impersonation_request(
    db: Session,
    grant_id: str,
    authorization: str,
    method: str = "GET",
):
    """Valida o grant + JWT e retorna o ImpersonationGrant ativo.

    Levanta HTTPException 401/403 em qualquer falha. Testável sem ASGI.
    """
    from app.infrastructure.db.models import ImpersonationGrant

    # 1. JWT precisa ser de PLATFORM_OWNER
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    try:
        payload = jwt.decode(
            authorization[7:], settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Não autenticado")
    if payload.get("role") != "PLATFORM_OWNER" or payload.get("type") is not None:
        raise HTTPException(
            status_code=403, detail="Impersonation exclusiva ao PLATFORM_OWNER"
        )

    # 2. Grant existe?
    try:
        grant_uuid = UUID(grant_id)
    except ValueError:
        raise HTTPException(status_code=403, detail="Grant de impersonation inválido")
    grant = (
        db.query(ImpersonationGrant)
        .filter(ImpersonationGrant.id == grant_uuid)
        .first()
    )
    if not grant:
        raise HTTPException(status_code=403, detail="Grant de impersonation inválido")

    # 3. Ativo (não expirado, não revogado)?
    if not grant.is_active:
        raise HTTPException(
            status_code=403, detail="Grant de impersonation expirado ou revogado"
        )

    # 4. Pertence ao PLATFORM_OWNER autenticado?
    if grant.platform_user_id != user_id:
        raise HTTPException(
            status_code=403, detail="Grant de impersonation pertence a outro usuário"
        )

    # Defesa em profundidade: READ_ONLY bloqueia métodos mutantes já aqui.
    if grant.mode == "READ_ONLY" and method.upper() not in _SAFE_METHODS:
        raise HTTPException(
            status_code=403,
            detail="Impersonation READ_ONLY — escrita exige mode=ELEVATED",
        )

    return grant


def audit_impersonated_request(db: Session, grant, actor_id: UUID, path: str, method: str):
    """Registra o acesso impersonado em audit_logs (visível ao tenant)."""
    from app.core.audit.sensitive_context import (
        SensitiveAuditContext,
        record_sensitive_action,
    )

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor_id,
            actor_role="PLATFORM_OWNER",
            action="impersonated_request",
            resource_type="ImpersonationGrant",
            resource_id=grant.id,
            company_id=grant.company_id,
            reason=grant.reason,
            after_snapshot={"path": path, "method": method, "mode": grant.mode},
        ),
        db,
    )
    db.commit()


def require_not_read_only(request: Request) -> None:
    """Dependency para endpoints que modificam dados.

    Se a request está impersonada com mode=READ_ONLY → 403.
    Sem impersonation: no-op.
    """
    if getattr(request.state, "impersonating", False):
        grant = getattr(request.state, "impersonation_grant", None)
        if grant is not None and grant.mode == "READ_ONLY":
            raise HTTPException(
                status_code=403,
                detail="Impersonation READ_ONLY — escrita exige mode=ELEVATED",
            )


class ImpersonationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        grant_id = request.headers.get(IMPERSONATE_HEADER)
        if not grant_id:
            return await call_next(request)

        from app.infrastructure.db.session import SessionLocal

        db = SessionLocal()
        try:
            grant = validate_impersonation_request(
                db,
                grant_id,
                request.headers.get("Authorization", ""),
                request.method,
            )
            request.state.impersonating = True
            request.state.impersonation_grant = grant
            request.state.effective_company_id = grant.company_id
            audit_impersonated_request(
                db, grant, grant.platform_user_id, request.url.path, request.method
            )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail}
            )
        except Exception:
            logger.exception("ImpersonationMiddleware: falha inesperada")
            return JSONResponse(
                status_code=500, content={"detail": "Erro interno de impersonation"}
            )
        finally:
            db.close()

        return await call_next(request)
