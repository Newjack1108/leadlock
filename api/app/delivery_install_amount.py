"""Identify and sum delivery/installation line amounts (Ex VAT) on quotes/orders."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence, Tuple

from app.models import QuoteItemLineType

DELIVERY_INSTALL_DESCRIPTIONS = frozenset(
    ("Delivery & Installation", "Delivery only", "Delivery", "Installation")
)


def is_delivery_or_install_line(item: Any) -> bool:
    """True when the line is a delivery or installation fee (by line_type or description)."""
    line_type = getattr(item, "line_type", None)
    if line_type in (QuoteItemLineType.DELIVERY, QuoteItemLineType.INSTALLATION):
        return True
    if isinstance(line_type, str) and line_type.upper() in (
        QuoteItemLineType.DELIVERY.value,
        QuoteItemLineType.INSTALLATION.value,
    ):
        return True
    desc = (getattr(item, "description", None) or "").strip()
    return desc in DELIVERY_INSTALL_DESCRIPTIONS


def _line_amount_ex_vat(item: Any) -> Decimal:
    final_total = getattr(item, "final_line_total", None)
    if final_total is not None:
        return Decimal(str(final_total))
    qty = Decimal(str(getattr(item, "quantity", 0) or 0))
    unit = Decimal(str(getattr(item, "unit_price", 0) or 0))
    return qty * unit


def sum_delivery_install_ex_vat(
    items: Sequence[Any] | Iterable[Any],
) -> Tuple[Optional[Decimal], Optional[str]]:
    """
    Sum Ex VAT delivery/install line totals.

    Returns (amount, label). amount is None when no matching lines.
    label is a single description or a comma-joined list when multiple.
    """
    matched: list[Any] = [item for item in items if is_delivery_or_install_line(item)]
    if not matched:
        return None, None
    total = sum((_line_amount_ex_vat(item) for item in matched), Decimal("0"))
    labels: list[str] = []
    seen: set[str] = set()
    for item in matched:
        desc = (getattr(item, "description", None) or "").strip()
        if desc and desc not in seen:
            seen.add(desc)
            labels.append(desc)
    label = ", ".join(labels) if labels else "Delivery / Installation"
    return total.quantize(Decimal("0.01")), label
