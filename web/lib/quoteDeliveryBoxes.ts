import type { Product, QuoteItemCreate } from '@/lib/types';
import { isRootQuoteLevelOptionalExtraLine } from '@/lib/quoteFormOptionalExtra';

const DELIVERY_LINE_TYPES = new Set(['DELIVERY', 'INSTALLATION']);

function boxesPerProduct(product: Product | null | undefined): number {
  const bpp = product?.boxes_per_product;
  if (bpp == null || bpp < 1) return 1;
  return bpp;
}

function isDeliveryOrInstallLine(item: QuoteItemCreate): boolean {
  if (item.line_type && DELIVERY_LINE_TYPES.has(item.line_type)) return true;
  return false;
}

/** Total physical boxes for delivery-only trailer trips (qty × boxes_per_product). */
export function calculateTotalQuoteDeliveryBoxes(
  items: QuoteItemCreate[],
  optionalExtraIds: Set<number>,
  getProduct: (item: QuoteItemCreate) => Product | null | undefined
): number {
  return items.reduce((total, item) => {
    if (isDeliveryOrInstallLine(item)) return total;
    if (isRootQuoteLevelOptionalExtraLine(item, optionalExtraIds)) return total;
    if (item.parent_index != null && item.parent_index !== undefined) return total;
    if (item.product_id == null) return total;
    const product = getProduct(item);
    if (product?.is_extra) return total;
    const qty = Number(item.quantity) || 0;
    if (qty < 1) return total;
    return total + qty * boxesPerProduct(product);
  }, 0);
}
