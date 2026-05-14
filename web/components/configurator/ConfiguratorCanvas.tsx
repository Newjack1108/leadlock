'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Minus, Move, Plus, RotateCcw, Search } from 'lucide-react';

import type { ConfiguratorBoxPlacement, Product } from '@/lib/types';
import {
  buildLayoutRectEntries,
  findPlacementCandidate,
  getCanvasBounds,
  getFootprint,
  type CandidatePlacement,
} from '@/lib/configurator/geometry';
import { cn } from '@/lib/utils';

const SCALE = 40;
const MIN_ZOOM = 0.35;
const MAX_ZOOM = 2.25;
const ZOOM_STEP = 0.15;

interface ConfiguratorCanvasProps {
  boxes: ConfiguratorBoxPlacement[];
  productMap: Record<number, Product>;
  selectedBoxId: string | null;
  onSelect: (boxId: string) => void;
  onMoveBox: (boxId: string, nextBox: Pick<ConfiguratorBoxPlacement, 'x' | 'y'>) => void;
  onRotateBox: (boxId: string, rotation: number) => void;
}

interface DragState {
  boxId: string;
  pointerId: number;
  offsetX: number;
  offsetY: number;
}

interface PanState {
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startPanX: number;
  startPanY: number;
}

interface RotateState {
  boxId: string;
  pointerId: number;
}

interface RotationCandidate {
  rotation: number;
  overlaps: boolean;
  connected: boolean;
  valid: boolean;
}

function clampZoom(value: number) {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Number(value.toFixed(2))));
}

function normalizeRotation(value: number) {
  return Number((((value % 360) + 360) % 360).toFixed(1));
}

