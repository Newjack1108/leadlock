'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import api, { getQuote, previewQuotePdf, getDiscountRequestsForQuote, getQuoteViewLink, acceptQuote } from '@/lib/api';
import { Quote, QuoteItem, Customer, QuoteDiscount, DiscountRequest, DiscountRequestStatus, QuoteTemperature } from '@/lib/types';
import SendQuoteEmailDialog from '@/components/SendQuoteEmailDialog';
import CallNotesDialog from '@/components/CallNotesDialog';
import { toast } from 'sonner';
import Link from 'next/link';
import { formatDateTime } from '@/lib/utils';
import { ArrowLeft, Mail, Eye, Tag, Pencil, ChevronDown, ChevronUp, Send, ExternalLink, CheckCircle, ShoppingBag } from 'lucide-react';
import RequestDiscountDialog from '@/components/RequestDiscountDialog';

const temperatureColors: Record<QuoteTemperature, string> = {
  HOT: 'bg-red-100 text-red-700',
  WARM: 'bg-amber-100 text-amber-700',
  COLD: 'bg-slate-100 text-slate-600',
};

export default function QuoteDetailPage() {
  const router = useRouter();
  const params = useParams();
  const quoteId = parseInt(params.id as string);

  const [quote, setQuote] = useState<Quote | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [sendEmailDialogOpen, setSendEmailDialogOpen] = useState(false);
  const [termsExpanded, setTermsExpanded] = useState(false);
  const [discountRequests, setDiscountRequests] = useState<DiscountRequest[]>([]);
  const [requestDialogOpen, setRequestDialogOpen] = useState(false);
  const [callNotesOpen, setCallNotesOpen] = useState(false);
  const [accepting, setAccepting] = useState(false);

  useEffect(() => {
    if (quoteId) {
      fetchQuote();
    }
  }, [quoteId]);

  const fetchDiscountRequests = async () => {
    try {
      const list = await getDiscountRequestsForQuote(quoteId);
      setDiscountRequests(list);
    } catch {
      setDiscountRequests([]);
    }
  };

  const fetchQuote = async () => {
    try {
      setLoading(true);
      const response = await getQuote(quoteId);
      setQuote(response);
      
      // Fetch customer if we have customer_id
      if (response.customer_id) {
        try {
          const customerResponse = await api.get(`/api/customers/${response.customer_id}`);
          setCustomer(customerResponse.data);
        } catch (error) {
          console.error('Failed to load customer');
        }
      }
      await fetchDiscountRequests();
    } catch (error: any) {
      toast.error('Failed to load quote');
      if (error.response?.status === 401) {
        router.push('/login');
      } else if (error.response?.status === 404) {
        router.push('/customers');
      }
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

  if (!quote) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Quote not found</div>
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
              <h1 className="text-3xl font-semibold">{quote.quote_number}</h1>
              {customer && (
                <p className="text-muted-foreground mt-1">
                  For {customer.name}
                </p>
              )}
            </div>
            <div className="flex items-center gap-3">
              <Badge className="text-sm">{quote.status}</Badge>
              {quote.temperature && (
                <Badge className={`text-sm ${temperatureColors[quote.temperature]}`}>
                  {quote.temperature}
                </Badge>
              )}
              {quote.status === 'DRAFT' && (
                <Button variant="outline" asChild>
                  <Link href={`/quotes/${quote.id}/edit`}>
                    <Pencil className="h-4 w-4 mr-2" />
                    Edit Draft
                  </Link>
                </Button>
              )}
              <Button
                variant="outline"
                onClick={async () => {
                  try {
                    await previewQuotePdf(quoteId);
                  } catch (error: any) {
                    toast.error(error.response?.data?.detail || error.message || 'Failed to download PDF');
                  }
                }}
              >
                <Eye className="h-4 w-4 mr-2" />
                Download PDF
              </Button>
              <Button
                onClick={() => setSendEmailDialogOpen(true)}
                disabled={!customer}
              >
                <Mail className="h-4 w-4 mr-2" />
                Send Quote
              </Button>
              {quote.status === 'SENT' && (
                <Button
                  variant="outline"
                  onClick={async () => {
                    try {
                      const { view_url } = await getQuoteViewLink(quoteId);
                      if (view_url) window.open(view_url, '_blank');
                      else toast.error('No view link available (set FRONTEND_BASE_URL and send the quote by email first).');
                    } catch {
                      toast.error('Failed to get view link');
                    }
                  }}
                >
                  <ExternalLink className="h-4 w-4 mr-2" />
                  Open customer view
                </Button>
              )}
              {['DRAFT', 'SENT', 'VIEWED'].includes(quote.status) && (
                <Button
                  onClick={async () => {
                    try {
                      setAccepting(true);
                      await acceptQuote(quoteId);
                      await fetchQuote();
                      toast.success('Quote accepted. Order created.');
                    } catch (error: any) {
                      toast.error(error.response?.data?.detail || 'Failed to accept quote');
                    } finally {
                      setAccepting(false);
                    }
                  }}
                  disabled={accepting}
                >
                  <CheckCircle className="h-4 w-4 mr-2" />
                  Accept quote
                </Button>
              )}
              {quote.status === 'ACCEPTED' && (
                <Button variant="outline" asChild>
                  <Link href={quote.order_id ? `/orders/${quote.order_id}` : '/orders'}>
                    <ShoppingBag className="h-4 w-4 mr-2" />
                    View order
                  </Link>
                </Button>
              )}
            </div>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Quote Items */}
            <Card>
              <CardHeader>
                <CardTitle>Quote Items</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
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
                        {quote.items && quote.items.length > 0 ? (
                          (() => {
                            const mainItems = quote.items
                              .filter((i: QuoteItem) => i.parent_quote_item_id == null)
                              .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
                            const getChildren = (parentId: number) =>
                              quote.items!
                                .filter((i: QuoteItem) => i.parent_quote_item_id === parentId)
                                .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
                            return mainItems.flatMap((item: QuoteItem) => {
                              const children = getChildren(item.id);
                              const hasDiscount = item.discount_amount > 0;
                              const rows: ReactNode[] = [
                                <tr key={item.id} className="border-b">
                                  <td className="py-2 px-3">
                                    {item.description}
                                    {hasDiscount && (
                                      <Badge variant="outline" className="ml-2 text-xs">
                                        Discounted
                                      </Badge>
                                    )}
                                  </td>
                                  <td className="text-right py-2 px-3">{Number(item.quantity).toFixed(2)}</td>
                                  <td className="text-right py-2 px-3">£{Number(item.unit_price).toFixed(2)}</td>
                                  <td className="text-right py-2 px-3">
                                    {hasDiscount ? (
                                      <div>
                                        <div className="text-muted-foreground line-through text-sm">
                                          £{Number(item.line_total).toFixed(2)}
                                        </div>
                                        <div className="font-medium text-destructive">
                                          £{Number(item.final_line_total).toFixed(2)}
                                        </div>
                                      </div>
                                    ) : (
                                      <span className="font-medium">£{Number(item.line_total).toFixed(2)}</span>
                                    )}
                                  </td>
                                </tr>,
                              ];
                              children.forEach((child: QuoteItem) => {
                                const childDiscount = child.discount_amount > 0;
                                rows.push(
                                  <tr key={child.id} className="border-b bg-muted/30">
                                    <td className="py-2 px-3 pl-8 text-muted-foreground">
                                      <span className="text-muted-foreground/80">— </span>
                                      {child.description}
                                      {childDiscount && (
                                        <Badge variant="outline" className="ml-2 text-xs">
                                          Discounted
                                        </Badge>
                                      )}
                                    </td>
                                    <td className="text-right py-2 px-3">{Number(child.quantity).toFixed(2)}</td>
                                    <td className="text-right py-2 px-3">£{Number(child.unit_price).toFixed(2)}</td>
                                    <td className="text-right py-2 px-3">
                                      {childDiscount ? (
                                        <div>
                                          <div className="text-muted-foreground line-through text-sm">
                                            £{Number(child.line_total).toFixed(2)}
                                          </div>
                                          <div className="font-medium text-destructive">
                                            £{Number(child.final_line_total).toFixed(2)}
                                          </div>
                                        </div>
                                      ) : (
                                        <span className="font-medium">£{Number(child.line_total).toFixed(2)}</span>
                                      )}
                                    </td>
                                  </tr>
                                );
                              });
                              return rows;
                            });
                          })()
                        ) : (
                          <tr>
                            <td colSpan={4} className="text-center py-4 text-muted-foreground">
                              No items in this quote
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                  
                  <div className="border-t pt-4 space-y-2">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Subtotal (Ex VAT):</span>
                      <span className="font-medium">£{Number(quote.subtotal).toFixed(2)}</span>
                    </div>
                    {Number(quote.discount_total) > 0 && (
                      <div className="flex justify-between text-destructive">
                        <span>Total Discount:</span>
                        <span>-£{Number(quote.discount_total).toFixed(2)}</span>
                      </div>
                    )}
                    <div className="flex justify-between font-semibold border-t pt-2">
                      <span>Total (Ex VAT):</span>
                      <span>£{Number(quote.total_amount).toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">VAT @ 20%:</span>
                      <span className="font-medium">£{Number(quote.vat_amount ?? Number(quote.total_amount) * 0.2).toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-lg font-semibold border-t pt-2">
                      <span>Total (inc VAT):</span>
                      <span>£{Number(quote.total_amount_inc_vat ?? Number(quote.total_amount) * 1.2).toFixed(2)}</span>
                    </div>
                    {Number(quote.deposit_amount) > 0 && (
                      <>
                        <div className="flex justify-between border-t pt-2">
                          <span className="font-medium">Deposit (on order, Ex VAT):</span>
                          <span className="font-medium">£{Number(quote.deposit_amount).toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="font-medium">Balance (Ex VAT):</span>
                          <span className="font-medium">£{Number(quote.balance_amount).toFixed(2)}</span>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Applied Discounts */}
            {quote.discounts && quote.discounts.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Applied Discounts</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {quote.discounts.map((discount: QuoteDiscount) => (
                      <div
                        key={discount.id}
                        className="flex items-start justify-between p-3 border rounded-md"
                      >
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <Tag className="h-4 w-4 text-muted-foreground" />
                            <p className="font-medium">{discount.description}</p>
                            {discount.scope === 'PRODUCT' && (
                              <Badge variant="outline" className="text-xs">
                                Building Only
                              </Badge>
                            )}
                            {discount.scope === 'QUOTE' && (
                              <Badge variant="outline" className="text-xs">
                                Entire Quote
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">
                            {discount.discount_type === 'PERCENTAGE'
                              ? `${discount.discount_value}%`
                              : `£${Number(discount.discount_value).toFixed(2)}`}{' '}
                            discount
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="font-semibold text-destructive">
                            -£{Number(discount.discount_amount).toFixed(2)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Discount requests */}
            <Card>
              <CardHeader>
                <CardTitle>Discount requests</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {quote.status === 'DRAFT' && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setRequestDialogOpen(true)}
                  >
                    <Send className="h-4 w-4 mr-2" />
                    Request a discount (requires approval)
                  </Button>
                )}
                {discountRequests.length > 0 ? (
                  <div className="space-y-2">
                    {discountRequests.map((dr) => (
                      <div
                        key={dr.id}
                        className="flex items-center justify-between p-3 border rounded-md text-sm"
                      >
                        <div>
                          <span className="font-medium">
                            {dr.discount_type === 'PERCENTAGE'
                              ? `${dr.discount_value}%`
                              : `£${Number(dr.discount_value).toFixed(2)}`}{' '}
                            off {dr.scope === 'PRODUCT' ? 'building items only' : 'entire quote'}
                          </span>
                          {dr.reason && (
                            <p className="text-muted-foreground mt-1">{dr.reason}</p>
                          )}
                          {dr.status === DiscountRequestStatus.REJECTED && dr.rejection_reason && (
                            <p className="text-destructive text-xs mt-1">{dr.rejection_reason}</p>
                          )}
                        </div>
                        <Badge
                          variant={
                            dr.status === DiscountRequestStatus.APPROVED
                              ? 'default'
                              : dr.status === DiscountRequestStatus.REJECTED
                                ? 'destructive'
                                : 'secondary'
                          }
                        >
                          {dr.status}
                        </Badge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No discount requests for this quote.</p>
                )}
              </CardContent>
            </Card>

            <RequestDiscountDialog
              quoteId={quoteId}
              open={requestDialogOpen}
              onOpenChange={setRequestDialogOpen}
              onSuccess={() => {
                fetchDiscountRequests();
                fetchQuote();
              }}
            />

            {/* Terms and Conditions */}
            {quote.terms_and_conditions && (
              <Card>
                <CardHeader
                  className="cursor-pointer hover:bg-muted/50 transition-colors rounded-t-lg"
                  onClick={() => setTermsExpanded((prev) => !prev)}
                >
                  <div className="flex items-center justify-between">
                    <CardTitle>Terms and Conditions</CardTitle>
                    {termsExpanded ? (
                      <ChevronUp className="h-5 w-5 text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronDown className="h-5 w-5 text-muted-foreground shrink-0" />
                    )}
                  </div>
                </CardHeader>
                {termsExpanded && (
                  <CardContent>
                    <div className="whitespace-pre-wrap text-sm">
                      {quote.terms_and_conditions}
                    </div>
                  </CardContent>
                )}
              </Card>
            )}

            {/* Notes (Internal) */}
            {quote.notes && (
              <Card>
                <CardHeader>
                  <CardTitle>Internal Notes</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="whitespace-pre-wrap text-sm text-muted-foreground">
                    {quote.notes}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Quote Details */}
            <Card>
              <CardHeader>
                <CardTitle>Quote Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Quote Number</div>
                  <div className="font-medium">{quote.quote_number}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Version</div>
                  <div className="font-medium">{quote.version}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Status</div>
                  <Badge>{quote.status}</Badge>
                </div>
                {quote.valid_until && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Valid Until</div>
                    <div className="font-medium">
                      {new Date(quote.valid_until).toLocaleDateString()}
                    </div>
                  </div>
                )}
                {quote.sent_at && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Sent At</div>
                    <div className="text-sm">
                      {formatDateTime(quote.sent_at)}
                    </div>
                  </div>
                )}
                {quote.viewed_at != null && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">First viewed at</div>
                    <div className="text-sm">
                      {formatDateTime(quote.viewed_at)}
                    </div>
                  </div>
                )}
                {quote.last_viewed_at != null && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Last viewed at</div>
                    <div className="text-sm">
                      {formatDateTime(quote.last_viewed_at)}
                    </div>
                  </div>
                )}
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Times viewed</div>
                  <div className="text-sm font-medium">{quote.total_open_count ?? 0}</div>
                </div>
                {quote.accepted_at && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Accepted At</div>
                    <div className="text-sm">
                      {formatDateTime(quote.accepted_at)}
                    </div>
                  </div>
                )}
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Created</div>
                  <div className="text-sm">
                    {formatDateTime(quote.created_at)}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Customer Info */}
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
                        <button
                          type="button"
                          className="text-sm text-primary hover:underline text-left"
                          onClick={() => setCallNotesOpen(true)}
                        >
                          {customer.phone}
                        </button>
                      </div>
                    )}
                    <Button
                      variant="outline"
                      className="w-full mt-4"
                      onClick={() => router.push(`/customers/${customer.id}`)}
                    >
                      View Customer Profile →
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </main>

      {customer && (
        <SendQuoteEmailDialog
          open={sendEmailDialogOpen}
          onOpenChange={setSendEmailDialogOpen}
          quoteId={quoteId}
          customer={customer}
          onSuccess={() => {
            fetchQuote();
          }}
        />
      )}

      {customer && customer.phone && (
        <CallNotesDialog
          open={callNotesOpen}
          onOpenChange={setCallNotesOpen}
          customerId={customer.id}
          customerName={customer.name}
          phone={customer.phone}
          onSuccess={() => fetchQuote()}
        />
      )}
    </div>
  );
}
