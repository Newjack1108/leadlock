"""Layout diagram overlay geometry matches web canvas (CSS-local coords)."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal

from app.configurator_layout_public import (
    _css_local_to_layout,
    _format_layout_dimension_meters,
    _get_corner_overlay_segments,
    _main_layout_envelope,
    _overlay_line_css_local,
    _placement_rect,
)
from app.models import ConfiguratorConnectionProfile, ConfiguratorFrontFace, Product, ProductCategory
from app.schemas import ConfiguratorBoxPlacement


def _corner_product(
    profile: ConfiguratorConnectionProfile,
    width: float,
    length: float,
) -> Product:
    return Product(
        id=1,
        name="Corner SKU",
        category=ProductCategory.CONFIGURATOR,
        base_price=Decimal("2500.00"),
        configurator_width=Decimal(str(width)),
        configurator_length=Decimal(str(length)),
        configurator_is_corner_box=True,
        configurator_connection_profile=profile,
        configurator_front_face=ConfiguratorFrontFace.BOTTOM,
    )


def test_corner_blocked_front_on_right_face_tall_sku():
    """Tall corner-left SKU: green front is on the right edge, lower segment."""
    width, length = 3.6, 4.9
    product = _corner_product(ConfiguratorConnectionProfile.CORNER_LEFT, width, length)
    segments = _get_corner_overlay_segments(product)
    blocked = next(s for s in segments if s.kind == "blocked_front")
    assert blocked.face == "right"

    join_length = min(width, length)
    front_length = max(width, length)
    assert blocked.start_ratio == join_length / front_length
    assert blocked.end_ratio == 1.0

    x1, y1, x2, y2 = _overlay_line_css_local(
        blocked.face, blocked.start_ratio, blocked.end_ratio, width, length
    )
    assert x1 == x2 == width
    assert y1 == join_length
    assert y2 == front_length

    box_x, box_y, rotation = 0.0, 0.0, 0
    center_x = box_x + width / 2
    center_y = box_y + length / 2
    p1 = _css_local_to_layout(x1, y1, center_x, center_y, width, length, rotation)
    p2 = _css_local_to_layout(x2, y2, center_x, center_y, width, length, rotation)

    assert abs(p1[0] - p2[0]) < 1e-6
    assert abs(p1[0] - (box_x + width)) < 1e-6
    assert abs(p1[1] - (box_y + join_length)) < 1e-6
    assert abs(p2[1] - (box_y + front_length)) < 1e-6
    assert p2[1] > p1[1]


def test_standard_front_on_bottom_face():
    """Non-corner box: full-width green front on bottom edge."""
    product = Product(
        id=2,
        name="Standard",
        category=ProductCategory.CONFIGURATOR,
        base_price=Decimal("2000.00"),
        configurator_width=Decimal("3.00"),
        configurator_length=Decimal("4.00"),
        configurator_front_face=ConfiguratorFrontFace.BOTTOM,
    )
    from app.configurator_layout_public import _get_standard_front_overlay_segment

    seg = _get_standard_front_overlay_segment(product)
    assert seg is not None
    assert seg.face == "bottom"

    x1, y1, x2, y2 = _overlay_line_css_local(seg.face, seg.start_ratio, seg.end_ratio, 3.0, 4.0)
    assert y1 == y2 == 4.0
    assert x1 == 0.0
    assert x2 == 3.0


def _layout_entry(box_id: str, x: float, y: float, width: float, length: float, rotation: int = 0) -> dict:
    placement = ConfiguratorBoxPlacement(
        id=box_id,
        product_id=0,
        x=x,
        y=y,
        rotation=rotation,
    )
    return {
        "box": SimpleNamespace(id=box_id),
        "rect": _placement_rect(placement, width, length),
    }


def test_main_layout_envelope_two_touching_boxes():
    entries = [
        _layout_entry("a", 0.0, 0.0, 3.6, 3.6),
        _layout_entry("b", 3.6, 0.0, 3.6, 3.6),
    ]
    envelope = _main_layout_envelope(entries)
    assert envelope["box_count"] == 2
    assert envelope["width_m"] == 7.2
    assert envelope["height_m"] == 3.6


def test_main_layout_envelope_excludes_detached_box():
    entries = [
        _layout_entry("a", 0.0, 0.0, 3.6, 3.6),
        _layout_entry("b", 3.6, 0.0, 3.6, 3.6),
        _layout_entry("detached", 0.0, 8.0, 2.4, 3.6),
    ]
    envelope = _main_layout_envelope(entries)
    assert envelope["box_count"] == 2
    assert envelope["width_m"] == 7.2
    assert envelope["height_m"] == 3.6


def test_main_layout_envelope_single_box():
    entries = [_layout_entry("solo", 1.0, 2.0, 3.6, 3.6)]
    envelope = _main_layout_envelope(entries)
    assert envelope["box_count"] == 1
    assert envelope["width_m"] == pytest.approx(3.6)
    assert envelope["height_m"] == pytest.approx(3.6)
    assert envelope["min_x"] == pytest.approx(1.0)
    assert envelope["min_y"] == pytest.approx(2.0)


def test_format_layout_dimension_meters_trims_trailing_zeros():
    assert _format_layout_dimension_meters(7.2) == "7.2"
    assert _format_layout_dimension_meters(3.0) == "3"
