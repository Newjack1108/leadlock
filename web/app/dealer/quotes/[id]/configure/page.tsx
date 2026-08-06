'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import ConfiguratorShell, { type ConfiguratorShellAdapters } from '@/components/configurator/ConfiguratorShell';
import DealerPageShell from '@/components/dealer/DealerPageShell';
import {
  applyDealerQuoteConfiguration,
  getApiErrorDetail,
  getDealerConfiguratorCatalog,
  getDealerQuote,
  getDealerQuoteConfiguration,
  previewDealerConfiguratorConfiguration,
  resetDealerQuoteConfiguration,
  saveDealerQuoteConfiguration,
} from '@/lib/api';
import type { Quote } from '@/lib/types';
import { QuoteStatus } from '@/lib/types';
import { toast } from 'sonner';

export default function DealerQuoteConfigurePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const quoteId = Number(params.id);
  const [loading, setLoading] = useState(true);
  const [quote, setQuote] = useState<Quote | null>(null);

  const adapters = useMemo<ConfiguratorShellAdapters>(
    () => ({
      getCatalog: getDealerConfiguratorCatalog,
      getConfiguration: getDealerQuoteConfiguration,
      saveConfiguration: saveDealerQuoteConfiguration,
      preview: previewDealerConfiguratorConfiguration,
      apply: applyDealerQuoteConfiguration,
      resetDraftLines: async (id) => {
        await resetDealerQuoteConfiguration(id);
      },
    }),
    []
  );

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!Number.isFinite(quoteId)) {
        router.replace('/dealer/quotes');
        return;
      }
      try {
        const loaded = await getDealerQuote(quoteId);
        if (cancelled) return;
        if (loaded.status !== QuoteStatus.DRAFT) {
          toast.error('Only draft quotes can be configured.');
          router.replace(`/dealer/quotes/${quoteId}`);
          return;
        }
        setQuote(loaded);
      } catch (error) {
        if (!cancelled) {
          toast.error(getApiErrorDetail(error) || 'Failed to load dealer quote');
          router.replace('/dealer/quotes');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [quoteId, router]);

  return (
    <DealerPageShell className="max-w-7xl">
      {loading ? (
        <Card className="border-primary/15">
          <CardContent className="py-12 text-center text-muted-foreground">
            Loading configurator...
          </CardContent>
        </Card>
      ) : quote ? (
        <ConfiguratorShell
          quote={quote}
          adapters={adapters}
          backHref={`/dealer/quotes/${quote.id}`}
          afterApplyHref={`/dealer/quotes/${quote.id}`}
        />
      ) : (
        <Card className="border-primary/15">
          <CardContent className="space-y-4 py-12 text-center">
            <p className="text-muted-foreground">Quote not available for configurator use.</p>
            <Button size="lg" className="h-12" onClick={() => router.push('/dealer/quotes')}>
              Back to quotes
            </Button>
          </CardContent>
        </Card>
      )}
    </DealerPageShell>
  );
}
