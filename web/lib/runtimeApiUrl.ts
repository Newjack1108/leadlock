/** Injected from root layout (server reads API_URL at request time). */
export type LeadlockWindow = Window & {
  __LEADLOCK_API_URL__?: string;
};

/**
 * API base URL for browser calls (no trailing slash).
 * An explicit empty injection means same-origin `/api` (HttpOnly cookie).
 * Do not fall through to the build-time URL in that case, or the browser
 * calls the API host and drops the session cookie.
 */
export function resolveApiBaseUrl(): string {
  if (typeof window !== 'undefined' && '__LEADLOCK_API_URL__' in window) {
    const injected = (window as LeadlockWindow).__LEADLOCK_API_URL__ ?? '';
    return injected.trim().replace(/\/+$/, '');
  }
  const builtIn = (process.env.NEXT_PUBLIC_API_URL || '').trim();
  return builtIn.replace(/\/+$/, '');
}
