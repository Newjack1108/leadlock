'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getOrders } from '@/lib/api';
import { Order } from '@/lib/types';
import { toast } from 'sonner';
import { FileText, ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

function formatCurrency(amount: number, currency: string = 'GBP'): string {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

export default function OrdersPage() {
  const router = useRouter();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOrders();
  }, []);

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') fetchOrders();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, []);

  const fetchOrders = async () => {
    try {
      setLoading(true);
      const data = await getOrders();
      setOrders(data);
    } catch (error: any) {
      toast.error('Failed to load orders');
      if (error.response?.status === 401) router.push('/login');
    } finally {
      setLoading(false);
    }
  };

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
        <h1 className="text-3xl font-semibold mb-8">Orders</h1>

        {orders.length === 0 ? (
          <Card>
            <CardContent className="p-6">
              <div className="text-center text-muted-foreground py-12">
                <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No orders yet</p>
                <p className="text-sm mt-2">Orders are created when a quote is accepted.</p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-3 font-medium">Order #</th>
                    <th className="text-left p-3 font-medium">Customer</th>
                    <th className="text-left p-3 font-medium">Total</th>
                    <th className="text-left p-3 font-medium">Status</th>
                    <th className="text-left p-3 font-medium">Created</th>
                    <th className="text-right p-3 font-medium">Quote</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((order) => (
                    <tr
                      key={order.id}
                      className="border-b last:border-0 hover:bg-muted/30 transition-colors cursor-pointer"
                      onClick={() => router.push(`/orders/${order.id}`)}
                    >
                      <td className="p-3 font-semibold">{order.order_number}</td>
                      <td className="p-3 text-muted-foreground">
                        {order.customer_name ?? '—'}
                      </td>
                      <td className="p-3 font-semibold">
                        {formatCurrency(order.total_amount, order.currency)}
                      </td>
                      <td className="p-3">
                        <div className="flex flex-wrap gap-1">
                          {(order.deposit_paid ?? false) && (
                            <Badge variant="secondary" className="text-xs">Deposit paid</Badge>
                          )}
                          {(order.installation_booked ?? false) && (
                            <Badge variant="secondary" className="text-xs">Inst. booked</Badge>
                          )}
                          {(order.installation_completed ?? false) && (
                            <Badge variant="default" className="text-xs">Inst. done</Badge>
                          )}
                          {!(order.deposit_paid ?? false) && !(order.installation_booked ?? false) && !(order.installation_completed ?? false) && (
                            <span className="text-muted-foreground text-sm">—</span>
                          )}
                        </div>
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {new Date(order.created_at).toLocaleDateString()}
                      </td>
                      <td className="p-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => router.push(`/quotes/${order.quote_id}`)}
                          title="View quote"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </main>
    </div>
  );
}
