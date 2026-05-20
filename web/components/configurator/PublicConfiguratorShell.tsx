'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import ConfiguratorCanvas from '@/components/configurator/ConfiguratorCanvas';
import ConfiguratorCatalog from '@/components/configurator/ConfiguratorCatalog';
import ConfiguratorLogo from '@/components/configurator/ConfiguratorLogo';
import {
  getApiErrorDetail,
  getPublicConfiguratorCatalog,
  previewPublicConfiguratorConfiguration,
  savePublicConfiguratorConfiguration,
  submitPublicConfiguratorLayout,
} from '@/lib/api';
import {
  addProductToConfiguration,
  canAddConfiguratorProduct,
  canRemoveConfiguratorBox,
  createEmptyConfiguration,
  getCatalogBoxProducts,
  getPlacedStarterProduct,
  getStarterProducts,
  layoutHasStarterBox,
} from '@/lib/configurator/defaults';
import { findPlacementCandidate, normalizeRotation } from '@/lib/configurator/geometry';
import { formatCurrency, getPreviewIssueCount } from '@/lib/configurator/summary';
import type {
  ConfiguratorBoxPlacement,
  ConfiguratorCatalogResponse,
  ConfiguratorDeliveryEstimateInclusion,
  ConfiguratorExtraSelection,
  ConfiguratorPreviewResponse,
  Product,
  PublicConfiguratorContext,
  QuoteConfigurationPayload,
} from '@/lib/types';

const DELIVERY_LINE_DESCRIPTIONS = new Set(['Delivery only', 'Delivery & Installation']);

function filterConfiguratorCatalogExtras(
  catalog: ConfiguratorCatalogResponse
): ConfiguratorCatalogResponse {
  return {
    ...catalog,
    extras: catalog.extras.filter((product) => product.allow_in_configurator),
  };
}

function pruneConfigurationExtras(
  configuration: QuoteConfigurationPayload,
  allowedExtraProductIds: Set<number>
): QuoteConfigurationPayload {
  if (configuration.extras.length === 0) return configuration;
  return {
    ...configuration,
    extras: configuration.extras.filter((extra) => allowedExtraProductIds.has(extra.product_id)),
  };
}

function stableConfigurationKey(configuration: QuoteConfigurationPayload): string {
  return JSON.stringify(configuration);
}

interface PublicConfiguratorShellProps {
  token: string;
  initialContext: PublicConfiguratorContext;
  customerPostcode: string;
  onSubmitted: () => void;
}

