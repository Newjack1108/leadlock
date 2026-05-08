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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Edit, Eye, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  createWeeklyPlanTemplate,
  deleteWeeklyPlanTemplate,
  getApiErrorDetail,
  getWeeklyPlanTemplates,
  previewWeeklyPlanTemplate,
  updateWeeklyPlanTemplate,
} from '@/lib/api';
import { SuggestedAction, WeeklyPlanTemplate } from '@/lib/types';

const CHANNEL_OPTIONS = ['EMAIL', 'SMS', 'CALL'] as const;

export default function WeeklyPlanTemplatesPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<WeeklyPlanTemplate[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false);
  const [previewBody, setPreviewBody] = useState<string | null>(null);
  const [previewSubject, setPreviewSubject] = useState<string | null>(null);
  const [editingTemplate, setEditingTemplate] = useState<WeeklyPlanTemplate | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    suggested_action: SuggestedAction.FOLLOW_UP,
    channel: 'EMAIL',
    subject_template: '',
    body_template: '',
    is_active: true,
  });

  const fetchTemplates = async () => {
    try {
      setLoading(true);
      const data = await getWeeklyPlanTemplates();
      setTemplates(data || []);
    } catch (error) {
      const detail = getApiErrorDetail(error);
      if ((error as any)?.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error(detail || 'Failed to load weekly plan templates');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, []);

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      suggested_action: SuggestedAction.FOLLOW_UP,
      channel: 'EMAIL',
      subject_template: '',
      body_template: '',
      is_active: true,
    });
  };

  const handleCreate = () => {
    setEditingTemplate(null);
    resetForm();
    setDialogOpen(true);
  };

  const handleEdit = (template: WeeklyPlanTemplate) => {
    setEditingTemplate(template);
    setFormData({
      name: template.name,
      description: template.description || '',
      suggested_action: template.suggested_action,
      channel: template.channel,
      subject_template: template.subject_template || '',
      body_template: template.body_template,
      is_active: template.is_active,
    });
    setDialogOpen(true);
  };

  const handleDelete = async (templateId: number) => {
    if (!confirm('Delete this weekly plan template?')) return;
    try {
      await deleteWeeklyPlanTemplate(templateId);
      toast.success('Template deleted');
      await fetchTemplates();
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to delete template');
    }
  };

  const handlePreview = async (template: WeeklyPlanTemplate) => {
    try {
      const preview = await previewWeeklyPlanTemplate(template.id, {
        customer_name: 'Alex Carter',
        quote_number: 'Q-54321',
      });
      setPreviewBody(preview.body || '');
      setPreviewSubject(preview.subject || null);
      setPreviewDialogOpen(true);
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to preview template');
    }
  };

  const handleSave = async () => {
    if (!formData.name.trim()) {
      toast.error('Template name is required');
      return;
    }
    if (!formData.body_template.trim()) {
      toast.error('Message body is required');
      return;
    }
    if (formData.channel === 'EMAIL' && !formData.subject_template.trim()) {
      toast.error('Email templates require a subject template');
      return;
    }
    try {
      const payload = {
        ...formData,
        subject_template: formData.channel === 'EMAIL' ? formData.subject_template : '',
      };
      if (editingTemplate) {
        await updateWeeklyPlanTemplate(editingTemplate.id, payload);
        toast.success('Template updated');
      } else {
        await createWeeklyPlanTemplate(payload);
        toast.success('Template created');
      }
      setDialogOpen(false);
      await fetchTemplates();
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to save template');
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
            <h1 className="text-3xl font-bold">Weekly Plan Templates</h1>
            <p className="text-muted-foreground mt-2">
              Manage global templates by action and channel for weekly plan recommendations.
            </p>
          </div>
          <Button onClick={handleCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Create Template
          </Button>
        </div>

        <div className="mb-4 p-4 bg-muted rounded-md text-sm text-muted-foreground space-y-1">
          <p><strong>Variables:</strong> <code>{'{{ customer.name }}'}</code>, <code>{'{{ quote.number }}'}</code>, <code>{'{{ company.name }}'}</code></p>
        </div>

        {templates.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              No weekly plan templates yet.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {templates.map((template) => (
              <Card key={template.id}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-lg">{template.name}</CardTitle>
                    <div className="flex gap-2">
                      <Badge variant="secondary">{template.channel}</Badge>
                      <Badge>{template.suggested_action}</Badge>
                      {!template.is_active ? <Badge variant="outline">Inactive</Badge> : null}
                    </div>
                  </div>
                  {template.description ? <CardDescription>{template.description}</CardDescription> : null}
                </CardHeader>
                <CardContent className="space-y-3">
                  {template.subject_template ? (
                    <div>
                      <p className="text-xs text-muted-foreground">Subject template:</p>
                      <p className="text-sm">{template.subject_template}</p>
                    </div>
                  ) : null}
                  <div>
                    <p className="text-xs text-muted-foreground">Body template:</p>
                    <p className="text-sm">{template.body_template}</p>
                  </div>
                  <div className="flex gap-2">
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
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingTemplate ? 'Edit Template' : 'Create Template'}</DialogTitle>
            <DialogDescription>Configure template content used for weekly plan suggestions.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Name</Label>
                <Input value={formData.name} onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))} />
              </div>
              <div>
                <Label>Description</Label>
                <Input value={formData.description} onChange={(e) => setFormData((p) => ({ ...p, description: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Suggested action</Label>
                <Select
                  value={formData.suggested_action}
                  onValueChange={(value) => setFormData((p) => ({ ...p, suggested_action: value as SuggestedAction }))}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.values(SuggestedAction).map((action) => (
                      <SelectItem key={action} value={action}>{action}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Channel</Label>
                <Select value={formData.channel} onValueChange={(value) => setFormData((p) => ({ ...p, channel: value }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CHANNEL_OPTIONS.map((channel) => (
                      <SelectItem key={channel} value={channel}>{channel}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {formData.channel === 'EMAIL' ? (
              <div>
                <Label>Subject Template</Label>
                <Input
                  value={formData.subject_template}
                  onChange={(e) => setFormData((p) => ({ ...p, subject_template: e.target.value }))}
                />
              </div>
            ) : null}
            <div>
              <Label>Body Template</Label>
              <Textarea
                value={formData.body_template}
                rows={6}
                onChange={(e) => setFormData((p) => ({ ...p, body_template: e.target.value }))}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) => setFormData((p) => ({ ...p, is_active: e.target.checked }))}
              />
              Active
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave}>{editingTemplate ? 'Save Changes' : 'Create Template'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={previewDialogOpen} onOpenChange={setPreviewDialogOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Template Preview</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            {previewSubject ? (
              <div>
                <p className="text-xs text-muted-foreground">Subject</p>
                <p className="text-sm font-medium">{previewSubject}</p>
              </div>
            ) : null}
            <div>
              <p className="text-xs text-muted-foreground">Body</p>
              <p className="text-sm whitespace-pre-wrap">{previewBody}</p>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

