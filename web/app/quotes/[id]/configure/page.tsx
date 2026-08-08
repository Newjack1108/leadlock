'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import ConfiguratorShell from '@/components/configurator/ConfiguratorShell';
import { getApiErrorDetail, getAuthMe, getQuote } from '@/lib/api';
import type { Quote } from '@/lib/types';
import { toast } from 'sonner';

function parseQuoteId(raw: string | string[] | undefined): number | null {
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (typeof value !== 'string' || value.trim() === '') return null;
  const id = Number(value);
  return Number.isFinite(id) && id > 0 ? id : null;
}

export default function QuoteConfiguratorDetailPage() {
  const params = useParams();
  const router = useRouter();
  const quoteId = parseQuoteId(params.id);
  const [loading, setLoading] = useState(true);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    if (quoteId == null) {
      // Wait for params on first paint; only treat as invalid once id is present but bad.
      if (params.id !== undefined && params.id !== null && params.id !== '') {
        setLoading(false);
        setError('Invalid quote id.');
      }
      return () => {
        cancelled = true;
      };
    }

    const load = async () => {
      setLoading(true);
      setError(null);
      setQuote(null);
      try {
        const [me, loadedQuote] = await Promise.all([getAuthMe(), getQuote(quoteId)]);
        if (cancelled) return;
        if (!me.can_access_configurator) {
          const message = 'Configurator access is not enabled for this account.';
          setError(message);
          toast.error(message);
          return;
        }
        if (loadedQuote.status !== 'DRAFT') {
          const message = 'Only draft quotes can be configured.';
          setError(message);
          toast.error(message);
          return;
        }
        setQuote(loadedQuote);
      } catch (err) {
        if (!cancelled) {
          const message = getApiErrorDetail(err) || 'Failed to load configurator quote';
          setError(message);
          toast.error(message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [quoteId, params.id]);

  const backHref = quoteId != null ? `/quotes/${quoteId}` : '/quotes';

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
              <p className="text-muted-foreground">
                {error || 'Quote not available for configurator use.'}
              </p>
              <Button onClick={() => router.push(backHref)}>Back to quote</Button>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
