import mimetypes
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_company_id
from app.infrastructure.db.session import get_db
from app.modules.uploads import service as upload_service

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


@router.post("/")
async def upload_image(
    file: UploadFile = File(...),
    company_id=Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Extensão não permitida. Use: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Arquivo muito grande. Máximo: 5 MB")

    content_type = mimetypes.types_map.get(ext, "application/octet-stream")

    try:
        url = upload_service.upload_image(content, ext, content_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Falha no upload. Tente novamente.") from exc

    return {"url": url}
