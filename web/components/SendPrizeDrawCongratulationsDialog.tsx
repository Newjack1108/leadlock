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
import api, { getApiErrorDetail, sendReviewPrizeDrawCongratulations } from '@/lib/api';
import { Customer, ReviewPrizeDrawWinner } from '@/lib/types';
import { toast } from 'sonner';
import { Gift, Mail, MessageSquare } from 'lucide-react';

interface SendPrizeDrawCongratulationsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  month: string;
  winner: ReviewPrizeDrawWinner;
  onSuccess?: () => void;
}

export default function SendPrizeDrawCongratulationsDialog({
  open,
  onOpenChange,
  month,
  winner,
  onSuccess,
}: SendPrizeDrawCongratulationsDialogProps) {
  const [channel, setChannel] = useState<'email' | 'sms'>('sms');
  const [loading, setLoading] = useState(false);
  const [loadingCustomer, setLoadingCustomer] = useState(false);
  const [customer, setCustomer] = useState<Customer | null>(null);

  useEffect(() => {
    if (!open) return;

    setChannel('sms');
    setCustomer(null);

    const load = async () => {
      setLoadingCustomer(true);
      try {
        const response = await api.get(`/api/customers/${winner.customer_id}`);
        const loaded = response.data as Customer;
        setCustomer(loaded);
        setChannel(loaded.phone?.trim() ? 'sms' : 'email');
      } catch {
        toast.error('Failed to load customer details');
        setCustomer(null);
      } finally {
        setLoadingCustomer(false);
      }
    };
    void load();
  }, [open, winner.customer_id]);

  const recipientEmail = (customer?.email ?? '').trim();
  const recipientPhone = (customer?.phone ?? '').trim();
  const canSend =
    channel === 'email' ? !!recipientEmail && !customer?.wrong_email_address : !!recipientPhone;
  const alreadySent = !!winner.congratulations_sent_at;

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

    if (alreadySent) {
      const confirmed = window.confirm(
        'Congratulations were already sent to this winner. Send again anyway?'
      );
      if (!confirmed) return;
    }

    setLoading(true);
    try {
      await sendReviewPrizeDrawCongratulations(month, {
        channel,
        force: alreadySent,
      });
      toast.success(`Congratulations sent by ${channel}`);
      onOpenChange(false);
      onSuccess?.();
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to send congratulations');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Gift className="h-5 w-5 text-amber-500" />
            Send congratulations
          </DialogTitle>
          <DialogDescription>
            Send a congratulations message to {winner.customer_name} for winning the {month} prize
            draw (order {winner.order_number}).
            {alreadySent ? (
              <>
                {' '}
                A message was already sent
                {winner.congratulations_channel
                  ? ` by ${winner.congratulations_channel.toLowerCase()}`
                  : ''}
                .
              </>
            ) : null}
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
              <Label htmlFor="congrats_to_email">Recipient email</Label>
              <Input
                id="congrats_to_email"
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
              <Label htmlFor="congrats_to_phone">Recipient phone</Label>
              <Input
                id="congrats_to_phone"
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
              {loading ? 'Sending…' : alreadySent ? `Resend by ${channel}` : `Send by ${channel}`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
