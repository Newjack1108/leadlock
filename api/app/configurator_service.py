from __future__ import annotations

from decimal import Decimal
from math import cos, pi, sin
from typing import Dict, List, Literal, Optional, Set, Tuple

from sqlmodel import Session, select

from app.delivery_install_service import compute_delivery_install_estimate
from app.models import (
    CompanySettings,
    ConfiguratorConnectionProfile,
    ConfiguratorFrontFace,
    Customer,
    Product,
    ProductCategory,
    Quote,
    QuoteItemLineType,
)
from app.schemas import (
    ConfiguratorDeliveryEstimateInclusion,
    ConfiguratorGeneratedLine,
    ConfiguratorPreviewResponse,
    ConfiguratorValidationIssue,
    QuoteConfigurationPayload,
)


ZERO = Decimal("0")
TOUCH_TOLERANCE = 0.0
OVERLAP_EPSILON = 1e-6
EDGE_EPSILON = 1e-6
Point = Tuple[float, float]
LayoutShape = Tuple[float, float, float, float, Tuple[Point, Point, Point, Point]]
Face = str
FACE_ORDER: Tuple[Face, Face, Face, Face] = ("top", "right", "bottom", "left")
FaceContact = Tuple[Face, Face, float, float]
EdgeInterval = Tuple[Face, float, float]
FaceContactState = Literal["valid", "forbidden_face", "blocked_front_segment"]
CORNER_PROFILE_FRONT_FACE: Face = "bottom"


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _footprint(product: Product, rotation: int) -> Tuple[Decimal, Decimal]:
    width = _to_decimal(product.configurator_width or ZERO)
    length = _to_decimal(product.configurator_length or ZERO)
    _ = rotation
    return width, length


def _rotate_point(x: float, y: float, center_x: float, center_y: float, rotation: float) -> Point:
    radians = rotation * pi / 180
    dx = x - center_x
    dy = y - center_y
    return (
        center_x + dx * cos(radians) - dy * sin(radians),
        center_y + dx * sin(radians) + dy * cos(radians),
    )


def _shape(box, product: Product) -> LayoutShape:
    x = float(_to_decimal(box.x))
    y = float(_to_decimal(box.y))
    width, length = _footprint(product, box.rotation)
    box_width = float(width)
    box_length = float(length)
    center_x = x + box_width / 2
    center_y = y + box_length / 2
    corners = (
        _rotate_point(x, y, center_x, center_y, box.rotation),
        _rotate_point(x + box_width, y, center_x, center_y, box.rotation),
        _rotate_point(x + box_width, y + box_length, center_x, center_y, box.rotation),
        _rotate_point(x, y + box_length, center_x, center_y, box.rotation),
    )
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return min(xs), min(ys), max(xs), max(ys), corners


def _range_overlap(a_start: float, a_end: float, b_start: float, b_end: float, tolerance: float = 0.0) -> bool:
    return max(a_start, b_start) < min(a_end, b_end) - tolerance - EDGE_EPSILON


def _get_axes(corners: Tuple[Point, Point, Point, Point]) -> List[Point]:
    axes: List[Point] = []
    for index, point in enumerate(corners):
        next_point = corners[(index + 1) % len(corners)]
        edge_x = next_point[0] - point[0]
        edge_y = next_point[1] - point[1]
        length = (edge_x**2 + edge_y**2) ** 0.5 or 1.0
        axes.append((-edge_y / length, edge_x / length))
    return axes


def _project(corners: Tuple[Point, Point, Point, Point], axis: Point) -> Tuple[float, float]:
    projections = [point[0] * axis[0] + point[1] * axis[1] for point in corners]
    return min(projections), max(projections)


def _rectangles_overlap(
    left: LayoutShape,
    right: LayoutShape,
) -> bool:
    left_corners = left[4]
    right_corners = right[4]
    for axis in [*_get_axes(left_corners), *_get_axes(right_corners)]:
        left_min, left_max = _project(left_corners, axis)
        right_min, right_max = _project(right_corners, axis)
        if left_max <= right_min + OVERLAP_EPSILON or right_max <= left_min + OVERLAP_EPSILON:
            return False
    return True


