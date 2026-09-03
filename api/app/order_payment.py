"""Shared payment-flag reconciliation for CRM PATCH and production webhooks."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional, Protocol


class _OrderPaymentFlags(Protocol):
    deposit_paid: Optional[bool]
    balance_paid: Optional[bool]
    paid_in_full: Optional[bool]


def is_deposit_paid(
    *,
    deposit_paid: bool = False,
    balance_paid: bool = False,
    paid_in_full: bool = False,
) -> bool:
    """Display/filter helper: deposit is satisfied if any full-payment flag is set."""
    return bool(deposit_paid or paid_in_full or balance_paid)


def is_paid_in_full(*, balance_paid: bool = False, paid_in_full: bool = False) -> bool:
    """Display/filter helper: paid in full if either full-payment flag is set."""
    return bool(paid_in_full or balance_paid)


def reconcile_payment_flags_from_update(
    update_dict: MutableMapping[str, Any],
    order: _OrderPaymentFlags | Mapping[str, Any],
) -> None:
    """
    Align deposit / balance / paid-in-full when any payment flag is written.

    - Marking paid in full or balance paid sets all three true.
    - Clearing paid in full clears paid_in_full and balance_paid; deposit stays.
    - Clearing deposit while fully paid also clears paid_in_full and balance_paid.
    """
    if not any(k in update_dict for k in ("deposit_paid", "balance_paid", "paid_in_full")):
        return

    def _current(field: str) -> bool:
        if isinstance(order, Mapping):
            return bool(order.get(field) or False)
        return bool(getattr(order, field, False) or False)

    deposit_paid = (
        bool(update_dict["deposit_paid"]) if "deposit_paid" in update_dict else _current("deposit_paid")
    )
    balance_paid = (
        bool(update_dict["balance_paid"]) if "balance_paid" in update_dict else _current("balance_paid")
    )
    paid_in_full = (
        bool(update_dict["paid_in_full"]) if "paid_in_full" in update_dict else _current("paid_in_full")
    )

    marking_full = ("paid_in_full" in update_dict and paid_in_full) or (
        "balance_paid" in update_dict and balance_paid
    )
    clearing_full = ("paid_in_full" in update_dict and not paid_in_full) or (
        "balance_paid" in update_dict and not balance_paid
    )
    clearing_deposit = "deposit_paid" in update_dict and not deposit_paid

    if marking_full:
        deposit_paid = True
        balance_paid = True
        paid_in_full = True
    elif clearing_full:
        # Leave deposit as requested/current; drop full-payment pair.
        balance_paid = False
        paid_in_full = False
        if "deposit_paid" not in update_dict:
            deposit_paid = _current("deposit_paid")
    elif clearing_deposit and (paid_in_full or balance_paid):
        # Deposit is implied by paid in full; clearing deposit un-pays the balance too.
        deposit_paid = False
        balance_paid = False
        paid_in_full = False
    elif deposit_paid and balance_paid:
        paid_in_full = True

    update_dict["deposit_paid"] = deposit_paid
    update_dict["balance_paid"] = balance_paid
    update_dict["paid_in_full"] = paid_in_full
