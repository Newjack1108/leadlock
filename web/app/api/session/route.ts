import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const AUTH_COOKIE = 'leadlock_token';
const SESSION_MAX_AGE = 60 * 60 * 8; // 8 hours

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
    maxAge: SESSION_MAX_AGE,
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
