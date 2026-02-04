import os
import sys
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlmodel import Session, select
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
)
from app.schemas import LeadCreate, LeadResponse
from app.auth import get_webhook_api_key
from app.workflow import check_sla_overdue
from app.routers.leads import enrich_lead_response
from app.sms_service import validate_twilio_webhook, normalize_phone, get_twilio_config

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
