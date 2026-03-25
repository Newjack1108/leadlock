'use client';

import { useRef, useState, useEffect } from 'react';
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import EmailBodyEditor from '@/components/EmailBodyEditor';
import { sendEmail, getEmailTemplates, previewEmailTemplate, getUserEmailSettings, getSalesDocuments, downloadSalesDocument } from '@/lib/api';
import { htmlToPlainText, isHtmlEffectivelyEmpty } from '@/lib/htmlEmail';
import { Customer, EmailTemplate, SalesDocument } from '@/lib/types';
import { toast } from 'sonner';
import { Paperclip, X, FolderOpen } from 'lucide-react';

const MAX_TOTAL_ATTACHMENTS_BYTES = 20 * 1024 * 1024; // 20MB

interface ComposeEmailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customer: Customer;
  onSuccess?: () => void;
  initialAttachments?: File[];
  initialSubject?: string;
}

export default function ComposeEmailDialog({
  open,
  onOpenChange,
  customer,
  onSuccess,
  initialAttachments,
  initialSubject,
}: ComposeEmailDialogProps) {
  const [loading, setLoading] = useState(false);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | undefined>(undefined);
  const [loadingTemplate, setLoadingTemplate] = useState(false);
  const [signature, setSignature] = useState('');
  const [attachments, setAttachments] = useState<File[]>([]);
  const [libraryDialogOpen, setLibraryDialogOpen] = useState(false);
  const [libraryDocs, setLibraryDocs] = useState<SalesDocument[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [librarySelected, setLibrarySelected] = useState<Set<number>>(new Set());
  const [libraryAdding, setLibraryAdding] = useState(false);
  const [formData, setFormData] = useState({
    to_email: customer.email || '',
    cc: '',
    subject: '',
    body: '',
  });
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch templates and user signature when dialog opens
  useEffect(() => {
    if (open) {
      fetchTemplates();
      fetchUserSignature();
      setFormData({
        to_email: customer.email || '',
        cc: '',
        subject: initialSubject ?? '',
        body: '',
      });
      setAttachments(initialAttachments ?? []);
      setSelectedTemplateId(undefined);
      setLoading(false); // Reset loading state when dialog opens
    } else {
      // Reset all state when dialog closes
      setLoading(false);
      setSelectedTemplateId(undefined);
      setAttachments([]);
    }
  }, [open, customer, initialAttachments, initialSubject]);

  const fetchUserSignature = async () => {
    try {
      const emailSettings = await getUserEmailSettings();
      setSignature(emailSettings.email_signature || '');
    } catch (error) {
      // User not authenticated or error - use empty signature
      setSignature('');
    }
  };

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

  const handleAttachmentChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length) return;
    const newFiles = Array.from(files);
    const totalSize = [...attachments, ...newFiles].reduce((sum, f) => sum + f.size, 0);
    if (totalSize > MAX_TOTAL_ATTACHMENTS_BYTES) {
      toast.error('Total attachment size exceeds 20MB limit');
      return;
    }
    setAttachments((prev) => [...prev, ...newFiles]);
    e.target.value = '';
  };

  const removeAttachment = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const openLibraryDialog = async () => {
    setLibraryDialogOpen(true);
    setLibrarySelected(new Set());
    try {
      setLibraryLoading(true);
      const docs = await getSalesDocuments();
      setLibraryDocs(docs);
    } catch {
      toast.error('Failed to load documents');
      setLibraryDocs([]);
    } finally {
      setLibraryLoading(false);
    }
  };

  const toggleLibrarySelected = (id: number) => {
    setLibrarySelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const addFromLibrary = async () => {
    if (librarySelected.size === 0) {
      toast.error('Select at least one document');
      return;
    }
    const totalSize = attachments.reduce((sum, f) => sum + f.size, 0);
    const ids = Array.from(librarySelected);
    try {
      setLibraryAdding(true);
      const newFiles: File[] = [];
      for (const id of ids) {
        const doc = libraryDocs.find((d) => d.id === id);
        if (!doc) continue;
        const blob = await downloadSalesDocument(id);
        const totalWithNew = totalSize + newFiles.reduce((s, f) => s + f.size, 0) + blob.size;
        if (totalWithNew > MAX_TOTAL_ATTACHMENTS_BYTES) {
          toast.error('Total attachments would exceed 20MB limit');
          break;
        }
        const file = new File([blob], doc.filename, { type: doc.content_type || 'application/octet-stream' });
        newFiles.push(file);
      }
      setAttachments((prev) => [...prev, ...newFiles]);
      setLibraryDialogOpen(false);
    } catch {
      toast.error('Failed to add documents');
    } finally {
      setLibraryAdding(false);
    }
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

    if (isHtmlEffectivelyEmpty(formData.body)) {
      toast.error('Email body is required');
      return;
    }

    // Validate CC and BCC if provided
    if (formData.cc && !validateEmailList(formData.cc)) {
      toast.error('Please enter valid email addresses for CC (comma-separated)');
      return;
    }

    const totalAttachmentSize = attachments.reduce((sum, f) => sum + f.size, 0);
    if (totalAttachmentSize > MAX_TOTAL_ATTACHMENTS_BYTES) {
      toast.error('Total attachment size exceeds 20MB limit');
      return;
    }

    setLoading(true);
    try {
      // Signature and disclaimer are appended by the backend for all outgoing emails
      await sendEmail(
        {
          customer_id: customer.id,
          to_email: formData.to_email,
          cc: formData.cc || undefined,
          subject: formData.subject,
          body_html: formData.body,
          body_text: htmlToPlainText(formData.body),
          template_id: selectedTemplateId,
        },
        attachments.length > 0 ? attachments : undefined
      );

      toast.success('Email sent successfully');
      // Reset loading before closing
      setLoading(false);
      onOpenChange(false);
      // Call onSuccess after a short delay to ensure dialog is closed
      // Wrap in try-catch to prevent errors from stalling the app
      setTimeout(() => {
        try {
          onSuccess?.();
        } catch (error) {
          console.error('Error in onSuccess callback:', error);
          // Don't let onSuccess errors break the UI
        }
      }, 100);
    } catch (error: any) {
      const detail = error.response?.data?.detail;
      let errorMessage = 'Failed to send email';
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        errorMessage = detail.map((e: { msg?: string }) => e.msg || JSON.stringify(e)).join('; ');
      } else if (error.message) {
        errorMessage = error.message;
      }
      toast.error(errorMessage);
      console.error('Email send error:', error);
    } finally {
      // Always reset loading state, even if there's an error
      setLoading(false);
    }
  };

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-full w-[98vw] h-[90vh] max-h-[90vh] flex flex-col p-0">
        <DialogHeader className="px-6 pt-6 pb-4 border-b">
          <DialogTitle className="text-xl">New Message</DialogTitle>
          <DialogDescription>
            Send an email to {customer.name}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col flex-1 overflow-hidden">
          <div className="px-6 py-4 space-y-3 border-b flex-shrink-0">
            {/* Template Selector */}
            <div className="space-y-1">
              <Label htmlFor="template" className="text-xs text-muted-foreground">Template (Optional)</Label>
              <Select
                value={selectedTemplateId?.toString() || 'none'}
                onValueChange={handleTemplateChange}
                disabled={loadingTemplate}
              >
                <SelectTrigger className="h-8">
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
            </div>

            {/* To and CC */}
            <div className="grid grid-cols-12 gap-2 items-center">
              <Label htmlFor="to_email" className="text-xs text-muted-foreground col-span-1">
                To:
              </Label>
              <Input
                id="to_email"
                type="email"
                value={formData.to_email}
                onChange={(e) => setFormData({ ...formData, to_email: e.target.value })}
                required
                placeholder="customer@example.com"
                className="col-span-11 h-8"
              />
            </div>

            <div className="grid grid-cols-12 gap-2 items-center">
              <Label htmlFor="cc" className="text-xs text-muted-foreground col-span-1">
                Cc:
              </Label>
              <Input
                id="cc"
                type="text"
                value={formData.cc}
                onChange={(e) => setFormData({ ...formData, cc: e.target.value })}
                placeholder="cc1@example.com, cc2@example.com"
                className="col-span-11 h-8"
              />
            </div>

            {/* Subject */}
            <div className="grid grid-cols-12 gap-2 items-center">
              <Label htmlFor="subject" className="text-xs text-muted-foreground col-span-1">
                Subject:
              </Label>
              <Input
                id="subject"
                type="text"
                value={formData.subject}
                onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                required
                placeholder="Email subject"
                className="col-span-11 h-8"
              />
            </div>

            {/* Attachments */}
            <div className="space-y-1">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                accept="*/*"
                onChange={handleAttachmentChange}
              />
              <div className="flex items-center gap-2 flex-wrap">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Paperclip className="h-4 w-4 mr-1" />
                  Attach files
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={openLibraryDialog}
                >
                  <FolderOpen className="h-4 w-4 mr-1" />
                  Attach from library
                </Button>
                <span className="text-xs text-muted-foreground">
                  Max 20MB total
                </span>
              </div>
              {attachments.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {attachments.map((file, index) => (
                    <div
                      key={`${file.name}-${index}`}
                      className="flex items-center gap-1 px-2 py-1 rounded-md bg-muted text-sm"
                    >
                      <span className="truncate max-w-[120px]" title={file.name}>
                        {file.name}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        ({(file.size / 1024).toFixed(1)} KB)
                      </span>
                      <button
                        type="button"
                        onClick={() => removeAttachment(index)}
                        className="ml-1 p-0.5 hover:bg-muted-foreground/20 rounded"
                        aria-label="Remove attachment"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Message Body - Takes up remaining space */}
          <div className="flex-1 flex flex-col overflow-hidden px-6 py-4 min-h-0">
            <Label htmlFor="body" className="sr-only">
              Message body
            </Label>
            <EmailBodyEditor
              id="body"
              value={formData.body}
              onChange={(html) => setFormData({ ...formData, body: html })}
              disabled={loading || loadingTemplate}
              placeholder="Write your message…"
              className="flex-1 min-h-[300px]"
            />
            
            {/* Signature Preview */}
            {signature && (
              <div className="mt-4 pt-4 border-t">
                <Label className="text-xs text-muted-foreground mb-2 block">
                  Signature (from your settings)
                </Label>
                <div
                  className="p-3 bg-muted rounded-md border text-sm"
                  dangerouslySetInnerHTML={{ __html: signature }}
                />
                <p className="text-xs text-muted-foreground mt-2">
                  This signature will be automatically appended to your email. Edit it in{' '}
                  <a href="/settings/user" className="text-primary hover:underline" target="_blank">
                    My Settings
                  </a>
                </p>
              </div>
            )}
          </div>

          {/* Footer */}
          <DialogFooter className="px-6 py-4 border-t flex-shrink-0">
            <div className="flex items-center justify-between w-full">
              <p className="text-xs text-muted-foreground">
                Available variables: {'{{ customer.name }}'}, {'{{ customer.email }}'}, {'{{ customer.phone }}'}, etc.
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setLoading(false); // Reset loading state when canceling
                    onOpenChange(false);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={
                    loading ||
                    !formData.to_email ||
                    !formData.subject.trim() ||
                    isHtmlEffectivelyEmpty(formData.body)
                  }
                >
                  {loading ? 'Sending...' : 'Send'}
                </Button>
              </div>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    {/* Attach from library dialog */}
    <Dialog open={libraryDialogOpen} onOpenChange={setLibraryDialogOpen}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Attach from library</DialogTitle>
          <DialogDescription>
            Select documents to attach from the sales library
          </DialogDescription>
        </DialogHeader>
        {libraryLoading ? (
          <div className="py-8 text-center text-muted-foreground">Loading...</div>
        ) : libraryDocs.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">
            No documents in the library. Upload documents from the Documents page.
          </div>
        ) : (
          <div className="max-h-[300px] overflow-y-auto space-y-2 py-2">
            {libraryDocs.map((doc) => (
              <label
                key={doc.id}
                className="flex items-center gap-3 p-2 rounded-md border cursor-pointer hover:bg-muted/50"
              >
                <input
                  type="checkbox"
                  checked={librarySelected.has(doc.id)}
                  onChange={() => toggleLibrarySelected(doc.id)}
                />
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{doc.name}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {doc.filename}
                    {doc.file_size != null ? ` · ${(doc.file_size / 1024).toFixed(1)} KB` : ''}
                  </p>
                </div>
              </label>
            ))}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-4">
          <Button variant="outline" onClick={() => setLibraryDialogOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={addFromLibrary}
            disabled={libraryLoading || libraryDocs.length === 0 || librarySelected.size === 0 || libraryAdding}
          >
            {libraryAdding ? 'Adding...' : `Add ${librarySelected.size} selected`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
    </>
  );
}
