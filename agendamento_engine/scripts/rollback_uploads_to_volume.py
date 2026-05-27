"""Script de rollback: reverte URLs de Supabase Storage para volume local.

Execução:
    python scripts/rollback_uploads_to_volume.py [--dry-run]

Requisito: arquivos ainda presentes em static/uploads/ (volume não removido).
Atenção: testar em staging com dump de produção ANTES do go-live.
"""
import argparse
import os
import sys
from pathlib import Path

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


def supabase_url_to_local(supabase_url: str, filename: str) -> str:
    return f"{WEBHOOK_BASE_URL}/static/uploads/{filename}"


def main(dry_run: bool) -> None:
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    engine = create_engine(DATABASE_URL)

    # Lista arquivos no bucket Supabase para construir o mapeamento reverso
    files = client.storage.from_(SUPABASE_STORAGE_BUCKET).list()
    if not files:
        print("Bucket vazio — nada a reverter.")
        return

    url_map: dict[str, str] = {}
    for f in files:
        filename = f["name"]
        supabase_url = client.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(filename)
        local_url = supabase_url_to_local(supabase_url, filename)
        url_map[supabase_url] = local_url

    print(f"Revertendo {len(url_map)} URLs...")

    with Session(engine) as db:
        single_url_targets = [
            ("professionals", "image_url"),
            ("services", "image_url"),
            ("products", "image_url"),
            ("company_profiles", "logo_url"),
            ("company_profiles", "cover_url"),
        ]
        for table, col in single_url_targets:
            for supabase_url, local_url in url_map.items():
                if dry_run:
                    print(f"  [dry-run] UPDATE {table}.{col}: {supabase_url} → {local_url}")
                else:
                    result = db.execute(
                        text(f"UPDATE {table} SET {col} = :new WHERE {col} = :old"),
                        {"new": local_url, "old": supabase_url},
                    )
                    if result.rowcount:
                        print(f"  {table}.{col}: {result.rowcount} linha(s)")

        for supabase_url, local_url in url_map.items():
            if dry_run:
                print(f"  [dry-run] UPDATE company_profiles.gallery_urls: {supabase_url}")
            else:
                db.execute(
                    text(
                        """
                        UPDATE company_profiles
                        SET gallery_urls = array_replace(gallery_urls, :old, :new)
                        WHERE :old = ANY(gallery_urls)
                        """
                    ),
                    {"old": supabase_url, "new": local_url},
                )

        if not dry_run:
            db.commit()

    print("\nRollback concluído.")
    if dry_run:
        print("(dry-run: nenhuma alteração foi persistida)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
