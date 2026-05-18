'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { LayoutGrid } from 'lucide-react';

import { type VariantProps } from 'class-variance-authority';

import { Button, buttonVariants } from '@/components/ui/button';
import { getAuthMe } from '@/lib/api';
import { cn } from '@/lib/utils';

interface DraftConfiguratorLinkProps {
  quoteId: number;
  variant?: VariantProps<typeof buttonVariants>['variant'];
  size?: VariantProps<typeof buttonVariants>['size'];
  className?: string;
  label?: string;
}

export default function DraftConfiguratorLink({
  quoteId,
  variant = 'outline',
  size,
  className,
  label = 'Configure layout',
}: DraftConfiguratorLinkProps) {
  const [canAccess, setCanAccess] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAuthMe()
      .then((me) => {
        if (!cancelled) setCanAccess(Boolean(me.can_access_configurator));
      })
      .catch(() => {
        if (!cancelled) setCanAccess(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!canAccess) return null;

  return (
    <Button variant={variant} size={size} className={cn(className)} asChild>
      <Link href={`/quotes/${quoteId}/configure`}>
        <LayoutGrid className="h-4 w-4" />
        {label}
      </Link>
    </Button>
  );
}
