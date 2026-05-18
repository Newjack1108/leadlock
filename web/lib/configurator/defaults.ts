import { getSuggestedPlacement } from '@/lib/configurator/geometry';
import type { ConfiguratorBoxPlacement, Product, QuoteConfigurationPayload } from '@/lib/types';

export function getStarterProducts(items: Product[]): Product[] {
  return items.filter((product) => product.configurator_is_starter_box);
}

export function canAddConfiguratorProduct(
  boxes: ConfiguratorBoxPlacement[],
  product: Product
): boolean {
  if (boxes.length === 0) {
    return Boolean(product.configurator_is_starter_box);
  }
  return true;
}

export function canRemoveConfiguratorBox(
  boxes: ConfiguratorBoxPlacement[],
  boxId: string,
  productMap: Record<number, Product>
): boolean {
  const box = boxes.find((entry) => entry.id === boxId);
  if (!box) return true;
  const product = productMap[box.product_id];
  if (!product?.configurator_is_starter_box) return true;
  return boxes.length <= 1;
}

export function layoutHasStarterBox(
  boxes: ConfiguratorBoxPlacement[],
  productMap: Record<number, Product>
): boolean {
  return boxes.some((box) => Boolean(productMap[box.product_id]?.configurator_is_starter_box));
}

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
