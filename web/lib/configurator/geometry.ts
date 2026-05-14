import type {
  ConfiguratorBoxPlacement,
  ConfiguratorConnectionProfile,
  ConfiguratorFrontFace,
  Product,
} from '@/lib/types';

export const SNAP_THRESHOLD = 0.45;
export const TOUCH_TOLERANCE = 0;
export const DEFAULT_CANVAS_PADDING = 1;
export const DEFAULT_GRID_STEP = 0.1;
const OVERLAP_EPSILON = 1e-6;
const EDGE_EPSILON = 1e-6;
const RIGHT_ANGLES = [0, 90, 180, 270] as const;
const POSITION_DECIMALS = 2;

export type BoxFace = ConfiguratorFrontFace;
const FACE_ORDER: readonly BoxFace[] = ['top', 'right', 'bottom', 'left'];
const CORNER_PROFILE_FRONT_FACE: BoxFace = 'bottom';
const CORNER_PROFILE_DEFAULT_ROTATION: Record<
  ConfiguratorConnectionProfile,
  ConfiguratorBoxPlacement['rotation']
> = {
  corner_left: 270,
  corner_right: 90,
};

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
  connectionBlocked: boolean;
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

interface FaceContact {
  leftFace: BoxFace;
  rightFace: BoxFace;
  overlapStart: number;
  overlapEnd: number;
}

interface EdgeInterval {
  face: BoxFace;
  start: number;
  end: number;
}

interface CornerBaseDefinition {
  frontFace: 'bottom';
  standardFace: 'left' | 'right';
  joinStart: number;
  joinEnd: number;
  blockedStart: number;
  blockedEnd: number;
}

interface CornerLayoutDefinition {
  frontFace: BoxFace;
  standardFace: BoxFace;
  joinInterval: EdgeInterval;
  blockedInterval: EdgeInterval | null;
}

type FaceContactState = 'valid' | 'forbidden_face' | 'blocked_front_segment';

interface LayoutAnalysis {
  graph: Map<string, Set<string>>;
  joinedFaces: Map<string, Set<BoxFace>>;
  frontBlocked: Set<string>;
  connectionBlocked: Set<string>;
}

export function roundLayoutValue(value: number, step = DEFAULT_GRID_STEP) {
  if (!Number.isFinite(value)) return 0;
  return Math.round(value / step) * step;
}

function roundPosition(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Number(value.toFixed(POSITION_DECIMALS));
}

export function normalizeRotation(value: number): ConfiguratorBoxPlacement['rotation'] {
  const normalized = ((Math.round(value / 90) * 90) % 360 + 360) % 360;
  if (RIGHT_ANGLES.includes(normalized as (typeof RIGHT_ANGLES)[number])) {
    return normalized as ConfiguratorBoxPlacement['rotation'];
  }
  return 0;
}

export function getFootprint(product: Product, rotation: number) {
  const width = Number(product.configurator_width ?? 0);
  const length = Number(product.configurator_length ?? 0);
  const normalized = normalizeRotation(rotation);
  if (normalized === 90 || normalized === 270) {
    return { width: length, length: width };
  }
  return { width, length };
}

export function getBaseFrontFace(product?: Product | null): BoxFace {
  const profile = getConnectionProfile(product);
  if (profile) {
    return CORNER_PROFILE_FRONT_FACE;
  }
  const frontFace = product?.configurator_front_face;
  if (frontFace && FACE_ORDER.includes(frontFace)) {
    return frontFace;
  }
  return 'top';
}

function getConnectionProfile(product?: Product | null): ConfiguratorConnectionProfile | null {
  const profile = product?.configurator_connection_profile;
  if (profile === 'corner_left' || profile === 'corner_right') {
    return profile;
  }
  return null;
}

function getNativeDimensions(product: Product | null | undefined) {
  return {
    width: Number(product?.configurator_width ?? 0),
    length: Number(product?.configurator_length ?? 0),
  };
}

