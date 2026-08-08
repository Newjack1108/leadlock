'use client';

import { Suspense, useEffect, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
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

/** Only allow in-app relative return paths (blocks open redirects). */
function safeReturnHref(raw: string | null): string | null {
  if (!raw) return null;
  if (!raw.startsWith('/') || raw.startsWith('//')) return null;
  return raw;
}

function QuoteConfiguratorDetailContent() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const quoteId = parseQuoteId(params.id);
  const returnHref = safeReturnHref(searchParams.get('return'));
  const [loading, setLoading] = useState(true);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [quoteMissing, setQuoteMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;

    if (quoteId == null) {
      // Wait for params on first paint; only treat as invalid once id is present but bad.
      if (params.id !== undefined && params.id !== null && params.id !== '') {
        setLoading(false);
        setError('Invalid quote id.');
        setQuoteMissing(true);
      }
      return () => {
        cancelled = true;
      };
    }

    const load = async () => {
      setLoading(true);
      setError(null);
      setQuote(null);
      setQuoteMissing(false);
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
          const status = (err as { response?: { status?: number } })?.response?.status;
          const message = getApiErrorDetail(err) || 'Failed to load configurator quote';
          setError(message);
          setQuoteMissing(status === 404);
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

  const backHref =
    returnHref ??
    (quoteMissing || quoteId == null ? '/quotes' : `/quotes/${quoteId}`);

  return (
    <main className="container mx-auto px-4 py-8 sm:px-6">
      {loading ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            Loading configurator...
          </CardContent>
        </Card>
      ) : quote ? (
        <ConfiguratorShell quote={quote} backHref={backHref} />
      ) : (
        <Card>
          <CardContent className="space-y-4 py-12 text-center">
            <p className="text-muted-foreground">
              {error || 'Quote not available for configurator use.'}
            </p>
            <Button onClick={() => router.push(backHref)}>
              {returnHref ? 'Back to draft' : quoteMissing ? 'Back to quotes' : 'Back to quote'}
            </Button>
          </CardContent>
        </Card>
      )}
    </main>
  );
}

export default function QuoteConfiguratorDetailPage() {
  return (
    <div className="min-h-screen">
      <Header />
      <Suspense
        fallback={
          <main className="container mx-auto px-4 py-8 sm:px-6">
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                Loading configurator...
              </CardContent>
            </Card>
          </main>
        }
      >
        <QuoteConfiguratorDetailContent />
      </Suspense>
    </div>
  );
}
