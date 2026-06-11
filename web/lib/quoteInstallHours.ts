import type { Product, QuoteItem, QuoteItemCreate } from '@/lib/types';
import { isRootQuoteLevelOptionalExtraLine } from '@/lib/quoteFormOptionalExtra';

export const DELIVERY_LINE_DESCRIPTION = 'Delivery';
export const INSTALLATION_LINE_DESCRIPTION = 'Installation';
export const DELIVERY_INSTALL_LEGACY_DESCRIPTION = 'Delivery & Installation';
export const DELIVERY_ONLY_DESCRIPTION = 'Delivery only';

type QuoteLineLike = Pick<
  QuoteItemCreate | QuoteItem,
  'line_type' | 'description' | 'is_custom'
>;

/** True when the line is delivery or installation (not eligible for negative unit price). */
export function isDeliveryOrInstallItem(item: QuoteLineLike): boolean {
  return (
    item.line_type === 'DELIVERY' ||
    item.line_type === 'INSTALLATION' ||
    (item.description === DELIVERY_INSTALL_LEGACY_DESCRIPTION && !!item.is_custom) ||
    (item.description === DELIVERY_ONLY_DESCRIPTION && !!item.is_custom)
  );
}

/** True when the line is a user-defined custom item (not from catalog). */
export function isCustomQuoteLine(item: QuoteItemCreate): boolean {
  return item.is_custom === true || item.product_id == null;
}

/** Custom non-delivery lines may use negative unit_price for credits. */
export function allowsNegativeUnitPrice(item: QuoteItemCreate): boolean {
  return isCustomQuoteLine(item) && !isDeliveryOrInstallItem(item);
}

export function isValidQuoteLineUnitPrice(item: QuoteItemCreate): boolean {
  const price = Number(item.unit_price);
  if (!Number.isFinite(price)) return false;
  if (allowsNegativeUnitPrice(item)) return true;
  return price >= 0;
}

export function isValidQuoteLine(item: QuoteItemCreate): boolean {
  return (
    item.description.trim().length > 0 &&
    (item.quantity ?? 0) > 0 &&
    isValidQuoteLineUnitPrice(item)
  );
}

export function quoteLineTotal(item: QuoteItemCreate): number {
  return (Number(item.quantity) || 0) * (Number(item.unit_price) || 0);
}

/** Parse unit price from input; catalog lines cannot go below zero. */
export function parseQuoteLineUnitPrice(
  item: QuoteItemCreate,
  raw: string
): number {
  const parsed = Math.round((parseFloat(raw) || 0) * 100) / 100;
  if (allowsNegativeUnitPrice(item)) return parsed;
  return Math.max(0, parsed);
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
