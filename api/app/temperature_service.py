"""
Temperature rules for quotes (COLD / WARM / HOT).
Recomputes quote temperature from engagement (opens) and optional cooling.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select, func

from app.models import Quote, QuoteEmail, QuoteTemperature, QuoteStatus

# Engagement thresholds
HOT_OPENS_THRESHOLD = 3
WARM_OPENS_THRESHOLD = 1

# Cooling: downgrade when no view for this many days
COOLING_DAYS_TO_WARM = 14   # HOT -> WARM after 14 days without view
COOLING_DAYS_TO_COLD = 30   # WARM (or HOT) -> COLD after 30 days without view


def _total_opens(session: Session, quote_id: int) -> int:
    """Total times the quote view link was opened (across all sends)."""
    total = session.exec(
        select(func.coalesce(func.sum(QuoteEmail.open_count), 0)).where(
            QuoteEmail.quote_id == quote_id
        )
    ).first() or 0
    return int(total) if hasattr(total, "__int__") else 0


def _days_since(dt: Optional[datetime]) -> Optional[float]:
    """Days since the given datetime (UTC). None if dt is None."""
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    # Ensure we compare timezone-aware to timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    return delta.total_seconds() / (24 * 3600)


def recompute_quote_temperature(session: Session, quote_id: int) -> Optional[QuoteTemperature]:
    """
    Apply temperature rules for a quote: upgrade from opens, optionally cool by inactivity.
    Only applies to SENT quotes. Updates quote.temperature if changed; caller should commit.
    Returns the (possibly new) temperature, or None if quote not found or not SENT.
    """
    quote = session.get(Quote, quote_id)
    if not quote:
        return None
    if quote.status != QuoteStatus.SENT:
        return quote.temperature

    total_opens = _total_opens(session, quote_id)
    current = quote.temperature

    # 1) Engagement-based temperature
    if total_opens >= HOT_OPENS_THRESHOLD:
        candidate = QuoteTemperature.HOT
    elif total_opens >= WARM_OPENS_THRESHOLD or quote.viewed_at is not None:
        candidate = QuoteTemperature.WARM
    else:
        candidate = QuoteTemperature.COLD

    # 2) Cooling: downgrade if no recent view
    if quote.last_viewed_at is not None:
        days = _days_since(quote.last_viewed_at)
        if days is not None:
            if days >= COOLING_DAYS_TO_COLD:
                candidate = QuoteTemperature.COLD
            elif days >= COOLING_DAYS_TO_WARM and candidate == QuoteTemperature.HOT:
                candidate = QuoteTemperature.WARM

    if candidate != current:
        quote.temperature = candidate
        session.add(quote)
        return candidate
    return current
