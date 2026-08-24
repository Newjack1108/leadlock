'use client';

import type { ReactNode } from 'react';
import { CallSessionProviderInner } from '@/components/callSessionContext';
import CallNotesDialog from '@/components/CallNotesDialog';
import ActiveCallBar from '@/components/ActiveCallBar';

export { useCallSession } from '@/components/callSessionContext';
export type { CallSessionTarget, CallSessionState } from '@/components/callSessionContext';

export default function CallSessionProvider({ children }: { children: ReactNode }) {
  return (
    <CallSessionProviderInner>
      {children}
      <CallNotesDialog />
      <ActiveCallBar />
    </CallSessionProviderInner>
  );
}
