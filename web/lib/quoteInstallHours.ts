import type { Product, QuoteItemCreate } from '@/lib/types';
import { isRootQuoteLevelOptionalExtraLine } from '@/lib/quoteFormOptionalExtra';

/** True when the line is a user-defined custom item (not from catalog). */
export function isCustomQuoteLine(item: QuoteItemCreate): boolean {
  return item.is_custom === true || item.product_id == null;
}

/** Per-unit installation hours for a quote line (catalog product or custom line field). */
export function lineInstallationHoursPerUnit(
  item: QuoteItemCreate,
  product: Product | null | undefined
): number {
  if (product?.installation_hours != null) {
    return Number(product.installation_hours) || 0;
  }
  if (isCustomQuoteLine(item) && item.installation_hours != null) {
    return Number(item.installation_hours) || 0;
  }
  return 0;
}

/** Total install hours contributed by a line (per-unit × quantity). */
export function lineInstallationHoursContribution(
  item: QuoteItemCreate,
  product: Product | null | undefined
): number {
  const perUnit = lineInstallationHoursPerUnit(item, product);
  if (perUnit <= 0) return 0;
  const qty = Number(item.quantity) || 0;
  return qty * perUnit;
}

export function calculateTotalQuoteInstallationHours(
  items: QuoteItemCreate[],
  optionalExtraIds: Set<number>,
  getProduct: (item: QuoteItemCreate) => Product | null | undefined
): number {
  return items.reduce((total, item) => {
    if (isRootQuoteLevelOptionalExtraLine(item, optionalExtraIds)) return total;
    const product = getProduct(item);
    return total + lineInstallationHoursContribution(item, product);
  }, 0);
}
