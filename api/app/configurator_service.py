from __future__ import annotations

from decimal import Decimal
from math import cos, pi, sin
from typing import Dict, List, Literal, Set, Tuple

from sqlmodel import Session, select

from app.models import ConfiguratorConnectionProfile, ConfiguratorFrontFace, Product, ProductCategory
from app.schemas import (
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
FaceContactState = Literal["valid", "forbidden_face", "blocked_front_segment"]


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _footprint(product: Product, rotation: int) -> Tuple[Decimal, Decimal]:
    width = _to_decimal(product.configurator_width or ZERO)
    length = _to_decimal(product.configurator_length or ZERO)
    if rotation in (90, 270):
        return length, width
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


def _rotate_face(face: Face, rotation: int) -> Face:
    base_index = FACE_ORDER.index(face) if face in FACE_ORDER else 0
    steps = rotation // 90
    return FACE_ORDER[(base_index + steps) % len(FACE_ORDER)]


def _front_start_adjacent_face(face: Face) -> Face:
    if face in ("top", "bottom"):
        return "left"
    return "top"


def _front_end_adjacent_face(face: Face) -> Face:
    if face in ("top", "bottom"):
        return "right"
    return "bottom"


def _corner_standard_face(face: Face, profile: str) -> Face:
    return (
        _front_start_adjacent_face(face)
        if profile == ConfiguratorConnectionProfile.CORNER_LEFT.value
        else _front_end_adjacent_face(face)
    )


def _face_length(shape: LayoutShape, face: Face) -> float:
    if face in ("top", "bottom"):
        return shape[2] - shape[0]
    return shape[3] - shape[1]


def _face_axis_start(shape: LayoutShape, face: Face) -> float:
    if face in ("top", "bottom"):
        return shape[0]
    return shape[1]


def _allowed_front_join_interval(box, product: Product, shape: LayoutShape, face: Face, profile: str) -> Tuple[float, float]:
    width, length = _footprint(product, box.rotation)
    face_length = _face_length(shape, face)
    join_length = float(min(width, length))
    blocked_length = max(0.0, face_length - join_length)
    axis_start = _face_axis_start(shape, face)

    if profile == ConfiguratorConnectionProfile.CORNER_LEFT.value:
        return axis_start + blocked_length, axis_start + face_length
    return axis_start, axis_start + join_length


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
    profile = _connection_profile(product)
    if profile is None:
        return "valid"

    front_face = _front_face(product, box.rotation)
    standard_face = _corner_standard_face(front_face, profile)
    if face == standard_face:
        return "valid"
    if face == front_face:
        allowed_start, allowed_end = _allowed_front_join_interval(box, product, shape, face, profile)
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


def build_configurator_preview(
    payload: QuoteConfigurationPayload,
    session: Session,
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
        if extra.quantity is not None and _to_decimal(extra.quantity) <= ZERO:
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
        quantity = (
            _to_decimal(extra.quantity)
            if extra.quantity is not None
            else Decimal(box_count if product.unit == "Per Box" else 1)
        )
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

    subtotal = sum((_to_decimal(line.quantity) * _to_decimal(line.unit_price) for line in lines), ZERO)
    has_errors = any(issue.severity == "error" for issue in issues)
    return ConfiguratorPreviewResponse(
        valid=not has_errors,
        issues=issues,
        items=lines,
        subtotal=subtotal,
        total_boxes=box_count,
    )
