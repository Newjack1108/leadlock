/** Staff shed agency sales: deposit defaults to 20% (commission). Otherwise 50%. */

export const STAFF_DEFAULT_DEPOSIT_RATE = 0.5;
export const STAFF_SHED_COMMISSION_DEPOSIT_RATE = 0.2;

export function isStaffShedCommissionSale(options: {
  leadType?: string | null;
  productCategories?: Array<string | null | undefined>;
  dealerId?: number | null;
}): boolean {
  if (options.dealerId != null) return false;
  if (options.leadType === 'SHEDS') return true;
  const cats = options.productCategories ?? [];
  return cats.some((c) => c === 'SHEDS');
}

export function staffDefaultDepositRate(options: {
  leadType?: string | null;
  productCategories?: Array<string | null | undefined>;
  dealerId?: number | null;
}): number {
  return isStaffShedCommissionSale(options)
    ? STAFF_SHED_COMMISSION_DEPOSIT_RATE
    : STAFF_DEFAULT_DEPOSIT_RATE;
}

export function defaultDepositLabel(rate: number): string {
  const pct = Math.round(rate * 100);
  if (rate === STAFF_SHED_COMMISSION_DEPOSIT_RATE) {
    return `${pct}% of total inc VAT — commission`;
  }
  return `${pct}% of total inc VAT`;
}
