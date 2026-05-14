'use client';

import { useMemo, useRef, useState } from 'react';

import type { ConfiguratorBoxPlacement, Product } from '@/lib/types';
import {
  buildLayoutRectEntries,
  findPlacementCandidate,
  getCanvasBounds,
  type CandidatePlacement,
} from '@/lib/configurator/geometry';
import { cn } from '@/lib/utils';

const SCALE = 40;

interface ConfiguratorCanvasProps {
  boxes: ConfiguratorBoxPlacement[];
  productMap: Record<number, Product>;
  selectedBoxId: string | null;
  onSelect: (boxId: string) => void;
  onMoveBox: (boxId: string, nextBox: Pick<ConfiguratorBoxPlacement, 'x' | 'y'>) => void;
}

interface DragState {
  boxId: string;
  pointerId: number;
  offsetX: number;
  offsetY: number;
}

export default function ConfiguratorCanvas({
  boxes,
  productMap,
  selectedBoxId,
  onSelect,
  onMoveBox,
}: ConfiguratorCanvasProps) {
  const innerRef = useRef<HTMLDivElement>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [dragCandidate, setDragCandidate] = useState<CandidatePlacement | null>(null);

  const renderBoxes = useMemo(() => {
    if (!dragState || !dragCandidate) return boxes;
    return boxes.map((box) =>
      box.id === dragState.boxId
        ? { ...box, x: dragCandidate.x, y: dragCandidate.y }
        : box
    );
  }, [boxes, dragCandidate, dragState]);

  const rectEntries = useMemo(
    () => buildLayoutRectEntries(renderBoxes, productMap),
    [renderBoxes, productMap]
  );

  const bounds = getCanvasBounds(rectEntries.map((entry) => entry.rect));

  const toCanvasPosition = (value: number, min: number) => (value - min + bounds.padding) * SCALE;

  const getLayoutPoint = (clientX: number, clientY: number) => {
    const rect = innerRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: (clientX - rect.left) / SCALE + bounds.minX - bounds.padding,
      y: (clientY - rect.top) / SCALE + bounds.minY - bounds.padding,
    };
  };

  const finalizeDrag = () => {
    if (dragState && dragCandidate?.valid) {
      onMoveBox(dragState.boxId, { x: dragCandidate.x, y: dragCandidate.y });
    }
    setDragState(null);
    setDragCandidate(null);
  };

  return (
    <div className="overflow-auto rounded-md border bg-muted/20 p-4">
      <div
        ref={innerRef}
        className="relative rounded-md border bg-background"
        style={{
          width: `${bounds.width * SCALE}px`,
          height: `${Math.max(bounds.height * SCALE, 560)}px`,
          backgroundImage:
            'linear-gradient(to right, rgba(148,163,184,0.2) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.2) 1px, transparent 1px)',
          backgroundSize: `${SCALE}px ${SCALE}px`,
        }}
        onClick={() => {
          if (!dragState) return;
          finalizeDrag();
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

        {rectEntries.map(({ box, product, rect }) => (
          <button
            key={box.id}
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onSelect(box.id);
            }}
            onPointerDown={(event) => {
              if (event.button !== 0) return;
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
              dragState?.boxId === box.id && dragCandidate && !dragCandidate.valid
                ? 'cursor-grabbing border-red-500 bg-red-100/90 text-red-900 shadow-lg'
                : dragState?.boxId === box.id
                  ? 'cursor-grabbing border-primary bg-primary/20 text-primary shadow-lg'
                  : selectedBoxId === box.id
                    ? 'cursor-grab border-primary bg-primary/15 text-primary shadow-sm'
                    : 'cursor-grab border-slate-300 bg-slate-100 text-slate-700 hover:bg-slate-200'
            )}
            style={{
              left: `${toCanvasPosition(rect.x1, bounds.minX)}px`,
              top: `${toCanvasPosition(rect.y1, bounds.minY)}px`,
              width: `${Math.max(rect.width * SCALE, 48)}px`,
              height: `${Math.max(rect.length * SCALE, 48)}px`,
            }}
          >
            <span
              className="pointer-events-none absolute inset-0"
              style={{
                transform: `rotate(${box.rotation}deg)`,
              }}
            >
              <span className="absolute left-1/2 top-2 flex -translate-x-1/2 items-center gap-1 rounded-full bg-background/85 px-2 py-0.5 text-[10px] font-semibold shadow-sm">
                <span className="block h-1.5 w-6 rounded-full bg-sky-500" />
                <span>Front</span>
              </span>
            </span>
            <span className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center px-2 text-center">
              <span className="max-w-full truncate text-[11px] font-semibold leading-tight">
                {product.name}
              </span>
              <span className="mt-1 text-[10px] text-muted-foreground">
                {rect.width} x {rect.length}
              </span>
            </span>
          </button>
        ))}
        {rectEntries.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
            Add configurator items from the catalogue to start the layout.
          </div>
        )}
        {dragState && dragCandidate && !dragCandidate.valid && (
          <div className="pointer-events-none absolute bottom-4 left-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 shadow-sm">
            {dragCandidate.overlaps
              ? 'This position overlaps another box.'
              : 'This position breaks the connected layout.'}
          </div>
        )}
      </div>
    </div>
  );
}
