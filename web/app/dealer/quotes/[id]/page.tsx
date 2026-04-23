'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { downloadDealerQuotePdf, getDealerQuote } from '@/lib/api';
import type { Quote } from '@/lib/types';

export default function DealerQuoteDetailPage() {
  const params = useParams<{ id: string }>();
  const [quote, setQuote] = useState<Quote | null>(null);

  useEffect(() => {
    const id = Number(params.id);
    if (!id) return;
    getDealerQuote(id).then(setQuote).catch(() => setQuote(null));
  }, [params.id]);

  if (!quote) {
    return (
      <main className="container mx-auto px-4 py-6 sm:px-6">
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">Loading quote...</CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="container mx-auto px-4 py-6 sm:px-6">
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>{quote.quote_number}</CardTitle>
          <Button onClick={() => downloadDealerQuotePdf(quote.id)}>Download PDF</Button>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p><strong>Customer:</strong> {quote.customer_name}</p>
          {quote.dealer_customer_postcode?.trim() && (
            <p><strong>Postcode:</strong> {quote.dealer_customer_postcode}</p>
          )}
          <p><strong>Status:</strong> {quote.status}</p>
          <p><strong>Total:</strong> £{Number(quote.total_amount).toFixed(2)}</p>
          <div className="space-y-2">
            {quote.items.map((item) => (
              <div key={item.id} className="flex items-center justify-between rounded border p-2">
                <span>{item.description} x {item.quantity}</span>
                <span>£{Number(item.final_line_total).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
