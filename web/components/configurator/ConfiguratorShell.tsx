'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import ConfiguratorCanvas from '@/components/configurator/ConfiguratorCanvas';
import ConfiguratorCatalog from '@/components/configurator/ConfiguratorCatalog';
import {
  applyQuoteConfiguration,
  getApiErrorDetail,
  getConfiguratorCatalog,
  getQuoteConfiguration,
  previewConfiguratorConfiguration,
  saveQuoteConfiguration,
} from '@/lib/api';
import { addProductToConfiguration, createEmptyConfiguration } from '@/lib/configurator/defaults';
import { formatCurrency, getPreviewIssueCount } from '@/lib/configurator/summary';
import type {
  ConfiguratorCatalogResponse,
  ConfiguratorExtraSelection,
  ConfiguratorPreviewResponse,
  Product,
  Quote,
  QuoteConfigurationPayload,
} from '@/lib/types';

interface ConfiguratorShellProps {
  quote: Quote;
}

export default function ConfiguratorShell({ quote }: ConfiguratorShellProps) {
  const router = useRouter();
  const [catalog, setCatalog] = useState<ConfiguratorCatalogResponse>({ items: [], extras: [] });
  const [configuration, setConfiguration] = useState<QuoteConfigurationPayload>(createEmptyConfiguration());
  const [preview, setPreview] = useState<ConfiguratorPreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [selectedBoxId, setSelectedBoxId] = useState<string | null>(null);

  const productMap = useMemo(() => {
    const rows = [...catalog.items, ...catalog.extras];
    return rows.reduce<Record<number, Product>>((acc, product) => {
      acc[product.id] = product;
      return acc;
    }, {});
  }, [catalog]);

  const selectedBox = configuration.boxes.find((box) => box.id === selectedBoxId) ?? null;
  const errorCount = getPreviewIssueCount(preview, 'error');
  const warningCount = getPreviewIssueCount(preview, 'warning');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        const [catalogResponse, savedConfiguration] = await Promise.all([
          getConfiguratorCatalog(),
          getQuoteConfiguration(quote.id).catch((error) => {
            if ((error as { response?: { status?: number } })?.response?.status === 404) {
              return null;
            }
            throw error;
          }),
        ]);
        if (cancelled) return;
        setCatalog(catalogResponse);
        const nextConfiguration = savedConfiguration?.configuration ?? createEmptyConfiguration(quote.quote_number);
        setConfiguration(nextConfiguration);
        setSelectedBoxId(nextConfiguration.boxes[0]?.id ?? null);
      } catch (error) {
        if (!cancelled) {
          toast.error(getApiErrorDetail(error) || 'Failed to load configurator data');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [quote.id, quote.quote_number]);

  useEffect(() => {
    if (loading) return;
    const timeoutId = window.setTimeout(async () => {
      try {
        const response = await previewConfiguratorConfiguration(configuration);
        setPreview(response);
      } catch {
        setPreview(null);
      }
    }, 250);
    return () => window.clearTimeout(timeoutId);
  }, [configuration, loading]);

  const updateConfiguration = (next: QuoteConfigurationPayload) => {
    setConfiguration(next);
    if (selectedBoxId && !next.boxes.some((box) => box.id === selectedBoxId)) {
      setSelectedBoxId(next.boxes[0]?.id ?? null);
    }
  };

  const handleAddItem = (product: Product) => {
    const next = addProductToConfiguration(configuration, product);
    updateConfiguration(next);
    setSelectedBoxId(next.boxes[next.boxes.length - 1]?.id ?? null);
  };

  const handleToggleExtra = (product: Product, checked: boolean) => {
    if (checked) {
      updateConfiguration({
        ...configuration,
        extras: [...configuration.extras, { product_id: product.id, quantity: product.unit === 'Per Box' ? undefined : 1 }],
      });
      return;
    }
    updateConfiguration({
      ...configuration,
      extras: configuration.extras.filter((extra) => extra.product_id !== product.id),
    });
  };

  const handleUpdateExtra = (
    productId: number,
    updater: (current: ConfiguratorExtraSelection) => ConfiguratorExtraSelection
  ) => {
    updateConfiguration({
      ...configuration,
      extras: configuration.extras.map((extra) =>
        extra.product_id === productId ? updater(extra) : extra
      ),
    });
  };

  const handleUpdateSelectedBox = (field: 'x' | 'y' | 'rotation', value: number) => {
    if (!selectedBox) return;
    updateConfiguration({
      ...configuration,
      boxes: configuration.boxes.map((box) =>
        box.id === selectedBox.id ? { ...box, [field]: value } : box
      ),
    });
  };

  const handleRemoveSelectedBox = () => {
    if (!selectedBox) return;
    updateConfiguration({
      ...configuration,
      boxes: configuration.boxes.filter((box) => box.id !== selectedBox.id),
    });
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const saved = await saveQuoteConfiguration(quote.id, configuration);
      setConfiguration(saved.configuration);
      toast.success('Configurator layout saved');
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to save configurator layout');
    } finally {
      setSaving(false);
    }
  };

  const handleApply = async () => {
    try {
      setApplying(true);
      await saveQuoteConfiguration(quote.id, configuration);
      await applyQuoteConfiguration(quote.id);
      toast.success('Configurator layout applied to draft quote');
      router.push(`/quotes/${quote.id}/edit`);
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to apply configurator layout');
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold">Quote Configurator</h1>
          <p className="mt-1 text-muted-foreground">
            {quote.quote_number} · {quote.customer_name || 'Draft quote'}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button variant="outline" onClick={() => router.push(`/quotes/${quote.id}`)}>
            Back to Quote
          </Button>
          <Button variant="secondary" onClick={() => void handleSave()} disabled={loading || saving}>
            {saving ? 'Saving...' : 'Save Layout'}
          </Button>
          <Button onClick={() => void handleApply()} disabled={loading || applying || !preview?.valid}>
            {applying ? 'Applying...' : 'Apply to Draft Quote'}
          </Button>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <ConfiguratorCatalog
          items={catalog.items}
          extras={catalog.extras}
          configuration={configuration}
          onAddItem={handleAddItem}
          onToggleExtra={handleToggleExtra}
          onUpdateExtra={handleUpdateExtra}
        />

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Layout Metadata</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="layout-name">Saved Layout Name</Label>
                <Input
                  id="layout-name"
                  value={configuration.name ?? ''}
                  onChange={(event) =>
                    updateConfiguration({
                      ...configuration,
                      name: event.target.value,
                    })
                  }
                  placeholder="e.g. Four-box L shape"
                />
                <p className="text-xs text-muted-foreground">
                  Stored with the quote configuration now so reusable presets can be added later without changing
                  the payload shape.
                </p>
              </div>
              <div className="space-y-2">
                <Label>Schema Version</Label>
                <Input value={String(configuration.schema_version ?? 1)} disabled />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Layout Canvas</CardTitle>
            </CardHeader>
            <CardContent>
              <ConfiguratorCanvas
                boxes={configuration.boxes}
                productMap={productMap}
                selectedBoxId={selectedBoxId}
                onSelect={setSelectedBoxId}
              />
            </CardContent>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Selected Item</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {selectedBox ? (
                  <>
                    <div className="space-y-1">
                      <p className="font-medium">{productMap[selectedBox.product_id]?.name || 'Unknown item'}</p>
                      <p className="text-sm text-muted-foreground">Edit placement and rotation for the selected item.</p>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="box-x">X Position</Label>
                        <Input
                          id="box-x"
                          type="number"
                          step="0.25"
                          value={selectedBox.x}
                          onChange={(event) => handleUpdateSelectedBox('x', Number(event.target.value || 0))}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="box-y">Y Position</Label>
                        <Input
                          id="box-y"
                          type="number"
                          step="0.25"
                          value={selectedBox.y}
                          onChange={(event) => handleUpdateSelectedBox('y', Number(event.target.value || 0))}
                        />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="box-rotation">Rotation</Label>
                      <Input
                        id="box-rotation"
                        type="number"
                        step="90"
                        min={0}
                        max={270}
                        value={selectedBox.rotation}
                        onChange={(event) =>
                          handleUpdateSelectedBox('rotation', Number(event.target.value || 0) as 0 | 90 | 180 | 270)
                        }
                      />
                    </div>
                    <div className="flex gap-3">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() =>
                          handleUpdateSelectedBox(
                            'rotation',
                            (((selectedBox.rotation + 90) % 360) as 0 | 90 | 180 | 270)
                          )
                        }
                      >
                        Rotate 90°
                      </Button>
                      <Button type="button" variant="destructive" onClick={handleRemoveSelectedBox}>
                        Remove Item
                      </Button>
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Select a configurator item on the canvas to edit its position or rotation.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Preview Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <div className="rounded-md border p-3">
                    <p className="text-muted-foreground">Boxes</p>
                    <p className="text-lg font-semibold">{preview?.total_boxes ?? 0}</p>
                  </div>
                  <div className="rounded-md border p-3">
                    <p className="text-muted-foreground">Errors</p>
                    <p className="text-lg font-semibold">{errorCount}</p>
                  </div>
                  <div className="rounded-md border p-3">
                    <p className="text-muted-foreground">Warnings</p>
                    <p className="text-lg font-semibold">{warningCount}</p>
                  </div>
                </div>
                <div className="rounded-md border p-3">
                  <p className="text-sm text-muted-foreground">Preview subtotal</p>
                  <p className="text-xl font-semibold">{formatCurrency(preview?.subtotal ?? 0)}</p>
                </div>
                <div className="space-y-2">
                  <p className="text-sm font-medium">Validation</p>
                  {preview?.issues?.length ? (
                    <div className="space-y-2">
                      {preview.issues.map((issue, index) => (
                        <div
                          key={`${issue.code}-${index}`}
                          className={`rounded-md border p-3 text-sm ${
                            issue.severity === 'error'
                              ? 'border-red-200 bg-red-50 text-red-800'
                              : 'border-amber-200 bg-amber-50 text-amber-800'
                          }`}
                        >
                          <p className="font-medium">{issue.message}</p>
                          {issue.box_ids.length > 0 && (
                            <p className="mt-1 text-xs opacity-80">Items: {issue.box_ids.join(', ')}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No validation issues.</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Quote Lines Preview</CardTitle>
            </CardHeader>
            <CardContent>
              {preview?.items?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="py-2 text-left">Description</th>
                        <th className="py-2 text-right">Qty</th>
                        <th className="py-2 text-right">Unit Price</th>
                        <th className="py-2 text-right">Line Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.items.map((item, index) => (
                        <tr key={`${item.description}-${index}`} className="border-b last:border-0">
                          <td className="py-2">{item.description}</td>
                          <td className="py-2 text-right">{Number(item.quantity).toFixed(2)}</td>
                          <td className="py-2 text-right">{formatCurrency(item.unit_price)}</td>
                          <td className="py-2 text-right">
                            {formatCurrency(Number(item.quantity) * Number(item.unit_price))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Add configurator items to generate a quote line preview.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
