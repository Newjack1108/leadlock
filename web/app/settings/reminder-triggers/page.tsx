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
import { Edit } from 'lucide-react';
import { getReminderRules, updateReminderRule } from '@/lib/api';
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
        <div className="mb-6">
          <h1 className="text-3xl font-semibold mb-2">Reminder Triggers</h1>
          <p className="text-muted-foreground">
            Configure when reminders are created for stale leads and quotes. Only Directors can edit.
          </p>
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
                      {isDirector && <th className="w-12" />}
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
                          <td className="py-2 px-2">
                            <Button variant="ghost" size="sm" onClick={() => handleEdit(rule)}>
                              <Edit className="h-4 w-4" />
                            </Button>
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
                  No reminder rules configured yet. Restart the API server to seed default rules.
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
                      {isDirector && <th className="w-12" />}
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
                          <td className="py-2 px-2">
                            <Button variant="ghost" size="sm" onClick={() => handleEdit(rule)}>
                              <Edit className="h-4 w-4" />
                            </Button>
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
