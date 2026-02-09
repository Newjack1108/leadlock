'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getQuote, updateDraftQuote, getProducts, getProduct, getCompanySettings, getDiscountTemplates, getDiscountRequestsForQuote, estimateDeliveryInstall } from '@/lib/api';
import api from '@/lib/api';
import { Customer, Product, QuoteItemCreate, DiscountTemplate, Quote, QuoteItem, QuoteDiscount, DiscountRequest, DiscountRequestStatus, QuoteTemperature, DeliveryInstallEstimateResponse } from '@/lib/types';
import Link from 'next/link';
import { toast } from 'sonner';
import { Plus, Trash2, ArrowLeft, X, ChevronDown, ChevronUp, Send } from 'lucide-react';
import RequestDiscountDialog from '@/components/RequestDiscountDialog';

const DEFAULT_TERMS_AND_CONDITIONS = `Key Terms Summary (For Quotations)

Orders & Payment
All orders are subject to our full Terms & Conditions.
A non-refundable deposit is required to secure your order.
Ownership of goods passes only once full payment has been received.

Prices
All prices are Ex VAT @ 20%. VAT will be added at 20% with a breakdown on the quote.
Delivery and installation are not included unless clearly specified.
Drawings and plans are for guidance only.

Delivery
Delivery dates are approximate and not guaranteed.
Delivery is to roadside only unless agreed otherwise.
Goods must be inspected on delivery; damage must be reported within 24 hours.

Installation
Installation (if included) requires a flat, level, suitable base and clear access.
Abortive visits due to poor access or base issues may incur charges.

Cancellations
Standard goods may be cancelled within 14 days of delivery.
Bespoke, made-to-order, or personalised items are non-refundable.
No cancellations once goods are assembled, altered, or used.

Planning & Use
Customers are responsible for planning permission where required.
Natural timber characteristics (knots, cracks, colour variation) are normal.

Warranty & Liability
12-month parts-only warranty.
We are not liable for third-party installation, access damage, weather events, or indirect losses.

Full Terms & Conditions available on request or on our website.
Statutory consumer rights are not affected.`;

function quoteItemsToFormItems(items: QuoteItem[]): QuoteItemCreate[] {
  const sorted = [...items].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
  const idToIndex: Record<number, number> = {};
  sorted.forEach((item, i) => {
    if (item.id != null) idToIndex[item.id] = i;
  });
  return sorted.map((item) => ({
    product_id: item.product_id ?? undefined,
    description: item.description,
    quantity: Number(item.quantity),
    unit_price: Number(item.unit_price),
    is_custom: item.is_custom ?? false,
    sort_order: item.sort_order ?? 0,
    parent_index: item.parent_quote_item_id != null ? idToIndex[item.parent_quote_item_id] : undefined,
  }));
}

