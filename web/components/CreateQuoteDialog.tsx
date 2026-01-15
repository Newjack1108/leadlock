'use client';

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { createQuote, getProducts } from '@/lib/api';
import { Customer, Product, QuoteItemCreate } from '@/lib/types';
import { toast } from 'sonner';
import { Plus, Trash2 } from 'lucide-react';

interface CreateQuoteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customer: Customer;
  onSuccess?: () => void;
}

export default function CreateQuoteDialog({
  open,
  onOpenChange,
  customer,
  onSuccess,
}: CreateQuoteDialogProps) {
  const [loading, setLoading] = useState(false);
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
    if (open) {
      fetchProducts();
      // Set default valid until to 30 days from now
      const date = new Date();
      date.setDate(date.getDate() + 30);
      setValidUntil(date.toISOString().split('T')[0]);
    }
  }, [open]);

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

      await createQuote(quoteData);
      toast.success('Quote created successfully');
      onOpenChange(false);
      
      // Reset form
      setItems([
        {
          description: '',
          quantity: 1,
          unit_price: 0,
          is_custom: false,
          sort_order: 0,
        },
      ]);
      const date = new Date();
      date.setDate(date.getDate() + 30);
      setValidUntil(date.toISOString().split('T')[0]);
      setTermsAndConditions('');
      setNotes('');
      setDepositAmount('');

      setTimeout(() => {
        try {
          onSuccess?.();
        } catch (error) {
          console.error('Error in onSuccess callback:', error);
        }
      }, 100);
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to create quote';
      toast.error(errorMessage);
      console.error('Quote creation error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create New Quote</DialogTitle>
          <DialogDescription>
            Create a new quote for {customer.name}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="space-y-6 py-4">
            {/* Quote Items */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <Label className="text-base font-semibold">Quote Items</Label>
                <Button type="button" variant="outline" size="sm" onClick={addItem}>
                  <Plus className="h-4 w-4 mr-2" />
                  Add Item
                </Button>
              </div>
              {items.map((item, index) => (
                <div key={index} className="p-4 border rounded-md space-y-3">
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
                  <div className="grid grid-cols-2 gap-4">
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
              <div className="p-3 bg-muted rounded-md space-y-2">
                <div className="flex justify-between items-center">
                  <span className="font-semibold">Subtotal:</span>
                  <span className="font-semibold">£{calculateSubtotal().toFixed(2)}</span>
                </div>
                <div className="flex justify-between items-center border-t pt-2">
                  <span className="font-semibold text-lg">Total:</span>
                  <span className="font-semibold text-lg">£{calculateTotal().toFixed(2)}</span>
                </div>
              </div>
            </div>

            {/* Quote Details */}
            <div className="space-y-4 border-t pt-4">
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
                  rows={4}
                />
              </div>
              <div className="space-y-2">
                <Label>Notes</Label>
                <Textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Internal notes (not visible to customer)..."
                  rows={3}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? 'Creating...' : 'Create Quote'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
