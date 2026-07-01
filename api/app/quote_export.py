"""CSV export for the main quotes list."""
import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import ColumnElement
from sqlmodel import Session, select

from app.constants import VAT_RATE_DECIMAL
from app.models import (
    Customer,
    Dealer,
    Lead,
    Quote,
    QuoteDiscount,
    QuoteItem,
    User,
)
from app.routers.quotes import (
    batch_lead_quotes_sent_counts,
    batch_quote_list_lookups,
    batch_reply_metrics_since_sent,
)

CSV_HEADERS = [
    "id",
    "quote_number",
    "version",
    "status",
    "temperature",
    "archived_at",
    "customer_id",
    "customer_number",
    "customer_name",
    "customer_email",
    "customer_phone",
    "customer_postcode",
    "lead_id",
    "lead_name",
    "lead_type",
    "dealer_id",
    "dealer_name",
    "dealer_customer_name",
    "dealer_customer_email",
    "dealer_customer_phone",
    "dealer_customer_address",
    "dealer_customer_postcode",
    "subtotal",
    "discount_total",
    "total_amount",
    "vat_amount",
    "total_amount_inc_vat",
    "deposit_amount",
    "balance_amount",
    "currency",
    "created_at",
    "updated_at",
    "valid_until",
    "sent_at",
    "viewed_at",
    "last_viewed_at",
    "accepted_at",
    "total_open_count",
    "customer_last_interacted_at",
    "lead_quotes_sent_count",
    "customer_replied_since_quote_sent",
    "inbound_count_since_quote_sent",
    "opportunity_stage",
    "close_probability",
    "expected_close_date",
    "next_action",
    "next_action_due_date",
    "loss_reason",
    "loss_category",
    "owner_name",
    "fulfillment_method",
    "use_alternate_delivery_address",
    "delivery_address_line1",
    "delivery_address_line2",
    "delivery_city",
    "delivery_county",
    "delivery_postcode",
    "delivery_country",
    "delivery_location_notes",
    "order_id",
    "created_by_name",
    "notes",
    "payment_link_url",
    "line_items_summary",
    "discounts_summary",
]


def _fmt_dt(value: Optional[datetime]) -> str:
    return value.isoformat() if value else ""


def _fmt_decimal(value: Optional[Decimal]) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def _fmt_enum(value) -> str:
    if value is None:
        return ""
    return value.value if hasattr(value, "value") else str(value)


def _fmt_bool(value: bool) -> str:
    return "Yes" if value else "No"


def _line_items_summary(items: List[QuoteItem]) -> str:
    parts = []
    for item in sorted(items, key=lambda row: (row.sort_order, row.id or 0)):
        parts.append(
            f"{item.quantity} x {item.description} @ {_fmt_decimal(item.unit_price)}"
            f" = {_fmt_decimal(item.final_line_total)}"
        )
    return " | ".join(parts)


def _discounts_summary(discounts: List[QuoteDiscount]) -> str:
    parts = []
    for discount in discounts:
        scope = _fmt_enum(discount.scope)
        parts.append(f"{discount.description} ({scope}): {_fmt_decimal(discount.discount_amount)}")
    return " | ".join(parts)


def _batch_items_by_quote(session: Session, quote_ids: List[int]) -> Dict[int, List[QuoteItem]]:
    if not quote_ids:
        return {}
    items_by_quote: Dict[int, List[QuoteItem]] = {}
    for item in session.exec(
        select(QuoteItem)
        .where(QuoteItem.quote_id.in_(quote_ids))
        .order_by(QuoteItem.quote_id, QuoteItem.sort_order, QuoteItem.id)
    ).all():
        if item.quote_id is not None:
            items_by_quote.setdefault(int(item.quote_id), []).append(item)
    return items_by_quote


def _batch_discounts_by_quote(session: Session, quote_ids: List[int]) -> Dict[int, List[QuoteDiscount]]:
    if not quote_ids:
        return {}
    discounts_by_quote: Dict[int, List[QuoteDiscount]] = {}
    for discount in session.exec(
        select(QuoteDiscount).where(QuoteDiscount.quote_id.in_(quote_ids))
    ).all():
        if discount.quote_id is not None:
            discounts_by_quote.setdefault(int(discount.quote_id), []).append(discount)
    return discounts_by_quote


def _batch_users_by_id(session: Session, user_ids: List[int]) -> Dict[int, User]:
    if not user_ids:
        return {}
    users_by_id: Dict[int, User] = {}
    for user in session.exec(select(User).where(User.id.in_(user_ids))).all():
        if user.id is not None:
            users_by_id[int(user.id)] = user
    return users_by_id


def _batch_dealers_by_id(session: Session, dealer_ids: List[int]) -> Dict[int, Dealer]:
    if not dealer_ids:
        return {}
    dealers_by_id: Dict[int, Dealer] = {}
    for dealer in session.exec(select(Dealer).where(Dealer.id.in_(dealer_ids))).all():
        if dealer.id is not None:
            dealers_by_id[int(dealer.id)] = dealer
    return dealers_by_id


