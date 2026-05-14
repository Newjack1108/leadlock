'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';

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
import { findPlacementCandidate, normalizeRotation } from '@/lib/configurator/geometry';
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

  const handleSetRotation = (boxId: string, rotation: number) => {
    if (!Number.isFinite(rotation)) return;
    const current = configuration.boxes.find((box) => box.id === boxId);
    if (!current) return;
    const rotatedBox = { ...current, rotation: normalizeRotation(rotation) };
    const candidate = findPlacementCandidate({
      movingBox: rotatedBox,
      rawX: rotatedBox.x,
      rawY: rotatedBox.y,
      boxes: configuration.boxes.map((box) => (box.id === boxId ? rotatedBox : box)),
      productMap,
      threshold: 0,
    });
    if (!candidate.valid) {
      toast.error(
        candidate.overlaps
          ? 'That rotation would overlap another box.'
          : candidate.frontBlocked
            ? 'The front of this box must stay on an exposed face.'
            : 'That rotation would disconnect the layout.'
      );
      return;
    }
    updateConfiguration({
      ...configuration,
      boxes: configuration.boxes.map((box) => (box.id === boxId ? rotatedBox : box)),
    });
  };

  const handleRemoveBox = (boxId: string) => {
    updateConfiguration({
      ...configuration,
      boxes: configuration.boxes.filter((box) => box.id !== boxId),
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
                onRotateBox={handleSetRotation}
                onRemoveBox={handleRemoveBox}
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
