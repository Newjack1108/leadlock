'use client';

import { Badge } from '@/components/ui/badge';

type TestCustomerBadgeProps = {
  className?: string;
};

export default function TestCustomerBadge({ className }: TestCustomerBadgeProps) {
  return (
    <Badge
      variant="secondary"
      className={`font-normal border-transparent bg-amber-600 text-white hover:bg-amber-600 dark:bg-amber-500 dark:text-slate-950 ${className ?? ''}`.trim()}
    >
      Test
    </Badge>
  );
}
