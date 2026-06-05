'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { getReviewHubContext } from '@/lib/api';
import { ReviewHubPublicContext } from '@/lib/types';
import { ExternalLink, Gift, Star } from 'lucide-react';
import { toast } from 'sonner';

export default function ReviewHubPage() {
  const params = useParams();
  const token = params.token as string;
  const [context, setContext] = useState<ReviewHubPublicContext | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        setLoading(true);
        const data = await getReviewHubContext(token);
        setContext(data);
      } catch {
        toast.error('This review link is invalid or has expired.');
      } finally {
        setLoading(false);
      }
    })();
  }, [token]);

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
            <p className="text-center text-muted-foreground">Review link not found.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const greetingName = context.customer_name?.split(' ')[0] || 'there';

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-muted/30">
      <Card className="max-w-lg w-full">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Star className="h-6 w-6 text-teal-600" />
            <CardTitle>We would love your feedback</CardTitle>
          </div>
          <p className="text-sm text-muted-foreground">
            Hi {greetingName}
            {context.company_name ? `, thank you for choosing ${context.company_name}` : ''}
            {context.order_number ? ` (order ${context.order_number})` : ''}.
          </p>
          <p className="text-sm text-muted-foreground">
            If you have a moment, please leave a review on one or more of the platforms below.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-2">
            {context.platforms.map((platform) => (
              <Button key={platform.code} variant="outline" className="w-full justify-start h-auto py-3" asChild>
                <a href={platform.url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="h-4 w-4 mr-2 shrink-0" />
                  Leave a {platform.label} review
                </a>
              </Button>
            ))}
          </div>

          {context.prize_draw ? (
            <div className="rounded-md border bg-teal-50/50 dark:bg-teal-950/20 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Gift className="h-5 w-5 text-teal-600 shrink-0" />
                <p className="font-medium">{context.prize_draw.title}</p>
              </div>
              {context.prize_draw.terms ? (
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{context.prize_draw.terms}</p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Left reviews on at least {context.prize_draw.min_platforms} platforms? Enter our monthly prize draw.
                </p>
              )}
              <Button className="w-full" asChild>
                <a href={context.prize_draw.url} target="_blank" rel="noopener noreferrer">
                  Enter the prize draw
                </a>
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
