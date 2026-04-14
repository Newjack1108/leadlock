'use client';

import { Badge } from '@/components/ui/badge';

type NinoxBadgeProps = {
  className?: string;
};

export default function NinoxBadge({ className }: NinoxBadgeProps) {
  return (
    <Badge
      variant="secondary"
      className={`font-normal border-transparent bg-blue-500 text-white hover:bg-blue-500 dark:bg-sky-400 dark:text-slate-950 ${className ?? ''}`.trim()}
    >
      Ninox
    </Badge>
  );
}
