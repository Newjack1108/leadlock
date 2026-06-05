'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  approveReviewPrizeDrawEntry,
  getReviewPrizeDrawEntries,
  getReviewPrizeDrawWinner,
  pickReviewPrizeDrawWinner,
  rejectReviewPrizeDrawEntry,
  resetReviewPrizeDrawWinner,
} from '@/lib/api';
import { ReviewPrizeDrawEntryListItem, ReviewPrizeDrawWinner } from '@/lib/types';
import { Gift, Trophy } from 'lucide-react';
import { toast } from 'sonner';

function currentMonthValue() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  return `${y}-${m}`;
}

export default function ReviewPrizeDrawPage() {
  const [month, setMonth] = useState(currentMonthValue);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [entries, setEntries] = useState<ReviewPrizeDrawEntryListItem[]>([]);
  const [approvedCount, setApprovedCount] = useState(0);
  const [winner, setWinner] = useState<ReviewPrizeDrawWinner | null>(null);
  const [loading, setLoading] = useState(true);
  const [picking, setPicking] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const params: { month: string; status?: string } = { month };
      if (statusFilter !== 'ALL') params.status = statusFilter;
      const [entriesRes, winnerRes] = await Promise.all([
        getReviewPrizeDrawEntries(params),
        getReviewPrizeDrawWinner(month),
      ]);
      setEntries(entriesRes.entries || []);
      setApprovedCount(entriesRes.approved_count ?? 0);
      setWinner(winnerRes);
    } catch {
      toast.error('Failed to load prize draw data');
    } finally {
      setLoading(false);
    }
  }, [month, statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredEntries = useMemo(() => {
    if (statusFilter === 'APPROVED') {
      return entries.filter((e) => e.status === 'APPROVED' && e.entry_month === month);
    }
    return entries;
  }, [entries, month, statusFilter]);

  const handleApprove = async (id: number) => {
    try {
      setBusyId(id);
      await approveReviewPrizeDrawEntry(id);
      toast.success('Entry approved');
      await load();
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      toast.error(detail || 'Failed to approve');
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (id: number) => {
    const note = window.prompt('Optional rejection note:') ?? undefined;
    try {
      setBusyId(id);
      await rejectReviewPrizeDrawEntry(id, note);
      toast.success('Entry rejected');
      await load();
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      toast.error(detail || 'Failed to reject');
    } finally {
      setBusyId(null);
    }
  };

  const handlePickWinner = async () => {
    try {
      setPicking(true);
      const result = await pickReviewPrizeDrawWinner(month);
      setWinner(result);
      toast.success(`Winner: ${result.customer_name}`);
      await load();
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      toast.error(detail || 'Could not pick winner');
    } finally {
      setPicking(false);
    }
  };

  const handleResetWinner = async () => {
    const confirmed = window.confirm(
      `Clear the picked winner for ${month}? Approved entries will stay eligible for a new draw.`
    );
    if (!confirmed) return;

    try {
      setResetting(true);
      await resetReviewPrizeDrawWinner(month);
      setWinner(null);
      toast.success(`Draw reset for ${month}`);
      await load();
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      toast.error(detail || 'Could not reset draw');
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-4 py-8 max-w-5xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Gift className="h-6 w-6 text-teal-600" />
            Review prize draw
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Approve customer entries and pick a random winner each month.{' '}
            <Link href="/settings/company" className="text-primary underline hover:no-underline">
              Configure in Company Settings
            </Link>
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Draw month</CardTitle>
            <CardDescription>Approved entries count toward the selected month.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-4 items-end">
            <div className="space-y-2">
              <Label htmlFor="draw-month">Month (YYYY-MM)</Label>
              <Input
                id="draw-month"
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                className="w-48"
              />
            </div>
            <div className="space-y-2">
              <Label>Filter</Label>
              <div className="flex flex-wrap gap-2">
                {(['ALL', 'PENDING', 'APPROVED', 'REJECTED'] as const).map((s) => (
                  <Button
                    key={s}
                    size="sm"
                    variant={statusFilter === s ? 'default' : 'outline'}
                    onClick={() => setStatusFilter(s)}
                  >
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Trophy className="h-5 w-5 text-amber-500" />
              Winner for {month}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {winner ? (
              <div className="rounded-md border p-4 space-y-1">
                <p className="font-medium">{winner.customer_name}</p>
                <p className="text-sm text-muted-foreground">
                  Order {winner.order_number} · {winner.platforms_claimed.join(', ')}
                </p>
                <p className="text-xs text-muted-foreground">
                  Picked {new Date(winner.picked_at).toLocaleString('en-GB')}
                  {winner.picked_by_name ? ` by ${winner.picked_by_name}` : ''}
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No winner picked yet for this month.</p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => void handlePickWinner()}
                disabled={picking || resetting || !!winner || approvedCount === 0}
              >
                {picking ? 'Picking…' : 'Pick random winner'}
              </Button>
              {winner ? (
                <Button
                  variant="outline"
                  onClick={() => void handleResetWinner()}
                  disabled={picking || resetting}
                >
                  {resetting ? 'Resetting…' : 'Reset draw'}
                </Button>
              ) : null}
            </div>
            {approvedCount === 0 && !winner ? (
              <p className="text-xs text-muted-foreground">No approved entries for {month}.</p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Entries {loading ? '' : `(${filteredEntries.length})`}</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-muted-foreground text-sm">Loading…</p>
            ) : filteredEntries.length === 0 ? (
              <p className="text-muted-foreground text-sm">No entries match this filter.</p>
            ) : (
              <div className="space-y-3">
                {filteredEntries.map((entry) => (
                  <div key={entry.id} className="border rounded-lg p-4 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{entry.customer_name}</span>
                      <Badge variant="outline">{entry.status}</Badge>
                      {entry.entry_month ? (
                        <span className="text-xs text-muted-foreground">Pool: {entry.entry_month}</span>
                      ) : null}
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Order {entry.order_number} · {(entry.platforms_claimed || []).join(', ')}
                    </p>
                    {entry.submitted_at ? (
                      <p className="text-xs text-muted-foreground">
                        Submitted {new Date(entry.submitted_at).toLocaleString('en-GB')}
                      </p>
                    ) : null}
                    {entry.status === 'PENDING' && entry.submitted_at ? (
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          disabled={busyId === entry.id}
                          onClick={() => void handleApprove(entry.id)}
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyId === entry.id}
                          onClick={() => void handleReject(entry.id)}
                        >
                          Reject
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
