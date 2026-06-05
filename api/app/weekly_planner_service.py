from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import httpx
from jinja2 import Template as JinjaTemplate
from sqlmodel import Session, and_, desc, func, select

from app.customer_outreach_service import _is_within_outreach_quiet_hours
from app.email_service import _html_to_plain, build_activity_email_notes, is_email_configured, send_email
from app.models import (
    Activity,
    ActivityType,
    CompanySettings,
    Customer,
    Email,
    EmailDirection,
    Lead,
    MessengerDirection,
    MessengerMessage,
    Order,
    Quote,
    QuoteStatus,
    ReminderPriority,
    ReminderRule,
    SmsDirection,
    SmsMessage,
    SuggestedAction,
    User,
    WeeklyPlanItem,
    WeeklyPlanItemStatus,
    WeeklyPlanRun,
    WeeklyPlanScope,
    WeeklyPlanTemplate,
)
from app.reminder_service import (
    calculate_days_stale,
    detect_stale_leads,
    detect_stale_opportunities,
    detect_stale_quotes,
    latest_quotes_per_customer,
)
from app.sms_service import normalize_phone, send_sms
from app.system_user_service import get_system_user_id

POSITIVE_BUY_SIGNALS = (
    "ready to order",
    "let's proceed",
    "lets proceed",
    "happy to go ahead",
    "go ahead",
    "book it in",
    "pay deposit",
    "accept quote",
    "looks good",
    "sounds good",
)

NEGATIVE_BUY_SIGNALS = (
    "too expensive",
    "too much",
    "can't afford",
    "cannot afford",
    "hold off",
    "not now",
    "later in the year",
    "next year",
    "shopping around",
    "using someone else",
    "gone with another",
)


def _extract_text_from_responses_api(data: dict) -> str:
    direct = (data.get("output_text") or "").strip()
    if direct:
        return direct
    out = data.get("output")
    if not isinstance(out, list):
        return ""
    parts: list[str] = []
    for item in out:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            continue
        for block in item.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") not in ("output_text", "text", None):
                continue
            txt = (block.get("text") or "").strip()
            if txt:
                parts.append(txt)
    return "\n".join(parts).strip()


def _text_signal_counts(texts: List[str]) -> Tuple[int, int]:
    positive = 0
    negative = 0
    for raw in texts:
        t = raw.lower()
        if any(sig in t for sig in POSITIVE_BUY_SIGNALS):
            positive += 1
        if any(sig in t for sig in NEGATIVE_BUY_SIGNALS):
            negative += 1
    return positive, negative


def _collect_customer_recent_text(session: Session, customer_id: int) -> List[str]:
    texts: List[str] = []
    inbound_emails = session.exec(
        select(Email)
        .where(Email.customer_id == customer_id, Email.direction == EmailDirection.RECEIVED)
        .order_by(desc(Email.received_at), desc(Email.created_at))
        .limit(5)
    ).all()
    for email in inbound_emails:
        val = (email.body_text or email.body_html or "").strip()
        if val:
            texts.append(val[:500])

    inbound_sms = session.exec(
        select(SmsMessage)
        .where(SmsMessage.customer_id == customer_id, SmsMessage.direction == SmsDirection.RECEIVED)
        .order_by(desc(SmsMessage.received_at), desc(SmsMessage.created_at))
        .limit(5)
    ).all()
    for sms in inbound_sms:
        val = (sms.body or "").strip()
        if val:
            texts.append(val[:300])

    inbound_messenger = session.exec(
        select(MessengerMessage)
        .where(
            MessengerMessage.customer_id == customer_id,
            MessengerMessage.direction == MessengerDirection.RECEIVED,
        )
        .order_by(desc(MessengerMessage.received_at), desc(MessengerMessage.created_at))
        .limit(4)
    ).all()
    for message in inbound_messenger:
        val = (message.body or "").strip()
        if val:
            texts.append(val[:300])
    return texts


def _heuristic_order_likelihood(
    *,
    quote: Optional[Quote],
    days_stale: int,
    recent_texts: List[str],
) -> Tuple[Decimal, Decimal, List[str]]:
    score = Decimal("50")
    reasons: List[str] = []
    if quote:
        if quote.close_probability is not None:
            score += Decimal(quote.close_probability) * Decimal("0.2")
            reasons.append("close_probability_signal")
        if quote.total_amount is not None and Decimal(quote.total_amount) >= Decimal("8000"):
            score += Decimal("4")
            reasons.append("higher_value_deal")
        if quote.viewed_at is not None:
            score += Decimal("6")
            reasons.append("quote_viewed")
        if quote.sent_at is not None and quote.viewed_at is None and days_stale >= 5:
            score -= Decimal("8")
            reasons.append("sent_not_opened")

    pos, neg = _text_signal_counts(recent_texts)
    if pos:
        score += Decimal(min(20, pos * 5))
        reasons.append("positive_buy_intent")
    if neg:
        score -= Decimal(min(25, neg * 6))
        reasons.append("objection_or_delay_language")

    if days_stale >= 14:
        score -= Decimal("12")
        reasons.append("high_staleness_decay")
    elif days_stale >= 7:
        score -= Decimal("5")
        reasons.append("moderate_staleness_decay")

    score = max(Decimal("1"), min(Decimal("99"), score))
    confidence = Decimal("0.65")
    return score, confidence, reasons


