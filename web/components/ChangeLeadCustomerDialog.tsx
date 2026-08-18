'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { getApiErrorDetail, getCustomers, reassignLeadCustomer } from '@/lib/api';
import { Customer, Lead } from '@/lib/types';
import { toast } from 'sonner';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  lead: Lead;
  onDone: (lead: Lead) => void;
};

export default function ChangeLeadCustomerDialog({ open, onOpenChange, lead, onDone }: Props) {
  const [search, setSearch] = useState('');
  const [results, setResults] = useState<Customer[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<Customer | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) {
      setSearch('');
      setResults([]);
      setSelected(null);
      setSaving(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const q = search.trim();
    if (q.length < 2) {
      setResults([]);
      setSearching(false);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const t = window.setTimeout(async () => {
      try {
        const data = await getCustomers({
          search: q,
          include_total: false,
          page: 1,
          page_size: 8,
        });
        if (cancelled) return;
        setResults((data.items ?? []).filter((c) => c.id !== lead.customer?.id));
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [search, open, lead.customer?.id]);

  const run = async (customerId?: number) => {
    setSaving(true);
    try {
      const updated = await reassignLeadCustomer(lead.id, customerId);
      onDone(updated);
      onOpenChange(false);
      toast.success(
        customerId
          ? `Lead linked to ${updated.customer?.customer_number ?? 'the selected customer'}`
          : `Created ${updated.customer?.customer_number ?? 'a new customer'} from this lead`
      );
    } catch (error: unknown) {
      const d = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      const message =
        typeof d === 'object' && d !== null && 'message' in d && typeof (d as { message: unknown }).message === 'string'
          ? (d as { message: string }).message
          : getApiErrorDetail(error);
      toast.error(message || 'Failed to change customer');
    } finally {
      setSaving(false);
    }
  };

  const current = lead.customer;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Change linked customer</DialogTitle>
          <DialogDescription>
            {current
              ? `This lead is linked to ${current.customer_number} (${current.name}). Quotes from this lead will move with it. The previous customer’s other records stay put.`
              : 'This lead has no customer yet. Create one from these details, or search for an existing record.'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2 overflow-y-auto flex-1 min-h-0">
          <div className="rounded-md border p-3 text-sm space-y-1">
            <div className="font-medium">Lead details</div>
            <div>{lead.name}</div>
            <div className="text-muted-foreground">{lead.email || 'No email'}</div>
            <div className="text-muted-foreground">{lead.phone || 'No phone'}</div>
          </div>
          {current && (
            <div className="rounded-md border p-3 text-sm space-y-1">
              <div className="font-medium">Currently linked</div>
              <div>{current.name}</div>
              <div className="text-muted-foreground">{current.email || 'No email'}</div>
              <div className="text-muted-foreground">{current.phone || 'No phone'}</div>
            </div>
          )}
          <Button
            className="w-full"
            onClick={() => run()}
            disabled={saving}
          >
            {saving && !selected ? 'Creating…' : 'Create new customer from this lead'}
          </Button>
          <div className="space-y-2">
            <Label htmlFor="reassign-customer-search">Or link to an existing customer</Label>
            <Input
              id="reassign-customer-search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setSelected(null);
              }}
              placeholder="Search name, email, phone, or number"
              disabled={saving}
            />
            {searching && <p className="text-xs text-muted-foreground">Searching…</p>}
            {results.length > 0 && (
              <div className="border rounded-md divide-y max-h-48 overflow-y-auto">
                {results.map((customer) => (
                  <button
                    key={customer.id}
                    type="button"
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-muted ${
                      selected?.id === customer.id ? 'bg-muted' : ''
                    }`}
                    onClick={() => setSelected(customer)}
                    disabled={saving}
                  >
                    <div className="font-medium">
                      {customer.name}{' '}
                      <span className="text-muted-foreground font-normal">
                        {customer.customer_number}
                      </span>
                    </div>
                    <div className="text-muted-foreground text-xs">
                      {[customer.email, customer.phone].filter(Boolean).join(' · ') || 'No contact details'}
                    </div>
                  </button>
                ))}
              </div>
            )}
            {selected && (
              <Button
                variant="outline"
                className="w-full"
                onClick={() => run(selected.id)}
                disabled={saving}
              >
                {saving ? 'Linking…' : `Link to ${selected.customer_number}`}
              </Button>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
