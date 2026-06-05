'use client';

import { useEffect, useRef, useState } from 'react';
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
import { Textarea } from '@/components/ui/textarea';
import { sendSms } from '@/lib/api';
import { toast } from 'sonner';

interface ComposeSmsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerId: number;
  leadId?: number | null;
  toPhone: string;
  onSuccess?: () => void;
  initialBody?: string;
}

export default function ComposeSmsDialog({
  open,
  onOpenChange,
  customerId,
  leadId,
  toPhone,
  onSuccess,
  initialBody,
}: ComposeSmsDialogProps) {
  const [loading, setLoading] = useState(false);
  const [to, setTo] = useState(toPhone);
  const [body, setBody] = useState('');
  const wasOpenRef = useRef(false);

  useEffect(() => {
    if (!open) {
      wasOpenRef.current = false;
      return;
    }
    if (!wasOpenRef.current) {
      wasOpenRef.current = true;
      setTo(toPhone);
      setBody(initialBody ?? '');
      setLoading(false);
    }
  }, [open, toPhone, initialBody]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const phone = to.trim();
    const message = body.trim();
    if (!phone) {
      toast.error('Phone number is required');
      return;
    }
    if (!message) {
      toast.error('Message is required');
      return;
    }
    setLoading(true);
    try {
      await sendSms({
        customer_id: customerId,
        to_phone: phone,
        body: message,
        lead_id: leadId ?? undefined,
      });
      toast.success('SMS sent successfully');
      setLoading(false);
      onOpenChange(false);
      window.setTimeout(() => {
        try {
          onSuccess?.();
        } catch (error) {
          console.error('Error in onSuccess callback:', error);
        }
      }, 100);
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      toast.error(typeof detail === 'string' ? detail : 'Failed to send SMS');
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Compose SMS</DialogTitle>
          <DialogDescription>Review and edit the message before sending.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="compose-sms-to">To</Label>
            <Input
              id="compose-sms-to"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="Phone number"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="compose-sms-body">Message</Label>
            <Textarea
              id="compose-sms-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={6}
              placeholder="Type your message..."
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? 'Sending...' : 'Send SMS'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
