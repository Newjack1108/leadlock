'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { LayoutGrid } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { getAuthMe } from '@/lib/api';
import { isPlaceholderOnlyDraftItems } from '@/lib/quoteDraftPayload';

interface DraftConfiguratorCalloutProps {
  quoteId: number | null;
  items: Array<{ description: string; quantity?: number; unit_price?: number }>;
}

export default function DraftConfiguratorCallout({ quoteId, items }: DraftConfiguratorCalloutProps) {
  const [canAccess, setCanAccess] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAuthMe()
      .then((me) => {
        if (!cancelled) setCanAccess(Boolean(me.can_access_configurator));
      })
      .catch(() => {
        if (!cancelled) setCanAccess(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!quoteId || !canAccess || !isPlaceholderOnlyDraftItems(items)) {
    return null;
  }

  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
        <p className="text-sm text-muted-foreground max-w-2xl">
          Build the stable block layout in the configurator first. When you are ready, return here to review terms
          and finish the quote.
        </p>
        <Button variant="default" className="shrink-0" asChild>
          <Link href={`/quotes/${quoteId}/configure`}>
            <LayoutGrid className="h-4 w-4" />
            Configure layout
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