export function getCornerBaseDefinition(product: Product | null | undefined): CornerBaseDefinition | null {
  const profile = getConnectionProfile(product);
  if (!profile) {
    return null;
  }

  const { width, length } = getNativeDimensions(product);
  const joinLength = Math.min(width, length);
  const blockedLength = Math.max(0, width - joinLength);

  if (profile === 'corner_left') {
    return {
      frontFace: 'bottom',
      standardFace: 'left',
      joinStart: blockedLength,
      joinEnd: width,
      blockedStart: 0,
      blockedEnd: blockedLength,
    };
  }

  return {
    frontFace: 'bottom',
    standardFace: 'right',
    joinStart: 0,
    joinEnd: joinLength,
    blockedStart: joinLength,
    blockedEnd: width,
  };
}

function rotateFace(face: BoxFace, rotation: number): BoxFace {
  const normalized = normalizeRotation(rotation);
  const baseIndex = FACE_ORDER.indexOf(face);
  const steps = normalized / 90;
  return FACE_ORDER[(baseIndex + steps) % FACE_ORDER.length] ?? 'top';
}

function getIntervalFromSegment(
  startPoint: { x: number; y: number },
  endPoint: { x: number; y: number },
  bounds: Pick<PlacementRect, 'x1' | 'x2' | 'y1' | 'y2'>
): EdgeInterval {
  if (Math.abs(startPoint.y - endPoint.y) <= EDGE_EPSILON) {
    const averageY = (startPoint.y + endPoint.y) / 2;
    const topDistance = Math.abs(averageY - bounds.y1);
    const bottomDistance = Math.abs(averageY - bounds.y2);
    return {
      face: topDistance <= bottomDistance ? 'top' : 'bottom',
      start: Math.min(startPoint.x, endPoint.x),
      end: Math.max(startPoint.x, endPoint.x),
    };
  }

  const averageX = (startPoint.x + endPoint.x) / 2;
  const leftDistance = Math.abs(averageX - bounds.x1);
  const rightDistance = Math.abs(averageX - bounds.x2);
  return {
    face: leftDistance <= rightDistance ? 'left' : 'right',
    start: Math.min(startPoint.y, endPoint.y),
    end: Math.max(startPoint.y, endPoint.y),
  };
}

function getRotatedCornerDefinition(
  box: ConfiguratorBoxPlacement,
  product: Product,
  rect: PlacementRect
): CornerLayoutDefinition | null {
  const base = getCornerBaseDefinition(product);
  if (!base) {
    return null;
  }

  const { width, length } = getNativeDimensions(product);
  if (width <= 0 || length <= 0) {
    return null;
  }

  const left = rect.centerX - width / 2;
  const right = rect.centerX + width / 2;
  const top = rect.centerY - length / 2;
  const bottom = rect.centerY + length / 2;

  const rotateSegmentPoint = (x: number, y: number) =>
    rotatePoint(x, y, rect.centerX, rect.centerY, box.rotation);

  const joinStartPoint = rotateSegmentPoint(left + base.joinStart, bottom);
  const joinEndPoint = rotateSegmentPoint(left + base.joinEnd, bottom);
  const joinInterval = getIntervalFromSegment(joinStartPoint, joinEndPoint, rect);

  const blockedInterval =
    base.blockedEnd - base.blockedStart > EDGE_EPSILON
      ? getIntervalFromSegment(
          rotateSegmentPoint(left + base.blockedStart, bottom),
          rotateSegmentPoint(left + base.blockedEnd, bottom),
          rect
        )
      : null;

  const standardInterval = getIntervalFromSegment(
    base.standardFace === 'right'
      ? rotateSegmentPoint(right, top)
      : rotateSegmentPoint(left, top),
    base.standardFace === 'right'
      ? rotateSegmentPoint(right, bottom)
      : rotateSegmentPoint(left, bottom),
    rect
  );

  return {
    frontFace: joinInterval.face,
    standardFace: standardInterval.face,
    joinInterval,
    blockedInterval,
  };
}

