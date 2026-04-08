'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FileText, Plus, Edit, Trash2, Eye, Check, Paperclip } from 'lucide-react';
import {
  getQuoteTemplates,
  createQuoteTemplate,
  updateQuoteTemplate,
  deleteQuoteTemplate,
  previewQuoteTemplate,
  getSalesDocuments,
} from '@/lib/api';
import { QuoteTemplate, QuoteTemplateCreate, QuoteTemplateUpdate, SalesDocument } from '@/lib/types';
import { toast } from 'sonner';

export default function QuoteTemplatesPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<QuoteTemplate[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<QuoteTemplate | null>(null);
  const [previewData, setPreviewData] = useState<{ subject: string; body_html: string } | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    email_subject_template: '',
    email_body_template: '',
    is_default: false,
    sales_document_ids: [] as number[],
  });
  const [allSalesDocs, setAllSalesDocs] = useState<SalesDocument[]>([]);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [libraryDocs, setLibraryDocs] = useState<SalesDocument[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [librarySelected, setLibrarySelected] = useState<Set<number>>(new Set());

  useEffect(() => {
    fetchTemplates();
  }, []);

  useEffect(() => {
    getSalesDocuments()
      .then(setAllSalesDocs)
      .catch(() => setAllSalesDocs([]));
  }, []);

  const fetchTemplates = async () => {
    try {
      setLoading(true);
      const data = await getQuoteTemplates();
      setTemplates(data);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load quote templates');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingTemplate(null);
    setFormData({
      name: '',
      description: '',
      email_subject_template: 'Quote {{ quote.quote_number }}',
      email_body_template: '<p>Dear {{ customer.name }},</p>\n\n<p>Thank you for your interest. We have prepared quote {{ quote.quote_number }} for you.</p>\n\n<p>Please use the secure link below to view the full quote. If you have any questions, we would be happy to help.</p>\n\n{% if custom_message %}\n<p>{{ custom_message }}</p>\n{% endif %}\n\n<p>Best regards,<br>\n{{ company_settings.company_name if company_settings else \'LeadLock CRM\' }}</p>',
      is_default: false,
      sales_document_ids: [],
    });
    setDialogOpen(true);
  };

  const handleEdit = (template: QuoteTemplate) => {
    setEditingTemplate(template);
    const ordered =
      template.attached_documents?.slice().sort((a, b) => a.sort_order - b.sort_order) ?? [];
    setFormData({
      name: template.name,
      description: template.description || '',
      email_subject_template: template.email_subject_template,
      email_body_template: template.email_body_template,
      is_default: template.is_default,
      sales_document_ids: ordered.map((d) => d.id),
    });
    setDialogOpen(true);
  };

  const openLibraryDialog = async () => {
    setLibraryOpen(true);
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

  const addFromLibrary = () => {
    if (librarySelected.size === 0) {
      toast.error('Select at least one document');
      return;
    }
    setFormData((prev) => {
      const next = [...prev.sales_document_ids];
      for (const id of librarySelected) {
        if (!next.includes(id)) next.push(id);
      }
      return { ...prev, sales_document_ids: next };
    });
    setLibraryOpen(false);
  };

  const removeAttachedId = (id: number) => {
    setFormData((prev) => ({
      ...prev,
      sales_document_ids: prev.sales_document_ids.filter((i) => i !== id),
    }));
  };

  const docLabelForId = (id: number) => {
    const fromList = allSalesDocs.find((d) => d.id === id);
    if (fromList) return fromList.name;
    return `Document #${id}`;
  };

  const handleDelete = async (templateId: number) => {
    if (!confirm('Are you sure you want to delete this template?')) {
      return;
    }

    try {
      await deleteQuoteTemplate(templateId);
      toast.success('Template deleted successfully');
      fetchTemplates();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to delete template');
    }
  };

  const handlePreview = async (template: QuoteTemplate) => {
    try {
      const preview = await previewQuoteTemplate(template.id);
      setPreviewData(preview);
      setPreviewDialogOpen(true);
    } catch (error: any) {
      toast.error('Failed to preview template');
    }
  };

  const handleSave = async () => {
    if (!formData.name.trim()) {
      toast.error('Template name is required');
      return;
    }
    if (!formData.email_subject_template.trim()) {
      toast.error('Subject template is required');
      return;
    }
    if (!formData.email_body_template.trim()) {
      toast.error('Body template is required');
      return;
    }

    try {
      const { sales_document_ids, ...rest } = formData;
      if (editingTemplate) {
        await updateQuoteTemplate(editingTemplate.id, {
          ...(rest as QuoteTemplateUpdate),
          sales_document_ids,
        });
        toast.success('Template updated successfully');
      } else {
        await createQuoteTemplate({
          ...(rest as Omit<QuoteTemplateCreate, 'sales_document_ids'>),
          sales_document_ids,
        });
        toast.success('Template created successfully');
      }
      setDialogOpen(false);
      fetchTemplates();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save template');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 sm:px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Quote Templates</h1>
            <p className="text-muted-foreground mt-2">
              Create and manage quote email templates with variable support
            </p>
          </div>
          <Button onClick={handleCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Create Template
          </Button>
        </div>

        <div className="mb-4 p-4 bg-muted rounded-md">
          <h3 className="font-semibold mb-2">Available Variables</h3>
          <p className="text-sm text-muted-foreground">
            Use these variables in your templates: <code className="bg-background px-1 rounded">{'{{ quote.quote_number }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ quote.total_amount }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ quote.valid_until }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ customer.name }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ customer.email }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ company_settings.company_name }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ custom_message }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ currency_symbol }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ vat_amount }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ total_amount_inc_vat }}'}</code>
          </p>
        </div>

        {templates.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <FileText className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No quote templates yet</p>
              <Button onClick={handleCreate} className="mt-4">
                <Plus className="h-4 w-4 mr-2" />
                Create Your First Template
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {templates.map((template) => (
              <Card key={template.id}>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-lg">{template.name}</CardTitle>
                      {template.is_default && (
                        <Badge className="mt-2" variant="default">
                          <Check className="h-3 w-3 mr-1" />
                          Default
                        </Badge>
                      )}
                    </div>
                  </div>
                  {template.description && (
                    <CardDescription className="mt-2">{template.description}</CardDescription>
                  )}
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div>
                      <p className="text-xs text-muted-foreground">Subject:</p>
                      <p className="text-sm truncate">{template.email_subject_template}</p>
                    </div>
                    <div className="flex items-start gap-2 text-sm text-muted-foreground">
                      <Paperclip className="h-4 w-4 shrink-0 mt-0.5" />
                      <span>
                        {template.attached_documents?.length
                          ? (() => {
                              const sorted =
                                template.attached_documents.slice().sort((a, b) => a.sort_order - b.sort_order);
                              const first = sorted[0].name;
                              const more = sorted.length - 1;
                              return more > 0
                                ? `${first} +${more} more`
                                : first;
                            })()
                          : 'No library attachments'}
                      </span>
                    </div>
                    <div className="flex gap-2 mt-4">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handlePreview(template)}
                      >
                        <Eye className="h-3 w-3 mr-1" />
                        Preview
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleEdit(template)}
                      >
                        <Edit className="h-3 w-3 mr-1" />
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleDelete(template.id)}
                      >
                        <Trash2 className="h-3 w-3 mr-1" />
                        Delete
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Create/Edit Dialog */}
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>
                {editingTemplate ? 'Edit Quote Template' : 'Create Quote Template'}
              </DialogTitle>
              <DialogDescription>
                Create a quote email template with variable support. Use Jinja2 syntax for variables.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">
                  Template Name <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="Standard Quote Email"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description (Optional)</Label>
                <Input
                  id="description"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Default template for sending quotes to customers"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email_subject_template">
                  Subject Template <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="email_subject_template"
                  value={formData.email_subject_template}
                  onChange={(e) => setFormData({ ...formData, email_subject_template: e.target.value })}
                  placeholder="Quote {{ quote.quote_number }}"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email_body_template">
                  Body Template (HTML) <span className="text-destructive">*</span>
                </Label>
                <Textarea
                  id="email_body_template"
                  value={formData.email_body_template}
                  onChange={(e) => setFormData({ ...formData, email_body_template: e.target.value })}
                  placeholder="<p>Dear {{ customer.name }},</p><p>Please view your quote...</p>"
                  rows={10}
                  className="font-mono text-sm"
                />
              </div>

              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Label>Email attachments (library)</Label>
                  <Button type="button" variant="outline" size="sm" onClick={openLibraryDialog}>
                    <Paperclip className="h-3.5 w-3.5 mr-1" />
                    Add from library
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  These files are sent automatically with every quote email that uses this template (in addition to any
                  per-send uploads).
                </p>
                {formData.sales_document_ids.length > 0 ? (
                  <ul className="text-sm space-y-1 border rounded-md p-2 max-h-[160px] overflow-y-auto">
                    {formData.sales_document_ids.map((id) => (
                      <li key={id} className="flex items-center justify-between gap-2">
                        <span className="truncate text-muted-foreground">{docLabelForId(id)}</span>
                        <Button type="button" variant="ghost" size="sm" className="shrink-0" onClick={() => removeAttachedId(id)}>
                          Remove
                        </Button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>

              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="is_default"
                  checked={formData.is_default}
                  onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
                  className="rounded"
                />
                <Label htmlFor="is_default">Set as default template</Label>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleSave}>
                {editingTemplate ? 'Update' : 'Create'} Template
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={libraryOpen} onOpenChange={setLibraryOpen}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Add from library</DialogTitle>
              <DialogDescription>Select sales documents to attach to this template when sending quote emails.</DialogDescription>
            </DialogHeader>
            {libraryLoading ? (
              <div className="py-8 text-center text-muted-foreground">Loading...</div>
            ) : libraryDocs.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground">
                No documents in the library. Upload documents from Sales Documents.
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
              <Button type="button" variant="outline" onClick={() => setLibraryOpen(false)}>
                Cancel
              </Button>
              <Button
                type="button"
                onClick={addFromLibrary}
                disabled={libraryLoading || libraryDocs.length === 0 || librarySelected.size === 0}
              >
                Add selected
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* Preview Dialog */}
        <Dialog open={previewDialogOpen} onOpenChange={setPreviewDialogOpen}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Template Preview</DialogTitle>
              <DialogDescription>
                This is how the template will look with sample quote and customer data
              </DialogDescription>
            </DialogHeader>

            {previewData && (
              <div className="space-y-4">
                <div>
                  <Label>Subject:</Label>
                  <p className="mt-1 p-2 bg-muted rounded">{previewData.subject}</p>
                </div>
                <div>
                  <Label>Body:</Label>
                  <div
                    className="mt-1 p-4 bg-muted rounded border"
                    dangerouslySetInnerHTML={{ __html: previewData.body_html }}
                  />
                </div>
              </div>
            )}

            <DialogFooter>
              <Button onClick={() => setPreviewDialogOpen(false)}>Close</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}
