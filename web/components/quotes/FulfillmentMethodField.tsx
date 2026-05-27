'use client';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import type { QuoteFulfillmentMethod } from '@/lib/types';

interface FulfillmentMethodFieldProps {
  value: QuoteFulfillmentMethod;
  onChange: (value: QuoteFulfillmentMethod) => void;
  disabled?: boolean;
  /** When true, switching to Collection is blocked (delivery/install lines on quote). */
  hasDeliveryInstallLines?: boolean;
  onCollectionBlocked?: () => void;
}

export default function FulfillmentMethodField({
  value,
  onChange,
  disabled,
  hasDeliveryInstallLines,
  onCollectionBlocked,
}: FulfillmentMethodFieldProps) {
  const tryChange = (next: QuoteFulfillmentMethod) => {
    if (next === 'COLLECTION' && hasDeliveryInstallLines) {
      onCollectionBlocked?.();
      return;
    }
    onChange(next);
  };

  return (
    <div className="space-y-2">
      <Label>Fulfillment</Label>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant={value === 'DELIVERY' ? 'default' : 'outline'}
          disabled={disabled}
          onClick={() => tryChange('DELIVERY')}
        >
          Delivery
        </Button>
        <Button
          type="button"
          size="sm"
          variant={value === 'COLLECTION' ? 'default' : 'outline'}
          disabled={disabled}
          onClick={() => tryChange('COLLECTION')}
        >
          Collection
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        {value === 'COLLECTION'
          ? 'Customer collects from the factory. Delivery and installation estimates are not available.'
          : 'Delivery or delivery & installation can be estimated and added to the quote.'}
      </p>
    </div>
  );
}