def _fallback_narrative(
    *,
    customer_name: str,
    action: SuggestedAction,
    channel: str,
    likelihood_score: Decimal,
    reasons: List[str],
) -> Tuple[str, List[str]]:
    score_val = int(round(float(likelihood_score)))
    if score_val >= 75:
        band = "high"
    elif score_val >= 50:
        band = "medium"
    else:
        band = "low"
    why = ", ".join(reasons[:3]) if reasons else "recent activity and quote context"
    explanation = (
        f"{customer_name or 'Customer'} currently has a {band} likelihood to order "
        f"(score {score_val}/100) based on {why}."
    )
    next_steps = [
        f"Use {channel} first with a concise follow-up and clear call-to-action.",
        "Ask one qualifying question to unblock the next decision.",
        "Set a dated next action and review status within 48 hours.",
    ]
    if action == SuggestedAction.PHONE_CALL:
        next_steps[0] = "Place a call first; if no answer, follow with a short SMS summary."
    elif action == SuggestedAction.REVIEW_QUOTE:
        next_steps[0] = "Review the quote options and send a refreshed version if needed."
    elif action == SuggestedAction.RESEND_QUOTE:
        next_steps[0] = "Resend the quote with a short recap of value and a response deadline."
    return explanation, next_steps


def _ai_order_likelihood_from_text(
    *,
    customer_name: str,
    quote_number: Optional[str],
    recent_texts: List[str],
    fallback_score: Decimal,
    fallback_reasons: List[str],
) -> Tuple[Decimal, Decimal, List[str], str, Optional[str], Optional[List[str]]]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not recent_texts:
        return fallback_score, Decimal("0.65"), fallback_reasons, "heuristic-v1", None, None

    model = os.getenv("OPENAI_WEEKLY_PLAN_MODEL", "").strip() or "gpt-4.1-mini"
    text_blob = "\n---\n".join([t[:350] for t in recent_texts[:8]])
    instructions = (
        "You score sales likelihood from customer communication snippets. "
        "Return strict JSON only with keys score (0-100 integer), confidence (0-1 float), "
        "reasons (array of <=5 short snake_case strings), explanation (single concise paragraph), "
        "next_steps (array of 3 concise action steps). "
        "No markdown."
    )
    user_prompt = (
        f"Customer: {customer_name or 'Customer'}\n"
        f"Quote: {quote_number or 'N/A'}\n"
        f"Recent inbound communication snippets:\n{text_blob}\n"
        "Estimate short-term ordering likelihood."
    )
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": instructions}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "metadata": {"feature": "weekly_order_likelihood"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        out = _extract_text_from_responses_api(data if isinstance(data, dict) else {})
        parsed = json.loads(out)
        score = int(parsed.get("score", int(fallback_score)))
        conf = float(parsed.get("confidence", 0.7))
        reasons = parsed.get("reasons") or fallback_reasons
        explanation = parsed.get("explanation")
        next_steps = parsed.get("next_steps")
        if not isinstance(reasons, list):
            reasons = fallback_reasons
        if not isinstance(explanation, str) or not explanation.strip():
            explanation = None
        if not isinstance(next_steps, list):
            next_steps = None
        else:
            next_steps = [str(step).strip() for step in next_steps if str(step).strip()][:3]
        clean_reasons = [re.sub(r"[^a-z0-9_]", "_", str(r).lower())[:50] for r in reasons[:5]]
        return (
            Decimal(max(0, min(100, score))),
            Decimal(str(max(0.0, min(1.0, conf)))),
            clean_reasons,
            f"ai-{model}",
            explanation.strip()[:1200] if explanation else None,
            next_steps,
        )
    except Exception:
        return fallback_score, Decimal("0.65"), fallback_reasons, "heuristic-v1", None, None


def _week_start_utc(today: Optional[date] = None) -> date:
    d = today or datetime.utcnow().date()
    return d - timedelta(days=d.weekday())


