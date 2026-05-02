"""resolve_sms_to_phone prefers explicit and customer, then lead(s)."""
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.models import Customer, Lead, LeadType, User, UserRole
from app.sms_service import resolve_sms_to_phone


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_explicit_to_wins_over_empty_customer():
    with _session() as session:
        u = User(
            email="a@b.c",
            full_name="A",
            hashed_password="x",
            role=UserRole.DIRECTOR,
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        c = Customer(customer_number="C-1", name="Cust")
        session.add(c)
        session.commit()
        session.refresh(c)
        assert resolve_sms_to_phone(session, c, explicit_to="07123456789") == "07123456789"


def test_lead_phone_when_customer_blank():
    with _session() as session:
        u = User(
            email="a@b.c",
            full_name="A",
            hashed_password="x",
            role=UserRole.DIRECTOR,
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        c = Customer(customer_number="C-2", name="Cust")
        session.add(c)
        session.commit()
        session.refresh(c)
        lead = Lead(
            name="L",
            phone="07987654321",
            lead_type=LeadType.UNKNOWN,
            customer_id=c.id,
        )
        session.add(lead)
        session.commit()
        assert resolve_sms_to_phone(session, c) == "07987654321"


def test_lead_id_pins_destination_when_multiple_leads():
    with _session() as session:
        u = User(
            email="a@b.c",
            full_name="A",
            hashed_password="x",
            role=UserRole.DIRECTOR,
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        c = Customer(customer_number="C-3", name="Cust")
        session.add(c)
        session.commit()
        session.refresh(c)
        lead_a = Lead(
            name="A",
            phone="07000000001",
            lead_type=LeadType.UNKNOWN,
            customer_id=c.id,
        )
        lead_b = Lead(
            name="B",
            phone="07000000002",
            lead_type=LeadType.UNKNOWN,
            customer_id=c.id,
        )
        session.add(lead_a)
        session.add(lead_b)
        session.commit()
        session.refresh(lead_a)
        session.refresh(lead_b)
        assert resolve_sms_to_phone(session, c, lead_id=lead_a.id) == "07000000001"
        assert resolve_sms_to_phone(session, c, lead_id=lead_b.id) == "07000000002"
