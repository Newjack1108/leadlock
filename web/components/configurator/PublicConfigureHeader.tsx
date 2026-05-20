'use client';

import ConfiguratorLogo from '@/components/configurator/ConfiguratorLogo';
import Logo from '@/components/Logo';
import { cn } from '@/lib/utils';

interface PublicConfigureHeaderProps {
  subtitle?: string;
  className?: string;
}

/** Single branding row for public /configure pages: company logo + configurator image. */
export default function PublicConfigureHeader({ subtitle, className }: PublicConfigureHeaderProps) {
  return (
    <header className={cn('border-b bg-background px-4 py-3', className)}>
      <div className="container mx-auto space-y-2">
        <div className="flex items-center justify-center gap-3 sm:justify-start">
          <Logo disableLink size="public" />
          <div className="h-10 w-px shrink-0 bg-border sm:h-11" aria-hidden />
          <ConfiguratorLogo className="h-10 w-auto max-h-10 max-w-[min(140px,40vw)] shrink-0 sm:h-11 sm:max-h-11" />
        </div>
        {subtitle ? (
          <p className="text-center text-sm font-medium leading-snug sm:text-left">{subtitle}</p>
        ) : null}
      </div>
    </header>
  );
}
