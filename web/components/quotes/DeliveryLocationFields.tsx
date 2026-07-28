'use client';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { QuoteFulfillmentMethod } from '@/lib/types';
import { isValidWhat3Words, normalizeWhat3Words } from '@/lib/what3words';

type DeliveryLocationFieldsProps = {
  fulfillmentMethod: QuoteFulfillmentMethod;
  useAlternateDeliveryAddress: boolean;
  onUseAlternateDeliveryAddressChange: (value: boolean) => void;
  deliveryAddressLine1: string;
  onDeliveryAddressLine1Change: (value: string) => void;
  deliveryAddressLine2: string;
  onDeliveryAddressLine2Change: (value: string) => void;
  deliveryCity: string;
  onDeliveryCityChange: (value: string) => void;
  deliveryCounty: string;
  onDeliveryCountyChange: (value: string) => void;
  deliveryPostcode: string;
  onDeliveryPostcodeChange: (value: string) => void;
  deliveryCountry: string;
  onDeliveryCountryChange: (value: string) => void;
  deliveryLocationNotes: string;
  onDeliveryLocationNotesChange: (value: string) => void;
  deliveryWhat3Words: string;
  onDeliveryWhat3WordsChange: (value: string) => void;
};

export default function DeliveryLocationFields(props: DeliveryLocationFieldsProps) {
  const {
    fulfillmentMethod,
    useAlternateDeliveryAddress,
    onUseAlternateDeliveryAddressChange,
    deliveryAddressLine1,
    onDeliveryAddressLine1Change,
    deliveryAddressLine2,
    onDeliveryAddressLine2Change,
    deliveryCity,
    onDeliveryCityChange,
    deliveryCounty,
    onDeliveryCountyChange,
    deliveryPostcode,
    onDeliveryPostcodeChange,
    deliveryCountry,
    onDeliveryCountryChange,
    deliveryLocationNotes,
    onDeliveryLocationNotesChange,
    deliveryWhat3Words,
    onDeliveryWhat3WordsChange,
  } = props;

  if (fulfillmentMethod === 'COLLECTION') return null;

  const w3wInvalid =
    Boolean(normalizeWhat3Words(deliveryWhat3Words)) && !isValidWhat3Words(deliveryWhat3Words);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="use_alternate_delivery_address"
          checked={useAlternateDeliveryAddress}
          onChange={(e) => onUseAlternateDeliveryAddressChange(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300"
        />
        <Label htmlFor="use_alternate_delivery_address" className="font-normal cursor-pointer">
          Use a different delivery address
        </Label>
      </div>
      {useAlternateDeliveryAddress && (
        <div className="space-y-3 rounded-md border p-3">
          <p className="text-xs text-muted-foreground">
            This is the delivery location sent to production for the works order and shown on the customer quote.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Label>Delivery address line 1</Label>
              <Input
                value={deliveryAddressLine1}
                onChange={(e) => onDeliveryAddressLine1Change(e.target.value)}
                placeholder="Address line 1"
              />
            </div>
            <div className="sm:col-span-2">
              <Label>Delivery address line 2</Label>
              <Input
                value={deliveryAddressLine2}
                onChange={(e) => onDeliveryAddressLine2Change(e.target.value)}
                placeholder="Address line 2"
              />
            </div>
            <div>
              <Label>City</Label>
              <Input value={deliveryCity} onChange={(e) => onDeliveryCityChange(e.target.value)} placeholder="City" />
            </div>
            <div>
              <Label>County</Label>
              <Input
                value={deliveryCounty}
                onChange={(e) => onDeliveryCountyChange(e.target.value)}
                placeholder="County"
              />
            </div>
            <div>
              <Label>Postcode</Label>
              <Input
                value={deliveryPostcode}
                onChange={(e) => onDeliveryPostcodeChange(e.target.value)}
                placeholder="Postcode"
                autoCapitalize="characters"
              />
            </div>
            <div>
              <Label>Country</Label>
              <Input
                value={deliveryCountry}
                onChange={(e) => onDeliveryCountryChange(e.target.value)}
                placeholder="Country"
              />
            </div>
            <div className="sm:col-span-2">
              <Label>What3Words (optional)</Label>
              <Input
                value={deliveryWhat3Words}
                onChange={(e) => onDeliveryWhat3WordsChange(e.target.value)}
                placeholder="e.g. filled.table.chair"
                aria-invalid={w3wInvalid}
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Precise install pin for field sites. Format: word.word.word
              </p>
              {w3wInvalid && (
                <p className="mt-1 text-xs text-destructive">
                  Enter three words separated by dots (e.g. filled.table.chair).
                </p>
              )}
            </div>
            <div className="sm:col-span-2">
              <Label>Delivery location notes</Label>
              <Textarea
                value={deliveryLocationNotes}
                onChange={(e) => onDeliveryLocationNotesChange(e.target.value)}
                placeholder="Site access, unloading notes, or delivery instructions"
                rows={3}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
