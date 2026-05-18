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
  frontFace: 'bottom' | 'left' | 'right';
  standardFace: 'left' | 'right' | 'bottom';
  joinStart: number;
  joinEnd: number;
  blockedStart: number;
  blockedEnd: number;
}

export type CornerOverlayKind = 'blocked_front' | 'joinable' | 'standard';

export interface CornerOverlaySegment {
  face: 'top' | 'bottom' | 'left' | 'right';
  kind: CornerOverlayKind;
  startRatio: number;
  endRatio: number;
  lengthMeters: number;
}

export interface CornerOverlayBarStyle {
  className: string;
  style: {
    left?: string;
    right?: string;
    top?: string;
    bottom?: string;
    width?: string;
    height?: string;
  };
}

export interface CornerOverlayLabelStyle {
  className: string;
  style: {
    left?: string;
    right?: string;
    top?: string;
    bottom?: string;
    transform?: string;
    transformOrigin?: string;
  };
  text: string;
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
  void rotation;
  return { width, length };
}

export function getBaseFrontFace(product?: Product | null): BoxFace {
  const cornerBaseDefinition = getCornerBaseDefinition(product);
  if (cornerBaseDefinition) {
    return cornerBaseDefinition.frontFace;
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

export function isCornerBoxProduct(product?: Product | null): boolean {
  return Boolean(product?.configurator_is_corner_box);
}

export function isCornerRotationLocked(product?: Product | null): boolean {
  return isCornerBoxProduct(product);
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
  const frontLength = Math.max(width, length);
  const blockedLength = Math.max(0, frontLength - joinLength);

  if (length > width) {
    if (profile === 'corner_left') {
      return {
        frontFace: 'right',
        standardFace: 'bottom',
        joinStart: 0,
        joinEnd: joinLength,
        blockedStart: joinLength,
        blockedEnd: frontLength,
      };
    }

    return {
      frontFace: 'left',
      standardFace: 'bottom',
      joinStart: 0,
      joinEnd: joinLength,
      blockedStart: joinLength,
      blockedEnd: frontLength,
    };
  }

  if (profile === 'corner_left') {
    return {
      frontFace: 'bottom',
      standardFace: 'left',
      joinStart: blockedLength,
      joinEnd: frontLength,
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
    blockedEnd: frontLength,
  };
}

function getCornerFaceLength(face: CornerBaseDefinition['frontFace'], width: number, length: number) {
  return face === 'bottom' ? width : length;
}

export function getCornerBlockedFrontLength(product: Product | null | undefined): number | null {
  const base = getCornerBaseDefinition(product);
  if (!base || base.blockedEnd - base.blockedStart <= EDGE_EPSILON) {
    return null;
  }
  const { width, length } = getNativeDimensions(product);
  return base.blockedEnd - base.blockedStart;
}

export function getCornerOverlaySegments(product: Product | null | undefined): CornerOverlaySegment[] {
  const base = getCornerBaseDefinition(product);
  if (!base) {
    return [];
  }

  const { width, length } = getNativeDimensions(product);
  if (width <= 0 || length <= 0) {
    return [];
  }

  const frontEdgeLength = getCornerFaceLength(base.frontFace, width, length);
  const standardEdgeLength = getCornerFaceLength(base.standardFace, width, length);
  const segments: CornerOverlaySegment[] = [];

  if (base.blockedEnd - base.blockedStart > EDGE_EPSILON) {
    segments.push({
      face: base.frontFace,
      kind: 'blocked_front',
      startRatio: base.blockedStart / frontEdgeLength,
      endRatio: base.blockedEnd / frontEdgeLength,
      lengthMeters: base.blockedEnd - base.blockedStart,
    });
  }

  if (base.joinEnd - base.joinStart > EDGE_EPSILON) {
    segments.push({
      face: base.frontFace,
      kind: 'joinable',
      startRatio: base.joinStart / frontEdgeLength,
      endRatio: base.joinEnd / frontEdgeLength,
      lengthMeters: base.joinEnd - base.joinStart,
    });
  }

  segments.push({
    face: base.standardFace,
    kind: 'standard',
    startRatio: 0,
    endRatio: 1,
    lengthMeters: standardEdgeLength,
  });

  return segments;
}

function getOverlayFaceLength(
  face: CornerOverlaySegment['face'],
  width: number,
  length: number
): number {
  return face === 'left' || face === 'right' ? length : width;
}

export function getStandardFrontOverlaySegment(
  product: Product | null | undefined
): CornerOverlaySegment | null {
  if (!product || getCornerBaseDefinition(product)) {
    return null;
  }

  const { width, length } = getNativeDimensions(product);
  if (width <= 0 || length <= 0) {
    return null;
  }

  const face = getBaseFrontFace(product);
  if (face !== 'top' && face !== 'bottom' && face !== 'left' && face !== 'right') {
    return null;
  }

  return {
    face,
    kind: 'blocked_front',
    startRatio: 0,
    endRatio: 1,
    lengthMeters: getOverlayFaceLength(face, width, length),
  };
}

const CORNER_OVERLAY_BAR_CLASS: Record<CornerOverlayKind, string> = {
  blocked_front: 'bg-emerald-500 shadow-[0_0_0_1px_rgba(6,78,59,0.55)]',
  joinable: 'bg-red-500/80 shadow-[0_0_0_1px_rgba(127,29,29,0.45)]',
  standard: 'bg-red-500/55 shadow-[0_0_0_1px_rgba(127,29,29,0.35)]',
};

function buildHorizontalOverlayStyle(
  edge: 'top' | 'bottom',
  startRatio: number,
  endRatio: number,
  thicknessPx: number
): CornerOverlayBarStyle['style'] {
  const span = Math.max(endRatio - startRatio, 0);
  return {
    left: `${startRatio * 100}%`,
    width: `${span * 100}%`,
    ...(edge === 'bottom' ? { bottom: '0' } : { top: '0' }),
    height: `${thicknessPx}px`,
  };
}

function buildVerticalOverlayStyle(
  face: 'left' | 'right',
  startRatio: number,
  endRatio: number,
  thicknessPx: number
): CornerOverlayBarStyle['style'] {
  const span = Math.max(endRatio - startRatio, 0);
  return {
    top: `${startRatio * 100}%`,
    height: `${span * 100}%`,
    ...(face === 'left' ? { left: '0' } : { right: '0' }),
    width: `${thicknessPx}px`,
  };
}

export function getCornerOverlayBarStyles(
  segment: CornerOverlaySegment,
  thicknessPx = 6
): CornerOverlayBarStyle {
  const startRatio = Math.min(segment.startRatio, segment.endRatio);
  const endRatio = Math.max(segment.startRatio, segment.endRatio);

  if (segment.face === 'bottom' || segment.face === 'top') {
    return {
      className: CORNER_OVERLAY_BAR_CLASS[segment.kind],
      style: buildHorizontalOverlayStyle(segment.face, startRatio, endRatio, thicknessPx),
    };
  }

  return {
    className: CORNER_OVERLAY_BAR_CLASS[segment.kind],
    style: buildVerticalOverlayStyle(segment.face, startRatio, endRatio, thicknessPx),
  };
}

export function getCornerBlockedFrontLabelStyle(
  segment: CornerOverlaySegment
): CornerOverlayLabelStyle | null {
  if (segment.kind !== 'blocked_front') {
    return null;
  }

  const centerRatio = (segment.startRatio + segment.endRatio) / 2;
  const lengthLabel = segment.lengthMeters.toFixed(1).replace(/\.0$/, '');

  if (segment.face === 'bottom') {
    return {
      className:
        'pointer-events-none absolute z-10 max-w-[90%] truncate rounded bg-emerald-950/90 px-1.5 py-0.5 text-[9px] font-semibold leading-none text-emerald-50',
      style: {
        left: `${centerRatio * 100}%`,
        bottom: '8px',
        transform: 'translateX(-50%)',
      },
      text: `Front ${lengthLabel}m`,
    };
  }

  if (segment.face === 'top') {
    return {
      className:
        'pointer-events-none absolute z-10 max-w-[90%] truncate rounded bg-emerald-950/90 px-1.5 py-0.5 text-[9px] font-semibold leading-none text-emerald-50',
      style: {
        left: `${centerRatio * 100}%`,
        top: '8px',
        transform: 'translateX(-50%)',
      },
      text: `Front ${lengthLabel}m`,
    };
  }

  if (segment.face === 'left') {
    return {
      className:
        'pointer-events-none absolute z-10 max-w-[90%] truncate rounded bg-emerald-950/90 px-1.5 py-0.5 text-[9px] font-semibold leading-none text-emerald-50',
      style: {
        top: `${centerRatio * 100}%`,
        left: '8px',
        transform: 'translateY(-50%) rotate(-90deg)',
        transformOrigin: 'left center',
      },
      text: `Front ${lengthLabel}m`,
    };
  }

  return {
    className:
      'pointer-events-none absolute z-10 max-w-[90%] truncate rounded bg-emerald-950/90 px-1.5 py-0.5 text-[9px] font-semibold leading-none text-emerald-50',
    style: {
      top: `${centerRatio * 100}%`,
      right: '8px',
      transform: 'translateY(-50%) rotate(90deg)',
      transformOrigin: 'right center',
    },
    text: `Front ${lengthLabel}m`,
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

function getFaceSegmentPoints(params: {
  face: CornerBaseDefinition['frontFace'] | CornerBaseDefinition['standardFace'];
  start: number;
  end: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
}) {
  const { face, start, end, left, right, top, bottom } = params;
  if (face === 'bottom') {
    return {
      startPoint: { x: left + start, y: bottom },
      endPoint: { x: left + end, y: bottom },
    };
  }
  if (face === 'left') {
    return {
      startPoint: { x: left, y: top + start },
      endPoint: { x: left, y: top + end },
    };
  }
  return {
    startPoint: { x: right, y: top + start },
    endPoint: { x: right, y: top + end },
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

  const joinSegment = getFaceSegmentPoints({
    face: base.frontFace,
    start: base.joinStart,
    end: base.joinEnd,
    left,
    right,
    top,
    bottom,
  });
  const blockedSegment =
    base.blockedEnd - base.blockedStart > EDGE_EPSILON
      ? getFaceSegmentPoints({
          face: base.frontFace,
          start: base.blockedStart,
          end: base.blockedEnd,
          left,
          right,
          top,
          bottom,
        })
      : null;
  const standardSegment = getFaceSegmentPoints({
    face: base.standardFace,
    start: 0,
    end: base.standardFace === 'bottom' ? width : length,
    left,
    right,
    top,
    bottom,
  });

  const joinStartPoint = rotateSegmentPoint(joinSegment.startPoint.x, joinSegment.startPoint.y);
  const joinEndPoint = rotateSegmentPoint(joinSegment.endPoint.x, joinSegment.endPoint.y);
  const joinInterval = getIntervalFromSegment(joinStartPoint, joinEndPoint, rect);

  const blockedInterval =
    blockedSegment
      ? getIntervalFromSegment(
          rotateSegmentPoint(blockedSegment.startPoint.x, blockedSegment.startPoint.y),
          rotateSegmentPoint(blockedSegment.endPoint.x, blockedSegment.endPoint.y),
          rect
        )
      : null;

  const standardInterval = getIntervalFromSegment(
    rotateSegmentPoint(standardSegment.startPoint.x, standardSegment.startPoint.y),
    rotateSegmentPoint(standardSegment.endPoint.x, standardSegment.endPoint.y),
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
  if (isCornerRotationLocked(product)) {
    return 0;
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

export interface MainLayoutEnvelope {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  widthM: number;
  heightM: number;
  boxCount: number;
}

export function formatLayoutDimensionMeters(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : String(rounded).replace(/\.?0+$/, '');
}

export function getConnectedComponents(
  entries: LayoutRectEntry[],
  tolerance = TOUCH_TOLERANCE
): Set<string>[] {
  if (entries.length === 0) return [];

  const { graph } = analyzeLayoutConnections(entries, tolerance);
  const visited = new Set<string>();
  const components: Set<string>[] = [];

  for (const entry of entries) {
    if (visited.has(entry.box.id)) continue;
    const component = getConnectedIdsFromGraph(graph, entry.box.id);
    component.forEach((id) => visited.add(id));
    components.push(component);
  }

  return components;
}

export function getLargestConnectedComponentIds(
  entries: LayoutRectEntry[],
  tolerance = TOUCH_TOLERANCE
): Set<string> {
  const components = getConnectedComponents(entries, tolerance);
  if (components.length === 0) return new Set<string>();

  const entryById = new Map(entries.map((entry) => [entry.box.id, entry]));

  const componentArea = (ids: Set<string>) =>
    [...ids].reduce((sum, id) => {
      const entry = entryById.get(id);
      if (!entry) return sum;
      return sum + entry.rect.boundsWidth * entry.rect.boundsHeight;
    }, 0);

  return components.reduce((best, current) => {
    if (current.size > best.size) return current;
    if (current.size < best.size) return best;
    return componentArea(current) > componentArea(best) ? current : best;
  });
}

export function getMainLayoutEnvelope(
  entries: LayoutRectEntry[],
  tolerance = TOUCH_TOLERANCE
): MainLayoutEnvelope {
  const mainIds = getLargestConnectedComponentIds(entries, tolerance);
  const mainEntries = entries.filter((entry) => mainIds.has(entry.box.id));

  if (mainEntries.length === 0) {
    return { minX: 0, minY: 0, maxX: 0, maxY: 0, widthM: 0, heightM: 0, boxCount: 0 };
  }

  const minX = Math.min(...mainEntries.map((entry) => entry.rect.x1));
  const minY = Math.min(...mainEntries.map((entry) => entry.rect.y1));
  const maxX = Math.max(...mainEntries.map((entry) => entry.rect.x2));
  const maxY = Math.max(...mainEntries.map((entry) => entry.rect.y2));

  return {
    minX,
    minY,
    maxX,
    maxY,
    widthM: maxX - minX,
    heightM: maxY - minY,
    boxCount: mainEntries.length,
  };
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
  const touchesOthers = otherEntries.some((entry) => rectsTouch(nextRect, entry.rect));

  return {
    x: snappedX,
    y: snappedY,
    snapped: Boolean(xCandidate || yCandidate),
    overlaps,
    connected,
    connectionBlocked,
    frontBlocked,
    valid: !overlaps && !connectionBlocked && !frontBlocked && (!touchesOthers || connected),
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
