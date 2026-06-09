'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import api, {
  generateWeeklyPlan,
  getApiErrorDetail,
  getAssignableUsers,
  getLatestWeeklyPlan,
  sendWeeklyPlanItem,
  sendWeeklyPlanItemsBulk,
  getWeeklyPlanMetrics,
  getWeeklyPlanTrend,
  updateWeeklyPlanItem,
} from '@/lib/api';
import ComposeEmailDialog from '@/components/ComposeEmailDialog';
import ComposeSmsDialog from '@/components/ComposeSmsDialog';
import { Badge } from '@/components/ui/badge';
import { Customer, WeeklyPlanItem, WeeklyPlanItemStatus, WeeklyPlanListResponse } from '@/lib/types';
import { CheckCircle2, Mail, MessageSquare, RefreshCw, User, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

type AssignableUser = { id: number; full_name: string; email: string };

const WEEKLY_PLAN_EMAIL_SUBJECT = 'Quick follow-up from LeadLock';
const WEEKLY_PLAN_AUTO_EXECUTE_STORAGE_KEY = 'll-weekly-plan-auto-execute';

function plainTextToEmailHtml(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return '';
  return trimmed
    .split(/\n\s*\n/)
    .map((para) => para.trim())
    .filter(Boolean)
    .map((para) => `<p>${para.replace(/\n/g, '<br>')}</p>`)
    .join('');
}

function isEditableMessageChannel(channel?: string | null): boolean {
  const upper = (channel || '').toUpperCase();
  return upper === 'SMS' || upper === 'EMAIL';
}

function canComposeEmail(item: WeeklyPlanItem): boolean {
  return item.customer_id != null && Boolean(item.customer_email?.trim());
}

function hasSmsStop(item: WeeklyPlanItem): boolean {
  return Boolean(item.customer_sms_bot_stopped);
}

function hasManualOutreachOptOut(item: WeeklyPlanItem): boolean {
  return Boolean(item.customer_automated_outreach_opt_out) && !item.customer_sms_bot_stopped;
}

function canComposeSms(item: WeeklyPlanItem): boolean {
  return item.customer_id != null && Boolean(item.customer_phone?.trim()) && !hasSmsStop(item);
}

function isSmsSendBlocked(item: WeeklyPlanItem): boolean {
  return (item.channel || '').toUpperCase() === 'SMS' && hasSmsStop(item);
}

function isDismissedWeeklyPlanStatus(status: WeeklyPlanItemStatus): boolean {
  return (
    status === WeeklyPlanItemStatus.COMPLETED ||
    status === WeeklyPlanItemStatus.REJECTED ||
    status === WeeklyPlanItemStatus.AUTO_SENT
  );
}

function buildMessageDrafts(items: WeeklyPlanItem[]): Record<number, string> {
  const drafts: Record<number, string> = {};
  for (const item of items) {
    drafts[item.id] = item.suggested_message || '';
  }
  return drafts;
}

export default function WeeklyPlanPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [busyItemId, setBusyItemId] = useState<number | null>(null);
  const [loadingRun, setLoadingRun] = useState(false);
  const [sendingBulk, setSendingBulk] = useState(false);
  const [plan, setPlan] = useState<WeeklyPlanListResponse | null>(null);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [trend, setTrend] = useState<Array<{ week_start: string; average_order_likelihood: number }>>([]);
  const [users, setUsers] = useState<AssignableUser[]>([]);
  const [messageDrafts, setMessageDrafts] = useState<Record<number, string>>({});

  const [ownerFilter, setOwnerFilter] = useState<string>('all');
  const [channelFilter, setChannelFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [likelihoodFilter, setLikelihoodFilter] = useState<string>('all');
  const [selectedItemIds, setSelectedItemIds] = useState<number[]>([]);
  const [autoExecuteOnGenerate, setAutoExecuteOnGenerate] = useState(false);

  const [composeEmailOpen, setComposeEmailOpen] = useState(false);
  const [composeCustomer, setComposeCustomer] = useState<Customer | null>(null);
  const [composeInitialSubject, setComposeInitialSubject] = useState('');
  const [composeInitialBody, setComposeInitialBody] = useState('');
  const composeEmailItemIdRef = useRef<number | null>(null);

  const [composeSmsOpen, setComposeSmsOpen] = useState(false);
  const [composeSmsCustomerId, setComposeSmsCustomerId] = useState<number | null>(null);
  const [composeSmsLeadId, setComposeSmsLeadId] = useState<number | null>(null);
  const [composeSmsPhone, setComposeSmsPhone] = useState('');
  const [composeSmsInitialBody, setComposeSmsInitialBody] = useState('');
  const composeSmsItemIdRef = useRef<number | null>(null);

  const resetComposeEmailState = () => {
    setComposeCustomer(null);
    setComposeInitialSubject('');
    setComposeInitialBody('');
  };

  const resetComposeSmsState = () => {
    setComposeSmsCustomerId(null);
    setComposeSmsLeadId(null);
    setComposeSmsPhone('');
    setComposeSmsInitialBody('');
  };

  const getItemDraft = useCallback(
    (item: WeeklyPlanItem) => messageDrafts[item.id] ?? item.suggested_message ?? '',
    [messageDrafts]
  );

  const setItemDraft = (itemId: number, value: string) => {
    setMessageDrafts((prev) => ({ ...prev, [itemId]: value }));
  };

  const saveDraftIfDirty = async (item: WeeklyPlanItem): Promise<void> => {
    const draft = getItemDraft(item).trim();
    const server = (item.suggested_message || '').trim();
    if (draft === server) return;
    await updateWeeklyPlanItem(item.id, { suggested_message: draft });
    setPlan((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((it) =>
          it.id === item.id ? { ...it, suggested_message: draft || null } : it
        ),
      };
    });
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const [latestPlan, assignableUsers] = await Promise.all([
        getLatestWeeklyPlan(),
        getAssignableUsers().catch(() => []),
      ]);
      setPlan(latestPlan);
      setMessageDrafts(buildMessageDrafts(latestPlan?.items || []));
      setUsers(assignableUsers || []);
      if (latestPlan?.run?.id) {
        const [metricsResult, trendResult] = await Promise.all([
          getWeeklyPlanMetrics(latestPlan.run.id).catch(() => null),
          getWeeklyPlanTrend(8).catch(() => ({ items: [] })),
        ]);
        setMetrics(metricsResult);
        setTrend(
          (trendResult?.items || []).map((item) => ({
            week_start: item.week_start,
            average_order_likelihood: Number(item.average_order_likelihood || 0),
          }))
        );
      } else {
        setMetrics(null);
        setTrend([]);
      }
      setSelectedItemIds([]);
    } catch (error: any) {
      if (error?.response?.status === 401) {
        router.push('/login');
        return;
      }
      setPlan(null);
      setMetrics(null);
      setMessageDrafts({});
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    try {
      setAutoExecuteOnGenerate(localStorage.getItem(WEEKLY_PLAN_AUTO_EXECUTE_STORAGE_KEY) === 'true');
    } catch {
      // ignore localStorage errors
    }
  }, []);

  const handleAutoExecuteToggle = (checked: boolean) => {
    setAutoExecuteOnGenerate(checked);
    try {
      localStorage.setItem(WEEKLY_PLAN_AUTO_EXECUTE_STORAGE_KEY, String(checked));
    } catch {
      // ignore localStorage errors
    }
  };

  const filteredItems = useMemo(() => {
    if (!plan?.items) return [];
    return plan.items.filter((item) => {
      if (statusFilter === 'all' && isDismissedWeeklyPlanStatus(item.status)) return false;
      if (ownerFilter !== 'all' && String(item.assigned_to_id || '') !== ownerFilter) return false;
      if (channelFilter !== 'all' && (item.channel || 'NONE') !== channelFilter) return false;
      if (statusFilter !== 'all' && item.status !== statusFilter) return false;
      if (likelihoodFilter !== 'all' && Number(item.order_likelihood_score || 0) < Number(likelihoodFilter)) return false;
      return true;
    });
  }, [plan, ownerFilter, channelFilter, statusFilter, likelihoodFilter]);

  const isItemSendable = (item: WeeklyPlanItem) =>
    item.status === WeeklyPlanItemStatus.PENDING_REVIEW && !isDismissedWeeklyPlanStatus(item.status);

  const sendableFilteredItems = useMemo(() => filteredItems.filter(isItemSendable), [filteredItems]);

  const channels = useMemo(() => {
    const unique = new Set<string>();
    (plan?.items || []).forEach((item) => unique.add(item.channel || 'NONE'));
    return Array.from(unique);
  }, [plan]);

  const outstandingItemsCount = useMemo(() => {
    if (!plan?.items) return 0;
    return plan.items.filter((item) => !isDismissedWeeklyPlanStatus(item.status)).length;
  }, [plan]);

  const refreshPlanMetrics = () => {
    if (!plan?.run?.id) return;
    getWeeklyPlanMetrics(plan.run.id)
      .then(setMetrics)
      .catch(() => null);
  };

  const removeItemsFromPlanView = (itemIds: number[]) => {
    if (itemIds.length === 0) return;
    const idSet = new Set(itemIds);
    setPlan((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.filter((it) => !idSet.has(it.id)),
      };
    });
    setMessageDrafts((prev) => {
      const next = { ...prev };
      for (const id of itemIds) {
        delete next[id];
      }
      return next;
    });
    setSelectedItemIds((prev) => prev.filter((id) => !idSet.has(id)));
    refreshPlanMetrics();
  };

  const handleGenerate = async () => {
    try {
      setLoadingRun(true);
      const run = await generateWeeklyPlan({ auto_execute: autoExecuteOnGenerate, dry_run: false });
      toast.success(
        autoExecuteOnGenerate
          ? `Weekly plan generated (${run.total_items} items, ${run.auto_sent_items} auto-sent)`
          : `Weekly plan generated (${run.total_items} items)`
      );
      await loadData();
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to generate weekly plan');
    } finally {
      setLoadingRun(false);
    }
  };

  const saveDraftsForItems = async (itemIds: number[]) => {
    if (!plan?.items) return;
    const items = plan.items.filter((it) => itemIds.includes(it.id));
    await Promise.all(items.map((item) => saveDraftIfDirty(item)));
  };

  const handleSendSelected = async () => {
    if (selectedItemIds.length === 0) return;
    try {
      setSendingBulk(true);
      await saveDraftsForItems(selectedItemIds);
      const result = await sendWeeklyPlanItemsBulk(selectedItemIds);
      toast.success(result.message);
      if (result.failed === 0 && result.sent > 0) {
        removeItemsFromPlanView(selectedItemIds);
      } else {
        await loadData();
      }
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to send selected items');
    } finally {
      setSendingBulk(false);
    }
  };

  const handleSendItem = async (item: WeeklyPlanItem) => {
    try {
      setBusyItemId(item.id);
      await saveDraftIfDirty(item);
      const updated = await sendWeeklyPlanItem(item.id);
      if (updated.status === WeeklyPlanItemStatus.AUTO_SENT) {
        const channel = (item.channel || '').toUpperCase();
        toast.success(channel === 'CALL' ? 'Call task logged' : 'Message sent');
        removeItemsFromPlanView([item.id]);
      } else {
        toast.error(updated.execution_error || 'Failed to send item');
        await loadData();
      }
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to send item');
    } finally {
      setBusyItemId(null);
    }
  };

  const handleComposeEmail = async (item: WeeklyPlanItem) => {
    if (!item.customer_id) return;
    try {
      setBusyItemId(item.id);
      const response = await api.get<Customer>(`/api/customers/${item.customer_id}`);
      const customer = response.data;
      if (!customer.email?.trim()) {
        toast.error('Customer has no email address');
        return;
      }
      composeEmailItemIdRef.current = item.id;
      setComposeInitialSubject(WEEKLY_PLAN_EMAIL_SUBJECT);
      setComposeInitialBody(plainTextToEmailHtml(getItemDraft(item)));
      setComposeCustomer(customer);
      setComposeEmailOpen(true);
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Failed to load customer');
    } finally {
      setBusyItemId(null);
    }
  };

  const handleComposeEmailOpenChange = (open: boolean) => {
    setComposeEmailOpen(open);
    if (!open) {
      resetComposeEmailState();
      window.setTimeout(() => {
        composeEmailItemIdRef.current = null;
      }, 200);
    }
  };

  const handleComposeEmailSuccess = async () => {
    const itemId = composeEmailItemIdRef.current;
    composeEmailItemIdRef.current = null;
    if (!itemId) return;
    try {
      setBusyItemId(itemId);
      await updateWeeklyPlanItem(itemId, {
        status: WeeklyPlanItemStatus.COMPLETED,
        outcome_result: 'completed_via_compose',
      });
      removeItemsFromPlanView([itemId]);
      toast.success('Email sent and item marked complete');
    } catch {
      toast.error('Email sent but failed to update weekly plan item');
    } finally {
      setBusyItemId(null);
    }
  };

  const handleComposeSms = (item: WeeklyPlanItem) => {
    if (!item.customer_id || !item.customer_phone?.trim()) return;
    composeSmsItemIdRef.current = item.id;
    setComposeSmsCustomerId(item.customer_id);
    setComposeSmsLeadId(item.lead_id ?? null);
    setComposeSmsPhone(item.customer_phone.trim());
    setComposeSmsInitialBody(getItemDraft(item));
    setComposeSmsOpen(true);
  };

  const handleComposeSmsOpenChange = (open: boolean) => {
    setComposeSmsOpen(open);
    if (!open) {
      resetComposeSmsState();
      window.setTimeout(() => {
        composeSmsItemIdRef.current = null;
      }, 200);
    }
  };

  const handleComposeSmsSuccess = async () => {
    const itemId = composeSmsItemIdRef.current;
    composeSmsItemIdRef.current = null;
    if (!itemId) return;
    try {
      setBusyItemId(itemId);
      await updateWeeklyPlanItem(itemId, {
        status: WeeklyPlanItemStatus.COMPLETED,
        outcome_result: 'completed_via_compose_sms',
      });
      removeItemsFromPlanView([itemId]);
      toast.success('SMS sent and item marked complete');
    } catch {
      toast.error('SMS sent but failed to update weekly plan item');
    } finally {
      setBusyItemId(null);
    }
  };

  const patchOutcome = async (
    item: WeeklyPlanItem,
    payload: { status?: WeeklyPlanItemStatus; response_received?: boolean; outcome_result?: string },
    successMessage: string
  ) => {
    try {
      setBusyItemId(item.id);
      await updateWeeklyPlanItem(item.id, payload);
      if (payload.status != null && isDismissedWeeklyPlanStatus(payload.status)) {
        removeItemsFromPlanView([item.id]);
      }
      toast.success(successMessage);
      if (payload.status == null || !isDismissedWeeklyPlanStatus(payload.status)) {
        await loadData();
      }
    } catch {
      toast.error('Failed to update outcome');
    } finally {
      setBusyItemId(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading weekly plan...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 sm:px-6 py-8 space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold mb-2">Weekly Plan</h1>
            <p className="text-muted-foreground">
              Prioritized AI recommendations with quick outcome updates.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoExecuteOnGenerate}
                onChange={(e) => handleAutoExecuteToggle(e.target.checked)}
                className="h-4 w-4 rounded border-input"
              />
              <span>
                Auto-send eligible items on generate
                <span className="block text-xs text-muted-foreground font-normal">
                  Sends up to 25 eligible SMS/email items without review
                </span>
              </span>
            </label>
            <Button variant="outline" onClick={loadData}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            <Button variant="outline" onClick={handleGenerate} disabled={loadingRun}>
              {loadingRun ? 'Generating...' : 'Generate Weekly Plan'}
            </Button>
            <Button onClick={handleSendSelected} disabled={sendingBulk || selectedItemIds.length === 0}>
              {sendingBulk ? 'Sending...' : `Send Selected (${selectedItemIds.length})`}
            </Button>
          </div>
        </div>

        {plan?.run && (
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Week Start</CardTitle>
              </CardHeader>
              <CardContent className="text-xl font-semibold">{plan.run.week_start}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Outstanding</CardTitle>
              </CardHeader>
              <CardContent className="text-xl font-semibold">{outstandingItemsCount}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Auto Sent</CardTitle>
              </CardHeader>
              <CardContent className="text-xl font-semibold">{plan.run.auto_sent_items}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Completion Rate</CardTitle>
              </CardHeader>
              <CardContent className="text-xl font-semibold">
                {Number(metrics?.completion_rate_pct || 0).toFixed(1)}%
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Avg Likelihood</CardTitle>
              </CardHeader>
              <CardContent className="text-xl font-semibold">
                {Number(metrics?.average_order_likelihood || 0).toFixed(1)}
              </CardContent>
            </Card>
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Filters</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            <Select value={ownerFilter} onValueChange={setOwnerFilter}>
              <SelectTrigger className="w-[220px]">
                <SelectValue placeholder="Owner" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All owners</SelectItem>
                {users.map((user) => (
                  <SelectItem key={user.id} value={String(user.id)}>
                    {user.full_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={channelFilter} onValueChange={setChannelFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Channel" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All channels</SelectItem>
                {channels.map((channel) => (
                  <SelectItem key={channel} value={channel}>
                    {channel}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[220px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {Object.values(WeeklyPlanItemStatus).map((status) => (
                  <SelectItem key={status} value={status}>
                    {status}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={likelihoodFilter} onValueChange={setLikelihoodFilter}>
              <SelectTrigger className="w-[220px]">
                <SelectValue placeholder="Min likelihood" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All likelihoods</SelectItem>
                <SelectItem value="25">Likelihood 25+</SelectItem>
                <SelectItem value="50">Likelihood 50+</SelectItem>
                <SelectItem value="70">Likelihood 70+</SelectItem>
                <SelectItem value="85">Likelihood 85+</SelectItem>
              </SelectContent>
            </Select>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Likelihood Trend (Week-over-Week Avg)</CardTitle>
          </CardHeader>
          <CardContent>
            {trend.length < 2 ? (
              <p className="text-sm text-muted-foreground">Not enough weekly runs yet to render trend.</p>
            ) : (
              <div className="w-full" style={{ height: 180 }}>
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={trend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis
                      dataKey="week_start"
                      tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                      tickFormatter={(value) => String(value).slice(5)}
                    />
                    <YAxis domain={[0, 100]} tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--card)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius)',
                      }}
                      formatter={(value: number | undefined) => [Number(value ?? 0).toFixed(1), 'Avg likelihood']}
                    />
                    <Line
                      type="monotone"
                      dataKey="average_order_likelihood"
                      stroke="#2563eb"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Prioritized Items ({filteredItems.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {filteredItems.length > 0 && sendableFilteredItems.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No sendable items under current filters. Only pending EMAIL/SMS items can be selected.
              </p>
            ) : null}
            {filteredItems.length === 0 ? (
              <p className="text-sm text-muted-foreground">No items match the selected filters.</p>
            ) : (
              filteredItems.map((item) => (
                <div key={item.id} className="border rounded-md p-3 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="text-sm font-medium flex items-center gap-2">
                      {isItemSendable(item) ? (
                        <input
                          type="checkbox"
                          checked={selectedItemIds.includes(item.id)}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            setSelectedItemIds((prev) =>
                              checked ? Array.from(new Set([...prev, item.id])) : prev.filter((id) => id !== item.id)
                            );
                          }}
                        />
                      ) : null}
                      Score {Number(item.priority_score).toFixed(1)} · {item.recommended_action}
                      {item.channel ? ` via ${item.channel}` : ''} · {item.status}
                      {hasSmsStop(item) ? (
                        <Badge
                          variant="destructive"
                          title="Customer opted out via STOP — do not send automated SMS"
                        >
                          SMS STOP
                        </Badge>
                      ) : null}
                      {hasManualOutreachOptOut(item) ? (
                        <Badge
                          variant="outline"
                          title="Automated reminder SMS/email stopped manually — manual messages still allowed"
                        >
                          No auto SMS
                        </Badge>
                      ) : null}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {item.assigned_to_name || 'Unassigned'} · {item.customer_name || item.lead_name || item.quote_number || 'Unknown target'}
                    </div>
                  </div>
                  <div className="text-xs">
                    Likelihood {Number(item.order_likelihood_score || 0).toFixed(1)} (conf {Number(item.order_likelihood_confidence || 0).toFixed(2)})
                  </div>
                  <div className="text-xs text-muted-foreground">{(item.reason_codes || []).join(', ')}</div>
                  {item.stale_source_label && item.stale_reference_at ? (
                    <div className="text-xs text-muted-foreground">
                      {item.days_stale != null ? `${item.days_stale}d since ` : 'Since '}
                      {item.stale_source_label} ·{' '}
                      {new Date(item.stale_reference_at).toLocaleDateString('en-GB', {
                        day: 'numeric',
                        month: 'short',
                        year: 'numeric',
                      })}
                    </div>
                  ) : null}
                  {(item.order_likelihood_reasons || []).length > 0 ? (
                    <div className="text-xs text-muted-foreground">AI/heuristic: {(item.order_likelihood_reasons || []).join(', ')}</div>
                  ) : null}
                  {item.likelihood_explanation ? (
                    <div className="text-sm bg-blue-50/50 dark:bg-blue-950/20 border border-blue-200/40 dark:border-blue-800/40 rounded p-2">
                      <span className="font-medium">Likelihood summary:</span> {item.likelihood_explanation}
                    </div>
                  ) : null}
                  {(item.recommended_next_steps || []).length > 0 ? (
                    <div className="text-sm border rounded p-2">
                      <div className="font-medium mb-1">Recommended next steps</div>
                      <ul className="list-disc pl-5 space-y-1 text-muted-foreground">
                        {(item.recommended_next_steps || []).map((step, idx) => (
                          <li key={`${item.id}-step-${idx}`}>{step}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {isEditableMessageChannel(item.channel) ? (
                    <div className="space-y-1">
                      <div className="text-xs font-medium text-muted-foreground">Suggested message</div>
                      <Textarea
                        value={getItemDraft(item)}
                        onChange={(e) => setItemDraft(item.id, e.target.value)}
                        rows={4}
                        className="text-sm bg-muted/50"
                        placeholder="Edit message before sending..."
                      />
                    </div>
                  ) : item.suggested_message ? (
                    <div className="text-sm bg-muted/50 rounded p-2">{item.suggested_message}</div>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    {item.customer_id != null ? (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          asChild
                          title={item.customer_name ? `Open ${item.customer_name}` : 'Open customer profile'}
                        >
                          <Link href={`/customers/${item.customer_id}`}>
                            <User className="h-4 w-4 mr-1" />
                            Customer profile
                          </Link>
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyItemId === item.id || !canComposeSms(item)}
                          onClick={() => handleComposeSms(item)}
                          title={
                            hasSmsStop(item)
                              ? 'Customer opted out via SMS STOP'
                              : canComposeSms(item)
                                ? 'Open SMS composer with suggested message'
                                : 'Customer has no phone number'
                          }
                        >
                          <MessageSquare className="h-4 w-4 mr-1" />
                          Compose SMS
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyItemId === item.id || !canComposeEmail(item)}
                          onClick={() => handleComposeEmail(item)}
                          title={
                            canComposeEmail(item)
                              ? 'Open email composer with suggested message'
                              : 'Customer has no email address'
                          }
                        >
                          <Mail className="h-4 w-4 mr-1" />
                          Compose email
                        </Button>
                      </>
                    ) : null}
                    <Button
                      size="sm"
                      disabled={
                        busyItemId === item.id ||
                        !isItemSendable(item) ||
                        isSmsSendBlocked(item) ||
                        isDismissedWeeklyPlanStatus(item.status)
                      }
                      onClick={() => handleSendItem(item)}
                      title={
                        isSmsSendBlocked(item)
                          ? 'Customer opted out via SMS STOP'
                          : isItemSendable(item)
                            ? 'Send or log this action now'
                            : 'Only pending review items can be sent'
                      }
                    >
                      Send now
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busyItemId === item.id || isDismissedWeeklyPlanStatus(item.status)}
                      onClick={() =>
                        patchOutcome(
                          item,
                          { status: WeeklyPlanItemStatus.COMPLETED, outcome_result: 'completed_manually' },
                          'Marked as completed'
                        )
                      }
                    >
                      <CheckCircle2 className="h-4 w-4 mr-1" />
                      Complete
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busyItemId === item.id || isDismissedWeeklyPlanStatus(item.status)}
                      onClick={() =>
                        patchOutcome(
                          item,
                          { status: WeeklyPlanItemStatus.REJECTED, outcome_result: 'rejected_by_user' },
                          'Marked as rejected'
                        )
                      }
                    >
                      <XCircle className="h-4 w-4 mr-1" />
                      Reject
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busyItemId === item.id}
                      onClick={() =>
                        patchOutcome(
                          item,
                          { response_received: true, outcome_result: 'customer_replied' },
                          'Marked response received'
                        )
                      }
                    >
                      Mark Replied
                    </Button>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </main>

      {composeCustomer && (
        <ComposeEmailDialog
          open={composeEmailOpen}
          onOpenChange={handleComposeEmailOpenChange}
          customer={composeCustomer}
          initialSubject={composeInitialSubject}
          initialBody={composeInitialBody}
          onSuccess={handleComposeEmailSuccess}
        />
      )}

      {composeSmsCustomerId != null && (
        <ComposeSmsDialog
          open={composeSmsOpen}
          onOpenChange={handleComposeSmsOpenChange}
          customerId={composeSmsCustomerId}
          leadId={composeSmsLeadId}
          toPhone={composeSmsPhone}
          initialBody={composeSmsInitialBody}
          onSuccess={handleComposeSmsSuccess}
        />
      )}
    </div>
  );
}
