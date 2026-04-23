import hashlib
from datetime import datetime
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select

from app.auth import require_dealer_user
from app.constants import VAT_RATE_DECIMAL
from app.database import get_session
from app.image_upload_service import upload_product_image
from app.delivery_install_service import compute_delivery_install_estimate
from app.models import (
    CompanySettings,
    Customer,
    Dealer,
    DealerAllowedDiscount,
    DealerDiscountPolicy,
    DiscountTemplate,
    Product,
    ProductOptionalExtra,
    Quote,
    QuoteDiscount,
    QuoteItem,
    QuoteItemLineType,
    QuoteStatus,
    User,
)
from app.quote_pdf_service import generate_quote_pdf_cached
from app.routers.quotes import apply_discount_to_quote, build_quote_response, generate_quote_number
from app.schemas import (
    DealerAllowedDiscountPolicyResponse,
    DealerDeliveryEstimateInclusion,
    DealerProfileResponse,
    DealerProfileUpdate,
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


def _dealer_quote_main_product_install_hours(session: Session, quote_id: int) -> float:
    """Sum installation hours x qty for main dealer lines only (excludes optional extras: sort_order >= 1000)."""
    items = session.exec(
        select(QuoteItem).where(QuoteItem.quote_id == quote_id).order_by(QuoteItem.sort_order)
    ).all()
    total = Decimal("0")
    for item in items:
        if item.sort_order >= 1000:
            continue
        if item.product_id is None:
            continue
        product = session.get(Product, item.product_id)
        if not product or product.is_extra:
            continue
        if product.installation_hours:
            total += item.quantity * product.installation_hours
    return float(total)


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


def _dealer_to_profile_response(dealer: Dealer) -> DealerProfileResponse:
    return DealerProfileResponse(
        id=dealer.id,
        name=dealer.name,
        company_name=dealer.company_name,
        contact_name=dealer.contact_name,
        email=dealer.email,
        phone=dealer.phone,
        address=dealer.address,
        vat_number=dealer.vat_number,
        registration_number=dealer.registration_number,
        website=dealer.website,
        logo_url=dealer.logo_url,
        is_active=dealer.is_active,
    )


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


@router.get("/profile", response_model=DealerProfileResponse)
async def get_dealer_profile(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dealer_user),
):
    dealer = _get_dealer_or_404(session, current_user.dealer_id)
    return _dealer_to_profile_response(dealer)


@router.put("/profile", response_model=DealerProfileResponse)
async def update_dealer_profile(
    payload: DealerProfileUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dealer_user),
):
    dealer = _get_dealer_or_404(session, current_user.dealer_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(dealer, field_name, value)
    dealer.updated_at = datetime.utcnow()
    session.add(dealer)
    session.commit()
    session.refresh(dealer)
    return _dealer_to_profile_response(dealer)


@router.post("/profile/logo", response_model=DealerProfileResponse)
async def upload_dealer_logo(
    logo: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dealer_user),
):
    dealer = _get_dealer_or_404(session, current_user.dealer_id)
    dealer.logo_url = await upload_product_image(logo)
    dealer.updated_at = datetime.utcnow()
    session.add(dealer)
    session.commit()
    session.refresh(dealer)
    return _dealer_to_profile_response(dealer)


