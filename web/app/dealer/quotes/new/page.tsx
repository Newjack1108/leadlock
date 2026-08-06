'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import DealerBrandStrip from '@/components/dealer/DealerBrandStrip';
import DealerPageShell from '@/components/dealer/DealerPageShell';
import DealerSection from '@/components/dealer/DealerSection';
import {
  createDealerQuote,
  estimateDeliveryInstall,
  getApiErrorDetail,
  getDealerDiscountPolicy,
  getDealerProducts,
  getDiscountTemplates,
  getProductOptionalExtras,
} from '@/lib/api';
import { ProductCategory } from '@/lib/types';
import type {
  DealerDeliveryEstimateInclusion,
  DeliveryInstallEstimateResponse,
  DiscountTemplate,
  Product,
} from '@/lib/types';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

type ProductRow = { product_id: number; quantity: number; selected_extra_ids: number[] };

export default function NewDealerQuotePage() {
  const router = useRouter();
  const [products, setProducts] = useState<Product[]>([]);
  const [customerName, setCustomerName] = useState('');
  const [customerEmail, setCustomerEmail] = useState('');
  const [customerPhone, setCustomerPhone] = useState('');
  const [customerAddress, setCustomerAddress] = useState('');
  const [customerPostcode, setCustomerPostcode] = useState('');
  const [rows, setRows] = useState<ProductRow[]>([]);
  const [extrasByProductId, setExtrasByProductId] = useState<Record<number, Product[]>>({});
  const [availableDiscounts, setAvailableDiscounts] = useState<DiscountTemplate[]>([]);
  const [selectedDiscountIds, setSelectedDiscountIds] = useState<number[]>([]);
  const [discountsLoading, setDiscountsLoading] = useState(true);
  const [discountsConfigured, setDiscountsConfigured] = useState(true);
  const [saving, setSaving] = useState(false);

  const [estDeliveryOnly, setEstDeliveryOnly] = useState<DeliveryInstallEstimateResponse | null>(null);
  const [estFull, setEstFull] = useState<DeliveryInstallEstimateResponse | null>(null);
  const [estLoading, setEstLoading] = useState(false);
  const [estErrDelivery, setEstErrDelivery] = useState<string | null>(null);
  const [estErrFull, setEstErrFull] = useState<string | null>(null);
  const [inclusion, setInclusion] = useState<DealerDeliveryEstimateInclusion>('none');

  useEffect(() => {
    getDealerProducts()
      .then((data: Product[]) =>
        setProducts(data.filter((product) => product.category === ProductCategory.STABLES))
      )
      .catch((err: unknown) => {
        setProducts([]);
        toast.error(getApiErrorDetail(err) || 'Could not load products. Check your account or try again.');
      });
  }, []);

  useEffect(() => {
    const loadDiscounts = async () => {
      setDiscountsLoading(true);
      try {
        const [policy, activeDiscounts] = await Promise.all([
          getDealerDiscountPolicy(),
          getDiscountTemplates(true),
        ]);
        const allowed = new Set(policy.allowed_discount_template_ids ?? []);
        setAvailableDiscounts(activeDiscounts.filter((discount: DiscountTemplate) => allowed.has(discount.id)));
        setDiscountsConfigured(true);
      } catch (err: unknown) {
        setAvailableDiscounts([]);
        setSelectedDiscountIds([]);
        const detail = getApiErrorDetail(err);
        const notConfigured = detail.toLowerCase().includes('not configured');
        setDiscountsConfigured(!notConfigured);
        if (!notConfigured) {
          toast.error(detail || 'Could not load dealer discounts');
        }
      } finally {
        setDiscountsLoading(false);
      }
    };
    void loadDiscounts();
  }, []);

  useEffect(() => {
    const productIds = rows.map((r) => r.product_id);
    if (!productIds.length) {
      setExtrasByProductId({});
      return;
    }
    let cancelled = false;
    const loadExtras = async () => {
      const entries = await Promise.all(
        productIds.map(async (productId) => {
          try {
            const extras = (await getProductOptionalExtras(productId)) as Product[];
            const dealerAllowed = extras.filter(
              (extra) => extra.is_active && extra.is_extra && extra.allow_trade_dealer_sale
            );
            return [productId, dealerAllowed] as const;
          } catch {
            return [productId, []] as const;
          }
        })
      );
      if (cancelled) return;
      setExtrasByProductId(Object.fromEntries(entries));
    };
    void loadExtras();
    return () => {
      cancelled = true;
    };
  }, [rows]);

  const installHours = useMemo(() => {
    return rows.reduce((total, row) => {
      const product = products.find((p) => p.id === row.product_id);
      const hrs = product?.installation_hours;
      if (hrs == null || Number(hrs) <= 0) return total;
      return total + row.quantity * Number(hrs);
    }, 0);
  }, [rows, products]);

  const deliveryBoxCount = useMemo(() => {
    return rows.reduce((total, row) => {
      const product = products.find((p) => p.id === row.product_id);
      const bpp = product?.boxes_per_product;
      const boxesPer = bpp == null || bpp < 1 ? 1 : bpp;
      return total + row.quantity * boxesPer;
    }, 0);
  }, [rows, products]);

  useEffect(() => {
    if (inclusion === 'delivery_and_install' && installHours <= 0) {
      setInclusion('none');
    }
  }, [installHours, inclusion]);

  const pcTrim = customerPostcode.trim();

  useEffect(() => {
    if (!pcTrim || !rows.length) {
      setEstDeliveryOnly(null);
      setEstFull(null);
      setEstErrDelivery(null);
      setEstErrFull(null);
      setEstLoading(false);
      return;
    }
    let cancelled = false;
    setEstLoading(true);
    setEstErrDelivery(null);
    setEstErrFull(null);

    const run = async () => {
      const settled = await Promise.allSettled([
        estimateDeliveryInstall(pcTrim, 0, {
          deliveryOnly: true,
          numberOfBoxes: deliveryBoxCount,
        }),
        ...(installHours > 0
          ? [estimateDeliveryInstall(pcTrim, installHours, { deliveryOnly: false })]
          : []),
      ]);
      if (cancelled) return;
      const onlyRes = settled[0];
      if (onlyRes.status === 'fulfilled') {
        setEstDeliveryOnly(onlyRes.value);
        setEstErrDelivery(null);
      } else {
        setEstDeliveryOnly(null);
        setEstErrDelivery(getApiErrorDetail(onlyRes.reason));
      }
      if (installHours > 0 && settled[1]) {
        const fullRes = settled[1];
        if (fullRes.status === 'fulfilled') {
          setEstFull(fullRes.value);
          setEstErrFull(null);
        } else {
          setEstFull(null);
          setEstErrFull(getApiErrorDetail(fullRes.reason));
        }
      } else {
        setEstFull(null);
        setEstErrFull(null);
      }
      setEstLoading(false);
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [pcTrim, rows, installHours, deliveryBoxCount]);

  const total = useMemo(() => {
    return rows.reduce((sum, row) => {
      const product = products.find((p) => p.id === row.product_id);
      if (!product) return sum;
      const extrasTotal = (extrasByProductId[row.product_id] ?? [])
        .filter((extra) => row.selected_extra_ids.includes(extra.id))
        .reduce((extraSum, extra) => extraSum + Number(extra.base_price) * row.quantity, 0);
      return sum + Number(product.base_price) * row.quantity + extrasTotal;
    }, 0);
  }, [rows, products, extrasByProductId]);

  const addProduct = (id: number) => {
    if (rows.some((r) => r.product_id === id)) return;
    setRows((prev) => [...prev, { product_id: id, quantity: 1, selected_extra_ids: [] }]);
  };

  const updateQty = (product_id: number, quantity: number) => {
    setRows((prev) => prev.map((r) => (r.product_id === product_id ? { ...r, quantity } : r)));
  };

  const removeRow = (product_id: number) => {
    setRows((prev) => prev.filter((r) => r.product_id !== product_id));
  };

  const toggleExtra = (product_id: number, extra_id: number, checked: boolean) => {
    setRows((prev) =>
      prev.map((r) => {
        if (r.product_id !== product_id) return r;
        const selected = checked
          ? Array.from(new Set([...r.selected_extra_ids, extra_id]))
          : r.selected_extra_ids.filter((id) => id !== extra_id);
        return { ...r, selected_extra_ids: selected };
      })
    );
  };

  /** Keep submit handler synchronous so React does not surface an unhandled rejection from an async `onSubmit`. */
  const submitQuoteAsync = async () => {
    setSaving(true);
    try {
      const quote = await createDealerQuote({
        customer_name: customerName.trim(),
        customer_email: customerEmail.trim() || undefined,
        customer_phone: customerPhone.trim() || undefined,
        customer_address: customerAddress.trim() || undefined,
        customer_postcode: pcTrim || undefined,
        delivery_estimate_inclusion: inclusion,
        discount_template_ids: selectedDiscountIds,
        product_items: rows.map((r) => ({
          product_id: r.product_id,
          quantity: r.quantity,
          selected_extra_ids: r.selected_extra_ids,
        })),
      });
      await router.push(`/dealer/quotes/${quote.id}`);
    } catch (err: unknown) {
      toast.error(getApiErrorDetail(err));
    } finally {
      setSaving(false);
    }
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerName.trim() || !rows.length) return;
    if (inclusion === 'delivery_and_install' && installHours <= 0) {
      toast.error('Add products with installation hours to include delivery & installation');
      return;
    }
    if (inclusion !== 'none' && inclusion !== 'collection' && !pcTrim) {
      toast.error('Enter customer postcode to include a delivery line');
      return;
    }
    if (inclusion === 'delivery_only' && estErrDelivery) {
      toast.error('Fix the delivery-only estimate error before creating the quote');
      return;
    }
    if (inclusion === 'delivery_and_install' && estErrFull) {
      toast.error('Fix the delivery & installation estimate error before creating the quote');
      return;
    }
    void submitQuoteAsync();
  };

  const canPickDeliveryOnly = !estErrDelivery && estDeliveryOnly && Number(estDeliveryOnly.cost_total) > 0;
  const canPickFull =
    installHours > 0 && !estErrFull && estFull && Number(estFull.cost_total) > 0;

  const submitBlocked =
    saving ||
    !rows.length ||
    (inclusion !== 'none' &&
      inclusion !== 'collection' &&
      (estLoading ||
        (inclusion === 'delivery_only' && !canPickDeliveryOnly) ||
        (inclusion === 'delivery_and_install' && !canPickFull)));

  return (
    <DealerPageShell>
      <div className="space-y-6">
        <DealerBrandStrip subtitle="Simple product quote" />
        <form onSubmit={onSubmit} className="space-y-8">
          <DealerSection
            title="Customer details"
            description="These details appear on your Cheshire Stables trade quote PDF."
          >
            <div className="rounded-xl border border-primary/15 bg-white p-4 shadow-sm sm:p-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="customer-name">Customer name</Label>
                  <Input
                    id="customer-name"
                    className="h-11"
                    value={customerName}
                    onChange={(e) => setCustomerName(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="customer-email">Customer email</Label>
                  <Input
                    id="customer-email"
                    type="email"
                    className="h-11"
                    value={customerEmail}
                    onChange={(e) => setCustomerEmail(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="customer-phone">Customer phone</Label>
                  <Input
                    id="customer-phone"
                    className="h-11"
                    value={customerPhone}
                    onChange={(e) => setCustomerPhone(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="customer-postcode">Customer / installation postcode</Label>
                  <Input
                    id="customer-postcode"
                    className="h-11"
                    value={customerPostcode}
                    onChange={(e) => setCustomerPostcode(e.target.value)}
                    placeholder="For delivery & install distance from factory"
                    autoCapitalize="characters"
                  />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="customer-address">Customer address</Label>
                  <Textarea
                    id="customer-address"
                    value={customerAddress}
                    onChange={(e) => setCustomerAddress(e.target.value)}
                    placeholder="For this PDF only (not saved as CRM customer)"
                  />
                </div>
              </div>
            </div>
          </DealerSection>

          {rows.length > 0 && (
            <DealerSection title="Fulfillment">
              <fieldset className="space-y-3 rounded-xl border border-primary/15 bg-white p-4 shadow-sm">
                <label className="flex min-h-11 items-center gap-3 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="fulfillment-dealer"
                    className="h-4 w-4"
                    checked={inclusion === 'collection'}
                    onChange={() => setInclusion('collection')}
                  />
                  Collection (customer collects from factory)
                </label>
                <p className="text-xs text-muted-foreground">
                  For delivery or delivery & installation lines, enter a postcode and use the delivery estimates section.
                </p>
              </fieldset>
            </DealerSection>
          )}

          {pcTrim && rows.length > 0 && inclusion !== 'collection' && (
            <DealerSection
              title="Delivery estimates"
              description="From factory to this postcode. Pick one option to add a single line to the quote."
            >
              <Card className="border-primary/15 shadow-sm">
                <CardHeader className="py-3">
                  <CardTitle className="text-base">Ex VAT estimates</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4 pt-0">
                  {estLoading && <p className="text-sm text-muted-foreground">Loading estimates…</p>}
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-primary/10 bg-primary/5 p-4 text-sm space-y-1">
                      <p className="font-semibold text-primary">Delivery only</p>
                      {estErrDelivery && (
                        <p className="text-destructive text-xs">{estErrDelivery}</p>
                      )}
                      {!estLoading && !estErrDelivery && estDeliveryOnly && (
                        <>
                          <p>
                            <span className="text-muted-foreground">Total: </span>
                            <span className="text-lg font-semibold">£{Number(estDeliveryOnly.cost_total).toFixed(2)}</span>
                          </p>
                          <p className="text-muted-foreground text-xs">
                            {estDeliveryOnly.distance_miles} mi one way · unload labour included in model
                            {(estDeliveryOnly.delivery_trips ?? 1) > 1 && (
                              <> · {estDeliveryOnly.delivery_trips} deliveries (max 3 boxes per trailer)</>
                            )}
                          </p>
                        </>
                      )}
                    </div>
                    <div className="rounded-xl border border-primary/10 bg-white p-4 text-sm space-y-1">
                      <p className="font-semibold text-primary">Delivery & installation</p>
                      {installHours <= 0 && (
                        <p className="text-muted-foreground text-xs">
                          Add products with installation hours to see this estimate.
                        </p>
                      )}
                      {installHours > 0 && estErrFull && (
                        <p className="text-destructive text-xs">{estErrFull}</p>
                      )}
                      {installHours > 0 && !estLoading && !estErrFull && estFull && (
                        <>
                          <p>
                            <span className="text-muted-foreground">Total: </span>
                            <span className="text-lg font-semibold">£{Number(estFull.cost_total).toFixed(2)}</span>
                          </p>
                          <p className="text-muted-foreground text-xs">
                            {estFull.fitting_days} fitting day(s) · {installHours.toFixed(1)} install hr (catalog)
                          </p>
                        </>
                      )}
                    </div>
                  </div>

                  <fieldset className="space-y-2">
                    <legend className="text-sm font-semibold">Include on quote</legend>
                    <div className="flex flex-col gap-2">
                      <label className="flex min-h-11 items-center gap-3 text-sm cursor-pointer rounded-lg border px-3">
                        <input
                          type="radio"
                          name="delivery-inclusion"
                          className="h-4 w-4"
                          checked={inclusion === 'none'}
                          onChange={() => setInclusion('none')}
                        />
                        None (products only)
                      </label>
                      <label
                        className={cn(
                          'flex min-h-11 items-center gap-3 text-sm rounded-lg border px-3',
                          canPickDeliveryOnly ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'
                        )}
                      >
                        <input
                          type="radio"
                          name="delivery-inclusion"
                          className="h-4 w-4"
                          checked={inclusion === 'delivery_only'}
                          disabled={!canPickDeliveryOnly}
                          onChange={() => setInclusion('delivery_only')}
                        />
                        Delivery only line
                      </label>
                      <label
                        className={cn(
                          'flex min-h-11 items-center gap-3 text-sm rounded-lg border px-3',
                          canPickFull ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'
                        )}
                      >
                        <input
                          type="radio"
                          name="delivery-inclusion"
                          className="h-4 w-4"
                          checked={inclusion === 'delivery_and_install'}
                          disabled={!canPickFull}
                          onChange={() => setInclusion('delivery_and_install')}
                        />
                        Delivery & installation line
                      </label>
                    </div>
                  </fieldset>
                </CardContent>
              </Card>
            </DealerSection>
          )}

          <DealerSection
            title="Products"
            description="Tap a Cheshire Stables product to add it to the quote."
          >
            <div className="grid gap-3 sm:grid-cols-2">
              {products.map((product) => {
                const selected = rows.some((r) => r.product_id === product.id);
                return (
                  <button
                    key={product.id}
                    type="button"
                    onClick={() => addProduct(product.id)}
                    disabled={selected}
                    className={cn(
                      'min-h-[4.5rem] rounded-xl border px-4 py-3 text-left shadow-sm transition-all',
                      selected
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-primary/20 bg-white hover:border-primary/40 hover:bg-primary/5'
                    )}
                  >
                    <span className="block text-base font-semibold">{product.name}</span>
                    <span className="mt-1 block text-sm text-muted-foreground">
                      £{Number(product.base_price).toFixed(2)}
                      {selected ? ' · Added' : ''}
                    </span>
                  </button>
                );
              })}
            </div>
          </DealerSection>

          <DealerSection title="Quote lines">
            <div className="space-y-3">
              {rows.map((row) => {
                const product = products.find((p) => p.id === row.product_id);
                if (!product) return null;
                const rowExtras = extrasByProductId[row.product_id] ?? [];
                const selectedExtras = rowExtras.filter((extra) =>
                  row.selected_extra_ids.includes(extra.id)
                );
                const extrasTotal = selectedExtras.reduce(
                  (extraSum, extra) => extraSum + Number(extra.base_price) * row.quantity,
                  0
                );
                return (
                  <div
                    key={row.product_id}
                    className="space-y-3 rounded-xl border border-primary/15 bg-white p-4 shadow-sm"
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                      <div className="flex-1 text-base font-semibold">{product.name}</div>
                      <div className="flex items-center gap-2">
                        <Input
                          type="number"
                          min={1}
                          className="h-11 w-24"
                          value={row.quantity}
                          onChange={(e) => updateQty(row.product_id, Math.max(1, Number(e.target.value)))}
                        />
                        <div className="min-w-[5.5rem] text-right text-base font-semibold">
                          £{(Number(product.base_price) * row.quantity + extrasTotal).toFixed(2)}
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          className="h-11 text-destructive"
                          onClick={() => removeRow(row.product_id)}
                        >
                          Remove
                        </Button>
                      </div>
                    </div>
                    {!!rowExtras.length && (
                      <div className="rounded-lg border border-dashed border-primary/25 px-3 py-2">
                        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-primary">
                          Optional extras
                        </p>
                        <div className="space-y-2">
                          {rowExtras.map((extra) => {
                            const checked = row.selected_extra_ids.includes(extra.id);
                            return (
                              <label
                                key={extra.id}
                                className="flex min-h-11 items-center justify-between gap-3 rounded-md px-1 text-sm"
                              >
                                <span className="flex items-center gap-3">
                                  <input
                                    type="checkbox"
                                    className="h-4 w-4"
                                    checked={checked}
                                    onChange={(e) => toggleExtra(row.product_id, extra.id, e.target.checked)}
                                  />
                                  {extra.name}
                                </span>
                                <span className="text-muted-foreground">
                                  +£{(Number(extra.base_price) * row.quantity).toFixed(2)}
                                </span>
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    )}
                    {!rowExtras.length && (
                      <p className="text-xs text-muted-foreground">No optional extras available for this product.</p>
                    )}
                  </div>
                );
              })}
              {!rows.length && (
                <p className="rounded-xl border border-dashed border-primary/30 bg-white px-4 py-6 text-center text-sm text-muted-foreground">
                  Select at least one product above.
                </p>
              )}
            </div>
          </DealerSection>

          <DealerSection title="Discounts">
            <div className="space-y-2 rounded-xl border border-primary/15 bg-white p-4 shadow-sm">
              {discountsLoading && (
                <p className="text-sm text-muted-foreground">Loading dealer discounts...</p>
              )}

              {!discountsLoading && !discountsConfigured && (
                <p className="text-sm text-muted-foreground">
                  No discounts configured for your dealer. Contact your admin.
                </p>
              )}

              {!discountsLoading && discountsConfigured && !availableDiscounts.length && (
                <p className="text-sm text-muted-foreground">No active allowed discounts available.</p>
              )}

              {!discountsLoading &&
                discountsConfigured &&
                availableDiscounts.map((discount) => {
                  const checked = selectedDiscountIds.includes(discount.id);
                  return (
                    <label
                      key={discount.id}
                      className="flex min-h-11 items-center justify-between gap-3 rounded-lg border px-3 text-sm"
                    >
                      <span className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          className="h-4 w-4"
                          checked={checked}
                          onChange={(e) =>
                            setSelectedDiscountIds((prev) =>
                              e.target.checked
                                ? Array.from(new Set([...prev, discount.id]))
                                : prev.filter((id) => id !== discount.id)
                            )
                          }
                        />
                        {discount.name}
                      </span>
                      <span className="text-muted-foreground">
                        {discount.discount_type === 'PERCENTAGE'
                          ? `${discount.discount_value}%`
                          : `£${discount.discount_value}`}{' '}
                        off {discount.scope === 'PRODUCT' ? 'building items' : 'entire quote'}
                      </span>
                    </label>
                  );
                })}
            </div>
          </DealerSection>

          <div className="sticky bottom-3 z-10 rounded-xl border border-primary/20 bg-white/95 p-4 shadow-lg backdrop-blur">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-base font-semibold">
                Estimated subtotal:{' '}
                <span className="text-xl text-primary">£{total.toFixed(2)}</span>
              </p>
              <Button type="submit" size="lg" className="h-12 w-full text-base sm:w-auto sm:min-w-[12rem]" disabled={submitBlocked}>
                {saving ? 'Creating...' : 'Create quote'}
              </Button>
            </div>
          </div>
        </form>
      </div>
    </DealerPageShell>
  );
}
