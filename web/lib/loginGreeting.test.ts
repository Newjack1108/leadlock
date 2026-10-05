import { describe, expect, it } from 'vitest';
import { postLoginPathForRole } from '@/lib/loginGreeting';

describe('postLoginPathForRole', () => {
  it('maps known roles to their home paths', () => {
    expect(postLoginPathForRole('CLOSER')).toBe('/closer-dashboard');
    expect(postLoginPathForRole('DEALER_ADMIN')).toBe('/dealer');
    expect(postLoginPathForRole('DEALER_USER')).toBe('/dealer');
    expect(postLoginPathForRole('MARKETING')).toBe('/dashboard');
  });

  it('defaults staff and unknown roles to leads', () => {
    expect(postLoginPathForRole('DIRECTOR')).toBe('/leads');
    expect(postLoginPathForRole('SALES_MANAGER')).toBe('/leads');
    expect(postLoginPathForRole(undefined)).toBe('/leads');
    expect(postLoginPathForRole(null)).toBe('/leads');
  });
});
