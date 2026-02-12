'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import api, {
  getOrder,
  updateOrder,
  getOrderDepositInvoicePdf,
  getOrderPaidInFullInvoicePdf,
  fetchOrderDepositInvoiceBlob,
  fetchOrderPaidInFullInvoiceBlob,
  pushOrderToXero,
  sendAccessSheet,
  sendOrderToProduction,
} from '@/lib/api';
import { Order, OrderItem, Customer } from '@/lib/types';
import { toast } from 'sonner';
import Link from 'next/link';
import { formatDateTime } from '@/lib/utils';
import { ArrowLeft, ChevronDown, ExternalLink, CheckCircle, Circle, FileDown, Mail, Upload, Copy, Link2, Send } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import ComposeEmailDialog from '@/components/ComposeEmailDialog';

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
  const [sendingAccessSheet, setSendingAccessSheet] = useState(false);
  const [sendingToProduction, setSendingToProduction] = useState(false);
  const [composeEmailOpen, setComposeEmailOpen] = useState(false);
  const [composeEmailInitialAttachments, setComposeEmailInitialAttachments] = useState<File[]>([]);
  const [composeEmailInitialSubject, setComposeEmailInitialSubject] = useState<string>('');

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

  const handleAttachDepositInvoiceToEmail = async () => {
    if (!customer || !order) return;
    try {
      const blob = await fetchOrderDepositInvoiceBlob(orderId);
      const file = new File([blob], `Invoice_Deposit_${orderId}.pdf`, { type: 'application/pdf' });
      setComposeEmailInitialAttachments([file]);
      setComposeEmailInitialSubject(order.order_number ? `Invoice - Order #${order.order_number}` : '');
      setComposeEmailOpen(true);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to load invoice');
    }
  };

  const handleAttachPaidInFullInvoiceToEmail = async () => {
    if (!customer || !order) return;
    try {
      const blob = await fetchOrderPaidInFullInvoiceBlob(orderId);
      const file = new File([blob], `Invoice_PaidInFull_${orderId}.pdf`, { type: 'application/pdf' });
      setComposeEmailInitialAttachments([file]);
      setComposeEmailInitialSubject(order.order_number ? `Invoice - Order #${order.order_number}` : '');
      setComposeEmailOpen(true);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to load invoice');
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

  const handleSendAccessSheet = async () => {
    try {
      setSendingAccessSheet(true);
      const result = await sendAccessSheet(orderId);
      await fetchOrder();
      if (result.access_sheet_url) {
        await navigator.clipboard.writeText(result.access_sheet_url);
        toast.success('Access sheet link copied to clipboard');
      }
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to get access sheet link');
    } finally {
      setSendingAccessSheet(false);
    }
  };

  const handleSendToProduction = async () => {
    try {
      setSendingToProduction(true);
      await sendOrderToProduction(orderId);
      toast.success('Order sent to production');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to send to production');
    } finally {
      setSendingToProduction(false);
    }
  };

  const handleCopyAccessSheetLink = () => {
    const url = order?.access_sheet?.access_sheet_url;
    if (url) {
      navigator.clipboard.writeText(url).then(() => toast.success('Link copied to clipboard'));
    }
  };

  const accessSheetLabels: Record<string, string> = {
    access_4x4_trailer: 'Access suitable for 4x4 and trailer',
    access_4x4_notes: 'Notes',
    drive_near_build: 'Can drive near build position',
    drive_near_build_notes: 'Notes',
    permission_drive_land: 'Permission to drive on land',
    permission_drive_land_notes: 'Notes',
    balances_paid_before: 'Balances paid before delivery',
    balances_paid_before_notes: 'Notes',
    horses_contained: 'Horses contained during install',
    horses_contained_notes: 'Notes',
    site_level: 'Site level',
    site_level_notes: 'Notes',
    area_clear: 'Area clear of grass/shrubs',
    area_clear_notes: 'Notes',
    ground_type: 'Ground type',
    brickwork_if_concrete: 'Brickwork if concrete',
    brickwork_notes: 'Notes',
    electricity_available: 'Electricity onsite',
    electricity_notes: 'Notes',
    toilet_facilities: 'Toilet facilities',
    toilet_notes: 'Notes',
    customer_signature: 'Customer signature',
    notes: 'Additional notes',
  };

  const formatAnswerKey = (key: string) =>
    accessSheetLabels[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  const GROUND_TYPE_LABELS: Record<string, string> = {
    NEW_CONCRETE: 'New Concrete',
    OLD_CONCRETE: 'Old Concrete',
    GRASS_FIELD: 'Grass/Field',
    HARDCORE: 'Hardcore',
  };

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

  if (!order) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Order not found</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
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
                  {(['deposit_paid', 'paid_in_full'] as const).map((key) => (
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
                <div className="mt-4 pt-4 border-t">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleSendToProduction}
                    disabled={sendingToProduction}
                  >
                    <Send className="h-4 w-4 mr-1" />
                    {sendingToProduction ? 'Sending...' : 'Send to production'}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Access Sheet */}
            <Card>
              <CardHeader>
                <CardTitle>Access Sheet</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Customer fills in access details via link. Send link to customer to complete.
                </p>
              </CardHeader>
              <CardContent className="space-y-3">
                {!order.access_sheet ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleSendAccessSheet}
                    disabled={sendingAccessSheet}
                  >
                    <Link2 className="h-4 w-4 mr-1" />
                    {sendingAccessSheet ? 'Creating...' : 'Send Access Sheet'}
                  </Button>
                ) : order.access_sheet.completed ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <CheckCircle className="h-4 w-4 text-green-600" />
                      Completed{' '}
                      {order.access_sheet.completed_at &&
                        formatDateTime(order.access_sheet.completed_at)}
                    </div>
                    {order.access_sheet.answers && Object.keys(order.access_sheet.answers).length > 0 && (
                      <div className="border rounded-md divide-y text-sm">
                        {Object.entries(order.access_sheet.answers)
                          .filter(([, v]) => v != null && v !== '')
                          .map(([key, value]) => (
                            <div
                              key={key}
                              className="flex flex-col sm:flex-row sm:items-start gap-1 px-3 py-2"
                            >
                              <span className="font-medium text-muted-foreground min-w-[180px]">
                                {formatAnswerKey(key)}:
                              </span>
                              <span>
                                {key === 'ground_type'
                                  ? GROUND_TYPE_LABELS[value as string] || value
                                  : value}
                              </span>
                            </div>
                          ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">Link sent – awaiting customer completion</p>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCopyAccessSheetLink}
                      >
                        <Copy className="h-4 w-4 mr-1" />
                        Copy link
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        asChild
                      >
                        <a
                          href={order.access_sheet.access_sheet_url ?? '#'}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <ExternalLink className="h-4 w-4 mr-1" />
                          Open form
                        </a>
                      </Button>
                    </div>
                  </div>
                )}
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
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!order.invoice_number || (!order.deposit_paid && !order.paid_in_full)}
                      >
                        <FileDown className="h-4 w-4 mr-1" />
                        Deposit Invoice
                        <ChevronDown className="h-4 w-4 ml-1" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start">
                      <DropdownMenuItem onClick={handleDepositInvoice}>
                        <FileDown className="h-4 w-4 mr-2" />
                        Download
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={handleAttachDepositInvoiceToEmail}
                        disabled={!customer}
                      >
                        <Mail className="h-4 w-4 mr-2" />
                        Attach to new email
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!order.invoice_number || !order.paid_in_full}
                      >
                        <FileDown className="h-4 w-4 mr-1" />
                        Paid in Full Invoice
                        <ChevronDown className="h-4 w-4 ml-1" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start">
                      <DropdownMenuItem onClick={handlePaidInFullInvoice}>
                        <FileDown className="h-4 w-4 mr-2" />
                        Download
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={handleAttachPaidInFullInvoiceToEmail}
                        disabled={!customer}
                      >
                        <Mail className="h-4 w-4 mr-2" />
                        Attach to new email
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
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

      {customer && (
        <ComposeEmailDialog
          open={composeEmailOpen}
          onOpenChange={(open) => {
            setComposeEmailOpen(open);
            if (!open) {
              setComposeEmailInitialAttachments([]);
              setComposeEmailInitialSubject('');
            }
          }}
          customer={customer}
          initialAttachments={composeEmailInitialAttachments}
          initialSubject={composeEmailInitialSubject}
        />
      )}
    </div>
  );
}
