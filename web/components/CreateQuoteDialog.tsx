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
import { createQuote, getProducts, getProduct } from '@/lib/api';
import { Customer, Product, QuoteItemCreate } from '@/lib/types';
import { toast } from 'sonner';
import { Plus, Trash2, ChevronDown, ChevronUp } from 'lucide-react';

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
  const [productDetails, setProductDetails] = useState<Record<number, Product>>({});
  const [termsExpanded, setTermsExpanded] = useState(false);

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
      // Only main products in dropdown; extras are added via Optional Extras section per product
      setProducts(response.filter((p: Product) => p.is_active && !p.is_extra));
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

  const updateItem = async (index: number, field: keyof QuoteItemCreate, value: any) => {
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
      const productId = parseInt(value, 10);
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

  const calculateSubtotal = () => {
    return items.reduce(
      (sum, item) =>
        sum + (Number(item.quantity) || 0) * (Math.max(0, Number(item.unit_price)) || 0),
      0
    );
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

    const originalIndices = items
      .map((_, i) => i)
      .filter((i) => {
        const it = items[i];
        return it.description.trim() && (it.quantity ?? 0) > 0 && (it.unit_price ?? 0) >= 0;
      });

    setLoading(true);
    try {
      const quoteData: any = {
        customer_id: customer.id,
        items: validItems.map((item, index) => {
          const parentInItems = item.parent_index;
          const parentIndexInPayload =
            parentInItems != null ? originalIndices.indexOf(parentInItems) : -1;
          return {
            product_id: item.product_id ?? null,
            description: item.description,
            quantity: Number(item.quantity),
            unit_price: Number(item.unit_price),
            is_custom: item.is_custom !== undefined ? item.is_custom : (item.product_id === undefined || item.product_id === null),
            sort_order: index,
            parent_index: parentIndexInPayload >= 0 ? parentIndexInPayload : undefined,
          };
        }),
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
      setProductDetails({});
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
      <DialogContent className="max-w-7xl max-h-[90vh] overflow-y-auto">
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
                <div>
                  <Label className="text-base font-semibold">Quote Items</Label>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    Add a product, then add optional extras to it. You can add multiple products, each with their own extras.
                  </p>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={addItem}>
                  <Plus className="h-4 w-4 mr-2" />
                  Add Product
                </Button>
              </div>
              {items.map((item, index) => (
                <div
                  key={index}
                  className={`p-4 border rounded-md space-y-3 ${item.parent_index != null ? 'pl-6 border-l-4 border-l-muted-foreground/30 bg-muted/20' : ''}`}
                >
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
                  <div className="grid grid-cols-2 gap-6">
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
                          {[...products].sort((a, b) => a.name.localeCompare(b.name)).map((product) => (
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
                    Line Total: £
                    {(
                      (Number(item.quantity) || 0) *
                      (Math.max(0, Number(item.unit_price)) || 0)
                    ).toFixed(2)}
                  </div>
                  {(() => {
                    const selectedProduct = getSelectedProduct(item);
                    if (!selectedProduct) return null;
                    const hasExtras = selectedProduct.optional_extras && selectedProduct.optional_extras.length > 0;
                    const extrasLoaded = productDetails[item.product_id!] != null;
                    return (
                      <div className="mt-4 pt-4 border-t space-y-2">
                        <Label className="text-sm font-medium">Optional Extras</Label>
                        {!extrasLoaded ? (
                          <p className="text-sm text-muted-foreground mt-1">Loading optional extras…</p>
                        ) : hasExtras ? (
                          <div className="mt-2 space-y-2">
                            {[...selectedProduct.optional_extras!]
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
                          <p className="text-sm text-muted-foreground mt-1">No optional extras for this product.</p>
                        )}
                      </div>
                    );
                  })()}
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
                    rows={4}
                  />
                )}
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
