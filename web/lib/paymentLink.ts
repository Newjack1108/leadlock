/** Company PayPal No Code Payments page. Used as the default pay-by-link URL. */
export const PAYPAL_PAYMENT_LINK = 'https://www.paypal.com/ncp/payment/HM6Y7ZSG5SYQ6';

export const TRUST_PAYMENT_LINK_HOST = 'paybylink.trustpayments.com';

const MESSAGE_URL_RE =
  /(?:https?:\/\/[^\s<>"']+|www\.[^\s<>"']+|(?:paybylink\.trustpayments\.com|paypal\.com)\/[^\s<>"']+)/gi;

const TRAILING_URL_PUNCTUATION = /[.,;:)>\]}"'`]+$/;

export function isPayPalPaymentLink(url: string | null | undefined): boolean {
  return canonicalPaymentUrl(url) === PAYPAL_PAYMENT_LINK;
}

export function isAllowedPaymentLink(url: string | null | undefined): boolean {
  return canonicalPaymentUrl(url) !== null;
}

export function messageContainsOnlyPaymentLink(message: string, paymentUrl: string): boolean {
  const expected = canonicalPaymentUrl(paymentUrl);
  if (!expected) return false;
  const found = extractMessageUrls(message);
  if (found.length === 0) return false;
  return found.every((url) => canonicalPaymentUrl(url) === expected);
}

function extractMessageUrls(message: string): string[] {
  const found: string[] = [];
  for (const match of message.matchAll(MESSAGE_URL_RE)) {
    let candidate = match[0].replace(TRAILING_URL_PUNCTUATION, '');
    const lowered = candidate.toLowerCase();
    if (!lowered.startsWith('http://') && !lowered.startsWith('https://')) {
      candidate = `https://${candidate}`;
    }
    found.push(candidate);
  }
  return found;
}

function canonicalPaymentUrl(url: string | null | undefined): string | null {
  const trimmed = (url || '').trim();
  if (!trimmed || trimmed.includes('\\') || trimmed.includes('@')) return null;
  let candidate = trimmed;
  const lowered = candidate.toLowerCase();
  if (
    lowered.startsWith('www.') ||
    lowered.startsWith('paybylink.') ||
    lowered.startsWith('paypal.com/')
  ) {
    candidate = `https://${candidate}`;
  }
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    return null;
  }
  if (parsed.protocol !== 'https:') return null;
  if (parsed.username || parsed.password || parsed.port) return null;
  if (parsed.hostname.toLowerCase() === 'www.paypal.com') {
    if (parsed.search || parsed.hash) return null;
    const path = parsed.pathname.replace(/\/+$/, '');
    if (path !== '/ncp/payment/HM6Y7ZSG5SYQ6') return null;
    return PAYPAL_PAYMENT_LINK;
  }
  if (parsed.hostname.toLowerCase() !== TRUST_PAYMENT_LINK_HOST) return null;
  if (parsed.hash || parsed.pathname.includes('..')) return null;
  if ((candidate.match(/https:\/\//gi) || []).length !== 1) return null;
  let path = parsed.pathname;
  if (path.endsWith('/') && path !== '/') path = path.replace(/\/+$/, '');
  if (path === '' || path === '/') return null;
  const query = parsed.search ? parsed.search.slice(1) : '';
  return `https://${TRUST_PAYMENT_LINK_HOST}${path}${query ? `?${query}` : ''}`;
}
