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
import { FileText, Plus, Edit, Trash2, Eye, Check } from 'lucide-react';
import {
  getQuoteTemplates,
  createQuoteTemplate,
  updateQuoteTemplate,
  deleteQuoteTemplate,
  previewQuoteTemplate,
} from '@/lib/api';
import { QuoteTemplate, QuoteTemplateCreate, QuoteTemplateUpdate } from '@/lib/types';
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
  });

  useEffect(() => {
    fetchTemplates();
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
    });
    setDialogOpen(true);
  };

  const handleEdit = (template: QuoteTemplate) => {
    setEditingTemplate(template);
    setFormData({
      name: template.name,
      description: template.description || '',
      email_subject_template: template.email_subject_template,
      email_body_template: template.email_body_template,
      is_default: template.is_default,
    });
    setDialogOpen(true);
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
      if (editingTemplate) {
        await updateQuoteTemplate(editingTemplate.id, formData as QuoteTemplateUpdate);
        toast.success('Template updated successfully');
      } else {
        await createQuoteTemplate(formData as QuoteTemplateCreate);
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
