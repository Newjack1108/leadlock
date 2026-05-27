"""Small helpers for SQLAlchemy/SQLModel query results."""
from typing import Any


def scalar_int(value: Any) -> int:
    """Coerce func.count() / scalar .one() results to int (int, Row, or tuple)."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (tuple, list)):
        return int(value[0]) if value else 0
    if hasattr(value, "_mapping"):
        return int(next(iter(value._mapping.values())))
    if hasattr(value, "__getitem__"):
        try:
            return int(value[0])
        except (TypeError, IndexError, KeyError):
            pass
    return int(value)
