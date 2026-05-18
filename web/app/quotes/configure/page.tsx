'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '@/components/Header';
import ConfiguratorLogo from '@/components/configurator/ConfiguratorLogo';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getApiErrorDetail, getAuthMe, getConfiguratorAccessStatus, getQuotes } from '@/lib/api';
import type { AuthMe, ConfiguratorAccessStatus, Quote } from '@/lib/types';
import { QuoteStatus } from '@/lib/types';
import { toast } from 'sonner';

export default function QuoteConfiguratorPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [me, setMe] = useState<AuthMe | null>(null);
  const [access, setAccess] = useState<ConfiguratorAccessStatus | null>(null);
  const [draftQuotes, setDraftQuotes] = useState<Quote[]>([]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [meResponse, accessResponse, quoteList] = await Promise.all([
          getAuthMe(),
          getConfiguratorAccessStatus(),
          getQuotes({ status: QuoteStatus.DRAFT, page_size: 20 }),
        ]);
        if (cancelled) return;
        if (!meResponse.can_access_configurator) {
          toast.error('Configurator access is not enabled for this account.');
          router.replace('/quotes');
          return;
        }
        setMe(meResponse);
        setAccess(accessResponse);
        setDraftQuotes(quoteList.items);
      } catch (error: unknown) {
        if (cancelled) return;
        toast.error(getApiErrorDetail(error) || 'Configurator access is not enabled for this account.');
        router.replace('/quotes');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 py-8 sm:px-6">
        <div className="max-w-3xl space-y-6">
          <div className="flex flex-col items-center gap-3 text-center">
            <ConfiguratorLogo />
            <p className="text-muted-foreground">
              Hidden beta route for the internal configurator. Live sales users stay on the existing quote flow.
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Configurator Access</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {loading ? (
                <p className="text-muted-foreground">Checking configurator access...</p>
              ) : (
                <>
                  <p>
                    <strong>Signed in as:</strong> {me?.full_name ?? 'User'}
                  </p>
                  <p>
                    <strong>Capability enabled:</strong> {access?.enabled ? 'Yes' : 'No'}
                  </p>
                  <p>
                    <strong>Access mode:</strong> {access?.mode ?? 'Unavailable'}
                  </p>
                  <p className="text-muted-foreground">
                    The configurator works against existing draft quotes so it can generate normal quote lines without
                    replacing the standard quote editor.
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Open a Draft Quote</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading draft quotes...</p>
              ) : draftQuotes.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No draft quotes are available yet. Create a draft from a lead or customer, then use{' '}
                  <span className="font-medium text-foreground">Configure layout</span> on the draft quote or create
                  page to open the configurator here.
                </p>
              ) : (
                draftQuotes.map((quote) => (
                  <div
                    key={quote.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-4"
                  >
                    <div>
                      <p className="font-medium">{quote.quote_number}</p>
                      <p className="text-sm text-muted-foreground">
                        {quote.customer_name || 'Draft quote'} {quote.lead_name ? `· ${quote.lead_name}` : ''}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" asChild>
                        <Link href={`/quotes/${quote.id}`}>View Quote</Link>
                      </Button>
                      <Button asChild>
                        <Link href={`/quotes/${quote.id}/configure`}>Open Configurator</Link>
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <div className="flex flex-wrap gap-3">
            <Button onClick={() => router.push('/quotes')}>Back to Quotes</Button>
            <Button variant="outline" onClick={() => router.push('/dashboard')}>
              Back to Dashboard
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}
