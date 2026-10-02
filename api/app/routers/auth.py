"""Auth routes: login, bootstrap, session cookie, and current user."""
from datetime import timedelta
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_user_base,
    get_password_hash,
    has_configurator_access,
    effective_on_leave,
)
from app.auth_cookies import clear_auth_cookie, set_auth_cookie
from app.database import DATABASE_URL, get_session
from app.db_utils import scalar_int
from app.login_quote_service import generate_login_quote
from app.models import Customer, Lead, User, UserRole
from app.rate_limit import enforce_rate_limit
from app.schemas import Token, UserLogin, UserResponse, BootstrapCreate, LoginQuoteResponse
from app.system_user_service import system_user_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _build_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        can_access_configurator=has_configurator_access(user),
        on_leave=bool(getattr(user, "on_leave", False)),
        leave_until=getattr(user, "leave_until", None),
    )


def _require_bootstrap_allowed(
    request: Request,
    x_bootstrap_secret: str | None = Header(None, alias="X-Bootstrap-Secret"),
) -> None:
    """Bootstrap is disabled on Railway unless BOOTSTRAP_SECRET matches.

    Locally, BOOTSTRAP_SECRET is optional; when set it must match the header.
    """
    import hmac

    enforce_rate_limit(request, scope="auth-bootstrap", max_requests=5, window_seconds=300)
    expected = (os.getenv("BOOTSTRAP_SECRET") or "").strip()
    on_railway = bool(os.getenv("RAILWAY_ENVIRONMENT"))
    if on_railway and not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap is disabled in this environment",
        )
    if expected and (
        not x_bootstrap_secret or not hmac.compare_digest(x_bootstrap_secret, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bootstrap secret",
        )


@router.post("/bootstrap", response_model=UserResponse)
async def bootstrap(
    data: BootstrapCreate,
    request: Request,
    session: Session = Depends(get_session),
    _: None = Depends(_require_bootstrap_allowed),
):
    """Create the first director when no users exist. Locked once any user exists."""
    existing = session.exec(select(User)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Users already exist. Bootstrap is only available when the database has no users.",
        )
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=get_password_hash(data.password),
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _build_user_response(user)


@router.post("/login", response_model=Token)
def login(
    credentials: UserLogin,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    enforce_rate_limit(request, scope="auth-login", max_requests=20, window_seconds=60)
    if credentials.email.strip().lower() == system_user_email():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    email = credentials.email.strip()
    email_key = email.lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        user = session.exec(select(User).where(func.lower(User.email) == email_key)).first()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires,
        token_version=int(getattr(user, "token_version", 0) or 0),
    )
    set_auth_cookie(response, access_token, max_age_seconds=ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(response: Response):
    clear_auth_cookie(response)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user_base),
    session: Session = Depends(get_session),
):
    # Re-evaluate leave (auto-clear) so the client sees accurate status
    effective_on_leave(current_user, session)
    return _build_user_response(current_user)


@router.get("/data-summary")
def get_data_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Row counts from the database this API instance uses (for diagnosing empty UI).
    """
    from urllib.parse import urlparse

    def _count(model, *conditions):
        stmt = select(func.count()).select_from(model)
        for cond in conditions:
            stmt = stmt.where(cond)
        return scalar_int(session.exec(stmt).one())

    db_host = urlparse(DATABASE_URL.replace("postgres://", "postgresql://", 1)).hostname
    return {
        "customers": _count(Customer),
        "leads": _count(Lead),
        "leads_not_archived": _count(Lead, Lead.archived_at.is_(None)),
        "users": _count(User),
        "database_host": db_host,
        "use_public_database_url": os.getenv("DATABASE_USE_PUBLIC", "")
            .strip()
            .lower()
            in ("1", "true", "yes"),
    }


@router.get("/login-quote", response_model=LoginQuoteResponse)
async def get_login_quote(current_user: User = Depends(get_current_user)):
    quote, source = await generate_login_quote()
    return {"quote": quote, "source": source}
