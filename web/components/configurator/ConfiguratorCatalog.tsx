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
  onAddItem: (product: Product) => void;
  onToggleExtra: (product: Product, checked: boolean) => void;
  onUpdateExtra: (productId: number, updater: (current: ConfiguratorExtraSelection) => ConfiguratorExtraSelection) => void;
}

export default function ConfiguratorCatalog({
  items,
  starterProducts,
  extras,
  configuration,
  layoutStarted,
  onAddItem,
  onToggleExtra,
  onUpdateExtra,
}: ConfiguratorCatalogProps) {
  const selectedExtras = new Map(configuration.extras.map((extra) => [extra.product_id, extra]));

  return (
    <div className="space-y-6">
      {!layoutStarted && (
        <Card>
          <CardHeader>
            <CardTitle>Starter boxes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {starterProducts.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No starter boxes are configured yet. Edit a CONFIGURATOR product and enable{' '}
                <span className="font-medium text-foreground">Starter box</span> so users can begin a layout.
              </p>
            ) : (
              starterProducts.map((product) => (
                <div key={product.id} className="flex items-center justify-between gap-3 rounded-md border p-3">
                  <div>
                    <p className="font-medium">{product.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {product.configurator_width ?? '—'}m x {product.configurator_length ?? '—'}m
                    </p>
                  </div>
                  <Button type="button" variant="outline" onClick={() => onAddItem(product)}>
                    Add
                  </Button>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      )}

      <Card className={cn(!layoutStarted && 'opacity-60')}>
        <CardHeader>
          <CardTitle>Configurator Items</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {!layoutStarted ? (
            <p className="text-sm text-muted-foreground">
              Add a starter box on the canvas to unlock the rest of the catalogue.
            </p>
          ) : items.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No configurator products are active yet. Create products with the `CONFIGURATOR` category first.
            </p>
          ) : (
            items.map((product) => (
              <div key={product.id} className="flex items-center justify-between gap-3 rounded-md border p-3">
                <div>
                  <p className="font-medium">{product.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {product.configurator_width ?? '—'}m x {product.configurator_length ?? '—'}m
                  </p>
                </div>
                <Button type="button" variant="outline" onClick={() => onAddItem(product)}>
                  Add
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Configurator Extras</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {extras.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No configurator extras are available yet. On each optional extra, enable{' '}
              <span className="font-medium text-foreground">Allow in configurator</span> so it appears here.{' '}
              <Link href="/products/optional-extras" className="font-medium text-primary underline-offset-4 hover:underline">
                Manage optional extras
              </Link>
            </p>
          ) : (
            extras.map((product) => {
              const selected = selectedExtras.get(product.id);
              const isPerBox = product.unit === 'Per Box';
              return (
                <div key={product.id} className="rounded-md border p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="font-medium">{product.name}</p>
                      <p className="text-sm text-muted-foreground">
                        £{Number(product.base_price).toFixed(2)} {product.unit ? `· ${product.unit}` : ''}
                      </p>
                    </div>
                    <ConfiguratorExtraIconButton
                      product={product}
                      selected={Boolean(selected)}
                      onToggle={() => onToggleExtra(product, !selected)}
                    />
                  </div>
                  {selected && !isPerBox && (
                    <div className="mt-3 space-y-2">
                      <Label htmlFor={`extra-qty-${product.id}`}>Quantity</Label>
                      <Input
                        id={`extra-qty-${product.id}`}
                        type="number"
                        min={1}
                        step="1"
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
                    <p className="mt-3 text-xs text-muted-foreground">
                      Quantity is calculated automatically from the number of boxes because this extra uses the
                      `Per Box` unit.
                    </p>
                  )}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>
    </div>
  );
}