function isIntervalWithinAllowedRange(contactStart: number, contactEnd: number, allowedStart: number, allowedEnd: number) {
  return contactStart >= allowedStart - EDGE_EPSILON && contactEnd <= allowedEnd + EDGE_EPSILON;
}

export function getFrontFace(product: Product | null | undefined, rotation: number): BoxFace {
  return rotateFace(getBaseFrontFace(product), rotation);
}

export function getRotationForFrontFace(
  product: Product | null | undefined,
  face: BoxFace
): ConfiguratorBoxPlacement['rotation'] {
  const baseFace = getBaseFrontFace(product);
  const baseIndex = FACE_ORDER.indexOf(baseFace);
  const targetIndex = FACE_ORDER.indexOf(face);
  const steps = (targetIndex - baseIndex + FACE_ORDER.length) % FACE_ORDER.length;
  return RIGHT_ANGLES[steps] ?? 0;
}

export function getDefaultBoxRotation(product: Product | null | undefined): ConfiguratorBoxPlacement['rotation'] {
  const profile = getConnectionProfile(product);
  if (profile) {
    return CORNER_PROFILE_DEFAULT_ROTATION[profile];
  }
  return getRotationForFrontFace(product, 'bottom');
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

function getSharedFaceContacts(
  a: PlacementRect,
  b: PlacementRect,
  tolerance = TOUCH_TOLERANCE
) {
  const faces: FaceContact[] = [];

  if (edgesClose(a.x2, b.x1, tolerance) && rangesOverlap(a.y1, a.y2, b.y1, b.y2, tolerance)) {
    faces.push({
      leftFace: 'right',
      rightFace: 'left',
      overlapStart: Math.max(a.y1, b.y1),
      overlapEnd: Math.min(a.y2, b.y2),
    });
  }
  if (edgesClose(b.x2, a.x1, tolerance) && rangesOverlap(a.y1, a.y2, b.y1, b.y2, tolerance)) {
    faces.push({
      leftFace: 'left',
      rightFace: 'right',
      overlapStart: Math.max(a.y1, b.y1),
      overlapEnd: Math.min(a.y2, b.y2),
    });
  }
  if (edgesClose(a.y2, b.y1, tolerance) && rangesOverlap(a.x1, a.x2, b.x1, b.x2, tolerance)) {
    faces.push({
      leftFace: 'bottom',
      rightFace: 'top',
      overlapStart: Math.max(a.x1, b.x1),
      overlapEnd: Math.min(a.x2, b.x2),
    });
  }
  if (edgesClose(b.y2, a.y1, tolerance) && rangesOverlap(a.x1, a.x2, b.x1, b.x2, tolerance)) {
    faces.push({
      leftFace: 'top',
      rightFace: 'bottom',
      overlapStart: Math.max(a.x1, b.x1),
      overlapEnd: Math.min(a.x2, b.x2),
    });
  }

  return faces;
}

export function rectsTouch(
  a: PlacementRect,
  b: PlacementRect,
  tolerance = TOUCH_TOLERANCE
) {
  return getSharedFaceContacts(a, b, tolerance).length > 0;
}

function getFaceContactState(
  entry: LayoutRectEntry,
  face: BoxFace,
  overlapStart: number,
  overlapEnd: number
): FaceContactState {
  const cornerDefinition = getRotatedCornerDefinition(entry.box, entry.product, entry.rect);
  if (!cornerDefinition) {
    return 'valid';
  }

  if (face === cornerDefinition.standardFace) {
    return 'valid';
  }

  if (face === cornerDefinition.joinInterval.face) {
    return isIntervalWithinAllowedRange(
      overlapStart,
      overlapEnd,
      cornerDefinition.joinInterval.start,
      cornerDefinition.joinInterval.end
    )
      ? 'valid'
      : 'blocked_front_segment';
  }

  return 'forbidden_face';
}

function analyzeLayoutConnections(entries: LayoutRectEntry[], tolerance = TOUCH_TOLERANCE): LayoutAnalysis {
  const graph = new Map<string, Set<string>>();
  const joinedFaces = new Map<string, Set<BoxFace>>();
  const frontBlocked = new Set<string>();
  const connectionBlocked = new Set<string>();

  entries.forEach(({ box }) => {
    graph.set(box.id, new Set<string>());
    joinedFaces.set(box.id, new Set<BoxFace>());
  });

  for (let index = 0; index < entries.length; index += 1) {
    const current = entries[index];
    for (let otherIndex = index + 1; otherIndex < entries.length; otherIndex += 1) {
      const other = entries[otherIndex];
      const contacts = getSharedFaceContacts(current.rect, other.rect, tolerance);

      contacts.forEach((contact) => {
        const currentState = getFaceContactState(
          current,
          contact.leftFace,
          contact.overlapStart,
          contact.overlapEnd
        );
        const otherState = getFaceContactState(
          other,
          contact.rightFace,
          contact.overlapStart,
          contact.overlapEnd
        );

        if (currentState === 'valid' && otherState === 'valid') {
          graph.get(current.box.id)?.add(other.box.id);
          graph.get(other.box.id)?.add(current.box.id);
          joinedFaces.get(current.box.id)?.add(contact.leftFace);
          joinedFaces.get(other.box.id)?.add(contact.rightFace);

          if (!getConnectionProfile(current.product) && contact.leftFace === getFrontFace(current.product, current.box.rotation)) {
            frontBlocked.add(current.box.id);
          }
          if (!getConnectionProfile(other.product) && contact.rightFace === getFrontFace(other.product, other.box.rotation)) {
            frontBlocked.add(other.box.id);
          }
          return;
        }

        connectionBlocked.add(current.box.id);
        connectionBlocked.add(other.box.id);
      });
    }
  }

  return {
    graph,
    joinedFaces,
    frontBlocked,
    connectionBlocked,
  };
}

function getConnectedIdsFromGraph(graph: Map<string, Set<string>>, startId?: string) {
  const connected = new Set<string>();
  const seed = startId ?? graph.keys().next().value;
  if (!seed) {
    return connected;
  }

  const queue = [seed];
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current || connected.has(current)) continue;
    connected.add(current);
    queue.push(...(graph.get(current) ?? []));
  }

  return connected;
}

