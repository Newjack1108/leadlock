'use client';

import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Plus, Trash2 } from 'lucide-react';
import type { Product } from '@/lib/types';

interface QuoteDisplayedOptionalExtrasSectionProps {
  displayedExtraIds: number[];
  onChange: (ids: number[]) => void;
  allOptionalExtras: Product[];
  productDetails?: Record<number, Product | undefined>;
}

export default function QuoteDisplayedOptionalExtrasSection({
  displayedExtraIds,
  onChange,
  allOptionalExtras,
  productDetails = {},
}: QuoteDisplayedOptionalExtrasSectionProps) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [filter, setFilter] = useState('');

  const extrasById = useMemo(() => {
    const map = new Map<number, Product>();
    for (const e of allOptionalExtras) {
      map.set(e.id, e);
    }
    for (const p of Object.values(productDetails)) {
      if (p?.is_extra) {
        map.set(p.id, p);
      }
    }
    return map;
  }, [allOptionalExtras, productDetails]);

  const displayed = displayedExtraIds
    .map((id) => ({ id, product: extrasById.get(id) }))
    .filter((row) => row.product != null) as { id: number; product: Product }[];

  const filteredPicker = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const available = allOptionalExtras.filter((e) => !displayedExtraIds.includes(e.id));
    const sorted = [...available].sort((a, b) => a.name.localeCompare(b.name));
    if (!q) return sorted;
    return sorted.filter((e) => e.name.toLowerCase().includes(q));
  }, [allOptionalExtras, displayedExtraIds, filter]);

  const addDisplayed = (extra: Product) => {
    if (displayedExtraIds.includes(extra.id)) return;
    onChange([...displayedExtraIds, extra.id]);
    setPickerOpen(false);
    setFilter('');
  };

  const removeDisplayed = (id: number) => {
    onChange(displayedExtraIds.filter((x) => x !== id));
  };

  return (
    <div className="space-y-3 rounded-md border p-4 bg-muted/30">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Label className="text-base font-medium">Optional extras for customer</Label>
          <p className="text-sm text-muted-foreground mt-1">
            These appear in &quot;Other Available Options&quot; on the customer quote and PDF. They are
            not added to the quote total — use &quot;Add extra to quote&quot; above to include an extra as a
            priced line.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => setPickerOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Add to show on quote
        </Button>
      </div>

      {displayed.length === 0 ? (
        <p className="text-sm text-muted-foreground">No optional extras selected for customer view.</p>
      ) : (
        <ul className="space-y-2">
          {displayed.map(({ id, product }) => (
            <li
              key={id}
              className="flex items-center justify-between gap-2 p-2 border rounded-md bg-background"
            >
              <div>
                <p className="text-sm font-medium">{product.name}</p>
                <p className="text-xs text-muted-foreground">
                  £{Number(product.base_price).toFixed(2)} (display only)
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => removeDisplayed(id)}
                aria-label={`Remove ${product.name}`}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent className="max-w-lg max-h-[min(80vh,520px)] flex flex-col">
          <DialogHeader>
            <DialogTitle>Optional extra — display only</DialogTitle>
            <DialogDescription>
              Customer will see this in Other Available Options; it will not be included in the quote
              total.
            </DialogDescription>
          </DialogHeader>
          <Input
            placeholder="Search…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="mb-2"
          />
          <div className="overflow-y-auto flex-1 space-y-2 min-h-0 pr-1">
            {filteredPicker.length === 0 ? (
              <p className="text-sm text-muted-foreground">No matching optional extras.</p>
            ) : (
              filteredPicker.map((extra) => (
                <div
                  key={extra.id}
                  className="flex items-center justify-between gap-2 p-2 border rounded-md"
                >
                  <div>
                    <p className="text-sm font-medium">{extra.name}</p>
                    <p className="text-xs text-muted-foreground">
                      £{Number(extra.base_price).toFixed(2)}
                    </p>
                  </div>
                  <Button type="button" variant="outline" size="sm" onClick={() => addDisplayed(extra)}>
                    <Plus className="h-3 w-3 mr-1" />
                    Add
                  </Button>
                </div>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
