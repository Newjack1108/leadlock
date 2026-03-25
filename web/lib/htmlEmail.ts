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
