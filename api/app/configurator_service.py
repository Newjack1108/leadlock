from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Tuple

from sqlmodel import Session, select

from app.models import Product, ProductCategory
from app.schemas import (
    ConfiguratorGeneratedLine,
    ConfiguratorPreviewResponse,
    ConfiguratorValidationIssue,
    QuoteConfigurationPayload,
)


ZERO = Decimal("0")


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _footprint(product: Product, rotation: int) -> Tuple[Decimal, Decimal]:
    width = _to_decimal(product.configurator_width or ZERO)
    length = _to_decimal(product.configurator_length or ZERO)
    if rotation in (90, 270):
        return length, width
    return width, length


def _rect(box, product: Product) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    x = _to_decimal(box.x)
    y = _to_decimal(box.y)
    width, length = _footprint(product, box.rotation)
    return x, y, x + width, y + length


def _range_overlap(a_start: Decimal, a_end: Decimal, b_start: Decimal, b_end: Decimal) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def _rectangles_overlap(
    left: Tuple[Decimal, Decimal, Decimal, Decimal],
    right: Tuple[Decimal, Decimal, Decimal, Decimal],
) -> bool:
    return left[0] < right[2] and left[2] > right[0] and left[1] < right[3] and left[3] > right[1]


def _touching(
    left: Tuple[Decimal, Decimal, Decimal, Decimal],
    right: Tuple[Decimal, Decimal, Decimal, Decimal],
) -> bool:
    shares_vertical_edge = (left[2] == right[0] or right[2] == left[0]) and _range_overlap(
        left[1], left[3], right[1], right[3]
    )
    shares_horizontal_edge = (left[3] == right[1] or right[3] == left[1]) and _range_overlap(
        left[0], left[2], right[0], right[2]
    )
    return shares_vertical_edge or shares_horizontal_edge


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

    layout_rects: Dict[str, Tuple[Decimal, Decimal, Decimal, Decimal]] = {}
    graph: Dict[str, set[str]] = {box.id: set() for box in payload.boxes}

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
        layout_rects[box.id] = _rect(box, product)

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
            elif _touching(rect, other_rect):
                graph[box.id].add(other.id)
                graph[other.id].add(box.id)

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
                    severity="warning",
                    message="Some configurator items are not attached to the main block.",
                    box_ids=sorted(set(layout_rects.keys()) - visited),
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
