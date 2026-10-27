import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const AUTH_COOKIE = 'leadlock_token';
const SESSION_MAX_AGE = 60 * 60 * 8; // 8 hours
const SESSION_MAX_AGE_CAP = 60 * 60 * 24 * 90; // 90 days

/** Decode JWT payload without verifying signature; expiry only drives cookie maxAge. */
function cookieMaxAgeFromAccessToken(accessToken: string): number {
  const parts = accessToken.split('.');
  if (parts.length < 2) {
    return SESSION_MAX_AGE;
  }
  try {
    const payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = payloadB64 + '='.repeat((4 - (payloadB64.length % 4)) % 4);
    const payloadJson =
      typeof atob === 'function'
        ? atob(padded)
        : Buffer.from(padded, 'base64').toString('utf8');
    const payload = JSON.parse(payloadJson) as { exp?: unknown };
    const exp = typeof payload.exp === 'number' ? payload.exp : null;
    if (exp == null) {
      return SESSION_MAX_AGE;
    }
    const remainingSeconds = Math.floor(exp - Date.now() / 1000);
    if (remainingSeconds <= 0) {
      return SESSION_MAX_AGE;
    }
    // Keep staff sessions at the 8-hour cap; only honour longer JWT expiry (bot viewer).
    if (remainingSeconds <= SESSION_MAX_AGE) {
      return SESSION_MAX_AGE;
    }
    return Math.min(remainingSeconds, SESSION_MAX_AGE_CAP);
  } catch {
    return SESSION_MAX_AGE;
  }
}

export async function POST(request: NextRequest) {
  let accessToken = '';
  try {
    const body = await request.json();
    accessToken = typeof body?.access_token === 'string' ? body.access_token.trim() : '';
  } catch {
    return NextResponse.json({ detail: 'Invalid body' }, { status: 400 });
  }
  if (!accessToken) {
    return NextResponse.json({ detail: 'access_token required' }, { status: 400 });
  }

  const secure = process.env.NODE_ENV === 'production';
  const response = NextResponse.json({ ok: true });
  response.cookies.set(AUTH_COOKIE, accessToken, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: cookieMaxAgeFromAccessToken(accessToken),
  });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(AUTH_COOKIE, '', {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 0,
  });
  return response;
}
