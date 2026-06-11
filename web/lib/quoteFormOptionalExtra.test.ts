import { describe, expect, it } from 'vitest';
import { insertOptionalExtraLine } from './quoteFormOptionalExtra';
import type { QuoteItemCreate } from '@/lib/types';

function line(
  description: string,
  parent_index?: number
): QuoteItemCreate {
  return {
    description,
    quantity: 1,
    unit_price: 100,
    is_custom: true,
    sort_order: 0,
    parent_index,
  };
}

function extraLine(description: string, parentIndex: number): QuoteItemCreate {
  return {
    description,
    quantity: 1,
    unit_price: 50,
    is_custom: false,
    product_id: 999,
    sort_order: parentIndex + 1,
    parent_index: parentIndex,
  };
}

describe('insertOptionalExtraLine', () => {
  it('keeps Product 2 extra linked after inserting Product 1 extra', () => {
    let items = [line('P1'), line('P2')];
    items = insertOptionalExtraLine(items, 1, extraLine('E2', 1));
    items = insertOptionalExtraLine(items, 0, extraLine('E1', 0));

    const e2 = items.find((it) => it.description === 'E2');
    expect(e2?.parent_index).toBe(2);
    expect(items.map((it) => it.description)).toEqual(['P1', 'E1', 'P2', 'E2']);
  });

  it('links extra to Product 2 when Product 1 already has an extra', () => {
    let items = [line('P1'), line('E1', 0), line('P2')];
    items = insertOptionalExtraLine(items, 2, extraLine('E2', 2));

    const e2 = items.find((it) => it.description === 'E2');
    expect(e2?.parent_index).toBe(2);
  });

  it('shifts parent_index when inserting under Product 1 with P2 and E2 present', () => {
    let items = [line('P1'), line('P2'), line('E2', 1)];
    items = insertOptionalExtraLine(items, 0, extraLine('E1', 0));

    const e2 = items.find((it) => it.description === 'E2');
    expect(e2?.parent_index).toBe(2);
    expect(items.map((it) => it.description)).toEqual(['P1', 'E1', 'P2', 'E2']);
  });
});
