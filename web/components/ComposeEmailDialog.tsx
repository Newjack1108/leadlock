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
import { sendEmail, getEmailTemplates, previewEmailTemplate } from '@/lib/api';
import { Customer, EmailTemplate } from '@/lib/types';
import { toast } from 'sonner';

interface ComposeEmailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customer: Customer;
  onSuccess?: () => void;
}

export default function ComposeEmailDialog({
  open,
  onOpenChange,
  customer,
  onSuccess,
}: ComposeEmailDialogProps) {
  const [loading, setLoading] = useState(false);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | undefined>(undefined);
  const [loadingTemplate, setLoadingTemplate] = useState(false);
  const [formData, setFormData] = useState({
    to_email: customer.email || '',
    cc: '',
    bcc: '',
    subject: '',
    body: '',
  });

  // Fetch templates when dialog opens
  useEffect(() => {
    if (open) {
      fetchTemplates();
      setFormData({
        to_email: customer.email || '',
        cc: '',
        bcc: '',
        subject: '',
        body: '',
      });
      setSelectedTemplateId(undefined);
    }
  }, [open, customer]);

  const fetchTemplates = async () => {
    try {
      const data = await getEmailTemplates();
      setTemplates(data);
    } catch (error: any) {
      console.error('Failed to load templates');
    }
  };

  const handleTemplateChange = async (templateId: string) => {
    if (templateId === 'none') {
      setSelectedTemplateId(undefined);
      setFormData({
        ...formData,
        subject: '',
        body: '',
      });
      return;
    }

    const id = parseInt(templateId);
    setSelectedTemplateId(id);
    setLoadingTemplate(true);

    try {
      // Preview template with current customer data
      const preview = await previewEmailTemplate(id, { customer_id: customer.id });
      setFormData({
        ...formData,
        subject: preview.subject,
        body: preview.body_html,
      });
    } catch (error: any) {
      toast.error('Failed to load template');
    } finally {
      setLoadingTemplate(false);
    }
  };

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email.trim());
  };

  const validateEmailList = (emails: string): boolean => {
    if (!emails.trim()) return true; // Empty is valid (optional field)
    const emailList = emails.split(',').map((e) => e.trim());
    return emailList.every((email) => validateEmail(email));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate required fields
    if (!formData.to_email) {
      toast.error('Recipient email is required');
      return;
    }

    if (!validateEmail(formData.to_email)) {
      toast.error('Please enter a valid recipient email address');
      return;
    }

    if (!formData.subject.trim()) {
      toast.error('Subject is required');
      return;
    }

    if (!formData.body.trim()) {
      toast.error('Email body is required');
      return;
    }

    // Validate CC and BCC if provided
    if (formData.cc && !validateEmailList(formData.cc)) {
      toast.error('Please enter valid email addresses for CC (comma-separated)');
      return;
    }

    if (formData.bcc && !validateEmailList(formData.bcc)) {
      toast.error('Please enter valid email addresses for BCC (comma-separated)');
      return;
    }

    setLoading(true);
    try {
      await sendEmail({
        customer_id: customer.id,
        to_email: formData.to_email,
        cc: formData.cc || undefined,
        bcc: formData.bcc || undefined,
        subject: formData.subject,
        body_html: formData.body,
        body_text: formData.body, // Use same content for plain text fallback
        template_id: selectedTemplateId,
      });

      toast.success('Email sent successfully');
      onOpenChange(false);
      onSuccess?.();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to send email');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Compose Email</DialogTitle>
          <DialogDescription>
            Send an email to {customer.name}. When they reply, it will create engagement proof to unlock quote creation.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="template">Email Template (Optional)</Label>
            <Select
              value={selectedTemplateId?.toString() || 'none'}
              onValueChange={handleTemplateChange}
              disabled={loadingTemplate}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select a template or start from scratch" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No Template (Start from scratch)</SelectItem>
                {templates.map((template) => (
                  <SelectItem key={template.id} value={template.id.toString()}>
                    {template.name} {template.is_default && '(Default)'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {loadingTemplate && (
              <p className="text-xs text-muted-foreground">Loading template...</p>
            )}
            <p className="text-xs text-muted-foreground">
              Available variables: {'{{ customer.name }}'}, {'{{ customer.email }}'}, {'{{ customer.phone }}'}, etc.
            </p>
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
              value={formData.cc}
              onChange={(e) => setFormData({ ...formData, cc: e.target.value })}
              placeholder="cc1@example.com, cc2@example.com"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="bcc">BCC (Optional)</Label>
            <Input
              id="bcc"
              type="text"
              value={formData.bcc}
              onChange={(e) => setFormData({ ...formData, bcc: e.target.value })}
              placeholder="bcc@example.com"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="subject">
              Subject <span className="text-destructive">*</span>
            </Label>
            <Input
              id="subject"
              type="text"
              value={formData.subject}
              onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
              required
              placeholder="Email subject"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="body">
              Message <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id="body"
              value={formData.body}
              onChange={(e) => setFormData({ ...formData, body: e.target.value })}
              required
              placeholder="Type your message here. HTML is supported."
              rows={10}
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              You can use HTML formatting in your message.
            </p>
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
            <Button type="submit" disabled={loading || !formData.to_email || !formData.subject || !formData.body}>
              {loading ? 'Sending...' : 'Send Email'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
