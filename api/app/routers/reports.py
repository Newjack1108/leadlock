"""
Sales reports API - JSON and PDF endpoints.
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlmodel import Session, select, func
from app.database import get_session
from app.auth import get_current_user
from app.models import (
    Lead, LeadStatus, Quote, QuoteStatus,
    User, CompanySettings,
    OpportunityStage,
)
from app.schemas import (
    PipelineValueReport, PipelineValueStageItem,
    SourcePerformanceReport, SourcePerformanceItem,
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

    start_of_week = start - timedelta(days=start.weekday()) if hasattr(start, "weekday") else start
    week_label = f"{start.strftime('%d %b')} - {end.strftime('%d %b %Y')}"

    return WeeklyPipelineSummaryReport(
        week_label=week_label,
        generated_at=datetime.utcnow(),
        new_count=new_count,
        quoted_count=quoted_count,
        won_count=won_count,
        lost_count=lost_count,
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
