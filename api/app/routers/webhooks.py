import os
import sys
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlmodel import Session, select
from typing import Optional
from app.database import get_session
from app.models import (
    Lead,
    User,
    StatusHistory,
    LeadStatus,
    LeadType,
    LeadSource,
    Customer,
    SmsMessage,
    SmsDirection,
    Activity,
    ActivityType,
    MessengerMessage,
    MessengerDirection,
)
from app.schemas import LeadCreate, LeadResponse
from app.auth import get_webhook_api_key
from app.workflow import check_sla_overdue
from app.routers.leads import enrich_lead_response
from app.sms_service import validate_twilio_webhook, normalize_phone, get_twilio_config
from app.messenger_service import parse_webhook_payload, get_user_profile, get_page_access_token

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/leads", response_model=LeadResponse)
async def create_lead_webhook(
    lead_data: LeadCreate,
    api_key: str = Depends(get_webhook_api_key),
    session: Session = Depends(get_session)
):
    """
    Create a lead via webhook (e.g., from Make.com).
    Requires X-API-Key header for authentication.
    """
    # Get default user ID from environment variable (optional)
    default_user_id = os.getenv("WEBHOOK_DEFAULT_USER_ID")
    
    # Create lead
    lead = Lead(**lead_data.dict())
    
    # Assign to default user if configured, otherwise leave unassigned
    if default_user_id:
        try:
            user_id = int(default_user_id)
            # Verify user exists
            statement = select(User).where(User.id == user_id)
            user = session.exec(statement).first()
            if user:
                lead.assigned_to_id = user_id
        except (ValueError, TypeError):
            # Invalid user ID, leave unassigned
            pass
    
    session.add(lead)
    session.commit()
    session.refresh(lead)
    
    # Create initial status history
    # Use default user ID for status history if available, otherwise use None
    changed_by_id = lead.assigned_to_id if lead.assigned_to_id else None
    
    if changed_by_id:
        status_history = StatusHistory(
            lead_id=lead.id,
            new_status=lead.status,
            changed_by_id=changed_by_id
        )
        session.add(status_history)
        session.commit()
    
    # For webhook responses, we need to create a minimal user object for enrich_lead_response
    # Since we don't have a current_user, we'll pass None and handle it in enrich_lead_response
    # Actually, let's get the user if assigned, otherwise create a dummy response
    if lead.assigned_to_id:
        statement = select(User).where(User.id == lead.assigned_to_id)
        current_user = session.exec(statement).first()
    else:
        # Create a minimal user-like object for the response
        # We'll just return the lead without enrichment if no user
        current_user = None
    
    if current_user:
        return enrich_lead_response(lead, session, current_user)
    else:
        # Return basic response without enrichment if no user assigned
        # Still check SLA
        sla_badge = check_sla_overdue(lead, session)
        quote_locked = False
        quote_lock_reason = None
        
        # Check quote prerequisites if lead has customer
        if lead.status == LeadStatus.QUALIFIED and lead.customer_id:
            from app.models import Customer
            from app.workflow import check_quote_prerequisites
            statement = select(Customer).where(Customer.id == lead.customer_id)
            customer = session.exec(statement).first()
            if customer:
                can_quote, error = check_quote_prerequisites(customer, session)
                if not can_quote:
                    quote_locked = True
                    quote_lock_reason = error
        
        from app.schemas import CustomerResponse
        customer_response = None
        if lead.customer_id:
            from app.models import Customer
            statement = select(Customer).where(Customer.id == lead.customer_id)
            customer = session.exec(statement).first()
            if customer:
                customer_response = CustomerResponse(
                    id=customer.id,
                    customer_number=customer.customer_number,
                    name=customer.name,
                    email=customer.email,
                    phone=customer.phone,
                    address_line1=customer.address_line1,
                    address_line2=customer.address_line2,
                    city=customer.city,
                    county=customer.county,
                    postcode=customer.postcode,
                    country=customer.country,
                    customer_since=customer.customer_since,
                    created_at=customer.created_at,
                    updated_at=customer.updated_at
                )
        
        return LeadResponse(
            id=lead.id,
            name=lead.name,
            email=lead.email,
            phone=lead.phone,
            postcode=lead.postcode,
            description=lead.description,
            status=lead.status,
            timeframe=lead.timeframe,
            scope_notes=lead.scope_notes,
            product_interest=lead.product_interest,
            lead_type=getattr(lead, 'lead_type', LeadType.UNKNOWN),
            lead_source=getattr(lead, 'lead_source', LeadSource.UNKNOWN),
            assigned_to_id=lead.assigned_to_id,
            customer_id=lead.customer_id,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
            sla_badge=sla_badge,
            quote_locked=quote_locked,
            quote_lock_reason=quote_lock_reason,
            customer=customer_response
        )


