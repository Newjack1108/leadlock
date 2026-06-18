from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select
from app.database import get_session
from app.models import CompanySettings, User
from app.auth import get_current_user, require_role
from app.bank_details_crypto import (
    build_masked_bank_response,
    decrypt_bank_value,
    encrypt_bank_value,
    prepare_bank_fields_for_save,
)
from app.schemas import (
    CompanySettingsCreate, CompanySettingsUpdate, CompanySettingsResponse,
    CompanySettingsBankDetailsRevealResponse,
    UserEmailSettingsUpdate, UserEmailSettingsResponse
)
from app.models import UserRole
from app.customer_import_export import (
    generate_example_csv,
    import_customers_from_csv,
    export_customers_to_csv,
)
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

MAX_IMPORT_SIZE_BYTES = 5 * 1024 * 1024  # 5MB


def get_company_settings(session: Session) -> CompanySettings:
    """Get or create the singleton company settings."""
    statement = select(CompanySettings)
    settings = session.exec(statement).first()
    return settings


BANK_DETAIL_FIELDS = ("bank_name", "bank_account_name", "account_number", "sort_code")


def _company_settings_response(settings: CompanySettings, current_user: User) -> CompanySettingsResponse:
    data = settings.dict()
    if current_user.role != UserRole.DIRECTOR:
        for field in BANK_DETAIL_FIELDS:
            data.pop(field, None)
        data["account_number_set"] = False
        data["sort_code_set"] = False
        return CompanySettingsResponse(**data)

    masked_account, masked_sort, account_set, sort_set = build_masked_bank_response(settings)
    data["account_number"] = masked_account
    data["sort_code"] = masked_sort
    data["account_number_set"] = account_set
    data["sort_code_set"] = sort_set
    return CompanySettingsResponse(**data)


def _apply_company_settings_create_data(settings_data: CompanySettingsCreate) -> dict:
    data = settings_data.dict()
    for field in ("account_number", "sort_code"):
        if field in data:
            data[field] = encrypt_bank_value(data.get(field))
    return data


@router.get("/company", response_model=CompanySettingsResponse)
async def get_company_settings_endpoint(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get company settings. All authenticated users can view. Bank details are excluded for non-DIRECTORs."""
    settings = get_company_settings(session)
    
    if not settings:
        raise HTTPException(status_code=404, detail="Company settings not found. Please create them first.")

    return _company_settings_response(settings, current_user)


@router.get("/company/bank-details", response_model=CompanySettingsBankDetailsRevealResponse)
async def reveal_company_bank_details(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    """Return decrypted bank account number and sort code. DIRECTOR only."""
    settings = get_company_settings(session)
    if not settings:
        raise HTTPException(status_code=404, detail="Company settings not found. Please create them first.")

    logger.info("Bank details revealed by user_id=%s", current_user.id)
    return CompanySettingsBankDetailsRevealResponse(
        account_number=decrypt_bank_value(settings.account_number),
        sort_code=decrypt_bank_value(settings.sort_code),
    )


@router.post("/company", response_model=CompanySettingsResponse)
async def create_company_settings(
    settings_data: CompanySettingsCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Create company settings. DIRECTOR only. Only works if none exist."""
    existing = get_company_settings(session)
    if existing:
        raise HTTPException(status_code=400, detail="Company settings already exist. Use PUT to update.")
    
    settings = CompanySettings(
        **_apply_company_settings_create_data(settings_data),
        updated_by_id=current_user.id,
    )
    session.add(settings)
    session.commit()
    session.refresh(settings)

    return _company_settings_response(settings, current_user)


@router.put("/company", response_model=CompanySettingsResponse)
async def update_company_settings(
    settings_data: CompanySettingsUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Update company settings. DIRECTOR only."""
    settings = get_company_settings(session)
    
    if not settings:
        raise HTTPException(status_code=404, detail="Company settings not found. Use POST to create them first.")
    
    update_data = prepare_bank_fields_for_save(
        settings_data.dict(exclude_unset=True),
        settings,
    )
    for field, value in update_data.items():
        setattr(settings, field, value)

    settings.updated_by_id = current_user.id
    settings.updated_at = datetime.utcnow()
    session.add(settings)
    session.commit()
    session.refresh(settings)

    return _company_settings_response(settings, current_user)


@router.get("/user/email", response_model=UserEmailSettingsResponse)
async def get_user_email_settings(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get current user's email settings."""
    return UserEmailSettingsResponse(
        smtp_host=current_user.smtp_host,
        smtp_port=current_user.smtp_port,
        smtp_user=current_user.smtp_user,
        smtp_use_tls=current_user.smtp_use_tls,
        smtp_from_email=current_user.smtp_from_email,
        smtp_from_name=current_user.smtp_from_name,
        imap_host=current_user.imap_host,
        imap_port=current_user.imap_port,
        imap_user=current_user.imap_user,
        imap_use_ssl=current_user.imap_use_ssl,
        email_signature=current_user.email_signature,
        email_test_mode=getattr(current_user, 'email_test_mode', False)
    )


@router.put("/user/email", response_model=UserEmailSettingsResponse)
async def update_user_email_settings(
    settings_data: UserEmailSettingsUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update current user's email settings. Users can only update their own."""
    try:
        update_data = settings_data.dict(exclude_unset=True)
        
        # Update only provided fields
        for field, value in update_data.items():
            if hasattr(current_user, field):
                setattr(current_user, field, value)
        
        current_user.updated_at = datetime.utcnow()
        session.add(current_user)
        session.commit()
        session.refresh(current_user)
    except Exception as e:
        session.rollback()
        err_msg = str(e)
        if "email_test_mode" in err_msg.lower() or "column" in err_msg.lower():
            raise HTTPException(
                status_code=500,
                detail="Email settings column may be missing. Try restarting the API to run migrations."
            )
        raise HTTPException(status_code=500, detail=f"Failed to save email settings: {err_msg}")
    
    return UserEmailSettingsResponse(
        smtp_host=current_user.smtp_host,
        smtp_port=current_user.smtp_port,
        smtp_user=current_user.smtp_user,
        smtp_use_tls=current_user.smtp_use_tls,
        smtp_from_email=current_user.smtp_from_email,
        smtp_from_name=current_user.smtp_from_name,
        imap_host=current_user.imap_host,
        imap_port=current_user.imap_port,
        imap_user=current_user.imap_user,
        imap_use_ssl=current_user.imap_use_ssl,
        email_signature=current_user.email_signature,
        email_test_mode=getattr(current_user, 'email_test_mode', False)
    )


@router.get("/customers/import-example")
async def get_customer_import_example(
    current_user: User = Depends(get_current_user)
):
    """Download an example CSV template for customer import. All authenticated users."""
    content = generate_example_csv()
    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=customer-import-example.csv"
        }
    )


@router.post("/customers/import")
async def import_customers(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Import customers from CSV. DIRECTOR only."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")
    content = await file.read()
    if len(content) > MAX_IMPORT_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")
    created, skipped, errors = import_customers_from_csv(
        text, session, skip_duplicates=True
    )
    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


@router.get("/customers/export")
async def export_customers(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Export all customers to CSV. All authenticated users."""
    content = export_customers_to_csv(session)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=customers-export-{date_str}.csv"
        }
    )