def _edges_close(left: float, right: float) -> bool:
    return abs(left - right) <= TOUCH_TOLERANCE + EDGE_EPSILON


def _base_front_face(product: Product) -> Face:
    corner_base = _corner_base_definition(product)
    if corner_base is not None:
        return str(corner_base["front_face"])
    front_face = product.configurator_front_face
    if isinstance(front_face, ConfiguratorFrontFace):
        return front_face.value
    if isinstance(front_face, str) and front_face in FACE_ORDER:
        return front_face
    return "top"


def _connection_profile(product: Product) -> str | None:
    profile = product.configurator_connection_profile
    if isinstance(profile, ConfiguratorConnectionProfile):
        return profile.value
    if isinstance(profile, str) and profile in (
        ConfiguratorConnectionProfile.CORNER_LEFT.value,
        ConfiguratorConnectionProfile.CORNER_RIGHT.value,
    ):
        return profile
    return None


def _corner_rotation_locked(product: Product) -> bool:
    return bool(getattr(product, "configurator_is_corner_box", False))


def _native_dimensions(product: Product) -> Tuple[float, float]:
    return float(_to_decimal(product.configurator_width or ZERO)), float(
        _to_decimal(product.configurator_length or ZERO)
    )


def _corner_base_definition(product: Product) -> dict[str, float | Face] | None:
    profile = _connection_profile(product)
    if profile is None:
        return None

    width, length = _native_dimensions(product)
    join_length = min(width, length)
    front_length = max(width, length)
    blocked_length = max(0.0, front_length - join_length)

    if length > width:
        if profile == ConfiguratorConnectionProfile.CORNER_LEFT.value:
            return {
                "front_face": "right",
                "standard_face": "bottom",
                "join_start": 0.0,
                "join_end": join_length,
                "blocked_start": join_length,
                "blocked_end": front_length,
            }

        return {
            "front_face": "left",
            "standard_face": "bottom",
            "join_start": 0.0,
            "join_end": join_length,
            "blocked_start": join_length,
            "blocked_end": front_length,
        }

    if profile == ConfiguratorConnectionProfile.CORNER_LEFT.value:
        return {
            "front_face": "bottom",
            "standard_face": "left",
            "join_start": blocked_length,
            "join_end": front_length,
            "blocked_start": 0.0,
            "blocked_end": blocked_length,
        }

    return {
        "front_face": "bottom",
        "standard_face": "right",
        "join_start": 0.0,
        "join_end": join_length,
        "blocked_start": join_length,
        "blocked_end": front_length,
    }


def _rotate_face(face: Face, rotation: int) -> Face:
    base_index = FACE_ORDER.index(face) if face in FACE_ORDER else 0
    steps = rotation // 90
    return FACE_ORDER[(base_index + steps) % len(FACE_ORDER)]


def _segment_interval(start_point: Point, end_point: Point, shape: LayoutShape) -> EdgeInterval:
    min_x, min_y, max_x, max_y = shape[0], shape[1], shape[2], shape[3]
    if abs(start_point[1] - end_point[1]) <= EDGE_EPSILON:
        average_y = (start_point[1] + end_point[1]) / 2
        face = "top" if abs(average_y - min_y) <= abs(average_y - max_y) else "bottom"
        return face, min(start_point[0], end_point[0]), max(start_point[0], end_point[0])

    average_x = (start_point[0] + end_point[0]) / 2
    face = "left" if abs(average_x - min_x) <= abs(average_x - max_x) else "right"
    return face, min(start_point[1], end_point[1]), max(start_point[1], end_point[1])


