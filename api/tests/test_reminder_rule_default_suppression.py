"""Tests: deleted reminder rules stay deleted across default-rule backfill."""

import os
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.auth import get_current_user
from app.database import backfill_default_reminder_rules, get_session
from app.models import (
    Customer,
    CustomerOutreachSend,
    DeletedReminderRuleName,
    ReminderPriority,
    ReminderRule,
    SuggestedAction,
    User,
    UserRole,
)
from app.routers import reminders as reminders_router


def _make_test_app(engine):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(reminders_router.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=UserRole.DIRECTOR)
    return app


def test_deleted_default_rule_not_recreated_by_backfill():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        director = User(
            email="director-suppress@example.com",
            hashed_password="dummy",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)

        rule = ReminderRule(
            rule_name="NEW_LEAD_STALE",
            entity_type="LEAD",
            status="NEW",
            threshold_minutes=4320,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.HIGH,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        rid = rule.id

    client = TestClient(_make_test_app(engine))
    res = client.delete(f"/api/reminders/rules/{rid}")
    assert res.status_code == 200

    with Session(engine) as session:
        backfill_default_reminder_rules(session)
        again = session.exec(select(ReminderRule).where(ReminderRule.rule_name == "NEW_LEAD_STALE")).first()
        assert again is None
        sup = session.get(DeletedReminderRuleName, "NEW_LEAD_STALE")
        assert sup is not None


def test_recreate_default_clears_suppression_and_backfill_no_duplicate():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        director = User(
            email="director-recreate@example.com",
            hashed_password="dummy",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)

        rule = ReminderRule(
            rule_name="NEW_LEAD_STALE",
            entity_type="LEAD",
            status="NEW",
            threshold_minutes=4320,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.HIGH,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        rid = rule.id

    client = TestClient(_make_test_app(engine))
    assert client.delete(f"/api/reminders/rules/{rid}").status_code == 200

    payload = {
        "rule_name": "NEW_LEAD_STALE",
        "entity_type": "LEAD",
        "status": "NEW",
        "threshold_minutes": 9999,
        "check_type": "LAST_ACTIVITY",
        "is_active": True,
        "priority": "HIGH",
        "suggested_action": "FOLLOW_UP",
    }
    res = client.post("/api/reminders/rules", json=payload)
    assert res.status_code == 200
    assert res.json()["threshold_minutes"] == 9999

    with Session(engine) as session:
        backfill_default_reminder_rules(session)
        rows = session.exec(select(ReminderRule).where(ReminderRule.rule_name == "NEW_LEAD_STALE")).all()
        assert len(rows) == 1
        assert rows[0].threshold_minutes == 9999
        assert session.get(DeletedReminderRuleName, "NEW_LEAD_STALE") is None


def test_deleted_custom_rule_stays_deleted_after_backfill():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        director = User(
            email="director-custom@example.com",
            hashed_password="dummy",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)

        rule = ReminderRule(
            rule_name="MY_CUSTOM_RULE_XYZ",
            entity_type="LEAD",
            status="NEW",
            threshold_minutes=60,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        rid = rule.id

    client = TestClient(_make_test_app(engine))
    assert client.delete(f"/api/reminders/rules/{rid}").status_code == 200

    with Session(engine) as session:
        backfill_default_reminder_rules(session)
        custom = session.exec(select(ReminderRule).where(ReminderRule.rule_name == "MY_CUSTOM_RULE_XYZ")).first()
        assert custom is None


def test_delete_rule_removes_outreach_log_rows_first():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        director = User(
            email="director-outreach-delete@example.com",
            hashed_password="dummy",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        customer = Customer(customer_number="C0001", name="Delete Test Customer")
        session.add(director)
        session.add(customer)
        session.commit()
        session.refresh(customer)

        rule = ReminderRule(
            rule_name="LEAD_OUTREACH_DELETE_TEST",
            entity_type="LEAD",
            status="NEW",
            threshold_minutes=60,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        rid = rule.id

        session.add(
            CustomerOutreachSend(
                reminder_rule_id=rid,
                customer_id=customer.id,
                channel="SMS",
            )
        )
        session.commit()

    client = TestClient(_make_test_app(engine))
    res = client.delete(f"/api/reminders/rules/{rid}")
    assert res.status_code == 200

    with Session(engine) as session:
        deleted_rule = session.exec(select(ReminderRule).where(ReminderRule.id == rid)).first()
        assert deleted_rule is None
        sends = session.exec(
            select(CustomerOutreachSend).where(CustomerOutreachSend.reminder_rule_id == rid)
        ).all()
        assert sends == []
