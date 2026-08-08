'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { LayoutGrid } from 'lucide-react';

import { type VariantProps } from 'class-variance-authority';

import { Button, buttonVariants } from '@/components/ui/button';
import { getAuthMe, getQuoteConfiguration } from '@/lib/api';
import { cn } from '@/lib/utils';

interface DraftConfiguratorLinkProps {
  quoteId: number;
  variant?: VariantProps<typeof buttonVariants>['variant'];
  size?: VariantProps<typeof buttonVariants>['size'];
  className?: string;
  label?: string;
  /** When set, configure page Back returns here instead of the quote detail. */
  returnHref?: string | null;
}

function configureHref(quoteId: number, returnHref?: string | null): string {
  const path = `/quotes/${quoteId}/configure`;
  if (!returnHref) return path;
  return `${path}?return=${encodeURIComponent(returnHref)}`;
}

export default function DraftConfiguratorLink({
  quoteId,
  variant = 'outline',
  size,
  className,
  label,
  returnHref,
}: DraftConfiguratorLinkProps) {
  const [canAccess, setCanAccess] = useState(false);
  const [savedBoxCount, setSavedBoxCount] = useState(0);
  const [hasSavedLayout, setHasSavedLayout] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAuthMe()
      .then((me) => {
        if (cancelled) return;
        const allowed = Boolean(me.can_access_configurator);
        setCanAccess(allowed);
        if (!allowed) return;
        return getQuoteConfiguration(quoteId).catch(() => {
          // 404 or probe failure: keep access; label falls back to "Configure layout".
          return null;
        });
      })
      .then((saved) => {
        if (cancelled || saved === undefined) return;
        const boxes = saved?.configuration?.boxes?.length ?? 0;
        const extras = saved?.configuration?.extras?.length ?? 0;
        setSavedBoxCount(boxes);
        setHasSavedLayout(boxes > 0 || extras > 0);
      })
      .catch(() => {
        // Auth failure only — do not hide the link when the layout probe fails.
        if (!cancelled) {
          setCanAccess(false);
          setHasSavedLayout(false);
          setSavedBoxCount(0);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [quoteId]);

  if (!canAccess) return null;

  const resolvedLabel = label ?? (hasSavedLayout ? 'Edit layout' : 'Configure layout');
  const title = hasSavedLayout && savedBoxCount > 0 ? `${savedBoxCount} boxes saved` : undefined;

  return (
    <Button variant={variant} size={size} className={cn(className)} asChild>
      <Link href={configureHref(quoteId, returnHref)} title={title}>
        <LayoutGrid className="h-4 w-4" />
        {resolvedLabel}
      </Link>
    </Button>
  );
}
