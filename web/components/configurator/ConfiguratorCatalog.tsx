'use client';

import { useState } from 'react';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { HardHat, Package, Truck } from 'lucide-react';

import type {
  ConfiguratorDeliveryEstimateInclusion,
  ConfiguratorExtraSelection,
  Product,
  QuoteConfigurationPayload,
} from '@/lib/types';
import ConfiguratorExtraIconButton from '@/components/configurator/ConfiguratorExtraIconButton';
import ConfiguratorExtraInfoHint from '@/components/configurator/ConfiguratorExtraInfoHint';
import ConfiguratorIconToggleButton from '@/components/configurator/ConfiguratorIconToggleButton';
import { cn } from '@/lib/utils';

interface ConfiguratorCatalogProps {
  boxProducts: Product[];
  starterProducts: Product[];
  placedStarterProduct: Product | null;
  hasStarterOnLayout: boolean;
  extras: Product[];
  configuration: QuoteConfigurationPayload;
  boxCount: number;
  extraQuantityByProductId: Map<number, number>;
  onAddItem: (product: Product) => void;
  onToggleExtra: (product: Product, checked: boolean) => void;
  onUpdateExtra: (productId: number, updater: (current: ConfiguratorExtraSelection) => ConfiguratorExtraSelection) => void;
  deliveryInclusion: ConfiguratorDeliveryEstimateInclusion;
  onSetDeliveryInclusion: (mode: ConfiguratorDeliveryEstimateInclusion) => void;
  deliveryLineUnitPrice?: number | null;
  deliveryLineQuantity?: number;
  deliveryDisabledReason?: string | null;
  className?: string;
}

function CatalogSection({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('space-y-1.5', className)}>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}

function ProductRow({ product, onAdd }: { product: Product; onAdd: () => void }) {
  const [justAdded, setJustAdded] = useState(false);

  const handleAdd = () => {
    onAdd();
    setJustAdded(true);
    window.setTimeout(() => setJustAdded(false), 500);
  };

  return (
    <div className="flex items-center gap-2 rounded-md border px-2 py-1.5">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-snug break-words" title={product.name}>
          {product.name}
        </p>
        <p className="text-xs text-muted-foreground tabular-nums">
          {product.configurator_width ?? '—'}m × {product.configurator_length ?? '—'}m
        </p>
      </div>
      <Button
        type="button"
        variant={justAdded ? 'default' : 'outline'}
        size="sm"
        className={cn(
          'h-10 min-h-[44px] min-w-[4.25rem] shrink-0 px-3 text-sm font-semibold touch-manipulation',
          'transition-all duration-150 active:scale-[0.96]',
          !justAdded &&
            'active:border-primary active:bg-primary active:text-primary-foreground',
          justAdded && 'bg-emerald-600 text-white hover:bg-emerald-600/90 border-emerald-600'
        )}
        onClick={handleAdd}
      >
        {justAdded ? 'Added' : 'Add'}
      </Button>
    </div>
  );
}

function PlacedStarterRow({ product }: { product: Product }) {
  return (
    <div className="rounded-md border border-primary/30 bg-primary/5 px-2 py-1.5">
      <p className="text-sm font-medium leading-snug break-words" title={product.name}>
        {product.name}
      </p>
      <p className="text-xs text-muted-foreground tabular-nums">
        {product.configurator_width ?? '—'}m × {product.configurator_length ?? '—'}m
      </p>
      <p className="mt-1 text-xs text-muted-foreground">Starter for this layout</p>
    </div>
  );
}

