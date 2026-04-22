'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { createDealerQuote, getDealerProducts } from '@/lib/api';
import type { Product } from '@/lib/types';
import { toast } from 'sonner';

type ProductRow = { product_id: number; quantity: number };

export default function NewDealerQuotePage() {
  const router = useRouter();
  const [products, setProducts] = useState<Product[]>([]);
  const [customerName, setCustomerName] = useState('');
  const [customerEmail, setCustomerEmail] = useState('');
  const [customerPhone, setCustomerPhone] = useState('');
  const [customerAddress, setCustomerAddress] = useState('');
  const [rows, setRows] = useState<ProductRow[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getDealerProducts()
      .then((data: Product[]) => setProducts(data))
      .catch((err: unknown) => {
        setProducts([]);
        const detail =
          err && typeof err === 'object' && 'response' in err
            ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : undefined;
        toast.error(
          typeof detail === 'string' ? detail : 'Could not load products. Check your account or try again.'
        );
      });
  }, []);

  const total = useMemo(() => {
    return rows.reduce((sum, row) => {
      const product = products.find((p) => p.id === row.product_id);
      if (!product) return sum;
      return sum + Number(product.base_price) * row.quantity;
    }, 0);
  }, [rows, products]);

  const addProduct = (id: number) => {
    if (rows.some((r) => r.product_id === id)) return;
    setRows((prev) => [...prev, { product_id: id, quantity: 1 }]);
  };

  const updateQty = (product_id: number, quantity: number) => {
    setRows((prev) => prev.map((r) => (r.product_id === product_id ? { ...r, quantity } : r)));
  };

  const removeRow = (product_id: number) => {
    setRows((prev) => prev.filter((r) => r.product_id !== product_id));
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerName.trim() || !rows.length) return;
    setSaving(true);
    try {
      const quote = await createDealerQuote({
        customer_name: customerName.trim(),
        customer_email: customerEmail.trim() || undefined,
        customer_phone: customerPhone.trim() || undefined,
        customer_address: customerAddress.trim() || undefined,
        product_items: rows.map((r) => ({ product_id: r.product_id, quantity: r.quantity })),
      });
      router.push(`/dealer/quotes/${quote.id}`);
    } finally {
      setSaving(false);
    }
  };

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
                <Input id="customer-name" value={customerName} onChange={(e) => setCustomerName(e.target.value)} required />
              </div>
              <div>
                <Label htmlFor="customer-email">Customer email</Label>
                <Input id="customer-email" type="email" value={customerEmail} onChange={(e) => setCustomerEmail(e.target.value)} />
              </div>
              <div>
                <Label htmlFor="customer-phone">Customer phone</Label>
                <Input id="customer-phone" value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} />
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
                return (
                  <div key={row.product_id} className="flex items-center gap-3 rounded border p-3">
                    <div className="flex-1 text-sm">{product.name}</div>
                    <Input
                      type="number"
                      min={1}
                      className="w-24"
                      value={row.quantity}
                      onChange={(e) => updateQty(row.product_id, Math.max(1, Number(e.target.value)))}
                    />
                    <div className="w-28 text-right text-sm">£{(Number(product.base_price) * row.quantity).toFixed(2)}</div>
                    <Button type="button" variant="ghost" onClick={() => removeRow(row.product_id)}>Remove</Button>
                  </div>
                );
              })}
              {!rows.length && <p className="text-sm text-muted-foreground">Select at least one product.</p>}
            </div>

            <div className="flex items-center justify-between border-t pt-4">
              <p className="text-sm font-medium">Estimated subtotal: £{total.toFixed(2)}</p>
              <Button type="submit" disabled={saving || !rows.length}>
                {saving ? 'Creating...' : 'Create quote'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
