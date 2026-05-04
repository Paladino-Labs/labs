import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import company_id_ctx, request_id_ctx, user_id_ctx


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Gera um request_id por requisição, extrai contexto do JWT se presente,
    e injeta X-Request-ID no header de resposta."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = str(uuid.uuid4())
        request_id_ctx.set(rid)
        user_id_ctx.set("-")
        company_id_ctx.set("-")

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            _try_set_jwt_context(auth[7:])

        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def _try_set_jwt_context(token: str) -> None:
    try:
        from jose import jwt, JWTError
        from app.core.config import settings

        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        if sub := payload.get("sub"):
            user_id_ctx.set(str(sub))
        if cid := payload.get("company_id"):
            company_id_ctx.set(str(cid))
    except Exception:
        pass
