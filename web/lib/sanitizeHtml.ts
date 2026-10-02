import DOMPurify from 'isomorphic-dompurify';

/** Allowlist suitable for email bodies and HTML signatures. */
const EMAIL_HTML_CONFIG = {
  USE_PROFILES: { html: true },
  FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'input', 'link', 'meta', 'base'],
  FORBID_ATTR: ['srcdoc'],
};

export function sanitizeHtml(dirty: string | null | undefined): string {
  if (!dirty) return '';
  return DOMPurify.sanitize(dirty, EMAIL_HTML_CONFIG);
}
