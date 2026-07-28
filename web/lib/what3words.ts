/** Free-text What3Words helpers (format only; no API). */

const WHAT3WORDS_RE = /^[a-z]+\.[a-z]+\.[a-z]+$/;

/** Strip whitespace and leading ///, lowercase. Empty becomes ''. */
export function normalizeWhat3Words(value: string | null | undefined): string {
  let text = (value ?? '').trim().toLowerCase();
  if (text.startsWith('///')) {
    text = text.slice(3).trim();
  }
  return text;
}

/** True when empty or valid word.word.word format. */
export function isValidWhat3Words(value: string | null | undefined): boolean {
  const normalized = normalizeWhat3Words(value);
  if (!normalized) return true;
  return WHAT3WORDS_RE.test(normalized);
}
