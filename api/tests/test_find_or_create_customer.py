"""Customer auto-link: email+phone, or name plus one contact field; conflicts create new."""
import uuid

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Customer, Lead, LeadStatus
from app.routers.leads import find_linkable_customer, find_or_create_customer


def _engine():
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _add_customer(session: Session, **kwargs) -> Customer:
    customer = Customer(
        customer_number=f"CUST-{uuid.uuid4().hex[:8]}",
        **kwargs,
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


def test_links_when_normalized_phone_and_name_agree():
    engine = _engine()
    with Session(engine) as session:
        existing = _add_customer(session, name="Alex", phone="+447700900456", email=None)
        lead = Lead(name="Alex", phone="07700900456", email=None, status=LeadStatus.NEW)
        customer = find_or_create_customer(lead, session)
        assert customer.id == existing.id


def test_links_when_email_and_phone_agree_even_if_name_differs():
    engine = _engine()
    with Session(engine) as session:
        existing = _add_customer(
            session,
            name="Old Name",
            email="same@example.com",
            phone="+447700900111",
        )
        lead = Lead(
            name="New Name",
            email="same@example.com",
            phone="07700900111",
            status=LeadStatus.NEW,
        )
        customer = find_or_create_customer(lead, session)
        assert customer.id == existing.id


def test_links_when_name_and_email_agree_without_phone():
    engine = _engine()
    with Session(engine) as session:
        existing = _add_customer(session, name="Pat Jones", email="pat@example.com", phone=None)
        lead = Lead(name="pat  jones", email="Pat@example.com", phone=None, status=LeadStatus.NEW)
        customer = find_or_create_customer(lead, session)
        assert customer.id == existing.id


def test_links_when_name_and_email_agree_and_lead_has_no_phone():
    engine = _engine()
    with Session(engine) as session:
        existing = _add_customer(
            session,
            name="Sam Lee",
            email="sam@example.com",
            phone="+447700900222",
        )
        lead = Lead(name="Sam Lee", email="sam@example.com", phone=None, status=LeadStatus.NEW)
        customer = find_or_create_customer(lead, session)
        assert customer.id == existing.id


def test_creates_new_when_name_and_phone_agree_but_emails_conflict():
    engine = _engine()
    with Session(engine) as session:
        existing = _add_customer(
            session,
            name="Alex",
            email="old@example.com",
            phone="+447700900456",
        )
        lead = Lead(
            name="Alex",
            email="new@example.com",
            phone="07700900456",
            status=LeadStatus.NEW,
        )
        customer = find_or_create_customer(lead, session)
        assert customer.id != existing.id
        assert customer.email == "new@example.com"


def test_creates_new_when_only_phone_matches_and_name_email_differ():
    engine = _engine()
    with Session(engine) as session:
        existing = _add_customer(
            session,
            name="Old Customer",
            email="old@example.com",
            phone="+447700900456",
        )
        lead = Lead(
            name="New Person",
            email="new@example.com",
            phone="07700900456",
            status=LeadStatus.NEW,
        )
        customer = find_or_create_customer(lead, session)
        assert customer.id != existing.id
        assert customer.name == "New Person"
        count = session.exec(select(Customer)).all()
        assert len(count) == 2


def test_creates_new_when_only_email_matches_and_name_phone_differ():
    engine = _engine()
    with Session(engine) as session:
        existing = _add_customer(
            session,
            name="Old Customer",
            email="shared@example.com",
            phone="+447700900111",
        )
        lead = Lead(
            name="New Person",
            email="shared@example.com",
            phone="07700900222",
            status=LeadStatus.NEW,
        )
        customer = find_or_create_customer(lead, session)
        assert customer.id != existing.id


def test_creates_new_when_only_email_matches_and_name_differs_without_phone():
    engine = _engine()
    with Session(engine) as session:
        existing = _add_customer(session, name="Old Customer", email="shared@example.com", phone=None)
        lead = Lead(name="New Person", email="shared@example.com", phone=None, status=LeadStatus.NEW)
        customer = find_or_create_customer(lead, session)
        assert customer.id != existing.id


def test_creates_new_when_only_phone_matches_and_name_differs_without_email():
    engine = _engine()
    with Session(engine) as session:
        existing = _add_customer(session, name="Old Customer", phone="+447700900456", email=None)
        lead = Lead(name="New Person", phone="07700900456", email=None, status=LeadStatus.NEW)
        customer = find_or_create_customer(lead, session)
        assert customer.id != existing.id


def test_find_linkable_customer_returns_none_on_conflict():
    engine = _engine()
    with Session(engine) as session:
        _add_customer(
            session,
            name="Old Customer",
            email="old@example.com",
            phone="+447700900456",
        )
        lead = Lead(
            name="New Person",
            email="new@example.com",
            phone="07700900456",
            status=LeadStatus.NEW,
        )
        assert find_linkable_customer(session, lead) is None
        remaining = session.exec(select(Customer)).all()
        assert len(remaining) == 1
