"""Map LeadCreate schema payloads to Lead model field dicts."""
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.schemas import LeadCreate

_LEAD_CREATE_ALIAS_FIELDS = frozenset({"first_name", "last_name", "full_name", "phone_number"})


def lead_create_to_model_fields(lead_data: "LeadCreate") -> dict[str, Any]:
    """Fields for ``Lead(**...)`` — excludes alias-only keys not on the Lead table."""
    return lead_data.model_dump(
        exclude=_LEAD_CREATE_ALIAS_FIELDS,
        exclude_none=True,
    )
