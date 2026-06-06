"""Tests for LeadCreate -> Lead model field mapping."""
from app.lead_create_utils import lead_create_to_model_fields
from app.models import LeadSource, LeadType
from app.schemas import LeadCreate


def test_lead_create_to_model_fields_excludes_aliases():
    data = LeadCreate(
        first_name="Jane",
        last_name="Doe",
        phone_number="+447700900400",
        lead_source=LeadSource.REFERRAL,
        lead_type=LeadType.SHEDS,
    )
    fields = lead_create_to_model_fields(data)
    assert "first_name" not in fields
    assert "last_name" not in fields
    assert "full_name" not in fields
    assert "phone_number" not in fields
    assert fields["name"] == "Jane Doe"
    assert fields["phone"] == "+447700900400"
    assert fields["lead_source"] == LeadSource.REFERRAL
    assert fields["lead_type"] == LeadType.SHEDS
