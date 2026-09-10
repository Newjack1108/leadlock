/** Paths that should not show the staff/dealer app header. */
export function appHeaderPathShouldHide(pathname: string | null): boolean {
  if (!pathname) return true;
  if (pathname === '/' || pathname === '/login' || pathname === '/on-leave') return true;
  if (pathname === '/data-deletion' || pathname === '/privacy') return true;
  if (pathname.startsWith('/quotes/view/')) return true;
  if (pathname.startsWith('/orders/view/')) return true;
  if (pathname.startsWith('/access-sheet/')) return true;
  if (pathname === '/configure' || pathname.startsWith('/configure/')) return true;
  if (pathname.startsWith('/review')) return true;
  if (pathname.startsWith('/xero-callback')) return true;
  return false;
}
