'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const redirectByRole = async () => {
      try {
        const response = await api.get('/api/auth/me');
        const role = response.data?.role;
        if (role === 'CLOSER') {
          router.replace('/closer-dashboard');
        } else {
          router.replace('/leads');
        }
      } catch {
        router.replace('/login');
      }
    };
    redirectByRole();
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-muted-foreground">Loading...</div>
    </div>
  );
}
