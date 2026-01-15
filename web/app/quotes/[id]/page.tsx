'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import api, { getQuote, previewQuotePdf } from '@/lib/api';
import { Quote, QuoteItem, Customer } from '@/lib/types';
import { toast } from 'sonner';
import SendQuoteEmailDialog from '@/components/SendQuoteEmailDialog';
import { ArrowLeft, Mail, Eye } from 'lucide-react';

export default function QuoteDetailPage() {
  const router = useRouter();
  const params = useParams();
  const quoteId = parseInt(params.id as string);

  const [quote, setQuote] = useState<Quote | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [sendEmailDialogOpen, setSendEmailDialogOpen] = useState(false);

  useEffect(() => {
    if (quoteId) {
      fetchQuote();
    }
  }, [quoteId]);

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
              <Button
                variant="outline"
                onClick={async () => {
                  try {
                    await previewQuotePdf(quoteId);
                  } catch (error: any) {
                    toast.error(error.response?.data?.detail || error.message || 'Failed to preview PDF');
                  }
                }}
              >
                <Eye className="h-4 w-4 mr-2" />
                Preview PDF
              </Button>
              <Button
                onClick={() => setSendEmailDialogOpen(true)}
                disabled={!customer}
              >
                <Mail className="h-4 w-4 mr-2" />
                Send Quote
              </Button>
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
                          quote.items.map((item: QuoteItem) => (
                            <tr key={item.id} className="border-b">
                              <td className="py-2 px-3">{item.description}</td>
                              <td className="text-right py-2 px-3">{Number(item.quantity).toFixed(2)}</td>
                              <td className="text-right py-2 px-3">£{Number(item.unit_price).toFixed(2)}</td>
                              <td className="text-right py-2 px-3 font-medium">£{Number(item.line_total).toFixed(2)}</td>
                            </tr>
                          ))
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
                      <span className="text-muted-foreground">Subtotal:</span>
                      <span className="font-medium">£{Number(quote.subtotal).toFixed(2)}</span>
                    </div>
                    {Number(quote.discount_total) > 0 && (
                      <div className="flex justify-between text-destructive">
                        <span>Discount:</span>
                        <span>-£{Number(quote.discount_total).toFixed(2)}</span>
                      </div>
                    )}
                    <div className="flex justify-between text-lg font-semibold border-t pt-2">
                      <span>Total:</span>
                      <span>£{Number(quote.total_amount).toFixed(2)}</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Terms and Conditions */}
            {quote.terms_and_conditions && (
              <Card>
                <CardHeader>
                  <CardTitle>Terms and Conditions</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="whitespace-pre-wrap text-sm">
                    {quote.terms_and_conditions}
                  </div>
                </CardContent>
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
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Currency</div>
                  <div className="font-medium">{quote.currency}</div>
                </div>
                {quote.sent_at && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Sent At</div>
                    <div className="text-sm">
                      {new Date(quote.sent_at).toLocaleString()}
                    </div>
                  </div>
                )}
                {quote.viewed_at && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Viewed At</div>
                    <div className="text-sm">
                      {new Date(quote.viewed_at).toLocaleString()}
                    </div>
                  </div>
                )}
                {quote.accepted_at && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Accepted At</div>
                    <div className="text-sm">
                      {new Date(quote.accepted_at).toLocaleString()}
                    </div>
                  </div>
                )}
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Created</div>
                  <div className="text-sm">
                    {new Date(quote.created_at).toLocaleString()}
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
                        <div className="text-sm">{customer.phone}</div>
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
    </div>
  );
}
