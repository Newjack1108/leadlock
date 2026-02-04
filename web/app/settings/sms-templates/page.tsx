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
import { MessageSquare, Plus, Edit, Trash2, Eye, Check } from 'lucide-react';
import {
  getSmsTemplates,
  createSmsTemplate,
  updateSmsTemplate,
  deleteSmsTemplate,
  previewSmsTemplate,
} from '@/lib/api';
import { SmsTemplate, SmsTemplateCreate, SmsTemplateUpdate } from '@/lib/types';
import { toast } from 'sonner';

export default function SmsTemplatesPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<SmsTemplate[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<SmsTemplate | null>(null);
  const [previewBody, setPreviewBody] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    body_template: '',
    is_default: false,
  });

  useEffect(() => {
    fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    try {
      setLoading(true);
      const data = await getSmsTemplates();
      setTemplates(data);
    } catch (error: unknown) {
      const err = error as { response?: { status?: number }; response?: { data?: { detail?: string } } };
      if (err.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load SMS templates');
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
      body_template: '',
      is_default: false,
    });
    setDialogOpen(true);
  };

  const handleEdit = (template: SmsTemplate) => {
    setEditingTemplate(template);
    setFormData({
      name: template.name,
      description: template.description || '',
      body_template: template.body_template,
      is_default: template.is_default,
    });
    setDialogOpen(true);
  };

  const handleDelete = async (templateId: number) => {
    if (!confirm('Are you sure you want to delete this template?')) return;
    try {
      await deleteSmsTemplate(templateId);
      toast.success('Template deleted successfully');
      fetchTemplates();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error(err.response?.data?.detail || 'Failed to delete template');
    }
  };

  const handlePreview = async (template: SmsTemplate) => {
    try {
      const preview = await previewSmsTemplate(template.id);
      setPreviewBody(preview.body);
      setPreviewDialogOpen(true);
    } catch {
      toast.error('Failed to preview template');
    }
  };

  const handleSave = async () => {
    if (!formData.name.trim()) {
      toast.error('Template name is required');
      return;
    }
    if (!formData.body_template.trim()) {
      toast.error('Message template is required');
      return;
    }
    try {
      if (editingTemplate) {
        await updateSmsTemplate(editingTemplate.id, formData as SmsTemplateUpdate);
        toast.success('Template updated successfully');
      } else {
        await createSmsTemplate(formData as SmsTemplateCreate);
        toast.success('Template created successfully');
      }
      setDialogOpen(false);
      fetchTemplates();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error(err.response?.data?.detail || 'Failed to save template');
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
            <h1 className="text-3xl font-bold">SMS Templates</h1>
            <p className="text-muted-foreground mt-2">
              Create and manage SMS templates with variable support
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
            Use in your template: <code className="bg-background px-1 rounded">{'{{ customer.name }}'}</code>,{' '}
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
              <MessageSquare className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No SMS templates yet</p>
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
                      <p className="text-xs text-muted-foreground">Message template:</p>
                      <p className="text-sm truncate">{template.body_template}</p>
                    </div>
                    <div className="flex gap-2 mt-4">
                      <Button size="sm" variant="outline" onClick={() => handlePreview(template)}>
                        <Eye className="h-3 w-3 mr-1" />
                        Preview
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => handleEdit(template)}>
                        <Edit className="h-3 w-3 mr-1" />
                        Edit
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => handleDelete(template.id)}>
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

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>
                {editingTemplate ? 'Edit SMS Template' : 'Create SMS Template'}
              </DialogTitle>
              <DialogDescription>
                Create an SMS template with variable support. Use Jinja2 syntax for variables.
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
                  placeholder="Follow-up SMS"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description (Optional)</Label>
                <Input
                  id="description"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Short description"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="body_template">
                  Message Template <span className="text-destructive">*</span>
                </Label>
                <Textarea
                  id="body_template"
                  value={formData.body_template}
                  onChange={(e) => setFormData({ ...formData, body_template: e.target.value })}
                  placeholder="Hi {{ customer.name }}, thanks for your interest. We'll call you soon."
                  rows={6}
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

        <Dialog open={previewDialogOpen} onOpenChange={setPreviewDialogOpen}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Template Preview</DialogTitle>
              <DialogDescription>
                Rendered with sample customer data
              </DialogDescription>
            </DialogHeader>
            {previewBody !== null && (
              <div className="p-4 bg-muted rounded border whitespace-pre-wrap text-sm">
                {previewBody}
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
