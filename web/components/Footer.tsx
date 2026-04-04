'use client';

import Logo from '@/components/Logo';

export default function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-border/60 bg-card/40 backdrop-blur-sm">
      <div className="container mx-auto flex flex-wrap items-center justify-center gap-x-3 gap-y-1 px-4 py-2.5 text-xs text-muted-foreground sm:px-6">
        <Logo size="sm" disableLink />
        <span>© {year} Newman Solutions</span>
      </div>
    </footer>
  );
}
