from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from sqlmodel import Session, select

from app.models import (
    Activity,
    ActivityType,
    Email,
    EmailDirection,
    Lead,
    LeadSource,
    LeadStatus,
    SmsDirection,
    SmsMessage,
    StatusHistory,
    User,
    CustomerOutreachSend,
)
from app.system_user_service import is_system_user

_FACEBOOK_STATUS_WINDOW = timedelta(minutes=5)
_AUTOMATED_ACTIVITY_PREFIXES: dict[ActivityType, tuple[str, ...]] = {
    ActivityType.EMAIL_RECEIVED: ("Email received from ",),
    ActivityType.SMS_RECEIVED: ("SMS received from ",),
    ActivityType.MESSENGER_RECEIVED: ("Messenger received:",),
    ActivityType.EMAIL_SENT: ("Automated email (rule ",),
    ActivityType.SMS_SENT: ("Automated SMS (rule ", "SMS bot reply sent to "),
    ActivityType.NOTE: ("Lead from Facebook Lead Ad form",),
}


@dataclass
class SystemAttributionBackfillResult:
    source_user_id: int
    source_email: str
    source_full_name: str
    system_user_id: int
    dry_run: bool
    activities_updated: int
    emails_updated: int
    sms_messages_updated: int
    status_history_updated: int

    @property
    def total_updated(self) -> int:
        return (
            self.activities_updated
            + self.emails_updated
            + self.sms_messages_updated
            + self.status_history_updated
        )


def _is_automated_activity(activity: Activity) -> bool:
    notes = (activity.notes or "").strip()
    prefixes = _AUTOMATED_ACTIVITY_PREFIXES.get(activity.activity_type, ())
    return any(notes.startswith(prefix) for prefix in prefixes)


def _matching_sms_activity_exists(message: SmsMessage, activities: list[Activity]) -> bool:
    body = (message.body or "").strip()
    if not body:
        return False
    expected_suffix = f"\n{body}"
    for activity in activities:
        if activity.customer_id != message.customer_id:
            continue
        notes = (activity.notes or "").strip()
        if not notes:
            continue
        if notes.endswith(expected_suffix):
            return True
    return False


def _candidate_activity_rows(session: Session, source_user_id: int) -> list[Activity]:
    rows = session.exec(select(Activity).where(Activity.created_by_id == source_user_id)).all()
    return [row for row in rows if _is_automated_activity(row)]


def _candidate_email_rows(session: Session, source_user_id: int) -> list[Email]:
    outreach_message_ids = {
        message_id
        for message_id in session.exec(
            select(CustomerOutreachSend.external_message_id).where(
                CustomerOutreachSend.channel == "EMAIL",
                CustomerOutreachSend.external_message_id.is_not(None),
            )
        ).all()
        if message_id
    }
    if not outreach_message_ids:
        return []
    rows = session.exec(
        select(Email).where(
            Email.created_by_id == source_user_id,
            Email.direction == EmailDirection.SENT,
        )
    ).all()
    return [row for row in rows if row.message_id and row.message_id in outreach_message_ids]


def _candidate_sms_rows(
    session: Session,
    source_user_id: int,
    automated_activities: list[Activity],
) -> list[SmsMessage]:
    outreach_sids = {
        sid
        for sid in session.exec(
            select(CustomerOutreachSend.external_message_id).where(
                CustomerOutreachSend.channel == "SMS",
                CustomerOutreachSend.external_message_id.is_not(None),
            )
        ).all()
        if sid
    }
    activities_by_customer: dict[int, list[Activity]] = defaultdict(list)
    for activity in automated_activities:
        if activity.activity_type == ActivityType.SMS_SENT:
            activities_by_customer[int(activity.customer_id)].append(activity)

    rows = session.exec(
        select(SmsMessage).where(
            SmsMessage.created_by_id == source_user_id,
            SmsMessage.direction == SmsDirection.SENT,
        )
    ).all()
    result: list[SmsMessage] = []
    for row in rows:
        if row.twilio_sid and row.twilio_sid in outreach_sids:
            result.append(row)
            continue
        if _matching_sms_activity_exists(row, activities_by_customer.get(row.customer_id, [])):
            result.append(row)
    return result


def _candidate_status_rows(session: Session, source_user_id: int) -> list[StatusHistory]:
    rows = session.exec(
        select(StatusHistory, Lead)
        .join(Lead, StatusHistory.lead_id == Lead.id)
        .where(StatusHistory.changed_by_id == source_user_id)
    ).all()
    result: list[StatusHistory] = []
    for history, lead in rows:
        if lead.lead_source != LeadSource.FACEBOOK:
            continue
        if history.old_status is not None or history.new_status != LeadStatus.NEW:
            continue
        if abs(history.created_at - lead.created_at) > _FACEBOOK_STATUS_WINDOW:
            continue
        result.append(history)
    return result


def backfill_system_attribution(
    session: Session,
    *,
    source_user: User,
    system_user_id: int,
    dry_run: bool,
) -> SystemAttributionBackfillResult:
    if source_user.id is None:
        raise ValueError("Source user must be persisted before backfill")
    if is_system_user(source_user) or source_user.id == system_user_id:
        raise ValueError("Cannot backfill the internal System account")

    automated_activities = _candidate_activity_rows(session, source_user.id)
    automated_emails = _candidate_email_rows(session, source_user.id)
    automated_sms = _candidate_sms_rows(session, source_user.id, automated_activities)
    automated_status_history = _candidate_status_rows(session, source_user.id)

    if not dry_run:
        for row in automated_activities:
            row.created_by_id = system_user_id
            session.add(row)
        for row in automated_emails:
            row.created_by_id = system_user_id
            session.add(row)
        for row in automated_sms:
            row.created_by_id = system_user_id
            session.add(row)
        for row in automated_status_history:
            row.changed_by_id = system_user_id
            session.add(row)
        session.commit()

    return SystemAttributionBackfillResult(
        source_user_id=source_user.id,
        source_email=source_user.email,
        source_full_name=source_user.full_name,
        system_user_id=system_user_id,
        dry_run=dry_run,
        activities_updated=len(automated_activities),
        emails_updated=len(automated_emails),
        sms_messages_updated=len(automated_sms),
        status_history_updated=len(automated_status_history),
    )
