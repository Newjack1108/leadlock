/** sessionStorage flag set on successful password login; read once by LoginGreeting. */
export const LEADLOCK_LOGIN_GREETING_SESSION_KEY = 'leadlock_login_greeting';

/** Auto-dismiss duration (ms). */
export const LOGIN_GREETING_AUTO_DISMISS_MS = 4_000;

const LOGIN_QUOTES = [
  { tone: 'witty', text: 'Success is 10% strategy and 90% remembering to hit save.' },
  { tone: 'witty', text: 'Great things begin with coffee, courage, and one brave click.' },
  { tone: 'fun', text: 'Today is a blank page. Sketch big, laugh often, ship something.' },
  { tone: 'fun', text: 'Momentum loves motion. Tiny steps still count as dancing forward.' },
  { tone: 'deep', text: 'Discipline is remembering what you want most, not what is easiest now.' },
  { tone: 'deep', text: 'Small consistent actions quietly become extraordinary outcomes.' },
] as const;

const DEFAULT_LOGIN_QUOTE = 'Show up with intention. The rest gets easier after the first step.';

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

export function pickRandomLoginQuote(): string {
  const playfulQuotes = LOGIN_QUOTES.filter((quote) => quote.tone === 'witty' || quote.tone === 'fun');
  const deepQuotes = LOGIN_QUOTES.filter((quote) => quote.tone === 'deep');
  const usePlayful = playfulQuotes.length > 0 && (deepQuotes.length === 0 || Math.random() < 0.7);
  const pool = usePlayful ? playfulQuotes : deepQuotes;
  if (pool.length === 0) return DEFAULT_LOGIN_QUOTE;
  const idx = Math.floor(Math.random() * pool.length);
  const selected = pool[idx];
  return selected?.text ?? DEFAULT_LOGIN_QUOTE;
}
