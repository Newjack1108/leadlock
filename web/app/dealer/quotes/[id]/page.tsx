'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { FileDown, LayoutGrid } from 'lucide-react';
import { toast } from 'sonner';
import DealerBrandStrip from '@/components/dealer/DealerBrandStrip';
import DealerPageShell from '@/components/dealer/DealerPageShell';
import DealerStatusBadge from '@/components/dealer/DealerStatusBadge';
import { Button } from '@/components/ui/button';
import { downloadDealerQuotePdf, getDealerQuote } from '@/lib/api';
import type { Quote } from '@/lib/types';
import { QuoteStatus } from '@/lib/types';

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
      <DealerPageShell>
        <div className="rounded-xl border bg-white px-4 py-8 text-center text-sm text-muted-foreground">
          Loading quote…
        </div>
      </DealerPageShell>
    );
  }

  const isDraft = quote.status === QuoteStatus.DRAFT;

  return (
    <DealerPageShell>
      <div className="space-y-6">
        <DealerBrandStrip subtitle="Quote details" />

        <section className="rounded-2xl border border-primary/20 bg-white p-5 shadow-sm sm:p-6">
          <div className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-semibold uppercase tracking-wide text-primary">
                  {quote.quote_number}
                </p>
                <h1 className="text-2xl font-semibold text-foreground sm:text-3xl">
                  {quote.customer_name || 'Customer'}
                </h1>
                {quote.dealer_customer_postcode?.trim() ? (
                  <p className="text-sm text-muted-foreground">
                    Postcode: {quote.dealer_customer_postcode}
                  </p>
                ) : null}
              </div>
              <DealerStatusBadge status={quote.status} />
            </div>

            <p className="text-3xl font-semibold tabular-nums text-foreground">
              £{Number(quote.total_amount).toFixed(2)}
              <span className="ml-2 text-base font-medium text-muted-foreground">ex VAT</span>
            </p>

            <div className="flex flex-col gap-2 sm:flex-row">
              {isDraft ? (
                <Link href={`/dealer/quotes/${quote.id}/configure`} className="sm:flex-1">
                  <Button size="lg" className="h-12 w-full text-base">
                    <LayoutGrid className="h-5 w-5" />
                    Configure layout
                  </Button>
                </Link>
              ) : null}
              <Button
                size="lg"
                variant={isDraft ? 'outline' : 'default'}
                className="h-12 w-full border-primary/30 text-base sm:flex-1"
                onClick={() => {
                  void downloadDealerQuotePdf(quote.id).catch((err: unknown) =>
                    toast.error(err instanceof Error ? err.message : 'Failed to download quote PDF')
                  );
                }}
              >
                <FileDown className="h-5 w-5" />
                Download PDF
              </Button>
            </div>
          </div>
        </section>

        <section className="space-y-3">
          <div className="border-l-4 border-primary pl-3">
            <h2 className="text-lg font-semibold">Line items</h2>
          </div>
          <div className="space-y-2">
            {quote.items.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-primary/10 bg-white px-4 py-3 shadow-sm"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-foreground">{item.description}</p>
                  <p className="text-sm text-muted-foreground">Qty {item.quantity}</p>
                </div>
                <p className="shrink-0 text-base font-semibold tabular-nums">
                  £{Number(item.final_line_total).toFixed(2)}
                </p>
              </div>
            ))}
          </div>
        </section>

        <Link href="/dealer/quotes">
          <Button variant="ghost" size="lg" className="h-11 w-full text-primary sm:w-auto">
            Back to quotes
          </Button>
        </Link>
      </div>
    </DealerPageShell>
  );
}
