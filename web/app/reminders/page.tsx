'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import ReminderList from '@/components/ReminderList';
import CreateTaskDialog from '@/components/CreateTaskDialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getStaleSummary, generateReminders } from '@/lib/api';
import { ReminderPriority, ReminderType, StaleSummary } from '@/lib/types';
import { toast } from 'sonner';
import { RefreshCw, ChevronDown, ChevronUp, ListTodo } from 'lucide-react';

export default function RemindersPage() {
  const router = useRouter();
  const [summary, setSummary] = useState<StaleSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [filterPriority, setFilterPriority] = useState<string>('all');
  const [filterType, setFilterType] = useState<string>('all');
  const [assignedScope, setAssignedScope] = useState<'mine' | 'all'>('all');
  const [createTaskOpen, setCreateTaskOpen] = useState(false);
  const [doneExpanded, setDoneExpanded] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const fetchData = async () => {
    try {
      setLoading(true);
      const summaryData = await getStaleSummary();
      setSummary(summaryData);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleGenerate = async () => {
    try {
      setGenerating(true);
      const result = await generateReminders();
      toast.success(`Generated ${result.count} reminders`);
      fetchData();
      setRefreshTrigger((t) => t + 1);
    } catch (error: any) {
      toast.error('Failed to generate reminders');
      console.error('Error generating reminders:', error);
    } finally {
      setGenerating(false);
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
        <div className="mb-6">
          <h1 className="text-3xl font-semibold mb-2">Reminders & Tasks</h1>
          <p className="text-muted-foreground">
            Track and manage stale leads and quotes that need attention
          </p>
        </div>

        {/* Summary Cards */}
        {summary && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Total Reminders</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{summary.total_reminders}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Urgent</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-red-600">{summary.urgent_count}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Stale Leads</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{summary.stale_leads_count}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Stale Quotes</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{summary.stale_quotes_count}</div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Filters and Actions */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-4">
            <Select value={assignedScope} onValueChange={(v) => setAssignedScope(v as 'mine' | 'all')}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Scope" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="mine">Assigned to me</SelectItem>
                <SelectItem value="all">Everyone (visible)</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filterPriority} onValueChange={setFilterPriority}>
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder="Priority" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Priorities</SelectItem>
                <SelectItem value={ReminderPriority.URGENT}>Urgent</SelectItem>
                <SelectItem value={ReminderPriority.HIGH}>High</SelectItem>
                <SelectItem value={ReminderPriority.MEDIUM}>Medium</SelectItem>
                <SelectItem value={ReminderPriority.LOW}>Low</SelectItem>
              </SelectContent>
            </Select>
            <Select value={filterType} onValueChange={setFilterType}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                <SelectItem value={ReminderType.LEAD_STALE}>Stale Leads</SelectItem>
                <SelectItem value={ReminderType.QUOTE_STALE}>Stale Quotes</SelectItem>
                <SelectItem value={ReminderType.QUOTE_EXPIRED}>Expired Quotes</SelectItem>
                <SelectItem value={ReminderType.QUOTE_EXPIRING}>Expiring Quotes</SelectItem>
                <SelectItem value={ReminderType.QUOTE_NOT_OPENED}>Quote not opened (48h)</SelectItem>
                <SelectItem value={ReminderType.QUOTE_OPENED_NO_REPLY}>Quote opened, no reply</SelectItem>
                <SelectItem value={ReminderType.MANUAL}>Manual (customer)</SelectItem>
                <SelectItem value={ReminderType.USER_TASK}>User tasks</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setCreateTaskOpen(true)}>
              <ListTodo className="h-4 w-4 mr-2" />
              Create task
            </Button>
            <Button
              variant="outline"
              onClick={fetchData}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            <Button
              onClick={handleGenerate}
              disabled={generating}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${generating ? 'animate-spin' : ''}`} />
              Generate Reminders
            </Button>
          </div>
        </div>

        <CreateTaskDialog
          open={createTaskOpen}
          onOpenChange={setCreateTaskOpen}
          onCreated={() => {
            fetchData();
            setRefreshTrigger((t) => t + 1);
          }}
        />

        {/* Active Reminders List */}
        <ReminderList
          showActions={true}
          showHeaderActions={false}
          assignedToMe={assignedScope === 'mine'}
          onReminderAction={() => {
            fetchData();
            setRefreshTrigger((t) => t + 1);
          }}
          priorityFilter={filterPriority !== 'all' ? filterPriority as ReminderPriority : undefined}
          typeFilter={filterType !== 'all' ? filterType as ReminderType : undefined}
          refreshTrigger={refreshTrigger}
        />

        {/* Collapsible Done Section */}
        <div className="mt-6">
          <Button
            variant="ghost"
            className="w-full justify-between px-4 py-3 h-auto font-medium"
            onClick={() => setDoneExpanded(!doneExpanded)}
          >
            <span>Done</span>
            {doneExpanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </Button>
          {doneExpanded && (
            <div className="mt-2">
              <ReminderList
                mode="done"
                showActions={false}
                showHeaderActions={false}
                assignedToMe={assignedScope === 'mine'}
                priorityFilter={filterPriority !== 'all' ? filterPriority as ReminderPriority : undefined}
                typeFilter={filterType !== 'all' ? filterType as ReminderType : undefined}
                refreshTrigger={refreshTrigger}
              />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
