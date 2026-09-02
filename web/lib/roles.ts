export function isMarketingRole(role: string | null | undefined): boolean {
  return role === 'MARKETING';
}

export function isViewerRole(role: string | null | undefined): boolean {
  return role === 'VIEWER';
}

export function isDealerRole(role: string | null | undefined): boolean {
  return role === 'DEALER_ADMIN' || role === 'DEALER_USER';
}

export function isSalesStaffRole(role: string | null | undefined): boolean {
  return !isDealerRole(role) && !isMarketingRole(role);
}

/** True when the account may create/edit/delete/send (not VIEWER). */
export function canMutateAsRole(role: string | null | undefined): boolean {
  return Boolean(role) && !isViewerRole(role) && !isDealerRole(role);
}

export function canManageFacebookAdverts(role: string | null | undefined): boolean {
  return role === 'DIRECTOR' || role === 'MARKETING';
}
