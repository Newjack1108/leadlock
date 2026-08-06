'use client';

import Logo from '@/components/Logo';

export default function DealerBrandStrip({
  subtitle = 'Trade dealer portal',
}: {
  subtitle?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-primary/20 bg-gradient-to-r from-primary/10 via-secondary/10 to-primary/5 px-4 py-3 sm:px-5">
      <Logo disableLink size="public" />
      <div className="min-w-0">
        <p className="text-sm font-semibold text-primary sm:text-base">Cheshire Stables</p>
        <p className="text-xs text-muted-foreground sm:text-sm">{subtitle}</p>
      </div>
    </div>
  );
}
