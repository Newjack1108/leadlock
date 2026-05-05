from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import require_role
from app.database import get_session
from app.models import (
    Dealer,
    DealerAllowedDiscount,
    DealerDiscountPolicy,
    DiscountTemplate,
    User,
    UserRole,
)
from app.schemas import DealerDiscountPolicyAdminResponse, DealerDiscountPolicyAdminUpdate, DealerSummaryResponse

router = APIRouter(prefix="/api/settings/dealers", tags=["settings-dealers"])


def _get_dealer_or_404(session: Session, dealer_id: int) -> Dealer:
    dealer = session.get(Dealer, dealer_id)
    if not dealer or not dealer.is_active:
        raise HTTPException(status_code=404, detail="Dealer not found")
    return dealer


@router.get("", response_model=List[DealerSummaryResponse])
async def list_dealers_for_settings(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    del current_user  # role guard only
    dealers = session.exec(select(Dealer).where(Dealer.is_active == True).order_by(Dealer.name.asc())).all()
    return [
        DealerSummaryResponse(
            id=dealer.id,
            name=dealer.name,
            company_name=dealer.company_name,
            is_active=dealer.is_active,
        )
        for dealer in dealers
    ]


@router.get("/{dealer_id}/discount-policy", response_model=DealerDiscountPolicyAdminResponse)
async def get_dealer_discount_policy_for_admin(
    dealer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    del current_user  # role guard only
    _get_dealer_or_404(session, dealer_id)

    policy = session.exec(
        select(DealerDiscountPolicy).where(DealerDiscountPolicy.dealer_id == dealer_id)
    ).first()
    allowed_ids = list(
        session.exec(
            select(DealerAllowedDiscount.discount_template_id).where(
                DealerAllowedDiscount.dealer_id == dealer_id
            )
        ).all()
    )
    if policy is None:
        default_mode = DealerDiscountPolicy.model_fields["mode"].default
        return DealerDiscountPolicyAdminResponse(
            dealer_id=dealer_id,
            mode=default_mode,
            allow_fixed_amount=False,
            allow_percentage=False,
            max_discount_percentage=None,
            max_discount_amount=None,
            allowed_discount_template_ids=allowed_ids,
        )
    return DealerDiscountPolicyAdminResponse(
        dealer_id=dealer_id,
        mode=policy.mode,
        allow_fixed_amount=policy.allow_fixed_amount,
        allow_percentage=policy.allow_percentage,
        max_discount_percentage=policy.max_discount_percentage,
        max_discount_amount=policy.max_discount_amount,
        allowed_discount_template_ids=allowed_ids,
    )


@router.put("/{dealer_id}/discount-policy", response_model=DealerDiscountPolicyAdminResponse)
async def upsert_dealer_discount_policy_for_admin(
    dealer_id: int,
    payload: DealerDiscountPolicyAdminUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    del current_user  # role guard only
    _get_dealer_or_404(session, dealer_id)

    requested_ids = list(dict.fromkeys(payload.allowed_discount_template_ids))
    if requested_ids:
        existing_ids = set(
            session.exec(select(DiscountTemplate.id).where(DiscountTemplate.id.in_(requested_ids))).all()
        )
        missing_ids = [template_id for template_id in requested_ids if template_id not in existing_ids]
        if missing_ids:
            raise HTTPException(status_code=404, detail=f"Discount template(s) not found: {missing_ids}")

    policy = session.exec(
        select(DealerDiscountPolicy).where(DealerDiscountPolicy.dealer_id == dealer_id)
    ).first()
    if not policy:
        policy = DealerDiscountPolicy(
            dealer_id=dealer_id,
            mode=payload.mode,
            allow_fixed_amount=payload.allow_fixed_amount,
            allow_percentage=payload.allow_percentage,
            max_discount_percentage=payload.max_discount_percentage,
            max_discount_amount=payload.max_discount_amount,
        )
    else:
        policy.mode = payload.mode
        policy.allow_fixed_amount = payload.allow_fixed_amount
        policy.allow_percentage = payload.allow_percentage
        policy.max_discount_percentage = payload.max_discount_percentage
        policy.max_discount_amount = payload.max_discount_amount
        policy.updated_at = datetime.utcnow()
    session.add(policy)

    existing_links = session.exec(
        select(DealerAllowedDiscount).where(DealerAllowedDiscount.dealer_id == dealer_id)
    ).all()
    for link in existing_links:
        session.delete(link)
    for template_id in requested_ids:
        session.add(DealerAllowedDiscount(dealer_id=dealer_id, discount_template_id=template_id))

    session.commit()
    session.refresh(policy)
    return DealerDiscountPolicyAdminResponse(
        dealer_id=dealer_id,
        mode=policy.mode,
        allow_fixed_amount=policy.allow_fixed_amount,
        allow_percentage=policy.allow_percentage,
        max_discount_percentage=policy.max_discount_percentage,
        max_discount_amount=policy.max_discount_amount,
        allowed_discount_template_ids=requested_ids,
    )
