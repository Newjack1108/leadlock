'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import {
  AlertTriangle,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  CheckCircle2,
  RotateCw,
  Trash2,
} from 'lucide-react';

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
import { findPlacementCandidate } from '@/lib/configurator/geometry';
import { formatCurrency, getPreviewIssueCount } from '@/lib/configurator/summary';
import type {
  ConfiguratorBoxPlacement,
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

function normalizeRotation(value: number): 0 | 90 | 180 | 270 {
  const next = ((value % 360) + 360) % 360;
  if (next === 90 || next === 180 || next === 270) return next;
  return 0;
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
  const selectedProduct = selectedBox ? productMap[selectedBox.product_id] ?? null : null;
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
    const next = addProductToConfiguration(configuration, product, productMap, selectedBoxId);
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

  const handleMoveBox = (boxId: string, nextBox: Pick<ConfiguratorBoxPlacement, 'x' | 'y'>) => {
    updateConfiguration({
      ...configuration,
      boxes: configuration.boxes.map((box) =>
        box.id === boxId ? { ...box, x: nextBox.x, y: nextBox.y } : box
      ),
    });
  };

  const handleRotateBox = (boxId: string, delta = 90) => {
    const current = configuration.boxes.find((box) => box.id === boxId);
    if (!current) return;
    const rotatedBox = { ...current, rotation: normalizeRotation(current.rotation + delta) };
    const candidate = findPlacementCandidate({
      movingBox: rotatedBox,
      rawX: rotatedBox.x,
      rawY: rotatedBox.y,
      boxes: configuration.boxes.map((box) => (box.id === boxId ? rotatedBox : box)),
      productMap,
      threshold: 0,
    });
    if (!candidate.valid) {
      toast.error('Rotating here would create an overlap or disconnect the layout.');
      return;
    }
    updateConfiguration({
      ...configuration,
      boxes: configuration.boxes.map((box) => (box.id === boxId ? rotatedBox : box)),
    });
  };

  const handleNudgeSelectedBox = (dx: number, dy: number) => {
    if (!selectedBox) return;
    const candidate = findPlacementCandidate({
      movingBox: selectedBox,
      rawX: Number((selectedBox.x + dx).toFixed(2)),
      rawY: Number((selectedBox.y + dy).toFixed(2)),
      boxes: configuration.boxes,
      productMap,
      threshold: 0,
    });
    if (!candidate.valid) {
      toast.error(candidate.overlaps ? 'That nudge would overlap another box.' : 'That nudge would disconnect the layout.');
      return;
    }
    handleMoveBox(selectedBox.id, {
      x: candidate.x,
      y: candidate.y,
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
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold">Quote Configurator</h1>
          <p className="mt-1 text-muted-foreground">
            {quote.quote_number} · {quote.customer_name || 'Draft quote'}
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            Drag boxes on the canvas to build the layout. Boxes snap to valid edges, cannot overlap, and the front
            marker rotates with each box.
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

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-6">
          <Card>
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <CardTitle>Layout Canvas</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  The canvas is the main workspace. Drag boxes to reposition them, and use rotation on the selected
                  box when you need to turn a corner.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                <div className="rounded-md border px-3 py-2">
                  <p className="text-muted-foreground">Boxes</p>
                  <p className="text-lg font-semibold">{preview?.total_boxes ?? configuration.boxes.length}</p>
                </div>
                <div className="rounded-md border px-3 py-2">
                  <p className="text-muted-foreground">Errors</p>
                  <p className="text-lg font-semibold">{errorCount}</p>
                </div>
                <div className="rounded-md border px-3 py-2">
                  <p className="text-muted-foreground">Warnings</p>
                  <p className="text-lg font-semibold">{warningCount}</p>
                </div>
                <div className="rounded-md border px-3 py-2">
                  <p className="text-muted-foreground">Subtotal</p>
                  <p className="text-lg font-semibold">{formatCurrency(preview?.subtotal ?? 0)}</p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <ConfiguratorCanvas
                boxes={configuration.boxes}
                productMap={productMap}
                selectedBoxId={selectedBoxId}
                onSelect={setSelectedBoxId}
                onMoveBox={handleMoveBox}
              />
              <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                The front marker is visual only in this beta. It rotates with the box so you can quickly read layout
                orientation without adding more product metadata yet.
              </div>
            </CardContent>
          </Card>

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

        <div className="space-y-6 xl:sticky xl:top-4 xl:self-start">
          <Card>
            <CardHeader>
              <CardTitle>Layout Metadata</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
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
              </div>
              <div className="space-y-2">
                <Label>Schema Version</Label>
                <Input value={String(configuration.schema_version ?? 1)} disabled />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Selected Box</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {selectedBox && selectedProduct ? (
                <>
                  <div>
                    <p className="font-medium">{selectedProduct.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {selectedProduct.configurator_width ?? '—'}m x {selectedProduct.configurator_length ?? '—'}m
                    </p>
                  </div>

                  <div className="grid grid-cols-3 gap-2 rounded-md border p-3 text-sm">
                    <div>
                      <p className="text-muted-foreground">X</p>
                      <p className="font-medium">{selectedBox.x.toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Y</p>
                      <p className="font-medium">{selectedBox.y.toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Rotation</p>
                      <p className="font-medium">{selectedBox.rotation}°</p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <p className="text-sm font-medium">Nudge</p>
                    <div className="grid grid-cols-3 gap-2">
                      <div />
                      <Button variant="outline" size="sm" onClick={() => handleNudgeSelectedBox(0, -0.25)}>
                        <ArrowUp className="h-4 w-4" />
                      </Button>
                      <div />
                      <Button variant="outline" size="sm" onClick={() => handleNudgeSelectedBox(-0.25, 0)}>
                        <ArrowLeft className="h-4 w-4" />
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleNudgeSelectedBox(0, 0.25)}>
                        <ArrowDown className="h-4 w-4" />
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleNudgeSelectedBox(0.25, 0)}>
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handleRotateBox(selectedBox.id, 90)}
                    >
                      <RotateCw className="mr-2 h-4 w-4" />
                      Rotate 90°
                    </Button>
                    <Button type="button" variant="destructive" size="sm" onClick={handleRemoveSelectedBox}>
                      <Trash2 className="mr-2 h-4 w-4" />
                      Remove
                    </Button>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Select a box on the canvas to rotate it, nudge it slightly, or remove it.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Validation</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {preview?.issues?.length ? (
                preview.issues.map((issue, index) => (
                  <div
                    key={`${issue.code}-${index}`}
                    className={`rounded-md border p-3 text-sm ${
                      issue.severity === 'error'
                        ? 'border-red-200 bg-red-50 text-red-800'
                        : 'border-amber-200 bg-amber-50 text-amber-800'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      {issue.severity === 'error' ? (
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      ) : (
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                      )}
                      <div>
                        <p className="font-medium">{issue.message}</p>
                        {issue.box_ids.length > 0 && (
                          <p className="mt-1 text-xs opacity-80">Items: {issue.box_ids.join(', ')}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
                  <div className="flex items-start gap-2">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                    <p>No validation issues. This layout is ready to save or apply.</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <ConfiguratorCatalog
            items={catalog.items}
            extras={catalog.extras}
            configuration={configuration}
            onAddItem={handleAddItem}
            onToggleExtra={handleToggleExtra}
            onUpdateExtra={handleUpdateExtra}
          />
        </div>
      </div>
    </div>
  );
}
