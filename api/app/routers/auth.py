from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.database import get_session
from app.models import User, UserRole
from app.auth import (
    verify_password,
    create_access_token,
    get_current_user,
    get_password_hash,
    has_configurator_access,
)
from app.system_user_service import system_user_email
from app.schemas import Token, UserLogin, UserResponse, BootstrapCreate, LoginQuoteResponse
from app.login_quote_service import generate_login_quote
from datetime import timedelta

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _build_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        can_access_configurator=has_configurator_access(user),
    )


@router.post("/bootstrap", response_model=UserResponse)
async def bootstrap(data: BootstrapCreate, session: Session = Depends(get_session)):
    """Create the first director when no users exist. No auth required. Locked once any user exists."""
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
async def login(credentials: UserLogin, session: Session = Depends(get_session)):
    if credentials.email.strip().lower() == system_user_email():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    statement = select(User).where(User.email == credentials.email)
    user = session.exec(statement).first()
    
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
    
    access_token_expires = timedelta(minutes=1440)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return _build_user_response(current_user)


@router.get("/login-quote", response_model=LoginQuoteResponse)
async def get_login_quote(current_user: User = Depends(get_current_user)):
    quote, source = await generate_login_quote()
    return {"quote": quote, "source": source}
