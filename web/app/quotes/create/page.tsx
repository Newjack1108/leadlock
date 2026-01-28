'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { createQuote, getProducts, getCompanySettings, getDiscountTemplates } from '@/lib/api';
import api from '@/lib/api';
import { Customer, Product, QuoteItemCreate, DiscountTemplate } from '@/lib/types';
import { toast } from 'sonner';
import { Plus, Trash2, ArrowLeft, X } from 'lucide-react';

// Default terms and conditions constant (fallback if not set in company settings)
const DEFAULT_TERMS_AND_CONDITIONS = `Key Terms Summary (For Quotations)

Orders & Payment
All orders are subject to our full Terms & Conditions.
A non-refundable deposit is required to secure your order.
Ownership of goods passes only once full payment has been received.

Prices
Prices are in GBP (£) and may exclude VAT unless stated.
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

function CreateQuoteContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const customerId = searchParams.get('customer_id') ? parseInt(searchParams.get('customer_id')!) : null;

  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [items, setItems] = useState<QuoteItemCreate[]>([
    {
      description: '',
      quantity: 1,
      unit_price: 0,
      is_custom: false,
      sort_order: 0,
    },
  ]);
  const [validUntil, setValidUntil] = useState('');
  const [termsAndConditions, setTermsAndConditions] = useState('');
  const [notes, setNotes] = useState('');
  const [depositAmount, setDepositAmount] = useState<number | ''>('');
  const [companySettings, setCompanySettings] = useState<any>(null);
  const [availableDiscounts, setAvailableDiscounts] = useState<DiscountTemplate[]>([]);
  const [selectedDiscountIds, setSelectedDiscountIds] = useState<number[]>([]);

  useEffect(() => {
    if (customerId) {
      fetchCustomer();
      fetchProducts();
      fetchDefaultTerms();
      fetchCompanySettings();
      fetchDiscounts();
      // Set default valid until to 30 days from now
      const date = new Date();
      date.setDate(date.getDate() + 30);
      setValidUntil(date.toISOString().split('T')[0]);
    } else {
      setPageLoading(false);
      toast.error('Customer ID is required');
      router.push('/customers');
    }
  }, [customerId]);

  const fetchCustomer = async () => {
    if (!customerId) return;
    try {
      const response = await api.get(`/api/customers/${customerId}`);
      setCustomer(response.data);
    } catch (error: any) {
      toast.error('Failed to load customer');
      if (error.response?.status === 401) {
        router.push('/login');
      } else if (error.response?.status === 404) {
        router.push('/customers');
      }
    } finally {
      setPageLoading(false);
    }
  };

  const fetchProducts = async () => {
    try {
      const response = await getProducts();
      setProducts(response.filter((p: Product) => p.is_active));
    } catch (error) {
      console.error('Failed to load products');
    }
  };

  const fetchDefaultTerms = async () => {
    try {
      const settings = await getCompanySettings();
      if (settings?.default_terms_and_conditions) {
        setTermsAndConditions(settings.default_terms_and_conditions);
      } else {
        setTermsAndConditions(DEFAULT_TERMS_AND_CONDITIONS);
      }
    } catch (error) {
      // If settings don't exist or error, use hardcoded default
      console.error('Failed to load company settings, using default terms');
      setTermsAndConditions(DEFAULT_TERMS_AND_CONDITIONS);
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
      const discounts = await getDiscountTemplates(true); // Only active discounts
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
    setItems(items.filter((_, i) => i !== index).map((item, i) => ({ ...item, sort_order: i })));
  };

  const updateItem = (index: number, field: keyof QuoteItemCreate, value: any) => {
    const newItems = [...items];
    if (field === 'product_id') {
      if (value === 'custom' || !value) {
        // Clear product selection - custom item
        newItems[index] = {
          ...newItems[index],
          product_id: undefined,
          is_custom: true,
        };
      } else {
        // Product selected
        const product = products.find((p) => p.id === parseInt(value));
        if (product) {
          newItems[index] = {
            ...newItems[index],
            product_id: product.id,
            description: product.name,
            unit_price: Number(product.base_price),
            is_custom: false,
          };
        }
      }
    } else {
      newItems[index] = { ...newItems[index], [field]: value };
    }
    setItems(newItems);
  };

  const addOptionalExtra = (productId: number, extra: Product) => {
    const newItem: QuoteItemCreate = {
      product_id: extra.id,
      description: extra.name,
      quantity: 1,
      unit_price: Number(extra.base_price),
      is_custom: false,
      sort_order: items.length,
    };
    setItems([...items, newItem]);
  };

  const getSelectedProduct = (item: QuoteItemCreate) => {
    if (item.product_id) {
      return products.find((p) => p.id === item.product_id);
    }
    return null;
  };

  const calculateInstallCost = (product: Product) => {
    if (!product.installation_hours || !companySettings?.hourly_install_rate) {
      return null;
    }
    return product.installation_hours * companySettings.hourly_install_rate;
  };

  const calculateSubtotal = () => {
    return items.reduce((sum, item) => sum + (item.quantity || 0) * (item.unit_price || 0), 0);
  };

  const calculateTotal = () => {
    // Note: Discounts are calculated on the backend
    // This is just the subtotal for preview
    return calculateSubtotal();
  };

  const calculateDefaultDeposit = () => {
    return calculateTotal() * 0.5;
  };

  const getDepositAmount = () => {
    if (depositAmount === '') {
      return calculateDefaultDeposit();
    }
    return Number(depositAmount);
  };

  const getBalanceAmount = () => {
    const total = calculateTotal();
    const deposit = getDepositAmount();
    return Math.max(0, total - deposit);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!customer) {
      toast.error('Customer information is missing');
      return;
    }

    // Validate items
    const validItems = items.filter(
      (item) => item.description.trim() && item.quantity > 0 && item.unit_price >= 0
    );

    if (validItems.length === 0) {
      toast.error('Please add at least one valid quote item');
      return;
    }

    setLoading(true);
    try {
      const quoteData: any = {
        customer_id: customer.id,
        items: validItems.map((item, index) => ({
          product_id: item.product_id || null,
          description: item.description,
          quantity: Number(item.quantity),
          unit_price: Number(item.unit_price),
          is_custom: item.is_custom !== undefined ? item.is_custom : (item.product_id === undefined || item.product_id === null),
          sort_order: index,
        })),
        discount_template_ids: selectedDiscountIds.length > 0 ? selectedDiscountIds : undefined,
      };

      // Only include optional fields if they have values
      if (validUntil) {
        quoteData.valid_until = new Date(validUntil).toISOString();
      }
      if (termsAndConditions && termsAndConditions.trim()) {
        quoteData.terms_and_conditions = termsAndConditions.trim();
      }
      if (notes && notes.trim()) {
        quoteData.notes = notes.trim();
      }
      // Include deposit_amount if explicitly set, otherwise let backend default to 50%
      if (depositAmount !== '') {
        quoteData.deposit_amount = Number(depositAmount);
      }

      const newQuote = await createQuote(quoteData);
      toast.success('Quote created successfully');
      
      // Redirect to the newly created quote detail page
      router.push(`/quotes/${newQuote.id}`);
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to create quote';
      toast.error(errorMessage);
      console.error('Quote creation error:', error);
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

  if (!customer) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Customer not found</div>
          <div className="text-center mt-4">
            <Button variant="outline" onClick={() => router.push('/customers')}>
              Back to Customers
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <Button variant="ghost" onClick={() => router.push(`/customers/${customer.id}`)} className="mb-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Customer
          </Button>
          <div>
            <h1 className="text-3xl font-semibold">Create New Quote</h1>
            <p className="text-muted-foreground mt-1">
              For {customer.name}
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="space-y-6">
            {/* Quote Items */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Quote Items</CardTitle>
                  <Button type="button" variant="outline" size="sm" onClick={addItem}>
                    <Plus className="h-4 w-4 mr-2" />
                    Add Item
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {items.map((item, index) => (
                  <div key={index} className="p-4 border rounded-md space-y-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">Item {index + 1}</span>
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
                          onValueChange={(value) => updateItem(index, 'product_id', value === 'custom' ? undefined : value)}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select product or enter custom" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="custom">Custom Item</SelectItem>
                            {products.map((product) => (
                              <SelectItem key={product.id} value={product.id.toString()}>
                                {product.name} - £{Number(product.base_price).toFixed(2)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-2">
                        <Label>
                          Description <span className="text-destructive">*</span>
                        </Label>
                        <Input
                          value={item.description}
                          onChange={(e) => updateItem(index, 'description', e.target.value)}
                          placeholder="Item description"
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>
                          Quantity <span className="text-destructive">*</span>
                        </Label>
                        <Input
                          type="number"
                          step="0.01"
                          min="0"
                          value={item.quantity}
                          onChange={(e) => updateItem(index, 'quantity', parseFloat(e.target.value) || 0)}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>
                          Unit Price (£) <span className="text-destructive">*</span>
                        </Label>
                        <Input
                          type="number"
                          step="0.01"
                          min="0"
                          value={item.unit_price}
                          onChange={(e) => updateItem(index, 'unit_price', parseFloat(e.target.value) || 0)}
                          required
                        />
                      </div>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      Line Total: £{((item.quantity || 0) * (item.unit_price || 0)).toFixed(2)}
                    </div>
                    {(() => {
                      const selectedProduct = getSelectedProduct(item);
                      if (!selectedProduct) return null;
                      
                      const installCost = calculateInstallCost(selectedProduct);
                      
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
                          {selectedProduct.optional_extras && selectedProduct.optional_extras.length > 0 && (
                            <div className="mt-2">
                              <Label className="text-sm font-medium">Optional Extras:</Label>
                              <div className="mt-2 space-y-2">
                                {selectedProduct.optional_extras.map((extra) => (
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
                                      onClick={() => addOptionalExtra(selectedProduct.id, extra)}
                                    >
                                      <Plus className="h-3 w-3 mr-1" />
                                      Add
                                    </Button>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                ))}
                <div className="p-4 bg-muted rounded-md space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold">Subtotal:</span>
                    <span className="font-semibold">£{calculateSubtotal().toFixed(2)}</span>
                  </div>
                  {selectedDiscountIds.length > 0 && (
                    <div className="flex justify-between items-center text-sm text-muted-foreground">
                      <span>Discounts will be calculated on submission</span>
                    </div>
                  )}
                  <div className="flex justify-between items-center border-t pt-2">
                    <span className="font-semibold text-lg">Total:</span>
                    <span className="font-semibold text-lg">£{calculateTotal().toFixed(2)}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Discounts Selection */}
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
                            {discount.name} - {discount.discount_type === 'PERCENTAGE' ? `${discount.discount_value}%` : `£${discount.discount_value}`} ({discount.scope === 'PRODUCT' ? 'Product' : 'Quote'})
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
                                off {discount.scope === 'PRODUCT' ? 'products' : 'entire quote'}
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
              </CardContent>
            </Card>

            {/* Quote Details */}
            <Card>
              <CardHeader>
                <CardTitle>Quote Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Deposit Amount (£)</Label>
                  <div className="space-y-2">
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
                      {depositAmount === '' ? (
                        <>Default deposit: £{calculateDefaultDeposit().toFixed(2)} (50% of total)</>
                      ) : (
                        <>Balance: £{getBalanceAmount().toFixed(2)}</>
                      )}
                    </div>
                  </div>
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
                  <Label>Terms and Conditions</Label>
                  <Textarea
                    value={termsAndConditions}
                    onChange={(e) => setTermsAndConditions(e.target.value)}
                    placeholder="Enter terms and conditions..."
                    rows={6}
                  />
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

            {/* Action Buttons */}
            <div className="flex items-center justify-end gap-4 pb-6">
              <Button
                type="button"
                variant="outline"
                onClick={() => router.push(`/customers/${customer.id}`)}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? 'Creating...' : 'Create Quote'}
              </Button>
            </div>
          </div>
        </form>
      </main>
    </div>
  );
}

export default function CreateQuotePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    }>
      <CreateQuoteContent />
    </Suspense>
  );
}
