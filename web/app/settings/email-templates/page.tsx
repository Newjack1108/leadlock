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
import { Mail, Plus, Edit, Trash2, Eye, Check } from 'lucide-react';
import {
  getEmailTemplates,
  createEmailTemplate,
  updateEmailTemplate,
  deleteEmailTemplate,
  previewEmailTemplate,
} from '@/lib/api';
import { EmailTemplate, EmailTemplateCreate, EmailTemplateUpdate } from '@/lib/types';
import { toast } from 'sonner';

export default function EmailTemplatesPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<EmailTemplate | null>(null);
  const [previewData, setPreviewData] = useState<{ subject: string; body_html: string } | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    subject_template: '',
    body_template: '',
    is_default: false,
  });

  useEffect(() => {
    fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    try {
      setLoading(true);
      const data = await getEmailTemplates();
      setTemplates(data);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load email templates');
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
      subject_template: '',
      body_template: '',
      is_default: false,
    });
    setDialogOpen(true);
  };

  const handleEdit = (template: EmailTemplate) => {
    setEditingTemplate(template);
    setFormData({
      name: template.name,
      description: template.description || '',
      subject_template: template.subject_template,
      body_template: template.body_template,
      is_default: template.is_default,
    });
    setDialogOpen(true);
  };

  const handleDelete = async (templateId: number) => {
    if (!confirm('Are you sure you want to delete this template?')) {
      return;
    }

    try {
      await deleteEmailTemplate(templateId);
      toast.success('Template deleted successfully');
      fetchTemplates();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to delete template');
    }
  };

  const handlePreview = async (template: EmailTemplate) => {
    try {
      const preview = await previewEmailTemplate(template.id);
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
    if (!formData.subject_template.trim()) {
      toast.error('Subject template is required');
      return;
    }
    if (!formData.body_template.trim()) {
      toast.error('Body template is required');
      return;
    }

    try {
      if (editingTemplate) {
        await updateEmailTemplate(editingTemplate.id, formData as EmailTemplateUpdate);
        toast.success('Template updated successfully');
      } else {
        await createEmailTemplate(formData as EmailTemplateCreate);
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
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Email Templates</h1>
            <p className="text-muted-foreground mt-2">
              Create and manage email templates with variable support
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
            Use these variables in your templates: <code className="bg-background px-1 rounded">{'{{ customer.name }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ customer.email }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ customer.phone }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ customer.customer_number }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ customer.address_line1 }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ customer.city }}'}</code>,{' '}
            <code className="bg-background px-1 rounded">{'{{ customer.postcode }}'}</code>
          </p>
        </div>

        {templates.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <Mail className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No email templates yet</p>
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
                      <p className="text-sm truncate">{template.subject_template}</p>
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
                {editingTemplate ? 'Edit Email Template' : 'Create Email Template'}
              </DialogTitle>
              <DialogDescription>
                Create an email template with variable support. Use Jinja2 syntax for variables.
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
                  placeholder="Welcome Email"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description (Optional)</Label>
                <Input
                  id="description"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Template for welcoming new customers"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="subject_template">
                  Subject Template <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="subject_template"
                  value={formData.subject_template}
                  onChange={(e) => setFormData({ ...formData, subject_template: e.target.value })}
                  placeholder="Hello {{ customer.name }}"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="body_template">
                  Body Template (HTML) <span className="text-destructive">*</span>
                </Label>
                <Textarea
                  id="body_template"
                  value={formData.body_template}
                  onChange={(e) => setFormData({ ...formData, body_template: e.target.value })}
                  placeholder="<p>Dear {{ customer.name }},</p><p>Welcome to our service!</p>"
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
                This is how the template will look with sample customer data
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
