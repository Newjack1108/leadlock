'use client';

import { useEffect, useState } from 'react';
import confetti from 'canvas-confetti';
import Logo from '@/components/Logo';
import { Button } from '@/components/ui/button';
import api from '@/lib/api';
import { displayFirstNameFromUser } from '@/lib/loginGreeting';
import { cn } from '@/lib/utils';
import styles from './on-leave.module.css';

const CONFETTI_COLORS = ['#1F6B3A', '#2d8f52', '#3FA86B', '#5cb87e', '#10B981', '#a7f3d0', '#ecfdf5'];

function formatBackOn(leaveUntil: string | null | undefined): string | null {
  if (!leaveUntil) return null;
  const raw = leaveUntil.includes('T') ? leaveUntil : `${leaveUntil}T00:00:00`;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

function clearAuthAndGoLogin() {
  localStorage.removeItem('token');
  document.cookie = 'token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  window.location.replace('/login');
}

function fireHolidayConfetti() {
  void confetti({
    particleCount: 90,
    spread: 88,
    startVelocity: 32,
    gravity: 0.9,
    scalar: 1,
    ticks: 220,
    origin: { x: 0.5, y: 0.55 },
    colors: CONFETTI_COLORS,
    zIndex: 40,
  });
}

export default function OnLeavePage() {
  const [ready, setReady] = useState(false);
  const [firstName, setFirstName] = useState('there');
  const [backOn, setBackOn] = useState<string | null>(null);
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const response = await api.get('/api/auth/me', {
          validateStatus: (status) => status === 200 || status === 401,
          skipAuthRedirect: true,
        });
        if (cancelled) return;
        if (response.status === 401) {
          clearAuthAndGoLogin();
          return;
        }
        if (!response.data?.on_leave) {
          window.location.replace('/');
          return;
        }
        setFirstName(
          displayFirstNameFromUser(response.data.full_name || '', response.data.email || '')
        );
        setBackOn(formatBackOn(response.data.leave_until));
        setReady(true);
        requestAnimationFrame(() => setEntered(true));

        const reduceMotion =
          typeof window !== 'undefined' &&
          window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (!reduceMotion) {
          fireHolidayConfetti();
        }
      } catch {
        if (!cancelled) clearAuthAndGoLogin();
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className={styles.screen}>
      <div className={styles.sunburst} aria-hidden />
      <div
        className={cn(
          'relative z-10 flex w-full max-w-2xl flex-col items-center text-center transition-all duration-500 ease-out',
          entered ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0'
        )}
      >
        <Logo />
        {ready ? (
          <>
            <p className="mt-10 text-lg font-medium text-white/85 sm:text-xl">
              See you later, {firstName}
            </p>
            <h1 className="mt-3 text-4xl font-bold tracking-tight text-white sm:text-6xl md:text-7xl">
              You&apos;re on holiday
            </h1>
            <p className="mt-5 max-w-lg text-base text-white/90 sm:text-xl">
              Have a lovely time — and stop thinking about work.
            </p>
            {backOn ? (
              <p className="mt-6 text-sm font-semibold uppercase tracking-[0.14em] text-white/75 sm:text-base">
                Back on {backOn}
              </p>
            ) : null}
            <Button
              type="button"
              variant="secondary"
              className="mt-10 h-12 w-full max-w-xs border-0 bg-white text-primary hover:bg-white/90"
              onClick={clearAuthAndGoLogin}
            >
              Log out
            </Button>
          </>
        ) : (
          <p className="mt-10 text-white/80">Loading...</p>
        )}
      </div>
    </div>
  );
}
