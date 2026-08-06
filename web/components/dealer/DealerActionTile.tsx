'use client';

import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function DealerActionTile({
  href,
  title,
  description,
  icon: Icon,
  variant = 'primary',
}: {
  href: string;
  title: string;
  description: string;
  icon: LucideIcon;
  variant?: 'primary' | 'secondary';
}) {
  return (
    <Link
      href={href}
      className={cn(
        'flex min-h-[5.5rem] items-start gap-4 rounded-xl border px-4 py-4 shadow-sm transition-all active:scale-[0.99]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        variant === 'primary'
          ? 'border-primary/30 bg-primary text-primary-foreground hover:bg-primary/90'
          : 'border-primary/20 bg-white text-foreground hover:border-primary/40 hover:bg-primary/5'
      )}
    >
      <span
        className={cn(
          'flex h-12 w-12 shrink-0 items-center justify-center rounded-xl',
          variant === 'primary' ? 'bg-white/15' : 'bg-primary/10 text-primary'
        )}
      >
        <Icon className="h-6 w-6" />
      </span>
      <span className="min-w-0 flex-1 text-left">
        <span className="block text-base font-semibold sm:text-lg">{title}</span>
        <span
          className={cn(
            'mt-0.5 block text-sm',
            variant === 'primary' ? 'text-primary-foreground/85' : 'text-muted-foreground'
          )}
        >
          {description}
        </span>
      </span>
    </Link>
  );
}
