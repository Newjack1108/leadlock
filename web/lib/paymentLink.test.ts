import { describe, expect, it } from 'vitest';
import {
  PAYPAL_PAYMENT_LINK,
  isAllowedPaymentLink,
  isPayPalPaymentLink,
  messageContainsOnlyPaymentLink,
} from '@/lib/paymentLink';

const trustLink = 'https://paybylink.trustpayments.com/order-123';

describe('payment link allowlist', () => {
  it('accepts the company PayPal page and a Trust card link', () => {
    expect(isPayPalPaymentLink(PAYPAL_PAYMENT_LINK)).toBe(true);
    expect(isAllowedPaymentLink(PAYPAL_PAYMENT_LINK)).toBe(true);
    expect(isAllowedPaymentLink(trustLink)).toBe(true);
    expect(isPayPalPaymentLink(trustLink)).toBe(false);
  });

  it('rejects other addresses', () => {
    expect(isAllowedPaymentLink('https://evil.example/pay')).toBe(false);
    expect(isAllowedPaymentLink('https://www.paypal.com/ncp/payment/OTHER')).toBe(false);
    expect(isAllowedPaymentLink('https://paybylink.trustpayments.com')).toBe(false);
    expect(isAllowedPaymentLink('https://paybylink.trustpayments.com.evil.com/order-123')).toBe(false);
    expect(isAllowedPaymentLink('http://paybylink.trustpayments.com/order-123')).toBe(false);
  });

  it('allows a message that contains only the link being sent', () => {
    expect(messageContainsOnlyPaymentLink(`Pay here: ${trustLink}`, trustLink)).toBe(true);
    expect(
      messageContainsOnlyPaymentLink(`Pay ${trustLink} or https://evil.example/pay`, trustLink)
    ).toBe(false);
    expect(messageContainsOnlyPaymentLink('Please call the office', trustLink)).toBe(false);
  });
});
