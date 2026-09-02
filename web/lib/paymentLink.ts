/** Company PayPal No Code Payments page. Used as the default pay-by-link URL. */
export const PAYPAL_PAYMENT_LINK = 'https://www.paypal.com/ncp/payment/HM6Y7ZSG5SYQ6';

export function isPayPalPaymentLink(url: string | null | undefined): boolean {
  return (url || '').trim() === PAYPAL_PAYMENT_LINK;
}
