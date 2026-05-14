import type { ConfiguratorBoxPlacement, Product } from '@/lib/types';

export const SNAP_THRESHOLD = 0.45;
export const TOUCH_TOLERANCE = 0;
export const DEFAULT_CANVAS_PADDING = 1;
export const DEFAULT_GRID_STEP = 0.25;
const OVERLAP_EPSILON = 1e-6;
const EDGE_EPSILON = 1e-6;
const RIGHT_ANGLES = [0, 90, 180, 270] as const;

export type BoxFace = 'top' | 'right' | 'bottom' | 'left';

export interface PlacementRect {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  boxWidth: number;
  boxLength: number;
  boundsWidth: number;
  boundsHeight: number;
  centerX: number;
  centerY: number;
  corners: Array<{ x: number; y: number }>;
}

export interface SnapGuide {
  orientation: 'vertical' | 'horizontal';
  position: number;
  start: number;
  end: number;
}

export interface CanvasBounds {
  minX: number;
  minY: number;
  width: number;
  height: number;
  padding: number;
}

export interface LayoutRectEntry {
  box: ConfiguratorBoxPlacement;
  product: Product;
  rect: PlacementRect;
}

export interface CandidatePlacement {
  x: number;
  y: number;
  snapped: boolean;
  overlaps: boolean;
  connected: boolean;
  frontBlocked: boolean;
  valid: boolean;
  guides: SnapGuide[];
}

interface SnapCandidate {
  value: number;
  distance: number;
  guide: SnapGuide;
}

