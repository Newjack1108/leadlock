export const CUSTOMERS_LIST_RETURN_URL_KEY = 'customersListReturnUrl';

export function parsePageFromSearchParams(sp: { get: (key: string) => string | null }): number {
  const raw = sp.get('page');
  if (!raw) return 1;
  const n = parseInt(raw, 10);
  return Number.isFinite(n) && n >= 1 ? n : 1;
}

export function saveCustomersListReturnUrl(): void {
  try {
    sessionStorage.setItem(
      CUSTOMERS_LIST_RETURN_URL_KEY,
      `${window.location.pathname}${window.location.search}`,
    );
  } catch {
    // ignore storage errors
  }
}

export function getCustomersListReturnUrl(): string | null {
  try {
    return sessionStorage.getItem(CUSTOMERS_LIST_RETURN_URL_KEY);
  } catch {
    return null;
  }
}
