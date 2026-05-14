'use client';

import type { ConfiguratorBoxPlacement, Product } from '@/lib/types';
import { getCanvasBounds, getPlacementRect } from '@/lib/configurator/geometry';
import { cn } from '@/lib/utils';

const SCALE = 40;

interface ConfiguratorCanvasProps {
  boxes: ConfiguratorBoxPlacement[];
  productMap: Record<number, Product>;
  selectedBoxId: string | null;
  onSelect: (boxId: string) => void;
}

export default function ConfiguratorCanvas({
  boxes,
  productMap,
  selectedBoxId,
  onSelect,
}: ConfiguratorCanvasProps) {
  const rectEntries = boxes
    .map((box) => {
      const product = productMap[box.product_id];
      if (!product) return null;
      return { box, product, rect: getPlacementRect(box, product) };
    })
    .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry));

  const bounds = getCanvasBounds(rectEntries.map((entry) => entry.rect));

  return (
    <div className="overflow-auto rounded-md border bg-muted/20 p-4">
      <div
        className="relative rounded-md border bg-background"
        style={{
          width: `${bounds.width * SCALE}px`,
          height: `${bounds.height * SCALE}px`,
          backgroundImage:
            'linear-gradient(to right, rgba(148,163,184,0.2) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.2) 1px, transparent 1px)',
          backgroundSize: `${SCALE}px ${SCALE}px`,
        }}
      >
        {rectEntries.map(({ box, product, rect }) => (
          <button
            key={box.id}
            type="button"
            onClick={() => onSelect(box.id)}
            className={cn(
              'absolute flex items-center justify-center rounded-md border text-center text-xs font-medium transition-colors',
              selectedBoxId === box.id
                ? 'border-primary bg-primary/15 text-primary'
                : 'border-slate-300 bg-slate-100 text-slate-700 hover:bg-slate-200'
            )}
            style={{
              left: `${rect.x1 * SCALE}px`,
              top: `${rect.y1 * SCALE}px`,
              width: `${Math.max(rect.width * SCALE, 48)}px`,
              height: `${Math.max(rect.length * SCALE, 48)}px`,
            }}
          >
            <span className="px-2">
              {product.name}
              <span className="block text-[11px] text-muted-foreground">
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
      </div>
    </div>
  );
}
