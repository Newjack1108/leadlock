/**
 * Helpers for compose-email HTML body: validation and plain-text multipart part.
 */

export function htmlToPlainText(html: string): string {
  if (typeof document === 'undefined') {
    return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  }
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const text = doc.body.textContent || '';
  return text.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
}

export function isHtmlEffectivelyEmpty(html: string): boolean {
  if (!html.trim()) return true;
  if (typeof document === 'undefined') {
    return html.replace(/<[^>]+>/g, '').trim().length === 0;
  }
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const text = (doc.body.textContent || '').replace(/\u00a0/g, ' ').trim();
  return text.length === 0;
}

/** True when HTML is unlikely to round-trip through TipTap StarterKit; use raw HTML source in compose. */
export function emailHtmlPrefersSourceView(html: string): boolean {
  if (!html || !html.trim()) return false;
  const head = html.trim().slice(0, 1200).toLowerCase();
  if (head.startsWith('<!doctype') || head.includes('<html')) return true;
  return /<\s*(table|tbody|thead|tfoot|tr|td|th|caption|colgroup|col|div|section|article|style|iframe|svg|pre|code)\b/i.test(
    html,
  );
}
