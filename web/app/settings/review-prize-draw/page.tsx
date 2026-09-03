'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import {
  addManualReviewPrizeDrawEntries,
  approveReviewPrizeDrawEntry,
  deleteManualReviewPrizeDrawEntry,
  getApiErrorDetail,
  getReviewPrizeDrawEntries,
  getReviewPrizeDrawWinner,
  pickReviewPrizeDrawWinner,
  rejectReviewPrizeDrawEntry,
  resetReviewPrizeDrawWinner,
} from '@/lib/api';
import { ReviewPrizeDrawEntryListItem, ReviewPrizeDrawWinner } from '@/lib/types';
import SendPrizeDrawCongratulationsDialog from '@/components/SendPrizeDrawCongratulationsDialog';
import { Gift, Plus, Send, Trash2, Trophy } from 'lucide-react';
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
  const [congratsDialogOpen, setCongratsDialogOpen] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [manualNames, setManualNames] = useState('');
  const [addingNames, setAddingNames] = useState(false);

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

  const handleAddManualNames = async () => {
    const names = manualNames
      .split('\n')
      .map((name) => name.trim())
      .filter(Boolean);
    if (names.length === 0) {
      toast.error('Enter at least one name');
      return;
    }

    try {
      setAddingNames(true);
      const result = await addManualReviewPrizeDrawEntries(month, names);
      const added = result.entries?.length ?? names.length;
      toast.success(added === 1 ? `Added ${result.entries[0].customer_name}` : `Added ${added} names`);
      setManualNames('');
      if (statusFilter === 'PENDING' || statusFilter === 'REJECTED') {
        setStatusFilter('ALL');
      } else {
        await load();
      }
    } catch (error: unknown) {
      toast.error(getApiErrorDetail(error) || 'Failed to add names');
    } finally {
      setAddingNames(false);
    }
  };

  const handleRemoveManual = async (entry: ReviewPrizeDrawEntryListItem) => {
    const confirmed = window.confirm(`Remove ${entry.customer_name} from the ${month} draw?`);
    if (!confirmed) return;

    try {
      setBusyId(entry.id);
      await deleteManualReviewPrizeDrawEntry(entry.id);
      toast.success(`Removed ${entry.customer_name}`);
      await load();
    } catch (error: unknown) {
      toast.error(getApiErrorDetail(error) || 'Failed to remove name');
    } finally {
      setBusyId(null);
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
            <CardTitle>Month</CardTitle>
            <CardDescription>
              Entries are listed by the month they were submitted. The winner is drawn from
              approved entries in this month&apos;s pool.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-4 items-end">
            <div className="space-y-2">
              <Label htmlFor="draw-month">Month entered (YYYY-MM)</Label>
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
                  {winner.is_manual
                    ? 'Manually added'
                    : `Order ${winner.order_number}${(winner.platforms_claimed || []).length ? ` · ${winner.platforms_claimed.join(', ')}` : ''}`}
                </p>
                <p className="text-xs text-muted-foreground">
                  Picked {new Date(winner.picked_at).toLocaleString('en-GB')}
                  {winner.picked_by_name ? ` by ${winner.picked_by_name}` : ''}
                </p>
                {winner.congratulations_sent_at ? (
                  <p className="text-xs text-teal-700 dark:text-teal-400">
                    Congratulations sent
                    {winner.congratulations_channel
                      ? ` by ${winner.congratulations_channel.toLowerCase()}`
                      : ''}{' '}
                    on {new Date(winner.congratulations_sent_at).toLocaleString('en-GB')}
                    {winner.congratulations_sent_by_name
                      ? ` by ${winner.congratulations_sent_by_name}`
                      : ''}
                  </p>
                ) : null}
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
                <>
                  {!winner.is_manual ? (
                    <Button
                      variant="secondary"
                      onClick={() => setCongratsDialogOpen(true)}
                      disabled={picking || resetting}
                    >
                      <Send className="h-4 w-4 mr-1" />
                      {winner.congratulations_sent_at ? 'Resend congratulations' : 'Send congratulations'}
                    </Button>
                  ) : null}
                  <Button
                    variant="outline"
                    onClick={() => void handleResetWinner()}
                    disabled={picking || resetting}
                  >
                    {resetting ? 'Resetting…' : 'Reset draw'}
                  </Button>
                </>
              ) : null}
            </div>
            {approvedCount === 0 && !winner ? (
              <p className="text-xs text-muted-foreground">No approved entries for {month}.</p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Entries {loading ? '' : `(${entries.length})`}</CardTitle>
            <CardDescription>
              Add extra names to this month&apos;s approved pool. They are included when you pick a
              winner. One name per line.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form
              className="flex flex-col sm:flex-row gap-2 sm:items-end"
              onSubmit={(e) => {
                e.preventDefault();
                void handleAddManualNames();
              }}
            >
              <div className="space-y-2 flex-1 min-w-0">
                <Label htmlFor="manual-names">Add names</Label>
                <Textarea
                  id="manual-names"
                  value={manualNames}
                  onChange={(e) => setManualNames(e.target.value)}
                  placeholder={"Jane Smith\nJohn Doe"}
                  rows={2}
                  disabled={addingNames}
                />
              </div>
              <Button type="submit" disabled={addingNames || !manualNames.trim()}>
                <Plus className="h-4 w-4 mr-1" />
                {addingNames ? 'Adding…' : 'Add to draw'}
              </Button>
            </form>
            {loading ? (
              <p className="text-muted-foreground text-sm">Loading…</p>
            ) : entries.length === 0 ? (
              <p className="text-muted-foreground text-sm">No entries match this filter.</p>
            ) : (
              <div className="space-y-3">
                {entries.map((entry) => (
                  <div key={entry.id} className="border rounded-lg p-4 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{entry.customer_name}</span>
                      <Badge variant="outline">{entry.status}</Badge>
                      {entry.is_manual ? <Badge variant="secondary">Manual</Badge> : null}
                      {entry.entry_month ? (
                        <span className="text-xs text-muted-foreground">Pool: {entry.entry_month}</span>
                      ) : null}
                    </div>
                    {entry.is_manual ? (
                      <p className="text-sm text-muted-foreground">Manually added</p>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        Order {entry.order_number} · {(entry.platforms_claimed || []).join(', ')}
                      </p>
                    )}
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
                    {entry.is_manual ? (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busyId === entry.id}
                        onClick={() => void handleRemoveManual(entry)}
                      >
                        <Trash2 className="h-4 w-4 mr-1" />
                        Remove
                      </Button>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </main>
      {winner && !winner.is_manual ? (
        <SendPrizeDrawCongratulationsDialog
          open={congratsDialogOpen}
          onOpenChange={setCongratsDialogOpen}
          month={month}
          winner={winner}
          onSuccess={() => void load()}
        />
      ) : null}
    </div>
  );
}
