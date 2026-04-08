'use client';

import { useState, useEffect, useMemo } from 'react';
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
  sendQuoteEmail,
  previewQuotePdf,
  getQuoteTemplates,
  postQuoteShareLink,
  sendQuoteSms,
  getQuote,
} from '@/lib/api';
import { QuoteEmailSendRequest, QuoteEmailSendResponse, Customer, QuoteTemplate as QuoteTemplateType } from '@/lib/types';
import { toast } from 'sonner';
import { Eye, ExternalLink, Copy, Mail, MessageSquare } from 'lucide-react';

interface SendQuoteEmailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  quoteId: number;
  customer: Customer;
  onSuccess?: () => void;
  variant?: 'quote' | 'order';
}

type SuccessState =
  | { type: 'email'; data: QuoteEmailSendResponse }
  | { type: 'sms'; view_url: string };

function preferredQuoteTemplateName(variant: 'quote' | 'order'): string {
  return variant === 'order' ? 'Order Confirmation' : 'First Quote';
}

export default function SendQuoteEmailDialog({
  open,
  onOpenChange,
  quoteId,
  customer,
  onSuccess,
  variant = 'quote',
}: SendQuoteEmailDialogProps) {
  const docLabel = variant === 'order' ? 'order' : 'quote';
  const [channel, setChannel] = useState<'email' | 'sms'>('email');
  const [loading, setLoading] = useState(false);
  const [copyLinkLoading, setCopyLinkLoading] = useState(false);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [successState, setSuccessState] = useState<SuccessState | null>(null);
  const [templates, setTemplates] = useState<QuoteTemplateType[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | undefined>(undefined);
  const [formData, setFormData] = useState<Omit<QuoteEmailSendRequest, 'template_id'>>({
    to_email: customer.email || '',
    cc: '',
    bcc: '',
    custom_message: '',
    include_available_extras: false,
  });
  const [smsPhone, setSmsPhone] = useState(customer.phone || '');
  const [smsBody, setSmsBody] = useState('');
  const [emailAttachments, setEmailAttachments] = useState<File[]>([]);

  useEffect(() => {
    if (open) {
      setSuccessState(null);
      setChannel('email');
      setFormData({
        to_email: customer.email || '',
        cc: '',
        bcc: '',
        custom_message: '',
        include_available_extras: false,
      });
      setSmsPhone(customer.phone || '');
      setSmsBody('');
      setEmailAttachments([]);
      setSelectedTemplateId(undefined);
      const fetchTemplates = async () => {
        setLoadingTemplates(true);
        try {
          const data = await getQuoteTemplates();
          setTemplates(data);
          const preferred = preferredQuoteTemplateName(variant);
          const match = data.find((t: QuoteTemplateType) => t.name === preferred);
          setSelectedTemplateId(match?.id);
        } catch (error) {
          setTemplates([]);
          setSelectedTemplateId(undefined);
          toast.error('Failed to load quote templates');
          console.error('Quote templates fetch error:', error);
        } finally {
          setLoadingTemplates(false);
        }
      };
      fetchTemplates();
      (async () => {
        try {
          const q = await getQuote(quoteId);
          setFormData((prev) => ({
            ...prev,
            include_available_extras: q.include_available_optional_extras ?? false,
          }));
        } catch {
          // keep default false
        }
      })();
    }
  }, [open, customer, variant, quoteId]);

  const templateLibraryAttachments = useMemo(() => {
    const t = templates.find((x) => x.id === selectedTemplateId);
    if (!t?.attached_documents?.length) return [];
    return [...t.attached_documents].sort((a, b) => a.sort_order - b.sort_order);
  }, [templates, selectedTemplateId]);

  const handleEmailAttachmentChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files;
    if (!list?.length) return;
    setEmailAttachments((prev) => [...prev, ...Array.from(list)]);
    e.target.value = '';
  };

  const removeEmailAttachment = (index: number) => {
    setEmailAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const handlePreview = async () => {
    try {
      await previewQuotePdf(quoteId);
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to download PDF';
      toast.error(errorMessage);
      console.error('Quote PDF download error:', error);
    }
  };

  const handleCopyShareLink = async () => {
    setCopyLinkLoading(true);
    try {
      const { view_url } = await postQuoteShareLink(quoteId, {
        include_available_extras: formData.include_available_extras ?? false,
      });
      await navigator.clipboard.writeText(view_url);
      toast.success('Customer view link copied to clipboard');
    } catch (error: any) {
      const detail = error.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : 'Failed to get share link';
      toast.error(msg);
    } finally {
      setCopyLinkLoading(false);
    }
  };

  const handleSubmitEmail = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.to_email) {
      toast.error('Recipient email is required');
      return;
    }

    if (selectedTemplateId === undefined) {
      toast.error('Please select an email template');
      return;
    }

    setLoading(true);
    try {
      const response = await sendQuoteEmail(
        quoteId,
        {
          ...formData,
          template_id: selectedTemplateId,
          include_available_extras: formData.include_available_extras ?? false,
        },
        emailAttachments.length ? emailAttachments : undefined
      );
      toast.success(`${docLabel.charAt(0).toUpperCase() + docLabel.slice(1)} email sent successfully`);
      if (response.view_url) {
        setSuccessState({ type: 'email', data: response });
      } else {
        onOpenChange(false);
        setTimeout(() => onSuccess?.(), 100);
      }
    } catch (error: any) {
      const detail = error.response?.data?.detail;
      let errorMessage = `Failed to send ${docLabel} email`;
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        errorMessage = detail.map((e: { msg?: string }) => e.msg || JSON.stringify(e)).join('; ');
      } else if (error.message) {
        errorMessage = error.message;
      }
      toast.error(errorMessage);
      console.error('Quote email send error:', error.response?.data ?? error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitSms = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await sendQuoteSms(quoteId, {
        to_phone: smsPhone.trim() || undefined,
        body: smsBody.trim() || undefined,
        include_available_extras: formData.include_available_extras ?? false,
      });
      toast.success('SMS sent successfully');
      setSuccessState({ type: 'sms', view_url: response.view_url });
    } catch (error: any) {
      const detail = error.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : 'Failed to send SMS';
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = (open: boolean) => {
    if (!open) setSuccessState(null);
    onOpenChange(open);
  };

  const successViewUrl =
    successState?.type === 'email' ? successState.data.view_url : successState?.type === 'sms' ? successState.view_url : null;

  const handleCopyLink = () => {
    if (successViewUrl) {
      navigator.clipboard.writeText(successViewUrl);
      toast.success('Link copied to clipboard');
    }
  };

  if (successViewUrl && successState) {
    const testMode = successState.type === 'email' ? successState.data.test_mode : undefined;
    return (
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {successState.type === 'email'
                ? `${docLabel.charAt(0).toUpperCase() + docLabel.slice(1)} email sent`
                : 'SMS sent'}
            </DialogTitle>
            <DialogDescription>
              {successState.type === 'email' && testMode
                ? 'Test mode: no email was sent. Use the link below to test the customer quote view and open tracking.'
                : successState.type === 'email'
                  ? 'Use the link below to open the customer view (e.g. for testing).'
                  : 'The customer view link was included in the SMS. You can copy it below if needed.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex flex-col gap-2">
              <Label className="text-sm font-medium">Customer view link</Label>
              <div className="flex gap-2">
                <Input readOnly value={successViewUrl} className="font-mono text-sm" />
                <Button type="button" variant="outline" size="icon" onClick={handleCopyLink} title="Copy link">
                  <Copy className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  asChild
                  className="border-green-600 text-green-700 hover:bg-green-50 hover:text-green-800 hover:border-green-700"
                >
                  <a href={successViewUrl} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-4 w-4 mr-2" />
                    Open
                  </a>
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => {
                onSuccess?.();
                handleClose(false);
              }}
            >
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            Send {docLabel.charAt(0).toUpperCase() + docLabel.slice(1)} by email or SMS
          </DialogTitle>
          <DialogDescription>
            Send a link to the online {docLabel} view (customer can print or download PDF from there). Choose email or SMS.
            Long SMS messages may use multiple segments.
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

        <div className="flex items-center space-x-2 py-2 border-b border-border">
          <input
            type="checkbox"
            id="include_extras_shared"
            checked={formData.include_available_extras ?? false}
            onChange={(e) =>
              setFormData({ ...formData, include_available_extras: e.target.checked })
            }
            className="h-4 w-4 rounded border-gray-300"
          />
          <Label htmlFor="include_extras_shared" className="font-normal cursor-pointer">
            Show available optional extras in the online view
          </Label>
        </div>

        {channel === 'email' ? (
          <form onSubmit={handleSubmitEmail} className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={handleCopyShareLink}
                disabled={loading || copyLinkLoading}
              >
                <Copy className="h-4 w-4 mr-2" />
                {copyLinkLoading ? 'Getting link…' : 'Copy customer view link'}
              </Button>
              <p className="text-xs text-muted-foreground w-full">
                Get the link without sending email (e.g. to paste into WhatsApp). Uses the optional extras setting above.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="template">
                Email template <span className="text-destructive">*</span>
              </Label>
              <Select
                value={selectedTemplateId !== undefined ? String(selectedTemplateId) : 'none'}
                onValueChange={(value) => setSelectedTemplateId(value === 'none' ? undefined : parseInt(value, 10))}
                disabled={loadingTemplates}
              >
                <SelectTrigger id="template">
                  <SelectValue placeholder="Select a template" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Select a template</SelectItem>
                  {templates.map((template) => (
                    <SelectItem key={template.id} value={template.id.toString()}>
                      {template.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {loadingTemplates && (
                <p className="text-xs text-muted-foreground">Loading templates...</p>
              )}
              {!loadingTemplates && templates.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No custom templates yet. Create templates in{' '}
                  <Link href="/settings/quote-templates" className="text-primary underline hover:no-underline">
                    Quote Templates settings
                  </Link>{' '}
                  to customize quote emails.
                </p>
              )}
              {templateLibraryAttachments.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  This template also attaches from the library:{' '}
                  {templateLibraryAttachments.map((d) => d.name).join(', ')}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="to_email">
                To Email <span className="text-destructive">*</span>
              </Label>
              <Input
                id="to_email"
                type="email"
                value={formData.to_email}
                onChange={(e) => setFormData({ ...formData, to_email: e.target.value })}
                required
                placeholder="customer@example.com"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="cc">CC (Optional)</Label>
              <Input
                id="cc"
                type="text"
                value={formData.cc || ''}
                onChange={(e) => setFormData({ ...formData, cc: e.target.value })}
                placeholder="cc1@example.com, cc2@example.com"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="bcc">BCC (Optional)</Label>
              <Input
                id="bcc"
                type="text"
                value={formData.bcc || ''}
                onChange={(e) => setFormData({ ...formData, bcc: e.target.value })}
                placeholder="bcc@example.com"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="custom_message">Custom Message (Optional)</Label>
              <Textarea
                id="custom_message"
                value={formData.custom_message || ''}
                onChange={(e) => setFormData({ ...formData, custom_message: e.target.value })}
                placeholder="Add a custom message that will be appended to the email template..."
                rows={4}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="quote_email_attachments">Attachments (optional)</Label>
              <Input
                id="quote_email_attachments"
                type="file"
                multiple
                onChange={handleEmailAttachmentChange}
                disabled={loading}
                className="cursor-pointer"
              />
              {emailAttachments.length > 0 && (
                <ul className="text-sm space-y-1">
                  {emailAttachments.map((f, i) => (
                    <li key={`${f.name}-${i}-${f.size}`} className="flex items-center justify-between gap-2">
                      <span className="truncate text-muted-foreground">{f.name}</span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="shrink-0"
                        onClick={() => removeEmailAttachment(i)}
                      >
                        Remove
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-muted-foreground">
                Up to 10MB per file, 25MB total (same limits as compose email).
              </p>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleClose(false)} disabled={loading}>
                Cancel
              </Button>
              <Button type="button" variant="outline" onClick={handlePreview} disabled={loading}>
                <Eye className="h-4 w-4 mr-2" />
                Download PDF
              </Button>
              <Button
                type="submit"
                disabled={
                  loading ||
                  !formData.to_email ||
                  loadingTemplates ||
                  selectedTemplateId === undefined
                }
              >
                {loading ? 'Sending…' : `Send ${docLabel.charAt(0).toUpperCase() + docLabel.slice(1)} email`}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <form onSubmit={handleSubmitSms} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="sms_phone">Mobile number</Label>
              <Input
                id="sms_phone"
                type="tel"
                value={smsPhone}
                onChange={(e) => setSmsPhone(e.target.value)}
                placeholder="Customer mobile number"
              />
              <p className="text-xs text-muted-foreground">Defaults to the customer profile phone. Requires Twilio on the server.</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="sms_body">Message (optional)</Label>
              <Textarea
                id="sms_body"
                value={smsBody}
                onChange={(e) => setSmsBody(e.target.value)}
                placeholder="Leave blank to send a short default message including the view link."
                rows={4}
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleClose(false)} disabled={loading}>
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? 'Sending…' : `Send ${docLabel.charAt(0).toUpperCase() + docLabel.slice(1)} by SMS`}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
