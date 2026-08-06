'use client';

import { cn } from '@/lib/utils';
import { QuoteStatus } from '@/lib/types';

const STATUS_STYLES: Record<string, string> = {
  [QuoteStatus.DRAFT]: 'bg-amber-100 text-amber-900 border-amber-200',
  [QuoteStatus.SENT]: 'bg-sky-100 text-sky-900 border-sky-200',
  [QuoteStatus.VIEWED]: 'bg-violet-100 text-violet-900 border-violet-200',
  [QuoteStatus.ACCEPTED]: 'bg-emerald-100 text-emerald-900 border-emerald-200',
  [QuoteStatus.REJECTED]: 'bg-red-100 text-red-900 border-red-200',
  [QuoteStatus.EXPIRED]: 'bg-muted text-muted-foreground border-border',
};

export default function DealerStatusBadge({ status }: { status?: string | null }) {
  const label = (status || 'UNKNOWN').replace(/_/g, ' ');
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide',
        STATUS_STYLES[status || ''] || 'bg-muted text-muted-foreground border-border'
      )}
    >
      {label}
    </span>
  );
}
