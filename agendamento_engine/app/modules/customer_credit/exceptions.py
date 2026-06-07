from fastapi import HTTPException


class NoCreditAvailableError(HTTPException):
    def __init__(self, detail: str = "Nenhuma cota disponível para este cliente"):
        super().__init__(status_code=422, detail=detail)
