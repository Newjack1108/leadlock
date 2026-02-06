'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import api, { getUnreadCountsByCustomer } from '@/lib/api';
import { Customer } from '@/lib/types';
import { getTelUrl } from '@/lib/utils';
import { toast } from 'sonner';
import { Search, ChevronRight } from 'lucide-react';
import CallNotesDialog from '@/components/CallNotesDialog';

export default function CustomersPage() {
  const router = useRouter();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [unreadByCustomer, setUnreadByCustomer] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [callNotesOpen, setCallNotesOpen] = useState(false);
  const [callNotesCustomer, setCallNotesCustomer] = useState<{ id: number; name: string; phone: string } | null>(null);

  useEffect(() => {
    fetchCustomers();
  }, []);

  const fetchCustomers = async () => {
    try {
      const params = search ? { search } : {};
      const [customersRes, unreadRes] = await Promise.all([
        api.get('/api/customers', { params }),
        getUnreadCountsByCustomer().catch(() => []),
      ]);
      setCustomers(customersRes.data);
      setUnreadByCustomer(
        Object.fromEntries((unreadRes || []).map((d) => [d.customer_id, d.unread_count]))
      );
    } catch (error: any) {
      toast.error('Failed to load customers');
      if (error.response?.status === 401) {
        router.push('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      if (search !== undefined) {
        fetchCustomers();
      }
    }, 300);
    return () => clearTimeout(timeoutId);
  }, [search]);

  function locationText(c: Customer): string {
    if (c.city && c.county) return `${c.city}, ${c.county}`;
    if (c.city) return c.city;
    if (c.postcode) return c.postcode;
    return '—';
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <h1 className="text-3xl font-semibold">Customers</h1>
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by name, email, phone..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        <Card>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-3 font-medium">Customer #</th>
                  <th className="text-left p-3 font-medium">Name</th>
                  <th className="text-left p-3 font-medium">Email</th>
                  <th className="text-left p-3 font-medium">Phone</th>
                  <th className="text-left p-3 font-medium">Location</th>
                  <th className="text-left p-3 font-medium">Customer since</th>
                  <th className="text-center p-3 font-medium w-20">Unread</th>
                  <th className="text-right p-3 font-medium w-16" aria-hidden />
                </tr>
              </thead>
              <tbody>
                {customers.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-8 text-center text-muted-foreground">
                      No customers found
                    </td>
                  </tr>
                ) : (
                  customers.map((customer) => (
                    <tr
                      key={customer.id}
                      className="border-b last:border-0 hover:bg-muted/30 cursor-pointer transition-colors"
                      onClick={() => router.push(`/customers/${customer.id}`)}
                    >
                      <td className="p-3 text-muted-foreground font-mono text-sm">
                        {customer.customer_number}
                      </td>
                      <td className="p-3 font-semibold">{customer.name}</td>
                      <td className="p-3 text-muted-foreground">
                        {customer.email || '—'}
                      </td>
                      <td className="p-3 text-muted-foreground" onClick={(e) => e.stopPropagation()}>
                        {customer.phone ? (
                          <button
                            type="button"
                            className="text-primary hover:underline text-left"
                            onClick={(e) => {
                              e.preventDefault();
                              setCallNotesCustomer({ id: customer.id, name: customer.name, phone: customer.phone! });
                              setCallNotesOpen(true);
                            }}
                          >
                            {customer.phone}
                          </button>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {locationText(customer)}
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {new Date(customer.customer_since).toLocaleDateString()}
                      </td>
                      <td className="p-3 text-center">
                        {unreadByCustomer[customer.id] > 0 ? (
                          <span className="inline-flex min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold items-center justify-center">
                            {unreadByCustomer[customer.id] > 99 ? '99+' : unreadByCustomer[customer.id]}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="p-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => router.push(`/customers/${customer.id}`)}
                        >
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </main>

      {callNotesCustomer && (
        <CallNotesDialog
          open={callNotesOpen}
          onOpenChange={setCallNotesOpen}
          customerId={callNotesCustomer.id}
          customerName={callNotesCustomer.name}
          phone={callNotesCustomer.phone}
        />
      )}
    </div>
  );
}
