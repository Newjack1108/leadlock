import { afterEach, describe, expect, it } from 'vitest';
import { resolveApiBaseUrl, type LeadlockWindow } from '@/lib/runtimeApiUrl';

const previousWindow = globalThis.window;

afterEach(() => {
  if (previousWindow === undefined) {
    delete (globalThis as { window?: Window }).window;
  } else {
    globalThis.window = previousWindow;
  }
});

describe('resolveApiBaseUrl', () => {
  it('uses an explicit empty injection as same-origin, not the baked API URL', () => {
    globalThis.window = { __LEADLOCK_API_URL__: '' } as LeadlockWindow;
    expect(resolveApiBaseUrl()).toBe('');
  });

  it('uses an injected absolute URL when one is provided', () => {
    globalThis.window = { __LEADLOCK_API_URL__: 'https://api.example.com/' } as LeadlockWindow;
    expect(resolveApiBaseUrl()).toBe('https://api.example.com');
  });
});
