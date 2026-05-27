/** Injected from root layout (server reads API_URL at request time). */
export type LeadlockWindow = Window & {
  __LEADLOCK_API_URL__?: string;
};

/** API base URL for browser calls (no trailing slash). */
export function resolveApiBaseUrl(): string {
  if (typeof window !== 'undefined') {
    const injected = (window as LeadlockWindow).__LEADLOCK_API_URL__?.trim();
    if (injected) {
      return injected.replace(/\/+$/, '');
    }
  }
  const builtIn = (process.env.NEXT_PUBLIC_API_URL || '').trim();
  return builtIn.replace(/\/+$/, '');
}
