'use client';

import { useCallback, useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import confetti from 'canvas-confetti';
import type { Options as ConfettiOptions } from 'canvas-confetti';
import { X } from 'lucide-react';
import api from '@/lib/api';
import {
  LEADLOCK_LOGIN_GREETING_SESSION_KEY,
  LOGIN_GREETING_AUTO_DISMISS_MS,
  displayFirstNameFromUser,
  getGreetingLabelForHour,
  loginGreetingPathShouldSuppress,
} from '@/lib/loginGreeting';

const CONFETTI_Z = 5100;
const CONFETTI_COLORS = ['#ec4899', '#f472b6', '#fbbf24', '#fcd34d', '#22d3ee', '#67e8f9', '#a855f7', '#ffffff'];

/** Returns delayed side-burst timeout id for cleanup. */
function fireLoginConfetti(): number {
  const burst = (opts: ConfettiOptions) => {
    void confetti({
      zIndex: CONFETTI_Z,
      colors: CONFETTI_COLORS,
      ...opts,
    });
  };

  burst({
    particleCount: 110,
    spread: 88,
    startVelocity: 38,
    gravity: 0.95,
    scalar: 1.05,
    ticks: 220,
    origin: { x: 0.5, y: 0.62 },
  });

  return window.setTimeout(() => {
    burst({
      particleCount: 55,
      angle: 58,
      spread: 52,
      startVelocity: 32,
      origin: { x: 0.08, y: 0.68 },
    });
    burst({
      particleCount: 55,
      angle: 122,
      spread: 52,
      startVelocity: 32,
      origin: { x: 0.92, y: 0.68 },
    });
  }, 160);
}

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

  useEffect(() => {
    if (!open) return;
    let delayed: number | undefined;
    const raf = window.requestAnimationFrame(() => {
      delayed = fireLoginConfetti();
    });
    return () => {
      window.cancelAnimationFrame(raf);
      if (delayed !== undefined) window.clearTimeout(delayed);
    };
  }, [open]);

  if (!open || !line) return null;

  return (
    <div className="fixed inset-0 z-[5000] flex items-center justify-center bg-gradient-to-br from-fuchsia-600/35 via-amber-400/30 to-cyan-500/35 p-6 backdrop-blur-[3px]">
      <div
        role="status"
        aria-live="polite"
        className="animate-in fade-in zoom-in-95 relative max-w-[min(36rem,calc(100vw-2rem))] rounded-3xl border-4 border-white/70 bg-gradient-to-br from-pink-500 via-amber-400 to-cyan-400 px-10 py-12 pr-14 text-center shadow-2xl shadow-fuchsia-500/40 ring-4 ring-yellow-200/80 duration-300"
      >
        <p className="text-4xl font-extrabold tracking-tight text-white drop-shadow-md sm:text-5xl">{line}</p>
        <p className="mt-4 text-xl font-semibold text-white/95 drop-shadow">
          Great to have you here — have a brilliant day.
        </p>
        <button
          type="button"
          onClick={dismiss}
          className="absolute right-4 top-4 rounded-full bg-white/20 p-2 text-white transition hover:bg-white/35"
          aria-label="Dismiss greeting"
        >
          <X className="size-6" />
        </button>
      </div>
    </div>
  );
}
