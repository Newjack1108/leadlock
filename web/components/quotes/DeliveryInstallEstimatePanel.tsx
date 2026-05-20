'use client';

import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { googleMapsDirectionsUrl } from '@/lib/googleMaps';
import { formatHoursMinutes } from '@/lib/utils';
import type { DeliveryInstallEstimateResponse } from '@/lib/types';

export type DeliveryEstimateMode = 'full' | 'delivery_only';

type CompanySettingsForEstimate = {
  postcode?: string | null;
  cost_per_mile?: number | null;
};

function resolvePostcodes(
  estimate: DeliveryInstallEstimateResponse,
  customerPostcode: string,
  companySettings: CompanySettingsForEstimate | null
): { factory: string; customer: string } {
  const factory =
    (estimate.factory_postcode || '').trim() ||
    (companySettings?.postcode || '').trim();
  const customer =
    (estimate.customer_postcode || '').trim() || customerPostcode.trim();
  return { factory, customer };
}

function mileageBreakdownSubtext(
  estimate: DeliveryInstallEstimateResponse,
  mode: DeliveryEstimateMode
): string | null {
  const rate = estimate.cost_per_mile ?? null;
  if (rate == null || rate <= 0 || estimate.cost_mileage == null) return null;

  const miles = estimate.distance_miles;
  const roundTrips = estimate.round_trips ?? 1;
  const parts = [`${miles} mi one way × 2`];
  if (roundTrips > 1) {
    parts.push(`× ${roundTrips} round trips`);
  } else {
    parts.push('(round trip)');
  }
  if (mode === 'delivery_only' && (estimate.delivery_trips ?? 1) > 1) {
    parts.push(`× ${estimate.delivery_trips} deliveries`);
  }
  parts.push(`× £${Number(rate).toFixed(2)}/mi`);
  return parts.join(' ');
}

interface DeliveryInstallEstimatePanelProps {
  estimate: DeliveryInstallEstimateResponse | null;
  mode: DeliveryEstimateMode;
  loading: boolean;
  error: string | null;
  customerPostcode: string;
  companySettings: CompanySettingsForEstimate | null;
  installHours: number;
  hasDeliveryLine: boolean;
  onModeChange: (mode: DeliveryEstimateMode) => void;
  onAdd: () => void;
  onRemove: () => void;
}