export default function ConfiguratorCatalog({
  boxProducts,
  starterProducts,
  placedStarterProduct,
  hasStarterOnLayout,
  extras,
  configuration,
  boxCount,
  extraQuantityByProductId,
  onAddItem,
  onToggleExtra,
  onUpdateExtra,
  deliveryInclusion,
  onSetDeliveryInclusion,
  deliveryLineUnitPrice,
  deliveryLineQuantity = 1,
  deliveryDisabledReason,
  className,
}: ConfiguratorCatalogProps) {
  const selectedExtras = new Map(configuration.extras.map((extra) => [extra.product_id, extra]));
  const deliveryToggleDisabled = Boolean(deliveryDisabledReason);

  return (
    <Card className={cn('flex max-h-[inherit] flex-col', className)}>
      <CardHeader className="shrink-0 pb-3">
        <CardTitle className="text-base">Catalogue</CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pb-4">
        <CatalogSection title="Starter box">
          {hasStarterOnLayout && placedStarterProduct ? (
            <PlacedStarterRow product={placedStarterProduct} />
          ) : starterProducts.length === 0 ? (
            <p className="text-xs text-muted-foreground">No starter boxes configured.</p>
          ) : (
            starterProducts.map((product) => (
              <ProductRow key={product.id} product={product} onAdd={() => onAddItem(product)} />
            ))
          )}
        </CatalogSection>

        <CatalogSection
          title="Boxes"
          className={cn('border-t pt-3', !hasStarterOnLayout && 'opacity-60')}
        >
          {!hasStarterOnLayout ? (
            <p className="text-xs text-muted-foreground">Add a starter box to unlock.</p>
          ) : boxProducts.length === 0 ? (
            <p className="text-xs text-muted-foreground">No configurator products yet.</p>
          ) : (
            boxProducts.map((product) => (
              <ProductRow key={product.id} product={product} onAdd={() => onAddItem(product)} />
            ))
          )}
        </CatalogSection>

        <CatalogSection title="Extras" className="border-t pt-3">
          {extras.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Enable extras in{' '}
              <Link href="/products/optional-extras" className="text-primary underline-offset-4 hover:underline">
                optional extras
              </Link>
              .
            </p>
          ) : (
            extras.map((product) => {
              const selected = selectedExtras.get(product.id);
              const isPerBox = Boolean(product.configurator_per_box);
              const resolvedQuantity = extraQuantityByProductId.get(product.id) ?? (isPerBox ? boxCount : undefined);
              return (
                <div key={product.id} className="rounded-md border px-2 py-1.5">
                  <div className="flex items-center gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex min-w-0 items-start gap-1">
                        <p className="text-sm font-medium leading-snug break-words" title={product.name}>
                          {product.name}
                        </p>
                        <ConfiguratorExtraInfoHint product={product} />
                      </div>
                      <p className="text-xs text-muted-foreground">
                        £{Number(product.base_price).toFixed(2)}
                        {product.unit ? ` · ${product.unit}` : ''}
                      </p>
                    </div>
                    <ConfiguratorExtraIconButton
                      product={product}
                      selected={Boolean(selected)}
                      onToggle={() => onToggleExtra(product, !selected)}
                    />
                  </div>
                  {selected && !isPerBox && (
                    <div className="mt-1.5 flex items-center gap-2">
                      <Label htmlFor={`extra-qty-${product.id}`} className="sr-only">
                        Quantity
                      </Label>
                      <Input
                        id={`extra-qty-${product.id}`}
                        type="number"
                        min={1}
                        step="1"
                        className="h-8 w-20"
                        value={selected.quantity ?? 1}
                        onChange={(event) =>
                          onUpdateExtra(product.id, (current) => ({
                            ...current,
                            quantity: Number(event.target.value || 1),
                          }))
                        }
                      />
                    </div>
                  )}
                  {selected && isPerBox && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Qty{' '}
                      <span className="font-medium text-foreground tabular-nums">
                        {resolvedQuantity ?? boxCount}
                      </span>{' '}
                      · {boxCount} {boxCount === 1 ? 'box' : 'boxes'}
                    </p>
                  )}
                </div>
              );
            })
          )}
        </CatalogSection>

        <CatalogSection title="Fulfillment" className="border-t pt-3">
          <div className="rounded-md border px-2 py-1.5 mb-2">
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium leading-snug">Collection</p>
                <p className="text-xs text-muted-foreground">Customer collects from factory (no delivery charge)</p>
              </div>
              <ConfiguratorIconToggleButton
                selected={deliveryInclusion === 'collection'}
                disabled={deliveryToggleDisabled}
                label={
                  deliveryInclusion === 'collection' ? 'Remove collection' : 'Customer collection'
                }
                onToggle={() => onSetDeliveryInclusion('collection')}
              >
                <Package className="h-5 w-5 text-muted-foreground" aria-hidden />
              </ConfiguratorIconToggleButton>
            </div>
          </div>
          {deliveryDisabledReason ? (
            <p className="text-xs text-muted-foreground">{deliveryDisabledReason}</p>
          ) : null}
          <div className="rounded-md border px-2 py-1.5">
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium leading-snug">Delivery only</p>
                <p className="text-xs text-muted-foreground">
                  {deliveryInclusion === 'delivery_only' && deliveryLineUnitPrice != null
                    ? deliveryLineQuantity > 1
                      ? `£${(deliveryLineUnitPrice * deliveryLineQuantity).toFixed(2)} · ${deliveryLineQuantity} deliveries (max 3 boxes per trailer)`
                      : `£${deliveryLineUnitPrice.toFixed(2)} · estimated`
                    : '1 driver, unload at site (max 3 boxes per trailer)'}
                </p>
              </div>
              <ConfiguratorIconToggleButton
                selected={deliveryInclusion === 'delivery_only'}
                disabled={deliveryToggleDisabled || deliveryInclusion === 'collection'}
                label={
                  deliveryInclusion === 'delivery_only'
                    ? 'Remove delivery only'
                    : 'Include delivery only'
                }
                onToggle={() => onSetDeliveryInclusion('delivery_only')}
              >
                <Truck className="h-5 w-5 text-muted-foreground" aria-hidden />
              </ConfiguratorIconToggleButton>
            </div>
          </div>
          <div className="rounded-md border px-2 py-1.5">
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium leading-snug">Delivery & installation</p>
                <p className="text-xs text-muted-foreground">
                  {deliveryInclusion === 'delivery_and_install' && deliveryLineUnitPrice != null
                    ? `£${deliveryLineUnitPrice.toFixed(2)} · estimated`
                    : 'From factory to site, 2-man team'}
                </p>
              </div>
              <ConfiguratorIconToggleButton
                selected={deliveryInclusion === 'delivery_and_install'}
                disabled={deliveryToggleDisabled || deliveryInclusion === 'collection'}
                label={
                  deliveryInclusion === 'delivery_and_install'
                    ? 'Remove delivery & installation'
                    : 'Include delivery & installation'
                }
                onToggle={() => onSetDeliveryInclusion('delivery_and_install')}
              >
                <span className="flex items-center justify-center gap-0.5" aria-hidden>
                  <Truck className="h-4 w-4 text-muted-foreground" />
                  <HardHat className="h-4 w-4 text-muted-foreground" />
                </span>
              </ConfiguratorIconToggleButton>
            </div>
          </div>
        </CatalogSection>
      </CardContent>
    </Card>
  );
}
