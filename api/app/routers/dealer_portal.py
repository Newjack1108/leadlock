import hashlib
from datetime import datetime
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, select

from app.auth import require_dealer_user
from app.constants import VAT_RATE_DECIMAL
from app.database import get_session
from app.models import (
    Customer,
    Dealer,
    DealerAllowedDiscount,
    DealerDiscountPolicy,
    DealerProductAccess,
    DiscountTemplate,
    Product,
    ProductOptionalExtra,
    Quote,
    QuoteDiscount,
    QuoteItem,
    QuoteStatus,
    User,
)
from app.quote_pdf_service import generate_quote_pdf_cached
from app.routers.quotes import apply_discount_to_quote, build_quote_response, generate_quote_number
from app.schemas import (
    DealerAllowedDiscountPolicyResponse,
    DealerQuoteCreate,
    DealerWelcomeResponse,
    ProductResponse,
    QuoteListResponse,
    QuoteResponse,
)


router = APIRouter(prefix="/api/dealer-portal", tags=["dealer-portal"])


def _get_dealer_or_404(session: Session, dealer_id: int) -> Dealer:
    dealer = session.get(Dealer, dealer_id)
    if not dealer or not dealer.is_active:
        raise HTTPException(status_code=404, detail="Dealer not found")
    return dealer


def _require_dealer_quote_access(quote: Quote, current_user: User) -> None:
    if quote.dealer_id != current_user.dealer_id:
        raise HTTPException(status_code=404, detail="Quote not found")


def _build_quote_revision_hash(quote: Quote, items: List[QuoteItem]) -> str:
    payload = [
        f"quote:{quote.id}",
        f"updated:{quote.updated_at.isoformat() if quote.updated_at else ''}",
        f"total:{quote.total_amount}",
    ]
    for item in sorted(items, key=lambda x: (x.sort_order, x.id or 0)):
        payload.append(
            "|".join(
                [
                    str(item.product_id or 0),
                    str(item.quantity),
                    str(item.unit_price),
                    str(item.line_total),
                    str(item.discount_amount),
                ]
            )
        )
    return hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()


@router.get("/welcome", response_model=DealerWelcomeResponse)
async def dealer_welcome(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dealer_user),
):
    dealer = _get_dealer_or_404(session, current_user.dealer_id)
    return DealerWelcomeResponse(
        dealer_id=dealer.id,
        dealer_name=dealer.name,
        user_id=current_user.id,
        user_name=current_user.full_name,
        commission_pct=current_user.dealer_commission_pct or 10,
    )


@router.get("/discount-policy", response_model=DealerAllowedDiscountPolicyResponse)
async def get_discount_policy(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dealer_user),
):
    _get_dealer_or_404(session, current_user.dealer_id)
    policy = session.exec(
        select(DealerDiscountPolicy).where(DealerDiscountPolicy.dealer_id == current_user.dealer_id)
    ).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Dealer discount policy not configured")

    allowed_ids = session.exec(
        select(DealerAllowedDiscount.discount_template_id).where(
            DealerAllowedDiscount.dealer_id == current_user.dealer_id
        )
    ).all()
    return DealerAllowedDiscountPolicyResponse(
        mode=policy.mode,
        allow_fixed_amount=policy.allow_fixed_amount,
        allow_percentage=policy.allow_percentage,
        max_discount_percentage=policy.max_discount_percentage,
        max_discount_amount=policy.max_discount_amount,
        allowed_discount_template_ids=list(allowed_ids),
    )


@router.get("/products", response_model=List[ProductResponse])
async def get_dealer_products(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dealer_user),
):
    _get_dealer_or_404(session, current_user.dealer_id)
    rows = session.exec(
        select(Product)
        .join(DealerProductAccess, DealerProductAccess.product_id == Product.id)
        .where(
            DealerProductAccess.dealer_id == current_user.dealer_id,
            Product.is_active == True,
        )
        .order_by(Product.name.asc())
    ).all()
    return list(rows)


