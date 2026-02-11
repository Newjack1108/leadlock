from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from app.database import get_session
from app.models import Order, OrderItem, Customer
from app.auth import get_current_user
from app.schemas import OrderResponse, OrderItemResponse, OrderUpdate
from app.models import User

router = APIRouter(prefix="/api/orders", tags=["orders"])


def build_order_response(order: Order, order_items: List[OrderItem], session: Session) -> OrderResponse:
    """Build OrderResponse with items and optional customer_name."""
    customer_name = None
    if order.customer_id:
        customer = session.exec(select(Customer).where(Customer.id == order.customer_id)).first()
        customer_name = customer.name if customer else None
    return OrderResponse(
        id=order.id,
        quote_id=order.quote_id,
        customer_id=order.customer_id,
        customer_name=customer_name,
        order_number=order.order_number,
        subtotal=order.subtotal,
        discount_total=order.discount_total,
        total_amount=order.total_amount,
        deposit_amount=order.deposit_amount,
        balance_amount=order.balance_amount,
        currency=order.currency,
        terms_and_conditions=order.terms_and_conditions,
        notes=order.notes,
        created_by_id=order.created_by_id,
        created_at=order.created_at,
        deposit_paid=order.deposit_paid,
        balance_paid=order.balance_paid,
        paid_in_full=order.paid_in_full,
        installation_booked=order.installation_booked,
        installation_completed=order.installation_completed,
        items=[
            OrderItemResponse(
                id=item.id,
                order_id=item.order_id,
                quote_item_id=item.quote_item_id,
                product_id=item.product_id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
                discount_amount=item.discount_amount,
                final_line_total=item.final_line_total,
                sort_order=item.sort_order,
                is_custom=item.is_custom,
            )
            for item in order_items
        ],
    )


@router.get("", response_model=List[OrderResponse])
async def list_orders(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List all orders (newest first)."""
    statement = select(Order).order_by(Order.created_at.desc())
    orders = session.exec(statement).all()
    result = []
    for order in orders:
        items = session.exec(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.sort_order)
        ).all()
        result.append(build_order_response(order, list(items), session))
    return result


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get a single order by id."""
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    items = session.exec(
        select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.sort_order)
    ).all()
    return build_order_response(order, list(items), session)


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: int,
    order_data: OrderUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update order status fields (deposit_paid, balance_paid, etc.)."""
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    update_dict = order_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(order, field, value)
    session.add(order)
    session.commit()
    session.refresh(order)
    items = session.exec(
        select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.sort_order)
    ).all()
    return build_order_response(order, list(items), session)
