"""Dashboard won/lost/closed counts come from quote actions, not lead status."""
import asyncio
import os
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import Lead, LeadStatus, LossCategory, Quote, QuoteStatus, User, UserRole
from app.routers.dashboard import get_dashboard_stats


def _engine():
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_dashboard_won_lost_closed_use_quote_actions():
    engine = _engine()
    in_range = datetime(2026, 6, 10, 12, 0, 0)
    out_of_range = datetime(2026, 5, 1, 12, 0, 0)

    with Session(engine) as session:
        user = User(
            email="dash-won-lost@example.com",
            hashed_password="x",
            full_name="Dash User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        lead_status_won = Lead(name="Lead Status Won", status=LeadStatus.WON, created_at=in_range)
        lead_closed = Lead(name="Lead Status Closed", status=LeadStatus.CLOSED, created_at=in_range)
        lead_a = Lead(name="Alice", status=LeadStatus.QUOTED, created_at=out_of_range)
        lead_b = Lead(name="Bob", status=LeadStatus.NEW, created_at=out_of_range)
        lead_c = Lead(name="Carol", status=LeadStatus.NEW, created_at=out_of_range)
        session.add(lead_status_won)
        session.add(lead_closed)
        session.add(lead_a)
        session.add(lead_b)
        session.add(lead_c)
        session.commit()
        for lead in (lead_status_won, lead_closed, lead_a, lead_b, lead_c):
            session.refresh(lead)

        session.add(
            Quote(
                quote_number="QT-DASH-WON",
                status=QuoteStatus.ACCEPTED,
                subtotal=Decimal("1000"),
                total_amount=Decimal("1000"),
                created_by_id=user.id,
                lead_id=lead_a.id,
                accepted_at=in_range,
                created_at=out_of_range,
                sent_at=out_of_range,
            )
        )
        # Mark Lost: REJECTED + loss_category
        session.add(
            Quote(
                quote_number="QT-DASH-LOST",
                status=QuoteStatus.REJECTED,
                subtotal=Decimal("800"),
                total_amount=Decimal("800"),
                created_by_id=user.id,
                lead_id=lead_b.id,
                loss_category=LossCategory.PRICE,
                loss_reason="Too expensive",
                created_at=out_of_range,
                sent_at=out_of_range,
                updated_at=in_range,
            )
        )
        # Close quote: REJECTED without loss_category
        session.add(
            Quote(
                quote_number="QT-DASH-CLOSED",
                status=QuoteStatus.REJECTED,
                subtotal=Decimal("600"),
                total_amount=Decimal("600"),
                created_by_id=user.id,
                lead_id=lead_c.id,
                created_at=out_of_range,
                sent_at=out_of_range,
                updated_at=in_range,
            )
        )
        session.add(
            Quote(
                quote_number="QT-DASH-OLD-WON",
                status=QuoteStatus.ACCEPTED,
                subtotal=Decimal("5000"),
                total_amount=Decimal("5000"),
                created_by_id=user.id,
                lead_id=lead_status_won.id,
                accepted_at=out_of_range,
                created_at=out_of_range,
                sent_at=out_of_range,
            )
        )
        session.commit()

        stats = asyncio.run(
            get_dashboard_stats(
                session=session,
                current_user=SimpleNamespace(role=UserRole.DIRECTOR),
                period=None,
                start_date="2026-06-08",
                end_date="2026-06-12",
            )
        )

    assert stats.won_count == 1
    assert stats.lost_count == 1
    assert stats.closed_count == 1
