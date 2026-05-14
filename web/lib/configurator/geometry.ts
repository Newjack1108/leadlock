import type { ConfiguratorBoxPlacement, Product } from '@/lib/types';

export interface PlacementRect {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  width: number;
  length: number;
}

export function getFootprint(product: Product, rotation: number) {
  const width = Number(product.configurator_width ?? 0);
  const length = Number(product.configurator_length ?? 0);
  if (rotation === 90 || rotation === 270) {
    return { width: length, length: width };
  }
  return { width, length };
}

export function getPlacementRect(box: ConfiguratorBoxPlacement, product: Product): PlacementRect {
  const { width, length } = getFootprint(product, box.rotation);
  return {
    x1: Number(box.x),
    y1: Number(box.y),
    x2: Number(box.x) + width,
    y2: Number(box.y) + length,
    width,
    length,
  };
}

export function placementsOverlap(a: PlacementRect, b: PlacementRect) {
  return a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;
}

export function getCanvasBounds(rects: PlacementRect[]) {
  if (rects.length === 0) {
    return { width: 6, height: 4 };
  }
  const maxX = Math.max(...rects.map((rect) => rect.x2));
  const maxY = Math.max(...rects.map((rect) => rect.y2));
  return {
    width: Math.max(6, Math.ceil(maxX + 1)),
    height: Math.max(4, Math.ceil(maxY + 1)),
  };
}
