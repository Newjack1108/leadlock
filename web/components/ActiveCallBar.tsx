'use client';

import { Phone, Maximize2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useCallSession } from '@/components/callSessionContext';

export default function ActiveCallBar() {
  const { session, expand } = useCallSession();

  if (!session || !session.callInProgress || session.expanded) {
    return null;
  }

  return (
    <div
      className="fixed bottom-4 left-4 right-4 z-[9000] mx-auto flex max-w-lg items-center gap-3 rounded-lg border bg-background px-4 py-3 shadow-lg sm:left-auto sm:right-6 sm:mx-0"
      role="status"
      aria-live="polite"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Phone className="h-4 w-4" />
      </div>
      <button
        type="button"
        className="min-w-0 flex-1 text-left"
        onClick={expand}
        aria-label={`Expand call with ${session.customerName}`}
      >
        <div className="truncate text-sm font-medium">{session.customerName}</div>
        <div className="truncate text-xs text-muted-foreground">
          On call · {session.phone}
        </div>
      </button>
      <Button type="button" size="sm" variant="secondary" onClick={expand}>
        <Maximize2 className="mr-1.5 h-3.5 w-3.5" />
        Expand
      </Button>
    </div>
  );
}
