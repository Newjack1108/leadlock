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
import { sendQuoteEmail } from '@/lib/api';
import { QuoteEmailSendRequest, Customer } from '@/lib/types';
import { toast } from 'sonner';

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
  const [templates, setTemplates] = useState<QuoteTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | undefined>(undefined);
  const [formData, setFormData] = useState<QuoteEmailSendRequest>({
    to_email: customer.email || '',
    cc: '',
    bcc: '',
    custom_message: '',
  });

  // Load templates (you may need to create this API endpoint)
  useEffect(() => {
    if (open) {
      // Reset form when dialog opens
      setFormData({
        to_email: customer.email || '',
        cc: '',
        bcc: '',
        custom_message: '',
      });
      setSelectedTemplateId(undefined);
      
      // TODO: Fetch templates from API
      // For now, we'll use a default template option
      setTemplates([]);
    }
  }, [open, customer]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.to_email) {
      toast.error('Recipient email is required');
      return;
    }

    setLoading(true);
    try {
      await sendQuoteEmail(quoteId, {
        ...formData,
        template_id: selectedTemplateId,
      });
      
      toast.success('Quote email sent successfully');
      setLoading(false);
      onOpenChange(false);
      // Wrap onSuccess in try-catch to prevent errors from stalling the app
      setTimeout(() => {
        try {
          onSuccess?.();
        } catch (error) {
          console.error('Error in onSuccess callback:', error);
          // Don't let onSuccess errors break the UI
        }
      }, 100);
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || 'Failed to send quote email';
      toast.error(errorMessage);
      console.error('Quote email send error:', error);
    } finally {
      // Always reset loading state, even if there's an error
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              Cancel
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