def _priority_weight(priority: ReminderPriority) -> Decimal:
    mapping = {
        ReminderPriority.LOW: Decimal("5"),
        ReminderPriority.MEDIUM: Decimal("12"),
        ReminderPriority.HIGH: Decimal("22"),
        ReminderPriority.URGENT: Decimal("35"),
    }
    return mapping.get(priority, Decimal("10"))


def _value_weight(quote: Optional[Quote]) -> Decimal:
    if not quote or quote.total_amount is None:
        return Decimal("0")
    amount = Decimal(quote.total_amount)
    if amount >= Decimal("15000"):
        return Decimal("18")
    if amount >= Decimal("8000"):
        return Decimal("12")
    if amount >= Decimal("3000"):
        return Decimal("7")
    return Decimal("3")


def _probability_weight(quote: Optional[Quote]) -> Decimal:
    if not quote or quote.close_probability is None:
        return Decimal("0")
    cp = Decimal(quote.close_probability)
    return max(Decimal("0"), min(Decimal("15"), cp / Decimal("7")))


def _default_message(action: SuggestedAction, customer_name: str, quote_number: Optional[str]) -> str:
    if action == SuggestedAction.PHONE_CALL:
        return f"Hi {customer_name}, just checking in to see if you had any questions."
    if action == SuggestedAction.RESEND_QUOTE and quote_number:
        return f"Hi {customer_name}, following up on quote {quote_number}. Happy to resend and tweak details."
    if action == SuggestedAction.REVIEW_QUOTE and quote_number:
        return f"Hi {customer_name}, would you like us to refresh quote {quote_number} with updated options?"
    return f"Hi {customer_name}, just a quick follow-up from the team."


def _resolve_weekly_template_message(
    session: Session,
    *,
    action: SuggestedAction,
    channel: str,
    customer_name: str,
    quote_number: Optional[str],
) -> str:
    template = session.exec(
        select(WeeklyPlanTemplate).where(
            WeeklyPlanTemplate.suggested_action == action,
            WeeklyPlanTemplate.channel == channel.upper(),
            WeeklyPlanTemplate.is_active.is_(True),
        )
    ).first()
    if not template:
        return _default_message(action, customer_name, quote_number)
    ctx = {
        "customer": {"name": customer_name or "there"},
        "quote": {"number": quote_number or ""},
        "company": {"name": "LeadLock"},
    }
    try:
        rendered = JinjaTemplate(template.body_template).render(**ctx).strip()
        return rendered or _default_message(action, customer_name, quote_number)
    except Exception:
        return _default_message(action, customer_name, quote_number)


def render_weekly_plan_item_message(
    session: Session,
    *,
    action: SuggestedAction,
    channel: str,
    customer_id: Optional[int],
    quote_id: Optional[int],
    fallback_customer_name: str = "there",
    customer_by_id: Optional[Dict[int, Customer]] = None,
    quote_by_id: Optional[Dict[int, Quote]] = None,
) -> str:
    customer_name = fallback_customer_name
    quote_number: Optional[str] = None

    if customer_id:
        customer = customer_by_id.get(customer_id) if customer_by_id is not None else session.get(Customer, customer_id)
        if customer and customer.name:
            customer_name = customer.name
    if quote_id:
        quote = quote_by_id.get(quote_id) if quote_by_id is not None else session.get(Quote, quote_id)
        if quote and quote.quote_number:
            quote_number = quote.quote_number

    return _resolve_weekly_template_message(
        session,
        action=action,
        channel=channel,
        customer_name=customer_name,
        quote_number=quote_number,
    )


def _blend_final_priority(base_priority_score: Decimal, likelihood_score: Decimal) -> Decimal:
    blended = (base_priority_score * Decimal("0.65")) + (likelihood_score * Decimal("0.35"))
    return max(Decimal("1"), min(Decimal("100"), blended))


def _stale_quote_entry_score(quote: Quote, rule: ReminderRule, days_stale: int) -> Decimal:
    return (
        Decimal("22")
        + Decimal(days_stale)
        + _priority_weight(rule.priority)
        + _value_weight(quote)
        + _probability_weight(quote)
    )


def _stale_opportunity_entry_score(opp: Quote, days_overdue: int) -> Decimal:
    return Decimal("30") + Decimal(days_overdue * 2) + _value_weight(opp) + _probability_weight(opp)


