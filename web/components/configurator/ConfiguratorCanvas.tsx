'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Minus, Move, Plus, RotateCcw, RotateCw, Search, Trash2 } from 'lucide-react';

import type { ConfiguratorBoxPlacement, Product } from '@/lib/types';
import {
  buildLayoutRectEntries,
  findPlacementCandidate,
  getCanvasBounds,
  getCornerBlockedFrontLabelStyle,
  getCornerOverlayBarStyles,
  getCornerOverlaySegments,
  getStandardFrontOverlaySegment,
  isCornerRotationLocked,
  normalizeRotation,
  type CandidatePlacement,
  type CanvasBounds,
} from '@/lib/configurator/geometry';
import { cn } from '@/lib/utils';

const SCALE = 40;
const MIN_ZOOM = 0.35;
const MAX_ZOOM = 2.25;
const ZOOM_STEP = 0.15;

interface ConfiguratorCanvasProps {
  boxes: ConfiguratorBoxPlacement[];
  productMap: Record<number, Product>;
  selectedBoxId?: string | null;
  onSelect?: (boxId: string) => void;
  onMoveBox?: (boxId: string, nextBox: Pick<ConfiguratorBoxPlacement, 'x' | 'y'>) => void;
  onRotateBox?: (boxId: string, rotation: number) => void;
  onRemoveBox?: (boxId: string) => void;
  readOnly?: boolean;
  viewportHeight?: string;
}

interface InteractionSnapshot {
  bounds: CanvasBounds;
  pan: { x: number; y: number };
  zoom: number;
}

interface DragState {
  boxId: string;
  pointerId: number;
  offsetX: number;
  offsetY: number;
  snapshot: InteractionSnapshot;
}

interface PanState {
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startPanX: number;
  startPanY: number;
}

function clampZoom(value: number) {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Number(value.toFixed(2))));
}

