"""
Sales reports API - JSON and PDF endpoints.
"""
import csv
import io
from collections import defaultdict
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlmodel import Session, select, func
from app.database import get_session
from app.auth import get_current_user
from app.models import (
    Lead, LeadStatus, LeadSource, LeadType,
    Quote, QuoteStatus, Order, OrderItem, Product,
    User, CompanySettings, FacebookAdvertProfile,
    OpportunityStage,
)
from app.schemas import (
    PipelineValueReport, PipelineValueStageItem,
    SourcePerformanceReport, SourcePerformanceItem,
    FacebookLeadConversionReport, FacebookLeadConversionSummary,
    FacebookLeadConversionBreakdownItem, FacebookLeadConversionRow,
    CloserPerformanceReport, CloserPerformanceItem,
    QuoteEngagementReport,
    WeeklyPipelineSummaryReport,
)
from app.report_pdf_service import (
    generate_pipeline_value_pdf,
    generate_source_performance_pdf,
    generate_closer_performance_pdf,
    generate_quote_engagement_pdf,
    generate_weekly_summary_pdf,
)
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

router = APIRouter(prefix="/api/reports", tags=["reports"])
VALID_REPORT_PERIODS = ("week", "month", "quarter", "year")
UNKNOWN_ADVERT_PROFILE_NAME = "Unknown / Not tagged"
UNKNOWN_PRODUCT_TYPE_NAME = "Unknown / uncategorised"


