'use client';

import { useEffect } from 'react';
import api, { logoutSession } from '@/lib/api';
import { postLoginPathForRole } from '@/lib/loginGreeting';

export default function Home() {
  useEffect(() => {
    let cancelled = false;
    const clearAuthStorage = async () => {
      await logoutSession();
    };

    const redirectByRole = async () => {
      try {
        // Treat 401 as success so the global axios error interceptor does not also
        // fire window.location to /login while this effect runs router.replace — that
        // double navigation can strand iOS Safari (e.g. opening from a bookmark).
        const response = await api.get('/api/auth/me', {
          validateStatus: (status) => status === 200 || status === 401,
          skipAuthRedirect: true,
        });
        if (cancelled) return;
        if (response.status === 401) {
          await clearAuthStorage();
          window.location.replace('/login');
          return;
        }
        if (response.data?.on_leave) {
          window.location.replace('/on-leave');
          return;
        }
        window.location.replace(postLoginPathForRole(response.data?.role));
      } catch {
        if (!cancelled) {
          clearAuthStorage();
          window.location.replace('/login');
        }
      }
    };

    redirectByRole();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-muted-foreground">Loading...</div>
    </div>
  );
}