def _face_segment_points(
    face: Face,
    start: float,
    end: float,
    left: float,
    right: float,
    top: float,
    bottom: float,
) -> Tuple[Point, Point]:
    if face == "bottom":
        return (left + start, bottom), (left + end, bottom)
    if face == "top":
        return (left + start, top), (left + end, top)
    if face == "left":
        return (left, top + start), (left, top + end)
    return (right, top + start), (right, top + end)


def _rotated_corner_definition(box, product: Product, shape: LayoutShape):
    base = _corner_base_definition(product)
    if base is None:
        return None

    width, length = _native_dimensions(product)
    if width <= 0 or length <= 0:
        return None

    center_x = (shape[0] + shape[2]) / 2
    center_y = (shape[1] + shape[3]) / 2
    left = center_x - width / 2
    right = center_x + width / 2
    top = center_y - length / 2
    bottom = center_y + length / 2

    def rotate_segment_point(x: float, y: float) -> Point:
        return _rotate_point(x, y, center_x, center_y, box.rotation)

    join_start = float(base["join_start"])
    join_end = float(base["join_end"])
    blocked_start = float(base["blocked_start"])
    blocked_end = float(base["blocked_end"])
    front_face = str(base["front_face"])
    standard_face = str(base["standard_face"])
    standard_length = width if standard_face in ("top", "bottom") else length

    join_start_point, join_end_point = _face_segment_points(
        front_face, join_start, join_end, left, right, top, bottom
    )

    join_interval = _segment_interval(
        rotate_segment_point(*join_start_point),
        rotate_segment_point(*join_end_point),
        shape,
    )

    blocked_interval = (
        _segment_interval(
            rotate_segment_point(*_face_segment_points(front_face, blocked_start, blocked_end, left, right, top, bottom)[0]),
            rotate_segment_point(*_face_segment_points(front_face, blocked_start, blocked_end, left, right, top, bottom)[1]),
            shape,
        )
        if blocked_end - blocked_start > EDGE_EPSILON
        else None
    )

    standard_start_point, standard_end_point = _face_segment_points(
        standard_face, 0.0, standard_length, left, right, top, bottom
    )
    standard_interval = _segment_interval(
        rotate_segment_point(*standard_start_point),
        rotate_segment_point(*standard_end_point),
        shape,
    )

    return {
        "front_face": join_interval[0],
        "join_interval": join_interval,
        "blocked_interval": blocked_interval,
        "standard_face": standard_interval[0],
    }


def _interval_within_allowed_range(contact_start: float, contact_end: float, allowed_start: float, allowed_end: float) -> bool:
    return contact_start >= allowed_start - EDGE_EPSILON and contact_end <= allowed_end + EDGE_EPSILON


def _front_face(product: Product, rotation: int) -> Face:
    return _rotate_face(_base_front_face(product), rotation)


def _shared_face_contacts(left: LayoutShape, right: LayoutShape) -> List[FaceContact]:
    faces: List[FaceContact] = []
    if _edges_close(left[2], right[0]) and _range_overlap(left[1], left[3], right[1], right[3], TOUCH_TOLERANCE):
        faces.append(("right", "left", max(left[1], right[1]), min(left[3], right[3])))
    if _edges_close(right[2], left[0]) and _range_overlap(left[1], left[3], right[1], right[3], TOUCH_TOLERANCE):
        faces.append(("left", "right", max(left[1], right[1]), min(left[3], right[3])))
    if _edges_close(left[3], right[1]) and _range_overlap(left[0], left[2], right[0], right[2], TOUCH_TOLERANCE):
        faces.append(("bottom", "top", max(left[0], right[0]), min(left[2], right[2])))
    if _edges_close(right[3], left[1]) and _range_overlap(left[0], left[2], right[0], right[2], TOUCH_TOLERANCE):
        faces.append(("top", "bottom", max(left[0], right[0]), min(left[2], right[2])))
    return faces


def _shared_faces(left: LayoutShape, right: LayoutShape) -> List[Tuple[Face, Face]]:
    return [(left_face, right_face) for left_face, right_face, _, _ in _shared_face_contacts(left, right)]


