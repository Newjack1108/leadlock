'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { LayoutGrid, Package, User } from 'lucide-react';
import { toast } from 'sonner';
import DealerActionTile from '@/components/dealer/DealerActionTile';
import DealerBrandStrip from '@/components/dealer/DealerBrandStrip';
import DealerPageShell from '@/components/dealer/DealerPageShell';
import DealerQuoteCard from '@/components/dealer/DealerQuoteCard';
import DealerSection from '@/components/dealer/DealerSection';
import { Button } from '@/components/ui/button';
import { downloadDealerQuotePdf, getDealerProfile, getDealerQuotes, getDealerWelcome } from '@/lib/api';
import type { DealerProfile, DealerWelcome, Quote } from '@/lib/types';

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

  return (
    <DealerPageShell>
      <div className="space-y-6">
        <DealerBrandStrip subtitle="Official trade dealer portal" />

        <section className="rounded-2xl border border-primary/20 bg-white p-5 shadow-sm sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-4">
              {dealerLogoUrl ? (
                <img
                  src={dealerLogoUrl}
                  alt={`${dealerName} logo`}
                  className="h-16 w-16 rounded-2xl border border-primary/15 bg-white object-contain p-2 shadow-sm sm:h-20 sm:w-20"
                />
              ) : (
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-2xl font-semibold text-primary sm:h-20 sm:w-20">
                  {dealerInitial}
                </div>
              )}
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wide text-primary">
                  Selling Cheshire Stables
                </p>
                <h1 className="truncate text-2xl font-semibold text-foreground sm:text-3xl">
                  {dealerName}
                </h1>
                <p className="text-sm text-muted-foreground sm:text-base">
                  {welcome?.user_name ? `Welcome back, ${welcome.user_name}.` : 'Welcome back.'}
                </p>
              </div>
            </div>
            {welcome ? (
              <div className="inline-flex items-center self-start rounded-full border border-primary/25 bg-primary/10 px-4 py-2 text-sm font-semibold text-primary">
                {welcome.commission_pct}% commission
              </div>
            ) : null}
          </div>
        </section>

        <DealerSection
          title="Create a quote"
          description="Choose how you want to price Cheshire Stables products for your customer."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <DealerActionTile
              href="/dealer/quotes/configure"
              title="Configurator quote"
              description="Build a layout visually, then download a PDF."
              icon={LayoutGrid}
              variant="primary"
            />
            <DealerActionTile
              href="/dealer/quotes/new"
              title="Simple product quote"
              description="Pick stables and extras from your approved list."
              icon={Package}
              variant="secondary"
            />
          </div>
        </DealerSection>

        <DealerSection title="Latest quote" description="Jump back into your most recent customer quote.">
          {loading ? (
            <div className="rounded-xl border bg-white px-4 py-8 text-center text-sm text-muted-foreground">
              Loading quote summary…
            </div>
          ) : latestQuote ? (
            <DealerQuoteCard
              quote={latestQuote}
              onDownloadPdf={(id) => {
                void downloadDealerQuotePdf(id).catch((err: unknown) =>
                  toast.error(err instanceof Error ? err.message : 'Failed to download quote PDF')
                );
              }}
            />
          ) : (
            <div className="rounded-xl border border-dashed border-primary/30 bg-white px-4 py-8 text-center">
              <p className="text-sm text-muted-foreground sm:text-base">
                No quotes yet. Start with the configurator or a simple product quote above.
              </p>
            </div>
          )}
          <div className="flex flex-col gap-2 sm:flex-row">
            <Link href="/dealer/quotes" className="sm:flex-1">
              <Button variant="outline" size="lg" className="h-12 w-full border-primary/30 text-base">
                View all quotes
              </Button>
            </Link>
            <Link href="/dealer/profile" className="sm:flex-1">
              <Button variant="ghost" size="lg" className="h-12 w-full text-base text-primary">
                <User className="h-5 w-5" />
                Dealer profile
              </Button>
            </Link>
          </div>
        </DealerSection>
      </div>
    </DealerPageShell>
  );
}
