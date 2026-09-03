/** Shared payment-flag display helpers (matches api/app/order_payment.py). */

export type OrderPaymentFlags = {
  deposit_paid?: boolean | null;
  balance_paid?: boolean | null;
  paid_in_full?: boolean | null;
};

export function isDepositPaid(order: OrderPaymentFlags | null | undefined): boolean {
  if (!order) return false;
  return !!(order.deposit_paid || order.paid_in_full || order.balance_paid);
}

export function isPaidInFull(order: OrderPaymentFlags | null | undefined): boolean {
  if (!order) return false;
  return !!(order.paid_in_full || order.balance_paid);
}