@router.get("/quotes", response_model=QuoteListResponse)
async def get_dealer_quotes(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dealer_user),
):
    quotes = session.exec(
        select(Quote)
        .where(
            Quote.dealer_id == current_user.dealer_id,
            Quote.status.notin_([QuoteStatus.REJECTED, QuoteStatus.EXPIRED]),
        )
        .order_by(Quote.created_at.desc())
    ).all()
    items: List[QuoteResponse] = []
    for quote in quotes:
        quote_items = session.exec(
            select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
        ).all()
        items.append(build_quote_response(quote, list(quote_items), session))
    return QuoteListResponse(items=items, total=len(items), page=1, page_size=max(1, len(items)))


@router.post("/quotes", response_model=QuoteResponse)
async def create_dealer_quote(
    payload: DealerQuoteCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dealer_user),
):
    _get_dealer_or_404(session, current_user.dealer_id)

    if not payload.product_items:
        raise HTTPException(status_code=400, detail="At least one product is required")

    allowed_product_ids = set(
        session.exec(
            select(DealerProductAccess.product_id).where(
                DealerProductAccess.dealer_id == current_user.dealer_id
            )
        ).all()
    )
    if not allowed_product_ids:
        raise HTTPException(status_code=400, detail="No products are enabled for this dealer")

    policy = session.exec(
        select(DealerDiscountPolicy).where(DealerDiscountPolicy.dealer_id == current_user.dealer_id)
    ).first()
    if not policy:
        raise HTTPException(status_code=400, detail="Dealer discount policy not configured")

    allowed_discount_ids = set(
        session.exec(
            select(DealerAllowedDiscount.discount_template_id).where(
                DealerAllowedDiscount.dealer_id == current_user.dealer_id
            )
        ).all()
    )
    if any(template_id not in allowed_discount_ids for template_id in payload.discount_template_ids):
        raise HTTPException(status_code=403, detail="One or more discounts are not permitted")

    customer = Customer(
        customer_number=f"DEALER-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
        name=payload.customer_name.strip(),
        email=payload.customer_email,
        phone=payload.customer_phone,
        customer_since=datetime.utcnow(),
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)

    quote = Quote(
        customer_id=customer.id,
        quote_number=generate_quote_number(session),
        version=1,
        status=QuoteStatus.DRAFT,
        subtotal=Decimal("0"),
        discount_total=Decimal("0"),
        total_amount=Decimal("0"),
        deposit_amount=Decimal("0"),
        balance_amount=Decimal("0"),
        currency="GBP",
        valid_until=payload.valid_until,
        notes=payload.notes,
        created_by_id=current_user.id,
        dealer_id=current_user.dealer_id,
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)

    quote_items: List[QuoteItem] = []
    subtotal = Decimal("0")
    for idx, line in enumerate(payload.product_items):
        if line.product_id not in allowed_product_ids:
            raise HTTPException(status_code=403, detail="Product not available for this dealer")
        product = session.get(Product, line.product_id)
        if not product or not product.is_active:
            raise HTTPException(status_code=404, detail=f"Product {line.product_id} not found")

        quantity = Decimal(str(line.quantity))
        line_total = Decimal(str(product.base_price)) * quantity
        quote_item = QuoteItem(
            quote_id=quote.id,
            product_id=product.id,
            description=product.name,
            quantity=quantity,
            unit_price=Decimal(str(product.base_price)),
            line_total=line_total,
            discount_amount=Decimal("0"),
            final_line_total=line_total,
            sort_order=idx,
            is_custom=False,
        )
        session.add(quote_item)
        quote_items.append(quote_item)
        subtotal += line_total

        if line.selected_extra_ids:
            allowed_extras = set(
                session.exec(
                    select(ProductOptionalExtra.optional_extra_id).where(
                        ProductOptionalExtra.product_id == product.id
                    )
                ).all()
            )
            for extra_id in line.selected_extra_ids:
                if extra_id not in allowed_extras or extra_id not in allowed_product_ids:
                    raise HTTPException(status_code=403, detail="Optional extra not available")
                extra = session.get(Product, extra_id)
                if not extra or not extra.is_active:
                    raise HTTPException(status_code=404, detail=f"Extra {extra_id} not found")
                extra_total = Decimal(str(extra.base_price)) * quantity
                extra_item = QuoteItem(
                    quote_id=quote.id,
                    product_id=extra.id,
                    description=extra.name,
                    quantity=quantity,
                    unit_price=Decimal(str(extra.base_price)),
                    line_total=extra_total,
                    discount_amount=Decimal("0"),
                    final_line_total=extra_total,
                    sort_order=idx + 1000 + extra.id,
                    is_custom=False,
                )
                session.add(extra_item)
                quote_items.append(extra_item)
                subtotal += extra_total

    session.commit()
    quote_items = list(
        session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)).all()
    )

    quote.subtotal = subtotal
    quote.total_amount = subtotal
    total_inc_vat = subtotal * (Decimal("1") + VAT_RATE_DECIMAL)
    quote.deposit_amount = total_inc_vat * Decimal("0.5")
    quote.balance_amount = total_inc_vat - quote.deposit_amount

    for template_id in payload.discount_template_ids:
        template = session.exec(
            select(DiscountTemplate).where(
                DiscountTemplate.id == template_id,
                DiscountTemplate.is_active == True,
            )
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail=f"Discount template {template_id} not found")
        apply_discount_to_quote(quote, template, quote_items, session, current_user)

    quote.discounts = session.exec(select(QuoteDiscount).where(QuoteDiscount.quote_id == quote.id)).all()
    item_discount_total = sum(item.discount_amount for item in quote_items)
    quote.discount_total = item_discount_total + sum(
        d.discount_amount for d in quote.discounts if d.quote_item_id is None
    )
    quote.total_amount = max(Decimal("0"), quote.subtotal - quote.discount_total)
    total_inc_vat = quote.total_amount * (Decimal("1") + VAT_RATE_DECIMAL)
    if quote.deposit_amount > total_inc_vat:
        quote.deposit_amount = total_inc_vat
    quote.balance_amount = total_inc_vat - quote.deposit_amount
    quote.updated_at = datetime.utcnow()
    quote.revision_hash = _build_quote_revision_hash(quote, quote_items)

    session.add(quote)
    session.commit()
    session.refresh(quote)
    return build_quote_response(quote, quote_items, session)


