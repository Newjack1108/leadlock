export function isMarketingRole(role: string | null | undefined): boolean {
  return role === 'MARKETING';
}

export function isDealerRole(role: string | null | undefined): boolean {
  return role === 'DEALER_ADMIN' || role === 'DEALER_USER';
}

export function isSalesStaffRole(role: string | null | undefined): boolean {
  return !isDealerRole(role) && !isMarketingRole(role);
}

export function canManageFacebookAdverts(role: string | null | undefined): boolean {
  return role === 'DIRECTOR' || role === 'MARKETING';
}
