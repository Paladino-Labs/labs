from datetime import datetime, timezone
from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _now_utc() -> datetime:
    """Retorna datetime atual sempre timezone-aware (UTC). Evita naive datetimes."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = Column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
        nullable=False,
    )