def _touching(
    left: LayoutShape,
    right: LayoutShape,
) -> bool:
    return len(_shared_face_contacts(left, right)) > 0


def _face_contact_state(box, product: Product, shape: LayoutShape, face: Face, overlap_start: float, overlap_end: float) -> FaceContactState:
    corner_definition = _rotated_corner_definition(box, product, shape)
    if corner_definition is None:
        return "valid"

    if face == corner_definition["standard_face"]:
        return "valid"
    join_face, allowed_start, allowed_end = corner_definition["join_interval"]
    if face == join_face:
        return (
            "valid"
            if _interval_within_allowed_range(overlap_start, overlap_end, allowed_start, allowed_end)
            else "blocked_front_segment"
        )
    return "forbidden_face"


def _load_products(session: Session, product_ids: List[int]) -> Dict[int, Product]:
    if not product_ids:
        return {}
    rows = session.exec(select(Product).where(Product.id.in_(product_ids))).all()
    return {row.id: row for row in rows if row.id is not None}


def resolve_quote_customer_postcode(quote: Quote, session: Session) -> Optional[str]:
    dealer_postcode = (getattr(quote, "dealer_customer_postcode", None) or "").strip()
    if dealer_postcode:
        return dealer_postcode
    if quote.customer_id:
        customer = session.get(Customer, quote.customer_id)
        if customer and customer.postcode:
            return customer.postcode.strip()
    return None


def _configurator_box_install_hours(
    payload: QuoteConfigurationPayload,
    box_products: Dict[int, Product],
) -> float:
    total = 0.0
    for box in payload.boxes:
        product = box_products.get(box.product_id)
        if not product or not product.installation_hours:
            continue
        total += float(product.installation_hours)
    return total


def _append_configurator_delivery_line(
    payload: QuoteConfigurationPayload,
    session: Session,
    customer_postcode: Optional[str],
    box_products: Dict[int, Product],
    lines: List[ConfiguratorGeneratedLine],
    issues: List[ConfiguratorValidationIssue],
    sort_order: int,
) -> Tuple[List[ConfiguratorGeneratedLine], List[ConfiguratorValidationIssue], int]:
    inclusion = payload.delivery_estimate_inclusion
    if inclusion in (
        ConfiguratorDeliveryEstimateInclusion.NONE,
        ConfiguratorDeliveryEstimateInclusion.COLLECTION,
    ):
        return lines, issues, sort_order

    postcode = (customer_postcode or "").strip()
    if not postcode:
        issues.append(
            ConfiguratorValidationIssue(
                code="DELIVERY_POSTCODE_REQUIRED",
                severity="error",
                message="Customer postcode is required to estimate delivery and installation.",
            )
        )
        return lines, issues, sort_order

    delivery_only = inclusion == ConfiguratorDeliveryEstimateInclusion.DELIVERY_ONLY
    install_hours = _configurator_box_install_hours(payload, box_products)
    if not delivery_only and install_hours <= 0:
        issues.append(
            ConfiguratorValidationIssue(
                code="DELIVERY_INSTALL_HOURS_REQUIRED",
                severity="error",
                message="Add configurator boxes with installation hours, or choose delivery only.",
            )
        )
        return lines, issues, sort_order

    settings = session.exec(select(CompanySettings).limit(1)).first()
    factory_postcode = (settings.postcode or "").strip() if settings else ""
    if not settings or not factory_postcode:
        issues.append(
            ConfiguratorValidationIssue(
                code="DELIVERY_ESTIMATE_FAILED",
                severity="error",
                message="Configure factory postcode and installation & travel in Company settings.",
            )
        )
        return lines, issues, sort_order

    box_count = len(payload.boxes)
    try:
        estimate = compute_delivery_install_estimate(
            factory_postcode=factory_postcode,
            customer_postcode=postcode,
            installation_hours=0.0 if delivery_only else install_hours,
            distance_before_overnight_miles=settings.distance_before_overnight_miles,
            cost_per_mile=settings.cost_per_mile,
            hourly_install_rate=settings.hourly_install_rate,
            hotel_allowance_per_night=settings.hotel_allowance_per_night,
            meal_allowance_per_day=settings.meal_allowance_per_day,
            average_speed_mph=settings.average_speed_mph,
            install_quote_margin_pct=settings.install_quote_margin_pct,
            delivery_only=delivery_only,
            number_of_boxes=box_count if delivery_only else None,
        )
    except ValueError as exc:
        issues.append(
            ConfiguratorValidationIssue(
                code="DELIVERY_ESTIMATE_FAILED",
                severity="error",
                message=str(exc),
            )
        )
        return lines, issues, sort_order

    cost_total = estimate.cost_total
    if cost_total is None or _to_decimal(cost_total) <= ZERO:
        issues.append(
            ConfiguratorValidationIssue(
                code="DELIVERY_ESTIMATE_FAILED",
                severity="error",
                message="Could not compute a delivery cost for this postcode.",
            )
        )
        return lines, issues, sort_order

    if estimate.settings_incomplete:
        issues.append(
            ConfiguratorValidationIssue(
                code="DELIVERY_ESTIMATE_INCOMPLETE",
                severity="warning",
                message="Some delivery costs could not be calculated. Complete Installation & travel in Company settings.",
            )
        )

    description = "Delivery only" if delivery_only else "Delivery & Installation"
    delivery_trips = estimate.delivery_trips if delivery_only else 1
    if delivery_only and delivery_trips > 1:
        unit_price = (_to_decimal(cost_total) / Decimal(str(delivery_trips))).quantize(Decimal("0.01"))
        quantity = Decimal(str(delivery_trips))
    else:
        unit_price = _to_decimal(cost_total).quantize(Decimal("0.01"))
        quantity = Decimal("1")
    lines.append(
        ConfiguratorGeneratedLine(
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            is_custom=True,
            sort_order=sort_order,
            include_in_building_discount=False,
            line_type=QuoteItemLineType.DELIVERY,
        )
    )
    return lines, issues, sort_order + 1


