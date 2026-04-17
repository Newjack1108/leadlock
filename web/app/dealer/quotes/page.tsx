'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getDealerQuotes } from '@/lib/api';
import type { Quote } from '@/lib/types';

export default function DealerQuotesPage() {
  const [quotes, setQuotes] = useState<Quote[]>([]);

  useEffect(() => {
    getDealerQuotes()
      .then((res) => setQuotes(res.items ?? []))
      .catch(() => setQuotes([]));
  }, []);

  return (
    <main className="container mx-auto px-4 py-6 sm:px-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Dealer Quotes</h1>
        <Link href="/dealer/quotes/new">
          <Button>Create quote</Button>
        </Link>
      </div>
      <div className="grid gap-3">
        {quotes.map((quote) => (
          <Card key={quote.id}>
            <CardHeader>
              <CardTitle className="text-base">{quote.quote_number}</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-between text-sm">
              <div>
                <p>{quote.customer_name ?? 'Customer'}</p>
                <p className="text-muted-foreground">Total: £{Number(quote.total_amount).toFixed(2)}</p>
              </div>
              <Link href={`/dealer/quotes/${quote.id}`}>
                <Button variant="outline" size="sm">Open</Button>
              </Link>
            </CardContent>
          </Card>
        ))}
        {!quotes.length && (
          <Card>
            <CardContent className="py-6 text-sm text-muted-foreground">
              No quotes created yet.
            </CardContent>
          </Card>
        )}
      </div>
    </main>
  );
}
