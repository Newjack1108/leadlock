import type { QuoteItem, QuoteItemCreate, QuoteTemperature } from '@/lib/types';

/** Map API quote lines to create/edit form lines (same as edit page). */
export function quoteItemsToFormItems(items: QuoteItem[]): QuoteItemCreate[] {
  const sorted = [...items].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
  const idToIndex: Record<number, number> = {};
  sorted.forEach((item, i) => {
    if (item.id != null) idToIndex[item.id] = i;
  });
  return sorted.map((item) => ({
    product_id: item.product_id ?? undefined,
    description: item.description,
    quantity: Number(item.quantity),
    unit_price: Math.round(Number(item.unit_price) * 100) / 100,
    is_custom: item.is_custom ?? false,
    sort_order: item.sort_order ?? 0,
    parent_index:
      item.parent_quote_item_id != null ? idToIndex[item.parent_quote_item_id] : undefined,
    line_type: item.line_type ?? undefined,
    include_in_building_discount: item.include_in_building_discount ?? true,
  }));
}

/** Single placeholder line when nothing valid is on the quote (API requires ≥1 item). */
export const DRAFT_PLACEHOLDER_LINE_DESCRIPTION = 'Draft — in progress';

export type QuoteDraftPayload = {
  valid_until?: string;
  terms_and_conditions?: string;
  notes?: string;
  deposit_amount?: number;
  items: Array<{
    product_id?: number;
    description: string;
    quantity: number;
    unit_price: number;
    is_custom?: boolean;
    sort_order?: number;
    parent_index?: number;
    line_type?: 'DELIVERY' | 'INSTALLATION';
    include_in_building_discount?: boolean;
  }>;
  discount_template_ids?: number[];
  temperature?: QuoteTemperature;
  include_spec_sheets?: boolean;
  include_available_optional_extras?: boolean;
  include_delivery_installation_contact_note?: boolean;
};

function isValidLine(item: QuoteItemCreate): boolean {
  return (
    item.description.trim().length > 0 &&
    (item.quantity ?? 0) > 0 &&
    (item.unit_price ?? 0) >= 0
  );
}

export interface BuildDraftPayloadInput {
  items: QuoteItemCreate[];
  validUntil: string;
  termsAndConditions: string;
  notes: string;
  temperature: QuoteTemperature | '';
  includeSpecSheets: boolean;
  includeAvailableOptionalExtras: boolean;
  includeDeliveryInstallationContactNote: boolean;
  depositAmount: number | '';
  selectedDiscountIds: number[];
}

export function buildUpdateDraftPayload(input: BuildDraftPayloadInput): QuoteDraftPayload {
  const {
    items,
    validUntil,
    termsAndConditions,
    notes,
    temperature,
    includeSpecSheets,
    includeAvailableOptionalExtras,
    includeDeliveryInstallationContactNote,
    depositAmount,
    selectedDiscountIds,
  } = input;

  const validItems = items.filter(isValidLine);
  const usingPlaceholder = validItems.length === 0;
  const linesForPayload: QuoteItemCreate[] = usingPlaceholder
    ? [
        {
          description: DRAFT_PLACEHOLDER_LINE_DESCRIPTION,
          quantity: 1,
          unit_price: 0,
          is_custom: true,
          sort_order: 0,
        },
      ]
    : validItems;

  const originalIndices = items
    .map((_, i) => i)
    .filter((i) => {
      const it = items[i];
      return isValidLine(it);
    });

  const payloadItems = linesForPayload.map((item, index) => {
    if (usingPlaceholder) {
      return {
        product_id: undefined,
        description: item.description,
        quantity: Number(item.quantity),
        unit_price: Number(item.unit_price),
        is_custom: true,
        sort_order: index,
        line_type: item.line_type ?? undefined,
        include_in_building_discount: item.include_in_building_discount !== false,
      };
    }
    const parentInItems = item.parent_index;
    const parentIndexInPayload =
      parentInItems != null ? originalIndices.indexOf(parentInItems) : -1;
    return {
      product_id: item.product_id ?? undefined,
      description: item.description,
      quantity: Number(item.quantity),
      unit_price: Number(item.unit_price),
      is_custom:
        item.is_custom !== undefined
          ? item.is_custom
          : item.product_id === undefined || item.product_id === null,
      sort_order: index,
      parent_index: parentIndexInPayload >= 0 ? parentIndexInPayload : undefined,
      line_type: item.line_type ?? undefined,
      include_in_building_discount: item.include_in_building_discount !== false,
    };
  });

  const payload: QuoteDraftPayload = {
    items: payloadItems,
    discount_template_ids: selectedDiscountIds.length > 0 ? selectedDiscountIds : undefined,
    include_spec_sheets: includeSpecSheets,
    include_available_optional_extras: includeAvailableOptionalExtras,
    include_delivery_installation_contact_note: includeDeliveryInstallationContactNote,
  };

  if (validUntil) {
    payload.valid_until = new Date(validUntil).toISOString();
  }
  if (termsAndConditions?.trim()) {
    payload.terms_and_conditions = termsAndConditions.trim();
  }
  if (notes?.trim()) {
    payload.notes = notes.trim();
  }
  if (temperature) {
    payload.temperature = temperature;
  }
  if (depositAmount !== '') {
    payload.deposit_amount = Number(depositAmount);
  }

  return payload;
}

export function stableDraftPayloadKey(payload: QuoteDraftPayload): string {
  return JSON.stringify(payload);
}
