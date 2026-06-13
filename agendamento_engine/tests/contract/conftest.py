"""Suite de testes de contrato — Estágio 0 (Sprint 25).

Valida os invariantes ponta a ponta do Estágio 0. Roda contra **SQLite/FakeDB**
por padrão (chamando os service functions reais) e tem variantes contra
**PostgreSQL real** (gated por `DATABASE_URL`) para EXCLUDE CONSTRAINT e RLS.

FakeDB avalia critérios reais de filtro do SQLAlchemy (padrão herdado dos
Sprints D/2.7), estendido para ge/le/gt/lt/in_/notin_ e um `execute` mínimo
que implementa a semântica de `processed_idempotency_keys` (idempotência).
"""
import os
import uuid
from datetime import datetime, timezone

import pytest

DATABASE_URL = os.getenv("DATABASE_URL")
requires_postgres = pytest.mark.skipif(
    not DATABASE_URL,
    reason="Requer PostgreSQL real — rodar com DATABASE_URL do Supabase",
)


# ── Avaliação de critérios de filtro ─────────────────────────────────────────

def _right_value(right):
    cls = right.__class__.__name__
    if cls == "True_":
        return True
    if cls == "False_":
        return False
    if cls == "Null":
        return None
    return getattr(right, "value", None)


def _criterion_matches(obj, c) -> bool:
    key = c.left.key
    actual = getattr(obj, key, None)
    op_name = getattr(c.operator, "__name__", "")
    val = _right_value(c.right)

    if op_name.startswith("notin") or op_name in ("not_in_op",):
        return actual not in (val or [])
    if op_name.startswith("in_"):
        return actual in (val or [])
    if op_name in ("is_", "is_op"):
        return actual is val
    if op_name in ("ne", "is_not", "is_not_op", "isnot"):
        return actual != val
    if op_name in ("lt",):
        return actual is not None and actual < val
    if op_name in ("le",):
        return actual is not None and actual <= val
    if op_name in ("gt",):
        return actual is not None and actual > val
    if op_name in ("ge",):
        return actual is not None and actual >= val
    return actual == val


class FakeQuery:
    def __init__(self, items):
        self.items = list(items)

    def filter(self, *criteria):
        return FakeQuery(
            [i for i in self.items if all(_criterion_matches(i, c) for c in criteria)]
        )

    def filter_by(self, **kw):
        return FakeQuery(
            [i for i in self.items if all(getattr(i, k, None) == v for k, v in kw.items())]
        )

    def options(self, *a, **k):
        return self

    def with_for_update(self, *a, **k):
        return self

    def order_by(self, *args, **k):
        items = list(self.items)
        for arg in reversed(args):
            element = getattr(arg, "element", arg)
            key = getattr(element, "key", None)
            modifier = getattr(arg, "modifier", None)
            descending = "desc" in getattr(modifier, "__name__", "")
            if key:
                items.sort(key=lambda o: (getattr(o, key, None) is None, getattr(o, key, None)),
                           reverse=descending)
        return FakeQuery(items)

    def offset(self, n):
        return FakeQuery(self.items[n:])

    def limit(self, n):
        return FakeQuery(self.items[:n])

    def first(self):
        return self.items[0] if self.items else None

    def all(self):
        return list(self.items)

    def count(self):
        return len(self.items)


_PK_FIELDS = (
    "id", "payment_id", "reservation_id", "policy_id", "commission_id",
    "payout_id", "movement_id", "entry_id", "account_id", "survey_id",
)


class FakeDB:
    """DB em memória multi-modelo com avaliação real de filtros."""

    def __init__(self):
        self.stores: dict = {}
        self.commits = 0
        self._idem: set = set()  # (key, consumer) — processed_idempotency_keys

    def _store(self, model):
        return self.stores.setdefault(model, [])

    def store_for(self, model):
        return self._store(model)

    def query(self, model, *rest):
        return FakeQuery(self._store(model))

    def add(self, obj):
        for pk in _PK_FIELDS:
            if hasattr(obj, pk) and getattr(obj, pk, None) is None:
                setattr(obj, pk, uuid.uuid4())
                break
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            try:
                obj.created_at = datetime.now(timezone.utc)
            except Exception:
                pass
        self._store(type(obj)).append(obj)

    def add_all(self, objs):
        for o in objs:
            self.add(o)

    # ── execute() mínimo: semântica de processed_idempotency_keys ────────────
    def execute(self, statement, params=None):
        sql = str(statement).lower()
        params = params or {}
        if "select 1 from processed_idempotency_keys" in sql:
            hit = (params.get("key"), params.get("consumer")) in self._idem
            return _FakeResult(1 if hit else None)
        if "insert into processed_idempotency_keys" in sql:
            self._idem.add((params.get("key"), params.get("consumer")))  # ON CONFLICT DO NOTHING
            return _FakeResult(None)
        return _FakeResult(None)

    def commit(self):
        self.commits += 1

    def flush(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def first(self):
        return (self._value,) if self._value is not None else None

    def scalar(self):
        return self._value


@pytest.fixture
def db():
    return FakeDB()
