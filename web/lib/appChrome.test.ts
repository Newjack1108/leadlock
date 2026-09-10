import { describe, expect, it } from 'vitest';
import { appHeaderPathShouldHide } from '@/lib/appChrome';

describe('appHeaderPathShouldHide', () => {
  it('hides public and chrome-less routes', () => {
    expect(appHeaderPathShouldHide(null)).toBe(true);
    expect(appHeaderPathShouldHide('/')).toBe(true);
    expect(appHeaderPathShouldHide('/login')).toBe(true);
    expect(appHeaderPathShouldHide('/privacy')).toBe(true);
    expect(appHeaderPathShouldHide('/quotes/view/abc')).toBe(true);
    expect(appHeaderPathShouldHide('/configure')).toBe(true);
    expect(appHeaderPathShouldHide('/configure/token')).toBe(true);
    expect(appHeaderPathShouldHide('/review/token')).toBe(true);
    expect(appHeaderPathShouldHide('/review-prize/token')).toBe(true);
    expect(appHeaderPathShouldHide('/xero-callback')).toBe(true);
  });

  it('shows the header on staff and dealer app routes', () => {
    expect(appHeaderPathShouldHide('/leads')).toBe(false);
    expect(appHeaderPathShouldHide('/customers/12')).toBe(false);
    expect(appHeaderPathShouldHide('/quotes/3')).toBe(false);
    expect(appHeaderPathShouldHide('/dealer')).toBe(false);
    expect(appHeaderPathShouldHide('/dashboard')).toBe(false);
  });
});
