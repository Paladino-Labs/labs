import json
import logging
import re
from contextvars import ContextVar
from datetime import datetime, timezone

# ─── Context vars — propagados via RequestContextMiddleware ────────────────────
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
user_id_ctx: ContextVar[str] = ContextVar("user_id", default="-")
company_id_ctx: ContextVar[str] = ContextVar("company_id", default="-")

# ─── CPF / CNPJ masking ───────────────────────────────────────────────────────
_CPF_RE = re.compile(r"\d{3}(\.\d{3}\.\d{3}-)\d{2}")
_CNPJ_RE = re.compile(r"\d{2}(\.\d{3}\.\d{3}/\d{4}-)\d{2}")


def mask_cpf_cnpj(value: str) -> str:
    """Substitui CPF e CNPJ formatados por versões mascaradas.

    CPF  123.456.789-09 → ***.456.789-**
    CNPJ 12.345.678/0001-90 → **.345.678/0001-**
    Strings sem documento retornam inalteradas.
    """
    value = _CNPJ_RE.sub(r"**\1**", value)
    value = _CPF_RE.sub(r"***\1**", value)
    return value


# ─── JSON formatter ───────────────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "request_id": request_id_ctx.get(),
            "message": record.getMessage(),
        }
        uid = user_id_ctx.get()
        cid = company_id_ctx.get()
        if uid != "-":
            entry["user_id"] = uid
        if cid != "-":
            entry["company_id"] = cid
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


# ─── Public setup ─────────────────────────────────────────────────────────────

def setup_logging(level: str = "INFO") -> None:
    """Substitui todos os handlers do root logger por um handler JSON."""
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.getLevelName(level.upper()))
