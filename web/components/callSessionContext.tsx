'use client';

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { toast } from 'sonner';

export type CallSessionTarget = {
  customerId: number;
  customerName: string;
  phone: string;
};

export type CallSessionState = CallSessionTarget & {
  notes: string;
  showSetReminder: boolean;
  reminderDate: string;
  reminderMessage: string;
  callInProgress: boolean;
  /** When true, full dialog is shown; when false (and call in progress), bar is shown. */
  expanded: boolean;
};

type CallLoggedListener = (customerId: number) => void;

export type CallSessionContextValue = {
  session: CallSessionState | null;
  openCall: (target: CallSessionTarget) => void;
  minimize: () => void;
  expand: () => void;
  endSession: () => void;
  updateSession: (patch: Partial<Omit<CallSessionState, 'customerId' | 'customerName' | 'phone'>>) => void;
  notifyCallLogged: (customerId: number) => void;
  registerCallLoggedListener: (listener: CallLoggedListener) => () => void;
};

const CallSessionContext = createContext<CallSessionContextValue | null>(null);

export function useCallSession(): CallSessionContextValue {
  const ctx = useContext(CallSessionContext);
  if (!ctx) {
    throw new Error('useCallSession must be used within CallSessionProvider');
  }
  return ctx;
}

export function CallSessionProviderInner({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<CallSessionState | null>(null);
  const listenersRef = useRef(new Set<CallLoggedListener>());

  const openCall = useCallback((target: CallSessionTarget) => {
    setSession((prev) => {
      if (prev) {
        toast.info(`Call with ${prev.customerName} is still open`);
        return { ...prev, expanded: true };
      }
      return {
        customerId: target.customerId,
        customerName: target.customerName,
        phone: target.phone,
        notes: '',
        showSetReminder: false,
        reminderDate: '',
        reminderMessage: '',
        callInProgress: false,
        expanded: true,
      };
    });
  }, []);

  const minimize = useCallback(() => {
    setSession((prev) => {
      if (!prev || !prev.callInProgress) return prev;
      return { ...prev, expanded: false };
    });
  }, []);

  const expand = useCallback(() => {
    setSession((prev) => (prev ? { ...prev, expanded: true } : prev));
  }, []);

  const endSession = useCallback(() => {
    setSession(null);
  }, []);

  const updateSession = useCallback(
    (patch: Partial<Omit<CallSessionState, 'customerId' | 'customerName' | 'phone'>>) => {
      setSession((prev) => (prev ? { ...prev, ...patch } : prev));
    },
    []
  );

  const notifyCallLogged = useCallback((customerId: number) => {
    listenersRef.current.forEach((listener) => {
      try {
        listener(customerId);
      } catch {
        // Ignore listener errors so one page cannot break others
      }
    });
  }, []);

  const registerCallLoggedListener = useCallback((listener: CallLoggedListener) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  const value = useMemo<CallSessionContextValue>(
    () => ({
      session,
      openCall,
      minimize,
      expand,
      endSession,
      updateSession,
      notifyCallLogged,
      registerCallLoggedListener,
    }),
    [
      session,
      openCall,
      minimize,
      expand,
      endSession,
      updateSession,
      notifyCallLogged,
      registerCallLoggedListener,
    ]
  );

  return (
    <CallSessionContext.Provider value={value}>{children}</CallSessionContext.Provider>
  );
}