@router.get("/quotes/{quote_id}", response_model=QuoteResponse)
async def get_dealer_quote(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dealer_user),
):
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    _require_dealer_quote_access(quote, current_user)
    quote_items = session.exec(
        select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
    ).all()
    return build_quote_response(quote, list(quote_items), session)


@router.get("/quotes/{quote_id}/pdf")
async def download_dealer_quote_pdf(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dealer_user),
):
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    _require_dealer_quote_access(quote, current_user)
    if not quote.customer_id:
        raise HTTPException(status_code=400, detail="Quote has no customer")
    customer = session.get(Customer, quote.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    quote_items = list(
        session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)).all()
    )
    revision_hash = quote.revision_hash or _build_quote_revision_hash(quote, quote_items)
    if quote.revision_hash != revision_hash:
        quote.revision_hash = revision_hash
        session.add(quote)
        session.commit()

    cache_key = f"{quote.id}:{revision_hash}:dealer:{current_user.dealer_id}"
    pdf_bytes, _ = generate_quote_pdf_cached(
        cache_key=cache_key,
        quote=quote,
        customer=customer,
        quote_items=quote_items,
        session=session,
        include_spec_sheets=getattr(quote, "include_spec_sheets", False),
    )
    filename = f"DealerQuote_{quote.quote_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
