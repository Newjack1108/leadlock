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
import { createQuote, getProducts } from '@/lib/api';
import api from '@/lib/api';
import { Customer, Product, QuoteItemCreate } from '@/lib/types';
import { toast } from 'sonner';
import { Plus, Trash2, ArrowLeft } from 'lucide-react';

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

  useEffect(() => {
    if (customerId) {
      fetchCustomer();
      fetchProducts();
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

  const calculateSubtotal = () => {
    return items.reduce((sum, item) => sum + (item.quantity || 0) * (item.unit_price || 0), 0);
  };

  const calculateTotal = () => {
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
                  </div>
                ))}
                <div className="p-4 bg-muted rounded-md space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold">Subtotal:</span>
                    <span className="font-semibold">£{calculateSubtotal().toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between items-center border-t pt-2">
                    <span className="font-semibold text-lg">Total:</span>
                    <span className="font-semibold text-lg">£{calculateTotal().toFixed(2)}</span>
                  </div>
                </div>
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
