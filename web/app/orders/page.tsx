'use client';

import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getOrders } from '@/lib/api';
import { Order } from '@/lib/types';
import { toast } from 'sonner';
import { FileText, ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

type OrderStatusFilter = 'new' | 'deposit_paid' | 'installation_booked' | 'installation_completed' | 'all';

function formatCurrency(amount: number, currency: string = 'GBP'): string {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

function orderMatchesStatusFilter(order: Order, filter: OrderStatusFilter): boolean {
  const dp = order.deposit_paid ?? false;
  const ib = order.installation_booked ?? false;
  const ic = order.installation_completed ?? false;
  switch (filter) {
    case 'new':
      return !dp && !ib && !ic;
    case 'deposit_paid':
      return dp;
    case 'installation_booked':
      return ib;
    case 'installation_completed':
      return ic;
    case 'all':
      return true;
    default:
      return true;
  }
}

export default function OrdersPage() {
  const router = useRouter();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<OrderStatusFilter>('new');
  const [searchQuery, setSearchQuery] = useState('');

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

  const filteredOrders = useMemo(() => {
    let result = orders.filter((o) => orderMatchesStatusFilter(o, statusFilter));
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter(
        (order) =>
          order.order_number?.toLowerCase().includes(q) ||
          order.customer_name?.toLowerCase().includes(q)
      );
    }
    return result;
  }, [orders, statusFilter, searchQuery]);

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <h1 className="text-3xl font-semibold mb-6">Orders</h1>

        {orders.length > 0 && (
          <div className="flex flex-col md:flex-row gap-4 mb-6">
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as OrderStatusFilter)}>
              <SelectTrigger className="w-full md:w-[200px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="new">New</SelectItem>
                <SelectItem value="deposit_paid">Deposit paid</SelectItem>
                <SelectItem value="installation_booked">Installation booked</SelectItem>
                <SelectItem value="installation_completed">Installation completed</SelectItem>
                <SelectItem value="all">All</SelectItem>
              </SelectContent>
            </Select>
            <Input
              placeholder="Search by order # or customer..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full md:w-[260px]"
            />
          </div>
        )}

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
        ) : filteredOrders.length === 0 ? (
          <Card>
            <CardContent className="p-6">
              <div className="text-center text-muted-foreground py-12">
                <p>No orders match your filters</p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-4"
                  onClick={() => {
                    setStatusFilter('all');
                    setSearchQuery('');
                  }}
                >
                  Clear filters
                </Button>
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
                  {filteredOrders.map((order) => (
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
                          {order.access_sheet && (
                            <Badge
                              variant={order.access_sheet.completed ? 'default' : 'outline'}
                              className="text-xs"
                              title={order.access_sheet.completed ? 'Access sheet completed' : 'Access sheet sent'}
                            >
                              {order.access_sheet.completed ? 'Access done' : 'Access sent'}
                            </Badge>
                          )}
                          {!(order.deposit_paid ?? false) && !(order.installation_booked ?? false) && !(order.installation_completed ?? false) && !order.access_sheet && (
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
