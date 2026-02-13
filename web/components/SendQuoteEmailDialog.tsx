'use client';

import { useState, useEffect } from 'react';
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
import { sendQuoteEmail, previewQuotePdf } from '@/lib/api';
import { QuoteEmailSendRequest, QuoteEmailSendResponse, Customer } from '@/lib/types';
import { toast } from 'sonner';
import { Eye, ExternalLink, Copy } from 'lucide-react';

interface QuoteTemplate {
  id: number;
  name: string;
  description?: string;
  email_subject_template: string;
  email_body_template: string;
}

interface SendQuoteEmailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  quoteId: number;
  customer: Customer;
  onSuccess?: () => void;
}

export default function SendQuoteEmailDialog({
  open,
  onOpenChange,
  quoteId,
  customer,
  onSuccess,
}: SendQuoteEmailDialogProps) {
  const [loading, setLoading] = useState(false);
  const [successResponse, setSuccessResponse] = useState<QuoteEmailSendResponse | null>(null);
  const [templates, setTemplates] = useState<QuoteTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | undefined>(undefined);
  const [formData, setFormData] = useState<QuoteEmailSendRequest>({
    to_email: customer.email || '',
    cc: '',
    bcc: '',
    custom_message: '',
  });

  // Reset form and success state when dialog opens
  useEffect(() => {
    if (open) {
      setSuccessResponse(null);
      setFormData({
        to_email: customer.email || '',
        cc: '',
        bcc: '',
        custom_message: '',
      });
      setSelectedTemplateId(undefined);
      setTemplates([]);
    }
  }, [open, customer]);

  const handlePreview = async () => {
    try {
      await previewQuotePdf(quoteId);
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to download PDF';
      toast.error(errorMessage);
      console.error('Quote PDF download error:', error);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.to_email) {
      toast.error('Recipient email is required');
      return;
    }

    setLoading(true);
    try {
      const response = await sendQuoteEmail(quoteId, {
        ...formData,
        template_id: selectedTemplateId,
      });
      setLoading(false);
      toast.success('Quote email sent successfully');
      if (response.view_url) {
        setSuccessResponse(response);
      } else {
        onOpenChange(false);
        setTimeout(() => onSuccess?.(), 100);
      }
    } catch (error: any) {
      const detail = error.response?.data?.detail;
      let errorMessage = 'Failed to send quote email';
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        errorMessage = detail.map((e: { msg?: string }) => e.msg || JSON.stringify(e)).join('; ');
      } else if (error.message) {
        errorMessage = error.message;
      }
      toast.error(errorMessage);
      console.error('Quote email send error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = (open: boolean) => {
    if (!open) setSuccessResponse(null);
    onOpenChange(open);
  };

  const handleCopyLink = () => {
    if (successResponse?.view_url) {
      navigator.clipboard.writeText(successResponse.view_url);
      toast.success('Link copied to clipboard');
    }
  };

  if (successResponse?.view_url) {
    return (
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Quote email sent</DialogTitle>
            <DialogDescription>
              {successResponse.test_mode
                ? 'Test mode: no email was sent. Use the link below to test the customer quote view and open tracking.'
                : 'Use the link below to open the customer quote view (e.g. for testing).'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex flex-col gap-2">
              <Label className="text-sm font-medium">Customer view link</Label>
              <div className="flex gap-2">
                <Input readOnly value={successResponse.view_url} className="font-mono text-sm" />
                <Button type="button" variant="outline" size="icon" onClick={handleCopyLink} title="Copy link">
                  <Copy className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  asChild
                >
                  <a href={successResponse.view_url} target="_blank" rel="noopener noreferrer">
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
          <DialogTitle>Send Quote via Email</DialogTitle>
          <DialogDescription>
            Send this quote to the customer with a PDF attachment. Select a template or use the default.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="template">Email Template (Optional)</Label>
            <Select
              value={selectedTemplateId?.toString() || 'default'}
              onValueChange={(value) => setSelectedTemplateId(value === 'default' ? undefined : parseInt(value))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select template or use default" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="default">Default Template</SelectItem>
                {templates.map((template) => (
                  <SelectItem key={template.id} value={template.id.toString()}>
                    {template.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleClose(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={handlePreview}
              disabled={loading}
            >
              <Eye className="h-4 w-4 mr-2" />
              Download PDF
            </Button>
            <Button type="submit" disabled={loading || !formData.to_email}>
              {loading ? 'Sending...' : 'Send Quote Email'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