def export_quotes_to_csv(session: Session, where_clause: ColumnElement) -> str:
    """Export all quotes matching where_clause as CSV text."""
    from app.models import Customer as CustomerModel, Lead as LeadModel

    statement = (
        select(Quote)
        .outerjoin(CustomerModel, Quote.customer_id == CustomerModel.id)
        .outerjoin(LeadModel, Quote.lead_id == LeadModel.id)
        .where(where_clause)
        .order_by(Quote.created_at.desc())
    )
    quotes = list(session.exec(statement).all())

    lead_ids_page = list({q.lead_id for q in quotes if q.lead_id})
    lead_sent_map = batch_lead_quotes_sent_counts(session, lead_ids_page)
    reply_map = batch_reply_metrics_since_sent(session, quotes)
    (
        customers_by_id,
        leads_by_id,
        open_counts_by_quote,
        order_id_by_quote,
        last_activity_by_customer,
    ) = batch_quote_list_lookups(session, quotes)

    quote_ids = [q.id for q in quotes if q.id is not None]
    items_by_quote = _batch_items_by_quote(session, quote_ids)
    discounts_by_quote = _batch_discounts_by_quote(session, quote_ids)

    user_ids = list(
        {
            uid
            for q in quotes
            for uid in (q.created_by_id, q.owner_id)
            if uid is not None
        }
    )
    users_by_id = _batch_users_by_id(session, user_ids)

    dealer_ids = list({q.dealer_id for q in quotes if q.dealer_id})
    dealers_by_id = _batch_dealers_by_id(session, dealer_ids)

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(CSV_HEADERS)

    for quote in quotes:
        if quote.id is None:
            continue
        qid = int(quote.id)

        customer: Optional[Customer] = None
        customer_name = None
        customer_last_interacted_at = None
        if quote.customer_id:
            cid = int(quote.customer_id)
            customer = customers_by_id.get(cid)
            customer_name = customer.name if customer else None
            customer_last_interacted_at = last_activity_by_customer.get(cid)
        elif quote.dealer_customer_name:
            customer_name = quote.dealer_customer_name

        lead_name = None
        lead_type = None
        if quote.lead_id:
            lead = leads_by_id.get(int(quote.lead_id))
            if lead:
                lead_name = lead.name
                lead_type = lead.lead_type

        replied, inbound_n = reply_map.get(qid, (False, 0))
        lead_n = lead_sent_map.get(int(quote.lead_id), 0) if quote.lead_id else None

        created_by = users_by_id.get(int(quote.created_by_id)) if quote.created_by_id else None
        owner = users_by_id.get(int(quote.owner_id)) if quote.owner_id else None
        dealer = dealers_by_id.get(int(quote.dealer_id)) if quote.dealer_id else None

        vat_amount = quote.total_amount * VAT_RATE_DECIMAL
        total_amount_inc_vat = quote.total_amount + vat_amount

        writer.writerow(
            [
                qid,
                quote.quote_number,
                quote.version,
                _fmt_enum(quote.status),
                _fmt_enum(quote.temperature),
                _fmt_dt(getattr(quote, "archived_at", None)),
                quote.customer_id or "",
                customer.customer_number if customer else "",
                customer_name or "",
                customer.email if customer else "",
                customer.phone if customer else "",
                customer.postcode if customer else "",
                quote.lead_id or "",
                lead_name or "",
                _fmt_enum(lead_type),
                quote.dealer_id or "",
                dealer.name if dealer else "",
                getattr(quote, "dealer_customer_name", None) or "",
                getattr(quote, "dealer_customer_email", None) or "",
                getattr(quote, "dealer_customer_phone", None) or "",
                getattr(quote, "dealer_customer_address", None) or "",
                getattr(quote, "dealer_customer_postcode", None) or "",
                _fmt_decimal(quote.subtotal),
                _fmt_decimal(quote.discount_total),
                _fmt_decimal(quote.total_amount),
                _fmt_decimal(vat_amount),
                _fmt_decimal(total_amount_inc_vat),
                _fmt_decimal(quote.deposit_amount),
                _fmt_decimal(quote.balance_amount),
                quote.currency,
                _fmt_dt(quote.created_at),
                _fmt_dt(quote.updated_at),
                _fmt_dt(quote.valid_until),
                _fmt_dt(quote.sent_at),
                _fmt_dt(quote.viewed_at),
                _fmt_dt(quote.last_viewed_at),
                _fmt_dt(quote.accepted_at),
                open_counts_by_quote.get(qid, 0),
                _fmt_dt(customer_last_interacted_at),
                lead_n if lead_n is not None else "",
                _fmt_bool(replied),
                inbound_n,
                _fmt_enum(quote.opportunity_stage),
                _fmt_decimal(quote.close_probability),
                _fmt_dt(quote.expected_close_date),
                quote.next_action or "",
                _fmt_dt(quote.next_action_due_date),
                quote.loss_reason or "",
                _fmt_enum(quote.loss_category),
                owner.full_name if owner else "",
                _fmt_enum(getattr(quote, "fulfillment_method", None)),
                _fmt_bool(getattr(quote, "use_alternate_delivery_address", False)),
                getattr(quote, "delivery_address_line1", None) or "",
                getattr(quote, "delivery_address_line2", None) or "",
                getattr(quote, "delivery_city", None) or "",
                getattr(quote, "delivery_county", None) or "",
                getattr(quote, "delivery_postcode", None) or "",
                getattr(quote, "delivery_country", None) or "",
                getattr(quote, "delivery_location_notes", None) or "",
                order_id_by_quote.get(qid, ""),
                created_by.full_name if created_by else "",
                quote.notes or "",
                getattr(quote, "payment_link_url", None) or "",
                _line_items_summary(items_by_quote.get(qid, [])),
                _discounts_summary(discounts_by_quote.get(qid, [])),
            ]
        )

    return output.getvalue()
