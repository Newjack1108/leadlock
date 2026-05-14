import { getSuggestedPlacement } from '@/lib/configurator/geometry';
import type { Product, QuoteConfigurationPayload } from '@/lib/types';

export function createEmptyConfiguration(name?: string): QuoteConfigurationPayload {
  return {
    schema_version: 1,
    name,
    boxes: [],
    extras: [],
  };
}

export function createPlacementId(productId: number, index: number): string {
  return `box-${productId}-${index}-${Math.random().toString(36).slice(2, 8)}`;
}

export function addProductToConfiguration(
  config: QuoteConfigurationPayload,
  product: Product,
  productMap: Record<number, Product>,
  anchorBoxId?: string | null
): QuoteConfigurationPayload {
  const nextIndex = config.boxes.length + 1;
  const { x, y, rotation } = getSuggestedPlacement(config.boxes, product, productMap, anchorBoxId);
  return {
    ...config,
    boxes: [
      ...config.boxes,
      {
        id: createPlacementId(product.id, nextIndex),
        product_id: product.id,
        x,
        y,
        rotation,
      },
    ],
  };
}
