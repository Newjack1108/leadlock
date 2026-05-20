'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import ConfiguratorShell from '@/components/configurator/ConfiguratorShell';
import { getApiErrorDetail, getAuthMe, getQuote } from '@/lib/api';
import type { Quote } from '@/lib/types';
import { QuoteStatus } from '@/lib/types';
import { toast } from 'sonner';

export default function QuoteConfiguratorDetailPage() {
  const params = useParams();
  const router = useRouter();
  const quoteId = Number(params.id);
  const [loading, setLoading] = useState(true);
  const [quote, setQuote] = useState<Quote | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [me, loadedQuote] = await Promise.all([getAuthMe(), getQuote(quoteId)]);
        if (cancelled) return;
        if (!me.can_access_configurator) {
          toast.error('Configurator access is not enabled for this account.');
          router.replace('/quotes');
          return;
        }
        if (loadedQuote.status !== QuoteStatus.DRAFT) {
          toast.error('Only draft quotes can be configured.');
          router.replace(`/quotes/${quoteId}`);
          return;
        }
        setQuote(loadedQuote);
      } catch (error) {
        if (!cancelled) {
          toast.error(getApiErrorDetail(error) || 'Failed to load configurator quote');
          router.replace('/quotes');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    if (Number.isFinite(quoteId)) {
      void load();
    } else {
      router.replace('/quotes');
    }
    return () => {
      cancelled = true;
    };
  }, [quoteId, router]);

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 py-8 sm:px-6">
        {loading ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              Loading configurator...
            </CardContent>
          </Card>
        ) : quote ? (
          <ConfiguratorShell quote={quote} />
        ) : (
          <Card>
            <CardContent className="space-y-4 py-12 text-center">
              <p className="text-muted-foreground">Quote not available for configurator use.</p>
              <Button
                onClick={() =>
                  router.push(Number.isFinite(quoteId) ? `/quotes/${quoteId}` : '/quotes')
                }
              >
                Back to quote
              </Button>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