def _reduce_stale_quote_entries(
    entries: List[Tuple[Quote, ReminderRule, int]],
) -> List[Tuple[Quote, ReminderRule, int]]:
    """Keep one stale quote entry per customer, using the latest quote globally."""
    if not entries:
        return []
    no_customer: List[Tuple[Quote, ReminderRule, int]] = []
    by_customer: Dict[int, List[Tuple[Quote, ReminderRule, int]]] = {}
    for entry in entries:
        quote = entry[0]
        if quote.customer_id is None:
            no_customer.append(entry)
            continue
        by_customer.setdefault(quote.customer_id, []).append(entry)

    reduced: List[Tuple[Quote, ReminderRule, int]] = list(no_customer)
    for customer_entries in by_customer.values():
        latest_quotes = latest_quotes_per_customer([entry[0] for entry in customer_entries])
        if not latest_quotes:
            continue
        latest_quote = latest_quotes[0]
        if latest_quote.id is None:
            continue
        matching = [entry for entry in customer_entries if entry[0].id == latest_quote.id]
        if not matching:
            continue
        reduced.append(max(matching, key=lambda entry: _stale_quote_entry_score(entry[0], entry[1], entry[2])))
    return reduced


def _reduce_stale_opportunity_entries(
    entries: List[Tuple[Quote, str, int]],
) -> List[Tuple[Quote, str, int]]:
    """Keep one stale opportunity entry per customer, using the latest opportunity quote."""
    if not entries:
        return []
    no_customer: List[Tuple[Quote, str, int]] = []
    by_customer: Dict[int, List[Tuple[Quote, str, int]]] = {}
    for entry in entries:
        opp = entry[0]
        if opp.customer_id is None:
            no_customer.append(entry)
            continue
        by_customer.setdefault(opp.customer_id, []).append(entry)

    reduced: List[Tuple[Quote, str, int]] = []
    for customer_entries in by_customer.values():
        latest_quotes = latest_quotes_per_customer([entry[0] for entry in customer_entries])
        if not latest_quotes:
            continue
        latest_opp = latest_quotes[0]
        if latest_opp.id is None:
            continue
        matching = [entry for entry in customer_entries if entry[0].id == latest_opp.id]
        if not matching:
            continue
        reduced.append(max(matching, key=lambda entry: _stale_opportunity_entry_score(entry[0], entry[2])))
    return reduced + no_customer


def _ordered_customer_and_lead_ids(session: Session) -> tuple[set[int], set[int]]:
    ordered_customer_ids = {
        customer_id
        for customer_id in session.exec(
            select(Order.customer_id).where(Order.customer_id.is_not(None))
        ).all()
        if customer_id is not None
    }
    accepted_rows = session.exec(
        select(Quote.customer_id, Quote.lead_id).where(
            (Quote.accepted_at.is_not(None)) | (Quote.status == QuoteStatus.ACCEPTED)
        )
    ).all()
    ordered_lead_ids: set[int] = set()
    for customer_id, lead_id in accepted_rows:
        if customer_id is not None:
            ordered_customer_ids.add(customer_id)
        if lead_id is not None:
            ordered_lead_ids.add(lead_id)
    return ordered_customer_ids, ordered_lead_ids


