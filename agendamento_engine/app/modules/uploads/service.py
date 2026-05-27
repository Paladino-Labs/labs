import logging
import uuid
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def upload_to_supabase(content: bytes, filename: str, content_type: str) -> str:
    """Faz upload do arquivo para Supabase Storage e retorna a URL pública.

    Levanta Exception se o upload falhar — o caller decide se retorna 500.
    """
    from supabase import create_client

    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    bucket = settings.SUPABASE_STORAGE_BUCKET

    client.storage.from_(bucket).upload(
        path=filename,
        file=content,
        file_options={"content-type": content_type, "upsert": "false"},
    )

    result = client.storage.from_(bucket).get_public_url(filename)
    return result


def upload_image(content: bytes, ext: str, content_type: str) -> str:
    """Gera filename único, faz upload para Supabase e retorna URL pública.

    Dual-write: Supabase é fonte de verdade. Volume local foi desativado.
    Matriz de falha: Supabase falha → Exception propagada → 500.
    """
    filename = f"{uuid.uuid4().hex}{ext}"
    url = upload_to_supabase(content, filename, content_type)
    return url
