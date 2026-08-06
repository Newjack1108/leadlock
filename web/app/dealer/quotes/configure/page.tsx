'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import DealerBrandStrip from '@/components/dealer/DealerBrandStrip';
import DealerPageShell from '@/components/dealer/DealerPageShell';
import DealerSection from '@/components/dealer/DealerSection';
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
    <DealerPageShell narrow>
      <div className="space-y-6">
        <DealerBrandStrip subtitle="Configurator quote" />
        <DealerSection
          title="Customer details"
          description="Enter customer details, then design the Cheshire Stables layout. Add a postcode for delivery estimates."
        >
          <form
            onSubmit={handleSubmit}
            className="space-y-4 rounded-xl border border-primary/15 bg-white p-4 shadow-sm sm:p-5"
          >
            <div className="space-y-2">
              <Label htmlFor="customer_name">Customer name</Label>
              <Input
                id="customer_name"
                className="h-11"
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
                  className="h-11"
                  value={customerEmail}
                  onChange={(e) => setCustomerEmail(e.target.value)}
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="customer_phone">Phone</Label>
                <Input
                  id="customer_phone"
                  className="h-11"
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
                className="h-11"
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
            <div className="flex flex-col gap-2 pt-2 sm:flex-row">
              <Button type="submit" size="lg" className="h-12 w-full text-base sm:flex-1" disabled={saving}>
                {saving ? 'Starting…' : 'Open configurator'}
              </Button>
              <Link href="/dealer/quotes/new" className="sm:flex-1">
                <Button
                  type="button"
                  variant="outline"
                  size="lg"
                  className="h-12 w-full border-primary/30 text-base"
                  disabled={saving}
                >
                  Simple product quote instead
                </Button>
              </Link>
            </div>
          </form>
        </DealerSection>
      </div>
    </DealerPageShell>
  );
}
