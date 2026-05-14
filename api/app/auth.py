from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select
from app.database import get_session
from app.models import User, UserRole
import os

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_email(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _env_csv(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {_normalize_email(item) for item in raw.split(",") if _normalize_email(item)}


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    statement = select(User).where(User.email == email)
    user = session.exec(statement).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise credentials_exception
    return user


def require_role(allowed_roles: list[UserRole]):
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    return role_checker


async def require_dealer_user(current_user: User = Depends(get_current_user)) -> User:
    allowed = {UserRole.DEALER_ADMIN, UserRole.DEALER_USER}
    if current_user.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dealer access only",
        )
    if current_user.dealer_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dealer account is not linked to a dealer",
        )
    if current_user.dealer_commission_pct not in (10, 15):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dealer commission must be 10 or 15",
        )
    return current_user


async def require_non_dealer_user(current_user: User = Depends(get_current_user)) -> User:
    """Dealers use the dealer portal only; block staff dashboard and related APIs."""
    if current_user.role in (UserRole.DEALER_ADMIN, UserRole.DEALER_USER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dashboard is not available for dealer accounts",
        )
    return current_user


def has_configurator_access(user: User) -> bool:
    if not _env_bool("CONFIGURATOR_ENABLED", default=False):
        return False
    if user.role in (UserRole.DEALER_ADMIN, UserRole.DEALER_USER):
        return False
    if _env_bool("CONFIGURATOR_ALLOW_DIRECTOR_OVERRIDE", default=False) and user.role == UserRole.DIRECTOR:
        return True
    allowed_emails = _env_csv("CONFIGURATOR_ALLOWED_EMAILS")
    return _normalize_email(user.email) in allowed_emails


async def require_configurator_access(current_user: User = Depends(get_current_user)) -> User:
    if not has_configurator_access(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Configurator access is not enabled for this account",
        )
    return current_user


def get_webhook_api_key(api_key: str = Header(None, alias="X-API-Key")) -> str:
    """Validate webhook API key from header."""
    expected_key = os.getenv("WEBHOOK_API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook API key not configured"
        )
    if api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    return api_key


def get_product_import_api_key(authorization: Optional[str] = Header(None, alias="Authorization")) -> str:
    """Validate Bearer token in Authorization header against product import API key."""
    expected_key = os.getenv("PRODUCT_IMPORT_API_KEY") or os.getenv("WEBHOOK_API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Product import API key not configured"
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()  # Remove "Bearer " prefix
    if token != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token