@router.post("/twilio/sms")
async def twilio_inbound_sms(request: Request, session: Session = Depends(get_session)):
    """
    Twilio webhook for incoming SMS. No JWT; validated via X-Twilio-Signature.
    Configure in Twilio: A MESSAGE COMES IN -> POST to this URL.
    """
    form = await request.form()
    params = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")
    _, auth_token, _ = get_twilio_config()
    if not auth_token:
        return Response(content="Twilio not configured", status_code=503)

    # Use TWILIO_SMS_WEBHOOK_URL when behind a proxy (e.g. Railway) so signature validation uses the public URL
    url = (os.getenv("TWILIO_SMS_WEBHOOK_URL") or str(request.url)).rstrip("/")
    if not validate_twilio_webhook(url, params, signature, auth_token):
        print("Twilio SMS webhook signature validation failed; set TWILIO_SMS_WEBHOOK_URL if behind a proxy", file=sys.stderr, flush=True)
        return Response(content="Invalid signature", status_code=403)

    from_phone = params.get("From", "")
    to_phone = params.get("To", "")
    body = params.get("Body", "")
    message_sid = params.get("MessageSid", "")
    if not from_phone or not body:
        print("Twilio SMS webhook: missing From or Body in request (params empty or incomplete)", file=sys.stderr, flush=True)
        return Response(content="<Response></Response>", media_type="application/xml")

    from_normalized = normalize_phone(from_phone)
    lead = None

    # Find customer by phone, then lead by phone
    stmt = select(Customer).where(Customer.phone.isnot(None))
    customers = list(session.exec(stmt).all())
    customer = None
    for c in customers:
        if c.phone and normalize_phone(c.phone) == from_normalized:
            customer = c
            break

    if not customer:
        stmt = select(Lead).where(Lead.phone.isnot(None))
        leads = list(session.exec(stmt).all())
        lead = None
        for l in leads:
            if l.phone and normalize_phone(l.phone) == from_normalized:
                lead = l
                break
        if lead and lead.customer_id:
            customer = session.get(Customer, lead.customer_id)
        if not customer and lead:
            # Attach to lead's customer if qualified, else skip storing (MVP: only known customers/leads)
            pass
        if not customer:
            # Unknown number: return 200 so Twilio doesn't retry; don't store
            mask = from_normalized[-4:] if len(from_normalized) >= 4 else "****"
            print(f"Twilio SMS: no customer/lead match for From=...{mask}", file=sys.stderr, flush=True)
            return Response(content="<Response></Response>", media_type="application/xml")

    # If we found only a lead with no customer, we still need a customer_id for SmsMessage.
    if not customer:
        mask = from_normalized[-4:] if len(from_normalized) >= 4 else "****"
        print(f"Twilio SMS: no customer/lead match for From=...{mask}", file=sys.stderr, flush=True)
        return Response(content="<Response></Response>", media_type="application/xml")

    # Resolve a valid user for Activity (avoid FK failure if user id 1 does not exist)
    activity_user_id = None
    try:
        preferred_id = int(os.getenv("TWILIO_ACTIVITY_USER_ID", "1"))
        u = session.get(User, preferred_id)
        if u:
            activity_user_id = u.id
    except (ValueError, TypeError):
        pass
    if activity_user_id is None:
        first_user = session.exec(select(User).limit(1)).first()
        if first_user:
            activity_user_id = first_user.id

    msg = SmsMessage(
        customer_id=customer.id,
        lead_id=lead.id if lead else None,
        direction=SmsDirection.RECEIVED,
        from_phone=from_phone,
        to_phone=to_phone,
        body=body,
        twilio_sid=message_sid,
        received_at=datetime.utcnow(),
    )
    session.add(msg)
    if activity_user_id is not None:
        activity = Activity(
            customer_id=customer.id,
            activity_type=ActivityType.SMS_RECEIVED,
            notes=f"SMS received from {from_phone}: {body[:50]}...",
            created_by_id=activity_user_id,
        )
        session.add(activity)
    print(f"Twilio SMS: stored inbound message for customer_id={customer.id}", file=sys.stderr, flush=True)
    session.commit()

    return Response(content="<Response></Response>", media_type="application/xml")


