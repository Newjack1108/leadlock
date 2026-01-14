'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import api from '@/lib/api';
import { Customer } from '@/lib/types';
import { toast } from 'sonner';

export default function CustomersPage() {
  const router = useRouter();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    fetchCustomers();
  }, []);

  const fetchCustomers = async () => {
    try {
      const params = search ? { search } : {};
      const response = await api.get('/api/customers', { params });
      setCustomers(response.data);
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
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-3xl font-semibold">Customers</h1>
          <div className="w-64">
            <Input
              placeholder="Search customers..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {customers.length === 0 ? (
            <div className="col-span-full text-center py-12 text-muted-foreground">
              No customers found
            </div>
          ) : (
            customers.map((customer) => (
              <Card
                key={customer.id}
                className="cursor-pointer hover:shadow-lg transition-shadow"
                onClick={() => router.push(`/customers/${customer.id}`)}
              >
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <span>{customer.name}</span>
                    <span className="text-sm font-normal text-muted-foreground">
                      {customer.customer_number}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    {customer.email && (
                      <div>
                        <span className="text-muted-foreground">Email: </span>
                        {customer.email}
                      </div>
                    )}
                    {customer.phone && (
                      <div>
                        <span className="text-muted-foreground">Phone: </span>
                        {customer.phone}
                      </div>
                    )}
                    {customer.city && (
                      <div>
                        <span className="text-muted-foreground">Location: </span>
                        {customer.city}, {customer.county}
                      </div>
                    )}
                    <div className="text-xs text-muted-foreground mt-2">
                      Customer since: {new Date(customer.customer_since).toLocaleDateString()}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </main>
    </div>
  );
}
