/** sessionStorage flag set on successful password login; read once by LoginGreeting. */
export const LEADLOCK_LOGIN_GREETING_SESSION_KEY = 'leadlock_login_greeting';

/** Auto-dismiss duration (ms). */
export const LOGIN_GREETING_AUTO_DISMISS_MS = 3_000;

export function getGreetingLabelForHour(hour: number): string {
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/** Paths where we do not show the post-login greeting (aligns with middleware public routes + home redirect). */
export function loginGreetingPathShouldSuppress(pathname: string | null): boolean {
  if (!pathname) return true;
  if (pathname === '/' || pathname === '/login') return true;
  if (pathname.startsWith('/quotes/view/')) return true;
  if (pathname.startsWith('/orders/view/')) return true;
  if (pathname.startsWith('/access-sheet/')) return true;
  return false;
}

export function displayFirstNameFromUser(fullName: string, email: string): string {
  const fromName = fullName.trim().split(/\s+/)[0];
  if (fromName) return fromName;
  const local = email.split('@')[0]?.trim();
  return local || 'there';
}
