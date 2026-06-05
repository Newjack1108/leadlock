'use client';

import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import api, { getApiErrorDetail, getOrder, sendOrderReviewRequest } from '@/lib/api';
import { Customer } from '@/lib/types';
import { toast } from 'sonner';
import { Mail, MessageSquare, Star } from 'lucide-react';

interface SendReviewRequestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orderId: number;
  orderNumber?: string;
  customer?: Customer | null;
  isReturningCustomer?: boolean;
  freeGiftTitle?: string | null;
  returningGiftEnabled?: boolean;
  onSuccess?: () => void;
}

export default function SendReviewRequestDialog({
  open,
  onOpenChange,
  orderId,
  orderNumber,
  customer: customerProp,
  isReturningCustomer: isReturningCustomerProp,
  freeGiftTitle: freeGiftTitleProp,
  returningGiftEnabled: returningGiftEnabledProp,
  onSuccess,
}: SendReviewRequestDialogProps) {
  const [channel, setChannel] = useState<'email' | 'sms'>('sms');
  const [loading, setLoading] = useState(false);
  const [loadingCustomer, setLoadingCustomer] = useState(false);
  const [customer, setCustomer] = useState<Customer | null>(customerProp ?? null);
  const [resolvedOrderNumber, setResolvedOrderNumber] = useState(orderNumber ?? '');
  const [isReturningCustomer, setIsReturningCustomer] = useState(isReturningCustomerProp ?? false);
  const [freeGiftTitle, setFreeGiftTitle] = useState(freeGiftTitleProp ?? 'free gift');
  const [returningGiftEnabled, setReturningGiftEnabled] = useState(returningGiftEnabledProp ?? true);

  useEffect(() => {
    if (!open) return;

    setChannel(customerProp?.phone?.trim() ? 'sms' : 'email');
    setCustomer(customerProp ?? null);
    setResolvedOrderNumber(orderNumber ?? '');
    setIsReturningCustomer(isReturningCustomerProp ?? false);
    setFreeGiftTitle(freeGiftTitleProp ?? 'free gift');
    setReturningGiftEnabled(returningGiftEnabledProp ?? true);

    const load = async () => {
      setLoadingCustomer(true);
      try {
        const [order, settingsResponse] = await Promise.all([
          getOrder(orderId),
          api.get('/api/settings/company').catch(() => null),
        ]);
        setResolvedOrderNumber(order.order_number ?? '');
        if (isReturningCustomerProp === undefined) {
          setIsReturningCustomer(order.is_returning_customer_for_review ?? false);
        }
        if (settingsResponse?.data) {
          const settings = settingsResponse.data as {
            review_returning_customer_enabled?: boolean;
            review_free_gift_title?: string | null;
          };
          if (returningGiftEnabledProp === undefined) {
            setReturningGiftEnabled(settings.review_returning_customer_enabled ?? true);
          }
          if (freeGiftTitleProp === undefined) {
            setFreeGiftTitle(settings.review_free_gift_title || 'free gift');
          }
        }
        if (customerProp) return;
        if (order.customer_id) {
          const response = await api.get(`/api/customers/${order.customer_id}`);
          const loaded = response.data as Customer;
          setCustomer(loaded);
          setChannel(loaded.phone?.trim() ? 'sms' : 'email');
        }
      } catch {
        toast.error('Failed to load customer details');
        setCustomer(null);
      } finally {
        setLoadingCustomer(false);
      }
    };
    void load();
  }, [
    open,
    orderId,
    orderNumber,
    customerProp,
    isReturningCustomerProp,
    freeGiftTitleProp,
    returningGiftEnabledProp,
  ]);

  const recipientEmail = (customer?.email ?? '').trim();
  const recipientPhone = (customer?.phone ?? '').trim();
  const canSend =
    channel === 'email' ? !!recipientEmail && !customer?.wrong_email_address : !!recipientPhone;
  const useReturningTemplate =
    isReturningCustomer && returningGiftEnabled;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSend) {
      toast.error(
        channel === 'email'
          ? 'Customer needs a valid email address'
          : 'Customer needs a phone number for SMS'
      );
      return;
    }

    setLoading(true);
    try {
      const result = await sendOrderReviewRequest(orderId, {
        channel,
        use_returning_template: useReturningTemplate ? true : false,
      });
      toast.success(result.message || `Review request sent by ${channel}`);
      onOpenChange(false);
      onSuccess?.();
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to send review request');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Star className="h-5 w-5 text-teal-600" />
            Send review request
          </DialogTitle>
          <DialogDescription>
            {useReturningTemplate ? (
              <>
                This returning customer will receive the welcome-back message promoting{' '}
                <strong>2 reviews for a {freeGiftTitle}</strong>
                {resolvedOrderNumber ? ` for order ${resolvedOrderNumber}` : ''}.
              </>
            ) : (
              <>
                Send post-install review links to the customer
                {resolvedOrderNumber ? ` for order ${resolvedOrderNumber}` : ''}.
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2">
          <Button
            type="button"
            variant={channel === 'email' ? 'default' : 'outline'}
            className="flex-1"
            onClick={() => setChannel('email')}
            disabled={loading || loadingCustomer}
          >
            <Mail className="h-4 w-4 mr-2" />
            Email
          </Button>
          <Button
            type="button"
            variant={channel === 'sms' ? 'default' : 'outline'}
            className="flex-1"
            onClick={() => setChannel('sms')}
            disabled={loading || loadingCustomer}
          >
            <MessageSquare className="h-4 w-4 mr-2" />
            SMS
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {channel === 'email' ? (
            <div className="space-y-2">
              <Label htmlFor="review_to_email">Recipient email</Label>
              <Input
                id="review_to_email"
                type="email"
                value={recipientEmail}
                readOnly
                placeholder={loadingCustomer ? 'Loading…' : 'No email on file'}
                className="bg-muted"
              />
              {customer?.wrong_email_address ? (
                <p className="text-xs text-destructive">Marked as wrong email address on customer record.</p>
              ) : null}
            </div>
          ) : (
            <div className="space-y-2">
              <Label htmlFor="review_to_phone">Recipient phone</Label>
              <Input
                id="review_to_phone"
                type="tel"
                value={recipientPhone}
                readOnly
                placeholder={loadingCustomer ? 'Loading…' : 'No phone on file'}
                className="bg-muted"
              />
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading || loadingCustomer || !canSend}>
              {loading ? 'Sending…' : `Send by ${channel}`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