def generate_weekly_plan(
    session: Session,
    *,
    generated_by_id: Optional[int] = None,
    auto_execute: bool = True,
    dry_run: bool = False,
) -> WeeklyPlanRun:
    week_start = _week_start_utc()
    run = WeeklyPlanRun(
        week_start=week_start,
        generated_by_id=generated_by_id,
        scope=WeeklyPlanScope.FULL_PIPELINE,
        model_version="hybrid-likelihood-v1",
    )
    session.add(run)
    session.flush()

    plan_items: List[WeeklyPlanItem] = []
    seen_keys: set[tuple[str, int]] = set()
    ordered_customer_ids, ordered_lead_ids = _ordered_customer_and_lead_ids(session)

    for lead, rule, days_stale in detect_stale_leads(session):
        if not lead.id:
            continue
        if (lead.customer_id is not None and lead.customer_id in ordered_customer_ids) or lead.id in ordered_lead_ids:
            continue
        key = ("lead", lead.id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        score = Decimal("25") + Decimal(days_stale) + _priority_weight(rule.priority)
        reason_codes = [f"lead_status:{lead.status.value}", "stale_lead"]
        if days_stale >= 7:
            reason_codes.append("no_recent_activity")
        action = rule.suggested_action
        channel = "CALL" if action == SuggestedAction.PHONE_CALL else "EMAIL"
        auto_eligible = action in (SuggestedAction.FOLLOW_UP, SuggestedAction.CONTACT_CUSTOMER) and channel == "EMAIL"
        customer_name = lead.name or "there"
        recent_texts = _collect_customer_recent_text(session, lead.customer_id) if lead.customer_id else []
        heuristic_score, heuristic_conf, heuristic_reasons = _heuristic_order_likelihood(
            quote=None,
            days_stale=days_stale,
            recent_texts=recent_texts,
        )
        likelihood_score, likelihood_conf, likelihood_reasons, _source, explanation, next_steps = _ai_order_likelihood_from_text(
            customer_name=customer_name,
            quote_number=None,
            recent_texts=recent_texts,
            fallback_score=heuristic_score,
            fallback_reasons=heuristic_reasons,
        )
        if not explanation or not next_steps:
            explanation, next_steps = _fallback_narrative(
                customer_name=customer_name,
                action=action,
                channel=channel,
                likelihood_score=likelihood_score,
                reasons=likelihood_reasons,
            )
        final_score = _blend_final_priority(min(Decimal("100"), score), likelihood_score)
        plan_items.append(
            WeeklyPlanItem(
                plan_run_id=run.id,
                lead_id=lead.id,
                customer_id=lead.customer_id,
                assigned_to_id=lead.assigned_to_id,
                priority_score=final_score,
                confidence=max(Decimal("0.60"), (Decimal("0.72") + likelihood_conf) / Decimal("2")),
                order_likelihood_score=likelihood_score,
                order_likelihood_confidence=likelihood_conf if likelihood_conf else heuristic_conf,
                order_likelihood_reasons=likelihood_reasons,
                likelihood_explanation=explanation,
                recommended_next_steps=next_steps or [],
                reason_codes=reason_codes,
                recommended_action=action,
                channel=channel,
                auto_eligible=auto_eligible,
                suggested_message=render_weekly_plan_item_message(
                    session,
                    action=action,
                    channel=channel,
                    customer_id=lead.customer_id,
                    quote_id=None,
                    fallback_customer_name=customer_name,
                ),
                due_date=datetime.utcnow().date() + timedelta(days=2),
            )
        )

    quote_by_id = {}
    seen_quote_customer_ids: set[int] = set()
    for quote, rule, days_stale in _reduce_stale_quote_entries(detect_stale_quotes(session)):
        if not quote.id:
            continue
        if (quote.customer_id is not None and quote.customer_id in ordered_customer_ids) or (
            quote.lead_id is not None and quote.lead_id in ordered_lead_ids
        ):
            continue
        if quote.customer_id is not None and quote.customer_id in seen_quote_customer_ids:
            continue
        quote_by_id[quote.id] = quote
        key = ("quote", quote.id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        score = Decimal("22") + Decimal(days_stale) + _priority_weight(rule.priority) + _value_weight(quote) + _probability_weight(quote)
        reason_codes = [f"quote_status:{quote.status.value}", "stale_quote"]
        if quote.sent_at and calculate_days_stale(quote.sent_at) >= 7:
            reason_codes.append("quote_decay_risk")
        action = rule.suggested_action
        channel = "SMS" if action in (SuggestedAction.RESEND_QUOTE, SuggestedAction.CONTACT_CUSTOMER) else "CALL"
        auto_eligible = channel in ("SMS", "EMAIL") and action in (SuggestedAction.RESEND_QUOTE, SuggestedAction.CONTACT_CUSTOMER)
        customer_name = "there"
        if quote.customer_id:
            customer = session.get(Customer, quote.customer_id)
            if customer and customer.name:
                customer_name = customer.name
        recent_texts = _collect_customer_recent_text(session, quote.customer_id) if quote.customer_id else []
        heuristic_score, heuristic_conf, heuristic_reasons = _heuristic_order_likelihood(
            quote=quote,
            days_stale=days_stale,
            recent_texts=recent_texts,
        )
        likelihood_score, likelihood_conf, likelihood_reasons, _source, explanation, next_steps = _ai_order_likelihood_from_text(
            customer_name=customer_name,
            quote_number=quote.quote_number,
            recent_texts=recent_texts,
            fallback_score=heuristic_score,
            fallback_reasons=heuristic_reasons,
        )
        if not explanation or not next_steps:
            explanation, next_steps = _fallback_narrative(
                customer_name=customer_name,
                action=action,
                channel=channel,
                likelihood_score=likelihood_score,
                reasons=likelihood_reasons,
            )
        final_score = _blend_final_priority(min(Decimal("100"), score), likelihood_score)
        plan_items.append(
            WeeklyPlanItem(
                plan_run_id=run.id,
                quote_id=quote.id,
                lead_id=quote.lead_id,
                customer_id=quote.customer_id,
                assigned_to_id=quote.owner_id or quote.created_by_id,
                priority_score=final_score,
                confidence=max(Decimal("0.65"), (Decimal("0.80") + likelihood_conf) / Decimal("2")),
                order_likelihood_score=likelihood_score,
                order_likelihood_confidence=likelihood_conf if likelihood_conf else heuristic_conf,
                order_likelihood_reasons=likelihood_reasons,
                likelihood_explanation=explanation,
                recommended_next_steps=next_steps or [],
                reason_codes=reason_codes,
                recommended_action=action,
                channel=channel,
                auto_eligible=auto_eligible,
                suggested_message=render_weekly_plan_item_message(
                    session,
                    action=action,
                    channel=channel,
                    customer_id=quote.customer_id,
                    quote_id=quote.id,
                    fallback_customer_name=customer_name,
                ),
                due_date=datetime.utcnow().date() + timedelta(days=2),
            )
        )
        if quote.customer_id is not None:
            seen_quote_customer_ids.add(quote.customer_id)

    for opp, reason, days_overdue in _reduce_stale_opportunity_entries(detect_stale_opportunities(session)):
        if not opp.id:
            continue
        if (opp.customer_id is not None and opp.customer_id in ordered_customer_ids) or (
            opp.lead_id is not None and opp.lead_id in ordered_lead_ids
        ):
            continue
        if opp.customer_id is not None and opp.customer_id in seen_quote_customer_ids:
            continue
        key = ("opp", opp.id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        score = Decimal("30") + Decimal(days_overdue * 2) + _value_weight(opp) + _probability_weight(opp)
        reason_codes = ["stale_opportunity", f"reason:{reason.lower()}"]
        action = SuggestedAction.FOLLOW_UP if days_overdue < 10 else SuggestedAction.REVIEW_QUOTE
        channel = "CALL" if days_overdue >= 7 else "EMAIL"
        customer_name = "there"
        if opp.customer_id:
            customer = session.get(Customer, opp.customer_id)
            if customer and customer.name:
                customer_name = customer.name
        recent_texts = _collect_customer_recent_text(session, opp.customer_id) if opp.customer_id else []
        heuristic_score, heuristic_conf, heuristic_reasons = _heuristic_order_likelihood(
            quote=opp,
            days_stale=days_overdue,
            recent_texts=recent_texts,
        )
        likelihood_score, likelihood_conf, likelihood_reasons, _source, explanation, next_steps = _ai_order_likelihood_from_text(
            customer_name=customer_name,
            quote_number=opp.quote_number,
            recent_texts=recent_texts,
            fallback_score=heuristic_score,
            fallback_reasons=heuristic_reasons,
        )
        if not explanation or not next_steps:
            explanation, next_steps = _fallback_narrative(
                customer_name=customer_name,
                action=action,
                channel=channel,
                likelihood_score=likelihood_score,
                reasons=likelihood_reasons,
            )
        final_score = _blend_final_priority(min(Decimal("100"), score), likelihood_score)
        plan_items.append(
            WeeklyPlanItem(
                plan_run_id=run.id,
                quote_id=opp.id,
                lead_id=opp.lead_id,
                customer_id=opp.customer_id,
                assigned_to_id=opp.owner_id or opp.created_by_id,
                priority_score=final_score,
                confidence=max(Decimal("0.60"), (Decimal("0.75") + likelihood_conf) / Decimal("2")),
                order_likelihood_score=likelihood_score,
                order_likelihood_confidence=likelihood_conf if likelihood_conf else heuristic_conf,
                order_likelihood_reasons=likelihood_reasons,
                likelihood_explanation=explanation,
                recommended_next_steps=next_steps or [],
                reason_codes=reason_codes,
                recommended_action=action,
                channel=channel,
                auto_eligible=channel == "EMAIL" and action == SuggestedAction.FOLLOW_UP,
                suggested_message=render_weekly_plan_item_message(
                    session,
                    action=action,
                    channel=channel,
                    customer_id=opp.customer_id,
                    quote_id=opp.id,
                    fallback_customer_name=customer_name,
                ),
                due_date=datetime.utcnow().date() + timedelta(days=1),
            )
        )
        if opp.customer_id is not None:
            seen_quote_customer_ids.add(opp.customer_id)

    plan_items.sort(key=lambda item: (item.priority_score, item.created_at), reverse=True)
    for item in plan_items:
        session.add(item)

    run.total_items = len(plan_items)
    run.auto_eligible_items = sum(1 for item in plan_items if item.auto_eligible)
    session.add(run)
    session.commit()
    session.refresh(run)

    if auto_execute and not dry_run:
        execute_auto_eligible_items(session, run.id)
        session.refresh(run)

    return run


def execute_auto_eligible_items(session: Session, run_id: int) -> int:
    run = session.get(WeeklyPlanRun, run_id)
    if not run:
        return 0

    company = session.exec(select(CompanySettings).limit(1)).first()
    if _is_within_outreach_quiet_hours(company):
        return 0

    items = session.exec(
        select(WeeklyPlanItem)
        .where(
            WeeklyPlanItem.plan_run_id == run_id,
            WeeklyPlanItem.auto_eligible.is_(True),
            WeeklyPlanItem.status == WeeklyPlanItemStatus.PENDING_REVIEW,
        )
        .order_by(desc(WeeklyPlanItem.priority_score))
        .limit(25)
    ).all()

    sent_count = 0
    for item in items:
        if _dispatch_weekly_plan_item(session, run, item):
            sent_count += 1

    run.auto_sent_items = sent_count
    session.add(run)
    session.commit()
    return sent_count


def _dispatch_weekly_plan_item(
    session: Session,
    run: WeeklyPlanRun,
    item: WeeklyPlanItem,
    *,
    sender_user_id: Optional[int] = None,
) -> bool:
    if not item.customer_id:
        item.status = WeeklyPlanItemStatus.AUTO_FAILED
        item.execution_error = "Missing customer on weekly plan item"
        item.updated_at = datetime.utcnow()
        session.add(item)
        return False
    customer = session.get(Customer, item.customer_id)
    if not customer:
        item.status = WeeklyPlanItemStatus.AUTO_FAILED
        item.execution_error = "Customer not found"
        item.updated_at = datetime.utcnow()
        session.add(item)
        return False
    if customer.automated_reminder_outreach_opt_out:
        item.status = WeeklyPlanItemStatus.REJECTED
        item.execution_error = "Customer opted out of automated reminder outreach"
        item.updated_at = datetime.utcnow()
        session.add(item)
        return False
    assignee = session.get(User, item.assigned_to_id) if item.assigned_to_id else None
    actor_id = sender_user_id or item.assigned_to_id or run.generated_by_id or get_system_user_id(session)
    channel = (item.channel or "").upper()
    now = datetime.utcnow()
    try:
        if channel == "SMS":
            phone = (customer.phone or "").strip()
            if not phone:
                raise ValueError("Customer has no phone number")
            success, sid, err = send_sms(phone, item.suggested_message or "Quick follow-up from the team.")
            if not success:
                raise ValueError(err or "SMS send failed")
            session.add(
                SmsMessage(
                    customer_id=customer.id,
                    lead_id=item.lead_id,
                    direction=SmsDirection.SENT,
                    from_phone="",
                    to_phone=normalize_phone(phone),
                    body=item.suggested_message or "",
                    twilio_sid=sid,
                    sent_at=now,
                    created_by_id=actor_id,
                )
            )
            session.add(
                Activity(
                    customer_id=customer.id,
                    activity_type=ActivityType.SMS_SENT,
                    notes=f"Weekly planner manual SMS\n{item.suggested_message or ''}",
                    created_by_id=actor_id,
                )
            )
        elif channel == "EMAIL":
            to_email = (customer.email or "").strip()
            if not to_email:
                raise ValueError("Customer has no email")
            if not assignee or not is_email_configured(assignee.id):
                raise ValueError("Assignee email not configured")
            subject = "Quick follow-up from LeadLock"
            body_html = f"<p>{(item.suggested_message or 'Quick follow-up from the team.')}</p>"
            success, message_id, err, sent_html, sent_text = send_email(
                to_email=to_email,
                subject=subject,
                body_html=body_html,
                body_text=_html_to_plain(body_html),
                user_id=assignee.id,
                customer_number=customer.customer_number,
            )
            if not success:
                raise ValueError(err or "Email send failed")
            session.add(
                Email(
                    customer_id=customer.id,
                    message_id=message_id,
                    direction=EmailDirection.SENT,
                    from_email=assignee.email,
                    to_email=to_email,
                    subject=subject,
                    body_html=sent_html or body_html,
                    body_text=sent_text or _html_to_plain(body_html),
                    sent_at=now,
                    created_by_id=actor_id,
                    thread_id=f"weekly-plan-{item.id}",
                )
            )
            session.add(
                Activity(
                    customer_id=customer.id,
                    activity_type=ActivityType.EMAIL_SENT,
                    notes=build_activity_email_notes(
                        "Weekly planner manual email",
                        subject,
                        sent_text or _html_to_plain(body_html),
                        sent_html or body_html,
                    ),
                    created_by_id=actor_id,
                )
            )
        elif channel == "CALL":
            phone = (customer.phone or "").strip()
            call_notes = item.suggested_message or "Follow-up call from weekly plan"
            if phone:
                call_notes = f"{call_notes}\nCustomer phone: {phone}"
            session.add(
                Activity(
                    customer_id=customer.id,
                    activity_type=ActivityType.CALL_ATTEMPTED,
                    notes=f"Weekly planner call task\n{call_notes}",
                    created_by_id=actor_id,
                )
            )
        else:
            raise ValueError(f"Unsupported channel: {item.channel or 'unknown'}")

        item.status = WeeklyPlanItemStatus.AUTO_SENT
        item.executed_at = now
        item.execution_error = None
        item.updated_at = now
        session.add(item)
        return True
    except Exception as exc:
        item.status = WeeklyPlanItemStatus.AUTO_FAILED
        item.execution_error = str(exc)[:1000]
        item.updated_at = datetime.utcnow()
        session.add(item)
        return False


def send_weekly_plan_item(
    session: Session,
    item_id: int,
    *,
    sender_user_id: Optional[int] = None,
) -> Optional[WeeklyPlanItem]:
    item = session.get(WeeklyPlanItem, item_id)
    if not item:
        return None
    if item.status != WeeklyPlanItemStatus.PENDING_REVIEW:
        item.execution_error = f"Item is {item.status.value} and cannot be sent"
        item.updated_at = datetime.utcnow()
        session.add(item)
        session.commit()
        session.refresh(item)
        return item
    run = session.get(WeeklyPlanRun, item.plan_run_id)
    if not run:
        item.status = WeeklyPlanItemStatus.AUTO_FAILED
        item.execution_error = "Parent plan run not found"
        item.updated_at = datetime.utcnow()
        session.add(item)
        session.commit()
        session.refresh(item)
        return item
    company = session.exec(select(CompanySettings).limit(1)).first()
    if _is_within_outreach_quiet_hours(company):
        item.status = WeeklyPlanItemStatus.AUTO_FAILED
        item.execution_error = "Blocked by quiet hours policy"
        item.updated_at = datetime.utcnow()
        session.add(item)
        session.commit()
        session.refresh(item)
        return item
    _dispatch_weekly_plan_item(session, run, item, sender_user_id=sender_user_id)
    if item.status == WeeklyPlanItemStatus.AUTO_SENT:
        run.auto_sent_items = int(run.auto_sent_items or 0) + 1
        session.add(run)
    session.commit()
    session.refresh(item)
    return item


def send_weekly_plan_items_bulk(
    session: Session,
    item_ids: List[int],
    *,
    sender_user_id: Optional[int] = None,
) -> dict:
    if not item_ids:
        return {"requested": 0, "sent": 0, "failed": 0}
    sent = 0
    failed = 0
    deduped_ids = list(dict.fromkeys(item_ids))
    for item_id in deduped_ids:
        item = send_weekly_plan_item(session, item_id, sender_user_id=sender_user_id)
        if not item:
            failed += 1
            continue
        if item.status == WeeklyPlanItemStatus.AUTO_SENT:
            sent += 1
        else:
            failed += 1
    return {"requested": len(deduped_ids), "sent": sent, "failed": failed}


def mark_plan_item_outcome(
    session: Session,
    item_id: int,
    *,
    status: Optional[WeeklyPlanItemStatus] = None,
    outcome_result: Optional[str] = None,
    response_received: Optional[bool] = None,
    suggested_message: Optional[str] = None,
) -> Optional[WeeklyPlanItem]:
    item = session.get(WeeklyPlanItem, item_id)
    if not item:
        return None
    if status is not None:
        item.status = status
    if outcome_result is not None:
        item.outcome_result = outcome_result
    if response_received is not None:
        item.response_received = response_received
    if suggested_message is not None:
        item.suggested_message = suggested_message.strip() or None
    item.updated_at = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def get_plan_metrics(session: Session, run_id: int) -> dict:
    run = session.get(WeeklyPlanRun, run_id)
    if not run:
        return {}
    total = run.total_items
    done = session.exec(
        select(func.count(WeeklyPlanItem.id)).where(
            WeeklyPlanItem.plan_run_id == run_id,
            WeeklyPlanItem.status.in_([WeeklyPlanItemStatus.COMPLETED, WeeklyPlanItemStatus.AUTO_SENT]),
        )
    ).one()
    replied = session.exec(
        select(func.count(WeeklyPlanItem.id)).where(
            WeeklyPlanItem.plan_run_id == run_id,
            WeeklyPlanItem.response_received.is_(True),
        )
    ).one()
    avg_likelihood = session.exec(
        select(func.avg(WeeklyPlanItem.order_likelihood_score)).where(
            WeeklyPlanItem.plan_run_id == run_id,
        )
    ).one()
    return {
        "run_id": run.id,
        "week_start": run.week_start,
        "total_items": total,
        "auto_eligible_items": run.auto_eligible_items,
        "auto_sent_items": run.auto_sent_items,
        "completed_items": int(done or 0),
        "response_received_items": int(replied or 0),
        "average_order_likelihood": float(avg_likelihood or 0),
        "completion_rate_pct": float((Decimal(done or 0) / Decimal(total) * Decimal("100")) if total else Decimal("0")),
    }
