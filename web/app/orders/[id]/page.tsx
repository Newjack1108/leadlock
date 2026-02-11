'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import api, { getOrder, updateOrder, getOrderDepositInvoicePdf, getOrderPaidInFullInvoicePdf, pushOrderToXero } from '@/lib/api';
import { Order, OrderItem, Customer } from '@/lib/types';
import { toast } from 'sonner';
import Link from 'next/link';
import { formatDateTime } from '@/lib/utils';
import { ArrowLeft, ExternalLink, CheckCircle, Circle, FileDown, Upload } from 'lucide-react';

function formatCurrency(amount: number, currency: string = 'GBP'): string {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

type StatusKey = 'deposit_paid' | 'balance_paid' | 'paid_in_full' | 'installation_booked' | 'installation_completed';

export default function OrderDetailPage() {
  const router = useRouter();
  const params = useParams();
  const orderId = parseInt(params.id as string);

  const [order, setOrder] = useState<Order | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<StatusKey | null>(null);
  const [pushingXero, setPushingXero] = useState(false);

  useEffect(() => {
    if (orderId) fetchOrder();
  }, [orderId]);

  const fetchOrder = async () => {
    try {
      setLoading(true);
      const response = await getOrder(orderId);
      setOrder(response);
      if (response.customer_id) {
        try {
          const cust = await api.get(`/api/customers/${response.customer_id}`);
          setCustomer(cust.data);
        } catch {
          setCustomer(null);
        }
      }
    } catch (error: any) {
      toast.error('Failed to load order');
      if (error.response?.status === 401) router.push('/login');
      else if (error.response?.status === 404) router.push('/orders');
    } finally {
      setLoading(false);
    }
  };

  const toggleStatus = async (key: StatusKey) => {
    if (!order) return;
    const current = order[key] ?? false;
    const next = !current;
    try {
      setUpdating(key);
      const updated = await updateOrder(orderId, { [key]: next });
      setOrder(updated);
      toast.success(`${key.replace('_', ' ')} ${next ? 'marked' : 'cleared'}`);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || `Failed to update ${key}`);
    } finally {
      setUpdating(null);
    }
  };

  const handleDepositInvoice = async () => {
    try {
      await getOrderDepositInvoicePdf(orderId);
      toast.success('Deposit invoice downloaded');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to download invoice');
    }
  };

  const handlePaidInFullInvoice = async () => {
    try {
      await getOrderPaidInFullInvoicePdf(orderId);
      toast.success('Paid in full invoice downloaded');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to download invoice');
    }
  };

  const handlePushToXero = async () => {
    try {
      setPushingXero(true);
      const result = await pushOrderToXero(orderId);
      await fetchOrder();
      toast.success(result.message || 'Pushed to XERO successfully');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to push to XERO');
    } finally {
      setPushingXero(false);
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

  if (!order) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Order not found</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <Button variant="ghost" onClick={() => router.back()} className="mb-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-semibold">{order.order_number}</h1>
              {customer && (
                <p className="text-muted-foreground mt-1">For {customer.name}</p>
              )}
            </div>
            <Button variant="outline" asChild>
              <Link href={`/quotes/${order.quote_id}`}>
                <ExternalLink className="h-4 w-4 mr-2" />
                View quote
              </Link>
            </Button>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-6">
            {/* Order Items */}
            <Card>
              <CardHeader>
                <CardTitle>Order Items</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-2 px-3">Description</th>
                        <th className="text-right py-2 px-3">Quantity</th>
                        <th className="text-right py-2 px-3">Unit Price</th>
                        <th className="text-right py-2 px-3">Line Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {order.items && order.items.length > 0 ? (
                        order.items
                          .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
                          .map((item: OrderItem) => (
                            <tr key={item.id} className="border-b">
                              <td className="py-2 px-3">{item.description}</td>
                              <td className="text-right py-2 px-3">{Number(item.quantity).toFixed(2)}</td>
                              <td className="text-right py-2 px-3">{formatCurrency(item.unit_price, order.currency)}</td>
                              <td className="text-right py-2 px-3 font-medium">
                                {formatCurrency(item.final_line_total, order.currency)}
                              </td>
                            </tr>
                          ))
                      ) : (
                        <tr>
                          <td colSpan={4} className="text-center py-4 text-muted-foreground">
                            No items
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="border-t pt-4 mt-4 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Subtotal:</span>
                    <span className="font-medium">{formatCurrency(order.subtotal, order.currency)}</span>
                  </div>
                  {Number(order.discount_total) > 0 && (
                    <div className="flex justify-between text-destructive">
                      <span>Discount:</span>
                      <span>-{formatCurrency(order.discount_total, order.currency)}</span>
                    </div>
                  )}
                  <div className="flex justify-between font-semibold text-lg">
                    <span>Total:</span>
                    <span>{formatCurrency(order.total_amount, order.currency)}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Payment Status */}
            <Card>
              <CardHeader>
                <CardTitle>Payment Status</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Deposit</div>
                    <div className="font-medium">{formatCurrency(order.deposit_amount, order.currency)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Balance due</div>
                    <div className="font-medium">{formatCurrency(order.balance_amount, order.currency)}</div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 pt-2">
                  {(['deposit_paid', 'balance_paid', 'paid_in_full'] as const).map((key) => (
                    <Button
                      key={key}
                      variant={order[key] ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => toggleStatus(key)}
                      disabled={updating === key}
                    >
                      {order[key] ? (
                        <CheckCircle className="h-4 w-4 mr-1" />
                      ) : (
                        <Circle className="h-4 w-4 mr-1 opacity-50" />
                      )}
                      {key.replace(/_/g, ' ')}
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Installation Status */}
            <Card>
              <CardHeader>
                <CardTitle>Installation</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {(['installation_booked', 'installation_completed'] as const).map((key) => (
                    <Button
                      key={key}
                      variant={order[key] ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => toggleStatus(key)}
                      disabled={updating === key}
                    >
                      {order[key] ? (
                        <CheckCircle className="h-4 w-4 mr-1" />
                      ) : (
                        <Circle className="h-4 w-4 mr-1 opacity-50" />
                      )}
                      {key.replace('installation_', '')}
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Invoices */}
            <Card>
              <CardHeader>
                <CardTitle>Invoices</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  {order.invoice_number
                    ? `Invoice ${order.invoice_number}`
                    : 'Mark deposit or paid in full to generate an invoice.'}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleDepositInvoice}
                    disabled={!order.invoice_number || (!order.deposit_paid && !order.paid_in_full)}
                  >
                    <FileDown className="h-4 w-4 mr-1" />
                    Download Deposit Paid Invoice
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handlePaidInFullInvoice}
                    disabled={!order.invoice_number || !order.paid_in_full}
                  >
                    <FileDown className="h-4 w-4 mr-1" />
                    Download Paid in Full Invoice
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handlePushToXero}
                    disabled={!order.invoice_number || pushingXero}
                  >
                    <Upload className="h-4 w-4 mr-1" />
                    {order.xero_invoice_id ? 'In XERO' : 'Push to XERO'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Order Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Order number</div>
                  <div className="font-medium">{order.order_number}</div>
                </div>
                {order.invoice_number && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Invoice number</div>
                    <div className="font-medium">{order.invoice_number}</div>
                  </div>
                )}
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Created</div>
                  <div className="text-sm">{formatDateTime(order.created_at)}</div>
                </div>
              </CardContent>
            </Card>

            {customer && (
              <Card>
                <CardHeader>
                  <CardTitle>Customer</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Name</div>
                      <div className="font-medium">{customer.name}</div>
                    </div>
                    {customer.email && (
                      <div>
                        <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Email</div>
                        <div className="text-sm">{customer.email}</div>
                      </div>
                    )}
                    {customer.phone && (
                      <div>
                        <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Phone</div>
                        <div className="text-sm">{customer.phone}</div>
                      </div>
                    )}
                    <Button
                      variant="outline"
                      className="w-full mt-4"
                      onClick={() => router.push(`/customers/${customer.id}`)}
                    >
                      View Customer Profile
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