@router.get("/products", response_model=List[ProductResponse])
async def get_dealer_products(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dealer_user),
):
    _get_dealer_or_404(session, current_user.dealer_id)
    rows = session.exec(
        select(Product)
        .where(
            Product.is_active == True,
            Product.allow_trade_dealer_sale == True,
            Product.is_extra == False,
        )
        .order_by(Product.name.asc())
    ).all()
    return [
        ProductResponse(**{**product.dict(), "is_production_synced": product.production_product_id is not None})
        for product in rows
    ]


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

    if payload.discount_template_ids:
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

    postcode = (payload.customer_postcode or "").strip() or None
    if payload.delivery_estimate_inclusion != DealerDeliveryEstimateInclusion.NONE and not postcode:
        raise HTTPException(
            status_code=400,
            detail="Customer postcode is required when including a delivery or delivery & installation line",
        )

    quote = Quote(
        customer_id=None,
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
        dealer_customer_name=payload.customer_name.strip(),
        dealer_customer_email=payload.customer_email,
        dealer_customer_phone=payload.customer_phone,
        dealer_customer_address=payload.customer_address,
        dealer_customer_postcode=postcode,
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)

    quote_items: List[QuoteItem] = []
    subtotal = Decimal("0")
    for idx, line in enumerate(payload.product_items):
        product = session.get(Product, line.product_id)
        if not product or not product.is_active:
            raise HTTPException(status_code=404, detail=f"Product {line.product_id} not found")
        if product.is_extra:
            raise HTTPException(
                status_code=403,
                detail="Optional extras cannot be added as a main line; add them via selected_extra_ids",
            )
        if not product.allow_trade_dealer_sale:
            raise HTTPException(status_code=403, detail="Product not available for trade dealer sale")

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
                if extra_id not in allowed_extras:
                    raise HTTPException(status_code=403, detail="Optional extra not available")
                extra = session.get(Product, extra_id)
                if not extra or not extra.is_active:
                    raise HTTPException(status_code=404, detail=f"Extra {extra_id} not found")
                if not extra.allow_trade_dealer_sale:
                    raise HTTPException(status_code=403, detail="Optional extra not available for trade dealer sale")
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

    if payload.delivery_estimate_inclusion != DealerDeliveryEstimateInclusion.NONE:
        install_hours = _dealer_quote_main_product_install_hours(session, quote.id)
        if payload.delivery_estimate_inclusion == DealerDeliveryEstimateInclusion.DELIVERY_AND_INSTALL:
            if install_hours <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Selected products have no installation hours; choose delivery only or add products with installation time",
                )
        delivery_only = payload.delivery_estimate_inclusion == DealerDeliveryEstimateInclusion.DELIVERY_ONLY
        inst_hours = 0.0 if delivery_only else install_hours

        settings = session.exec(select(CompanySettings).limit(1)).first()
        if not settings:
            raise HTTPException(
                status_code=400,
                detail="Configure factory postcode and installation & travel settings in Company settings.",
            )
        factory_postcode = (settings.postcode or "").strip()
        if not factory_postcode:
            raise HTTPException(
                status_code=400,
                detail="Configure factory postcode and installation & travel settings in Company settings.",
            )
        try:
            est = compute_delivery_install_estimate(
                factory_postcode=factory_postcode,
                customer_postcode=postcode,
                installation_hours=inst_hours,
                distance_before_overnight_miles=settings.distance_before_overnight_miles,
                cost_per_mile=settings.cost_per_mile,
                hourly_install_rate=settings.hourly_install_rate,
                hotel_allowance_per_night=settings.hotel_allowance_per_night,
                meal_allowance_per_day=settings.meal_allowance_per_day,
                average_speed_mph=settings.average_speed_mph,
                install_quote_margin_pct=settings.install_quote_margin_pct,
                delivery_only=delivery_only,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if est.cost_total is None or est.cost_total <= 0:
            raise HTTPException(
                status_code=400,
                detail="Could not compute a delivery cost for this postcode; check company rates and postcode.",
            )

        max_sort = max((i.sort_order for i in quote_items), default=-1)
        desc = "Delivery only" if delivery_only else "Delivery & Installation"
        cost = est.cost_total.quantize(Decimal("0.01"))
        delivery_item = QuoteItem(
            quote_id=quote.id,
            product_id=None,
            description=desc,
            quantity=Decimal("1"),
            unit_price=cost,
            line_total=cost,
            discount_amount=Decimal("0"),
            final_line_total=cost,
            sort_order=max_sort + 1,
            is_custom=True,
            line_type=QuoteItemLineType.DELIVERY,
        )
        session.add(delivery_item)
        session.commit()
        quote_items = list(
            session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)).all()
        )
        subtotal = sum((i.line_total for i in quote_items), start=Decimal("0"))

    quote.subtotal = subtotal
    quote.total_amount = subtotal

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
    commission_pct = Decimal(str(current_user.dealer_commission_pct or 10))
    quote.deposit_amount = (total_inc_vat * commission_pct / Decimal(100)).quantize(Decimal("0.01"))
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
    quote_items = list(
        session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)).all()
    )
    dealer = _get_dealer_or_404(session, current_user.dealer_id)
    customer_number = f"DEALER-{quote.id}"
    customer = Customer(
        customer_number=customer_number,
        name=quote.dealer_customer_name or "Customer",
        email=quote.dealer_customer_email,
        phone=quote.dealer_customer_phone,
        address_line1=quote.dealer_customer_address,
        postcode=getattr(quote, "dealer_customer_postcode", None),
    )
    revision_hash = quote.revision_hash or _build_quote_revision_hash(quote, quote_items)
    if quote.revision_hash != revision_hash:
        quote.revision_hash = revision_hash
        session.add(quote)
        session.commit()

    dealer_profile_hash = hashlib.sha256(
        "|".join(
            [
                str(dealer.updated_at.isoformat() if dealer.updated_at else ""),
                str(dealer.company_name or ""),
                str(dealer.contact_name or ""),
                str(dealer.email or ""),
                str(dealer.phone or ""),
                str(dealer.address or ""),
                str(dealer.vat_number or ""),
                str(dealer.registration_number or ""),
                str(dealer.website or ""),
                str(dealer.logo_url or ""),
            ]
        ).encode("utf-8")
    ).hexdigest()
    cache_key = f"{quote.id}:{revision_hash}:dealer:{current_user.dealer_id}:profile:{dealer_profile_hash}"
    pdf_bytes, _ = generate_quote_pdf_cached(
        cache_key=cache_key,
        quote=quote,
        customer=customer,
        quote_items=quote_items,
        session=session,
        include_spec_sheets=getattr(quote, "include_spec_sheets", False),
        dealer_profile={
            "company_name": dealer.company_name or dealer.name,
            "contact_name": dealer.contact_name or "",
            "email": dealer.email or "",
            "phone": dealer.phone or "",
            "address": dealer.address or "",
            "vat_number": dealer.vat_number or "",
            "registration_number": dealer.registration_number or "",
            "website": dealer.website or "",
        },
        trader_logo_url=dealer.logo_url,
    )
    filename = f"DealerQuote_{quote.quote_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
