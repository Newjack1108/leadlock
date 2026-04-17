import asyncio
import pytest
from fastapi import HTTPException

from app.auth import require_dealer_user
from app.models import User, UserRole


def test_require_dealer_user_accepts_valid_dealer():
    user = User(
        id=1,
        email="dealer@example.com",
        hashed_password="x",
        full_name="Dealer User",
        role=UserRole.DEALER_USER,
        dealer_id=99,
        dealer_commission_pct=10,
    )
    result = asyncio.run(require_dealer_user(current_user=user))
    assert result.id == 1


def test_require_dealer_user_rejects_invalid_commission():
    user = User(
        id=1,
        email="dealer@example.com",
        hashed_password="x",
        full_name="Dealer User",
        role=UserRole.DEALER_USER,
        dealer_id=99,
        dealer_commission_pct=12,
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_dealer_user(current_user=user))
    assert exc.value.status_code == 400
