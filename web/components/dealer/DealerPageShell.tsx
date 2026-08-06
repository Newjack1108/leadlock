'use client';

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export default function DealerPageShell({
  children,
  className,
  narrow = false,
}: {
  children: ReactNode;
  className?: string;
  narrow?: boolean;
}) {
  return (
    <main
      className={cn(
        'container mx-auto px-4 py-5 sm:px-6 sm:py-8',
        narrow ? 'max-w-2xl' : 'max-w-5xl',
        className
      )}
    >
      {children}
    </main>
  );
}
