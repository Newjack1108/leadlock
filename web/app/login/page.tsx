'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import Logo from '@/components/Logo';
import api, { AUTH_FETCH_TIMEOUT_MS, getApiErrorDetail } from '@/lib/api';
import { LEADLOCK_LOGIN_GREETING_SESSION_KEY } from '@/lib/loginGreeting';
import { toast } from 'sonner';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const response = await api.post(
        '/api/auth/login',
        { email, password },
        { timeout: AUTH_FETCH_TIMEOUT_MS }
      );

      const accessToken = response.data?.access_token as string | undefined;
      if (!accessToken) {
        throw new Error('Login did not return a session');
      }
      const sessionRes = await fetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_token: accessToken }),
        redirect: 'manual',
      });
      if (sessionRes.type === 'opaqueredirect' || !sessionRes.ok) {
        throw new Error('Could not start a session. Please try again.');
      }
      try {
        localStorage.removeItem('token');
      } catch {
        // ignore
      }
      document.cookie = 'token=; path=/; max-age=0';
      sessionStorage.setItem(LEADLOCK_LOGIN_GREETING_SESSION_KEY, '1');
      router.push('/');
    } catch (error: unknown) {
      const message = getApiErrorDetail(error);
      toast.error(
        message.includes('Network Error') || message.includes('CORS')
          ? `${message} — check API is online and CORS_ORIGINS includes this site.`
          : message || 'Login failed'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <Card className="w-full max-w-md shadow-lg">
        <CardHeader className="space-y-6">
          <div className="flex justify-center">
            <Logo />
          </div>
          <div className="space-y-2">
            <CardTitle className="text-2xl text-center">Welcome</CardTitle>
            <CardDescription className="text-center">
              Sign in to access LeadLock
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@cheshirestables.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={loading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={loading}
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Signing in...' : 'Sign In'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
