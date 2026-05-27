"""Shared helpers for alternate delivery location on quotes and orders."""
from typing import Any, Optional, Protocol

from fastapi import HTTPException

from app.models import QuoteFulfillmentMethod


class DeliveryLocationFields(Protocol):
    use_alternate_delivery_address: bool
    delivery_address_line1: Optional[str]
    delivery_address_line2: Optional[str]
    delivery_city: Optional[str]
    delivery_county: Optional[str]
    delivery_postcode: Optional[str]
    delivery_country: Optional[str]
    delivery_location_notes: Optional[str]
    fulfillment_method: QuoteFulfillmentMethod


def build_delivery_address(entity: Any) -> str:
    """Build full address string from delivery location fields."""
    parts = []
    if getattr(entity, "delivery_address_line1", None):
        parts.append(entity.delivery_address_line1)
    if getattr(entity, "delivery_address_line2", None):
        parts.append(entity.delivery_address_line2)
    if getattr(entity, "delivery_city", None):
        parts.append(entity.delivery_city)
    if getattr(entity, "delivery_county", None):
        parts.append(entity.delivery_county)
    if getattr(entity, "delivery_postcode", None):
        parts.append(entity.delivery_postcode)
    country = getattr(entity, "delivery_country", None)
    if country:
        parts.append(country)
    return ", ".join(parts) if parts else ""


def has_full_delivery_address(entity: Any) -> bool:
    """True when delivery line 1, city, and postcode are all non-empty after strip."""
    line1 = (getattr(entity, "delivery_address_line1", None) or "").strip()
    city = (getattr(entity, "delivery_city", None) or "").strip()
    postcode = (getattr(entity, "delivery_postcode", None) or "").strip()
    return bool(line1 and city and postcode)


def assert_alternate_delivery_valid(
    use_alternate: bool,
    fulfillment_method: QuoteFulfillmentMethod,
    delivery_address_line1: Optional[str],
    delivery_city: Optional[str],
    delivery_postcode: Optional[str],
) -> None:
    """Raise HTTP 400 when alternate delivery is enabled but address is incomplete."""
    if not use_alternate:
        return
    if fulfillment_method == QuoteFulfillmentMethod.COLLECTION:
        return
    line1 = (delivery_address_line1 or "").strip()
    city = (delivery_city or "").strip()
    postcode = (delivery_postcode or "").strip()
    if not (line1 and city and postcode):
        raise HTTPException(
            status_code=400,
            detail=(
                "Delivery location requires address line 1, city, and postcode "
                "when using a different delivery address."
            ),
        )


def apply_delivery_location_fields(
    target: Any,
    *,
    use_alternate_delivery_address: Optional[bool] = None,
    delivery_address_line1: Optional[str] = None,
    delivery_address_line2: Optional[str] = None,
    delivery_city: Optional[str] = None,
    delivery_county: Optional[str] = None,
    delivery_postcode: Optional[str] = None,
    delivery_country: Optional[str] = None,
    delivery_location_notes: Optional[str] = None,
    set_fields: bool = True,
) -> None:
    """Apply delivery location fields to a Quote or Order model instance."""
    if not set_fields:
        return
    if use_alternate_delivery_address is not None:
        target.use_alternate_delivery_address = use_alternate_delivery_address
    if not getattr(target, "use_alternate_delivery_address", False):
        target.delivery_address_line1 = None
        target.delivery_address_line2 = None
        target.delivery_city = None
        target.delivery_county = None
        target.delivery_postcode = None
        target.delivery_country = "United Kingdom"
        target.delivery_location_notes = None
        return
    if delivery_address_line1 is not None:
        target.delivery_address_line1 = delivery_address_line1 or None
    if delivery_address_line2 is not None:
        target.delivery_address_line2 = delivery_address_line2 or None
    if delivery_city is not None:
        target.delivery_city = delivery_city or None
    if delivery_county is not None:
        target.delivery_county = delivery_county or None
    if delivery_postcode is not None:
        target.delivery_postcode = delivery_postcode or None
    if delivery_country is not None:
        target.delivery_country = delivery_country or "United Kingdom"
    if delivery_location_notes is not None:
        target.delivery_location_notes = delivery_location_notes or None


def copy_delivery_location_fields(source: Any, target: Any) -> None:
    """Copy delivery location fields from quote to order (or quote to quote)."""
    target.use_alternate_delivery_address = getattr(
        source, "use_alternate_delivery_address", False
    )
    target.delivery_address_line1 = getattr(source, "delivery_address_line1", None)
    target.delivery_address_line2 = getattr(source, "delivery_address_line2", None)
    target.delivery_city = getattr(source, "delivery_city", None)
    target.delivery_county = getattr(source, "delivery_county", None)
    target.delivery_postcode = getattr(source, "delivery_postcode", None)
    target.delivery_country = getattr(source, "delivery_country", None) or "United Kingdom"
    target.delivery_location_notes = getattr(source, "delivery_location_notes", None)


def delivery_location_response_fields(entity: Any) -> dict:
    """Dict of delivery fields for API responses."""
    return {
        "use_alternate_delivery_address": getattr(
            entity, "use_alternate_delivery_address", False
        ),
        "delivery_address_line1": getattr(entity, "delivery_address_line1", None),
        "delivery_address_line2": getattr(entity, "delivery_address_line2", None),
        "delivery_city": getattr(entity, "delivery_city", None),
        "delivery_county": getattr(entity, "delivery_county", None),
        "delivery_postcode": getattr(entity, "delivery_postcode", None),
        "delivery_country": getattr(entity, "delivery_country", None),
        "delivery_location_notes": getattr(entity, "delivery_location_notes", None),
    }


def sync_delivery_location_from_payload(
    target: Any,
    payload: Any,
    *,
    partial: bool = False,
) -> None:
    """Apply delivery location fields from a create/draft/update payload."""
    fields_set = getattr(payload, "model_fields_set", None) or getattr(payload, "__fields_set__", set())

    def _should_apply(field: str) -> bool:
        return not partial or field in fields_set

    if _should_apply("use_alternate_delivery_address"):
        target.use_alternate_delivery_address = bool(
            getattr(payload, "use_alternate_delivery_address", False)
        )

    if not target.use_alternate_delivery_address:
        target.delivery_address_line1 = None
        target.delivery_address_line2 = None
        target.delivery_city = None
        target.delivery_county = None
        target.delivery_postcode = None
        target.delivery_country = "United Kingdom"
        target.delivery_location_notes = None
        return

    for field in (
        "delivery_address_line1",
        "delivery_address_line2",
        "delivery_city",
        "delivery_county",
        "delivery_postcode",
        "delivery_country",
        "delivery_location_notes",
    ):
        if _should_apply(field):
            value = getattr(payload, field, None)
            if field == "delivery_country":
                setattr(target, field, value or "United Kingdom")
            else:
                setattr(target, field, value or None)