interface AnchorInsets {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export function roundLayoutValue(value: number, step = DEFAULT_GRID_STEP) {
  if (!Number.isFinite(value)) return 0;
  return Math.round(value / step) * step;
}

export function normalizeRotation(value: number): ConfiguratorBoxPlacement['rotation'] {
  const normalized = ((Math.round(value / 90) * 90) % 360 + 360) % 360;
  if (RIGHT_ANGLES.includes(normalized as (typeof RIGHT_ANGLES)[number])) {
    return normalized as ConfiguratorBoxPlacement['rotation'];
  }
  return 0;
}

export function getFootprint(product: Product, rotation: number) {
  void rotation;
  const width = Number(product.configurator_width ?? 0);
  const length = Number(product.configurator_length ?? 0);
  return { width, length };
}

export function getFrontFace(rotation: number): BoxFace {
  const normalized = normalizeRotation(rotation);
  if (normalized === 90) return 'right';
  if (normalized === 180) return 'bottom';
  if (normalized === 270) return 'left';
  return 'top';
}

function toRadians(rotation: number) {
  return (rotation * Math.PI) / 180;
}

function rotatePoint(
  x: number,
  y: number,
  centerX: number,
  centerY: number,
  rotation: number
) {
  const radians = toRadians(rotation);
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  const dx = x - centerX;
  const dy = y - centerY;

  return {
    x: centerX + dx * cos - dy * sin,
    y: centerY + dx * sin + dy * cos,
  };
}

export function getPlacementRect(box: ConfiguratorBoxPlacement, product: Product): PlacementRect {
  const { width, length } = getFootprint(product, box.rotation);
  const centerX = Number(box.x) + width / 2;
  const centerY = Number(box.y) + length / 2;
  const corners = [
    rotatePoint(Number(box.x), Number(box.y), centerX, centerY, box.rotation),
    rotatePoint(Number(box.x) + width, Number(box.y), centerX, centerY, box.rotation),
    rotatePoint(Number(box.x) + width, Number(box.y) + length, centerX, centerY, box.rotation),
    rotatePoint(Number(box.x), Number(box.y) + length, centerX, centerY, box.rotation),
  ];
  const xs = corners.map((corner) => corner.x);
  const ys = corners.map((corner) => corner.y);
  return {
    x1: Math.min(...xs),
    y1: Math.min(...ys),
    x2: Math.max(...xs),
    y2: Math.max(...ys),
    boxWidth: width,
    boxLength: length,
    boundsWidth: Math.max(...xs) - Math.min(...xs),
    boundsHeight: Math.max(...ys) - Math.min(...ys),
    centerX,
    centerY,
    corners,
  };
}

function getAxes(corners: PlacementRect['corners']) {
  return corners.map((corner, index) => {
    const next = corners[(index + 1) % corners.length];
    const edgeX = next.x - corner.x;
    const edgeY = next.y - corner.y;
    const length = Math.hypot(edgeX, edgeY) || 1;
    return {
      x: -edgeY / length,
      y: edgeX / length,
    };
  });
}

function projectCorners(corners: PlacementRect['corners'], axis: { x: number; y: number }) {
  const projections = corners.map((corner) => corner.x * axis.x + corner.y * axis.y);
  return {
    min: Math.min(...projections),
    max: Math.max(...projections),
  };
}

export function placementsOverlap(a: PlacementRect, b: PlacementRect) {
  const axes = [...getAxes(a.corners), ...getAxes(b.corners)];

  for (const axis of axes) {
    const projectionA = projectCorners(a.corners, axis);
    const projectionB = projectCorners(b.corners, axis);
    if (
      projectionA.max <= projectionB.min + OVERLAP_EPSILON ||
      projectionB.max <= projectionA.min + OVERLAP_EPSILON
    ) {
      return false;
    }
  }

  return true;
}

export function rangesOverlap(
  aStart: number,
  aEnd: number,
  bStart: number,
  bEnd: number,
  tolerance = TOUCH_TOLERANCE
) {
  return Math.max(aStart, bStart) < Math.min(aEnd, bEnd) - tolerance - EDGE_EPSILON;
}

function edgesClose(a: number, b: number, tolerance = TOUCH_TOLERANCE) {
  return Math.abs(a - b) <= tolerance + EDGE_EPSILON;
}

function getSharedFaces(
  a: PlacementRect,
  b: PlacementRect,
  tolerance = TOUCH_TOLERANCE
) {
  const faces: Array<[BoxFace, BoxFace]> = [];

  if (edgesClose(a.x2, b.x1, tolerance) && rangesOverlap(a.y1, a.y2, b.y1, b.y2, tolerance)) {
    faces.push(['right', 'left']);
  }
  if (edgesClose(b.x2, a.x1, tolerance) && rangesOverlap(a.y1, a.y2, b.y1, b.y2, tolerance)) {
    faces.push(['left', 'right']);
  }
  if (edgesClose(a.y2, b.y1, tolerance) && rangesOverlap(a.x1, a.x2, b.x1, b.x2, tolerance)) {
    faces.push(['bottom', 'top']);
  }
  if (edgesClose(b.y2, a.y1, tolerance) && rangesOverlap(a.x1, a.x2, b.x1, b.x2, tolerance)) {
    faces.push(['top', 'bottom']);
  }

  return faces;
}

export function rectsTouch(
  a: PlacementRect,
  b: PlacementRect,
  tolerance = TOUCH_TOLERANCE
) {
  return getSharedFaces(a, b, tolerance).length > 0;
}

export function getJoinedFaces(entries: LayoutRectEntry[], tolerance = TOUCH_TOLERANCE) {
  const joinedFaces = new Map<string, Set<BoxFace>>();
  entries.forEach(({ box }) => joinedFaces.set(box.id, new Set<BoxFace>()));

  for (let index = 0; index < entries.length; index += 1) {
    const current = entries[index];
    for (let otherIndex = index + 1; otherIndex < entries.length; otherIndex += 1) {
      const other = entries[otherIndex];
      const sharedFaces = getSharedFaces(current.rect, other.rect, tolerance);
      sharedFaces.forEach(([currentFace, otherFace]) => {
        joinedFaces.get(current.box.id)?.add(currentFace);
        joinedFaces.get(other.box.id)?.add(otherFace);
      });
    }
  }

  return joinedFaces;
}

export function isFrontFaceExposed(
  box: ConfiguratorBoxPlacement,
  joinedFaces: Map<string, Set<BoxFace>>
) {
  return !joinedFaces.get(box.id)?.has(getFrontFace(box.rotation));
}

function getAnchorInsets(box: ConfiguratorBoxPlacement, rect: PlacementRect): AnchorInsets {
  return {
    left: rect.x1 - Number(box.x),
    right: rect.x2 - Number(box.x),
    top: rect.y1 - Number(box.y),
    bottom: rect.y2 - Number(box.y),
  };
}

export function buildLayoutRectEntries(
  boxes: ConfiguratorBoxPlacement[],
  productMap: Record<number, Product>
): LayoutRectEntry[] {
  return boxes
    .map((box) => {
      const product = productMap[box.product_id];
      if (!product) return null;
      return { box, product, rect: getPlacementRect(box, product) };
    })
    .filter((entry): entry is LayoutRectEntry => Boolean(entry));
}

export function getCanvasBounds(rects: PlacementRect[], padding = DEFAULT_CANVAS_PADDING): CanvasBounds {
  if (rects.length === 0) {
    return {
      minX: 0,
      minY: 0,
      width: 10,
      height: 7,
      padding,
    };
  }

  const minX = Math.min(0, Math.floor(Math.min(...rects.map((rect) => rect.x1))));
  const minY = Math.min(0, Math.floor(Math.min(...rects.map((rect) => rect.y1))));
  const maxX = Math.max(...rects.map((rect) => rect.x2));
  const maxY = Math.max(...rects.map((rect) => rect.y2));

  return {
    minX,
    minY,
    width: Math.max(10, Math.ceil(maxX - minX + padding * 2)),
    height: Math.max(7, Math.ceil(maxY - minY + padding * 2)),
    padding,
  };
}

export function getConnectedBoxIds(entries: LayoutRectEntry[], tolerance = TOUCH_TOLERANCE) {
  if (entries.length === 0) return new Set<string>();

  const graph = new Map<string, Set<string>>();
  entries.forEach(({ box }) => graph.set(box.id, new Set<string>()));

  for (let index = 0; index < entries.length; index += 1) {
    const current = entries[index];
    for (let otherIndex = index + 1; otherIndex < entries.length; otherIndex += 1) {
      const other = entries[otherIndex];
      if (rectsTouch(current.rect, other.rect, tolerance)) {
        graph.get(current.box.id)?.add(other.box.id);
        graph.get(other.box.id)?.add(current.box.id);
      }
    }
  }

  const connected = new Set<string>();
  const queue = [entries[0].box.id];
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current || connected.has(current)) continue;
    connected.add(current);
    queue.push(...(graph.get(current) ?? []));
  }

  return connected;
}