def build_configurator_preview(
    payload: QuoteConfigurationPayload,
    session: Session,
    customer_postcode: Optional[str] = None,
) -> ConfiguratorPreviewResponse:
    issues: List[ConfiguratorValidationIssue] = []
    if not payload.boxes:
        issues.append(
            ConfiguratorValidationIssue(
                code="EMPTY_LAYOUT",
                severity="error",
                message="Add at least one configurator item before previewing or applying.",
            )
        )

    seen_box_ids: set[str] = set()
    for box in payload.boxes:
        if box.id in seen_box_ids:
            issues.append(
                ConfiguratorValidationIssue(
                    code="DUPLICATE_BOX_ID",
                    severity="error",
                    message=f"Layout item id '{box.id}' is duplicated.",
                    box_ids=[box.id],
                )
            )
        seen_box_ids.add(box.id)

    box_products = _load_products(session, [box.product_id for box in payload.boxes])
    extra_products = _load_products(session, [extra.product_id for extra in payload.extras])

    starter_box_ids = [
        box.id
        for box in payload.boxes
        if bool(getattr(box_products.get(box.product_id), "configurator_is_starter_box", False))
    ]
    if payload.boxes and not starter_box_ids:
        issues.append(
            ConfiguratorValidationIssue(
                code="STARTER_BOX_REQUIRED",
                severity="error",
                message="Layout must include a starter box.",
                box_ids=[box.id for box in payload.boxes],
            )
        )
    if len(starter_box_ids) > 1:
        issues.append(
            ConfiguratorValidationIssue(
                code="MULTIPLE_STARTER_BOXES",
                severity="error",
                message="Layout can only include one starter box.",
                box_ids=starter_box_ids,
            )
        )

    layout_rects: Dict[str, LayoutShape] = {}
    graph: Dict[str, set[str]] = {box.id: set() for box in payload.boxes}
    joined_faces: Dict[str, set[Face]] = {box.id: set() for box in payload.boxes}
    invalid_connection_pairs: Set[Tuple[str, str, str]] = set()

    for box in payload.boxes:
        product = box_products.get(box.product_id)
        if not product or not product.is_active:
            issues.append(
                ConfiguratorValidationIssue(
                    code="UNKNOWN_PRODUCT",
                    severity="error",
                    message="One or more configurator products could not be found.",
                    box_ids=[box.id],
                )
            )
            continue
        if product.category != ProductCategory.CONFIGURATOR or product.is_extra:
            issues.append(
                ConfiguratorValidationIssue(
                    code="INVALID_PRODUCT_TYPE",
                    severity="error",
                    message=f"{product.name} is not a configurator item.",
                    box_ids=[box.id],
                )
            )
            continue
        if product.configurator_width is None or product.configurator_length is None:
            issues.append(
                ConfiguratorValidationIssue(
                    code="MISSING_DIMENSIONS",
                    severity="error",
                    message=f"{product.name} is missing configurator dimensions.",
                    box_ids=[box.id],
                )
            )
            continue
        if _corner_rotation_locked(product) and int(box.rotation or 0) % 360 != 0:
            issues.append(
                ConfiguratorValidationIssue(
                    code="CORNER_ROTATION_LOCKED",
                    severity="error",
                    message=(
                        f"{product.name} is a fixed-orientation corner box. "
                        "Use a different corner product instead of rotating it on the canvas."
                    ),
                    box_ids=[box.id],
                )
            )
            continue
        width, length = _footprint(product, box.rotation)
        if width <= ZERO or length <= ZERO:
            issues.append(
                ConfiguratorValidationIssue(
                    code="INVALID_DIMENSIONS",
                    severity="error",
                    message=f"{product.name} must have configurator dimensions greater than zero.",
                    box_ids=[box.id],
                )
            )
            continue
        layout_rects[box.id] = _shape(box, product)

    for index, box in enumerate(payload.boxes):
        rect = layout_rects.get(box.id)
        if rect is None:
            continue
        for other in payload.boxes[index + 1 :]:
            other_rect = layout_rects.get(other.id)
            if other_rect is None:
                continue
            if _rectangles_overlap(rect, other_rect):
                issues.append(
                    ConfiguratorValidationIssue(
                        code="OVERLAP",
                        severity="error",
                        message="Configurator items cannot overlap on the layout grid.",
                        box_ids=[box.id, other.id],
                    )
                )
            else:
                current_product = box_products.get(box.product_id)
                other_product = box_products.get(other.product_id)
                if not current_product or not other_product:
                    continue
                contacts = _shared_face_contacts(rect, other_rect)
                if not contacts:
                    continue
                for box_face, other_face, overlap_start, overlap_end in contacts:
                    box_state = _face_contact_state(
                        box,
                        current_product,
                        rect,
                        box_face,
                        overlap_start,
                        overlap_end,
                    )
                    other_state = _face_contact_state(
                        other,
                        other_product,
                        other_rect,
                        other_face,
                        overlap_start,
                        overlap_end,
                    )
                    if box_state == "valid" and other_state == "valid":
                        graph[box.id].add(other.id)
                        graph[other.id].add(box.id)
                        joined_faces[box.id].add(box_face)
                        joined_faces[other.id].add(other_face)
                        continue

                    issue_code = (
                        "INVALID_CONNECTION_SEGMENT"
                        if "blocked_front_segment" in (box_state, other_state)
                        else "INVALID_CONNECTION_FACE"
                    )
                    invalid_connection_pairs.add(tuple(sorted((box.id, other.id))) + (issue_code,))

    if len(layout_rects) > 1:
        to_visit = [next(iter(layout_rects.keys()))]
        visited: set[str] = set()
        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
            visited.add(current)
            to_visit.extend(graph.get(current, set()) - visited)
        if len(visited) != len(layout_rects):
            issues.append(
                ConfiguratorValidationIssue(
                    code="DISCONNECTED_LAYOUT",
                    severity="error",
                    message="All configurator items must attach to the main block.",
                    box_ids=sorted(set(layout_rects.keys()) - visited),
                )
            )

    for left_id, right_id, issue_code in sorted(invalid_connection_pairs):
        issues.append(
            ConfiguratorValidationIssue(
                code=issue_code,
                severity="error",
                message=(
                    "Corner boxes can only join across their marked 3.5m front section."
                    if issue_code == "INVALID_CONNECTION_SEGMENT"
                    else "Configurator items can only connect on their allowed join sides."
                ),
                box_ids=[left_id, right_id],
            )
        )

    for box in payload.boxes:
        if box.id not in layout_rects:
            continue
        product = box_products.get(box.product_id)
        if not product:
            continue
        if _connection_profile(product):
            continue
        if _front_face(product, box.rotation) in joined_faces.get(box.id, set()):
            issues.append(
                ConfiguratorValidationIssue(
                    code="FRONT_FACE_BLOCKED",
                    severity="error",
                    message="The front of a configurator item must stay on an exposed face.",
                    box_ids=[box.id],
                )
            )

    for extra in payload.extras:
        product = extra_products.get(extra.product_id)
        if not product or not product.is_active:
            issues.append(
                ConfiguratorValidationIssue(
                    code="UNKNOWN_EXTRA",
                    severity="error",
                    message="One or more configurator extras could not be found.",
                )
            )
            continue
        if not product.is_extra or not product.allow_in_configurator:
            issues.append(
                ConfiguratorValidationIssue(
                    code="INVALID_EXTRA",
                    severity="error",
                    message=f"{product.name} is not enabled for configurator use.",
                )
            )
        if not product.configurator_per_box and extra.quantity is not None and _to_decimal(extra.quantity) <= ZERO:
            issues.append(
                ConfiguratorValidationIssue(
                    code="INVALID_EXTRA_QUANTITY",
                    severity="error",
                    message=f"{product.name} must have a quantity greater than zero.",
                )
            )

    lines: List[ConfiguratorGeneratedLine] = []
    sort_order = 0
    for box in payload.boxes:
        product = box_products.get(box.product_id)
        if not product or product.category != ProductCategory.CONFIGURATOR or product.is_extra:
            continue
        lines.append(
            ConfiguratorGeneratedLine(
                product_id=product.id,
                description=product.name,
                quantity=Decimal("1"),
                unit_price=product.base_price,
                is_custom=False,
                sort_order=sort_order,
                include_in_building_discount=True,
            )
        )
        sort_order += 1

    box_count = len(lines)
    for extra in payload.extras:
        product = extra_products.get(extra.product_id)
        if not product or not product.is_extra or not product.allow_in_configurator:
            continue
        if product.configurator_per_box:
            quantity = Decimal(box_count)
        elif extra.quantity is not None:
            quantity = _to_decimal(extra.quantity)
        else:
            quantity = Decimal("1")
        lines.append(
            ConfiguratorGeneratedLine(
                product_id=product.id,
                description=product.name,
                quantity=quantity,
                unit_price=product.base_price,
                is_custom=False,
                sort_order=sort_order,
                include_in_building_discount=False,
            )
        )
        sort_order += 1

    lines, issues, _sort_order = _append_configurator_delivery_line(
        payload,
        session,
        customer_postcode,
        box_products,
        lines,
        issues,
        sort_order,
    )

    subtotal = sum((_to_decimal(line.quantity) * _to_decimal(line.unit_price) for line in lines), ZERO)
    has_errors = any(issue.severity == "error" for issue in issues)
    return ConfiguratorPreviewResponse(
        valid=not has_errors,
        issues=issues,
        items=lines,
        subtotal=subtotal,
        total_boxes=box_count,
    )
