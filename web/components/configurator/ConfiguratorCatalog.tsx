'use client';

import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type {
  ConfiguratorExtraSelection,
  Product,
  QuoteConfigurationPayload,
} from '@/lib/types';
import ConfiguratorExtraIconButton from '@/components/configurator/ConfiguratorExtraIconButton';
import { cn } from '@/lib/utils';

interface ConfiguratorCatalogProps {
  items: Product[];
  starterProducts: Product[];
  extras: Product[];
  configuration: QuoteConfigurationPayload;
  layoutStarted: boolean;
  boxCount: number;
  extraQuantityByProductId: Map<number, number>;
  onAddItem: (product: Product) => void;
  onToggleExtra: (product: Product, checked: boolean) => void;
  onUpdateExtra: (productId: number, updater: (current: ConfiguratorExtraSelection) => ConfiguratorExtraSelection) => void;
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
  return (
    <div className="flex items-center gap-2 rounded-md border px-2 py-1.5">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium leading-tight">{product.name}</p>
        <p className="text-xs text-muted-foreground tabular-nums">
          {product.configurator_width ?? '—'}m × {product.configurator_length ?? '—'}m
        </p>
      </div>
      <Button type="button" variant="outline" size="sm" className="h-7 shrink-0 px-2" onClick={onAdd}>
        Add
      </Button>
    </div>
  );
}

export default function ConfiguratorCatalog({
  items,
  starterProducts,
  extras,
  configuration,
  layoutStarted,
  boxCount,
  extraQuantityByProductId,
  onAddItem,
  onToggleExtra,
  onUpdateExtra,
  className,
}: ConfiguratorCatalogProps) {
  const selectedExtras = new Map(configuration.extras.map((extra) => [extra.product_id, extra]));

  return (
    <Card className={cn('flex max-h-[inherit] flex-col', className)}>
      <CardHeader className="shrink-0 pb-3">
        <CardTitle className="text-base">Catalogue</CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pb-4">
        {!layoutStarted && (
          <CatalogSection title="Starter boxes">
            {starterProducts.length === 0 ? (
              <p className="text-xs text-muted-foreground">No starter boxes configured.</p>
            ) : (
              starterProducts.map((product) => (
                <ProductRow key={product.id} product={product} onAdd={() => onAddItem(product)} />
              ))
            )}
          </CatalogSection>
        )}

        <CatalogSection
          title="Boxes"
          className={cn(!layoutStarted && 'border-t pt-3', !layoutStarted && 'opacity-60')}
        >
          {!layoutStarted ? (
            <p className="text-xs text-muted-foreground">Add a starter box to unlock.</p>
          ) : items.length === 0 ? (
            <p className="text-xs text-muted-foreground">No configurator products yet.</p>
          ) : (
            items.map((product) => (
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
                      <p className="truncate text-sm font-medium leading-tight">{product.name}</p>
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
      </CardContent>
    </Card>
  );
}
