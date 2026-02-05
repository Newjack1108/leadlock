import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  // Check for token in cookie (we'll set this on login)
  const token = request.cookies.get('token')?.value;
  
  const isLoginPage = request.nextUrl.pathname === '/login';
  const isPublicQuoteView = request.nextUrl.pathname.startsWith('/quotes/view/');
  const isPublicPage = isLoginPage || isPublicQuoteView;

  // If no token and trying to access protected route, redirect to login
  // Note: We also check token in client-side, this is just a basic check
  if (!isPublicPage && !token) {
    // Allow through - client-side will handle redirect if token missing
    return NextResponse.next();
  }

  // If has token and on login page, redirect to leads
  if (isLoginPage && token) {
    return NextResponse.redirect(new URL('/leads', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};
