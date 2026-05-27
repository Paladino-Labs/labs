from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def get_real_ip(request: Request) -> str:
    """Extrai o IP real do cliente considerando proxies reversos (Railway, etc.).

    Railway injeta X-Forwarded-For com o IP original do cliente como primeiro
    elemento. Sem esse tratamento, todo tráfego chegaria do mesmo IP do load
    balancer e o rate limit bloquearia todos os usuários simultaneamente.
    """
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=get_real_ip)
