from fastapi import HTTPException


def not_found(entity: str = "Recurso") -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} não encontrado")


def forbidden(detail: str = "Sem permissão") -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


def conflict(detail: str = "Conflito") -> HTTPException:
    return HTTPException(status_code=409, detail=detail)


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Não autenticado")
