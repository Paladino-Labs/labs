from fastapi import HTTPException


def require_admin(current_user) -> None:
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
