'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { LayoutGrid, Package } from 'lucide-react';
import { toast } from 'sonner';
import DealerActionTile from '@/components/dealer/DealerActionTile';
import DealerBrandStrip from '@/components/dealer/DealerBrandStrip';
import DealerPageShell from '@/components/dealer/DealerPageShell';
import DealerQuoteCard from '@/components/dealer/DealerQuoteCard';
import DealerSection from '@/components/dealer/DealerSection';
import { downloadDealerQuotePdf, getDealerQuotes } from '@/lib/api';
import type { Quote } from '@/lib/types';

export default function DealerQuotesPage() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getDealerQuotes()
      .then((res) => setQuotes(res.items ?? []))
      .catch(() => setQuotes([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <DealerPageShell>
      <div className="space-y-6">
        <DealerBrandStrip subtitle="Your Cheshire Stables quotes" />

        <DealerSection
          title="Quotes"
          description="Open a quote to download the PDF or continue a draft layout."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <DealerActionTile
              href="/dealer/quotes/configure"
              title="Configurator quote"
              description="Design a layout for your customer."
              icon={LayoutGrid}
              variant="primary"
            />
            <DealerActionTile
              href="/dealer/quotes/new"
              title="Simple product quote"
              description="Quick quote from approved products."
              icon={Package}
              variant="secondary"
            />
          </div>
        </DealerSection>

        <div className="space-y-3">
          {loading ? (
            <div className="rounded-xl border bg-white px-4 py-8 text-center text-sm text-muted-foreground">
              Loading quotes…
            </div>
          ) : null}

          {!loading &&
            quotes.map((quote) => (
              <DealerQuoteCard
                key={quote.id}
                quote={quote}
                onDownloadPdf={(id) => {
                  void downloadDealerQuotePdf(id).catch((err: unknown) =>
                    toast.error(err instanceof Error ? err.message : 'Failed to download quote PDF')
                  );
                }}
              />
            ))}

          {!loading && !quotes.length ? (
            <div className="rounded-xl border border-dashed border-primary/30 bg-white px-4 py-10 text-center">
              <p className="mb-4 text-base text-muted-foreground">No quotes created yet.</p>
              <div className="mx-auto grid max-w-md gap-3">
                <Link
                  href="/dealer/quotes/configure"
                  className="inline-flex h-12 items-center justify-center rounded-md bg-primary px-4 text-base font-semibold text-primary-foreground"
                >
                  Start configurator quote
                </Link>
                <Link
                  href="/dealer/quotes/new"
                  className="inline-flex h-12 items-center justify-center rounded-md border border-primary/30 bg-white px-4 text-base font-semibold text-foreground"
                >
                  Start simple product quote
                </Link>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </DealerPageShell>
  );
}
