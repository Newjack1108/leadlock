'use client';

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export default function DealerSection({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('space-y-4', className)}>
      <div className="space-y-1 border-l-4 border-primary pl-3">
        <h2 className="text-lg font-semibold text-foreground sm:text-xl">{title}</h2>
        {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}
