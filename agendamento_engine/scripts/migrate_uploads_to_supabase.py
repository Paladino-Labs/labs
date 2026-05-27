"""Script one-shot: copia uploads do volume local para Supabase Storage.

Execução:
    python scripts/migrate_uploads_to_supabase.py [--dry-run]

Etapas:
  1. Lê todos os arquivos em static/uploads/
  2. Faz upload de cada arquivo para Supabase Storage (skip se já existir)
  3. Atualiza URLs nas tabelas:
       professionals.image_url
       services.image_url
       products.image_url
       company_profiles.logo_url
       company_profiles.cover_url
       company_profiles.gallery_urls  (array JSONB)

Requisito: SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_STORAGE_BUCKET no .env
"""
import argparse
import os
import sys
from pathlib import Path

# Garante que o módulo app pode ser importado
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "uploads")
DATABASE_URL = os.environ["DATABASE_URL"]
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_BASE_URL", "http://localhost:8000")

LOCAL_UPLOAD_DIR = Path("static/uploads")


def get_public_url(client, filename: str) -> str:
    return client.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(filename)


def upload_file(client, path: Path, dry_run: bool) -> str:
    filename = path.name
    if dry_run:
        print(f"  [dry-run] upload: {filename}")
        return get_public_url(client, filename)

    content = path.read_bytes()
    import mimetypes
    ext = path.suffix.lower()
    content_type = mimetypes.types_map.get(ext, "application/octet-stream")
    try:
        client.storage.from_(SUPABASE_STORAGE_BUCKET).upload(
            path=filename,
            file=content,
            file_options={"content-type": content_type, "upsert": "false"},
        )
        print(f"  uploaded: {filename}")
    except Exception as exc:
        if "already exists" in str(exc).lower() or "duplicate" in str(exc).lower():
            print(f"  skip (already exists): {filename}")
        else:
            print(f"  ERROR uploading {filename}: {exc}")
            raise
    return get_public_url(client, filename)


def local_url(filename: str) -> str:
    return f"{WEBHOOK_BASE_URL}/static/uploads/{filename}"


def main(dry_run: bool) -> None:
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    engine = create_engine(DATABASE_URL)

    if not LOCAL_UPLOAD_DIR.exists():
        print("static/uploads/ não existe — nada a migrar.")
        return

    files = list(LOCAL_UPLOAD_DIR.iterdir())
    print(f"Arquivos encontrados: {len(files)}")

    url_map: dict[str, str] = {}
    for f in files:
        if f.is_file():
            supabase_url = upload_file(client, f, dry_run)
            url_map[local_url(f.name)] = supabase_url

    if not url_map:
        print("Nenhum arquivo para migrar.")
        return

    print(f"\nAtualizando URLs no banco ({len(url_map)} arquivos)...")

    with Session(engine) as db:
        # Tabelas com coluna única de URL
        single_url_targets = [
            ("professionals", "image_url"),
            ("services", "image_url"),
            ("products", "image_url"),
            ("company_profiles", "logo_url"),
            ("company_profiles", "cover_url"),
        ]
        for table, col in single_url_targets:
            for old_url, new_url in url_map.items():
                if dry_run:
                    print(f"  [dry-run] UPDATE {table}.{col}: {old_url} → {new_url}")
                else:
                    result = db.execute(
                        text(f"UPDATE {table} SET {col} = :new WHERE {col} = :old"),
                        {"new": new_url, "old": old_url},
                    )
                    if result.rowcount:
                        print(f"  {table}.{col}: {result.rowcount} linha(s)")

        # gallery_urls é ARRAY(String) — usa array_replace nativo do PostgreSQL
        for old_url, new_url in url_map.items():
            if dry_run:
                print(f"  [dry-run] UPDATE company_profiles.gallery_urls: {old_url}")
            else:
                result = db.execute(
                    text(
                        """
                        UPDATE company_profiles
                        SET gallery_urls = array_replace(gallery_urls, :old, :new)
                        WHERE :old = ANY(gallery_urls)
                        """
                    ),
                    {"old": old_url, "new": new_url},
                )
                if result.rowcount:
                    print(f"  company_profiles.gallery_urls: {result.rowcount} linha(s)")

        if not dry_run:
            db.commit()

    print("\nMigração concluída.")
    if dry_run:
        print("(dry-run: nenhuma alteração foi persistida)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
