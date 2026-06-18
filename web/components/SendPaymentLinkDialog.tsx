'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  sendOrderPaymentLink,
  sendQuotePaymentLink,
  getEmailTemplates,
  getSmsTemplates,
  getApiErrorDetail,
} from '@/lib/api';
import { Customer, Order, Quote, EmailTemplate, SmsTemplate } from '@/lib/types';
import { toast } from 'sonner';
import { Mail, MessageSquare, CreditCard } from 'lucide-react';

type SendPaymentLinkDialogProps =
  | {
      open: boolean;
      onOpenChange: (open: boolean) => void;
      order: Order;
      quote?: undefined;
      customer: Customer;
      onSuccess?: () => void;
    }
  | {
      open: boolean;
      onOpenChange: (open: boolean) => void;
      quote: Quote;
      order?: undefined;
      customer: Customer;
      onSuccess?: () => void;
    };

export default function SendPaymentLinkDialog(props: SendPaymentLinkDialogProps) {
  const { open, onOpenChange, customer, onSuccess } = props;
  const isQuote = props.quote != null;
  const documentNumber = isQuote ? props.quote.quote_number : props.order.order_number;
  const paymentLinkUrl = isQuote
    ? props.quote.payment_link_url
    : props.order.payment_link_url;

  const [channel, setChannel] = useState<'email' | 'sms'>('email');
  const [loading, setLoading] = useState(false);
  const [paymentUrl, setPaymentUrl] = useState('');
  const [saveLink, setSaveLink] = useState(true);
  const [toEmail, setToEmail] = useState('');
  const [toPhone, setToPhone] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [emailTemplates, setEmailTemplates] = useState<EmailTemplate[]>([]);
  const [smsTemplates, setSmsTemplates] = useState<SmsTemplate[]>([]);
  const [selectedEmailTemplateId, setSelectedEmailTemplateId] = useState<number | undefined>(undefined);
  const [selectedSmsTemplateId, setSelectedSmsTemplateId] = useState<number | undefined>(undefined);
  const [loadingTemplates, setLoadingTemplates] = useState(false);

  useEffect(() => {
    if (!open) return;
    setChannel('email');
    setPaymentUrl(paymentLinkUrl?.trim() || '');
    setSaveLink(true);
    setToEmail(customer.email || '');
    setToPhone(customer.phone || '');
    setSubject('');
    setBody('');
    setSelectedEmailTemplateId(undefined);
    setSelectedSmsTemplateId(undefined);

    const loadTemplates = async () => {
      setLoadingTemplates(true);
      try {
        const [emails, sms] = await Promise.all([getEmailTemplates(), getSmsTemplates()]);
        setEmailTemplates(emails);
        setSmsTemplates(sms);
      } catch {
        toast.error('Failed to load templates');
        setEmailTemplates([]);
        setSmsTemplates([]);
      } finally {
        setLoadingTemplates(false);
      }
    };
    void loadTemplates();
  }, [open, paymentLinkUrl, customer.email, customer.phone]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const url = paymentUrl.trim();
    if (!url) {
      toast.error('Payment URL is required');
      return;
    }
    if (!url.startsWith('https://')) {
      toast.error('Payment URL must start with https://');
      return;
    }
    if (channel === 'email' && !toEmail.trim()) {
      toast.error('Recipient email is required');
      return;
    }

    setLoading(true);
    try {
      const payload = {
        channel,
        payment_url: url,
        to_email: channel === 'email' ? toEmail.trim() : undefined,
        to_phone: channel === 'sms' ? toPhone.trim() || undefined : undefined,
        subject: channel === 'email' ? subject.trim() || undefined : undefined,
        body: body.trim() || undefined,
        template_id: channel === 'email' ? selectedEmailTemplateId : selectedSmsTemplateId,
      };

      if (isQuote) {
        await sendQuotePaymentLink(props.quote.id, {
          ...payload,
          save_link_on_quote: saveLink,
        });
      } else {
        await sendOrderPaymentLink(props.order.id, {
          ...payload,
          save_link_on_order: saveLink,
        });
      }

      toast.success(`Payment link sent by ${channel}`);
      onOpenChange(false);
      onSuccess?.();
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to send payment link');
    } finally {
      setLoading(false);
    }
  };

  const documentLabel = isQuote ? 'quote' : 'order';
  const rememberLabel = isQuote ? 'Remember link on this quote' : 'Remember link on this order';
  const numberVar = isQuote ? '{{ quote.quote_number }}' : '{{ order.order_number }}';
  const defaultSmsPlaceholder = isQuote
    ? `Leave blank to send: Pay deposit for quote ${documentNumber}: [link]`
    : `Leave blank to send: Pay online for order ${documentNumber}: [link]`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CreditCard className="h-5 w-5" />
            Send payment link
          </DialogTitle>
          <DialogDescription>
            Paste the pay-by-link URL from your payment provider, then send it to the customer for{' '}
            {documentLabel} {documentNumber}.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2 mb-2">
          <Button
            type="button"
            variant={channel === 'email' ? 'default' : 'outline'}
            className="flex-1"
            onClick={() => setChannel('email')}
          >
            <Mail className="h-4 w-4 mr-2" />
            Email
          </Button>
          <Button
            type="button"
            variant={channel === 'sms' ? 'default' : 'outline'}
            className="flex-1"
            onClick={() => setChannel('sms')}
          >
            <MessageSquare className="h-4 w-4 mr-2" />
            SMS
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="payment_url">
              Payment URL <span className="text-destructive">*</span>
            </Label>
            <Input
              id="payment_url"
              type="url"
              value={paymentUrl}
              onChange={(e) => setPaymentUrl(e.target.value)}
              placeholder="https://..."
              className="font-mono text-sm"
              required
            />
          </div>

          <div className="flex items-center space-x-2">
            <input
              type="checkbox"
              id="save_payment_link"
              checked={saveLink}
              onChange={(e) => setSaveLink(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300"
            />
            <Label htmlFor="save_payment_link" className="font-normal cursor-pointer">
              {rememberLabel}
            </Label>
          </div>

          {channel === 'email' ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="email_template">Email template (optional)</Label>
                <Select
                  value={selectedEmailTemplateId !== undefined ? String(selectedEmailTemplateId) : 'none'}
                  onValueChange={(v) =>
                    setSelectedEmailTemplateId(v === 'none' ? undefined : parseInt(v, 10))
                  }
                  disabled={loadingTemplates}
                >
                  <SelectTrigger id="email_template">
                    <SelectValue placeholder="Default message" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Default message</SelectItem>
                    {emailTemplates.map((t) => (
                      <SelectItem key={t.id} value={String(t.id)}>
                        {t.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {!loadingTemplates && emailTemplates.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    Create templates in{' '}
                    <Link href="/settings/email-templates" className="text-primary underline hover:no-underline">
                      Email Templates
                    </Link>
                    . Use <code className="text-xs">{'{{ payment_link }}'}</code> and{' '}
                    <code className="text-xs">{numberVar}</code>.
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="to_email">
                  To email <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="to_email"
                  type="email"
                  value={toEmail}
                  onChange={(e) => setToEmail(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email_subject">Subject (optional)</Label>
                <Input
                  id="email_subject"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder={`Payment for ${documentLabel} ${documentNumber}`}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email_body">Message (optional)</Label>
                <Textarea
                  id="email_body"
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  placeholder="Leave blank for the default email with the payment link."
                  rows={4}
                />
              </div>
            </>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="sms_template">SMS template (optional)</Label>
                <Select
                  value={selectedSmsTemplateId !== undefined ? String(selectedSmsTemplateId) : 'none'}
                  onValueChange={(v) =>
                    setSelectedSmsTemplateId(v === 'none' ? undefined : parseInt(v, 10))
                  }
                  disabled={loadingTemplates}
                >
                  <SelectTrigger id="sms_template">
                    <SelectValue placeholder="Default message" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Default message</SelectItem>
                    {smsTemplates.map((t) => (
                      <SelectItem key={t.id} value={String(t.id)}>
                        {t.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {!loadingTemplates && smsTemplates.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    Create templates in{' '}
                    <Link href="/settings/sms-templates" className="text-primary underline hover:no-underline">
                      SMS Templates
                    </Link>
                    . Use <code className="text-xs">{'{{ payment_link }}'}</code>
                    {isQuote && (
                      <>
                        {' '}
                        and <code className="text-xs">{'{{ quote.deposit_amount }}'}</code>
                      </>
                    )}
                    .
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="sms_phone">Mobile number</Label>
                <Input
                  id="sms_phone"
                  type="tel"
                  value={toPhone}
                  onChange={(e) => setToPhone(e.target.value)}
                  placeholder="Customer mobile number"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="sms_body">Message (optional)</Label>
                <Textarea
                  id="sms_body"
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  placeholder={defaultSmsPlaceholder}
                  rows={4}
                />
              </div>
            </>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? 'Sending…' : `Send payment link by ${channel}`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