def get_date_range_for_period(period: str) -> tuple[datetime, datetime]:
    """Return (start, end) datetime for the given period (week, month, quarter, year)."""
    now = datetime.utcnow()
    end = now
    if period == "week":
        start_of_week = now - timedelta(days=now.weekday())
        start = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "quarter":
        quarter_start_month = ((now.month - 1) // 3) * 3 + 1
        start = now.replace(month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = datetime(1970, 1, 1)
    return start, end


def _get_company_name(session: Session) -> str:
    """Get company name from settings for report header."""
    stmt = select(CompanySettings).limit(1)
    cs = session.exec(stmt).first()
    return (cs.trading_name or cs.company_name or "LeadLock") if cs else "LeadLock"


def _normalise_period(period: Optional[str]) -> Optional[str]:
    if period and period.lower() in VALID_REPORT_PERIODS:
        return period.lower()
    return None


def _enum_value(value, default: str = "Unknown") -> str:
    if value is None:
        return default
    return value.value if hasattr(value, "value") else str(value)


def _decimal_or_zero(value: Optional[Decimal]) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _average_days_to_convert(rows: list[FacebookLeadConversionRow]) -> float:
    values = [row.days_to_convert for row in rows if row.days_to_convert is not None]
    return round(sum(values) / len(values), 1) if values else 0.0


def _derive_product_type(
    lead: Lead,
    orders: list[Order],
    items_by_order_id: dict[int, list[OrderItem]],
    products_by_id: dict[int, Product],
) -> str:
    product_categories: set[str] = set()
    saw_custom_line = False
    for order in orders:
        if order.id is None:
            continue
        for item in items_by_order_id.get(order.id, []):
            if item.product_id:
                product = products_by_id.get(item.product_id)
                if product and product.category:
                    product_categories.add(_enum_value(product.category))
            elif item.description:
                saw_custom_line = True

    if len(product_categories) == 1:
        return next(iter(product_categories))
    if len(product_categories) > 1:
        return "Mixed"

    lead_type = _enum_value(lead.lead_type, "")
    if lead_type and lead_type != LeadType.UNKNOWN.value:
        return lead_type

    if lead.product_interest and lead.product_interest.strip():
        return lead.product_interest.strip()

    if saw_custom_line:
        return "Custom / uncategorised"

    return UNKNOWN_PRODUCT_TYPE_NAME


def _build_facebook_lead_conversion_breakdown(
    rows: list[FacebookLeadConversionRow],
    attribute_name: str,
) -> list[FacebookLeadConversionBreakdownItem]:
    grouped_rows: dict[str, list[FacebookLeadConversionRow]] = defaultdict(list)
    for row in rows:
        grouped_rows[getattr(row, attribute_name)].append(row)

    items: list[FacebookLeadConversionBreakdownItem] = []
    for name, group_rows in grouped_rows.items():
        leads_count = len(group_rows)
        converted_leads = sum(1 for row in group_rows if row.converted)
        total_orders = sum(row.order_count for row in group_rows)
        total_revenue = sum((_decimal_or_zero(row.order_amount) for row in group_rows), Decimal("0"))
        conversion_rate = round((converted_leads / leads_count * 100), 1) if leads_count else 0.0
        average_order_value = (total_revenue / total_orders) if total_orders else Decimal("0")
        items.append(FacebookLeadConversionBreakdownItem(
            name=name,
            leads_count=leads_count,
            converted_leads=converted_leads,
            conversion_rate=conversion_rate,
            total_orders=total_orders,
            total_revenue=total_revenue,
            average_order_value=average_order_value,
            average_days_to_convert=_average_days_to_convert(group_rows),
        ))

    items.sort(key=lambda item: (item.leads_count, item.total_revenue), reverse=True)
    return items


def _build_facebook_lead_conversion_report(
    session: Session,
    period: Optional[str],
) -> FacebookLeadConversionReport:
    period_key = _normalise_period(period)
    lead_stmt = select(Lead).where(Lead.lead_source == LeadSource.FACEBOOK)
    if period_key:
        start, end = get_date_range_for_period(period_key)
        lead_stmt = lead_stmt.where(Lead.created_at >= start).where(Lead.created_at <= end)

    leads = list(session.exec(lead_stmt.order_by(Lead.created_at.desc())).all())
    if not leads:
        return FacebookLeadConversionReport(
            period=period_key,
            generated_at=datetime.utcnow(),
            summary=FacebookLeadConversionSummary(
                total_facebook_leads=0,
                converted_leads=0,
                conversion_rate=0.0,
                total_orders=0,
                total_order_revenue=Decimal("0"),
                average_order_value=Decimal("0"),
                average_days_to_convert=0.0,
                unknown_advert_profile_leads=0,
                won_without_order_leads=0,
            ),
            advert_breakdown=[],
            product_type_breakdown=[],
            rows=[],
        )

    lead_ids = [lead.id for lead in leads if lead.id is not None]
    quotes = list(session.exec(select(Quote).where(Quote.lead_id.in_(lead_ids))).all()) if lead_ids else []
    quote_by_id = {quote.id: quote for quote in quotes if quote.id is not None}

    quotes_by_lead_id: dict[int, list[Quote]] = defaultdict(list)
    for quote in quotes:
        if quote.lead_id is not None:
            quotes_by_lead_id[quote.lead_id].append(quote)

    quote_ids = [quote.id for quote in quotes if quote.id is not None]
    orders = list(session.exec(select(Order).where(Order.quote_id.in_(quote_ids))).all()) if quote_ids else []

    orders_by_quote_id: dict[int, list[Order]] = defaultdict(list)
    for order in orders:
        orders_by_quote_id[order.quote_id].append(order)

    order_ids = [order.id for order in orders if order.id is not None]
    order_items = list(session.exec(select(OrderItem).where(OrderItem.order_id.in_(order_ids))).all()) if order_ids else []
    items_by_order_id: dict[int, list[OrderItem]] = defaultdict(list)
    for item in order_items:
        items_by_order_id[item.order_id].append(item)

    product_ids = sorted({item.product_id for item in order_items if item.product_id is not None})
    products = list(session.exec(select(Product).where(Product.id.in_(product_ids))).all()) if product_ids else []
    products_by_id = {product.id: product for product in products if product.id is not None}

    advert_profile_ids = sorted({lead.facebook_advert_profile_id for lead in leads if lead.facebook_advert_profile_id is not None})
    advert_profiles = (
        list(session.exec(select(FacebookAdvertProfile).where(FacebookAdvertProfile.id.in_(advert_profile_ids))).all())
        if advert_profile_ids else []
    )
    advert_profiles_by_id = {profile.id: profile for profile in advert_profiles if profile.id is not None}

    rows: list[FacebookLeadConversionRow] = []
    for lead in leads:
        if lead.id is None:
            continue

        lead_quotes = sorted(
            quotes_by_lead_id.get(lead.id, []),
            key=lambda quote: (quote.created_at, quote.id or 0),
        )

        lead_orders: list[Order] = []
        for quote in lead_quotes:
            if quote.id is not None:
                lead_orders.extend(sorted(
                    orders_by_quote_id.get(quote.id, []),
                    key=lambda order: (order.created_at, order.id or 0),
                ))

        primary_order = lead_orders[0] if lead_orders else None
        latest_quote = lead_quotes[-1] if lead_quotes else None
        primary_quote = quote_by_id.get(primary_order.quote_id) if primary_order else latest_quote
        order_total = sum((_decimal_or_zero(order.total_amount) for order in lead_orders), Decimal("0"))
        days_to_convert = None
        if primary_order:
            days_to_convert = round((primary_order.created_at - lead.created_at).total_seconds() / 86400, 1)

        advert_profile_name = UNKNOWN_ADVERT_PROFILE_NAME
        if lead.facebook_advert_profile_id is not None:
            advert_profile = advert_profiles_by_id.get(lead.facebook_advert_profile_id)
            if advert_profile:
                advert_profile_name = advert_profile.name

        rows.append(FacebookLeadConversionRow(
            lead_id=lead.id,
            lead_created_at=lead.created_at,
            lead_name=lead.name,
            email=lead.email,
            phone=lead.phone,
            lead_status=_enum_value(lead.status),
            lead_source=_enum_value(lead.lead_source),
            advert_profile_name=advert_profile_name,
            product_interest=lead.product_interest,
            lead_type=_enum_value(lead.lead_type),
            product_type=_derive_product_type(lead, lead_orders, items_by_order_id, products_by_id),
            quote_number=primary_quote.quote_number if primary_quote else None,
            order_number=primary_order.order_number if primary_order else None,
            order_created_at=primary_order.created_at if primary_order else None,
            order_amount=order_total if lead_orders else None,
            days_to_convert=days_to_convert,
            converted=bool(lead_orders),
            order_count=len(lead_orders),
            won_without_order=(lead.status == LeadStatus.WON and not lead_orders),
        ))

    total_facebook_leads = len(rows)
    converted_leads = sum(1 for row in rows if row.converted)
    total_orders = sum(row.order_count for row in rows)
    total_order_revenue = sum((_decimal_or_zero(row.order_amount) for row in rows), Decimal("0"))
    conversion_rate = round((converted_leads / total_facebook_leads * 100), 1) if total_facebook_leads else 0.0
    average_order_value = (total_order_revenue / total_orders) if total_orders else Decimal("0")
    unknown_advert_profile_leads = sum(1 for row in rows if row.advert_profile_name == UNKNOWN_ADVERT_PROFILE_NAME)
    won_without_order_leads = sum(1 for row in rows if row.won_without_order)

    return FacebookLeadConversionReport(
        period=period_key,
        generated_at=datetime.utcnow(),
        summary=FacebookLeadConversionSummary(
            total_facebook_leads=total_facebook_leads,
            converted_leads=converted_leads,
            conversion_rate=conversion_rate,
            total_orders=total_orders,
            total_order_revenue=total_order_revenue,
            average_order_value=average_order_value,
            average_days_to_convert=_average_days_to_convert(rows),
            unknown_advert_profile_leads=unknown_advert_profile_leads,
            won_without_order_leads=won_without_order_leads,
        ),
        advert_breakdown=_build_facebook_lead_conversion_breakdown(rows, "advert_profile_name"),
        product_type_breakdown=_build_facebook_lead_conversion_breakdown(rows, "product_type"),
        rows=rows,
    )


# --- Pipeline Value Report ---

@router.get("/pipeline-value", response_model=PipelineValueReport)
async def get_pipeline_value_report(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
    period: Optional[str] = Query(None, description="week, month, quarter, year. Omit for all-time."),
):
    """Weighted pipeline by opportunity stage and close probability."""
    quote_filter = Quote.status.in_([
        QuoteStatus.SENT, QuoteStatus.VIEWED, QuoteStatus.ACCEPTED,
        QuoteStatus.REJECTED, QuoteStatus.EXPIRED,
    ])
    if period and period.lower() in ("week", "month", "quarter", "year"):
        start, end = get_date_range_for_period(period.lower())
        quote_filter = quote_filter & (Quote.sent_at >= start) & (Quote.sent_at <= end)

    # Weighted value = total_amount * (close_probability/100), treating NULL prob as 0
    weighted_expr = Quote.total_amount * (func.coalesce(Quote.close_probability, 0) / 100)
    stmt = (
        select(
            Quote.opportunity_stage,
            func.count(Quote.id).label("cnt"),
            func.coalesce(func.sum(Quote.total_amount), 0).label("total_val"),
            func.coalesce(func.sum(weighted_expr), 0).label("weighted_val"),
        )
        .where(quote_filter)
        .where(Quote.opportunity_stage.isnot(None))
        .group_by(Quote.opportunity_stage)
    )
    rows = session.exec(stmt).all()

    stages = []
    total_value = Decimal("0")
    total_weighted = Decimal("0")
    stage_order = [
        OpportunityStage.DISCOVERY, OpportunityStage.CONCEPT, OpportunityStage.QUOTE_SENT,
        OpportunityStage.FOLLOW_UP, OpportunityStage.DECISION_PENDING,
        OpportunityStage.WON, OpportunityStage.LOST,
    ]
    seen_stages = {}
    for r in rows:
        seen_stages[r[0]] = (r[1], r[2] or Decimal("0"), r[3] or Decimal("0"))

    for stage in stage_order:
        if stage in seen_stages:
            cnt, tv, wv = seen_stages[stage]
            stages.append(PipelineValueStageItem(
                stage=stage.value if hasattr(stage, "value") else str(stage),
                count=cnt,
                total_value=tv,
                weighted_value=wv,
            ))
            total_value += tv
            total_weighted += wv

    return PipelineValueReport(
        period=period,
        generated_at=datetime.utcnow(),
        stages=stages,
        total_value=total_value,
        total_weighted_value=total_weighted,
    )


@router.get("/pipeline-value/pdf")
async def get_pipeline_value_pdf(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
    period: Optional[str] = Query(None),
):
    """Download Pipeline Value Report as PDF."""
    report = await get_pipeline_value_report(session=session, current_user=current_user, period=period)
    data = {
        "period": report.period,
        "stages": [s.model_dump() for s in report.stages],
        "total_value": float(report.total_value),
        "total_weighted_value": float(report.total_weighted_value),
    }
    company_name = _get_company_name(session)
    buffer = generate_pipeline_value_pdf(data, company_name)
    pdf_content = buffer.read()
    fn = f"Pipeline_Value_Report_{datetime.utcnow().strftime('%Y-%m-%d')}.pdf"
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


# --- Source Performance Report ---

@router.get("/source-performance", response_model=SourcePerformanceReport)
async def get_source_performance_report(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
    period: Optional[str] = Query(None),
):
    """Leads and conversion by lead_source."""
    date_filter = None
    if period and period.lower() in ("week", "month", "quarter", "year"):
        start, end = get_date_range_for_period(period.lower())
        date_filter = (Lead.created_at >= start) & (Lead.created_at <= end)

    stmt = (
        select(Lead.lead_source, func.count(Lead.id).label("cnt"))
        .group_by(Lead.lead_source)
    )
    if date_filter:
        stmt = stmt.where(date_filter)
    rows = session.exec(stmt).all()

    sources = []
    total_leads = 0
    for row in rows:
        source_val = row[0]
        source_str = source_val.value if hasattr(source_val, "value") else (str(source_val) if source_val else "Unknown")
        cnt = row[1]

        quoted_stmt = select(func.count(Lead.id)).where(Lead.lead_source == source_val).where(
            Lead.status.in_([LeadStatus.QUOTED, LeadStatus.WON])
        )
        if date_filter:
            quoted_stmt = quoted_stmt.where(date_filter)
        quoted_count = session.exec(quoted_stmt).one()

        won_stmt = select(func.count(Lead.id)).where(Lead.lead_source == source_val).where(Lead.status == LeadStatus.WON)
        if date_filter:
            won_stmt = won_stmt.where(date_filter)
        won_count = session.exec(won_stmt).one()

        conversion = (won_count / cnt * 100) if cnt > 0 else 0.0
        sources.append(SourcePerformanceItem(
            source=source_str,
            leads_count=cnt,
            quoted_count=quoted_count,
            won_count=won_count,
            conversion_rate=round(conversion, 1),
        ))
        total_leads += cnt

    sources.sort(key=lambda x: x.leads_count, reverse=True)
    return SourcePerformanceReport(
        period=period,
        generated_at=datetime.utcnow(),
        sources=sources,
        total_leads=total_leads,
    )


@router.get("/source-performance/pdf")
async def get_source_performance_pdf(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
    period: Optional[str] = Query(None),
):
    """Download Source Performance Report as PDF."""
    report = await get_source_performance_report(session=session, current_user=current_user, period=period)
    data = {
        "period": report.period,
        "sources": [s.model_dump() for s in report.sources],
        "total_leads": report.total_leads,
    }
    company_name = _get_company_name(session)
    buffer = generate_source_performance_pdf(data, company_name)
    pdf_content = buffer.read()
    fn = f"Source_Performance_Report_{datetime.utcnow().strftime('%Y-%m-%d')}.pdf"
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


# --- Facebook Lead Conversion Report ---

@router.get("/facebook-lead-conversion", response_model=FacebookLeadConversionReport)
async def get_facebook_lead_conversion_report(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
    period: Optional[str] = Query(None),
):
    """Lead-to-order conversion and revenue for Facebook leads."""
    return _build_facebook_lead_conversion_report(session, period)


@router.get("/facebook-lead-conversion.csv")
async def download_facebook_lead_conversion_report_csv(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
    period: Optional[str] = Query(None),
):
    """Download Facebook lead-to-order conversion report as CSV."""
    report = _build_facebook_lead_conversion_report(session, period)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "Lead Date",
        "Lead Name",
        "Email",
        "Phone",
        "Lead Status",
        "Lead Source",
        "Advert Profile",
        "Product Interest",
        "Lead Type",
        "Product Type",
        "Quote Number",
        "Order Number",
        "Order Date",
        "Order Amount",
        "Days To Convert",
        "Converted",
        "Order Count",
        "Won Without Order",
    ])
    for row in report.rows:
        writer.writerow([
            row.lead_created_at.isoformat(),
            row.lead_name,
            row.email or "",
            row.phone or "",
            row.lead_status,
            row.lead_source,
            row.advert_profile_name,
            row.product_interest or "",
            row.lead_type,
            row.product_type,
            row.quote_number or "",
            row.order_number or "",
            row.order_created_at.isoformat() if row.order_created_at else "",
            f"{row.order_amount:.2f}" if row.order_amount is not None else "",
            f"{row.days_to_convert:.1f}" if row.days_to_convert is not None else "",
            "Yes" if row.converted else "No",
            row.order_count,
            "Yes" if row.won_without_order else "No",
        ])

    filename = f"Facebook_Lead_To_Order_Report_{datetime.utcnow().strftime('%Y-%m-%d')}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Closer Performance Report ---