export default function ConfiguratorCanvas({
  boxes,
  productMap,
  selectedBoxId = null,
  onSelect,
  onMoveBox,
  onRotateBox,
  onRemoveBox,
  readOnly = false,
  viewportHeight = '72vh',
}: ConfiguratorCanvasProps) {
  const interactive = !readOnly && Boolean(onMoveBox);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [dragCandidate, setDragCandidate] = useState<CandidatePlacement | null>(null);
  const [panState, setPanState] = useState<PanState | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 24, y: 24 });
  const [hasManualView, setHasManualView] = useState(false);

  const renderBoxes = useMemo(() => {
    if (dragState && dragCandidate) {
      return boxes.map((box) =>
        box.id === dragState.boxId ? { ...box, x: dragCandidate.x, y: dragCandidate.y } : box
      );
    }
    return boxes;
  }, [boxes, dragCandidate, dragState]);

  const rectEntries = useMemo(
    () => buildLayoutRectEntries(renderBoxes, productMap),
    [renderBoxes, productMap]
  );

  const bounds = getCanvasBounds(rectEntries.map((entry) => entry.rect));
  const interactionSnapshot = dragState?.snapshot ?? null;
  const displayBounds = interactionSnapshot?.bounds ?? bounds;
  const displayPan = interactionSnapshot?.pan ?? pan;
  const displayZoom = interactionSnapshot?.zoom ?? zoom;
  const layoutContentWidth = bounds.width * SCALE;
  const layoutContentHeight = bounds.height * SCALE;
  const contentWidth = displayBounds.width * SCALE;
  const contentHeight = displayBounds.height * SCALE;
  const isInteracting = Boolean(dragState);

  const toCanvasPosition = (value: number, min: number) => (value - min + displayBounds.padding) * SCALE;

  const fitToViewport = useCallback((manual = false) => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const viewportWidth = viewport.clientWidth - 24;
    const viewportHeight = viewport.clientHeight - 24;
    if (viewportWidth <= 0 || viewportHeight <= 0) return;

    const fitZoom = Math.min(viewportWidth / layoutContentWidth, viewportHeight / layoutContentHeight);
    const nextZoom = clampZoom(manual ? fitZoom : Math.min(1, fitZoom));
    setZoom(nextZoom);
    setPan({
      x: (viewport.clientWidth - layoutContentWidth * nextZoom) / 2,
      y: (viewport.clientHeight - layoutContentHeight * nextZoom) / 2,
    });
    setHasManualView(manual);
  }, [layoutContentHeight, layoutContentWidth]);

  const resetView = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    setZoom(1);
    setPan({
      x: (viewport.clientWidth - layoutContentWidth) / 2,
      y: (viewport.clientHeight - layoutContentHeight) / 2,
    });
    setHasManualView(true);
  }, [layoutContentHeight, layoutContentWidth]);

  useEffect(() => {
    if (hasManualView || isInteracting) return;
    const frameId = window.requestAnimationFrame(() => {
      fitToViewport(false);
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [fitToViewport, hasManualView, isInteracting]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || typeof ResizeObserver === 'undefined') return undefined;

    const observer = new ResizeObserver(() => {
      if (!hasManualView && !isInteracting) {
        fitToViewport(false);
      }
    });

    observer.observe(viewport);
    return () => observer.disconnect();
  }, [fitToViewport, hasManualView, isInteracting]);

  const zoomAroundPoint = (nextZoomRaw: number, clientX?: number, clientY?: number) => {
    if (isInteracting) return;
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

  const getInteractionSnapshot = (): InteractionSnapshot => ({
    bounds,
    pan: { ...pan },
    zoom,
  });

  const getLayoutPoint = (clientX: number, clientY: number, snapshot?: InteractionSnapshot) => {
    const viewportRect = viewportRef.current?.getBoundingClientRect();
    if (!viewportRect) return { x: 0, y: 0 };
    const activeBounds = snapshot?.bounds ?? bounds;
    const activePan = snapshot?.pan ?? pan;
    const activeZoom = snapshot?.zoom ?? zoom;

    const scaledX = (clientX - viewportRect.left - activePan.x) / activeZoom;
    const scaledY = (clientY - viewportRect.top - activePan.y) / activeZoom;

    return {
      x: scaledX / SCALE + activeBounds.minX - activeBounds.padding,
      y: scaledY / SCALE + activeBounds.minY - activeBounds.padding,
    };
  };

  const finalizeDrag = () => {
    if (dragState && dragCandidate?.valid && onMoveBox) {
      onMoveBox(dragState.boxId, { x: dragCandidate.x, y: dragCandidate.y });
    }
    setDragState(null);
    setDragCandidate(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Move className="h-4 w-4" />
          <span>
            {readOnly
              ? 'Drag the background to pan. Use + / − or Fit to zoom.'
              : 'Drag background to pan. Use + / − or Fit to zoom.'}
          </span>
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
            onClick={resetView}
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
          panState ? 'cursor-grabbing' : 'cursor-grab'
        )}
        style={{ height: viewportHeight, minHeight: readOnly ? 360 : 560 }}
      >
        <div
          className="absolute left-0 top-0"
          style={{ transform: `translate(${displayPan.x}px, ${displayPan.y}px)` }}
        >
          <div
            className="origin-top-left"
            style={{
              transform: `scale(${displayZoom})`,
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
                if (event.target !== event.currentTarget || event.button !== 0 || dragState) return;
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
              }}
            >
              {dragCandidate?.guides.map((guide, index) => {
                if (guide.orientation === 'vertical') {
                  return (
                    <div
                      key={`guide-v-${index}`}
                      className="pointer-events-none absolute border-l border-dashed border-primary/70"
                      style={{
                        left: `${toCanvasPosition(guide.position, displayBounds.minX)}px`,
                        top: `${toCanvasPosition(guide.start, displayBounds.minY)}px`,
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
                      top: `${toCanvasPosition(guide.position, displayBounds.minY)}px`,
                      left: `${toCanvasPosition(guide.start, displayBounds.minX)}px`,
                      width: `${(guide.end - guide.start) * SCALE}px`,
                    }}
                  />
                );
              })}

              {rectEntries.map(({ box, product, rect }) => {
                const isDragging = dragState?.boxId === box.id;
                const activeInvalid = isDragging && dragCandidate && !dragCandidate.valid;
                const boxPixelWidth = rect.boxWidth * SCALE;
                const boxPixelHeight = rect.boxLength * SCALE;
                const showDimensions = boxPixelWidth >= 90 && boxPixelHeight >= 86;
                const compactLabel = boxPixelWidth < 90 || boxPixelHeight < 64;
                const cornerOverlaySegments = getCornerOverlaySegments(product);
                const standardFrontSegment = getStandardFrontOverlaySegment(product);
                const edgeOverlaySegments = cornerOverlaySegments.length
                  ? cornerOverlaySegments
                  : standardFrontSegment
                    ? [standardFrontSegment]
                    : [];
                const showEdgeOverlays = edgeOverlaySegments.length > 0;
                const rotationLocked = isCornerRotationLocked(product);
                const blockedFrontLabelSegment = edgeOverlaySegments.find(
                  (segment) => segment.kind === 'blocked_front'
                );
                const blockedFrontLabelStyle = blockedFrontLabelSegment
                  ? getCornerBlockedFrontLabelStyle(blockedFrontLabelSegment)
                  : null;
                const showBlockedFrontLabel =
                  Boolean(blockedFrontLabelStyle) && boxPixelWidth >= 88 && boxPixelHeight >= 64;
                const overlayThickness = compactLabel ? 4 : 6;

                const boxStyle = {
                  left: `${toCanvasPosition(rect.centerX, displayBounds.minX)}px`,
                  top: `${toCanvasPosition(rect.centerY, displayBounds.minY)}px`,
                  width: `${rect.boxWidth * SCALE}px`,
                  height: `${rect.boxLength * SCALE}px`,
                  transform: `translate(-50%, -50%) rotate(${box.rotation}deg)`,
                };
                const boxClassName = cn(
                  'absolute overflow-visible rounded-md border text-left text-xs font-medium transition-colors',
                  readOnly
                    ? 'pointer-events-none border-slate-300 bg-slate-100 text-slate-700'
                    : activeInvalid
                      ? 'touch-none cursor-grabbing border-red-500 bg-red-100/90 text-red-900 shadow-lg'
                      : isDragging
                        ? 'touch-none cursor-grabbing border-primary bg-primary/20 text-primary shadow-lg'
                        : selectedBoxId === box.id
                          ? 'touch-none cursor-grab border-primary bg-primary/15 text-primary shadow-sm'
                          : 'touch-none cursor-grab border-slate-300 bg-slate-100 text-slate-700 hover:bg-slate-200'
                );

                const boxContent = (
                  <>
                  {selectedBoxId === box.id && !readOnly && onRotateBox && onRemoveBox && (
                    <span
                      className="absolute left-1/2 top-0 z-20 flex items-center gap-2"
                      style={{
                        transform: `translate(-50%, calc(-100% - 10px)) rotate(${-box.rotation}deg)`,
                      }}
                    >
                      {!rotationLocked && (
                        <>
                          <span
                            className="flex h-7 w-7 items-center justify-center rounded-full border border-primary/60 bg-background text-primary shadow-sm"
                            onPointerCancel={(event) => {
                              event.stopPropagation();
                            }}
                            onPointerDown={(event) => {
                              event.stopPropagation();
                            }}
                            onClick={(event) => {
                              event.stopPropagation();
                              onRotateBox(box.id, normalizeRotation(box.rotation - 90));
                            }}
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                          </span>
                          <span
                            className="flex h-7 w-7 items-center justify-center rounded-full border border-primary/60 bg-background text-primary shadow-sm"
                            onPointerCancel={(event) => {
                              event.stopPropagation();
                            }}
                            onPointerDown={(event) => {
                              event.stopPropagation();
                            }}
                            onClick={(event) => {
                              event.stopPropagation();
                              onRotateBox(box.id, normalizeRotation(box.rotation + 90));
                            }}
                          >
                            <RotateCw className="h-3.5 w-3.5" />
                          </span>
                        </>
                      )}
                      <span
                        className="flex h-7 w-7 items-center justify-center rounded-full border border-red-300 bg-background text-red-600 shadow-sm"
                        onPointerDown={(event) => {
                          event.stopPropagation();
                        }}
                        onClick={(event) => {
                          event.stopPropagation();
                          setDragState(null);
                          setDragCandidate(null);
                          onRemoveBox(box.id);
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </span>
                    </span>
                  )}
                  {showEdgeOverlays && (
                    <span className="pointer-events-none absolute inset-0 z-[1]">
                      {edgeOverlaySegments.map((segment, index) => {
                        const overlay = getCornerOverlayBarStyles(segment, overlayThickness);
                        return (
                          <span
                            key={`${segment.face}-${segment.kind}-${index}`}
                            className={cn('absolute', overlay.className)}
                            style={overlay.style}
                            aria-hidden
                          />
                        );
                      })}
                      {showBlockedFrontLabel && blockedFrontLabelStyle && (
                        <span
                          className={blockedFrontLabelStyle.className}
                          style={blockedFrontLabelStyle.style}
                        >
                          {blockedFrontLabelStyle.text}
                        </span>
                      )}
                    </span>
                  )}
                  <span
                    className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center overflow-hidden px-2 text-center"
                    style={{ transform: `rotate(${-box.rotation}deg)` }}
                  >
                    <span
                      className={cn(
                        'max-w-full overflow-hidden break-words font-semibold leading-tight',
                        compactLabel ? 'text-[9px]' : 'text-[11px]'
                      )}
                      style={{
                        display: '-webkit-box',
                        WebkitBoxOrient: 'vertical',
                        WebkitLineClamp: compactLabel ? 2 : 3,
                      }}
                    >
                      {product.name}
                    </span>
                    {showDimensions && (
                      <span className="mt-1 max-w-full truncate text-[10px] text-muted-foreground">
                        {rect.boxWidth} x {rect.boxLength}
                      </span>
                    )}
                  </span>
                  </>
                );

                if (readOnly) {
                  return (
                    <div key={box.id} className={boxClassName} style={boxStyle}>
                      {boxContent}
                    </div>
                  );
                }

                return (
                  <button
                    key={box.id}
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelect?.(box.id);
                    }}
                    onPointerDown={(event) => {
                      if (!interactive || event.button !== 0) return;
                      event.stopPropagation();
                      const snapshot = getInteractionSnapshot();
                      const point = getLayoutPoint(event.clientX, event.clientY, snapshot);
                      setDragState({
                        boxId: box.id,
                        pointerId: event.pointerId,
                        offsetX: point.x - box.x,
                        offsetY: point.y - box.y,
                        snapshot,
                      });
                      setDragCandidate({
                        x: box.x,
                        y: box.y,
                        snapped: false,
                        overlaps: false,
                        connected: true,
                        connectionBlocked: false,
                        frontBlocked: false,
                        valid: true,
                        guides: [],
                      });
                      onSelect?.(box.id);
                      event.currentTarget.setPointerCapture(event.pointerId);
                    }}
                    onPointerMove={(event) => {
                      if (!dragState || dragState.boxId !== box.id) return;
                      const point = getLayoutPoint(event.clientX, event.clientY, dragState.snapshot);
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
                    className={boxClassName}
                    style={boxStyle}
                  >
                    {boxContent}
                  </button>
                );
              })}

              {rectEntries.length === 0 && (
                <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
                  Add configurator items from the catalogue to start the layout.
                </div>
              )}

              {dragState && dragCandidate && !dragCandidate.valid && (
                <div className="pointer-events-none absolute bottom-4 left-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 shadow-sm">
                  {dragCandidate.overlaps
                    ? 'This position overlaps another box.'
                    : dragCandidate.connectionBlocked
                      ? 'This join hits a blocked side or fixed front section.'
                    : dragCandidate.frontBlocked
                      ? 'The front of this box must stay on an exposed face.'
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