# --- Facebook Messenger webhook ---

def _get_activity_user_id(session) -> Optional[int]:
    """Resolve a valid user ID for Activity records (e.g. FACEBOOK_ACTIVITY_USER_ID or first user)."""
    try:
        preferred_id = int(os.getenv("FACEBOOK_ACTIVITY_USER_ID", "1"))
        u = session.get(User, preferred_id)
        if u:
            return u.id
    except (ValueError, TypeError):
        pass
    first_user = session.exec(select(User).limit(1)).first()
    return first_user.id if first_user else None


@router.get("/facebook/messenger")
async def facebook_messenger_verify(request: Request):
    """Facebook webhook verification: return hub.challenge if verify_token matches."""
    hub_mode = request.query_params.get("hub.mode")
    hub_verify_token = request.query_params.get("hub.verify_token")
    hub_challenge = request.query_params.get("hub.challenge")
    verify_token = os.getenv("FACEBOOK_VERIFY_TOKEN")
    if not verify_token or hub_mode != "subscribe" or hub_verify_token != verify_token or not hub_challenge:
        raise HTTPException(status_code=403, detail="Verification failed")
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/facebook/messenger")
async def facebook_messenger_webhook(request: Request, session: Session = Depends(get_session)):
    """
    Process incoming Facebook Messenger webhook events.
    Match by messenger_psid (Customer first, then Lead with customer_id); unknown users get Lead + Customer created.
    """
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=200)
    events = parse_webhook_payload(body)
    if not events:
        return Response(status_code=200)
    activity_user_id = _get_activity_user_id(session)
    now = datetime.utcnow()
    for ev in events:
        sender_psid = ev["sender_id"]
        text = ev.get("text", "")
        mid = ev.get("mid")
        if not text:
            continue
        customer = None
        lead = None
        # Match: Customer first by messenger_psid
        stmt = select(Customer).where(Customer.messenger_psid == sender_psid)
        customer = session.exec(stmt).first()
        if not customer:
            stmt = select(Lead).where(Lead.messenger_psid == sender_psid)
            lead = session.exec(stmt).first()
            if lead and lead.customer_id:
                customer = session.get(Customer, lead.customer_id)
        if not customer:
            # Unknown user: create Lead + Customer
            ok, first_name, last_name, err = get_user_profile(sender_psid, get_page_access_token())
            name = " ".join(filter(None, [first_name, last_name])) if (first_name or last_name) else f"Facebook {sender_psid[:8]}"
            from datetime import date
            year = date.today().year
            num_stmt = select(Customer).where(Customer.customer_number.like(f"CUST-{year}-%"))
            existing = list(session.exec(num_stmt).all())
            numbers = []
            for c in existing:
                try:
                    num = int(c.customer_number.split("-")[-1])
                    numbers.append(num)
                except (ValueError, IndexError):
                    continue
            next_num = max(numbers) + 1 if numbers else 1
            customer_number = f"CUST-{year}-{next_num:03d}"
            customer = Customer(
                customer_number=customer_number,
                name=name,
                messenger_psid=sender_psid,
                customer_since=now,
            )
            session.add(customer)
            session.flush()
            lead = Lead(
                name=name,
                lead_source=LeadSource.FACEBOOK,
                messenger_psid=sender_psid,
                customer_id=customer.id,
            )
            session.add(lead)
            session.flush()
        msg = MessengerMessage(
            customer_id=customer.id,
            lead_id=lead.id if lead else None,
            direction=MessengerDirection.RECEIVED,
            from_psid=sender_psid,
            to_psid=None,
            body=text,
            facebook_mid=mid,
            received_at=now,
        )
        session.add(msg)
        if activity_user_id:
            activity = Activity(
                customer_id=customer.id,
                activity_type=ActivityType.MESSENGER_RECEIVED,
                notes=f"Messenger received: {text[:50]}...",
                created_by_id=activity_user_id,
            )
            session.add(activity)
    try:
        session.commit()
    except Exception as e:
        print(f"Facebook Messenger webhook commit error: {e}", file=sys.stderr, flush=True)
        session.rollback()
    return Response(status_code=200)
