'use client';

import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PrizeDrawEntry } from '@/lib/types';
import { approveReviewPrizeDrawEntry, rejectReviewPrizeDrawEntry } from '@/lib/api';
import { Copy, Gift, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import { useState } from 'react';

type PrizeDrawStaffPanelProps = {
  entry: PrizeDrawEntry | null | undefined;
  prizeDrawEnabled?: boolean;
  onUpdated?: () => void;
};

const statusVariant = (status?: string | null) => {
  if (status === 'APPROVED') return 'default';
  if (status === 'REJECTED') return 'destructive';
  if (status === 'PENDING') return 'secondary';
  return 'outline';
};

export default function PrizeDrawStaffPanel({
  entry,
  prizeDrawEnabled,
  onUpdated,
}: PrizeDrawStaffPanelProps) {
  const [busy, setBusy] = useState(false);

  if (!prizeDrawEnabled) return null;

  const copyLink = async () => {
    if (!entry?.prize_draw_url) return;
    try {
      await navigator.clipboard.writeText(entry.prize_draw_url);
      toast.success('Prize draw link copied');
    } catch {
      toast.error('Could not copy link');
    }
  };

  const handleApprove = async () => {
    if (!entry?.id) return;
    try {
      setBusy(true);
      await approveReviewPrizeDrawEntry(entry.id);
      toast.success('Prize draw entry approved');
      onUpdated?.();
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      toast.error(detail || 'Failed to approve entry');
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async () => {
    if (!entry?.id) return;
    const note = window.prompt('Optional note for rejection:') ?? undefined;
    try {
      setBusy(true);
      await rejectReviewPrizeDrawEntry(entry.id, note);
      toast.success('Prize draw entry rejected');
      onUpdated?.();
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      toast.error(detail || 'Failed to reject entry');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-md border bg-muted/30 p-3 space-y-3">
      <div className="flex items-center gap-2">
        <Gift className="h-4 w-4 text-teal-600" />
        <span className="text-sm font-medium">Monthly prize draw</span>
        {entry?.status ? (
          <Badge variant={statusVariant(entry.status)}>{entry.status}</Badge>
        ) : (
          <Badge variant="outline">No entry yet</Badge>
        )}
      </div>

      {entry?.platforms_claimed?.length ? (
        <p className="text-xs text-muted-foreground">
          Platforms claimed: {entry.platforms_claimed.join(', ')}
        </p>
      ) : null}

      {entry?.rejection_note ? (
        <p className="text-xs text-destructive">Rejected: {entry.rejection_note}</p>
      ) : null}

      {entry?.prize_draw_url ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => void copyLink()}>
            <Copy className="h-3.5 w-3.5 mr-1" />
            Copy entry link
          </Button>
          <Button size="sm" variant="outline" asChild>
            <a href={entry.prize_draw_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-3.5 w-3.5 mr-1" />
              Open form
            </a>
          </Button>
        </div>
      ) : null}

      {entry?.status === 'PENDING' && entry.submitted_at ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={busy} onClick={() => void handleApprove()}>
            Approve entry
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void handleReject()}>
            Reject entry
          </Button>
        </div>
      ) : null}

      <p className="text-xs text-muted-foreground">
        <Link href="/settings/review-prize-draw" className="text-primary underline hover:no-underline">
          Monthly draw admin
        </Link>
      </p>
    </div>
  );
}
