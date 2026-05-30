"""
Context manager de sessão DB para tasks Celery.

Uso:
    with celery_db_session(company_id) as db:
        # queries aqui — RLS já configurado
        db.commit()  # opcional: auto-commit no exit do with

company_id=None → bypass RLS (worker de plataforma, ex: cleanup, scan multi-tenant).
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from app.core.db_rls import set_rls_context


@contextmanager
def celery_db_session(company_id: str | None) -> Generator[Session, None, None]:
    from app.infrastructure.db.session import SessionLocal

    db = SessionLocal()
    try:
        set_rls_context(db, company_id)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
