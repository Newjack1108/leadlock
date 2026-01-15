'use client';

import { Badge } from '@/components/ui/badge';
import { ReminderPriority } from '@/lib/types';

interface StaleIndicatorProps {
  priority: ReminderPriority;
  daysStale: number;
  className?: string;
}

export default function StaleIndicator({ priority, daysStale, className }: StaleIndicatorProps) {
  const getVariant = () => {
    switch (priority) {
      case ReminderPriority.URGENT:
        return 'destructive';
      case ReminderPriority.HIGH:
        return 'default';
      case ReminderPriority.MEDIUM:
        return 'secondary';
      case ReminderPriority.LOW:
        return 'outline';
      default:
        return 'secondary';
    }
  };

  const getLabel = () => {
    if (daysStale >= 14) {
      return `Stale (${daysStale}d)`;
    } else if (daysStale >= 7) {
      return `${daysStale}d stale`;
    } else {
      return `${daysStale}d`;
    }
  };

  return (
    <Badge variant={getVariant()} className={className}>
      {getLabel()}
    </Badge>
  );
}
