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
import { Textarea } from '@/components/ui/textarea';
import EmailBodyEditor from '@/components/EmailBodyEditor';
import { sendEmail, getEmailTemplates, previewEmailTemplate, previewComposeEmail, getUserEmailSettings, getSalesDocuments, downloadSalesDocument } from '@/lib/api';
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
  const [bodyEditMode, setBodyEditMode] = useState<'visual' | 'source'>('source');
  const [signaturePreviewOpen, setSignaturePreviewOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewResult, setPreviewResult] = useState<{
    body_html: string;
    subject?: string;
    to_email?: string;
    cc?: string;
  } | null>(null);
  const [formData, setFormData] = useState({
    to_email: customer.email || '',
    cc: '',
    subject: '',
    body: '',
  });
  const fileInputRef = useRef<HTMLInputElement>(null);
  /** Bumps on each template selection so stale `previewEmailTemplate` responses are ignored. */
  const templatePreviewRequestIdRef = useRef(0);
  /** Only reset form when the dialog opens — not when `customer` refetches while open (that was wiping template body after WYSIWYG). */
  const wasOpenRef = useRef(false);

  useEffect(() => {
    if (!open) {
      if (wasOpenRef.current) {
        setLoading(false);
        setSelectedTemplateId(undefined);
        setAttachments([]);
      }
      wasOpenRef.current = false;
      return;
    }

    if (!wasOpenRef.current) {
      wasOpenRef.current = true;
      setBodyEditMode('source');
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
      setLoading(false);
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
      setTemplates(Array.isArray(data) ? data : []);
    } catch (error: unknown) {
      console.error('Failed to load templates', error);
      setTemplates([]);
      toast.error('Failed to load email templates');
    }
  };

  const handleTemplateChange = async (templateId: string) => {
    templatePreviewRequestIdRef.current += 1;
    const requestId = templatePreviewRequestIdRef.current;

    if (templateId === 'none') {
      // Only clear the body when leaving a real template. If the user already had "No
      // Template" and typed a scratch message, re-selecting "none" must not wipe the body
      // (Radix may call onValueChange('none') again in some cases).
      const hadTemplate = selectedTemplateId != null;
      setSelectedTemplateId(undefined);
      setLoadingTemplate(false);
      setFormData((prev) => ({
        ...prev,
        ...(hadTemplate ? { body: '' } : {}),
      }));
      return;
    }

    const id = parseInt(templateId, 10);
    if (Number.isNaN(id)) {
      return;
    }

    setSelectedTemplateId(id);
    setLoadingTemplate(true);

    try {
      const preview = await previewEmailTemplate(id, { customer_id: customer.id });
      if (templatePreviewRequestIdRef.current !== requestId) return;
      const body = preview.body_html ?? '';
      setFormData((prev) => ({
        ...prev,
        subject: preview.subject,
        body,
      }));
      setBodyEditMode('source');
    } catch {
      if (templatePreviewRequestIdRef.current !== requestId) return;
      toast.error('Failed to load template');
    } finally {
      if (templatePreviewRequestIdRef.current === requestId) {
        setLoadingTemplate(false);
      }
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

  const handlePreview = async () => {
    if (isHtmlEffectivelyEmpty(formData.body)) {
      toast.error('Add a message body to preview');
      return;
    }
    setPreviewLoading(true);
    try {
      const data = await previewComposeEmail({
        customer_id: customer.id,
        body_html: formData.body,
        body_text: htmlToPlainText(formData.body),
        subject: formData.subject,
        to_email: formData.to_email,
        cc: formData.cc || undefined,
        attachment_filenames: attachments.map((f) => f.name),
      });
      setPreviewResult({
        body_html: data.body_html,
        subject: data.subject ?? formData.subject,
        to_email: data.to_email ?? formData.to_email,
        cc: data.cc ?? formData.cc,
      });
      setPreviewOpen(true);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: unknown } }; message?: string };
      const detail = err.response?.data?.detail;
      const msg =
        typeof detail === 'string'
          ? detail
          : err.message || 'Failed to load preview';
      toast.error(msg);
      console.error('Email preview error:', error);
    } finally {
      setPreviewLoading(false);
    }
  };

  const sendDisabled =
    loading ||
    !formData.to_email ||
    !formData.subject.trim() ||
    isHtmlEffectivelyEmpty(formData.body);

  const sendDisabledTitle = sendDisabled
    ? loading
      ? 'Sending…'
      : !formData.to_email
        ? 'Add a recipient email address'
        : !formData.subject.trim()
          ? 'Add a subject'
          : 'Add a message body'
    : undefined;

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(98vw,1600px)] max-w-[min(98vw,1600px)] sm:max-w-[min(98vw,1600px)] h-[92vh] max-h-[92vh] min-h-[85vh] flex flex-col p-0">
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
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, to_email: e.target.value }))
                }
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
                onChange={(e) => setFormData((prev) => ({ ...prev, cc: e.target.value }))}
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
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, subject: e.target.value }))
                }
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
          <div className="flex-1 flex flex-col overflow-hidden px-6 py-4 min-h-0 gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2 flex-shrink-0">
              <div className="flex items-center gap-2 flex-wrap min-w-0">
                <Label htmlFor={bodyEditMode === 'visual' ? 'body' : 'body_source'} className="text-sm font-normal">
                  Message
                </Label>
                {signature ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs shrink-0"
                    onClick={() => setSignaturePreviewOpen(true)}
                  >
                    View signature
                  </Button>
                ) : null}
              </div>
              <div className="flex rounded-md border border-input p-0.5 bg-muted/30 shrink-0">
                <Button
                  type="button"
                  variant={bodyEditMode === 'visual' ? 'default' : 'ghost'}
                  size="sm"
                  className="h-7"
                  onClick={() => setBodyEditMode('visual')}
                  disabled={loading || loadingTemplate}
                >
                  Visual
                </Button>
                <Button
                  type="button"
                  variant={bodyEditMode === 'source' ? 'default' : 'ghost'}
                  size="sm"
                  className="h-7"
                  onClick={() => setBodyEditMode('source')}
                  disabled={loading || loadingTemplate}
                >
                  HTML source
                </Button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground flex-shrink-0">
              Templates load in HTML source so the full body appears reliably; switch to Visual for simple formatting when needed. HTML source gives full control (tables, custom markup).
            </p>
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
              {bodyEditMode === 'visual' ? (
                <EmailBodyEditor
                  id="body"
                  value={formData.body}
                  onChange={(html) => setFormData((prev) => ({ ...prev, body: html }))}
                  disabled={loading || loadingTemplate}
                  placeholder="Write your message…"
                  className="flex-1 min-h-0 [&_.ProseMirror]:text-base"
                />
              ) : (
                <Textarea
                  id="body_source"
                  value={formData.body}
                  onChange={(e) => setFormData((prev) => ({ ...prev, body: e.target.value }))}
                  placeholder="<p>Your HTML message…</p>"
                  disabled={loading || loadingTemplate}
                  rows={20}
                  className="font-mono text-base flex-1 min-h-[min(50vh,560px)] resize-y"
                />
              )}
            </div>
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
                  type="button"
                  variant="outline"
                  onClick={handlePreview}
                  disabled={
                    loading ||
                    loadingTemplate ||
                    previewLoading ||
                    isHtmlEffectivelyEmpty(formData.body)
                  }
                >
                  {previewLoading ? 'Loading…' : 'Preview'}
                </Button>
                <Button
                  type="submit"
                  title={sendDisabledTitle}
                  disabled={sendDisabled}
                >
                  {loading ? 'Sending...' : 'Send'}
                </Button>
              </div>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    <Dialog open={signaturePreviewOpen} onOpenChange={setSignaturePreviewOpen}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Signature preview</DialogTitle>
          <DialogDescription>
            This signature is appended automatically when you send. Edit it in My Settings.
          </DialogDescription>
        </DialogHeader>
        {signature ? (
          <div
            className="p-3 bg-muted rounded-md border text-sm max-h-[50vh] overflow-y-auto"
            dangerouslySetInnerHTML={{ __html: signature }}
          />
        ) : null}
        <DialogFooter className="gap-2 sm:justify-between">
          <a
            href="/settings/user"
            className="text-sm text-primary hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            My Settings
          </a>
          <Button type="button" variant="outline" onClick={() => setSignaturePreviewOpen(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog
      open={previewOpen}
      onOpenChange={(o) => {
        setPreviewOpen(o);
        if (!o) setPreviewResult(null);
      }}
    >
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Send preview</DialogTitle>
          <DialogDescription>
            How this message will look when sent (including signature and layout).
          </DialogDescription>
        </DialogHeader>
        {previewResult && (
          <div className="space-y-3 text-sm overflow-hidden flex flex-col flex-1 min-h-0">
            {previewResult.subject != null && previewResult.subject !== '' && (
              <div>
                <span className="text-muted-foreground">Subject: </span>
                <span className="font-medium">{previewResult.subject}</span>
              </div>
            )}
            {previewResult.to_email != null && previewResult.to_email !== '' && (
              <div>
                <span className="text-muted-foreground">To: </span>
                <span>{previewResult.to_email}</span>
              </div>
            )}
            {previewResult.cc != null && previewResult.cc.trim() !== '' && (
              <div>
                <span className="text-muted-foreground">Cc: </span>
                <span>{previewResult.cc}</span>
              </div>
            )}
            <div className="border rounded-md bg-muted/30 overflow-auto max-h-[min(60vh,560px)] p-4">
              <div
                className="max-w-[600px] mx-auto bg-background border shadow-sm rounded-md overflow-hidden"
                dangerouslySetInnerHTML={{ __html: previewResult.body_html }}
              />
            </div>
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setPreviewOpen(false)}>
            Close
          </Button>
        </DialogFooter>
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