export function getJoinedFaces(entries: LayoutRectEntry[], tolerance = TOUCH_TOLERANCE) {
  return analyzeLayoutConnections(entries, tolerance).joinedFaces;
}

export function isFrontFaceExposed(
  box: ConfiguratorBoxPlacement,
  product: Product | null | undefined,
  joinedFaces: Map<string, Set<BoxFace>>
) {
  if (getConnectionProfile(product)) {
    return true;
  }
  return !joinedFaces.get(box.id)?.has(getFrontFace(product, box.rotation));
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
  const analysis = analyzeLayoutConnections(entries, tolerance);
  return getConnectedIdsFromGraph(analysis.graph, entries[0]?.box.id);
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
      x: roundPosition(rawX),
      y: roundPosition(rawY),
      snapped: false,
      overlaps: false,
      connected: true,
      connectionBlocked: false,
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
  const snappedX = xCandidate ? roundPosition(xCandidate.value) : baseX;

  const rectAfterX = getPlacementRect({ ...movingBox, x: snappedX, y: baseY }, movingProduct);
  const movingInsetsAfterX = getAnchorInsets({ ...movingBox, x: snappedX, y: baseY }, rectAfterX);
  const yCandidate = getBestCandidate(
    otherEntries.flatMap((entry) =>
      getSnapCandidates(baseY, 'y', movingInsetsAfterX, rectAfterX, entry.rect, threshold)
    )
  );
  const snappedY = yCandidate ? roundPosition(yCandidate.value) : baseY;

  const nextBox = { ...movingBox, x: snappedX, y: snappedY };
  const nextRect = getPlacementRect(nextBox, movingProduct);
  const overlaps = otherEntries.some((entry) => placementsOverlap(nextRect, entry.rect));
  const layoutEntries = buildLayoutRectEntries(
    boxes.map((box) => (box.id === movingBox.id ? nextBox : box)),
    productMap
  );
  const analysis = analyzeLayoutConnections(layoutEntries);
  const connected = getConnectedIdsFromGraph(analysis.graph, layoutEntries[0]?.box.id).size === layoutEntries.length;
  const connectionBlocked = analysis.connectionBlocked.has(nextBox.id);
  const frontBlocked = analysis.frontBlocked.has(nextBox.id);

  return {
    x: snappedX,
    y: snappedY,
    snapped: Boolean(xCandidate || yCandidate),
    overlaps,
    connected,
    connectionBlocked,
    frontBlocked,
    valid: !overlaps && connected && !connectionBlocked && !frontBlocked,
    guides: [xCandidate?.guide, yCandidate?.guide].filter((guide): guide is SnapGuide => Boolean(guide)),
  } satisfies CandidatePlacement;
}

