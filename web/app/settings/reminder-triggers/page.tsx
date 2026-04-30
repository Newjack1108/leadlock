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
import { Badge } from '@/components/ui/badge';
import { Edit, Plus, Trash2 } from 'lucide-react';
import {
  getReminderRules,
  updateReminderRule,
  createReminderRule,
  deleteReminderRule,
  getOutreachSends,
  getSmsTemplates,
  getEmailTemplates,
} from '@/lib/api';
import {
  ReminderRule,
  ReminderRuleUpdate,
  ReminderPriority,
  SuggestedAction,
  OutreachSendListItem,
  OutreachSendTargetType,
  SmsTemplate,
  EmailTemplate,
} from '@/lib/types';
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
const OUTREACH_NONE = 'NONE';

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
    threshold_minutes: 0,
    is_active: true,
    priority: ReminderPriority.MEDIUM,
    suggested_action: SuggestedAction.FOLLOW_UP,
    outreach_channel: OUTREACH_NONE as typeof OUTREACH_NONE | 'SMS' | 'EMAIL',
    outreach_sms_template_id: null as number | null,
    outreach_email_template_id: null as number | null,
    outreach_cooldown_days: 14,
    outreach_on_lead_create: false,
  });
  const [smsTemplates, setSmsTemplates] = useState<SmsTemplate[]>([]);
  const [emailTemplates, setEmailTemplates] = useState<EmailTemplate[]>([]);
  const [saving, setSaving] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createSaving, setCreateSaving] = useState(false);
  const [outreachSends, setOutreachSends] = useState<OutreachSendListItem[]>([]);
  const [outreachLoading, setOutreachLoading] = useState(false);
  const [outreachTotal, setOutreachTotal] = useState(0);
  const [outreachPage, setOutreachPage] = useState(1);
  const [outreachChannelFilter, setOutreachChannelFilter] = useState<'ALL' | 'SMS' | 'EMAIL'>('ALL');
  const [outreachTargetFilter, setOutreachTargetFilter] = useState<'ALL' | OutreachSendTargetType>('ALL');
  const OUTREACH_PAGE_SIZE = 10;
  const [createForm, setCreateForm] = useState({
    rule_name: '',
    entity_type: 'LEAD' as 'LEAD' | 'QUOTE',
    status: 'NEW' as string,
    check_type: 'LAST_ACTIVITY' as string,
    threshold_minutes: 10080,
    is_active: true,
    priority: ReminderPriority.MEDIUM,
    suggested_action: SuggestedAction.FOLLOW_UP,
    outreach_channel: OUTREACH_NONE as typeof OUTREACH_NONE | 'SMS' | 'EMAIL',
    outreach_sms_template_id: null as number | null,
    outreach_email_template_id: null as number | null,
    outreach_cooldown_days: 14,
    outreach_on_lead_create: false,
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

  useEffect(() => {
    fetchOutreachSends();
  }, [outreachPage, outreachChannelFilter, outreachTargetFilter]);

  useEffect(() => {
    if (!isDirector) return;
    const loadTemplates = async () => {
      try {
        const [sms, email] = await Promise.all([getSmsTemplates(), getEmailTemplates()]);
        setSmsTemplates(sms);
        setEmailTemplates(email);
      } catch {
        toast.error('Failed to load templates for outreach settings');
      }
    };
    loadTemplates();
  }, [isDirector]);

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

  const fetchOutreachSends = async () => {
    try {
      setOutreachLoading(true);
      const data = await getOutreachSends({
        channel: outreachChannelFilter === 'ALL' ? undefined : outreachChannelFilter,
        target_type: outreachTargetFilter === 'ALL' ? undefined : outreachTargetFilter,
        page: outreachPage,
        page_size: OUTREACH_PAGE_SIZE,
      });
      setOutreachSends(data.items || []);
      setOutreachTotal(data.total || 0);
    } catch {
      toast.error('Failed to load automated outreach sends');
      setOutreachSends([]);
      setOutreachTotal(0);
    } finally {
      setOutreachLoading(false);
    }
  };

  const handleEdit = (rule: ReminderRule) => {
    setEditingRule(rule);
    const ch = rule.customer_outreach_channel;
    setFormData({
      threshold_minutes: rule.threshold_minutes,
      is_active: rule.is_active,
      priority: rule.priority,
      suggested_action: rule.suggested_action,
      outreach_channel: ch === 'SMS' ? 'SMS' : ch === 'EMAIL' ? 'EMAIL' : OUTREACH_NONE,
      outreach_sms_template_id: rule.customer_outreach_sms_template_id ?? null,
      outreach_email_template_id: rule.customer_outreach_email_template_id ?? null,
      outreach_cooldown_days: rule.customer_outreach_cooldown_days ?? 14,
      outreach_on_lead_create: rule.customer_outreach_on_lead_create ?? false,
    });
    setEditDialogOpen(true);
  };

  const handleSave = async () => {
    if (!editingRule) return;
    if (formData.outreach_channel === 'SMS' && formData.outreach_sms_template_id == null) {
      toast.error('Choose an SMS template for customer outreach');
      return;
    }
    if (formData.outreach_channel === 'EMAIL' && formData.outreach_email_template_id == null) {
      toast.error('Choose an email template for customer outreach');
      return;
    }
    try {
      setSaving(true);
      const update: ReminderRuleUpdate = {
        threshold_minutes: formData.threshold_minutes,
        is_active: formData.is_active,
        priority: formData.priority,
        suggested_action: formData.suggested_action,
      };
      if (formData.outreach_channel === OUTREACH_NONE) {
        update.customer_outreach_channel = null;
        update.customer_outreach_on_lead_create = false;
      } else {
        update.customer_outreach_channel = formData.outreach_channel;
        update.customer_outreach_sms_template_id =
          formData.outreach_channel === 'SMS' ? formData.outreach_sms_template_id : null;
        update.customer_outreach_email_template_id =
          formData.outreach_channel === 'EMAIL' ? formData.outreach_email_template_id : null;
        update.customer_outreach_cooldown_days = formData.outreach_cooldown_days;
        if (editingRule.entity_type === 'LEAD') {
          update.customer_outreach_on_lead_create = formData.outreach_on_lead_create;
        }
      }
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
      threshold_minutes: 10080,
      is_active: true,
      priority: ReminderPriority.MEDIUM,
      suggested_action: SuggestedAction.FOLLOW_UP,
      outreach_channel: OUTREACH_NONE,
      outreach_sms_template_id: null,
      outreach_email_template_id: null,
      outreach_cooldown_days: 14,
      outreach_on_lead_create: false,
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
    if (createForm.outreach_channel === 'SMS' && createForm.outreach_sms_template_id == null) {
      toast.error('Choose an SMS template for customer outreach');
      return;
    }
    if (createForm.outreach_channel === 'EMAIL' && createForm.outreach_email_template_id == null) {
      toast.error('Choose an email template for customer outreach');
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
        threshold_minutes: createForm.threshold_minutes,
        check_type: createForm.check_type,
        is_active: createForm.is_active,
        priority: createForm.priority,
        suggested_action: createForm.suggested_action,
        status: statusPayload,
        ...(createForm.outreach_channel !== OUTREACH_NONE
          ? {
              customer_outreach_channel: createForm.outreach_channel,
              customer_outreach_sms_template_id:
                createForm.outreach_channel === 'SMS' ? createForm.outreach_sms_template_id : null,
              customer_outreach_email_template_id:
                createForm.outreach_channel === 'EMAIL' ? createForm.outreach_email_template_id : null,
              customer_outreach_cooldown_days: createForm.outreach_cooldown_days,
              ...(createForm.entity_type === 'LEAD' && createForm.outreach_on_lead_create
                ? { customer_outreach_on_lead_create: true }
                : {}),
            }
          : {}),
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
        <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold mb-2">Reminder Triggers</h1>
            <p className="text-muted-foreground">
              Configure when reminders are created for stale leads and quotes. Only Directors can create, edit, or delete.
              New rules must use check types the engine already supports (see form options). You can optionally send a
              customer-facing SMS or email when stale thresholds match; the server runs that on a timer (not when you
              click Generate Reminders), with a cooldown per rule to limit repeat sends. For lead rules with outreach
              enabled, you can also send once immediately when a new lead is created in the matching status (for example a
              thank-you SMS). You are responsible for consent and compliance.
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
              <CardTitle>Automated Outreach Sends</CardTitle>
              <CardDescription>
                SMS and email messages sent automatically by reminder rule outreach.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="grid gap-2">
                  <Label>Channel</Label>
                  <Select
                    value={outreachChannelFilter}
                    onValueChange={(v) => {
                      setOutreachChannelFilter(v as 'ALL' | 'SMS' | 'EMAIL');
                      setOutreachPage(1);
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ALL">All channels</SelectItem>
                      <SelectItem value="SMS">SMS</SelectItem>
                      <SelectItem value="EMAIL">Email</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-2">
                  <Label>Target type</Label>
                  <Select
                    value={outreachTargetFilter}
                    onValueChange={(v) => {
                      setOutreachTargetFilter(v as 'ALL' | OutreachSendTargetType);
                      setOutreachPage(1);
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ALL">All targets</SelectItem>
                      <SelectItem value="LEAD">Lead</SelectItem>
                      <SelectItem value="QUOTE">Quote</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2 px-2 font-medium">Sent</th>
                      <th className="text-left py-2 px-2 font-medium">Status</th>
                      <th className="text-left py-2 px-2 font-medium">Channel</th>
                      <th className="text-left py-2 px-2 font-medium">Target</th>
                      <th className="text-left py-2 px-2 font-medium">Customer</th>
                      <th className="text-left py-2 px-2 font-medium">Lead</th>
                      <th className="text-left py-2 px-2 font-medium">Quote</th>
                      <th className="text-left py-2 px-2 font-medium">Rule</th>
                    </tr>
                  </thead>
                  <tbody>
                    {outreachLoading ? (
                      <tr>
                        <td colSpan={8} className="py-4 px-2 text-muted-foreground">
                          Loading outreach sends...
                        </td>
                      </tr>
                    ) : outreachSends.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="py-4 px-2 text-muted-foreground">
                          No automated outreach sends found for the selected filters.
                        </td>
                      </tr>
                    ) : (
                      outreachSends.map((send) => (
                        <tr key={send.id} className="border-b last:border-0">
                          <td className="py-2 px-2">{new Date(send.sent_at).toLocaleString('en-GB')}</td>
                          <td className="py-2 px-2">
                            <div className="flex flex-col gap-1">
                              <Badge variant={send.status === 'FAILED' ? 'destructive' : 'secondary'} className="w-fit">
                                {send.status}
                              </Badge>
                              {send.status === 'FAILED' && send.failure_reason ? (
                                <span className="text-xs text-muted-foreground">{send.failure_reason}</span>
                              ) : null}
                            </div>
                          </td>
                          <td className="py-2 px-2">{send.channel}</td>
                          <td className="py-2 px-2">{send.target_type}</td>
                          <td className="py-2 px-2">{send.customer_name || `#${send.customer_id}`}</td>
                          <td className="py-2 px-2">{send.lead_name || (send.lead_id ? `#${send.lead_id}` : '—')}</td>
                          <td className="py-2 px-2">{send.quote_number || (send.quote_id ? `#${send.quote_id}` : '—')}</td>
                          <td className="py-2 px-2">{formatRuleName(send.reminder_rule_name)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between gap-3">
                <p className="text-xs text-muted-foreground">
                  Showing {outreachSends.length} of {outreachTotal}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={outreachPage <= 1 || outreachLoading}
                    onClick={() => setOutreachPage((p) => Math.max(1, p - 1))}
                  >
                    Previous
                  </Button>
                  <span className="text-xs text-muted-foreground">Page {outreachPage}</span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={outreachLoading || outreachPage * OUTREACH_PAGE_SIZE >= outreachTotal}
                    onClick={() => setOutreachPage((p) => p + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

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
                      <th className="text-left py-2 px-2 font-medium">Minimum whole minutes</th>
                      <th className="text-left py-2 px-2 font-medium">Active</th>
                      <th className="text-left py-2 px-2 font-medium">Priority</th>
                      <th className="text-left py-2 px-2 font-medium">Action</th>
                      <th className="text-left py-2 px-2 font-medium">Customer auto</th>
                      {isDirector && <th className="text-right py-2 px-2 font-medium">Manage</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {leadRules.map((rule) => (
                      <tr key={rule.id} className="border-b last:border-0">
                        <td className="py-2 px-2">{formatRuleName(rule.rule_name)}</td>
                        <td className="py-2 px-2">{rule.status || '-'}</td>
                        <td className="py-2 px-2">{CHECK_TYPE_LABELS[rule.check_type] || rule.check_type}</td>
                        <td className="py-2 px-2 tabular-nums">
                          {rule.threshold_minutes}
                          <span className="text-muted-foreground"> min</span>
                        </td>
                        <td className="py-2 px-2">{rule.is_active ? 'Yes' : 'No'}</td>
                        <td className="py-2 px-2">{rule.priority}</td>
                        <td className="py-2 px-2">{rule.suggested_action.replace(/_/g, ' ')}</td>
                        <td className="py-2 px-2 text-muted-foreground">
                          <span className="block">{rule.customer_outreach_channel || '—'}</span>
                          {rule.customer_outreach_on_lead_create ? (
                            <span className="text-xs">Also on new lead</span>
                          ) : null}
                        </td>
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
                      <th className="text-left py-2 px-2 font-medium">Minimum whole minutes</th>
                      <th className="text-left py-2 px-2 font-medium">Active</th>
                      <th className="text-left py-2 px-2 font-medium">Priority</th>
                      <th className="text-left py-2 px-2 font-medium">Action</th>
                      <th className="text-left py-2 px-2 font-medium">Customer auto</th>
                      {isDirector && <th className="text-right py-2 px-2 font-medium">Manage</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {quoteRules.map((rule) => (
                      <tr key={rule.id} className="border-b last:border-0">
                        <td className="py-2 px-2">{formatRuleName(rule.rule_name)}</td>
                        <td className="py-2 px-2">{rule.status || '-'}</td>
                        <td className="py-2 px-2">{CHECK_TYPE_LABELS[rule.check_type] || rule.check_type}</td>
                        <td className="py-2 px-2 tabular-nums">
                          {rule.threshold_minutes}
                          <span className="text-muted-foreground"> min</span>
                        </td>
                        <td className="py-2 px-2">{rule.is_active ? 'Yes' : 'No'}</td>
                        <td className="py-2 px-2">{rule.priority}</td>
                        <td className="py-2 px-2">{rule.suggested_action.replace(/_/g, ' ')}</td>
                        <td className="py-2 px-2 text-muted-foreground">
                          {rule.customer_outreach_channel || '—'}
                        </td>
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
                      outreach_on_lead_create: et === 'LEAD' ? f.outreach_on_lead_create : false,
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
                <Label htmlFor="create_threshold">Minimum whole minutes</Label>
                <div className="flex items-center gap-2">
                  <Input
                    id="create_threshold"
                    type="number"
                    min={0}
                    className="max-w-[10rem]"
                    value={createForm.threshold_minutes}
                    onChange={(e) =>
                      setCreateForm((f) => ({ ...f, threshold_minutes: parseInt(e.target.value, 10) || 0 }))
                    }
                    aria-describedby="create_threshold_hint"
                  />
                  <span id="create_threshold_hint" className="text-sm text-muted-foreground shrink-0">
                    minutes (not hours)
                  </span>
                </div>
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
              {isDirector && (
                <>
                  <div className="rounded-md border p-3 space-y-3 bg-muted/30">
                    <p className="text-sm font-medium">Customer outreach (optional)</p>
                    <p className="text-xs text-muted-foreground">
                      Stale matching uses the timer worker; optional immediate send runs when a new lead is saved (webhook
                      or app). Cooldown limits repeats.
                    </p>
                    <div className="grid gap-2">
                      <Label>Channel</Label>
                      <Select
                        value={createForm.outreach_channel}
                        onValueChange={(v) =>
                          setCreateForm((f) => ({
                            ...f,
                            outreach_channel: v as typeof OUTREACH_NONE | 'SMS' | 'EMAIL',
                            outreach_on_lead_create: v === OUTREACH_NONE ? false : f.outreach_on_lead_create,
                          }))
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={OUTREACH_NONE}>None</SelectItem>
                          <SelectItem value="SMS">SMS</SelectItem>
                          <SelectItem value="EMAIL">Email</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    {createForm.outreach_channel === 'SMS' && (
                      <div className="grid gap-2">
                        <Label>SMS template</Label>
                        <Select
                          value={
                            createForm.outreach_sms_template_id != null
                              ? String(createForm.outreach_sms_template_id)
                              : 'none'
                          }
                          onValueChange={(v) =>
                            setCreateForm((f) => ({
                              ...f,
                              outreach_sms_template_id: v === 'none' ? null : parseInt(v, 10),
                            }))
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Choose template" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">Choose template</SelectItem>
                            {smsTemplates.map((t) => (
                              <SelectItem key={t.id} value={String(t.id!)}>
                                {t.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                    {createForm.outreach_channel === 'EMAIL' && (
                      <div className="grid gap-2">
                        <Label>Email template</Label>
                        <Select
                          value={
                            createForm.outreach_email_template_id != null
                              ? String(createForm.outreach_email_template_id)
                              : 'none'
                          }
                          onValueChange={(v) =>
                            setCreateForm((f) => ({
                              ...f,
                              outreach_email_template_id: v === 'none' ? null : parseInt(v, 10),
                            }))
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Choose template" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">Choose template</SelectItem>
                            {emailTemplates.map((t) => (
                              <SelectItem key={t.id} value={String(t.id!)}>
                                {t.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                    {createForm.outreach_channel !== OUTREACH_NONE && (
                      <div className="grid gap-2">
                        <Label htmlFor="create_cooldown">Cooldown (days)</Label>
                        <Input
                          id="create_cooldown"
                          type="number"
                          min={0}
                          value={createForm.outreach_cooldown_days}
                          onChange={(e) =>
                            setCreateForm((f) => ({
                              ...f,
                              outreach_cooldown_days: parseInt(e.target.value, 10) || 0,
                            }))
                          }
                        />
                      </div>
                    )}
                    {createForm.entity_type === 'LEAD' && createForm.outreach_channel !== OUTREACH_NONE && (
                      <label className="flex items-start gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          className="mt-0.5 rounded border-input"
                          checked={createForm.outreach_on_lead_create}
                          onChange={(e) =>
                            setCreateForm((f) => ({ ...f, outreach_on_lead_create: e.target.checked }))
                          }
                        />
                        <span>
                          Send immediately when a new lead is created in this rule&apos;s status (in addition to stale
                          reminders).
                        </span>
                      </label>
                    )}
                  </div>
                </>
              )}
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
                <Label htmlFor="threshold_minutes">Minimum whole minutes</Label>
                <div className="flex items-center gap-2">
                  <Input
                    id="threshold_minutes"
                    type="number"
                    min={0}
                    className="max-w-[10rem]"
                    value={formData.threshold_minutes}
                    onChange={(e) =>
                      setFormData((f) => ({ ...f, threshold_minutes: parseInt(e.target.value, 10) || 0 }))
                    }
                    aria-describedby="edit_threshold_hint"
                  />
                  <span id="edit_threshold_hint" className="text-sm text-muted-foreground shrink-0">
                    minutes (not hours)
                  </span>
                </div>
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
              <div className="rounded-md border p-3 space-y-3 bg-muted/30">
                <p className="text-sm font-medium">Customer outreach (optional)</p>
                <p className="text-xs text-muted-foreground">
                  Stale matching uses the timer worker; optional immediate send runs when a new lead is saved. Cooldown
                  limits repeats.
                </p>
                <div className="grid gap-2">
                  <Label>Channel</Label>
                  <Select
                    value={formData.outreach_channel}
                    onValueChange={(v) =>
                      setFormData((f) => ({
                        ...f,
                        outreach_channel: v as typeof OUTREACH_NONE | 'SMS' | 'EMAIL',
                        outreach_on_lead_create: v === OUTREACH_NONE ? false : f.outreach_on_lead_create,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={OUTREACH_NONE}>None</SelectItem>
                      <SelectItem value="SMS">SMS</SelectItem>
                      <SelectItem value="EMAIL">Email</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {formData.outreach_channel === 'SMS' && (
                  <div className="grid gap-2">
                    <Label>SMS template</Label>
                    <Select
                      value={
                        formData.outreach_sms_template_id != null
                          ? String(formData.outreach_sms_template_id)
                          : 'none'
                      }
                      onValueChange={(v) =>
                        setFormData((f) => ({
                          ...f,
                          outreach_sms_template_id: v === 'none' ? null : parseInt(v, 10),
                        }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Choose template" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">Choose template</SelectItem>
                        {smsTemplates.map((t) => (
                          <SelectItem key={t.id} value={String(t.id!)}>
                            {t.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                {formData.outreach_channel === 'EMAIL' && (
                  <div className="grid gap-2">
                    <Label>Email template</Label>
                    <Select
                      value={
                        formData.outreach_email_template_id != null
                          ? String(formData.outreach_email_template_id)
                          : 'none'
                      }
                      onValueChange={(v) =>
                        setFormData((f) => ({
                          ...f,
                          outreach_email_template_id: v === 'none' ? null : parseInt(v, 10),
                        }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Choose template" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">Choose template</SelectItem>
                        {emailTemplates.map((t) => (
                          <SelectItem key={t.id} value={String(t.id!)}>
                            {t.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                {formData.outreach_channel !== OUTREACH_NONE && (
                  <div className="grid gap-2">
                    <Label htmlFor="edit_cooldown">Cooldown (days)</Label>
                    <Input
                      id="edit_cooldown"
                      type="number"
                      min={0}
                      value={formData.outreach_cooldown_days}
                      onChange={(e) =>
                        setFormData((f) => ({
                          ...f,
                          outreach_cooldown_days: parseInt(e.target.value, 10) || 0,
                        }))
                      }
                    />
                  </div>
                )}
                {editingRule?.entity_type === 'LEAD' && formData.outreach_channel !== OUTREACH_NONE && (
                  <label className="flex items-start gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      className="mt-0.5 rounded border-input"
                      checked={formData.outreach_on_lead_create}
                      onChange={(e) =>
                        setFormData((f) => ({ ...f, outreach_on_lead_create: e.target.checked }))
                      }
                    />
                    <span>
                      Send immediately when a new lead is created in this rule&apos;s status (in addition to stale
                      reminders).
                    </span>
                  </label>
                )}
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
