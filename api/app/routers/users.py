from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.database import get_session
from app.models import User, UserRole
from app.auth import get_current_user, require_role, get_password_hash
from app.schemas import (
    UserCreate,
    UserUpdate,
    UserListResponse,
    AssignableUserResponse,
    SystemAttributionBackfillRequest,
    SystemAttributionBackfillResponse,
)
from app.system_attribution_service import backfill_system_attribution
from app.system_user_service import (
    get_system_user_id,
    has_reserved_system_name,
    is_system_user,
    is_system_user_email,
    system_user_email,
)

router = APIRouter(prefix="/api/users", tags=["users"])


def _user_to_response(user: User) -> UserListResponse:
    return UserListResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        dealer_id=user.dealer_id,
        dealer_commission_pct=user.dealer_commission_pct,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _validate_dealer_user_payload(data: UserCreate | UserUpdate) -> None:
    role = getattr(data, "role", None)
    dealer_id = getattr(data, "dealer_id", None)
    commission = getattr(data, "dealer_commission_pct", None)
    if role in (UserRole.DEALER_ADMIN, UserRole.DEALER_USER):
        if dealer_id is None:
            raise HTTPException(status_code=400, detail="dealer_id is required for dealer users")
        if commission not in (10, 15):
            raise HTTPException(status_code=400, detail="dealer_commission_pct must be 10 or 15")


def _validate_not_reserved_system_identity(data: UserCreate | UserUpdate) -> None:
    email = getattr(data, "email", None)
    if is_system_user_email(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{system_user_email()} is reserved for the internal System account",
        )
    full_name = getattr(data, "full_name", None)
    if has_reserved_system_name(full_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The name 'System' is reserved for the internal System account",
        )


def _ensure_user_is_manageable(user: User) -> None:
    if is_system_user(user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The internal System account is managed automatically and cannot be changed here",
        )


@router.get("", response_model=list[UserListResponse])
async def list_users(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    """List all users. DIRECTOR only."""
    statement = select(User).where(User.email != system_user_email())
    users = session.exec(statement).all()
    return [_user_to_response(u) for u in users]


@router.get("/assignable", response_model=list[AssignableUserResponse])
async def list_assignable_users(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Active users for task assignee picker (any authenticated user)."""
    statement = select(User).where(User.is_active == True).order_by(User.full_name)  # noqa: E712
    users = session.exec(statement).all()
    return [
        AssignableUserResponse(id=u.id, full_name=u.full_name, email=u.email)
        for u in users
    ]


@router.post("", response_model=UserListResponse)
async def create_user(
    data: UserCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    """Create a new user. DIRECTOR only."""
    _validate_not_reserved_system_identity(data)
    existing = session.exec(select(User).where(User.email == data.email)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists",
        )
    _validate_dealer_user_payload(data)
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=get_password_hash(data.password),
        role=data.role,
        dealer_id=data.dealer_id,
        dealer_commission_pct=data.dealer_commission_pct,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_to_response(user)


@router.post("/system-attribution/backfill", response_model=SystemAttributionBackfillResponse)
async def backfill_system_user_attribution(
    payload: SystemAttributionBackfillRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    """Reassign clearly automated historical rows from a human user to the internal System account."""
    del current_user  # role guard only
    source_user: User | None
    if payload.user_id is not None:
        source_user = session.get(User, payload.user_id)
    else:
        source_user = session.exec(select(User).where(User.email == payload.email)).first()
    if not source_user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_user_is_manageable(source_user)

    try:
        result = backfill_system_attribution(
            session,
            source_user=source_user,
            system_user_id=get_system_user_id(session),
            dry_run=payload.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SystemAttributionBackfillResponse(
        source_user_id=result.source_user_id,
        source_email=result.source_email,
        source_full_name=result.source_full_name,
        system_user_id=result.system_user_id,
        dry_run=result.dry_run,
        activities_updated=result.activities_updated,
        emails_updated=result.emails_updated,
        sms_messages_updated=result.sms_messages_updated,
        status_history_updated=result.status_history_updated,
        total_updated=result.total_updated,
    )


@router.get("/{user_id}", response_model=UserListResponse)
async def get_user(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    """Get a single user. DIRECTOR only."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_user_is_manageable(user)
    return _user_to_response(user)


@router.put("/{user_id}", response_model=UserListResponse)
async def update_user(
    user_id: int,
    data: UserUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    """Update a user. DIRECTOR only."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_user_is_manageable(user)
    _validate_not_reserved_system_identity(data)
    _validate_dealer_user_payload(data)
    update_data = data.dict(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    for field, value in update_data.items():
        setattr(user, field, value)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_to_response(user)


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    """Soft-deactivate a user. DIRECTOR only."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_user_is_manageable(user)
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )
    user.is_active = False
    session.add(user)
    session.commit()
    return {"message": "User deactivated"}
