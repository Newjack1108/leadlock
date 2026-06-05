'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { getReviewPrizeContext, submitReviewPrizeEntry } from '@/lib/api';
import { ReviewPrizePublicContext } from '@/lib/types';
import { Gift, Star } from 'lucide-react';
import { toast } from 'sonner';

export default function ReviewPrizePage() {
  const params = useParams();
  const token = params.token as string;
  const [context, setContext] = useState<ReviewPrizePublicContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        setLoading(true);
        const data = await getReviewPrizeContext(token);
        setContext(data);
        if (data.platforms_claimed?.length) {
          setSelected(data.platforms_claimed);
        }
        if (data.status === 'PENDING' && data.submitted_at) {
          setSubmitted(true);
        }
        if (data.status === 'APPROVED') {
          setSubmitted(true);
        }
      } catch {
        toast.error('This prize draw link is invalid or has expired.');
      } finally {
        setLoading(false);
      }
    })();
  }, [token]);

  const minPlatforms = context?.min_platforms ?? 2;
  const canSubmit = context?.can_submit ?? false;
  const selectionValid = selected.length >= minPlatforms;

  const statusMessage = useMemo(() => {
    if (!context) return null;
    if (context.status === 'APPROVED') {
      return 'Your entry has been approved. Good luck in the draw!';
    }
    if (context.status === 'PENDING' && context.submitted_at) {
      return "Thanks — we've received your entry and will confirm it shortly.";
    }
    if (context.status === 'REJECTED') {
      return 'Your previous entry was not approved. You can submit again if you have left reviews on more platforms.';
    }
    return null;
  }, [context]);

  const togglePlatform = (code: string) => {
    setSelected((prev) =>
      prev.includes(code) ? prev.filter((p) => p !== code) : [...prev, code]
    );
  };

  const handleSubmit = async () => {
    if (!selectionValid) return;
    try {
      setSubmitting(true);
      await submitReviewPrizeEntry(token, selected);
      setSubmitted(true);
      const refreshed = await getReviewPrizeContext(token);
      setContext(refreshed);
      toast.success('Entry submitted — we will confirm shortly.');
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      toast.error(detail || 'Could not submit entry');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-muted/30">
        <p className="text-muted-foreground">Loading…</p>
      </div>
    );
  }

  if (!context) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-muted/30">
        <Card className="max-w-lg w-full">
          <CardContent className="pt-6">
            <p className="text-center text-muted-foreground">Prize draw link not found.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-muted/30">
      <Card className="max-w-lg w-full">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Gift className="h-6 w-6 text-teal-600" />
            <CardTitle>{context.prize_title || 'Monthly prize draw'}</CardTitle>
          </div>
          <p className="text-sm text-muted-foreground">
            Hi {context.customer_name}, thank you for your reviews on order {context.order_number}.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {context.prize_terms ? (
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">{context.prize_terms}</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Select the platforms where you have left a review (at least {minPlatforms} required).
            </p>
          )}

          {statusMessage ? (
            <div className="rounded-md border bg-teal-50/50 dark:bg-teal-950/20 p-3 text-sm flex gap-2">
              <Star className="h-4 w-4 shrink-0 text-teal-600 mt-0.5" />
              <span>{statusMessage}</span>
            </div>
          ) : null}

          {canSubmit && !submitted ? (
            <>
              <div className="space-y-3">
                {context.platforms.map((platform) => (
                  <div key={platform.code} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id={`platform-${platform.code}`}
                      checked={selected.includes(platform.code)}
                      onChange={() => togglePlatform(platform.code)}
                      className="h-4 w-4 rounded border-gray-300"
                    />
                    <Label htmlFor={`platform-${platform.code}`} className="font-normal cursor-pointer">
                      I left a review on {platform.label}
                    </Label>
                  </div>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                {selected.length} of {minPlatforms} minimum selected
              </p>
              <Button
                className="w-full"
                disabled={!selectionValid || submitting}
                onClick={() => void handleSubmit()}
              >
                {submitting ? 'Submitting…' : 'Enter prize draw'}
              </Button>
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
