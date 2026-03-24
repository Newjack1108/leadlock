"""
Resolve inbound email thread_id so replies appear in the same thread as sent mail.

Graph/Exchange assigns its own Message-ID on send; LeadLock stores a local message_id.
We match using In-Reply-To / References when possible, then subject, then latest sent mail.
"""
import re
from typing import Optional, List

from sqlmodel import Session, select

from app.models import Email, EmailDirection


def _strip_angle(mid: Optional[str]) -> str:
    if not mid:
        return ""
    s = mid.strip()
    if s.startswith("<") and s.endswith(">"):
        return s[1:-1].strip()
    return s


def _refs_tokens(refs: Optional[str]) -> List[str]:
    if not refs:
        return []
    return re.findall(r"<([^>]+)>", refs)


def _norm_subject(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"^(re|fwd|fw|aw|antw):\s*", "", s, flags=re.I | re.MULTILINE)
    return s.strip().lower()


def _extract_addr(field: Optional[str]) -> Optional[str]:
    if not field:
        return None
    m = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", field, re.I)
    return m.group(0).lower() if m else None


def find_thread_id_for_inbound(
    session: Session,
    customer_id: int,
    customer_email: str,
    in_reply_to: Optional[str],
    references: Optional[str],
    inbound_subject: str,
) -> Optional[str]:
    """
    Return thread_id for an inbound message so it groups with get_email_thread().

    get_email_thread uses Email.thread_id or falls back to message_id for the anchor.
    """
    customer_email = (customer_email or "").strip().lower()

    # Build candidate Message-IDs from reply headers (with/without angle brackets)
    candidates: List[str] = []
    if in_reply_to:
        t = in_reply_to.strip()
        candidates.append(t)
        candidates.append(f"<{_strip_angle(t)}>")
    for r in _refs_tokens(references):
        candidates.append(f"<{r}>")
        candidates.append(r)

    seen = set()
    uniq_candidates = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            uniq_candidates.append(c)

    for c in uniq_candidates:
        statement = select(Email).where(
            Email.customer_id == customer_id,
            Email.message_id == c,
        )
        hit = session.exec(statement).first()
        if hit:
            return hit.thread_id or hit.message_id

        # Normalized compare (Exchange vs stored formatting)
        stripped = _strip_angle(c)
        statement = select(Email).where(Email.customer_id == customer_id)
        for em in session.exec(statement).all():
            if em.message_id and _strip_angle(em.message_id) == stripped:
                return em.thread_id or em.message_id

    # Subject match: "Re: Quote QT-1" vs "Quote QT-1"
    ns = _norm_subject(inbound_subject)
    if ns:
        statement = (
            select(Email)
            .where(
                Email.customer_id == customer_id,
                Email.direction == EmailDirection.SENT,
            )
            .order_by(Email.sent_at.desc(), Email.id.desc())
        )
        for em in session.exec(statement).all():
            if _norm_subject(em.subject or "") == ns:
                return em.thread_id or em.message_id

    # Latest sent email to this customer (same To address)
    statement = (
        select(Email)
        .where(
            Email.customer_id == customer_id,
            Email.direction == EmailDirection.SENT,
        )
        .order_by(Email.sent_at.desc(), Email.id.desc())
    )
    for em in session.exec(statement).all():
        to_addr = _extract_addr(em.to_email or "")
        if to_addr and to_addr == customer_email:
            return em.thread_id or em.message_id

    return None