export default function ConfiguratorCanvas({
  boxes,
  productMap,
  selectedBoxId,
  onSelect,
  onMoveBox,
  onRotateBox,
}: ConfiguratorCanvasProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [dragCandidate, setDragCandidate] = useState<CandidatePlacement | null>(null);
  const [rotateState, setRotateState] = useState<RotateState | null>(null);
  const [rotationCandidate, setRotationCandidate] = useState<RotationCandidate | null>(null);
  const [panState, setPanState] = useState<PanState | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 24, y: 24 });
  const [hasManualView, setHasManualView] = useState(false);

  const renderBoxes = useMemo(() => {
    if (rotateState && rotationCandidate) {
      return boxes.map((box) =>
        box.id === rotateState.boxId ? { ...box, rotation: rotationCandidate.rotation } : box
      );
    }
    if (dragState && dragCandidate) {
      return boxes.map((box) =>
        box.id === dragState.boxId ? { ...box, x: dragCandidate.x, y: dragCandidate.y } : box
      );
    }
    return boxes;
  }, [boxes, dragCandidate, dragState, rotateState, rotationCandidate]);

  const rectEntries = useMemo(
    () => buildLayoutRectEntries(renderBoxes, productMap),
    [renderBoxes, productMap]
  );

  const bounds = getCanvasBounds(rectEntries.map((entry) => entry.rect));
  const contentWidth = bounds.width * SCALE;
  const contentHeight = bounds.height * SCALE;

  const toCanvasPosition = (value: number, min: number) => (value - min + bounds.padding) * SCALE;

  const fitToViewport = useCallback((manual = false) => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const viewportWidth = viewport.clientWidth - 24;
    const viewportHeight = viewport.clientHeight - 24;
    if (viewportWidth <= 0 || viewportHeight <= 0) return;

    const nextZoom = clampZoom(Math.min(viewportWidth / contentWidth, viewportHeight / contentHeight));
    setZoom(nextZoom);
    setPan({
      x: (viewport.clientWidth - contentWidth * nextZoom) / 2,
      y: (viewport.clientHeight - contentHeight * nextZoom) / 2,
    });
    setHasManualView(manual);
  }, [contentHeight, contentWidth]);

  useEffect(() => {
    if (hasManualView) return;
    fitToViewport(false);
  }, [fitToViewport, hasManualView]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || typeof ResizeObserver === 'undefined') return undefined;

    const observer = new ResizeObserver(() => {
      if (!hasManualView) {
        fitToViewport(false);
      }
    });

    observer.observe(viewport);
    return () => observer.disconnect();
  }, [fitToViewport, hasManualView]);

  const zoomAroundPoint = (nextZoomRaw: number, clientX?: number, clientY?: number) => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const nextZoom = clampZoom(nextZoomRaw);
    if (nextZoom === zoom) return;

    const viewportRect = viewport.getBoundingClientRect();
    const anchorX = clientX ?? viewportRect.left + viewport.clientWidth / 2;
    const anchorY = clientY ?? viewportRect.top + viewport.clientHeight / 2;
    const localX = anchorX - viewportRect.left;
    const localY = anchorY - viewportRect.top;
    const worldX = (localX - pan.x) / zoom;
    const worldY = (localY - pan.y) / zoom;

    setZoom(nextZoom);
    setPan({
      x: localX - worldX * nextZoom,
      y: localY - worldY * nextZoom,
    });
    setHasManualView(true);
  };

  const getLayoutPoint = (clientX: number, clientY: number) => {
    const viewportRect = viewportRef.current?.getBoundingClientRect();
    if (!viewportRect) return { x: 0, y: 0 };

    const scaledX = (clientX - viewportRect.left - pan.x) / zoom;
    const scaledY = (clientY - viewportRect.top - pan.y) / zoom;

    return {
      x: scaledX / SCALE + bounds.minX - bounds.padding,
      y: scaledY / SCALE + bounds.minY - bounds.padding,
    };
  };

  const getRotationForPointer = (box: ConfiguratorBoxPlacement, clientX: number, clientY: number) => {
    const product = productMap[box.product_id];
    if (!product) return box.rotation;
    const point = getLayoutPoint(clientX, clientY);
    const { width, length } = getFootprint(product, box.rotation);
    const centerX = Number(box.x) + width / 2;
    const centerY = Number(box.y) + length / 2;
    const angle = (Math.atan2(point.y - centerY, point.x - centerX) * 180) / Math.PI + 90;
    return normalizeRotation(angle);
  };

  const getRotationPreview = (box: ConfiguratorBoxPlacement, rotation: number) => {
    const candidate = findPlacementCandidate({
      movingBox: { ...box, rotation },
      rawX: box.x,
      rawY: box.y,
      boxes,
      productMap,
      threshold: 0,
    });
    return {
      rotation,
      overlaps: candidate.overlaps,
      connected: candidate.connected,
      valid: candidate.valid,
    } satisfies RotationCandidate;
  };

  const finalizeDrag = () => {
    if (dragState && dragCandidate?.valid) {
      onMoveBox(dragState.boxId, { x: dragCandidate.x, y: dragCandidate.y });
    }
    setDragState(null);
    setDragCandidate(null);
  };

  const finalizeRotation = () => {
    if (rotateState && rotationCandidate?.valid) {
      onRotateBox(rotateState.boxId, rotationCandidate.rotation);
    }
    setRotateState(null);
    setRotationCandidate(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Move className="h-4 w-4" />
          <span>Drag background to pan. Use mouse wheel or controls to zoom.</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="min-w-14 text-right text-sm font-medium text-muted-foreground">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            className="rounded-md border px-2 py-1 text-sm hover:bg-accent"
            onClick={() => zoomAroundPoint(zoom - ZOOM_STEP)}
            aria-label="Zoom out"
          >
            <Minus className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="rounded-md border px-2 py-1 text-sm hover:bg-accent"
            onClick={() => zoomAroundPoint(zoom + ZOOM_STEP)}
            aria-label="Zoom in"
          >
            <Plus className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="rounded-md border px-3 py-1 text-sm hover:bg-accent"
            onClick={() => fitToViewport(true)}
          >
            <Search className="mr-1 inline h-4 w-4" />
            Fit
          </button>
          <button
            type="button"
            className="rounded-md border px-3 py-1 text-sm hover:bg-accent"
            onClick={() => {
              setZoom(1);
              setPan({ x: 24, y: 24 });
              setHasManualView(true);
            }}
          >
            <RotateCcw className="mr-1 inline h-4 w-4" />
            Reset
          </button>
        </div>
      </div>

      <div
        ref={viewportRef}
        className={cn(
          'relative overflow-hidden rounded-md border bg-muted/20',
          panState ? 'cursor-grabbing' : rotateState ? 'cursor-crosshair' : 'cursor-grab'
        )}
        style={{ height: '72vh', minHeight: 560 }}
        onWheel={(event) => {
          event.preventDefault();
          const delta = event.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
          zoomAroundPoint(zoom + delta, event.clientX, event.clientY);
        }}
      >
        <div className="absolute left-0 top-0" style={{ transform: `translate(${pan.x}px, ${pan.y}px)` }}>
          <div
            className="origin-top-left"
            style={{
              transform: `scale(${zoom})`,
            }}
          >
            <div
              className="relative rounded-md border bg-background"
              style={{
                width: `${contentWidth}px`,
                height: `${contentHeight}px`,
                backgroundImage:
                  'linear-gradient(to right, rgba(148,163,184,0.2) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.2) 1px, transparent 1px)',
                backgroundSize: `${SCALE}px ${SCALE}px`,
              }}
              onPointerDown={(event) => {
                if (event.target !== event.currentTarget || event.button !== 0 || dragState || rotateState) return;
                setPanState({
                  pointerId: event.pointerId,
                  startClientX: event.clientX,
                  startClientY: event.clientY,
                  startPanX: pan.x,
                  startPanY: pan.y,
                });
                event.currentTarget.setPointerCapture(event.pointerId);
              }}
              onPointerMove={(event) => {
                if (!panState || panState.pointerId !== event.pointerId) return;
                setPan({
                  x: panState.startPanX + (event.clientX - panState.startClientX),
                  y: panState.startPanY + (event.clientY - panState.startClientY),
                });
                setHasManualView(true);
              }}
              onPointerUp={(event) => {
                if (!panState || panState.pointerId !== event.pointerId) return;
                if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                  event.currentTarget.releasePointerCapture(event.pointerId);
                }
                setPanState(null);
              }}
              onPointerCancel={(event) => {
                if (!panState || panState.pointerId !== event.pointerId) return;
                if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                  event.currentTarget.releasePointerCapture(event.pointerId);
                }
                setPanState(null);
              }}
              onClick={() => {
                if (dragState) finalizeDrag();
                if (rotateState) finalizeRotation();
              }}
            >
              {dragCandidate?.guides.map((guide, index) => {
                if (guide.orientation === 'vertical') {
                  return (
                    <div
                      key={`guide-v-${index}`}
                      className="pointer-events-none absolute border-l border-dashed border-primary/70"
                      style={{
                        left: `${toCanvasPosition(guide.position, bounds.minX)}px`,
                        top: `${toCanvasPosition(guide.start, bounds.minY)}px`,
                        height: `${(guide.end - guide.start) * SCALE}px`,
                      }}
                    />
                  );
                }
                return (
                  <div
                    key={`guide-h-${index}`}
                    className="pointer-events-none absolute border-t border-dashed border-primary/70"
                    style={{
                      top: `${toCanvasPosition(guide.position, bounds.minY)}px`,
                      left: `${toCanvasPosition(guide.start, bounds.minX)}px`,
                      width: `${(guide.end - guide.start) * SCALE}px`,
                    }}
                  />
                );
              })}

              {rectEntries.map(({ box, product, rect }) => {
                const isDragging = dragState?.boxId === box.id;
                const isRotating = rotateState?.boxId === box.id;
                const activeInvalid =
                  (isDragging && dragCandidate && !dragCandidate.valid) ||
                  (isRotating && rotationCandidate && !rotationCandidate.valid);

                return (
                <button
                  key={box.id}
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(box.id);
                  }}
                  onPointerDown={(event) => {
                    if (rotateState) return;
                    if (event.button !== 0) return;
                    event.stopPropagation();
                    const point = getLayoutPoint(event.clientX, event.clientY);
                    setDragState({
                      boxId: box.id,
                      pointerId: event.pointerId,
                      offsetX: point.x - box.x,
                      offsetY: point.y - box.y,
                    });
                    setDragCandidate({
                      x: box.x,
                      y: box.y,
                      snapped: false,
                      overlaps: false,
                      connected: true,
                      valid: true,
                      guides: [],
                    });
                    onSelect(box.id);
                    event.currentTarget.setPointerCapture(event.pointerId);
                  }}
                  onPointerMove={(event) => {
                    if (rotateState) return;
                    if (!dragState || dragState.boxId !== box.id) return;
                    const point = getLayoutPoint(event.clientX, event.clientY);
                    const candidate = findPlacementCandidate({
                      movingBox: box,
                      rawX: point.x - dragState.offsetX,
                      rawY: point.y - dragState.offsetY,
                      boxes,
                      productMap,
                    });
                    setDragCandidate(candidate);
                  }}
                  onPointerUp={(event) => {
                    if (dragState?.boxId !== box.id || dragState.pointerId !== event.pointerId) return;
                    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                      event.currentTarget.releasePointerCapture(event.pointerId);
                    }
                    finalizeDrag();
                  }}
                  onPointerCancel={(event) => {
                    if (dragState?.boxId !== box.id || dragState.pointerId !== event.pointerId) return;
                    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                      event.currentTarget.releasePointerCapture(event.pointerId);
                    }
                    setDragState(null);
                    setDragCandidate(null);
                  }}
                  className={cn(
                    'absolute touch-none rounded-md border text-left text-xs font-medium transition-colors',
                    activeInvalid
                      ? 'cursor-grabbing border-red-500 bg-red-100/90 text-red-900 shadow-lg'
                      : isDragging || isRotating
                        ? 'cursor-grabbing border-primary bg-primary/20 text-primary shadow-lg'
                        : selectedBoxId === box.id
                          ? 'cursor-grab border-primary bg-primary/15 text-primary shadow-sm'
                          : 'cursor-grab border-slate-300 bg-slate-100 text-slate-700 hover:bg-slate-200'
                  )}
                  style={{
                    left: `${toCanvasPosition(rect.centerX, bounds.minX)}px`,
                    top: `${toCanvasPosition(rect.centerY, bounds.minY)}px`,
                    width: `${Math.max(rect.boxWidth * SCALE, 48)}px`,
                    height: `${Math.max(rect.boxLength * SCALE, 48)}px`,
                    transform: `translate(-50%, -50%) rotate(${box.rotation}deg)`,
                  }}
                >
                  {selectedBoxId === box.id && (
                    <span
                      className="absolute left-1/2 top-0 z-20 flex h-7 w-7 -translate-x-1/2 -translate-y-[calc(100%+10px)] items-center justify-center rounded-full border border-primary/60 bg-background text-primary shadow-sm"
                      onPointerDown={(event) => {
                        if (event.button !== 0) return;
                        event.stopPropagation();
                        const rotation = getRotationForPointer(box, event.clientX, event.clientY);
                        setDragState(null);
                        setDragCandidate(null);
                        setRotateState({
                          boxId: box.id,
                          pointerId: event.pointerId,
                        });
                        setRotationCandidate(getRotationPreview(box, rotation));
                        onSelect(box.id);
                        event.currentTarget.setPointerCapture(event.pointerId);
                      }}
                      onPointerMove={(event) => {
                        if (!rotateState || rotateState.boxId !== box.id || rotateState.pointerId !== event.pointerId) {
                          return;
                        }
                        const rotation = getRotationForPointer(box, event.clientX, event.clientY);
                        setRotationCandidate(getRotationPreview(box, rotation));
                      }}
                      onPointerUp={(event) => {
                        if (!rotateState || rotateState.boxId !== box.id || rotateState.pointerId !== event.pointerId) {
                          return;
                        }
                        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                          event.currentTarget.releasePointerCapture(event.pointerId);
                        }
                        finalizeRotation();
                      }}
                      onPointerCancel={(event) => {
                        if (!rotateState || rotateState.boxId !== box.id || rotateState.pointerId !== event.pointerId) {
                          return;
                        }
                        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                          event.currentTarget.releasePointerCapture(event.pointerId);
                        }
                        setRotateState(null);
                        setRotationCandidate(null);
                      }}
                    >
                      <span className="pointer-events-none text-sm">↻</span>
                    </span>
                  )}
                  <span className="pointer-events-none absolute inset-0">
                    <span className="absolute left-1/2 top-2 flex -translate-x-1/2 items-center gap-1 rounded-full bg-background/85 px-2 py-0.5 text-[10px] font-semibold shadow-sm">
                      <span className="block h-1.5 w-6 rounded-full bg-sky-500" />
                      <span>Front</span>
                    </span>
                  </span>
                  <span
                    className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center px-2 text-center"
                    style={{ transform: `rotate(${-box.rotation}deg)` }}
                  >
                    <span className="max-w-full truncate text-[11px] font-semibold leading-tight">
                      {product.name}
                    </span>
                    <span className="mt-1 text-[10px] text-muted-foreground">
                      {rect.boxWidth} x {rect.boxLength}
                    </span>
                    {isRotating && rotationCandidate && (
                      <span className="mt-1 rounded-full bg-background/85 px-2 py-0.5 text-[10px] font-semibold text-foreground shadow-sm">
                        {rotationCandidate.rotation.toFixed(1)}°
                      </span>
                    )}
                  </span>
                </button>
              )})}

              {rectEntries.length === 0 && (
                <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
                  Add configurator items from the catalogue to start the layout.
                </div>
              )}

              {((dragState && dragCandidate && !dragCandidate.valid) ||
                (rotateState && rotationCandidate && !rotationCandidate.valid)) && (
                <div className="pointer-events-none absolute bottom-4 left-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 shadow-sm">
                  {(dragCandidate?.overlaps || rotationCandidate?.overlaps)
                    ? 'This position overlaps another box.'
                    : 'This position breaks the connected layout.'}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
