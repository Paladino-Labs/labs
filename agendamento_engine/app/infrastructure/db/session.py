from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.core.config import settings
from app.core.logging import company_id_ctx

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        cid_str = company_id_ctx.get()
        # "-" é o valor padrão (sem JWT). None ou vazio → PLATFORM_OWNER → bypass.
        company_id = cid_str if (cid_str and cid_str != "-") else None
        set_rls_context(db, company_id)
        yield db
    finally:
        db.close()
