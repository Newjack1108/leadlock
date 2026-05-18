"""
Build customer-safe layout payloads and render layout diagrams (SVG / PDF).
Geometry mirrors web/lib/configurator/geometry.ts (SCALE = 40 on web).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from typing import Any, List, Optional, Tuple
from xml.sax.saxutils import escape

from sqlmodel import Session, select

from app.models import ConfiguratorConnectionProfile, ConfiguratorFrontFace, Product, ProductCategory, QuoteConfiguration
from app.schemas import (
    ConfiguratorBoxPlacement,
    PublicLayoutBoxResponse,
    PublicQuoteLayoutResponse,
    QuoteConfigurationPayload,
)

EDGE_EPSILON = 1e-6
TOUCH_TOLERANCE = 0.0
OVERALL_CAPTION_OFFSET_M = 0.4
PDF_LAYOUT_TARGET_WIDTH_PT = 170 * 2.834645669  # ~170mm in points
PDF_LAYOUT_MAX_HEIGHT_PT = 220 * 2.834645669
DEFAULT_CANVAS_PADDING = 1.0

# Web canvas uses SCALE=40 px per meter; PDF uses points per meter derived from fit scale.


@dataclass
class _CornerBaseDefinition:
    front_face: str
    standard_face: str
    join_start: float
    join_end: float
    blocked_start: float
    blocked_end: float


@dataclass
class _OverlaySegment:
    face: str
    kind: str  # blocked_front | joinable | standard
    start_ratio: float
    end_ratio: float
    length_meters: float


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _get_native_dimensions(product: Product) -> Tuple[float, float]:
    return _to_float(product.configurator_width), _to_float(product.configurator_length)


def _get_corner_base_definition(product: Product) -> Optional[_CornerBaseDefinition]:
    profile = product.configurator_connection_profile
    if not profile:
        return None
    if isinstance(profile, ConfiguratorConnectionProfile):
        profile_value = profile.value
    else:
        profile_value = str(profile)

    width, length = _get_native_dimensions(product)
    join_length = min(width, length)
    front_length = max(width, length)
    blocked_length = max(0.0, front_length - join_length)

    if length > width:
        if profile_value == ConfiguratorConnectionProfile.CORNER_LEFT.value:
            return _CornerBaseDefinition("right", "bottom", 0.0, join_length, join_length, front_length)
        return _CornerBaseDefinition("left", "bottom", 0.0, join_length, join_length, front_length)

    if profile_value == ConfiguratorConnectionProfile.CORNER_LEFT.value:
        return _CornerBaseDefinition("bottom", "left", blocked_length, front_length, 0.0, blocked_length)
    return _CornerBaseDefinition("bottom", "right", 0.0, join_length, join_length, front_length)


def _corner_face_length(face: str, width: float, length: float) -> float:
    return length if face in ("left", "right") else width


def _get_corner_blocked_front_length(product: Product) -> Optional[Decimal]:
    base = _get_corner_base_definition(product)
    if not base or base.blocked_end - base.blocked_start <= EDGE_EPSILON:
        return None
    return Decimal(str(round(base.blocked_end - base.blocked_start, 2)))


def _get_corner_overlay_segments(product: Product) -> List[_OverlaySegment]:
    base = _get_corner_base_definition(product)
    if not base:
        return []
    width, length = _get_native_dimensions(product)
    if width <= 0 or length <= 0:
        return []

    front_edge_length = _corner_face_length(base.front_face, width, length)
    standard_edge_length = _corner_face_length(base.standard_face, width, length)
    segments: List[_OverlaySegment] = []

    if base.blocked_end - base.blocked_start > EDGE_EPSILON:
        segments.append(
            _OverlaySegment(
                base.front_face,
                "blocked_front",
                base.blocked_start / front_edge_length,
                base.blocked_end / front_edge_length,
                base.blocked_end - base.blocked_start,
            )
        )
    if base.join_end - base.join_start > EDGE_EPSILON:
        segments.append(
            _OverlaySegment(
                base.front_face,
                "joinable",
                base.join_start / front_edge_length,
                base.join_end / front_edge_length,
                base.join_end - base.join_start,
            )
        )
    segments.append(_OverlaySegment(base.standard_face, "standard", 0.0, 1.0, standard_edge_length))
    return segments


def _get_base_front_face(product: Product) -> str:
    base = _get_corner_base_definition(product)
    if base:
        return base.front_face
    face = product.configurator_front_face
    if face:
        return face.value if hasattr(face, "value") else str(face)
    return "top"


def _get_standard_front_overlay_segment(product: Product) -> Optional[_OverlaySegment]:
    if _get_corner_base_definition(product):
        return None
    width, length = _get_native_dimensions(product)
    if width <= 0 or length <= 0:
        return None
    face = _get_base_front_face(product)
    if face not in ("top", "bottom", "left", "right"):
        return None
    edge_len = length if face in ("left", "right") else width
    return _OverlaySegment(face, "blocked_front", 0.0, 1.0, edge_len)


def _edge_overlay_segments(product: Product) -> List[_OverlaySegment]:
    corner = _get_corner_overlay_segments(product)
    if corner:
        return corner
    standard = _get_standard_front_overlay_segment(product)
    return [standard] if standard else []


def _rotate_point(x: float, y: float, cx: float, cy: float, rotation: int) -> Tuple[float, float]:
    rad = math.radians(rotation)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)
    dx = x - cx
    dy = y - cy
    return cx + dx * cos_r - dy * sin_r, cy + dx * sin_r + dy * cos_r


def _placement_rect(box: ConfiguratorBoxPlacement, width: float, length: float) -> dict:
    cx = _to_float(box.x) + width / 2
    cy = _to_float(box.y) + length / 2
    rot = int(box.rotation)
    corners = [
        _rotate_point(_to_float(box.x), _to_float(box.y), cx, cy, rot),
        _rotate_point(_to_float(box.x) + width, _to_float(box.y), cx, cy, rot),
        _rotate_point(_to_float(box.x) + width, _to_float(box.y) + length, cx, cy, rot),
        _rotate_point(_to_float(box.x), _to_float(box.y) + length, cx, cy, rot),
    ]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return {
        "x1": min(xs),
        "y1": min(ys),
        "x2": max(xs),
        "y2": max(ys),
        "box_width": width,
        "box_length": length,
        "center_x": cx,
        "center_y": cy,
        "rotation": rot,
    }


def _canvas_bounds(rects: List[dict], padding: float = DEFAULT_CANVAS_PADDING) -> dict:
    if not rects:
        return {"min_x": 0.0, "min_y": 0.0, "width": 10.0, "height": 7.0, "padding": padding}
    min_x = min(0.0, math.floor(min(r["x1"] for r in rects)))
    min_y = min(0.0, math.floor(min(r["y1"] for r in rects)))
    max_x = max(r["x2"] for r in rects)
    max_y = max(r["y2"] for r in rects)
    return {
        "min_x": min_x,
        "min_y": min_y,
        "width": max(10.0, math.ceil(max_x - min_x + padding * 2)),
        "height": max(7.0, math.ceil(max_y - min_y + padding * 2)),
        "padding": padding,
    }


def _ranges_overlap(
    a_start: float,
    a_end: float,
    b_start: float,
    b_end: float,
    tolerance: float = TOUCH_TOLERANCE,
) -> bool:
    return max(a_start, b_start) < min(a_end, b_end) - tolerance - EDGE_EPSILON


def _edges_close(a: float, b: float, tolerance: float = TOUCH_TOLERANCE) -> bool:
    return abs(a - b) <= tolerance + EDGE_EPSILON


def _rects_touch(a: dict, b: dict, tolerance: float = TOUCH_TOLERANCE) -> bool:
    if _edges_close(a["x2"], b["x1"], tolerance) and _ranges_overlap(
        a["y1"], a["y2"], b["y1"], b["y2"], tolerance
    ):
        return True
    if _edges_close(b["x2"], a["x1"], tolerance) and _ranges_overlap(
        a["y1"], a["y2"], b["y1"], b["y2"], tolerance
    ):
        return True
    if _edges_close(a["y2"], b["y1"], tolerance) and _ranges_overlap(
        a["x1"], a["x2"], b["x1"], b["x2"], tolerance
    ):
        return True
    if _edges_close(b["y2"], a["y1"], tolerance) and _ranges_overlap(
        a["x1"], a["x2"], b["x1"], b["x2"], tolerance
    ):
        return True
    return False


def _connected_components(entries: List[dict], tolerance: float = TOUCH_TOLERANCE) -> List[set[str]]:
    if not entries:
        return []

    graph: dict[str, set[str]] = {entry["box"].id: set() for entry in entries}
    for index, left in enumerate(entries):
        for right in entries[index + 1 :]:
            if _rects_touch(left["rect"], right["rect"], tolerance):
                graph[left["box"].id].add(right["box"].id)
                graph[right["box"].id].add(left["box"].id)

    visited: set[str] = set()
    components: List[set[str]] = []
    for entry in entries:
        box_id = entry["box"].id
        if box_id in visited:
            continue
        component: set[str] = set()
        queue = [box_id]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            queue.extend(graph.get(current, set()) - visited)
        components.append(component)
    return components


def _format_layout_dimension_meters(value: float) -> str:
    rounded = round(value, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    text = f"{rounded:.2f}".rstrip("0").rstrip(".")
    return text


def _rect_envelope_area(rect: dict) -> float:
    return (rect["x2"] - rect["x1"]) * (rect["y2"] - rect["y1"])


def _main_layout_envelope(entries: List[dict], tolerance: float = TOUCH_TOLERANCE) -> dict:
    empty = {
        "min_x": 0.0,
        "min_y": 0.0,
        "max_x": 0.0,
        "max_y": 0.0,
        "width_m": 0.0,
        "height_m": 0.0,
        "box_count": 0,
    }
    if not entries:
        return empty

    components = _connected_components(entries, tolerance)
    if not components:
        return empty

    entry_by_id = {entry["box"].id: entry for entry in entries}

    def component_area(ids: set[str]) -> float:
        return sum(_rect_envelope_area(entry_by_id[box_id]["rect"]) for box_id in ids if box_id in entry_by_id)

    main_ids = max(
        components,
        key=lambda ids: (len(ids), component_area(ids)),
    )
    main_entries = [entry for entry in entries if entry["box"].id in main_ids]
    if not main_entries:
        return empty

    min_x = min(entry["rect"]["x1"] for entry in main_entries)
    min_y = min(entry["rect"]["y1"] for entry in main_entries)
    max_x = max(entry["rect"]["x2"] for entry in main_entries)
    max_y = max(entry["rect"]["y2"] for entry in main_entries)
    return {
        "min_x": min_x,
        "min_y": min_y,
        "max_x": max_x,
        "max_y": max_y,
        "width_m": max_x - min_x,
        "height_m": max_y - min_y,
        "box_count": len(main_entries),
    }


def _draw_dashed_line(
    draw: Any,
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    fill: Tuple[int, int, int],
    width: int = 1,
    dash_length: float = 6,
    gap_length: float = 4,
) -> None:
    x1, y1 = p1
    x2, y2 = p2
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 1e-6:
        return
    dx = (x2 - x1) / length
    dy = (y2 - y1) / length
    pos = 0.0
    draw_on = True
    while pos < length:
        segment = min(dash_length if draw_on else gap_length, length - pos)
        if draw_on:
            sx = x1 + dx * pos
            sy = y1 + dy * pos
            ex = x1 + dx * (pos + segment)
            ey = y1 + dy * (pos + segment)
            draw.line([(sx, sy), (ex, ey)], fill=fill, width=width)
        pos += segment
        draw_on = not draw_on


def _draw_main_layout_overlay_png(
    draw: Any,
    envelope: dict,
    to_px_x: Any,
    to_px_y: Any,
    font_sm: Any,
) -> None:
    if envelope["box_count"] <= 0:
        return

    stroke = (100, 116, 139)
    x0 = to_px_x(envelope["min_x"])
    y0 = to_px_y(envelope["min_y"])
    x1 = to_px_x(envelope["max_x"])
    y1 = to_px_y(envelope["max_y"])
    for edge in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        _draw_dashed_line(draw, (edge[0], edge[1]), (edge[2], edge[3]), stroke, width=1)

    caption = (
        f"Overall: {_format_layout_dimension_meters(envelope['width_m'])} m × "
        f"{_format_layout_dimension_meters(envelope['height_m'])} m"
    )
    cx = to_px_x((envelope["min_x"] + envelope["max_x"]) / 2)
    cy = to_px_y(envelope["max_y"] + OVERALL_CAPTION_OFFSET_M)
    bbox = draw.textbbox((0, 0), caption, font=font_sm)
    tw = bbox[2] - bbox[0]
    draw.text((cx - tw / 2, cy), caption, fill=stroke, font=font_sm)


def _append_main_layout_overlay_svg(
    parts: List[str],
    envelope: dict,
    to_svg_x: Any,
    to_svg_y: Any,
) -> None:
    if envelope["box_count"] <= 0:
        return

    x0 = to_svg_x(envelope["min_x"])
    y0 = to_svg_y(envelope["min_y"])
    x1 = to_svg_x(envelope["max_x"])
    y1 = to_svg_y(envelope["max_y"])
    parts.append(
        f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" '
        f'fill="none" stroke="#64748b" stroke-width="1.5" stroke-dasharray="6 4"/>'
    )
    caption = (
        f"Overall: {_format_layout_dimension_meters(envelope['width_m'])} m × "
        f"{_format_layout_dimension_meters(envelope['height_m'])} m"
    )
    cx = to_svg_x((envelope["min_x"] + envelope["max_x"]) / 2)
    cy = to_svg_y(envelope["max_y"] + OVERALL_CAPTION_OFFSET_M)
    parts.append(
        f'<text x="{cx:.2f}" y="{cy:.2f}" text-anchor="middle" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#64748b">'
        f"{escape(caption)}</text>"
    )


def _product_from_layout_box(box: PublicLayoutBoxResponse) -> Product:
    """Minimal product stand-in for geometry (not persisted)."""
    profile = None
    if box.connection_profile:
        try:
            profile = ConfiguratorConnectionProfile(box.connection_profile)
        except ValueError:
            profile = None
    front_face = None
    if box.front_face:
        try:
            front_face = ConfiguratorFrontFace(box.front_face)
        except ValueError:
            front_face = None
    return Product(
        id=0,
        name=box.label,
        category=ProductCategory.CONFIGURATOR,
        base_price=Decimal("0"),
        configurator_width=box.width,
        configurator_length=box.length,
        configurator_is_corner_box=box.is_corner_box,
        configurator_connection_profile=profile,
        configurator_front_face=front_face,
    )


def build_layout_for_public_view(session: Session, quote_id: int) -> Optional[PublicQuoteLayoutResponse]:
    record = session.exec(
        select(QuoteConfiguration).where(QuoteConfiguration.quote_id == quote_id)
    ).first()
    if not record:
        return None

    payload = QuoteConfigurationPayload.model_validate(record.configuration_json or {})
    if not payload.boxes:
        return None

    boxes_out: List[PublicLayoutBoxResponse] = []
    for placement in payload.boxes:
        product = session.get(Product, placement.product_id)
        if not product:
            continue
        width = product.configurator_width
        length = product.configurator_length
        if not width or not length or _to_float(width) <= 0 or _to_float(length) <= 0:
            continue

        front_face = None
        if product.configurator_front_face:
            front_face = (
                product.configurator_front_face.value
                if hasattr(product.configurator_front_face, "value")
                else str(product.configurator_front_face)
            )
        connection_profile = None
        if product.configurator_connection_profile:
            connection_profile = (
                product.configurator_connection_profile.value
                if hasattr(product.configurator_connection_profile, "value")
                else str(product.configurator_connection_profile)
            )

        boxes_out.append(
            PublicLayoutBoxResponse(
                id=placement.id,
                label=product.name,
                x=placement.x,
                y=placement.y,
                rotation=placement.rotation,
                width=width,
                length=length,
                is_corner_box=bool(product.configurator_is_corner_box),
                front_face=front_face,
                connection_profile=connection_profile,
                blocked_front_m=_get_corner_blocked_front_length(product),
            )
        )

    if not boxes_out:
        return None

    return PublicQuoteLayoutResponse(name=payload.name, boxes=boxes_out)


def _layout_entries(layout: PublicQuoteLayoutResponse) -> List[dict]:
    entries = []
    for box in layout.boxes:
        product = _product_from_layout_box(box)
        width = _to_float(box.width)
        length = _to_float(box.length)
        placement = ConfiguratorBoxPlacement(
            id=box.id,
            product_id=0,
            x=box.x,
            y=box.y,
            rotation=box.rotation,
        )
        rect = _placement_rect(placement, width, length)
        entries.append(
            {
                "box": box,
                "product": product,
                "rect": rect,
                "segments": _edge_overlay_segments(product),
            }
        )
    return entries


def _segment_color(kind: str) -> str:
    if kind == "blocked_front":
        return "#10b981"
    if kind == "joinable":
        return "#ef4444"
    return "#f87171"


def _overlay_line_css_local(
    face: str, start_ratio: float, end_ratio: float, box_w: float, box_h: float
) -> Tuple[float, float, float, float]:
    """Segment line in CSS box coords (origin top-left, y down). Matches web overlay bars."""
    start_ratio = min(start_ratio, end_ratio)
    end_ratio = max(start_ratio, end_ratio)
    if face == "bottom":
        y = box_h
        x1 = start_ratio * box_w
        x2 = end_ratio * box_w
        return x1, y, x2, y
    if face == "top":
        y = 0.0
        x1 = start_ratio * box_w
        x2 = end_ratio * box_w
        return x1, y, x2, y
    if face == "left":
        x = 0.0
        y1 = start_ratio * box_h
        y2 = end_ratio * box_h
        return x, y1, x, y2
    x = box_w
    y1 = start_ratio * box_h
    y2 = end_ratio * box_h
    return x, y1, x, y2


def _css_local_to_layout(
    lx: float,
    ly: float,
    center_x: float,
    center_y: float,
    box_w: float,
    box_h: float,
    rotation: int,
) -> Tuple[float, float]:
    ux = center_x - box_w / 2 + lx
    uy = center_y - box_h / 2 + ly
    return _rotate_point(ux, uy, center_x, center_y, rotation)


def layout_to_svg(layout: PublicQuoteLayoutResponse) -> bytes:
    """Top-down layout diagram as SVG (fit ~800px wide)."""
    entries = _layout_entries(layout)
    if not entries:
        return b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'

    rects = [e["rect"] for e in entries]
    bounds = _canvas_bounds(rects)
    scale = 40.0
    pad = bounds["padding"]
    svg_w = bounds["width"] * scale
    svg_h = bounds["height"] * scale

    def to_svg_x(x: float) -> float:
        return (x - bounds["min_x"] + pad) * scale

    def to_svg_y(y: float) -> float:
        return (y - bounds["min_y"] + pad) * scale

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w:.1f}" height="{svg_h:.1f}" '
        f'viewBox="0 0 {svg_w:.1f} {svg_h:.1f}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
    ]

    for entry in entries:
        box = entry["box"]
        rect = entry["rect"]
        bw = rect["box_width"]
        bl = rect["box_length"]
        cx = to_svg_x(rect["center_x"])
        cy = to_svg_y(rect["center_y"])
        rot = rect["rotation"]
        label = escape(str(box.label))
        parts.append(
            f'<g transform="translate({cx:.2f},{cy:.2f}) rotate({rot})">'
            f'<rect x="{-bw * scale / 2:.2f}" y="{-bl * scale / 2:.2f}" '
            f'width="{bw * scale:.2f}" height="{bl * scale:.2f}" '
            f'fill="#f1f5f9" stroke="#94a3b8" stroke-width="1.5" rx="4"/>'
        )
        for seg in entry["segments"]:
            x1, y1, x2, y2 = _overlay_line_css_local(
                seg.face, seg.start_ratio, seg.end_ratio, bw, bl
            )
            color = _segment_color(seg.kind)
            stroke_w = 6 if seg.kind == "blocked_front" else 4
            parts.append(
                f'<line x1="{(x1 - bw / 2) * scale:.2f}" y1="{(y1 - bl / 2) * scale:.2f}" '
                f'x2="{(x2 - bw / 2) * scale:.2f}" y2="{(y2 - bl / 2) * scale:.2f}" '
                f'stroke="{color}" stroke-width="{stroke_w}" stroke-linecap="round"/>'
            )
        dim = f"{bw:g}m × {bl:g}m".replace("g", "")
        parts.append(
            f'<text x="0" y="0" text-anchor="middle" dominant-baseline="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="11" fill="#334155">'
            f'<tspan x="0" dy="-6">{label}</tspan>'
            f'<tspan x="0" dy="14" font-size="9" fill="#64748b">{dim}</tspan>'
            f"</text></g>"
        )

    _append_main_layout_overlay_svg(parts, _main_layout_envelope(entries), to_svg_x, to_svg_y)

    parts.append("</svg>")
    return "".join(parts).encode("utf-8")


def layout_to_png(layout: PublicQuoteLayoutResponse, pixels_per_meter: float = 40.0) -> bytes:
    """Rasterize layout for PDF embedding (Pillow)."""
    from PIL import Image, ImageDraw, ImageFont

    entries = _layout_entries(layout)
    if not entries:
        return b""

    rects = [e["rect"] for e in entries]
    bounds = _canvas_bounds(rects)
    pad = bounds["padding"]
    img_w = max(1, int(bounds["width"] * pixels_per_meter))
    img_h = max(1, int(bounds["height"] * pixels_per_meter))
    image = Image.new("RGB", (img_w, img_h), "#f8fafc")
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("arial.ttf", 11)
        font_sm = ImageFont.truetype("arial.ttf", 9)
    except OSError:
        font = ImageFont.load_default()
        font_sm = font

    def to_px_x(x: float) -> float:
        return (x - bounds["min_x"] + pad) * pixels_per_meter

    def to_px_y(y: float) -> float:
        return (y - bounds["min_y"] + pad) * pixels_per_meter

    def hex_to_rgb(color: str) -> Tuple[int, int, int]:
        color = color.lstrip("#")
        return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

    for entry in entries:
        box = entry["box"]
        rect = entry["rect"]
        bw = rect["box_width"]
        bl = rect["box_length"]
        rot = int(rect["rotation"])
        cx_layout = rect["center_x"]
        cy_layout = rect["center_y"]

        def css_to_layout(lx: float, ly: float) -> Tuple[float, float]:
            return _css_local_to_layout(lx, ly, cx_layout, cy_layout, bw, bl, rot)

        def to_pixel(x: float, y: float) -> Tuple[float, float]:
            return to_px_x(x), to_px_y(y)

        corners_css = [(0, 0), (bw, 0), (bw, bl), (0, bl)]
        poly = [to_pixel(*css_to_layout(x, y)) for x, y in corners_css]
        draw.polygon(poly, fill="#f1f5f9", outline="#94a3b8")

        for seg in entry["segments"]:
            x1, y1, x2, y2 = _overlay_line_css_local(
                seg.face, seg.start_ratio, seg.end_ratio, bw, bl
            )
            p1 = to_pixel(*css_to_layout(x1, y1))
            p2 = to_pixel(*css_to_layout(x2, y2))
            color = _segment_color(seg.kind)
            width_px = 6 if seg.kind == "blocked_front" else 4
            draw.line([p1, p2], fill=hex_to_rgb(color), width=width_px)

        label = str(box.label)[:40]
        dim = f"{bw:g}m x {bl:g}".replace("g", "")
        tx, ty = to_pixel(*css_to_layout(bw / 2, bl / 2))
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((tx - tw / 2, ty - 8), label, fill="#334155", font=font)
        bbox2 = draw.textbbox((0, 0), dim, font=font_sm)
        tw2 = bbox2[2] - bbox2[0]
        draw.text((tx - tw2 / 2, ty + 4), dim, fill="#64748b", font=font_sm)

    _draw_main_layout_overlay_png(
        draw,
        _main_layout_envelope(entries),
        to_px_x,
        to_px_y,
        font_sm,
    )

    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def append_layout_pdf_elements(
    elements: list,
    layout: PublicQuoteLayoutResponse,
    heading_style: Any,
    normal_style: Any,
) -> None:
    """Add a layout plan page to a ReportLab story."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, PageBreak, Paragraph, Spacer

    png_bytes = layout_to_png(layout)
    if not png_bytes:
        return

    from PIL import Image as PILImage

    pil = PILImage.open(BytesIO(png_bytes))
    img_w, img_h = pil.size
    max_w = PDF_LAYOUT_TARGET_WIDTH_PT
    max_h = PDF_LAYOUT_MAX_HEIGHT_PT
    scale = min(max_w / img_w, max_h / img_h, 1.0)
    display_w = img_w * scale
    display_h = img_h * scale

    elements.append(PageBreak())
    elements.append(Paragraph("Stable layout plan", heading_style))
    elements.append(
        Paragraph(
            "Plan view of the stable boxes included in this quote. "
            "Final positions may be confirmed at order stage.",
            normal_style,
        )
    )
    elements.append(Spacer(1, 6 * mm))
    elements.append(Image(BytesIO(png_bytes), width=display_w, height=display_h))
    elements.append(Spacer(1, 8 * mm))
