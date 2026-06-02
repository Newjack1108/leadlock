from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select, or_

from app.models import Lead
from app.sms_service import normalize_phone


@dataclass
class LeadDuplicateMatch:
    is_duplicate: bool
    confidence: Decimal
    reason: Optional[str]
    matched_fields: Optional[str]
    primary_lead_id: Optional[int]


def _score_candidate(lead: Lead, candidate: Lead) -> tuple[int, list[str], Optional[str]]:
    score = 0
    matched_fields: list[str] = []
    reason: Optional[str] = None

    lead_email = (lead.email or "").strip().lower()
    candidate_email = (candidate.email or "").strip().lower()
    if lead_email and candidate_email and lead_email == candidate_email:
        score += 70
        matched_fields.append("email")
        reason = reason or "email_match"

    lead_phone = normalize_phone(lead.phone or "")
    candidate_phone = normalize_phone(candidate.phone or "")
    if lead_phone and candidate_phone and lead_phone == candidate_phone:
        score += 70
        matched_fields.append("phone")
        reason = reason or "phone_match"

    lead_name = (lead.name or "").strip().lower()
    candidate_name = (candidate.name or "").strip().lower()
    lead_postcode = (lead.postcode or "").strip().lower()
    candidate_postcode = (candidate.postcode or "").strip().lower()
    if lead_name and candidate_name and lead_postcode and candidate_postcode:
        if lead_name == candidate_name and lead_postcode == candidate_postcode:
            score += 40
            matched_fields.append("name_postcode")
            reason = reason or "name_postcode_match"

    if candidate.created_at and lead.created_at:
        if abs((lead.created_at - candidate.created_at).total_seconds()) <= 14 * 24 * 3600:
            score += 10
            matched_fields.append("time_window")

    return score, matched_fields, reason


def detect_duplicate_for_lead(session: Session, lead: Lead) -> LeadDuplicateMatch:
    if not lead.id:
        return LeadDuplicateMatch(False, Decimal("0.00"), None, None, None)

    email = (lead.email or "").strip()
    phone = (lead.phone or "").strip()
    name = (lead.name or "").strip()
    postcode = (lead.postcode or "").strip()
    if not any([email, phone, (name and postcode)]):
        return LeadDuplicateMatch(False, Decimal("0.00"), None, None, None)

    lookback = datetime.utcnow() - timedelta(days=90)
    query = select(Lead).where(Lead.id != lead.id, Lead.created_at >= lookback)

    predicates = []
    if email:
        predicates.append(Lead.email == email)
    if phone:
        predicates.append(Lead.phone == phone)
    if name and postcode:
        predicates.append((Lead.name == name) & (Lead.postcode == postcode))
    if not predicates:
        return LeadDuplicateMatch(False, Decimal("0.00"), None, None, None)

    candidates = list(session.exec(query.where(or_(*predicates))).all())
    if phone:
        for c in session.exec(select(Lead).where(Lead.id != lead.id, Lead.created_at >= lookback)).all():
            if c in candidates:
                continue
            if normalize_phone(c.phone or "") and normalize_phone(c.phone or "") == normalize_phone(phone):
                candidates.append(c)

    best: Optional[Lead] = None
    best_score = 0
    best_fields: list[str] = []
    best_reason: Optional[str] = None
    for c in candidates:
        score, matched_fields, reason = _score_candidate(lead, c)
        if score > best_score:
            best_score = score
            best_fields = matched_fields
            best_reason = reason
            best = c

    if best is None or best_score < 50:
        return LeadDuplicateMatch(False, Decimal("0.00"), None, None, None)

    primary_id = best.primary_lead_id or best.id
    if primary_id is None:
        return LeadDuplicateMatch(False, Decimal("0.00"), None, None, None)

    return LeadDuplicateMatch(
        is_duplicate=True,
        confidence=Decimal(str(min(best_score, 100))).quantize(Decimal("0.01")),
        reason=best_reason or "possible_duplicate",
        matched_fields=",".join(best_fields) if best_fields else None,
        primary_lead_id=int(primary_id),
    )
