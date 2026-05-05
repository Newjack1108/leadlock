'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { downloadDealerQuotePdf, getDealerProfile, getDealerQuotes, getDealerWelcome } from '@/lib/api';
import type { DealerProfile, DealerWelcome, Quote } from '@/lib/types';
import { toast } from 'sonner';

export default function DealerWelcomePage() {
  const [welcome, setWelcome] = useState<DealerWelcome | null>(null);
  const [profile, setProfile] = useState<DealerProfile | null>(null);
  const [latestQuote, setLatestQuote] = useState<Quote | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const [welcomeRes, profileRes, quotesRes] = await Promise.allSettled([
        getDealerWelcome(),
        getDealerProfile(),
        getDealerQuotes(),
      ]);
      if (welcomeRes.status === 'fulfilled') setWelcome(welcomeRes.value);
      else setWelcome(null);
      if (profileRes.status === 'fulfilled') setProfile(profileRes.value);
      else setProfile(null);
      if (quotesRes.status === 'fulfilled') setLatestQuote((quotesRes.value.items ?? [])[0] ?? null);
      else setLatestQuote(null);
      setLoading(false);
    };
    void load();
  }, []);

  const dealerName = profile?.company_name || profile?.name || welcome?.dealer_name || 'Trade Dealer';
  const dealerLogoUrl = profile?.logo_url;
  const dealerInitial = (dealerName || 'T').trim().charAt(0).toUpperCase();

  const formatDate = (value?: string) => {
    if (!value) return '—';
    return new Date(value).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  };

  return (
    <main className="container mx-auto px-4 py-6 sm:px-6">
      <div className="space-y-5">
        <Card className="border-slate-200 bg-gradient-to-br from-slate-50 to-blue-50/70">
          <CardContent className="pt-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-4">
                {dealerLogoUrl ? (
                  <img
                    src={dealerLogoUrl}
                    alt={`${dealerName} logo`}
                    className="h-16 w-16 rounded-xl border bg-white object-contain p-2 shadow-sm"
                  />
                ) : (
                  <div className="flex h-16 w-16 items-center justify-center rounded-xl border bg-white text-xl font-semibold text-slate-700 shadow-sm">
                    {dealerInitial}
                  </div>
                )}
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Dealer portal</p>
                  <h1 className="text-2xl font-semibold text-slate-900">{dealerName}</h1>
                  <p className="text-sm text-slate-600">
                    {welcome?.user_name ? `Welcome back, ${welcome.user_name}.` : 'Welcome back.'}
                  </p>
                </div>
              </div>
              {welcome && (
                <div className="rounded-lg border bg-white/80 px-4 py-3 text-sm text-slate-700 shadow-sm">
                  <p><strong>Commission:</strong> {welcome.commission_pct}%</p>
                  <p><strong>Dealer ID:</strong> {welcome.dealer_id}</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Latest Quote</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {loading && <p className="text-sm text-muted-foreground">Loading quote summary...</p>}
            {!loading && latestQuote && (
              <>
                <div className="grid gap-2 text-sm sm:grid-cols-2">
                  <p><strong>Quote:</strong> {latestQuote.quote_number}</p>
                  <p><strong>Customer:</strong> {latestQuote.customer_name ?? 'Customer'}</p>
                  <p><strong>Total:</strong> £{Number(latestQuote.total_amount).toFixed(2)}</p>
                  <p><strong>Updated:</strong> {formatDate(latestQuote.updated_at)}</p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Link href={`/dealer/quotes/${latestQuote.id}`}>
                    <Button>Open quote</Button>
                  </Link>
                  <Button
                    variant="outline"
                    onClick={() => {
                      void downloadDealerQuotePdf(latestQuote.id).catch((err: unknown) =>
                        toast.error(err instanceof Error ? err.message : 'Failed to download quote PDF')
                      );
                    }}
                  >
                    Download PDF
                  </Button>
                  <Link href="/dealer/quotes/new">
                    <Button variant="outline">Create quote</Button>
                  </Link>
                </div>
              </>
            )}
            {!loading && !latestQuote && (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  No quotes yet. Create your first quote to start tracking customer proposals.
                </p>
                <Link href="/dealer/quotes/new">
                  <Button>Create your first quote</Button>
                </Link>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Build simple quotes from your approved products and download PDF documents.
            </p>
            <p className="text-sm text-muted-foreground">
              Add your logo and company details in Dealer profile — they appear on quote PDFs.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link href="/dealer/quotes">
                <Button>View quotes</Button>
              </Link>
              <Link href="/dealer/quotes/new">
                <Button variant="outline">Create quote</Button>
              </Link>
              <Link href="/dealer/profile">
                <Button variant="outline">Dealer profile</Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