export default function DeliveryInstallEstimatePanel({
  estimate,
  mode,
  loading,
  error,
  customerPostcode,
  companySettings,
  installHours,
  hasDeliveryLine,
  onModeChange,
  onAdd,
  onRemove,
}: DeliveryInstallEstimatePanelProps) {
  const { factory, customer } = estimate
    ? resolvePostcodes(estimate, customerPostcode, companySettings)
    : { factory: (companySettings?.postcode || '').trim(), customer: customerPostcode.trim() };

  const mapsUrl =
    factory && customer ? googleMapsDirectionsUrl(factory, customer) : null;
  const mileageSubtext = estimate ? mileageBreakdownSubtext(estimate, mode) : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Delivery & installation estimate</CardTitle>
        <p className="text-sm text-muted-foreground font-normal">
          From factory to customer postcode. Choose delivery only (1 driver, 1 hr unload) or full delivery
          & installation (8hr fitting days, 2-man team). Add below to include in quote total.
        </p>
        <div className="flex flex-wrap gap-2 pt-2">
          <Button
            type="button"
            size="sm"
            variant={mode === 'full' ? 'default' : 'outline'}
            onClick={() => onModeChange('full')}
          >
            Delivery & installation
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mode === 'delivery_only' ? 'default' : 'outline'}
            onClick={() => onModeChange('delivery_only')}
          >
            Delivery only
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {mode === 'full' && installHours <= 0 && (
          <p className="text-sm text-muted-foreground">
            Add building lines with installation hours to estimate delivery and installation, or switch to
            Delivery only.
          </p>
        )}
        {loading && <p className="text-sm text-muted-foreground">Loading estimate…</p>}
        {error && (
          <div className="rounded-md border border-amber-200 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800 p-3 text-sm">
            <p className="font-medium text-amber-800 dark:text-amber-200">Cannot calculate estimate</p>
            <p className="text-amber-700 dark:text-amber-300 mt-1">{error}</p>
            <Link
              href="/settings/company"
              className="text-amber-700 dark:text-amber-300 underline mt-2 inline-block"
            >
              Configure factory postcode and installation & travel in Company settings
            </Link>
          </div>
        )}
        {!loading && !error && estimate && (
          <div className="space-y-3">
            {factory && customer && (
              <div className="rounded-md border bg-muted/30 px-3 py-2 text-sm space-y-1.5">
                <p>
                  <span className="text-muted-foreground">Route: </span>
                  <span className="font-medium">
                    Factory ({factory}) → Customer ({customer})
                  </span>
                </p>
                {mapsUrl && (
                  <a
                    href={mapsUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open route in Google Maps
                  </a>
                )}
              </div>
            )}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-muted-foreground">Distance (one way):</span>{' '}
                <span className="font-medium">{estimate.distance_miles} miles</span>
              </div>
              <div>
                <span className="text-muted-foreground">Travel time (one way):</span>{' '}
                <span className="font-medium">{formatHoursMinutes(estimate.travel_time_hours_one_way)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Fitting days (8hr):</span>{' '}
                <span className="font-medium">{estimate.fitting_days}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Overnight stay:</span>{' '}
                <span className="font-medium">{estimate.requires_overnight ? 'Yes' : 'No'}</span>
              </div>
              {estimate.requires_overnight && (
                <div>
                  <span className="text-muted-foreground">Nights away:</span>{' '}
                  <span className="font-medium">{estimate.nights_away}</span>
                </div>
              )}
              {mode === 'delivery_only' && (estimate.delivery_trips ?? 1) > 1 && (
                <div>
                  <span className="text-muted-foreground">Deliveries:</span>{' '}
                  <span className="font-medium">
                    {estimate.delivery_trips} (max 3 boxes per trailer)
                  </span>
                </div>
              )}
            </div>
            <div className="border-t pt-3 space-y-1 text-sm">
              {estimate.cost_mileage != null && (
                <div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Mileage:</span>
                    <span>£{Number(estimate.cost_mileage).toFixed(2)}</span>
                  </div>
                  {mileageSubtext && (
                    <p className="text-xs text-muted-foreground mt-0.5">{mileageSubtext}</p>
                  )}
                </div>
              )}
              {estimate.cost_labour != null && (
                <div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">
                      {mode === 'delivery_only' ? 'Labour (unload):' : 'Labour (install):'}
                    </span>
                    <span>£{Number(estimate.cost_labour).toFixed(2)}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {mode === 'delivery_only'
                      ? '1 hr unload'
                      : `${installHours.toFixed(1)} install hr`}
                  </p>
                </div>
              )}
              {estimate.cost_hotel != null && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Hotel:</span>
                  <span>£{Number(estimate.cost_hotel).toFixed(2)}</span>
                </div>
              )}
              {estimate.cost_meals != null && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Meals:</span>
                  <span>£{Number(estimate.cost_meals).toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between font-semibold pt-1 border-t">
                <span>Total (Mileage + Labour + Hotel + Meals, Ex VAT):</span>
                <span>£{Number(estimate.cost_total).toFixed(2)}</span>
              </div>
            </div>
            {estimate.settings_incomplete && (
              <p className="text-xs text-muted-foreground">
                Some costs could not be calculated. Complete Installation & travel in Company settings.
              </p>
            )}
            <div className="flex flex-wrap gap-2 pt-2 border-t">
              {hasDeliveryLine ? (
                <>
                  <Button type="button" variant="secondary" size="sm" disabled>
                    Added to quote
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={onRemove}>
                    Remove
                  </Button>
                </>
              ) : (
                <Button type="button" variant="default" size="sm" onClick={onAdd}>
                  Add to quote
                </Button>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
