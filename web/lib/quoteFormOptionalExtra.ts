import type { Product, QuoteItemCreate } from '@/lib/types';

export function optionalExtraIdSetFromList(extras: Product[]): Set<number> {
  return new Set(extras.map((e) => e.id));
}

/** Root line whose product is an optional extra (quote-level), not a main building product. */
export function isRootQuoteLevelOptionalExtraLine(
  item: QuoteItemCreate,
  optionalExtraIds: Set<number>,
  productById?: Record<number, Product | undefined>
): boolean {
  if (item.parent_index != null && item.parent_index !== undefined) return false;
  if (item.product_id == null) return false;
  if (optionalExtraIds.has(item.product_id)) return true;
  return productById?.[item.product_id]?.is_extra === true;
}

export function buildQuoteLevelOptionalExtraLine(extra: Product): QuoteItemCreate {
  return {
    product_id: extra.id,
    description: extra.name,
    quantity: 1,
    unit_price: Math.round(Number(extra.base_price) * 100) / 100,
    is_custom: false,
    parent_index: undefined,
    include_in_building_discount: false,
  };
}

/** 1-based index among root “building” lines only (excludes quote-level optional extras). */
export function rootBuildingProductNumberAtIndex(
  items: QuoteItemCreate[],
  index: number,
  optionalExtraIds: Set<number>,
  productById?: Record<number, Product | undefined>
): number {
  return items.filter(
    (it, i) =>
      i <= index &&
      (it.parent_index == null || it.parent_index === undefined) &&
      !isRootQuoteLevelOptionalExtraLine(it, optionalExtraIds, productById)
  ).length;
}
