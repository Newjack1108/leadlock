'use client';

import { useEffect } from 'react';
import api from '@/lib/api';

export default function Home() {
  useEffect(() => {
    let cancelled = false;
    const clearAuthStorage = () => {
      if (typeof window === 'undefined') return;
      localStorage.removeItem('token');
      document.cookie = 'token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
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
          clearAuthStorage();
          window.location.replace('/login');
          return;
        }

        const role = response.data?.role;
        const path =
          role === 'CLOSER'
            ? '/closer-dashboard'
            : role === 'DEALER_ADMIN' || role === 'DEALER_USER'
              ? '/dealer'
              : '/leads';
        window.location.replace(path);
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
