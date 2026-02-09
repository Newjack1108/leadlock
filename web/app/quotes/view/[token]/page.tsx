'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { getPublicQuoteView, downloadPublicQuotePdf } from '@/lib/api';
import type { PublicQuoteView } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const currencySymbol = (currency: string) => (currency === 'GBP' ? '£' : currency + ' ');
const formatAmount = (n: number, currency: string) =>
  `${currencySymbol(currency)}${Number(n).toFixed(2)}`;

export default function PublicQuoteViewPage() {
  const params = useParams();
  const token = params.token as string;
  const [data, setData] = useState<PublicQuoteView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    getPublicQuoteView(token)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err.response?.status === 404 ? 'Quote not found' : 'Failed to load quote');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen bg-muted/30 flex items-center justify-center p-6">
        <p className="text-muted-foreground">Loading your quote...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-muted/30 flex items-center justify-center p-6">
        <div className="text-center">
          <p className="text-destructive font-medium">{error || 'Quote not found'}</p>
          <p className="text-sm text-muted-foreground mt-2">The link may have expired or be invalid.</p>
        </div>
      </div>
    );
  }

  const handlePrint = () => window.print();
  const handleDownloadPdf = () => {
    if (!token) return;
    downloadPublicQuotePdf(token).catch(() => setError('Failed to download PDF'));
  };

  return (
    <div className="min-h-screen bg-muted/30 py-8 px-4 quote-view-page">
      <div className="max-w-2xl mx-auto">
        <div className="quote-view-actions flex gap-2 mb-4 print:hidden">
          <Button variant="outline" size="sm" onClick={handlePrint}>
            Print
          </Button>
          <Button variant="outline" size="sm" onClick={handleDownloadPdf}>
            Download PDF
          </Button>
        </div>
        <Card className="quote-view-print">
          <CardHeader className="pb-2">
            <CardTitle className="text-xl">Quote {data.quote_number}</CardTitle>
            <p className="text-muted-foreground text-sm">Prepared for {data.customer_name}</p>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Line items */}
            <div>
              <h3 className="font-medium mb-3">Items</h3>
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-2">Description</th>
                    <th className="py-2 pr-2 w-20 text-right">Qty</th>
                    <th className="py-2 pr-2 w-24 text-right">Unit price</th>
                    <th className="py-2 w-24 text-right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item, i) => (
                    <tr key={i} className="border-b">
                      <td className="py-2 pr-2">{item.description}</td>
                      <td className="py-2 pr-2 text-right">{Number(item.quantity)}</td>
                      <td className="py-2 pr-2 text-right">{formatAmount(item.unit_price, data.currency)}</td>
                      <td className="py-2 text-right">{formatAmount(item.final_line_total, data.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Totals */}
            <div className="border-t pt-4 space-y-1 text-sm">
              {data.discount_total > 0 && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Discount</span>
                  <span>-{formatAmount(data.discount_total, data.currency)}</span>
                </div>
              )}
              <div className="flex justify-between font-medium">
                <span>Total (ex VAT)</span>
                <span>{formatAmount(data.total_amount, data.currency)}</span>
              </div>
              {data.vat_amount != null && data.total_amount_inc_vat != null && (
                <>
                  <div className="flex justify-between text-muted-foreground">
                    <span>VAT @ 20%</span>
                    <span>{formatAmount(data.vat_amount, data.currency)}</span>
                  </div>
                  <div className="flex justify-between font-medium pt-1">
                    <span>Total (inc VAT)</span>
                    <span>{formatAmount(data.total_amount_inc_vat, data.currency)}</span>
                  </div>
                </>
              )}
              {data.deposit_amount > 0 && (
                <div className="flex justify-between text-muted-foreground pt-1">
                  <span>Deposit</span>
                  <span>{formatAmount(data.deposit_amount, data.currency)}</span>
                </div>
              )}
            </div>

            {data.valid_until && (
              <p className="text-sm text-muted-foreground">
                Valid until: {new Date(data.valid_until).toLocaleDateString()}
              </p>
            )}

            {data.terms_and_conditions && (
              <div className="pt-2 border-t">
                <h3 className="font-medium mb-2 text-sm">Terms & conditions</h3>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{data.terms_and_conditions}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
