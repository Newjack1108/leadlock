"""Staff shed commission: deposit is turnover; balance is not."""
from decimal import Decimal
from typing import Optional, Sequence

from sqlmodel import Session

from app.constants import (
    STAFF_DEFAULT_DEPOSIT_RATE,
    STAFF_SHED_COMMISSION_DEPOSIT_RATE,
    VAT_RATE_DECIMAL,
)
from app.models import LeadType, Order, Quote, QuoteItem
from app.quote_brand import resolve_quote_brand_lead_type

_VAT_MULTIPLIER = Decimal("1") + VAT_RATE_DECIMAL


def is_staff_shed_commission_sale(
    quote: Quote,
    items: Sequence[QuoteItem],
    session: Optional[Session],
) -> bool:
    """True when a staff (non-dealer) quote is a shed agency/commission sale."""
    if quote.dealer_id is not None:
        return False
    return resolve_quote_brand_lead_type(quote, items, session) == LeadType.SHEDS


def default_deposit_rate(
    quote: Quote,
    items: Sequence[QuoteItem],
    session: Optional[Session],
) -> Decimal:
    """Fraction of total inc VAT used when deposit_amount is omitted."""
    if is_staff_shed_commission_sale(quote, items, session):
        return STAFF_SHED_COMMISSION_DEPOSIT_RATE
    return STAFF_DEFAULT_DEPOSIT_RATE


def default_deposit_amount(
    total_inc_vat: Decimal,
    quote: Quote,
    items: Sequence[QuoteItem],
    session: Optional[Session],
) -> Decimal:
    """Default deposit (inc VAT) for a quote."""
    rate = default_deposit_rate(quote, items, session)
    return total_inc_vat * rate


def recognised_turnover(
    total_amount: Decimal,
    deposit_amount: Decimal,
    *,
    is_commission: bool,
) -> Decimal:
    """
    Ex-VAT amount that counts as company turnover.

    For staff shed commission sales, only the deposit (ex VAT) counts.
    Otherwise the full quote/order total_amount (ex VAT) counts.
    """
    if not is_commission:
        return _decimal_or_zero(total_amount)
    deposit = _decimal_or_zero(deposit_amount)
    if deposit <= 0:
        return Decimal("0")
    return (deposit / _VAT_MULTIPLIER).quantize(Decimal("0.01"))


def quote_recognised_turnover(
    quote: Quote,
    items: Sequence[QuoteItem],
    session: Optional[Session],
) -> Decimal:
    """Recognised turnover for a quote."""
    return recognised_turnover(
        quote.total_amount,
        quote.deposit_amount,
        is_commission=is_staff_shed_commission_sale(quote, items, session),
    )


def order_recognised_turnover(
    order: Order,
    quote: Optional[Quote],
    items: Sequence[QuoteItem],
    session: Optional[Session],
) -> Decimal:
    """Recognised turnover for an order (uses linked quote for commission detection)."""
    if quote is None:
        return _decimal_or_zero(order.total_amount)
    return recognised_turnover(
        order.total_amount,
        order.deposit_amount,
        is_commission=is_staff_shed_commission_sale(quote, items, session),
    )


def _decimal_or_zero(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