function EditQuoteContent() {
  const router = useRouter();
  const params = useParams();
  const quoteId = params.id ? parseInt(params.id as string) : null;

  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [items, setItems] = useState<QuoteItemCreate[]>([]);
  const [validUntil, setValidUntil] = useState('');
  const [termsAndConditions, setTermsAndConditions] = useState('');
  const [notes, setNotes] = useState('');
  const [temperature, setTemperature] = useState<QuoteTemperature | ''>('');
  const [depositAmount, setDepositAmount] = useState<number | ''>('');
  const [companySettings, setCompanySettings] = useState<any>(null);
  const [availableDiscounts, setAvailableDiscounts] = useState<DiscountTemplate[]>([]);
  const [selectedDiscountIds, setSelectedDiscountIds] = useState<number[]>([]);
  const [discountRequests, setDiscountRequests] = useState<DiscountRequest[]>([]);
  const [requestDialogOpen, setRequestDialogOpen] = useState(false);
  const [productDetails, setProductDetails] = useState<Record<number, Product>>({});
  const [termsExpanded, setTermsExpanded] = useState(false);
  const [deliveryEstimate, setDeliveryEstimate] = useState<DeliveryInstallEstimateResponse | null>(null);
  const [deliveryEstimateLoading, setDeliveryEstimateLoading] = useState(false);
  const [deliveryEstimateError, setDeliveryEstimateError] = useState<string | null>(null);

  const fetchDiscountRequests = async () => {
    if (!quoteId) return;
    try {
      const list = await getDiscountRequestsForQuote(quoteId);
      setDiscountRequests(list);
    } catch {
      setDiscountRequests([]);
    }
  };

  useEffect(() => {
    if (quoteId) {
      fetchQuoteAndCustomer();
      fetchProducts();
      fetchCompanySettings();
      fetchDiscounts();
    } else {
      setPageLoading(false);
    }
  }, [quoteId]);

  const fetchQuoteAndCustomer = async () => {
    if (!quoteId) return;
    try {
      setPageLoading(true);
      const quoteData = await getQuote(quoteId);
      if (quoteData.status !== 'DRAFT') {
        toast.error('Only draft quotes can be edited');
        router.push(`/quotes/${quoteId}`);
        return;
      }
      setQuote(quoteData);
      setItems(
        quoteData.items?.length
          ? quoteItemsToFormItems(quoteData.items)
          : [{ description: '', quantity: 1, unit_price: 0, is_custom: false, sort_order: 0 }]
      );
      setValidUntil(
        quoteData.valid_until ? new Date(quoteData.valid_until).toISOString().split('T')[0] : ''
      );
      setTermsAndConditions(quoteData.terms_and_conditions ?? '');
      setNotes(quoteData.notes ?? '');
      setTemperature(quoteData.temperature ?? '');
      setDepositAmount(quoteData.deposit_amount ?? '');
      setSelectedDiscountIds(
        (quoteData.discounts ?? [])
          .filter((d: QuoteDiscount) => d.template_id != null)
          .map((d: QuoteDiscount) => d.template_id!)
          .filter((id: number | undefined): id is number => id != null) ?? []
      );
      if (quoteData.customer_id) {
        const customerResponse = await api.get(`/api/customers/${quoteData.customer_id}`);
        setCustomer(customerResponse.data);
      }
      await fetchDiscountRequests();
    } catch (error: any) {
      toast.error('Failed to load quote');
      if (error.response?.status === 401) router.push('/login');
      else if (error.response?.status === 404) router.push('/quotes');
    } finally {
      setPageLoading(false);
    }
  };

  const fetchProducts = async () => {
    try {
      const response = await getProducts();
      setProducts(response.filter((p: Product) => p.is_active && !p.is_extra));
    } catch (error) {
      console.error('Failed to load products');
    }
  };

  const fetchCompanySettings = async () => {
    try {
      const settings = await getCompanySettings();
      setCompanySettings(settings);
    } catch (error) {
      console.error('Failed to load company settings');
    }
  };

  const fetchDiscounts = async () => {
    try {
      const discounts = await getDiscountTemplates(true);
      setAvailableDiscounts(discounts);
    } catch (error) {
      console.error('Failed to load discounts');
    }
  };

  const addItem = () => {
    setItems([
      ...items,
      {
        description: '',
        quantity: 1,
        unit_price: 0,
        is_custom: false,
        sort_order: items.length,
      },
    ]);
  };

  const removeItem = (index: number) => {
    const newItems = items
      .filter((_, i) => i !== index)
      .map((item, i) => {
        let parent_index = item.parent_index;
        if (parent_index !== undefined && parent_index !== null) {
          if (parent_index === index) parent_index = undefined;
          else if (parent_index > index) parent_index = parent_index - 1;
        }
        return { ...item, sort_order: i, parent_index };
      });
    setItems(newItems);
  };

  const updateItem = async (index: number, field: keyof QuoteItemCreate, value: unknown) => {
    const newItems = [...items];
    if (field === 'product_id') {
      if (value === 'custom' || !value) {
        newItems[index] = {
          ...newItems[index],
          product_id: undefined,
          is_custom: true,
        };
        setItems(newItems);
        return;
      }
      const productId = parseInt(value as string, 10);
      const product = products.find((p) => p.id === productId);
      if (product) {
        newItems[index] = {
          ...newItems[index],
          product_id: product.id,
          description: product.name,
          unit_price: Number(product.base_price),
          is_custom: false,
        };
        setItems(newItems);
        try {
          const detailed = await getProduct(productId);
          setProductDetails((prev) => ({ ...prev, [productId]: detailed }));
        } catch {
          setProductDetails((prev) => ({ ...prev, [productId]: product }));
        }
        return;
      }
    }
    newItems[index] = { ...newItems[index], [field]: value };
    setItems(newItems);
  };

  const addOptionalExtra = (parentIndex: number, extra: Product) => {
    const parentItem = items[parentIndex];
    const parentProduct = getSelectedProduct(parentItem);
    const parentQty = Number(parentItem?.quantity) || 1;
    const boxesPerProduct = parentProduct?.boxes_per_product ?? 1;
    const quantity =
      extra.unit === 'Per Box' ? parentQty * boxesPerProduct : parentQty;

    const newItem: QuoteItemCreate = {
      product_id: extra.id,
      description: extra.name,
      quantity,
      unit_price: Number(extra.base_price),
      is_custom: false,
      sort_order: parentIndex + 1,
      parent_index: parentIndex,
    };
    const newItems = [...items];
    newItems.splice(parentIndex + 1, 0, newItem);
    setItems(newItems.map((it, i) => ({ ...it, sort_order: i })));
  };

  const getSelectedProduct = (item: QuoteItemCreate) => {
    if (!item.product_id) return null;
    return productDetails[item.product_id] ?? products.find((p) => p.id === item.product_id) ?? null;
  };

  const calculateTotalInstallationHours = (): number => {
    return items.reduce((total, item) => {
      if (item.parent_index != null) return total;
      const product = getSelectedProduct(item);
      if (!product?.installation_hours) return total;
      const qty = Number(item.quantity) || 0;
      return total + qty * product.installation_hours;
    }, 0);
  };

  useEffect(() => {
    const postcode = customer?.postcode?.trim();
    const installHours = calculateTotalInstallationHours();
    if (!postcode || installHours <= 0) {
      setDeliveryEstimate(null);
      setDeliveryEstimateError(null);
      return;
    }
    let cancelled = false;
    setDeliveryEstimateLoading(true);
    setDeliveryEstimateError(null);
    estimateDeliveryInstall(postcode, installHours)
      .then((data) => {
        if (!cancelled) {
          setDeliveryEstimate(data);
          setDeliveryEstimateError(null);
        }
      })
      .catch((err: any) => {
        if (!cancelled) {
          setDeliveryEstimate(null);
          const msg = err.response?.data?.detail || 'Failed to load delivery estimate';
          setDeliveryEstimateError(Array.isArray(msg) ? msg[0]?.msg ?? String(msg) : msg);
        }
      })
      .finally(() => {
        if (!cancelled) setDeliveryEstimateLoading(false);
      });
    return () => { cancelled = true; };
  }, [customer?.postcode, items, productDetails, products]);

  const calculateInstallCost = (product: Product) => {
    if (!product.installation_hours || !companySettings?.hourly_install_rate) return null;
    return product.installation_hours * companySettings.hourly_install_rate;
  };

  const calculateSubtotal = () => {
    return items.reduce(
      (sum, item) =>
        sum + (Number(item.quantity) || 0) * (Math.max(0, Number(item.unit_price)) || 0),
      0
    );
  };

  const calculateDefaultDeposit = () => calculateSubtotal() * 0.5;
  const getDepositAmount = () =>
    depositAmount === '' ? calculateDefaultDeposit() : Number(depositAmount);
  const getBalanceAmount = () => Math.max(0, calculateSubtotal() - getDepositAmount());

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quoteId || !quote) return;

    const validItems = items.filter(
      (item) => item.description.trim() && (item.quantity ?? 0) > 0 && (item.unit_price ?? 0) >= 0
    );
    if (validItems.length === 0) {
      toast.error('Please add at least one valid quote item');
      return;
    }

    const originalIndices = items
      .map((_, i) => i)
      .filter((i) => {
        const it = items[i];
        return it.description.trim() && (it.quantity ?? 0) > 0 && (it.unit_price ?? 0) >= 0;
      });

    setLoading(true);
    try {
      const payload = {
        items: validItems.map((item, index) => {
          const parentInItems = item.parent_index;
          const parentIndexInPayload =
            parentInItems != null ? originalIndices.indexOf(parentInItems) : -1;
          return {
            product_id: item.product_id ?? null,
            description: item.description,
            quantity: Number(item.quantity),
            unit_price: Number(item.unit_price),
            is_custom: item.is_custom !== undefined ? item.is_custom : (item.product_id == null),
            sort_order: index,
            parent_index: parentIndexInPayload >= 0 ? parentIndexInPayload : undefined,
          };
        }),
        discount_template_ids:
          selectedDiscountIds.length > 0 ? selectedDiscountIds : undefined,
      } as Parameters<typeof updateDraftQuote>[1];

      if (validUntil) payload.valid_until = new Date(validUntil).toISOString();
      if (termsAndConditions?.trim()) payload.terms_and_conditions = termsAndConditions.trim();
      if (notes?.trim()) payload.notes = notes.trim();
      if (temperature) payload.temperature = temperature;
      if (depositAmount !== '') payload.deposit_amount = Number(depositAmount);

      await updateDraftQuote(quoteId, payload);
      toast.success('Draft quote updated');
      router.push(`/quotes/${quoteId}`);
    } catch (error: any) {
      const msg =
        error.response?.data?.detail || error.message || 'Failed to update draft quote';
      toast.error(msg);
      console.error('Update draft error:', error);
    } finally {
      setLoading(false);
    }
  };

  if (pageLoading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  if (!quote || !quoteId) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Quote not found</div>
          <Button variant="outline" onClick={() => router.push('/quotes')}>
            Back to Quotes
          </Button>
        </div>
      </div>
    );
  }

  if (quote.status !== 'DRAFT') {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">
            Only draft quotes can be edited.
          </div>
          <Button variant="outline" onClick={() => router.push(`/quotes/${quoteId}`)}>
            View Quote
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <Button
            variant="ghost"
            onClick={() => router.push(`/quotes/${quoteId}`)}
            className="mb-4"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Quote
          </Button>
          <div>
            <h1 className="text-3xl font-semibold">Edit Draft: {quote.quote_number}</h1>
            {customer && (
              <p className="text-muted-foreground mt-1">For {customer.name}</p>
            )}
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Quote Items</CardTitle>
                    <p className="text-sm text-muted-foreground mt-1">
                      Add or change products and optional extras.
                    </p>
                  </div>
                  <Button type="button" variant="outline" size="sm" onClick={addItem}>
                    <Plus className="h-4 w-4 mr-2" />
                    Add Product
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {items.map((item, index) => (
                  <div
                    key={index}
                    className={`p-4 border rounded-md space-y-4 ${item.parent_index != null ? 'pl-6 border-l-4 border-l-muted-foreground/30 bg-muted/20' : ''}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">
                        {item.parent_index != null ? (
                          <>Optional extra</>
                        ) : (
                          <>Product {items.filter((_, i) => i <= index && items[i].parent_index == null).length}</>
                        )}
                      </span>
                      {items.length > 1 && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => removeItem(index)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      )}
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label>Product (Optional)</Label>
                        <Select
                          value={item.product_id?.toString() || 'custom'}
                          onValueChange={(value) =>
                            updateItem(index, 'product_id', value === 'custom' ? undefined : value)
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select product or enter custom" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="custom">Custom Item</SelectItem>
                            {[...products]
                              .sort((a, b) => a.name.localeCompare(b.name))
                              .map((product) => (
                                <SelectItem key={product.id} value={product.id.toString()}>
                                  {product.name} - £{Number(product.base_price).toFixed(2)}
                                </SelectItem>
                              ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <Label>Description <span className="text-destructive">*</span></Label>
                        <Input
                          value={item.description}
                          onChange={(e) => updateItem(index, 'description', e.target.value)}
                          placeholder="Item description"
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Quantity <span className="text-destructive">*</span></Label>
                        <Input
                          type="number"
                          step="0.01"
                          min="0"
                          value={item.quantity}
                          onChange={(e) =>
                            updateItem(index, 'quantity', parseFloat(e.target.value) || 0)
                          }
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Unit Price (£) <span className="text-destructive">*</span></Label>
                        <Input
                          type="number"
                          step="0.01"
                          min="0"
                          value={item.unit_price}
                          onChange={(e) =>
                            updateItem(index, 'unit_price', parseFloat(e.target.value) || 0)
                          }
                          required
                        />
                      </div>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      Line Total: £
                      {(
                        (Number(item.quantity) || 0) *
                        (Math.max(0, Number(item.unit_price)) || 0)
                      ).toFixed(2)}
                    </div>
                    {(() => {
                      const selectedProduct = getSelectedProduct(item);
                      if (!selectedProduct) return null;
                      const installCost = calculateInstallCost(selectedProduct);
                      const hasExtras =
                        selectedProduct.optional_extras &&
                        selectedProduct.optional_extras.length > 0;
                      const extrasLoaded = productDetails[item.product_id!] != null;
                      return (
                        <div className="mt-4 pt-4 border-t space-y-2">
                          {selectedProduct.installation_hours && (
                            <div className="text-sm">
                              <span className="text-muted-foreground">Installation Hours: </span>
                              <span className="font-medium">{selectedProduct.installation_hours} hours</span>
                            </div>
                          )}
                          {installCost !== null && (
                            <div className="text-sm">
                              <span className="text-muted-foreground">Installation Cost: </span>
                              <span className="font-medium">£{installCost.toFixed(2)}</span>
                            </div>
                          )}
                          <div className="mt-2">
                            <Label className="text-sm font-medium">Optional Extras</Label>
                            {!extrasLoaded ? (
                              <p className="text-sm text-muted-foreground mt-1">
                                Loading optional extras…
                              </p>
                            ) : hasExtras ? (
                              <div className="mt-2 space-y-2">
                                {[...(selectedProduct.optional_extras ?? [])]
                                  .sort((a, b) => a.name.localeCompare(b.name))
                                  .map((extra) => (
                                    <div
                                      key={extra.id}
                                      className="flex items-center justify-between p-2 border rounded-md hover:bg-muted/50"
                                    >
                                      <div className="flex-1">
                                        <p className="text-sm font-medium">{extra.name}</p>
                                        <p className="text-xs text-muted-foreground">
                                          £{Number(extra.base_price).toFixed(2)}
                                        </p>
                                      </div>
                                      <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        onClick={() => addOptionalExtra(index, extra)}
                                      >
                                        <Plus className="h-3 w-3 mr-1" />
                                        Add
                                      </Button>
                                    </div>
                                  ))}
                              </div>
                            ) : (
                              <p className="text-sm text-muted-foreground mt-1">
                                No optional extras for this product.
                              </p>
                            )}
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                ))}
                <div className="p-4 bg-muted rounded-md space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold">Subtotal (Ex VAT):</span>
                    <span className="font-semibold">£{calculateSubtotal().toFixed(2)}</span>
                  </div>
                  {selectedDiscountIds.length > 0 && (
                    <div className="flex justify-between items-center text-sm text-muted-foreground">
                      <span>Discounts will be recalculated on save</span>
                    </div>
                  )}
                  <div className="flex justify-between items-center border-t pt-2">
                    <span className="font-semibold">Total (Ex VAT):</span>
                    <span className="font-semibold">£{calculateSubtotal().toFixed(2)}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {(customer?.postcode?.trim() && calculateTotalInstallationHours() > 0) && (
              <Card>
                <CardHeader>
                  <CardTitle>Delivery & installation estimate</CardTitle>
                  <p className="text-sm text-muted-foreground font-normal">
                    From factory to customer postcode; 8hr fitting days, 2-man team. Not added to quote total.
                  </p>
                </CardHeader>
                <CardContent className="space-y-4">
                  {deliveryEstimateLoading && (
                    <p className="text-sm text-muted-foreground">Loading estimate…</p>
                  )}
                  {deliveryEstimateError && (
                    <div className="rounded-md border border-amber-200 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800 p-3 text-sm">
                      <p className="font-medium text-amber-800 dark:text-amber-200">Cannot calculate estimate</p>
                      <p className="text-amber-700 dark:text-amber-300 mt-1">{deliveryEstimateError}</p>
                      <Link href="/settings/company" className="text-amber-700 dark:text-amber-300 underline mt-2 inline-block">Configure factory postcode and installation & travel in Company settings</Link>
                    </div>
                  )}
                  {!deliveryEstimateLoading && !deliveryEstimateError && deliveryEstimate && (
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div><span className="text-muted-foreground">Distance (one way):</span> <span className="font-medium">{deliveryEstimate.distance_miles} miles</span></div>
                        <div><span className="text-muted-foreground">Travel time (one way):</span> <span className="font-medium">{deliveryEstimate.travel_time_hours_one_way} hrs</span></div>
                        <div><span className="text-muted-foreground">Fitting days (8hr):</span> <span className="font-medium">{deliveryEstimate.fitting_days}</span></div>
                        <div><span className="text-muted-foreground">Overnight stay:</span> <span className="font-medium">{deliveryEstimate.requires_overnight ? 'Yes' : 'No'}</span></div>
                        {deliveryEstimate.requires_overnight && (
                          <div><span className="text-muted-foreground">Nights away:</span> <span className="font-medium">{deliveryEstimate.nights_away}</span></div>
                        )}
                      </div>
                      <div className="border-t pt-3 space-y-1 text-sm">
                        {deliveryEstimate.cost_mileage != null && <div className="flex justify-between"><span className="text-muted-foreground">Mileage:</span><span>£{Number(deliveryEstimate.cost_mileage).toFixed(2)}</span></div>}
                        {deliveryEstimate.cost_labour != null && <div className="flex justify-between"><span className="text-muted-foreground">Labour:</span><span>£{Number(deliveryEstimate.cost_labour).toFixed(2)}</span></div>}
                        {deliveryEstimate.cost_hotel != null && <div className="flex justify-between"><span className="text-muted-foreground">Hotel:</span><span>£{Number(deliveryEstimate.cost_hotel).toFixed(2)}</span></div>}
                        {deliveryEstimate.cost_meals != null && <div className="flex justify-between"><span className="text-muted-foreground">Meals:</span><span>£{Number(deliveryEstimate.cost_meals).toFixed(2)}</span></div>}
                        <div className="flex justify-between font-semibold pt-1 border-t"><span>Total (Ex VAT):</span><span>£{Number(deliveryEstimate.cost_total).toFixed(2)}</span></div>
                      </div>
                      {deliveryEstimate.settings_incomplete && (
                        <p className="text-xs text-muted-foreground">Some costs could not be calculated. Complete Installation & travel in Company settings.</p>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle>Discounts & Giveaways</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Select Discounts</Label>
                  <Select
                    value=""
                    onValueChange={(value) => {
                      if (value && !selectedDiscountIds.includes(parseInt(value))) {
                        setSelectedDiscountIds([...selectedDiscountIds, parseInt(value)]);
                      }
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select a discount to apply..." />
                    </SelectTrigger>
                    <SelectContent>
                      {availableDiscounts
                        .filter((d) => !selectedDiscountIds.includes(d.id))
                        .map((discount) => (
                          <SelectItem key={discount.id} value={discount.id.toString()}>
                            {discount.name} -{' '}
                            {discount.discount_type === 'PERCENTAGE'
                              ? `${discount.discount_value}%`
                              : `£${discount.discount_value}`}{' '}
                            ({discount.scope === 'PRODUCT' ? 'Product (Building Only)' : 'Entire Quote'})
                            {discount.is_giveaway && ' 🎁'}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>
                {selectedDiscountIds.length > 0 && (
                  <div className="space-y-2">
                    <Label>Selected Discounts</Label>
                    <div className="space-y-2">
                      {selectedDiscountIds.map((discountId) => {
                        const discount = availableDiscounts.find((d) => d.id === discountId);
                        if (!discount) return null;
                        return (
                          <div
                            key={discountId}
                            className="flex items-center justify-between p-3 border rounded-md"
                          >
                            <div className="flex-1">
                              <p className="font-medium">
                                {discount.name}
                                {discount.is_giveaway && ' 🎁'}
                              </p>
                              <p className="text-sm text-muted-foreground">
                                {discount.discount_type === 'PERCENTAGE'
                                  ? `${discount.discount_value}%`
                                  : `£${discount.discount_value}`}{' '}
                                off {discount.scope === 'PRODUCT' ? 'building items only' : 'entire quote'}
                              </p>
                            </div>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                setSelectedDiscountIds(
                                  selectedDiscountIds.filter((id) => id !== discountId)
                                )
                              }
                            >
                              <X className="h-4 w-4" />
                            </Button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                <div className="border-t pt-4 mt-4 space-y-3">
                  <Label>Discount requests (require approval)</Label>
                  <p className="text-sm text-muted-foreground">
                    No suitable discount? Request one for manager approval.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setRequestDialogOpen(true)}
                  >
                    <Send className="h-4 w-4 mr-2" />
                    Request a discount
                  </Button>
                  {discountRequests.length > 0 && (
                    <div className="space-y-2">
                      {discountRequests.map((dr) => (
                        <div
                          key={dr.id}
                          className="flex items-center justify-between p-3 border rounded-md text-sm"
                        >
                          <div>
                            <span className="font-medium">
                              {dr.discount_type === 'PERCENTAGE'
                                ? `${dr.discount_value}%`
                                : `£${Number(dr.discount_value).toFixed(2)}`}{' '}
                              off {dr.scope === 'PRODUCT' ? 'building items only' : 'entire quote'}
                            </span>
                            {dr.reason && (
                              <p className="text-muted-foreground mt-1">{dr.reason}</p>
                            )}
                          </div>
                          <Badge
                            variant={
                              dr.status === DiscountRequestStatus.APPROVED
                                ? 'default'
                                : dr.status === DiscountRequestStatus.REJECTED
                                  ? 'destructive'
                                  : 'secondary'
                            }
                          >
                            {dr.status}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            <RequestDiscountDialog
              quoteId={quoteId!}
              open={requestDialogOpen}
              onOpenChange={setRequestDialogOpen}
              onSuccess={fetchDiscountRequests}
            />

            <Card>
              <CardHeader>
                <CardTitle>Quote Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Deposit Amount (£)</Label>
                  <Input
                    type="number"
                    step="0.01"
                    min="0"
                    value={depositAmount}
                    onChange={(e) => {
                      const value = e.target.value;
                      setDepositAmount(value === '' ? '' : parseFloat(value) || 0);
                    }}
                    placeholder={`Default: £${calculateDefaultDeposit().toFixed(2)} (50%)`}
                  />
                  <div className="text-sm text-muted-foreground">
                    {depositAmount === ''
                      ? `Default deposit: £${calculateDefaultDeposit().toFixed(2)} (50% of total)`
                      : `Balance: £${getBalanceAmount().toFixed(2)}`}
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>Deal temperature</Label>
                  <Select
                    value={temperature || ''}
                    onValueChange={(v) => setTemperature(v ? (v as QuoteTemperature) : '')}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select temperature" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={QuoteTemperature.HOT}>Hot</SelectItem>
                      <SelectItem value={QuoteTemperature.WARM}>Warm</SelectItem>
                      <SelectItem value={QuoteTemperature.COLD}>Cold</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Valid Until</Label>
                  <Input
                    type="date"
                    value={validUntil}
                    onChange={(e) => setValidUntil(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <button
                    type="button"
                    className="flex items-center justify-between w-full text-left font-medium leading-none hover:opacity-80"
                    onClick={() => setTermsExpanded((prev) => !prev)}
                  >
                    <Label className="cursor-pointer">Terms and Conditions</Label>
                    {termsExpanded ? (
                      <ChevronUp className="h-4 w-4 text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
                    )}
                  </button>
                  {termsExpanded && (
                    <Textarea
                      value={termsAndConditions}
                      onChange={(e) => setTermsAndConditions(e.target.value)}
                      placeholder="Enter terms and conditions..."
                      rows={6}
                    />
                  )}
                </div>
                <div className="space-y-2">
                  <Label>Notes</Label>
                  <Textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Internal notes (not visible to customer)..."
                    rows={4}
                  />
                </div>
              </CardContent>
            </Card>

            <div className="flex items-center justify-end gap-4 pb-6">
              <Button
                type="button"
                variant="outline"
                onClick={() => router.push(`/quotes/${quoteId}`)}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? 'Saving...' : 'Save Draft'}
              </Button>
            </div>
          </div>
        </form>
      </main>
    </div>
  );
}

export default function EditQuotePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-background">
          <Header />
          <div className="container mx-auto px-6 py-8">
            <div className="text-center py-12 text-muted-foreground">Loading...</div>
          </div>
        </div>
      }
    >
      <EditQuoteContent />
    </Suspense>
  );
}
