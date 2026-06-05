"""
Customer review hub: one short link per order with platform review buttons.
"""
from __future__ import annotations

import os
import secrets
from typing import List, Optional, Tuple

from sqlmodel import Session, select

from app.models import CompanySettings, Customer, Order, ReviewHubRequest
from app.review_prize_draw_service import (
    build_prize_draw_url,
    configured_platforms,
    ensure_prize_draw_entry,
    is_prize_draw_enabled,
)

PLATFORM_URL_FIELDS = {
    "GOOGLE": "review_google_url",
    "FACEBOOK": "review_facebook_url",
    "TRUSTPILOT": "review_trustpilot_url",
}


def build_review_hub_url(token: str) -> str:
    frontend = (os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL") or "").strip()
    if not frontend or not (frontend.startswith("http://") or frontend.startswith("https://")):
        frontend = "https://leadlock-frontend-production.up.railway.app"
    base = frontend.rstrip("/")
    return f"{base}/review/{token}"


def _get_company_settings(session: Session) -> Optional[CompanySettings]:
    return session.exec(select(CompanySettings).limit(1)).first()


def get_hub_for_order(session: Session, order_id: int) -> Optional[ReviewHubRequest]:
    return session.exec(
        select(ReviewHubRequest)
        .where(ReviewHubRequest.order_id == order_id)
        .order_by(ReviewHubRequest.created_at.desc())
        .limit(1)
    ).first()


def get_hub_by_token(session: Session, token: str) -> Optional[ReviewHubRequest]:
    return session.exec(
        select(ReviewHubRequest).where(ReviewHubRequest.access_token == token)
    ).first()


def ensure_review_hub_request(order: Order, session: Session) -> Optional[ReviewHubRequest]:
    """Mint a review hub token for an order (idempotent)."""
    if not order.id:
        return None

    existing = get_hub_for_order(session, order.id)
    if existing:
        return existing

    hub = ReviewHubRequest(
        order_id=order.id,
        access_token=secrets.token_urlsafe(32),
    )
    session.add(hub)
    session.flush()
    return hub


def _platform_links(settings: CompanySettings) -> List[dict]:
    links: List[dict] = []
    for code, label in configured_platforms(settings):
        field = PLATFORM_URL_FIELDS.get(code)
        url = getattr(settings, field, None) if field else None
        if url:
            links.append({"code": code, "label": label, "url": url})
    return links


def get_hub_context(token: str, session: Session) -> Tuple[Optional[dict], Optional[str]]:
    """Build public hub page context. Returns (data, error_message)."""
    hub = get_hub_by_token(session, token)
    if not hub:
        return None, "Invalid or expired review link"

    order = session.get(Order, hub.order_id)
    if not order:
        return None, "Order not found"

    settings = _get_company_settings(session)
    if not settings:
        return None, "Company settings not found"

    customer = session.get(Customer, order.customer_id) if order.customer_id else None
    company_name = (settings.trading_name or settings.company_name or "").strip()
    platforms = _platform_links(settings)
    if not platforms:
        return None, "No review platforms configured"

    prize_draw = None
    if is_prize_draw_enabled(settings):
        entry = ensure_prize_draw_entry(order, session)
        if entry:
            prize_draw = {
                "title": settings.review_prize_draw_title or "Monthly prize draw",
                "terms": settings.review_prize_draw_terms,
                "min_platforms": max(1, int(settings.review_prize_draw_min_platforms or 2)),
                "url": build_prize_draw_url(entry.access_token),
            }

    return {
        "company_name": company_name,
        "customer_name": customer.name if customer else None,
        "order_number": order.order_number,
        "platforms": platforms,
        "prize_draw": prize_draw,
    }, None


def build_hub_url_for_order(order: Order, session: Session) -> str:
    """Return review hub URL for an order, minting a token if needed."""
    hub = ensure_review_hub_request(order, session)
    if not hub:
        return ""
    return build_review_hub_url(hub.access_token)
