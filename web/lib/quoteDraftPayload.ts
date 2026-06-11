import type {
  Quote,
  QuoteFulfillmentMethod,
  QuoteItem,
  QuoteItemCreate,
  QuoteTemperature,
} from '@/lib/types';
import { isValidQuoteLine } from '@/lib/quoteInstallHours';

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
    installation_hours:
      item.installation_hours != null ? Number(item.installation_hours) : undefined,
  }));
}

/** Single placeholder line when nothing valid is on the quote (API requires ≥1 item). */
export const DRAFT_PLACEHOLDER_LINE_DESCRIPTION = 'Draft — in progress';

export function isPlaceholderOnlyDraftItems(
  items: Array<{ description: string; quantity?: number; unit_price?: number }>
): boolean {
  const validItems = items.filter(
    (item) => item.description.trim() && Number(item.quantity) > 0 && Number(item.unit_price) >= 0
  );
  return (
    validItems.length === 1 &&
    validItems[0].description.trim() === DRAFT_PLACEHOLDER_LINE_DESCRIPTION
  );
}

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
    installation_hours?: number;
  }>;
  discount_template_ids?: number[];
  temperature?: QuoteTemperature;
  include_spec_sheets?: boolean;
  include_available_optional_extras?: boolean;
  displayed_optional_extra_ids?: number[];
  include_delivery_installation_contact_note?: boolean;
  fulfillment_method?: QuoteFulfillmentMethod;
  use_alternate_delivery_address?: boolean;
  delivery_address_line1?: string;
  delivery_address_line2?: string;
  delivery_city?: string;
  delivery_county?: string;
  delivery_postcode?: string;
  delivery_country?: string;
  delivery_location_notes?: string;
};

function isValidLine(item: QuoteItemCreate): boolean {
  return isValidQuoteLine(item);
}

export interface BuildDraftPayloadInput {
  items: QuoteItemCreate[];
  validUntil: string;
  termsAndConditions: string;
  notes: string;
  temperature: QuoteTemperature | '';
  includeSpecSheets: boolean;
  includeAvailableOptionalExtras: boolean;
  displayedOptionalExtraIds: number[];
  includeDeliveryInstallationContactNote: boolean;
  fulfillmentMethod: QuoteFulfillmentMethod;
  useAlternateDeliveryAddress: boolean;
  deliveryAddressLine1: string;
  deliveryAddressLine2: string;
  deliveryCity: string;
  deliveryCounty: string;
  deliveryPostcode: string;
  deliveryCountry: string;
  deliveryLocationNotes: string;
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
    displayedOptionalExtraIds,
    includeDeliveryInstallationContactNote,
    fulfillmentMethod,
    useAlternateDeliveryAddress,
    deliveryAddressLine1,
    deliveryAddressLine2,
    deliveryCity,
    deliveryCounty,
    deliveryPostcode,
    deliveryCountry,
    deliveryLocationNotes,
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
        installation_hours:
          item.installation_hours != null && item.installation_hours > 0
            ? Number(item.installation_hours)
            : undefined,
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
      installation_hours:
        item.installation_hours != null && item.installation_hours > 0
          ? Number(item.installation_hours)
          : undefined,
    };
  });

  const payload: QuoteDraftPayload = {
    items: payloadItems,
    discount_template_ids: selectedDiscountIds.length > 0 ? selectedDiscountIds : undefined,
    include_spec_sheets: includeSpecSheets,
    include_available_optional_extras: includeAvailableOptionalExtras,
    displayed_optional_extra_ids:
      displayedOptionalExtraIds.length > 0 ? displayedOptionalExtraIds : [],
    include_delivery_installation_contact_note: includeDeliveryInstallationContactNote,
    fulfillment_method: fulfillmentMethod,
    use_alternate_delivery_address: useAlternateDeliveryAddress,
    delivery_address_line1: useAlternateDeliveryAddress ? deliveryAddressLine1.trim() || undefined : undefined,
    delivery_address_line2: useAlternateDeliveryAddress ? deliveryAddressLine2.trim() || undefined : undefined,
    delivery_city: useAlternateDeliveryAddress ? deliveryCity.trim() || undefined : undefined,
    delivery_county: useAlternateDeliveryAddress ? deliveryCounty.trim() || undefined : undefined,
    delivery_postcode: useAlternateDeliveryAddress ? deliveryPostcode.trim() || undefined : undefined,
    delivery_country: useAlternateDeliveryAddress ? deliveryCountry.trim() || 'United Kingdom' : undefined,
    delivery_location_notes: useAlternateDeliveryAddress ? deliveryLocationNotes.trim() || undefined : undefined,
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

/** Reset draft quote lines to bootstrap placeholder while preserving quote metadata. */
export function buildPlaceholderOnlyDraftPayloadFromQuote(quote: Quote): QuoteDraftPayload {
  const payload: QuoteDraftPayload = {
    items: [
      {
        description: DRAFT_PLACEHOLDER_LINE_DESCRIPTION,
        quantity: 1,
        unit_price: 0,
        is_custom: true,
        sort_order: 0,
      },
    ],
    include_spec_sheets: quote.include_spec_sheets,
    include_available_optional_extras: quote.include_available_optional_extras,
    displayed_optional_extra_ids: quote.displayed_optional_extra_ids ?? [],
    include_delivery_installation_contact_note: quote.include_delivery_installation_contact_note,
    fulfillment_method: quote.fulfillment_method ?? 'DELIVERY',
    use_alternate_delivery_address: quote.use_alternate_delivery_address ?? false,
    delivery_address_line1: quote.delivery_address_line1 ?? undefined,
    delivery_address_line2: quote.delivery_address_line2 ?? undefined,
    delivery_city: quote.delivery_city ?? undefined,
    delivery_county: quote.delivery_county ?? undefined,
    delivery_postcode: quote.delivery_postcode ?? undefined,
    delivery_country: quote.delivery_country ?? 'United Kingdom',
    delivery_location_notes: quote.delivery_location_notes ?? undefined,
  };

  if (quote.valid_until) {
    payload.valid_until = quote.valid_until;
  }
  if (quote.terms_and_conditions?.trim()) {
    payload.terms_and_conditions = quote.terms_and_conditions.trim();
  }
  if (quote.notes?.trim()) {
    payload.notes = quote.notes.trim();
  }
  if (quote.temperature) {
    payload.temperature = quote.temperature;
  }
  if (quote.deposit_amount != null) {
    payload.deposit_amount = Number(quote.deposit_amount);
  }

  return payload;
}
