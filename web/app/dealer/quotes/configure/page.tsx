'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { createDealerConfiguratorDraft, getApiErrorDetail } from '@/lib/api';
import { toast } from 'sonner';

export default function DealerConfiguratorStartPage() {
  const router = useRouter();
  const [customerName, setCustomerName] = useState('');
  const [customerEmail, setCustomerEmail] = useState('');
  const [customerPhone, setCustomerPhone] = useState('');
  const [customerAddress, setCustomerAddress] = useState('');
  const [customerPostcode, setCustomerPostcode] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = customerName.trim();
    if (!name) {
      toast.error('Customer name is required');
      return;
    }
    setSaving(true);
    try {
      const quote = await createDealerConfiguratorDraft({
        customer_name: name,
        customer_email: customerEmail.trim() || undefined,
        customer_phone: customerPhone.trim() || undefined,
        customer_address: customerAddress.trim() || undefined,
        customer_postcode: customerPostcode.trim() || undefined,
        notes: notes.trim() || undefined,
      });
      toast.success('Draft created — build the layout');
      router.push(`/dealer/quotes/${quote.id}/configure`);
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Could not start configurator quote');
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="container mx-auto max-w-2xl px-4 py-6 sm:px-6">
      <Card>
        <CardHeader>
          <CardTitle>Start configurator quote</CardTitle>
          <p className="text-sm text-muted-foreground">
            Enter customer details, then design the layout. Add a postcode if you need delivery estimates.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="customer_name">Customer name</Label>
              <Input
                id="customer_name"
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
                required
                disabled={saving}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="customer_email">Email</Label>
                <Input
                  id="customer_email"
                  type="email"
                  value={customerEmail}
                  onChange={(e) => setCustomerEmail(e.target.value)}
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="customer_phone">Phone</Label>
                <Input
                  id="customer_phone"
                  value={customerPhone}
                  onChange={(e) => setCustomerPhone(e.target.value)}
                  disabled={saving}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="customer_address">Address</Label>
              <Textarea
                id="customer_address"
                value={customerAddress}
                onChange={(e) => setCustomerAddress(e.target.value)}
                disabled={saving}
                rows={2}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="customer_postcode">Postcode</Label>
              <Input
                id="customer_postcode"
                value={customerPostcode}
                onChange={(e) => setCustomerPostcode(e.target.value)}
                disabled={saving}
                placeholder="Needed for delivery estimates"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="notes">Notes</Label>
              <Textarea
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                disabled={saving}
                rows={2}
              />
            </div>
            <div className="flex flex-wrap gap-3">
              <Button type="submit" disabled={saving}>
                {saving ? 'Starting…' : 'Open configurator'}
              </Button>
              <Link href="/dealer/quotes/new">
                <Button type="button" variant="outline" disabled={saving}>
                  Simple product quote instead
                </Button>
              </Link>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