@router.get("/closer-performance", response_model=CloserPerformanceReport)
async def get_closer_performance_report(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Wins and revenue by salesperson."""
    users = list(session.exec(select(User)).all())

    closers = []
    for user in users:
        leads_assigned = session.exec(
            select(func.count(Lead.id)).where(Lead.assigned_to_id == user.id)
        ).one()

        won_count = session.exec(
            select(func.count(Lead.id)).where(
                Lead.assigned_to_id == user.id,
                Lead.status == LeadStatus.WON,
            )
        ).one()

        revenue_stmt = (
            select(func.coalesce(func.sum(Quote.total_amount), 0))
            .where(Quote.status == QuoteStatus.ACCEPTED)
            .where((Quote.owner_id == user.id) | ((Quote.owner_id.is_(None)) & (Quote.created_by_id == user.id)))
        )
        total_revenue = session.exec(revenue_stmt).one() or Decimal("0")

        if leads_assigned > 0 or won_count > 0 or total_revenue > 0:
            closers.append(CloserPerformanceItem(
                user_id=user.id,
                full_name=user.full_name,
                leads_assigned=leads_assigned,
                won_count=won_count,
                total_revenue=total_revenue,
            ))

    closers.sort(key=lambda x: x.total_revenue, reverse=True)
    return CloserPerformanceReport(
        generated_at=datetime.utcnow(),
        closers=closers,
    )


@router.get("/closer-performance/pdf")
async def get_closer_performance_pdf(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Download Closer Performance Report as PDF."""
    report = await get_closer_performance_report(session=session, current_user=current_user)
    data = {
        "closers": [c.model_dump() for c in report.closers],
    }
    for c in data["closers"]:
        c["total_revenue"] = float(c["total_revenue"])
    company_name = _get_company_name(session)
    buffer = generate_closer_performance_pdf(data, company_name)
    pdf_content = buffer.read()
    fn = f"Closer_Performance_Report_{datetime.utcnow().strftime('%Y-%m-%d')}.pdf"
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


# --- Quote Engagement Report ---

@router.get("/quote-engagement", response_model=QuoteEngagementReport)
async def get_quote_engagement_report(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
    period: Optional[str] = Query(None),
):
    """Sent vs viewed vs no reply."""
    quote_filter = Quote.status.in_([
        QuoteStatus.SENT, QuoteStatus.VIEWED, QuoteStatus.ACCEPTED,
        QuoteStatus.REJECTED, QuoteStatus.EXPIRED,
    ])
    if period and period.lower() in ("week", "month", "quarter", "year"):
        start, end = get_date_range_for_period(period.lower())
        quote_filter = quote_filter & (Quote.sent_at >= start) & (Quote.sent_at <= end)

    sent_count = session.exec(select(func.count(Quote.id)).where(quote_filter)).one()

    viewed_count = session.exec(
        select(func.count(Quote.id)).where(quote_filter, Quote.viewed_at.isnot(None))
    ).one()

    not_opened_count = session.exec(
        select(func.count(Quote.id)).where(quote_filter, Quote.viewed_at.is_(None))
    ).one()

    viewed_no_reply_count = session.exec(
        select(func.count(Quote.id)).where(
            quote_filter,
            Quote.viewed_at.isnot(None),
            Quote.status.notin_([QuoteStatus.ACCEPTED, QuoteStatus.REJECTED]),
        )
    ).one()

    accepted_count = session.exec(
        select(func.count(Quote.id)).where(quote_filter, Quote.status == QuoteStatus.ACCEPTED)
    ).one()

    rejected_count = session.exec(
        select(func.count(Quote.id)).where(quote_filter, Quote.status == QuoteStatus.REJECTED)
    ).one()

    return QuoteEngagementReport(
        period=period,
        generated_at=datetime.utcnow(),
        sent_count=sent_count,
        viewed_count=viewed_count,
        not_opened_count=not_opened_count,
        viewed_no_reply_count=viewed_no_reply_count,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
    )


@router.get("/quote-engagement/pdf")
async def get_quote_engagement_pdf(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
    period: Optional[str] = Query(None),
):
    """Download Quote Engagement Report as PDF."""
    report = await get_quote_engagement_report(session=session, current_user=current_user, period=period)
    data = report.model_dump()
    company_name = _get_company_name(session)
    buffer = generate_quote_engagement_pdf(data, company_name)
    pdf_content = buffer.read()
    fn = f"Quote_Engagement_Report_{datetime.utcnow().strftime('%Y-%m-%d')}.pdf"
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


# --- Weekly Pipeline Summary Report ---

@router.get("/weekly-summary", response_model=WeeklyPipelineSummaryReport)
async def get_weekly_summary_report(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """New leads, quoted, won, lost for the current week."""
    start, end = get_date_range_for_period("week")
    date_filter = (Lead.created_at >= start) & (Lead.created_at <= end)

    new_count = session.exec(
        select(func.count(Lead.id)).where(date_filter, Lead.status == LeadStatus.NEW)
    ).one()

    quoted_count = session.exec(
        select(func.count(Lead.id)).where(date_filter, Lead.status == LeadStatus.QUOTED)
    ).one()

    won_count = session.exec(
        select(func.count(Lead.id)).where(date_filter, Lead.status == LeadStatus.WON)
    ).one()

    lost_count = session.exec(
        select(func.count(Lead.id)).where(date_filter, Lead.status == LeadStatus.LOST)
    ).one()

    closed_count = session.exec(
        select(func.count(Lead.id)).where(date_filter, Lead.status == LeadStatus.CLOSED)
    ).one()

    start_of_week = start - timedelta(days=start.weekday()) if hasattr(start, "weekday") else start
    week_label = f"{start.strftime('%d %b')} - {end.strftime('%d %b %Y')}"

    return WeeklyPipelineSummaryReport(
        week_label=week_label,
        generated_at=datetime.utcnow(),
        new_count=new_count,
        quoted_count=quoted_count,
        won_count=won_count,
        lost_count=lost_count,
        closed_count=closed_count,
        start_date=start,
        end_date=end,
    )


@router.get("/weekly-summary/pdf")
async def get_weekly_summary_pdf(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Download Weekly Pipeline Summary Report as PDF."""
    report = await get_weekly_summary_report(session=session, current_user=current_user)
    data = report.model_dump()
    data["start_date"] = report.start_date.isoformat() if report.start_date else ""
    data["end_date"] = report.end_date.isoformat() if report.end_date else ""
    company_name = _get_company_name(session)
    buffer = generate_weekly_summary_pdf(data, company_name)
    pdf_content = buffer.read()
    fn = f"Weekly_Pipeline_Summary_{datetime.utcnow().strftime('%Y-%m-%d')}.pdf"
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )
