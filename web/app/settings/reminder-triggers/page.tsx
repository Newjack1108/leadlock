'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Edit, Plus, Trash2 } from 'lucide-react';
import { getReminderRules, updateReminderRule, createReminderRule, deleteReminderRule } from '@/lib/api';
import { ReminderRule, ReminderRuleUpdate, ReminderPriority, SuggestedAction } from '@/lib/types';
import api from '@/lib/api';
import { toast } from 'sonner';

const CHECK_TYPE_LABELS: Record<string, string> = {
  LAST_ACTIVITY: 'Last activity',
  STATUS_DURATION: 'Status duration',
  SENT_DATE: 'Sent date',
  VALID_UNTIL: 'Valid until',
  SENT_NOT_OPENED: 'Sent, not opened',
  OPENED_NO_REPLY: 'Opened, no reply',
};

const LEAD_CHECK_TYPES = ['LAST_ACTIVITY', 'STATUS_DURATION'] as const;
const QUOTE_CHECK_TYPES = [
  'SENT_DATE',
  'VALID_UNTIL',
  'STATUS_DURATION',
  'SENT_NOT_OPENED',
  'OPENED_NO_REPLY',
] as const;
const LEAD_STATUSES = [
  'NEW',
  'CONTACT_ATTEMPTED',
  'ENGAGED',
  'QUALIFIED',
  'QUOTED',
  'WON',
  'LOST',
] as const;
const QUOTE_STATUSES = ['DRAFT', 'SENT', 'VIEWED', 'ACCEPTED', 'REJECTED', 'EXPIRED'] as const;
const QUOTE_STATUS_NONE = '__none__';

function formatRuleName(name: string): string {
  return name
    .split('_')
    .map((w) => w.charAt(0) + w.slice(1).toLowerCase())
    .join(' ');
}

export default function ReminderTriggersPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [rules, setRules] = useState<ReminderRule[]>([]);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<ReminderRule | null>(null);
  const [formData, setFormData] = useState({
    threshold_days: 0,
    is_active: true,
    priority: ReminderPriority.MEDIUM,
    suggested_action: SuggestedAction.FOLLOW_UP,
  });
  const [saving, setSaving] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createSaving, setCreateSaving] = useState(false);
  const [createForm, setCreateForm] = useState({
    rule_name: '',
    entity_type: 'LEAD' as 'LEAD' | 'QUOTE',
    status: 'NEW' as string,
    check_type: 'LAST_ACTIVITY' as string,
    threshold_days: 7,
    is_active: true,
    priority: ReminderPriority.MEDIUM,
    suggested_action: SuggestedAction.FOLLOW_UP,
  });

  const isDirector = userRole === 'DIRECTOR';

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const response = await api.get('/api/auth/me');
        setUserRole(response.data.role);
      } catch {
        setUserRole(null);
      }
    };
    fetchUser();
  }, []);

  useEffect(() => {
    fetchRules();
  }, []);

  const fetchRules = async () => {
    try {
      setLoading(true);
      const data = await getReminderRules();
      setRules(data);
    } catch (error: unknown) {
      const err = error as { response?: { status?: number } };
      if (err.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load reminder rules');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (rule: ReminderRule) => {
    setEditingRule(rule);
    setFormData({
      threshold_days: rule.threshold_days,
      is_active: rule.is_active,
      priority: rule.priority,
      suggested_action: rule.suggested_action,
    });
    setEditDialogOpen(true);
  };

  const handleSave = async () => {
    if (!editingRule) return;
    try {
      setSaving(true);
      const update: ReminderRuleUpdate = {
        threshold_days: formData.threshold_days,
        is_active: formData.is_active,
        priority: formData.priority,
        suggested_action: formData.suggested_action,
      };
      await updateReminderRule(editingRule.id, update);
      toast.success('Rule updated successfully');
      setEditDialogOpen(false);
      setEditingRule(null);
      fetchRules();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error(err.response?.data?.detail || 'Failed to update rule');
    } finally {
      setSaving(false);
    }
  };

  const openCreateDialog = () => {
    setCreateForm({
      rule_name: '',
      entity_type: 'LEAD',
      status: 'NEW',
      check_type: 'LAST_ACTIVITY',
      threshold_days: 7,
      is_active: true,
      priority: ReminderPriority.MEDIUM,
      suggested_action: SuggestedAction.FOLLOW_UP,
    });
    setCreateDialogOpen(true);
  };

  const handleDelete = async (rule: ReminderRule) => {
    const label = formatRuleName(rule.rule_name);
    if (
      !confirm(
        `Delete reminder rule "${label}"? Existing reminders are not removed; this rule will no longer create new ones.`
      )
    ) {
      return;
    }
    try {
      await deleteReminderRule(rule.id);
      if (editingRule?.id === rule.id) {
        setEditDialogOpen(false);
        setEditingRule(null);
      }
      toast.success('Rule deleted');
      fetchRules();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error(err.response?.data?.detail || 'Failed to delete rule');
    }
  };

  const handleCreateSave = async () => {
    const name = createForm.rule_name.trim();
    if (!name) {
      toast.error('Rule name is required');
      return;
    }
    if (createForm.entity_type === 'LEAD' && !createForm.status) {
      toast.error('Lead status is required');
      return;
    }
    try {
      setCreateSaving(true);
      const statusPayload =
        createForm.entity_type === 'LEAD'
          ? createForm.status
          : createForm.status === QUOTE_STATUS_NONE
            ? null
            : createForm.status;
      await createReminderRule({
        rule_name: name,
        entity_type: createForm.entity_type,
        threshold_days: createForm.threshold_days,
        check_type: createForm.check_type,
        is_active: createForm.is_active,
        priority: createForm.priority,
        suggested_action: createForm.suggested_action,
        status: statusPayload,
      });
      toast.success('Rule created successfully');
      setCreateDialogOpen(false);
      fetchRules();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error(err.response?.data?.detail || 'Failed to create rule');
    } finally {
      setCreateSaving(false);
    }
  };

  const leadRules = rules.filter((r) => r.entity_type === 'LEAD');
  const quoteRules = rules.filter((r) => r.entity_type === 'QUOTE');
  const hasNoRules = rules.length === 0;

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold mb-2">Reminder Triggers</h1>
            <p className="text-muted-foreground">
              Configure when reminders are created for stale leads and quotes. Only Directors can create, edit, or delete.
              New rules must use check types the engine already supports (see form options).
            </p>
          </div>
          {isDirector && (
            <Button type="button" className="shrink-0" onClick={openCreateDialog}>
              <Plus className="h-4 w-4 mr-2" />
              Add rule
            </Button>
          )}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Lead Rules</CardTitle>
              <CardDescription>
                Triggers for leads based on status and time since last activity
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2 px-2 font-medium">Rule</th>
                      <th className="text-left py-2 px-2 font-medium">Status</th>
                      <th className="text-left py-2 px-2 font-medium">Check</th>
                      <th className="text-left py-2 px-2 font-medium">Threshold</th>
                      <th className="text-left py-2 px-2 font-medium">Active</th>
                      <th className="text-left py-2 px-2 font-medium">Priority</th>
                      <th className="text-left py-2 px-2 font-medium">Action</th>
                      {isDirector && <th className="text-right py-2 px-2 font-medium">Manage</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {leadRules.map((rule) => (
                      <tr key={rule.id} className="border-b last:border-0">
                        <td className="py-2 px-2">{formatRuleName(rule.rule_name)}</td>
                        <td className="py-2 px-2">{rule.status || '-'}</td>
                        <td className="py-2 px-2">{CHECK_TYPE_LABELS[rule.check_type] || rule.check_type}</td>
                        <td className="py-2 px-2">{rule.threshold_days} days</td>
                        <td className="py-2 px-2">{rule.is_active ? 'Yes' : 'No'}</td>
                        <td className="py-2 px-2">{rule.priority}</td>
                        <td className="py-2 px-2">{rule.suggested_action.replace(/_/g, ' ')}</td>
                        {isDirector && (
                          <td className="py-2 px-2 text-right">
                            <div className="inline-flex items-center gap-0">
                              <Button variant="ghost" size="sm" onClick={() => handleEdit(rule)} aria-label="Edit rule">
                                <Edit className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-destructive hover:text-destructive"
                                onClick={() => handleDelete(rule)}
                                aria-label="Delete rule"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {hasNoRules && (
            <Card>
              <CardContent>
                <p className="text-sm text-muted-foreground py-4">
                  No reminder rules loaded. Restart the API server to backfill default rules from the database migration.
                </p>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Quote Rules</CardTitle>
              <CardDescription>
                Triggers for quotes based on sent date, expiry, and engagement
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2 px-2 font-medium">Rule</th>
                      <th className="text-left py-2 px-2 font-medium">Status</th>
                      <th className="text-left py-2 px-2 font-medium">Check</th>
                      <th className="text-left py-2 px-2 font-medium">Threshold</th>
                      <th className="text-left py-2 px-2 font-medium">Active</th>
                      <th className="text-left py-2 px-2 font-medium">Priority</th>
                      <th className="text-left py-2 px-2 font-medium">Action</th>
                      {isDirector && <th className="text-right py-2 px-2 font-medium">Manage</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {quoteRules.map((rule) => (
                      <tr key={rule.id} className="border-b last:border-0">
                        <td className="py-2 px-2">{formatRuleName(rule.rule_name)}</td>
                        <td className="py-2 px-2">{rule.status || '-'}</td>
                        <td className="py-2 px-2">{CHECK_TYPE_LABELS[rule.check_type] || rule.check_type}</td>
                        <td className="py-2 px-2">{rule.threshold_days} days</td>
                        <td className="py-2 px-2">{rule.is_active ? 'Yes' : 'No'}</td>
                        <td className="py-2 px-2">{rule.priority}</td>
                        <td className="py-2 px-2">{rule.suggested_action.replace(/_/g, ' ')}</td>
                        {isDirector && (
                          <td className="py-2 px-2 text-right">
                            <div className="inline-flex items-center gap-0">
                              <Button variant="ghost" size="sm" onClick={() => handleEdit(rule)} aria-label="Edit rule">
                                <Edit className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-destructive hover:text-destructive"
                                onClick={() => handleDelete(rule)}
                                aria-label="Delete rule"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>

        <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
          <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Add reminder rule</DialogTitle>
              <DialogDescription>
                Unique name (letters, numbers, underscores). Combines entity, status filter, and check type with existing
                reminder logic—new check types still require backend changes.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="create_rule_name">Rule name</Label>
                <Input
                  id="create_rule_name"
                  placeholder="e.g. ENGAGED_STALE_CUSTOM"
                  value={createForm.rule_name}
                  onChange={(e) => setCreateForm((f) => ({ ...f, rule_name: e.target.value }))}
                />
              </div>
              <div className="grid gap-2">
                <Label>Entity</Label>
                <Select
                  value={createForm.entity_type}
                  onValueChange={(v) => {
                    const et = v as 'LEAD' | 'QUOTE';
                    setCreateForm((f) => ({
                      ...f,
                      entity_type: et,
                      check_type: et === 'LEAD' ? LEAD_CHECK_TYPES[0] : QUOTE_CHECK_TYPES[0],
                      status: et === 'LEAD' ? 'NEW' : QUOTE_STATUS_NONE,
                    }));
                  }}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="LEAD">Lead</SelectItem>
                    <SelectItem value="QUOTE">Quote</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>
                  {createForm.entity_type === 'LEAD' ? 'Lead status' : 'Quote status (optional)'}
                </Label>
                <Select
                  value={createForm.entity_type === 'LEAD' ? createForm.status : createForm.status || QUOTE_STATUS_NONE}
                  onValueChange={(v) => setCreateForm((f) => ({ ...f, status: v }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {createForm.entity_type === 'QUOTE' && (
                      <SelectItem value={QUOTE_STATUS_NONE}>All quotes (no status filter)</SelectItem>
                    )}
                    {(createForm.entity_type === 'LEAD' ? LEAD_STATUSES : QUOTE_STATUSES).map((s) => (
                      <SelectItem key={s} value={s}>
                        {s.replace(/_/g, ' ')}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>Check type</Label>
                <Select
                  value={createForm.check_type}
                  onValueChange={(v) => setCreateForm((f) => ({ ...f, check_type: v }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(createForm.entity_type === 'LEAD' ? LEAD_CHECK_TYPES : QUOTE_CHECK_TYPES).map((ct) => (
                      <SelectItem key={ct} value={ct}>
                        {CHECK_TYPE_LABELS[ct] || ct}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="create_threshold">Threshold (days)</Label>
                <Input
                  id="create_threshold"
                  type="number"
                  min={0}
                  value={createForm.threshold_days}
                  onChange={(e) =>
                    setCreateForm((f) => ({ ...f, threshold_days: parseInt(e.target.value, 10) || 0 }))
                  }
                />
              </div>
              <div className="grid gap-2">
                <Label>Active</Label>
                <Select
                  value={createForm.is_active ? 'true' : 'false'}
                  onValueChange={(v) => setCreateForm((f) => ({ ...f, is_active: v === 'true' }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="true">Yes</SelectItem>
                    <SelectItem value="false">No</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>Priority</Label>
                <Select
                  value={createForm.priority}
                  onValueChange={(v) => setCreateForm((f) => ({ ...f, priority: v as ReminderPriority }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ReminderPriority.LOW}>Low</SelectItem>
                    <SelectItem value={ReminderPriority.MEDIUM}>Medium</SelectItem>
                    <SelectItem value={ReminderPriority.HIGH}>High</SelectItem>
                    <SelectItem value={ReminderPriority.URGENT}>Urgent</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>Suggested action</Label>
                <Select
                  value={createForm.suggested_action}
                  onValueChange={(v) => setCreateForm((f) => ({ ...f, suggested_action: v as SuggestedAction }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={SuggestedAction.FOLLOW_UP}>Follow up</SelectItem>
                    <SelectItem value={SuggestedAction.MARK_LOST}>Mark lost</SelectItem>
                    <SelectItem value={SuggestedAction.RESEND_QUOTE}>Resend quote</SelectItem>
                    <SelectItem value={SuggestedAction.REVIEW_QUOTE}>Review quote</SelectItem>
                    <SelectItem value={SuggestedAction.CONTACT_CUSTOMER}>Contact customer</SelectItem>
                    <SelectItem value={SuggestedAction.PHONE_CALL}>Phone call</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" type="button" onClick={() => setCreateDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="button" onClick={handleCreateSave} disabled={createSaving}>
                {createSaving ? 'Creating...' : 'Create rule'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Edit Rule</DialogTitle>
              <DialogDescription>
                {editingRule && formatRuleName(editingRule.rule_name)}
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="threshold_days">Threshold (days)</Label>
                <Input
                  id="threshold_days"
                  type="number"
                  min={0}
                  value={formData.threshold_days}
                  onChange={(e) => setFormData((f) => ({ ...f, threshold_days: parseInt(e.target.value, 10) || 0 }))}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="is_active">Active</Label>
                <Select
                  value={formData.is_active ? 'true' : 'false'}
                  onValueChange={(v) => setFormData((f) => ({ ...f, is_active: v === 'true' }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="true">Yes</SelectItem>
                    <SelectItem value="false">No</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="priority">Priority</Label>
                <Select
                  value={formData.priority}
                  onValueChange={(v) => setFormData((f) => ({ ...f, priority: v as ReminderPriority }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ReminderPriority.LOW}>Low</SelectItem>
                    <SelectItem value={ReminderPriority.MEDIUM}>Medium</SelectItem>
                    <SelectItem value={ReminderPriority.HIGH}>High</SelectItem>
                    <SelectItem value={ReminderPriority.URGENT}>Urgent</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="suggested_action">Suggested Action</Label>
                <Select
                  value={formData.suggested_action}
                  onValueChange={(v) => setFormData((f) => ({ ...f, suggested_action: v as SuggestedAction }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={SuggestedAction.FOLLOW_UP}>Follow up</SelectItem>
                    <SelectItem value={SuggestedAction.MARK_LOST}>Mark lost</SelectItem>
                    <SelectItem value={SuggestedAction.RESEND_QUOTE}>Resend quote</SelectItem>
                    <SelectItem value={SuggestedAction.REVIEW_QUOTE}>Review quote</SelectItem>
                    <SelectItem value={SuggestedAction.CONTACT_CUSTOMER}>Contact customer</SelectItem>
                    <SelectItem value={SuggestedAction.PHONE_CALL}>Phone call</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? 'Saving...' : 'Save'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}