export function isLayoutConnected(entries: LayoutRectEntry[], tolerance = TOUCH_TOLERANCE) {
  if (entries.length <= 1) return true;
  return getConnectedBoxIds(entries, tolerance).size === entries.length;
}

function getSnapCandidates(
  rawValue: number,
  axis: 'x' | 'y',
  movingInsets: AnchorInsets,
  movingRect: PlacementRect,
  otherRect: PlacementRect,
  threshold: number
): SnapCandidate[] {
  if (axis === 'x') {
    const overlap = rangesOverlap(movingRect.y1, movingRect.y2, otherRect.y1, otherRect.y2, 0);
    const candidates = [
      {
        value: otherRect.x1 - movingInsets.right,
        guide: {
          orientation: 'vertical' as const,
          position: otherRect.x1,
          start: Math.min(movingRect.y1, otherRect.y1),
          end: Math.max(movingRect.y2, otherRect.y2),
        },
      },
      {
        value: otherRect.x2 - movingInsets.left,
        guide: {
          orientation: 'vertical' as const,
          position: otherRect.x2,
          start: Math.min(movingRect.y1, otherRect.y1),
          end: Math.max(movingRect.y2, otherRect.y2),
        },
      },
      {
        value: otherRect.x1 - movingInsets.left,
        guide: {
          orientation: 'vertical' as const,
          position: otherRect.x1,
          start: otherRect.y1,
          end: otherRect.y2,
        },
      },
      {
        value: otherRect.x2 - movingInsets.right,
        guide: {
          orientation: 'vertical' as const,
          position: otherRect.x2,
          start: otherRect.y1,
          end: otherRect.y2,
        },
      },
    ];

    return candidates
      .map((candidate) => ({
        value: candidate.value,
        guide: candidate.guide,
        distance: Math.abs(rawValue - candidate.value),
      }))
      .filter((candidate) => candidate.distance <= threshold && overlap);
  }

  const overlap = rangesOverlap(movingRect.x1, movingRect.x2, otherRect.x1, otherRect.x2, 0);
  const candidates = [
    {
      value: otherRect.y1 - movingInsets.bottom,
      guide: {
        orientation: 'horizontal' as const,
        position: otherRect.y1,
        start: Math.min(movingRect.x1, otherRect.x1),
        end: Math.max(movingRect.x2, otherRect.x2),
      },
    },
    {
      value: otherRect.y2 - movingInsets.top,
      guide: {
        orientation: 'horizontal' as const,
        position: otherRect.y2,
        start: Math.min(movingRect.x1, otherRect.x1),
        end: Math.max(movingRect.x2, otherRect.x2),
      },
    },
    {
      value: otherRect.y1 - movingInsets.top,
      guide: {
        orientation: 'horizontal' as const,
        position: otherRect.y1,
        start: otherRect.x1,
        end: otherRect.x2,
      },
    },
    {
      value: otherRect.y2 - movingInsets.bottom,
      guide: {
        orientation: 'horizontal' as const,
        position: otherRect.y2,
        start: otherRect.x1,
        end: otherRect.x2,
      },
    },
  ];

  return candidates
    .map((candidate) => ({
      value: candidate.value,
      guide: candidate.guide,
      distance: Math.abs(rawValue - candidate.value),
    }))
    .filter((candidate) => candidate.distance <= threshold && overlap);
}

function getBestCandidate(candidates: SnapCandidate[]) {
  return candidates.sort((left, right) => left.distance - right.distance)[0] ?? null;
}

