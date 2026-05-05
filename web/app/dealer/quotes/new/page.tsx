'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  createDealerQuote,
  estimateDeliveryInstall,
  getApiErrorDetail,
  getDealerDiscountPolicy,
  getDealerProducts,
  getDiscountTemplates,
} from '@/lib/api';
import type {
  DealerDeliveryEstimateInclusion,
  DeliveryInstallEstimateResponse,
  DiscountTemplate,
  Product,
} from '@/lib/types';
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
  const [availableDiscounts, setAvailableDiscounts] = useState<DiscountTemplate[]>([]);
  const [selectedDiscountIds, setSelectedDiscountIds] = useState<number[]>([]);
  const [saving, setSaving] = useState(false);

  const [estDeliveryOnly, setEstDeliveryOnly] = useState<DeliveryInstallEstimateResponse | null>(null);
  const [estFull, setEstFull] = useState<DeliveryInstallEstimateResponse | null>(null);
  const [estLoading, setEstLoading] = useState(false);
  const [estErrDelivery, setEstErrDelivery] = useState<string | null>(null);
  const [estErrFull, setEstErrFull] = useState<string | null>(null);
  const [inclusion, setInclusion] = useState<DealerDeliveryEstimateInclusion>('none');

  useEffect(() => {
    getDealerProducts()
      .then((data: Product[]) => setProducts(data))
      .catch((err: unknown) => {
        setProducts([]);
        toast.error(getApiErrorDetail(err) || 'Could not load products. Check your account or try again.');
      });
  }, []);

  useEffect(() => {
    const loadDiscounts = async () => {
      try {
        const [policy, activeDiscounts] = await Promise.all([
          getDealerDiscountPolicy(),
          getDiscountTemplates(true),
        ]);
        const allowed = new Set(policy.allowed_discount_template_ids ?? []);
        setAvailableDiscounts(activeDiscounts.filter((discount: DiscountTemplate) => allowed.has(discount.id)));
      } catch (err: unknown) {
        // If policy is not configured for this dealer, just hide discount selection.
        setAvailableDiscounts([]);
        setSelectedDiscountIds([]);
        const detail = getApiErrorDetail(err);
        if (!detail.toLowerCase().includes('not configured')) {
          toast.error(detail || 'Could not load dealer discounts');
        }
      }
    };
    void loadDiscounts();
  }, []);

  const installHours = useMemo(() => {
    return rows.reduce((total, row) => {
      const product = products.find((p) => p.id === row.product_id);
      const hrs = product?.installation_hours;
      if (hrs == null || Number(hrs) <= 0) return total;
      return total + row.quantity * Number(hrs);
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
        estimateDeliveryInstall(pcTrim, 0, { deliveryOnly: true }),
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
  }, [pcTrim, rows, installHours]);

  const total = useMemo(() => {
    return rows.reduce((sum, row) => {
      const product = products.find((p) => p.id === row.product_id);
      if (!product) return sum;
      const extrasTotal = (product.optional_extras ?? [])
        .filter((extra) => row.selected_extra_ids.includes(extra.id))
        .reduce((extraSum, extra) => extraSum + Number(extra.base_price) * row.quantity, 0);
      return sum + Number(product.base_price) * row.quantity + extrasTotal;
    }, 0);
  }, [rows, products]);

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
    if (inclusion !== 'none' && !pcTrim) {
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
      (estLoading ||
        (inclusion === 'delivery_only' && !canPickDeliveryOnly) ||
        (inclusion === 'delivery_and_install' && !canPickFull)));

  return (
    <main className="container mx-auto px-4 py-6 sm:px-6">
      <Card>
        <CardHeader>
          <CardTitle>Create Dealer Quote</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="customer-name">Customer name</Label>
                <Input
                  id="customer-name"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  required
                />
              </div>
              <div>
                <Label htmlFor="customer-email">Customer email</Label>
                <Input
                  id="customer-email"
                  type="email"
                  value={customerEmail}
                  onChange={(e) => setCustomerEmail(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="customer-phone">Customer phone</Label>
                <Input
                  id="customer-phone"
                  value={customerPhone}
                  onChange={(e) => setCustomerPhone(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="customer-postcode">Customer / installation postcode</Label>
                <Input
                  id="customer-postcode"
                  value={customerPostcode}
                  onChange={(e) => setCustomerPostcode(e.target.value)}
                  placeholder="For delivery & install distance from factory"
                  autoCapitalize="characters"
                />
              </div>
              <div className="sm:col-span-2">
                <Label htmlFor="customer-address">Customer address</Label>
                <Textarea
                  id="customer-address"
                  value={customerAddress}
                  onChange={(e) => setCustomerAddress(e.target.value)}
                  placeholder="For this PDF only (not saved as CRM customer)"
                />
              </div>
            </div>

            {pcTrim && rows.length > 0 && (
              <Card className="border-muted">
                <CardHeader className="py-3">
                  <CardTitle className="text-base">Delivery estimates (Ex VAT)</CardTitle>
                  <p className="text-sm text-muted-foreground font-normal">
                    From factory to this postcode. Pick one option below to add a single line to the quote.
                  </p>
                </CardHeader>
                <CardContent className="space-y-4 pt-0">
                  {estLoading && <p className="text-sm text-muted-foreground">Loading estimates…</p>}
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-md border p-3 text-sm space-y-1">
                      <p className="font-medium">Delivery only</p>
                      {estErrDelivery && (
                        <p className="text-destructive text-xs">{estErrDelivery}</p>
                      )}
                      {!estLoading && !estErrDelivery && estDeliveryOnly && (
                        <>
                          <p>
                            <span className="text-muted-foreground">Total: </span>
                            <span className="font-semibold">£{Number(estDeliveryOnly.cost_total).toFixed(2)}</span>
                          </p>
                          <p className="text-muted-foreground text-xs">
                            {estDeliveryOnly.distance_miles} mi one way · unload labour included in model
                          </p>
                        </>
                      )}
                    </div>
                    <div className="rounded-md border p-3 text-sm space-y-1">
                      <p className="font-medium">Delivery & installation</p>
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
                            <span className="font-semibold">£{Number(estFull.cost_total).toFixed(2)}</span>
                          </p>
                          <p className="text-muted-foreground text-xs">
                            {estFull.fitting_days} fitting day(s) · {installHours.toFixed(1)} install hr (catalog)
                          </p>
                        </>
                      )}
                    </div>
                  </div>

                  <fieldset className="space-y-2">
                    <legend className="text-sm font-medium">Include on quote</legend>
                    <div className="flex flex-col gap-2">
                      <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="radio"
                          name="delivery-inclusion"
                          checked={inclusion === 'none'}
                          onChange={() => setInclusion('none')}
                        />
                        None (products only)
                      </label>
                      <label
                        className={`flex items-center gap-2 text-sm ${canPickDeliveryOnly ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}
                      >
                        <input
                          type="radio"
                          name="delivery-inclusion"
                          checked={inclusion === 'delivery_only'}
                          disabled={!canPickDeliveryOnly}
                          onChange={() => setInclusion('delivery_only')}
                        />
                        Delivery only line
                      </label>
                      <label
                        className={`flex items-center gap-2 text-sm ${canPickFull ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}
                      >
                        <input
                          type="radio"
                          name="delivery-inclusion"
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
            )}

            <div className="space-y-2">
              <Label>Add product</Label>
              <div className="flex flex-wrap gap-2">
                {products.map((product) => (
                  <Button key={product.id} type="button" variant="outline" onClick={() => addProduct(product.id)}>
                    {product.name}
                  </Button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              {rows.map((row) => {
                const product = products.find((p) => p.id === row.product_id);
                if (!product) return null;
                const selectedExtras = (product.optional_extras ?? []).filter((extra) =>
                  row.selected_extra_ids.includes(extra.id)
                );
                const extrasTotal = selectedExtras.reduce(
                  (extraSum, extra) => extraSum + Number(extra.base_price) * row.quantity,
                  0
                );
                return (
                  <div key={row.product_id} className="space-y-3 rounded border p-3">
                    <div className="flex items-center gap-3">
                      <div className="flex-1 text-sm">{product.name}</div>
                      <Input
                        type="number"
                        min={1}
                        className="w-24"
                        value={row.quantity}
                        onChange={(e) => updateQty(row.product_id, Math.max(1, Number(e.target.value)))}
                      />
                      <div className="w-28 text-right text-sm">
                        £{(Number(product.base_price) * row.quantity + extrasTotal).toFixed(2)}
                      </div>
                      <Button type="button" variant="ghost" onClick={() => removeRow(row.product_id)}>
                        Remove
                      </Button>
                    </div>
                    {!!product.optional_extras?.length && (
                      <div className="rounded-md border border-dashed px-3 py-2">
                        <p className="text-xs font-medium text-muted-foreground mb-2">Optional extras</p>
                        <div className="space-y-2">
                          {product.optional_extras.map((extra) => {
                            const checked = row.selected_extra_ids.includes(extra.id);
                            return (
                              <label key={extra.id} className="flex items-center justify-between gap-3 text-sm">
                                <span className="flex items-center gap-2">
                                  <input
                                    type="checkbox"
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
                  </div>
                );
              })}
              {!rows.length && <p className="text-sm text-muted-foreground">Select at least one product.</p>}
            </div>

            {!!availableDiscounts.length && (
              <div className="space-y-2">
                <Label>Available discounts</Label>
                <div className="space-y-2 rounded border p-3">
                  {availableDiscounts.map((discount) => {
                    const checked = selectedDiscountIds.includes(discount.id);
                    return (
                      <label key={discount.id} className="flex items-center justify-between gap-3 text-sm">
                        <span className="flex items-center gap-2">
                          <input
                            type="checkbox"
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
              </div>
            )}

            <div className="flex items-center justify-between border-t pt-4">
              <p className="text-sm font-medium">Estimated subtotal: £{total.toFixed(2)}</p>
              <Button type="submit" disabled={submitBlocked}>
                {saving ? 'Creating...' : 'Create quote'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
