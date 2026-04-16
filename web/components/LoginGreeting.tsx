'use client';

import { useCallback, useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { X } from 'lucide-react';
import api from '@/lib/api';
import {
  LEADLOCK_LOGIN_GREETING_SESSION_KEY,
  LOGIN_GREETING_AUTO_DISMISS_MS,
  displayFirstNameFromUser,
  getGreetingLabelForHour,
  loginGreetingPathShouldSuppress,
} from '@/lib/loginGreeting';

export default function LoginGreeting() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [line, setLine] = useState('');

  const dismiss = useCallback(() => {
    setOpen(false);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (loginGreetingPathShouldSuppress(pathname)) return;
    if (sessionStorage.getItem(LEADLOCK_LOGIN_GREETING_SESSION_KEY) !== '1') return;
    if (!localStorage.getItem('token')) return;

    let cancelled = false;

    const run = async () => {
      try {
        const { data } = await api.get<{ full_name: string; email: string }>('/api/auth/me');
        if (cancelled) return;
        sessionStorage.removeItem(LEADLOCK_LOGIN_GREETING_SESSION_KEY);
        const hour = new Date().getHours();
        const greeting = getGreetingLabelForHour(hour);
        const name = displayFirstNameFromUser(data.full_name ?? '', data.email ?? '');
        setLine(`${greeting}, ${name}!`);
        setOpen(true);
      } catch {
        if (cancelled) return;
        // Keep session flag so a refresh or route change can retry /me.
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const id = window.setTimeout(dismiss, LOGIN_GREETING_AUTO_DISMISS_MS);
    return () => window.clearTimeout(id);
  }, [open, dismiss]);

  if (!open || !line) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-[200] flex justify-center px-4">
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-auto relative max-w-md rounded-2xl border border-amber-200/80 bg-gradient-to-br from-amber-100 via-yellow-50 to-sky-100 px-5 py-4 pr-12 text-center shadow-lg shadow-amber-200/40 ring-1 ring-white/60"
      >
        <p className="text-lg font-semibold tracking-tight text-amber-950">{line}</p>
        <p className="mt-1 text-sm text-amber-900/80">Great to have you here. Have a productive day.</p>
        <button
          type="button"
          onClick={dismiss}
          className="absolute right-3 top-3 rounded-full p-1 text-amber-900/60 transition hover:bg-amber-200/60 hover:text-amber-950"
          aria-label="Dismiss greeting"
        >
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
}