export function getSuggestedPlacement(
  boxes: ConfiguratorBoxPlacement[],
  product: Product,
  productMap: Record<number, Product>,
  anchorBoxId?: string | null
) {
  const rotation = getDefaultBoxRotation(product);
  if (boxes.length === 0) {
    return { x: 0, y: 0, rotation };
  }

  const entries = buildLayoutRectEntries(boxes, productMap);
  const referenceBox = {
    id: 'candidate',
    product_id: product.id,
    x: 0,
    y: 0,
    rotation,
  } satisfies ConfiguratorBoxPlacement;
  const referenceRect = getPlacementRect(referenceBox, product);
  const movingInsets = getAnchorInsets(referenceBox, referenceRect);
  const anchorEntry =
    entries.find((entry) => entry.box.id === anchorBoxId) ??
    entries[entries.length - 1];
  const orderedEntries = [anchorEntry, ...entries.filter((entry) => entry.box.id !== anchorEntry.box.id)];

  for (const entry of orderedEntries) {
    const candidates = [
      {
        x: roundPosition(entry.rect.x2 - movingInsets.left),
        y: roundPosition(entry.rect.y1 - movingInsets.top),
      },
      {
        x: roundPosition(entry.rect.x1 - movingInsets.left),
        y: roundPosition(entry.rect.y2 - movingInsets.top),
      },
      {
        x: roundPosition(Math.max(0, entry.rect.x1 - movingInsets.right)),
        y: roundPosition(entry.rect.y1 - movingInsets.top),
      },
      {
        x: roundPosition(entry.rect.x1 - movingInsets.left),
        y: roundPosition(Math.max(0, entry.rect.y1 - movingInsets.bottom)),
      },
    ];

    for (const candidate of candidates) {
      const nextRect = getPlacementRect(
        {
          id: 'candidate',
          product_id: product.id,
          x: candidate.x,
          y: candidate.y,
          rotation,
        },
        product
      );
      const overlaps = entries.some((other) => placementsOverlap(nextRect, other.rect));
      if (!overlaps) {
        const nextBox = {
          id: 'candidate',
          product_id: product.id,
          x: candidate.x,
          y: candidate.y,
          rotation,
        } satisfies ConfiguratorBoxPlacement;
        const nextEntries = [...entries, { box: nextBox, product, rect: nextRect }];
        const analysis = analyzeLayoutConnections(nextEntries);
        const connected = getConnectedIdsFromGraph(analysis.graph, nextEntries[0]?.box.id).size === nextEntries.length;
        if (!analysis.connectionBlocked.has(nextBox.id) && !analysis.frontBlocked.has(nextBox.id) && connected) {
          return { ...candidate, rotation };
        }
      }
    }
  }

  const maxX = Math.max(...entries.map((entry) => entry.rect.x2));

  return {
    x: roundPosition(maxX),
    y: 0,
    rotation,
  };
}