export default function PublicConfiguratorShell({
  token,
  initialContext,
  customerPostcode,
  onSubmitted,
}: PublicConfiguratorShellProps) {
  const [catalog, setCatalog] = useState<ConfiguratorCatalogResponse>({ items: [], extras: [] });
  const [configuration, setConfiguration] = useState<QuoteConfigurationPayload>(() =>
    initialContext.configuration ?? createEmptyConfiguration()
  );
  const [preview, setPreview] = useState<ConfiguratorPreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [layoutLoaded, setLayoutLoaded] = useState(false);
  const [autosaveStatus, setAutosaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const persistedConfigurationKeyRef = useRef('');
  const [selectedBoxId, setSelectedBoxId] = useState<string | null>(null);

  const productMap = useMemo(() => {
    const rows = [...catalog.items, ...catalog.extras];
    return rows.reduce<Record<number, Product>>((acc, product) => {
      acc[product.id] = product;
      return acc;
    }, {});
  }, [catalog]);

  const starterProducts = useMemo(() => getStarterProducts(catalog.items), [catalog.items]);
  const catalogBoxProducts = useMemo(() => getCatalogBoxProducts(catalog.items), [catalog.items]);
  const placedStarterProduct = useMemo(
    () => getPlacedStarterProduct(configuration.boxes, productMap),
    [configuration.boxes, productMap]
  );
  const hasStarterOnLayout = layoutHasStarterBox(configuration.boxes, productMap);

  const errorCount = getPreviewIssueCount(preview, 'error');
  const warningCount = getPreviewIssueCount(preview, 'warning');
  const deliveryInclusion: ConfiguratorDeliveryEstimateInclusion =
    configuration.delivery_estimate_inclusion ?? 'none';

  const deliveryPreviewLine = useMemo(() => {
    if (!preview?.items?.length || deliveryInclusion === 'none') return null;
    return (
      preview.items.find(
        (item) =>
          item.line_type === 'DELIVERY' ||
          DELIVERY_LINE_DESCRIPTIONS.has(item.description)
      ) ?? null
    );
  }, [preview?.items, deliveryInclusion]);

  const deliveryDisabledReason = !customerPostcode.trim()
    ? 'Add your delivery postcode above to estimate delivery.'
    : null;

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        const catalogResponse = await getPublicConfiguratorCatalog();
        if (cancelled) return;
        const catalogFiltered = filterConfiguratorCatalogExtras(catalogResponse);
        const allowedExtraProductIds = new Set(catalogFiltered.extras.map((p) => p.id));
        const loaded =
          initialContext.configuration ?? createEmptyConfiguration();
        const nextConfiguration = pruneConfigurationExtras(loaded, allowedExtraProductIds);
        setCatalog(catalogFiltered);
        setConfiguration(nextConfiguration);
        setSelectedBoxId(nextConfiguration.boxes[0]?.id ?? null);
        persistedConfigurationKeyRef.current = stableConfigurationKey(nextConfiguration);
        setLayoutLoaded(true);
      } catch (error) {
        if (!cancelled) {
          toast.error(getApiErrorDetail(error) || 'Failed to load layout builder');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [token, initialContext.configuration]);

  useEffect(() => {
    if (!layoutLoaded || loading || saving || submitting) return;
    const key = stableConfigurationKey(configuration);
    if (key === persistedConfigurationKeyRef.current) return;
    const timeoutId = window.setTimeout(async () => {
      try {
        setAutosaveStatus('saving');
        const saved = await savePublicConfiguratorConfiguration(token, configuration);
        const next = saved.configuration ?? configuration;
        persistedConfigurationKeyRef.current = stableConfigurationKey(next);
        setConfiguration(next);
        setAutosaveStatus('saved');
      } catch {
        setAutosaveStatus('error');
      }
    }, 400);
    return () => window.clearTimeout(timeoutId);
  }, [configuration, layoutLoaded, loading, saving, submitting, token]);

  useEffect(() => {
    if (loading) return;
    const timeoutId = window.setTimeout(async () => {
      try {
        const response = await previewPublicConfiguratorConfiguration(
          token,
          configuration,
          customerPostcode
        );
        setPreview(response);
      } catch {
        setPreview(null);
      }
    }, 250);
    return () => window.clearTimeout(timeoutId);
  }, [configuration, loading, customerPostcode, token]);

  const updateConfiguration = (next: QuoteConfigurationPayload) => {
    setConfiguration(next);
    if (selectedBoxId && !next.boxes.some((box) => box.id === selectedBoxId)) {
      setSelectedBoxId(next.boxes[0]?.id ?? null);
    }
  };

  const handleAddItem = (product: Product) => {
    if (!canAddConfiguratorProduct(configuration.boxes, product, productMap)) {
      if (product.configurator_is_starter_box && hasStarterOnLayout) {
        toast.error('Only one starter box per layout.');
      } else {
        toast.error('Place a starter box first.');
      }
      return;
    }
    const next = addProductToConfiguration(configuration, product, productMap, selectedBoxId);
    updateConfiguration(next);
    setSelectedBoxId(next.boxes[next.boxes.length - 1]?.id ?? null);
  };

  const handleSetDeliveryInclusion = (mode: ConfiguratorDeliveryEstimateInclusion) => {
    const current = configuration.delivery_estimate_inclusion ?? 'none';
    updateConfiguration({
      ...configuration,
      delivery_estimate_inclusion: current === mode ? 'none' : mode,
    });
  };

  const handleToggleExtra = (product: Product, checked: boolean) => {
    if (checked) {
      updateConfiguration({
        ...configuration,
        extras: [...configuration.extras, { product_id: product.id, quantity: 1 }],
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
    const product = productMap[current.product_id];
    if (product?.configurator_is_corner_box) {
      toast.error('Corner boxes cannot be rotated.');
      return;
    }
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
          : 'That rotation is not allowed here.'
      );
      return;
    }
    updateConfiguration({
      ...configuration,
      boxes: configuration.boxes.map((box) =>
        box.id === boxId ? { ...box, x: candidate.x, y: candidate.y, rotation: rotatedBox.rotation } : box
      ),
    });
  };

  const handleRemoveBox = (boxId: string) => {
    if (!canRemoveConfiguratorBox(configuration.boxes, boxId, productMap)) {
      toast.error('Remove other boxes before deleting the starter.');
      return;
    }
    updateConfiguration({
      ...configuration,
      boxes: configuration.boxes.filter((box) => box.id !== boxId),
    });
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const saved = await savePublicConfiguratorConfiguration(token, configuration);
      const next = saved.configuration ?? configuration;
      persistedConfigurationKeyRef.current = stableConfigurationKey(next);
      setConfiguration(next);
      setAutosaveStatus('saved');
      toast.success('Progress saved');
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = async () => {
    if (!preview?.valid) {
      toast.error('Fix layout errors before submitting.');
      return;
    }
    if (!window.confirm('Submit your layout to Cheshire Stables? You can still ask us to change it later.')) {
      return;
    }
    try {
      setSubmitting(true);
      await savePublicConfiguratorConfiguration(token, configuration);
      await submitPublicConfiguratorLayout(token);
      toast.success('Layout submitted — thank you!');
      onSubmitted();
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to submit layout');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="py-16 text-center text-muted-foreground">Loading layout builder…</div>
    );
  }

  const subtotalFormatted = formatCurrency(preview?.subtotal ?? 0);
  const boxTotal = preview?.total_boxes ?? configuration.boxes.length;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-4">
          <ConfiguratorLogo className="h-10" />
          <p className="text-sm text-muted-foreground">
            {initialContext.customer_name ? `Hi ${initialContext.customer_name}` : 'Design your layout'}
            {autosaveStatus === 'saving' && (
              <span className="ml-2 text-xs">Saving…</span>
            )}
            {autosaveStatus === 'saved' && (
              <span className="ml-2 text-xs text-emerald-600">Saved</span>
            )}
          </p>
          <div className="flex flex-wrap items-stretch gap-2 text-sm">
            <div className="min-w-[4.5rem] shrink-0 rounded-md border px-3 py-2">
              <p className="text-xs text-muted-foreground">Boxes</p>
              <p className="text-lg font-semibold tabular-nums">{boxTotal}</p>
            </div>
            <div className="min-w-[11rem] shrink-0 rounded-md border px-3 py-2.5">
              <p className="text-xs text-muted-foreground">Estimated subtotal</p>
              <p className="text-xl font-semibold tabular-nums">{subtotalFormatted}</p>
              <p className="text-xs text-muted-foreground">Ex VAT · indicative only</p>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={() => void handleSave()} disabled={saving || submitting}>
            {saving ? 'Saving…' : 'Save progress'}
          </Button>
          <Button size="sm" onClick={() => void handleSubmit()} disabled={submitting || !preview?.valid}>
            {submitting ? 'Submitting…' : 'Submit layout'}
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)_260px] lg:items-start">
        <ConfiguratorCatalog
          className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-8rem)]"
          boxProducts={catalogBoxProducts}
          starterProducts={starterProducts}
          placedStarterProduct={placedStarterProduct}
          hasStarterOnLayout={hasStarterOnLayout}
          extras={catalog.extras}
          configuration={configuration}
          boxCount={configuration.boxes.length}
          extraQuantityByProductId={
            new Map(
              (preview?.items ?? [])
                .filter((item) => item.product_id != null)
                .map((item) => [item.product_id as number, Number(item.quantity)])
            )
          }
          onAddItem={handleAddItem}
          onToggleExtra={handleToggleExtra}
          onUpdateExtra={handleUpdateExtra}
          deliveryInclusion={deliveryInclusion}
          onSetDeliveryInclusion={handleSetDeliveryInclusion}
          deliveryLineUnitPrice={
            deliveryPreviewLine != null ? Number(deliveryPreviewLine.unit_price) : null
          }
          deliveryLineQuantity={
            deliveryPreviewLine != null ? Number(deliveryPreviewLine.quantity) : 1
          }
          deliveryDisabledReason={deliveryDisabledReason}
        />

        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Layout</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <ConfiguratorCanvas
              boxes={configuration.boxes}
              productMap={productMap}
              selectedBoxId={selectedBoxId}
              onSelect={setSelectedBoxId}
              onMoveBox={handleMoveBox}
              onRotateBox={handleSetRotation}
              onRemoveBox={handleRemoveBox}
              canRemoveBox={(boxId) => canRemoveConfiguratorBox(configuration.boxes, boxId, productMap)}
            />
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Layout name</CardTitle>
            </CardHeader>
            <CardContent>
              <Input
                value={configuration.name ?? ''}
                onChange={(event) =>
                  updateConfiguration({ ...configuration, name: event.target.value })
                }
                placeholder="e.g. Four-box run"
                className="h-9"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Validation</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className={`rounded-md border px-2 py-1.5 ${errorCount > 0 ? 'border-red-200 bg-red-50/50' : ''}`}>
                  <p className="text-xs text-muted-foreground">Errors</p>
                  <p className={`text-lg font-semibold tabular-nums ${errorCount > 0 ? 'text-red-700' : ''}`}>
                    {errorCount}
                  </p>
                </div>
                <div className={`rounded-md border px-2 py-1.5 ${warningCount > 0 ? 'border-amber-200 bg-amber-50/50' : ''}`}>
                  <p className="text-xs text-muted-foreground">Warnings</p>
                  <p className={`text-lg font-semibold tabular-nums ${warningCount > 0 ? 'text-amber-800' : ''}`}>
                    {warningCount}
                  </p>
                </div>
              </div>
              <div className="max-h-36 space-y-1.5 overflow-y-auto">
                {preview?.issues?.length ? (
                  preview.issues.map((issue, index) => (
                    <div
                      key={`${issue.code}-${index}`}
                      className={`rounded-md border px-2 py-1.5 text-xs ${
                        issue.severity === 'error'
                          ? 'border-red-200 bg-red-50 text-red-800'
                          : 'border-amber-200 bg-amber-50 text-amber-800'
                      }`}
                    >
                      <p className="font-medium">{issue.message}</p>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-emerald-700">No validation issues.</p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Lines preview</CardTitle>
            </CardHeader>
            <CardContent>
              {preview?.items?.length ? (
                <div className="max-h-40 overflow-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th className="py-1 text-left font-medium">Item</th>
                        <th className="py-1 text-right font-medium">Qty</th>
                        <th className="py-1 text-right font-medium">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.items.map((item, index) => (
                        <tr key={`${item.description}-${index}`} className="border-b border-border/50 last:border-0">
                          <td className="max-w-[7rem] truncate py-1 pr-2">{item.description}</td>
                          <td className="py-1 text-right tabular-nums">{Number(item.quantity).toFixed(0)}</td>
                          <td className="py-1 text-right tabular-nums whitespace-nowrap">
                            {formatCurrency(Number(item.quantity) * Number(item.unit_price))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Add boxes to preview lines.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
