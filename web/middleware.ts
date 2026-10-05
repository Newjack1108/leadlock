import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const AUTH_COOKIE = 'leadlock_token';
const LEGACY_AUTH_COOKIE = 'token';

function withSecurityHeaders(response: NextResponse): NextResponse {
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  response.headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  response.headers.set(
    'Content-Security-Policy',
    [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https:",
      "font-src 'self' data:",
      "connect-src 'self' https: http://localhost:* http://127.0.0.1:*",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join('; ')
  );
  return response;
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Session cookie is set before the user has a token. Do not treat it as a page route.
  if (pathname === '/api/session') {
    return NextResponse.next();
  }

  // Attach JWT from HttpOnly cookie so same-origin /api rewrites authenticate against FastAPI.
  if (pathname.startsWith('/api/')) {
    const token = request.cookies.get(AUTH_COOKIE)?.value;
    if (token) {
      const headers = new Headers(request.headers);
      if (!headers.get('authorization')) {
        headers.set('Authorization', `Bearer ${token}`);
      }
      return NextResponse.next({ request: { headers } });
    }
    return NextResponse.next();
  }

  const token =
    request.cookies.get(AUTH_COOKIE)?.value ||
    request.cookies.get(LEGACY_AUTH_COOKIE)?.value;

  const isLoginPage = pathname === '/login';
  const isPublicQuoteView = pathname.startsWith('/quotes/view/');
  const isPublicOrderView = pathname.startsWith('/orders/view/');
  const isPublicAccessSheet = pathname.startsWith('/access-sheet/');
  const isPublicConfigure =
    pathname === '/configure' || pathname.startsWith('/configure/');
  const isPublicReview =
    pathname.startsWith('/review/') || pathname.startsWith('/review-prize/');
  const isDataDeletionPage = pathname === '/data-deletion';
  const isPrivacyPage = pathname === '/privacy';
  const isPublicPage =
    isLoginPage ||
    isPublicQuoteView ||
    isPublicOrderView ||
    isPublicAccessSheet ||
    isPublicConfigure ||
    isPublicReview ||
    isDataDeletionPage ||
    isPrivacyPage;

  if (!isPublicPage && !token) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('next', pathname);
    return withSecurityHeaders(NextResponse.redirect(loginUrl));
  }

  if (isLoginPage && token) {
    return withSecurityHeaders(NextResponse.redirect(new URL('/', request.url)));
  }

  return withSecurityHeaders(NextResponse.next());
}

export const config = {
  matcher: [
    '/api/:path*',
    // Public files such as /email-icon.png must skip auth. The image optimizer
    // fetches them without a cookie; a login redirect is not an image, so the
    // customer profile icons fail to render.
    '/((?!_next/static|_next/image|.*\\.(?:png|jpe?g|gif|webp|svg|ico|txt|xml|webmanifest)$).*)',
  ],
};
