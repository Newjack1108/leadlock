'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  executeWeeklyPlanAuto,
  generateWeeklyPlan,
  getAssignableUsers,
  getLatestWeeklyPlan,
  getWeeklyPlanMetrics,
  updateWeeklyPlanItem,
} from '@/lib/api';
import { WeeklyPlanItem, WeeklyPlanItemStatus, WeeklyPlanListResponse } from '@/lib/types';
import { CheckCircle2, RefreshCw, XCircle } from 'lucide-react';
import { toast } from 'sonner';

type AssignableUser = { id: number; full_name: string; email: string };

export default function WeeklyPlanPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [busyItemId, setBusyItemId] = useState<number | null>(null);
  const [loadingRun, setLoadingRun] = useState(false);
  const [plan, setPlan] = useState<WeeklyPlanListResponse | null>(null);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [users, setUsers] = useState<AssignableUser[]>([]);

  const [ownerFilter, setOwnerFilter] = useState<string>('all');
  const [channelFilter, setChannelFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const loadData = async () => {
    try {
      setLoading(true);
      const [latestPlan, assignableUsers] = await Promise.all([
        getLatestWeeklyPlan(),
        getAssignableUsers().catch(() => []),
      ]);
      setPlan(latestPlan);
      setUsers(assignableUsers || []);
      if (latestPlan?.run?.id) {
        const metricsResult = await getWeeklyPlanMetrics(latestPlan.run.id).catch(() => null);
        setMetrics(metricsResult);
      } else {
        setMetrics(null);
      }
    } catch (error: any) {
      if (error?.response?.status === 401) {
        router.push('/login');
        return;
      }
      setPlan(null);
      setMetrics(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredItems = useMemo(() => {
    if (!plan?.items) return [];
    return plan.items.filter((item) => {
      if (ownerFilter !== 'all' && String(item.assigned_to_id || '') !== ownerFilter) return false;
      if (channelFilter !== 'all' && (item.channel || 'NONE') !== channelFilter) return false;
      if (statusFilter !== 'all' && item.status !== statusFilter) return false;
      return true;
    });
  }, [plan, ownerFilter, channelFilter, statusFilter]);

  const channels = useMemo(() => {
    const unique = new Set<string>();
    (plan?.items || []).forEach((item) => unique.add(item.channel || 'NONE'));
    return Array.from(unique);
  }, [plan]);

  const handleGenerate = async () => {
    try {
      setLoadingRun(true);
      const run = await generateWeeklyPlan({ auto_execute: true, dry_run: false });
      toast.success(`Weekly plan generated (${run.total_items} items)`);
      await loadData();
    } catch {
      toast.error('Failed to generate weekly plan');
    } finally {
      setLoadingRun(false);
    }
  };

  const handleRunAuto = async () => {
    if (!plan?.run?.id) return;
    try {
      setLoadingRun(true);
      const result = await executeWeeklyPlanAuto(plan.run.id);
      toast.success(result.message);
      await loadData();
    } catch {
      toast.error('Failed to execute auto actions');
    } finally {
      setLoadingRun(false);
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
      toast.success(successMessage);
      await loadData();
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
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={loadData}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            <Button variant="outline" onClick={handleGenerate} disabled={loadingRun}>
              {loadingRun ? 'Generating...' : 'Generate Weekly Plan'}
            </Button>
            <Button onClick={handleRunAuto} disabled={loadingRun || !plan?.run}>
              Run Auto Actions
            </Button>
          </div>
        </div>

        {plan?.run && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Week Start</CardTitle>
              </CardHeader>
              <CardContent className="text-xl font-semibold">{plan.run.week_start}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Items</CardTitle>
              </CardHeader>
              <CardContent className="text-xl font-semibold">{plan.run.total_items}</CardContent>
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
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Prioritized Items ({filteredItems.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {filteredItems.length === 0 ? (
              <p className="text-sm text-muted-foreground">No items match the selected filters.</p>
            ) : (
              filteredItems.map((item) => (
                <div key={item.id} className="border rounded-md p-3 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="text-sm font-medium">
                      Score {Number(item.priority_score).toFixed(1)} · {item.recommended_action}
                      {item.channel ? ` via ${item.channel}` : ''} · {item.status}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {item.assigned_to_name || 'Unassigned'} · {item.customer_name || item.lead_name || item.quote_number || 'Unknown target'}
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground">{(item.reason_codes || []).join(', ')}</div>
                  {item.suggested_message ? (
                    <div className="text-sm bg-muted/50 rounded p-2">{item.suggested_message}</div>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busyItemId === item.id}
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
                      disabled={busyItemId === item.id}
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
    </div>
  );
}
