import os
import sys
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
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
    Product,
    ProductCategory,
)
from app.schemas import LeadCreate, LeadResponse, ProductImportPayload, ProductImportResponse
from app.auth import get_webhook_api_key, get_product_import_api_key
from app.routers.settings import get_company_settings
from app.workflow import check_sla_overdue
from app.routers.leads import enrich_lead_response
from app.sms_service import validate_twilio_webhook, normalize_phone, get_twilio_config
from app.messenger_service import (
    parse_webhook_payload,
    get_user_profile,
    get_page_access_token,
    fetch_leadgen_lead,
)

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


@router.post("/products", response_model=ProductImportResponse)
async def import_product_webhook(
    payload: ProductImportPayload,
    _api_key: str = Depends(get_product_import_api_key),
    session: Session = Depends(get_session),
):
    """
    Create or update a product pushed from the production app.
    Requires Bearer token in Authorization header.
    Upsert: if product_id (Production's ID) provided, match by production_product_id; else match by name.
    Products from production send cost ex VAT; RRP (base_price) is derived using company gross margin % if set.
    """
    # Map payload to Product fields: cost ex VAT from production
    cost_ex_vat = payload.price_ex_vat
    settings = get_company_settings(session)
    margin_pct = getattr(settings, "product_import_gross_margin_pct", None) if settings else None
    if margin_pct is not None and Decimal("0") < margin_pct < Decimal("100"):
        # RRP = Cost / (1 - margin%/100)
        divisor = Decimal("1") - (margin_pct / 100)
        base_price = (cost_ex_vat / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        base_price = cost_ex_vat
    installation_hours = payload.install_hours
    number_of_boxes_int = int(payload.number_of_boxes) if payload.number_of_boxes is not None else 0

    # Upsert: prefer production_product_id if provided, else fall back to name
    existing = None
    if payload.product_id is not None:
        existing = session.exec(
            select(Product).where(Product.production_product_id == payload.product_id)
        ).first()
    if existing is None:
        existing = session.exec(select(Product).where(Product.name == payload.name)).first()

    if existing:
        existing.name = payload.name
        existing.description = payload.description or None
        existing.base_price = base_price
        existing.installation_hours = installation_hours
        existing.boxes_per_product = number_of_boxes_int
        if payload.product_id is not None:
            existing.production_product_id = payload.product_id
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        product = existing
    else:
        product = Product(
            name=payload.name,
            description=payload.description or None,
            category=ProductCategory.STABLES,
            subcategory=None,
            is_extra=False,
            base_price=base_price,
            unit="Unit",
            is_active=True,
            installation_hours=installation_hours,
            boxes_per_product=number_of_boxes_int,
            production_product_id=payload.product_id,
        )
        session.add(product)
        session.commit()
        session.refresh(product)

    return ProductImportResponse(success=True, product_id=str(product.id))


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
            # Phone fallback: get profile (with optional phone), match by normalized phone
            ok, first_name, last_name, profile_phone, err = get_user_profile(sender_psid, get_page_access_token())
            if profile_phone:
                from_normalized = normalize_phone(profile_phone)
                if from_normalized:
                    stmt = select(Customer).where(Customer.phone.isnot(None))
                    for c in session.exec(stmt).all():
                        if c.phone and normalize_phone(c.phone) == from_normalized:
                            customer = c
                            break
                    if not customer:
                        stmt = select(Lead).where(Lead.phone.isnot(None))
                        for l in session.exec(stmt).all():
                            if l.phone and normalize_phone(l.phone) == from_normalized and l.customer_id:
                                lead = l
                                customer = session.get(Customer, l.customer_id)
                                break
                    if customer:
                        customer.messenger_psid = sender_psid
                        session.add(customer)
                        if lead:
                            lead.messenger_psid = sender_psid
                            session.add(lead)
            if not customer:
                # Unknown user: create Lead + Customer
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


# --- Facebook Lead Ads webhook ---

def _parse_leadgen_events(body: dict) -> list[dict]:
    """Extract leadgen events from Meta webhook payload. Returns list of {leadgen_id, page_id, form_id, created_time}."""
    if body.get("object") != "page":
        return []
    events = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            value = change.get("value") or {}
            leadgen_id = value.get("leadgen_id")
            if leadgen_id:
                events.append({
                    "leadgen_id": str(leadgen_id),
                    "page_id": value.get("page_id"),
                    "form_id": value.get("form_id"),
                    "created_time": value.get("created_time"),
                })
    return events


def _leadgen_field_map_to_lead_data(field_map: dict) -> dict:
    """Map Facebook Lead Ad field_data to LeadLock name, email, phone, postcode, description."""
    # Common Meta field names
    name = (
        field_map.get("full_name") or
        " ".join(filter(None, [field_map.get("first_name"), field_map.get("last_name")])) or
        field_map.get("name")
    )
    if not name or not name.strip():
        name = "Facebook Lead"
    email = (field_map.get("email") or "").strip() or None
    phone = (field_map.get("phone_number") or field_map.get("phone") or "").strip() or None
    postcode = (field_map.get("postcode") or field_map.get("zip") or field_map.get("zip_code") or "").strip() or None
    # Use known keys for description; then any remaining custom keys
    known = {"full_name", "first_name", "last_name", "name", "email", "phone_number", "phone", "postcode", "zip", "zip_code", "city", "state"}
    extra = [f"{k}: {v}" for k, v in field_map.items() if k not in known and v]
    description = "\n".join(extra) if extra else None
    return {"name": name.strip(), "email": email, "phone": phone, "postcode": postcode, "description": description}


@router.get("/facebook/leadgen")
async def facebook_leadgen_verify(request: Request):
    """Facebook Lead Ads webhook verification: return hub.challenge if verify_token matches."""
    hub_mode = request.query_params.get("hub.mode")
    hub_verify_token = request.query_params.get("hub.verify_token")
    hub_challenge = request.query_params.get("hub.challenge")
    verify_token = os.getenv("FACEBOOK_VERIFY_TOKEN")
    if not verify_token or hub_mode != "subscribe" or hub_verify_token != verify_token or not hub_challenge:
        raise HTTPException(status_code=403, detail="Verification failed")
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/facebook/leadgen")
async def facebook_leadgen_webhook(request: Request, session: Session = Depends(get_session)):
    """
    Process incoming Facebook Lead Ads webhook events.
    Fetches lead data from Graph API and creates Customer + Lead with lead_source=FACEBOOK.
    """
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=200)
    events = _parse_leadgen_events(body)
    if not events:
        return Response(status_code=200)
    activity_user_id = _get_activity_user_id(session)
    token = get_page_access_token()
    if not token:
        print("Facebook Lead Ads webhook: FACEBOOK_PAGE_ACCESS_TOKEN not set", file=sys.stderr, flush=True)
        return Response(status_code=200)
    from datetime import date
    now = datetime.utcnow()
    year = date.today().year
    for ev in events:
        leadgen_id = ev["leadgen_id"]
        ok, field_map, err = fetch_leadgen_lead(leadgen_id, token)
        if not ok or not field_map:
            print(f"Facebook Lead Ads: failed to fetch lead {leadgen_id}: {err}", file=sys.stderr, flush=True)
            continue
        data = _leadgen_field_map_to_lead_data(field_map)
        # Optionally match existing customer by email or phone
        customer = None
        if data.get("email"):
            stmt = select(Customer).where(Customer.email == data["email"])
            customer = session.exec(stmt).first()
        if not customer and data.get("phone"):
            from app.sms_service import normalize_phone as norm
            stmt = select(Customer).where(Customer.phone.isnot(None))
            for c in session.exec(stmt).all():
                if c.phone and norm(c.phone) == norm(data["phone"]):
                    customer = c
                    break
        if not customer:
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
                name=data["name"],
                email=data.get("email"),
                phone=data.get("phone"),
                postcode=data.get("postcode"),
                customer_since=now,
            )
            session.add(customer)
            session.flush()
        lead = Lead(
            name=data["name"],
            email=data.get("email"),
            phone=data.get("phone"),
            postcode=data.get("postcode"),
            description=data.get("description"),
            lead_source=LeadSource.FACEBOOK,
            customer_id=customer.id,
        )
        session.add(lead)
        session.flush()
        if activity_user_id:
            activity = Activity(
                customer_id=customer.id,
                activity_type=ActivityType.NOTE,
                notes="Lead from Facebook Lead Ad form",
                created_by_id=activity_user_id,
            )
            session.add(activity)
            status_history = StatusHistory(
                lead_id=lead.id,
                new_status=LeadStatus.NEW,
                changed_by_id=activity_user_id,
            )
            session.add(status_history)
    try:
        session.commit()
    except Exception as e:
        print(f"Facebook Lead Ads webhook commit error: {e}", file=sys.stderr, flush=True)
        session.rollback()
    return Response(status_code=200)
