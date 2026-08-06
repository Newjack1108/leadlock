'use client';

import Link from 'next/link';
import { FileDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import DealerStatusBadge from '@/components/dealer/DealerStatusBadge';
import type { Quote } from '@/lib/types';
import { QuoteStatus } from '@/lib/types';
import { cn } from '@/lib/utils';

function formatDate(value?: string) {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export default function DealerQuoteCard({
  quote,
  onDownloadPdf,
  className,
}: {
  quote: Quote;
  onDownloadPdf?: (quoteId: number) => void;
  className?: string;
}) {
  const isDraft = quote.status === QuoteStatus.DRAFT;

  return (
    <article
      className={cn(
        'rounded-xl border border-primary/15 bg-white p-4 shadow-sm sm:p-5',
        className
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-primary">
            {quote.quote_number}
          </p>
          <h3 className="truncate text-lg font-semibold text-foreground">
            {quote.customer_name ?? 'Customer'}
          </h3>
          <p className="text-sm text-muted-foreground">Updated {formatDate(quote.updated_at)}</p>
        </div>
        <DealerStatusBadge status={quote.status} />
      </div>

      <p className="mt-4 text-2xl font-semibold tabular-nums text-foreground">
        £{Number(quote.total_amount).toFixed(2)}
        <span className="ml-1 text-sm font-medium text-muted-foreground">ex VAT</span>
      </p>

      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <Link href={`/dealer/quotes/${quote.id}`} className="sm:flex-1">
          <Button className="h-12 w-full text-base" size="lg">
            Open quote
          </Button>
        </Link>
        {isDraft ? (
          <Link href={`/dealer/quotes/${quote.id}/configure`} className="sm:flex-1">
            <Button variant="outline" className="h-12 w-full border-primary/30 text-base" size="lg">
              Configure layout
            </Button>
          </Link>
        ) : null}
        {onDownloadPdf ? (
          <Button
            type="button"
            variant="secondary"
            className="h-12 w-full text-base sm:w-auto sm:px-5"
            size="lg"
            onClick={() => onDownloadPdf(quote.id)}
          >
            <FileDown className="h-5 w-5" />
            PDF
          </Button>
        ) : null}
      </div>
    </article>
  );
}
