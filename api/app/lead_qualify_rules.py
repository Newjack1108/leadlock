"""Rules for lead source/type before a lead may become QUALIFIED."""
from typing import Optional

from app.models import LeadSource, LeadType

DISALLOWED_LEAD_SOURCES_FOR_QUALIFY = frozenset({LeadSource.MANUAL_ENTRY, LeadSource.OTHER})

STAFF_SELECTABLE_LEAD_SOURCES: tuple[LeadSource, ...] = tuple(
    s
    for s in LeadSource
    if s not in DISALLOWED_LEAD_SOURCES_FOR_QUALIFY and s != LeadSource.WEBSITE
)

SELECTABLE_LEAD_TYPES: tuple[LeadType, ...] = (
    LeadType.STABLES,
    LeadType.SHEDS,
    LeadType.CABINS,
)


def lead_source_allows_qualify(source: LeadSource | None) -> bool:
    return source not in DISALLOWED_LEAD_SOURCES_FOR_QUALIFY


def lead_type_allows_qualify(lead_type: LeadType | None) -> bool:
    return lead_type is not None and lead_type != LeadType.UNKNOWN


def lead_fields_allow_qualify(
    source: LeadSource | None,
    lead_type: LeadType | None,
) -> bool:
    return lead_source_allows_qualify(source) and lead_type_allows_qualify(lead_type)


def qualify_fields_error(
    source: LeadSource | None,
    lead_type: LeadType | None,
) -> Optional[dict]:
    """Stable HTTP 400 detail when qualify prerequisites are not met."""
    if lead_fields_allow_qualify(source, lead_type):
        return None
    parts: list[str] = []
    if not lead_source_allows_qualify(source):
        parts.append("select a lead source (not Manual entry or Other)")
    if not lead_type_allows_qualify(lead_type):
        parts.append("select a lead type (Stables, Sheds, or Cabins)")
    return {
        "error": "LEAD_FIELDS_REQUIRED_FOR_QUALIFY",
        "message": "Before qualifying: " + "; ".join(parts) + ".",
    }


def staff_may_set_lead_source(source: LeadSource | None) -> bool:
    if source is None:
        return True
    return source in STAFF_SELECTABLE_LEAD_SOURCES


def staff_may_set_lead_type(lead_type: LeadType | None) -> bool:
    if lead_type is None:
        return True
    return lead_type in SELECTABLE_LEAD_TYPES
