'use client';

import { useCallback, useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import confetti from 'canvas-confetti';
import type { Options as ConfettiOptions } from 'canvas-confetti';
import { X } from 'lucide-react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import {
  LEADLOCK_LOGIN_GREETING_SESSION_KEY,
  LOGIN_GREETING_AUTO_DISMISS_MS,
  displayFirstNameFromUser,
  getGreetingLabelForHour,
  loginGreetingPathShouldSuppress,
} from '@/lib/loginGreeting';

/** Match globals.css brand greens: --primary #1F6B3A, --secondary / --success #3FA86B */
const CONFETTI_Z = 5100;
const CONFETTI_COLORS = ['#1F6B3A', '#2d8f52', '#3FA86B', '#5cb87e', '#10B981', '#a7f3d0', '#ecfdf5'];

const FADE_OUT_MS = 500;

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
    particleCount: 85,
    spread: 82,
    startVelocity: 34,
    gravity: 0.95,
    scalar: 0.95,
    ticks: 200,
    origin: { x: 0.5, y: 0.62 },
  });

  return window.setTimeout(() => {
    burst({
      particleCount: 42,
      angle: 58,
      spread: 48,
      startVelocity: 28,
      origin: { x: 0.08, y: 0.68 },
    });
    burst({
      particleCount: 42,
      angle: 122,
      spread: 48,
      startVelocity: 28,
      origin: { x: 0.92, y: 0.68 },
    });
  }, 160);
}

export default function LoginGreeting() {
  const pathname = usePathname();
  const [active, setActive] = useState(false);
  const [exiting, setExiting] = useState(false);
  const [line, setLine] = useState('');

  const dismiss = useCallback(() => {
    setExiting(true);
  }, []);

  useEffect(() => {
    if (!exiting) return;
    const id = window.setTimeout(() => {
      setActive(false);
      setExiting(false);
      setLine('');
    }, FADE_OUT_MS);
    return () => window.clearTimeout(id);
  }, [exiting]);

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
        setExiting(false);
        setActive(true);
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
    if (!active || exiting) return;
    const id = window.setTimeout(dismiss, LOGIN_GREETING_AUTO_DISMISS_MS);
    return () => window.clearTimeout(id);
  }, [active, exiting, dismiss]);

  useEffect(() => {
    if (!active || exiting) return;
    let delayed: number | undefined;
    const raf = window.requestAnimationFrame(() => {
      delayed = fireLoginConfetti();
    });
    return () => {
      window.cancelAnimationFrame(raf);
      if (delayed !== undefined) window.clearTimeout(delayed);
    };
  }, [active, exiting]);

  if (!active || !line) return null;

  return (
    <div
      className={cn(
        'fixed inset-0 z-[5000] flex items-center justify-center bg-primary/10 p-6 backdrop-blur-[2px] transition-opacity duration-500 ease-out',
        exiting ? 'pointer-events-none opacity-0' : 'opacity-100',
      )}
    >
      <div
        role="status"
        aria-live="polite"
        className={cn(
          'relative max-w-[min(36rem,calc(100vw-2rem))] rounded-3xl border-2 border-primary/20 bg-gradient-to-br from-emerald-50/95 via-green-50/95 to-teal-50/90 px-10 py-12 pr-14 text-center shadow-xl shadow-primary/10 ring-1 ring-primary/15 transition-all duration-500 ease-out',
          exiting ? 'translate-y-1 scale-[0.98] opacity-0' : 'translate-y-0 scale-100 opacity-100',
        )}
      >
        <p className="text-4xl font-extrabold tracking-tight text-primary sm:text-5xl">{line}</p>
        <p className="mt-4 text-xl font-medium text-muted-foreground">
          Great to have you here — have a brilliant day.
        </p>
        <button
          type="button"
          onClick={dismiss}
          className="absolute right-4 top-4 rounded-full bg-primary/10 p-2 text-primary transition hover:bg-primary/15"
          aria-label="Dismiss greeting"
        >
          <X className="size-6" />
        </button>
      </div>
    </div>
  );
}