export function findPlacementCandidate(params: {
  movingBox: ConfiguratorBoxPlacement;
  rawX: number;
  rawY: number;
  boxes: ConfiguratorBoxPlacement[];
  productMap: Record<number, Product>;
  threshold?: number;
}) {
  const { movingBox, rawX, rawY, boxes, productMap, threshold = SNAP_THRESHOLD } = params;
  const movingProduct = productMap[movingBox.product_id];
  if (!movingProduct) {
    return {
      x: roundLayoutValue(rawX),
      y: roundLayoutValue(rawY),
      snapped: false,
      overlaps: false,
      connected: true,
      frontBlocked: false,
      valid: false,
      guides: [],
    } satisfies CandidatePlacement;
  }

  const baseX = Math.max(0, roundLayoutValue(rawX));
  const baseY = Math.max(0, roundLayoutValue(rawY));
  const initialRect = getPlacementRect({ ...movingBox, x: baseX, y: baseY }, movingProduct);
  const movingInsets = getAnchorInsets({ ...movingBox, x: baseX, y: baseY }, initialRect);
  const otherEntries = buildLayoutRectEntries(
    boxes.filter((box) => box.id !== movingBox.id),
    productMap
  );

  const xCandidate = getBestCandidate(
    otherEntries.flatMap((entry) => getSnapCandidates(baseX, 'x', movingInsets, initialRect, entry.rect, threshold))
  );
  const snappedX = xCandidate ? roundLayoutValue(xCandidate.value) : baseX;

  const rectAfterX = getPlacementRect({ ...movingBox, x: snappedX, y: baseY }, movingProduct);
  const movingInsetsAfterX = getAnchorInsets({ ...movingBox, x: snappedX, y: baseY }, rectAfterX);
  const yCandidate = getBestCandidate(
    otherEntries.flatMap((entry) =>
      getSnapCandidates(baseY, 'y', movingInsetsAfterX, rectAfterX, entry.rect, threshold)
    )
  );
  const snappedY = yCandidate ? roundLayoutValue(yCandidate.value) : baseY;

  const nextBox = { ...movingBox, x: snappedX, y: snappedY };
  const nextRect = getPlacementRect(nextBox, movingProduct);
  const overlaps = otherEntries.some((entry) => placementsOverlap(nextRect, entry.rect));
  const layoutEntries = buildLayoutRectEntries(
    boxes.map((box) => (box.id === movingBox.id ? nextBox : box)),
    productMap
  );
  const connected = isLayoutConnected(layoutEntries);
  const joinedFaces = getJoinedFaces(layoutEntries);
  const frontBlocked = !isFrontFaceExposed(nextBox, joinedFaces);

  return {
    x: snappedX,
    y: snappedY,
    snapped: Boolean(xCandidate || yCandidate),
    overlaps,
    connected,
    frontBlocked,
    valid: !overlaps && connected && !frontBlocked,
    guides: [xCandidate?.guide, yCandidate?.guide].filter((guide): guide is SnapGuide => Boolean(guide)),
  } satisfies CandidatePlacement;
}

export function getSuggestedPlacement(
  boxes: ConfiguratorBoxPlacement[],
  product: Product,
  productMap: Record<number, Product>,
  anchorBoxId?: string | null
) {
  if (boxes.length === 0) {
    return { x: 0, y: 0 };
  }

  const entries = buildLayoutRectEntries(boxes, productMap);
  const footprint = getFootprint(product, 0);
  const anchorEntry =
    entries.find((entry) => entry.box.id === anchorBoxId) ??
    entries[entries.length - 1];
  const orderedEntries = [anchorEntry, ...entries.filter((entry) => entry.box.id !== anchorEntry.box.id)];

  for (const entry of orderedEntries) {
    const candidates = [
      { x: roundLayoutValue(entry.rect.x2), y: roundLayoutValue(entry.rect.y1) },
      { x: roundLayoutValue(entry.rect.x1), y: roundLayoutValue(entry.rect.y2) },
      { x: roundLayoutValue(Math.max(0, entry.rect.x1 - footprint.width)), y: roundLayoutValue(entry.rect.y1) },
      { x: roundLayoutValue(entry.rect.x1), y: roundLayoutValue(Math.max(0, entry.rect.y1 - footprint.length)) },
    ];

    for (const candidate of candidates) {
      const nextRect = getPlacementRect(
        {
          id: 'candidate',
          product_id: product.id,
          x: candidate.x,
          y: candidate.y,
          rotation: 0,
        },
        product
      );
      const overlaps = entries.some((other) => placementsOverlap(nextRect, other.rect));
      if (!overlaps) {
        return candidate;
      }
    }
  }

  const maxX = Math.max(...entries.map((entry) => entry.rect.x2));

  return {
    x: roundLayoutValue(maxX),
    y: 0,
  };
}
