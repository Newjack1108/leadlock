'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import ReminderList from '@/components/ReminderList';
import api, {
  getDashboardStats,
  getStaleSummary,
  getCompanySettings,
  getDiscountTemplates,
  getUnreadSms,
  getUnreadMessenger,
  getLeadLocations,
  getDashboardCommunicationTotals,
  getFacebookLeadConversionReport,
  downloadPipelineValueReportPdf,
  downloadSourcePerformanceReportPdf,
  downloadFacebookLeadConversionReportCsv,
  downloadCloserPerformanceReportPdf,
  downloadQuoteEngagementReportPdf,
  downloadWeeklySummaryReportPdf,
} from '@/lib/api';
import { DashboardStats, StaleSummary, CompanySettings, UnreadSmsSummary, UnreadMessengerSummary, LeadLocationItem, DiscountTemplate, DashboardCommunicationTotals, FacebookLeadConversionReport, FacebookLeadConversionRow, DashboardPresetPeriod, DateRangeQueryParams } from '@/lib/types';
import { getInstallationLeadTimeRows, hasAnyInstallationLeadTime } from '@/lib/companyLeadTimeDisplay';
import { toast } from 'sonner';
import { TrendingUp, Users, CheckCircle2, Trophy, Bell, ArrowRight, Clock, MessageSquare, FileDown, BarChart3, Target, MessageCircle, Calendar, DoorClosed, LayoutDashboard } from 'lucide-react';
import StatusPieChart from '@/components/StatusPieChart';
import LeadsBySourceBarChart from '@/components/LeadsBySourceBarChart';

const LeadMap = dynamic(() => import('@/components/LeadMap'), { ssr: false });

type DashboardDateFilter =
  | { mode: 'preset'; period: DashboardPresetPeriod }
  | { mode: 'custom'; start_date: string; end_date: string };

const PRESET_PERIODS: DashboardPresetPeriod[] = ['all', 'week', 'month', 'quarter', 'year'];

function getTodayDateInputValue(): string {
  return new Date().toISOString().slice(0, 10);
}

function getDaysAgoDateInputValue(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

function formatCurrency(amount?: number | null, currency: string = 'GBP'): string {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount ?? 0);
}

function formatShortDate(value?: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

function formatDays(value?: number | null): string {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(1)} days`;
}

function getConversionRowStatus(row: FacebookLeadConversionRow): string {
  if (row.converted) return 'Ordered';
  if (row.won_without_order) return 'Won without order';
  return 'Lead only';
}

function getOrderReference(row: FacebookLeadConversionRow): string {
  if (!row.order_number) {
    return row.order_count > 0 ? `${row.order_count} orders` : '—';
  }
  if (row.order_count <= 1) return row.order_number;
  return `${row.order_number} +${row.order_count - 1}`;
}

function formatDateInputLabel(value?: string | null): string {
  if (!value) return '—';
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return value;
  return new Date(year, month - 1, day).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

function getPresetPeriodLabel(period: DashboardPresetPeriod): string {
  switch (period) {
    case 'all':
      return 'All Time';
    case 'week':
      return 'This Week';
    case 'month':
      return 'This Month';
    case 'quarter':
      return 'This Quarter';
    case 'year':
      return 'This Year';
    default:
      return 'Selected Range';
  }
}

function getDateRangeParams(filter: DashboardDateFilter): DateRangeQueryParams {
  if (filter.mode === 'custom') {
    return {
      start_date: filter.start_date,
      end_date: filter.end_date,
    };
  }
  return { period: filter.period };
}

function getActiveRangeLabel(filter: DashboardDateFilter): string {
  if (filter.mode === 'preset') {
    return getPresetPeriodLabel(filter.period);
  }
  return `${formatDateInputLabel(filter.start_date)} - ${formatDateInputLabel(filter.end_date)}`;
}

function toDateInputValue(value?: string | null): string {
  return value ? value.slice(0, 10) : '';
}

export default function DashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [companySettings, setCompanySettings] = useState<CompanySettings | null>(null);
  const [staleSummary, setStaleSummary] = useState<StaleSummary | null>(null);
  const [unreadSms, setUnreadSms] = useState<UnreadSmsSummary | null>(null);
  const [unreadMessenger, setUnreadMessenger] = useState<UnreadMessengerSummary | null>(null);
  const [leadLocations, setLeadLocations] = useState<LeadLocationItem[]>([]);
  const [communicationTotals, setCommunicationTotals] = useState<DashboardCommunicationTotals | null>(null);
  const [facebookLeadReport, setFacebookLeadReport] = useState<FacebookLeadConversionReport | null>(null);
  const [activeDiscounts, setActiveDiscounts] = useState<DiscountTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [dateFilter, setDateFilter] = useState<DashboardDateFilter>({ mode: 'preset', period: 'week' });
  const [lastPresetPeriod, setLastPresetPeriod] = useState<DashboardPresetPeriod>('week');
  const [showCustomEditor, setShowCustomEditor] = useState(false);
  const [customStartDate, setCustomStartDate] = useState(getDaysAgoDateInputValue(6));
  const [customEndDate, setCustomEndDate] = useState(getTodayDateInputValue());
  const [userRole, setUserRole] = useState<string | null>(null);
  const activeDateParams = useMemo(() => getDateRangeParams(dateFilter), [dateFilter]);
  const activeRangeLabel = useMemo(() => getActiveRangeLabel(dateFilter), [dateFilter]);

  const fetchDashboard = useCallback(async () => {
    try {
      const me = await api.get('/api/auth/me');
      const role = me.data?.role as string | undefined;
      setUserRole(role ?? null);
      if (role === 'DEALER_ADMIN' || role === 'DEALER_USER') {
        router.replace('/dealer');
        return;
      }

      const [statsRes, staleRes, companyRes, unreadSmsRes, unreadMessengerRes, locationsRes, discountsRes, communicationRes, facebookReportRes] = await Promise.all([
        getDashboardStats(activeDateParams),
        getStaleSummary().catch(() => null), // Don't fail if reminders not available
        getCompanySettings().catch(() => null), // Don't fail if settings not set up yet
        getUnreadSms().catch(() => ({ count: 0, messages: [] })),
        getUnreadMessenger().catch(() => ({ count: 0, messages: [] })),
        getLeadLocations(activeDateParams).catch(() => []),
        getDiscountTemplates(true).catch(() => []),
        getDashboardCommunicationTotals(activeDateParams).catch(() => null),
        getFacebookLeadConversionReport(activeDateParams).catch(() => null),
      ]);
      setStats(statsRes);
      setStaleSummary(staleRes);
      setCompanySettings(companyRes ?? null);
      setUnreadSms(unreadSmsRes ?? { count: 0, messages: [] });
      setUnreadMessenger(unreadMessengerRes ?? { count: 0, messages: [] });
      setLeadLocations(Array.isArray(locationsRes) ? locationsRes : []);
      setActiveDiscounts(Array.isArray(discountsRes) ? discountsRes : []);
      setCommunicationTotals(communicationRes);
      setFacebookLeadReport(facebookReportRes);
    } catch (error: unknown) {
      const status = typeof error === 'object' && error !== null && 'response' in error
        ? (error as { response?: { status?: number } }).response?.status
        : undefined;
      if (status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load dashboard');
      }
    } finally {
      setLoading(false);
    }
  }, [activeDateParams, router]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  const openCustomEditor = () => {
    if (dateFilter.mode === 'custom') {
      setCustomStartDate(dateFilter.start_date);
      setCustomEndDate(dateFilter.end_date);
    } else if (communicationTotals?.start_date && communicationTotals?.end_date) {
      setCustomStartDate(toDateInputValue(communicationTotals.start_date));
      setCustomEndDate(toDateInputValue(communicationTotals.end_date));
    }
    setShowCustomEditor(true);
  };

  const handlePresetChange = (period: DashboardPresetPeriod) => {
    setLastPresetPeriod(period);
    setDateFilter({ mode: 'preset', period });
    setShowCustomEditor(false);
  };

  const applyCustomRange = () => {
    if (!customStartDate || !customEndDate) {
      toast.error('Choose both a start date and end date.');
      return;
    }
    if (customEndDate < customStartDate) {
      toast.error('End date must be on or after the start date.');
      return;
    }
    setDateFilter({
      mode: 'custom',
      start_date: customStartDate,
      end_date: customEndDate,
    });
    setShowCustomEditor(true);
  };

  const cancelCustomEditor = () => {
    if (dateFilter.mode === 'custom') {
      setDateFilter({ mode: 'preset', period: lastPresetPeriod });
    }
    setShowCustomEditor(false);
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

  if (!stats) {
    return null;
  }

  const liveGiveaways = activeDiscounts.filter((discount) => discount.is_giveaway).length;
  const liveSpecialOffers = activeDiscounts.filter((discount) => !discount.is_giveaway).length;
  const totalInteractions = communicationTotals?.total ?? 0;
  const emailTotal = communicationTotals ? communicationTotals.email.sent + communicationTotals.email.received : 0;
  const smsTotal = communicationTotals ? communicationTotals.sms.sent + communicationTotals.sms.received : 0;
  const phoneTotal = communicationTotals ? communicationTotals.phone_answered + communicationTotals.phone_unanswered : 0;
  const formatShare = (value: number) => {
    if (totalInteractions <= 0) return '0%';
    return `${Math.round((value / totalInteractions) * 100)}%`;
  };
  const formatSplit = (value: number, total: number) => {
    if (total <= 0) return '0%';
    return `${Math.round((value / total) * 100)}%`;
  };

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 sm:px-6 py-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div className="flex items-center gap-3">
            <div>
              <h1 className="text-3xl font-semibold">Dashboard</h1>
              <p className="text-sm text-muted-foreground mt-1">Showing: {activeRangeLabel}</p>
            </div>
            {(userRole === 'DIRECTOR' || userRole === 'SALES_MANAGER') && (
              <Link href="/closer-dashboard">
                <Button variant="outline" size="sm">
                  <LayoutDashboard className="h-4 w-4 mr-2" />
                  Closer Dashboard
                </Button>
              </Link>
            )}
          </div>
          <div className="flex max-w-full flex-wrap gap-2">
            {PRESET_PERIODS.map((period) => (
              <Button
                key={period}
                variant={dateFilter.mode === 'preset' && dateFilter.period === period ? 'default' : 'outline'}
                size="sm"
                className="shrink-0"
                onClick={() => handlePresetChange(period)}
              >
                {period === 'all' ? 'All' : period.charAt(0).toUpperCase() + period.slice(1)}
              </Button>
            ))}
            <Button
              variant={dateFilter.mode === 'custom' || showCustomEditor ? 'default' : 'outline'}
              size="sm"
              className="shrink-0"
              onClick={openCustomEditor}
            >
              Custom
            </Button>
          </div>
        </div>

        {showCustomEditor && (
          <Card className="mb-6">
            <CardContent className="py-4">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
                <div className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <p className="mb-1 text-sm font-medium">Start date</p>
                    <Input type="date" value={customStartDate} onChange={(e) => setCustomStartDate(e.target.value)} />
                  </div>
                  <div>
                    <p className="mb-1 text-sm font-medium">End date</p>
                    <Input type="date" value={customEndDate} onChange={(e) => setCustomEndDate(e.target.value)} />
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" onClick={applyCustomRange}>
                    Apply range
                  </Button>
                  <Button variant="outline" size="sm" onClick={cancelCustomEditor}>
                    {dateFilter.mode === 'custom' ? `Use ${getPresetPeriodLabel(lastPresetPeriod)}` : 'Cancel'}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Installation lead times – clear indicator for sales */}
        {hasAnyInstallationLeadTime(companySettings) && (
          <div className="mb-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card className="border-primary/30 bg-primary/5">
              <CardContent className="py-4">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                    <Clock className="h-5 w-5 text-primary" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-medium text-muted-foreground">
                        Installation lead time (by product type)
                      </p>
                      <Link href="/settings/company">
                        <Button variant="outline" size="sm">
                          Edit
                        </Button>
                      </Link>
                    </div>
                    <ul className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      {getInstallationLeadTimeRows(companySettings!).map((row) => (
                        <li key={row.label} className="rounded-md border border-primary/20 bg-background/70 px-3 py-2">
                          <p className="text-xs text-muted-foreground">{row.label}</p>
                          <p className="text-base font-semibold leading-tight">{row.value}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="border-emerald-500/30 bg-emerald-500/5">
              <CardContent className="py-4">
                <p className="text-sm font-medium text-muted-foreground mb-3">
                  Live promotions available
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg border border-border/80 bg-background/80 px-3 py-2">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Giveaways</p>
                    <p className="text-2xl font-bold text-emerald-700 dark:text-emerald-400">{liveGiveaways}</p>
                  </div>
                  <div className="rounded-lg border border-border/80 bg-background/80 px-3 py-2">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Special offers</p>
                    <p className="text-2xl font-bold text-emerald-700 dark:text-emerald-400">{liveSpecialOffers}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Metrics Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Leads</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_leads}</div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Engaged %</CardTitle>
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.engaged_percentage}%</div>
              <p className="text-xs text-muted-foreground">
                {stats.engaged_count} leads engaged
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Qualified %</CardTitle>
              <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.qualified_percentage}%</div>
              <p className="text-xs text-muted-foreground">
                {stats.qualified_count} leads qualified
              </p>
            </CardContent>
          </Card>

          <Link href="/leads?status=WON" className="block">
            <Card className="cursor-pointer transition-colors hover:border-primary/50">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Won</CardTitle>
                <Trophy className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.won_count}</div>
                <p className="text-xs text-muted-foreground">
                  {stats.leads_with_sent_quotes_count} quoted
                </p>
              </CardContent>
            </Card>
          </Link>
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Lead Status</CardTitle>
            </CardHeader>
            <CardContent>
              <StatusPieChart
                newCount={stats.new_count}
                quotedCount={stats.leads_with_sent_quotes_count}
                wonCount={stats.won_count}
                lostCount={stats.lost_count}
                closedCount={stats.closed_count}
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Leads by Source</CardTitle>
            </CardHeader>
            <CardContent>
              <LeadsBySourceBarChart data={stats.leads_by_source || []} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Lead Locations</CardTitle>
            </CardHeader>
            <CardContent>
              <LeadMap
                locations={leadLocations}
                loading={loading}
                period={dateFilter.mode === 'custom' ? 'custom' : dateFilter.period}
                periodLabel={activeRangeLabel}
              />
            </CardContent>
          </Card>
        </div>

        {communicationTotals && (
          <Card className="mb-8 border-primary/20 bg-primary/5">
            <CardHeader>
              <CardTitle className="text-lg">Communication Activity Overview</CardTitle>
              <p className="text-sm text-muted-foreground">
                {activeRangeLabel} across email, SMS, and phone.
              </p>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="rounded-lg border border-primary/30 bg-primary/10 p-4">
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">Total interactions</p>
                  <p className="text-2xl font-bold text-primary">{communicationTotals.total}</p>
                  <p className="text-xs text-muted-foreground mt-1">100% of communication</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Sent {communicationTotals.total_sent} ({formatSplit(communicationTotals.total_sent, communicationTotals.total)}) / Received {communicationTotals.total_received} ({formatSplit(communicationTotals.total_received, communicationTotals.total)})
                  </p>
                </div>
                <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-4">
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">Email</p>
                  <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">{emailTotal}</p>
                  <p className="text-xs text-muted-foreground mt-1">{formatShare(emailTotal)} of total</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Reply rate: {communicationTotals.email_reply_rate_pct}% (customers who replied after email sent)
                  </p>
                </div>
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4">
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">SMS</p>
                  <p className="text-2xl font-bold text-emerald-700 dark:text-emerald-300">{smsTotal}</p>
                  <p className="text-xs text-muted-foreground mt-1">{formatShare(smsTotal)} of total</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Reply rate: {communicationTotals.sms_reply_rate_pct}% (customers who replied after SMS sent)
                  </p>
                </div>
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">Phone</p>
                  <p className="text-2xl font-bold text-amber-700 dark:text-amber-300">{phoneTotal}</p>
                  <p className="text-xs text-muted-foreground mt-1">{formatShare(phoneTotal)} of total</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Answered {communicationTotals.phone_answered} ({formatSplit(communicationTotals.phone_answered, phoneTotal)}) / Non-answered {communicationTotals.phone_unanswered} ({formatSplit(communicationTotals.phone_unanswered, phoneTotal)})
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Status Breakdown */}
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-6 mb-8">
          <Link href="/leads?status=NEW" className="block">
            <Card className="cursor-pointer transition-colors hover:border-primary/50 h-full">
              <CardHeader>
                <CardTitle className="text-lg">New</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stats.new_count}</div>
              </CardContent>
            </Card>
          </Link>
          <Link href="/quotes?status=SENT" className="block">
            <Card className="cursor-pointer transition-colors hover:border-primary/50 h-full">
              <CardHeader>
                <CardTitle className="text-lg">Quoted</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stats.leads_with_sent_quotes_count}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  {stats.quotes_sent_count} quotes sent
                </p>
              </CardContent>
            </Card>
          </Link>
          <Link href="/leads?status=WON" className="block">
            <Card className="cursor-pointer transition-colors hover:border-primary/50 h-full">
              <CardHeader>
                <CardTitle className="text-lg">Won</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stats.won_count}</div>
              </CardContent>
            </Card>
          </Link>
          <Link href="/leads?status=LOST" className="block">
            <Card className="cursor-pointer transition-colors hover:border-primary/50 h-full">
              <CardHeader>
                <CardTitle className="text-lg">Lost</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stats.lost_count}</div>
              </CardContent>
            </Card>
          </Link>
          <Link href="/leads?status=CLOSED" className="block">
            <Card className="cursor-pointer transition-colors hover:border-primary/50 h-full">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-lg">Closed</CardTitle>
                <DoorClosed className="h-5 w-5 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stats.closed_count}</div>
                <p className="text-xs text-muted-foreground mt-1">Qualified, no quote</p>
              </CardContent>
            </Card>
          </Link>
        </div>

        {/* Sales Reports */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              Sales Reports
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              Download PDF reports to assist sales analysis
            </p>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
              <div className="flex flex-col p-4 rounded-lg border border-border">
                <div className="flex items-center gap-2 mb-2">
                  <Target className="h-4 w-4 text-primary" />
                  <span className="font-medium">Pipeline Value</span>
                </div>
                <p className="text-xs text-muted-foreground mb-3">
                  Weighted pipeline by stage and close probability
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => downloadPipelineValueReportPdf(activeDateParams)}
                  className="mt-auto"
                >
                  <FileDown className="h-4 w-4 mr-1" />
                  Download PDF
                </Button>
              </div>
              <div className="flex flex-col p-4 rounded-lg border border-border">
                <div className="flex items-center gap-2 mb-2">
                  <BarChart3 className="h-4 w-4 text-primary" />
                  <span className="font-medium">Source Performance</span>
                </div>
                <p className="text-xs text-muted-foreground mb-3">
                  Leads and conversion by lead source
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => downloadSourcePerformanceReportPdf(activeDateParams)}
                  className="mt-auto"
                >
                  <FileDown className="h-4 w-4 mr-1" />
                  Download PDF
                </Button>
              </div>
              <div className="flex flex-col p-4 rounded-lg border border-border">
                <div className="flex items-center gap-2 mb-2">
                  <Users className="h-4 w-4 text-primary" />
                  <span className="font-medium">Closer Performance</span>
                </div>
                <p className="text-xs text-muted-foreground mb-3">
                  Wins and revenue by salesperson
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => downloadCloserPerformanceReportPdf()}
                  className="mt-auto"
                >
                  <FileDown className="h-4 w-4 mr-1" />
                  Download PDF
                </Button>
              </div>
              <div className="flex flex-col p-4 rounded-lg border border-border">
                <div className="flex items-center gap-2 mb-2">
                  <MessageCircle className="h-4 w-4 text-primary" />
                  <span className="font-medium">Quote Engagement</span>
                </div>
                <p className="text-xs text-muted-foreground mb-3">
                  Sent vs viewed vs no reply
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => downloadQuoteEngagementReportPdf(activeDateParams)}
                  className="mt-auto"
                >
                  <FileDown className="h-4 w-4 mr-1" />
                  Download PDF
                </Button>
              </div>
              <div className="flex flex-col p-4 rounded-lg border border-border">
                <div className="flex items-center gap-2 mb-2">
                  <Calendar className="h-4 w-4 text-primary" />
                  <span className="font-medium">Weekly Summary</span>
                </div>
                <p className="text-xs text-muted-foreground mb-3">
                  New, quoted, won, lost this week
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => downloadWeeklySummaryReportPdf()}
                  className="mt-auto"
                >
                  <FileDown className="h-4 w-4 mr-1" />
                  Download PDF
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Facebook Lead-to-Order */}
        {facebookLeadReport && (
          <Card className="mb-8">
            <CardHeader>
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Target className="h-5 w-5" />
                    Facebook Lead-to-Order
                  </CardTitle>
                  <p className="text-sm text-muted-foreground mt-1">
                    {activeRangeLabel} Facebook lead performance, conversion, revenue, and tagged advert breakdown.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => downloadFacebookLeadConversionReportCsv(activeDateParams)}
                >
                  <FileDown className="h-4 w-4 mr-1" />
                  Download CSV
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {facebookLeadReport.rows.length === 0 ? (
                <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
                  No Facebook leads found for this period.
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-lg border p-4">
                      <p className="text-sm text-muted-foreground">Facebook leads</p>
                      <p className="mt-1 text-2xl font-semibold">{facebookLeadReport.summary.total_facebook_leads}</p>
                    </div>
                    <div className="rounded-lg border p-4">
                      <p className="text-sm text-muted-foreground">Converted leads</p>
                      <p className="mt-1 text-2xl font-semibold">{facebookLeadReport.summary.converted_leads}</p>
                      <p className="text-xs text-muted-foreground">
                        {facebookLeadReport.summary.total_orders} linked orders
                      </p>
                    </div>
                    <div className="rounded-lg border p-4">
                      <p className="text-sm text-muted-foreground">Conversion rate</p>
                      <p className="mt-1 text-2xl font-semibold">{facebookLeadReport.summary.conversion_rate}%</p>
                      <p className="text-xs text-muted-foreground">
                        Lead to order
                      </p>
                    </div>
                    <div className="rounded-lg border p-4">
                      <p className="text-sm text-muted-foreground">Order revenue</p>
                      <p className="mt-1 text-2xl font-semibold">
                        {formatCurrency(facebookLeadReport.summary.total_order_revenue)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Avg order {formatCurrency(facebookLeadReport.summary.average_order_value)}
                      </p>
                    </div>
                    <div className="rounded-lg border p-4">
                      <p className="text-sm text-muted-foreground">Avg days to convert</p>
                      <p className="mt-1 text-2xl font-semibold">
                        {formatDays(facebookLeadReport.summary.average_days_to_convert)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Converted leads only
                      </p>
                    </div>
                    <div className="rounded-lg border p-4">
                      <p className="text-sm text-muted-foreground">Unknown advert tags</p>
                      <p className="mt-1 text-2xl font-semibold">{facebookLeadReport.summary.unknown_advert_profile_leads}</p>
                      <p className="text-xs text-muted-foreground">
                        Need manual advert tagging
                      </p>
                    </div>
                    <div className="rounded-lg border p-4">
                      <p className="text-sm text-muted-foreground">Won without order</p>
                      <p className="mt-1 text-2xl font-semibold">{facebookLeadReport.summary.won_without_order_leads}</p>
                      <p className="text-xs text-muted-foreground">
                        Historical edge case
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                    <div className="rounded-lg border">
                      <div className="border-b px-4 py-3">
                        <h3 className="font-medium">By Advert Profile</h3>
                        <p className="text-sm text-muted-foreground">Conversion and revenue by tagged Facebook advert.</p>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b bg-muted/40">
                              <th className="p-3 text-left font-medium">Advert</th>
                              <th className="p-3 text-left font-medium">Leads</th>
                              <th className="p-3 text-left font-medium">Conv %</th>
                              <th className="p-3 text-left font-medium">Revenue</th>
                              <th className="p-3 text-left font-medium">Avg days</th>
                            </tr>
                          </thead>
                          <tbody>
                            {facebookLeadReport.advert_breakdown.map((item) => (
                              <tr key={item.name} className="border-b last:border-0">
                                <td className="p-3 font-medium">{item.name}</td>
                                <td className="p-3 text-muted-foreground">
                                  {item.leads_count}
                                  <span className="ml-1 text-xs">({item.converted_leads} converted)</span>
                                </td>
                                <td className="p-3">{item.conversion_rate}%</td>
                                <td className="p-3">{formatCurrency(item.total_revenue)}</td>
                                <td className="p-3">{formatDays(item.average_days_to_convert)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="rounded-lg border">
                      <div className="border-b px-4 py-3">
                        <h3 className="font-medium">By Product Type</h3>
                        <p className="text-sm text-muted-foreground">See which product interest converts fastest and best.</p>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b bg-muted/40">
                              <th className="p-3 text-left font-medium">Product type</th>
                              <th className="p-3 text-left font-medium">Leads</th>
                              <th className="p-3 text-left font-medium">Conv %</th>
                              <th className="p-3 text-left font-medium">Revenue</th>
                              <th className="p-3 text-left font-medium">Avg days</th>
                            </tr>
                          </thead>
                          <tbody>
                            {facebookLeadReport.product_type_breakdown.map((item) => (
                              <tr key={item.name} className="border-b last:border-0">
                                <td className="p-3 font-medium">{item.name}</td>
                                <td className="p-3 text-muted-foreground">
                                  {item.leads_count}
                                  <span className="ml-1 text-xs">({item.converted_leads} converted)</span>
                                </td>
                                <td className="p-3">{item.conversion_rate}%</td>
                                <td className="p-3">{formatCurrency(item.total_revenue)}</td>
                                <td className="p-3">{formatDays(item.average_days_to_convert)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border">
                    <div className="border-b px-4 py-3">
                      <h3 className="font-medium">Lead Details</h3>
                      <p className="text-sm text-muted-foreground">
                        Lead-level breakdown showing tagged advert, order outcome, and conversion timing.
                      </p>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b bg-muted/40">
                            <th className="p-3 text-left font-medium">Lead date</th>
                            <th className="p-3 text-left font-medium">Lead</th>
                            <th className="p-3 text-left font-medium">Advert</th>
                            <th className="p-3 text-left font-medium">Product type</th>
                            <th className="p-3 text-left font-medium">Quote</th>
                            <th className="p-3 text-left font-medium">Order</th>
                            <th className="p-3 text-left font-medium">Order amount</th>
                            <th className="p-3 text-left font-medium">Days</th>
                            <th className="p-3 text-left font-medium">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {facebookLeadReport.rows.map((row) => (
                            <tr key={row.lead_id} className="border-b last:border-0 align-top">
                              <td className="p-3 text-muted-foreground">{formatShortDate(row.lead_created_at)}</td>
                              <td className="p-3">
                                <div className="font-medium">{row.lead_name}</div>
                                <div className="text-xs text-muted-foreground">
                                  {[row.email, row.phone].filter(Boolean).join(' • ') || row.lead_status}
                                </div>
                              </td>
                              <td className="p-3">{row.advert_profile_name}</td>
                              <td className="p-3">
                                <div>{row.product_type}</div>
                                {row.product_interest && (
                                  <div className="text-xs text-muted-foreground">{row.product_interest}</div>
                                )}
                              </td>
                              <td className="p-3 text-muted-foreground">{row.quote_number || '—'}</td>
                              <td className="p-3">
                                <div>{getOrderReference(row)}</div>
                                {row.order_created_at && (
                                  <div className="text-xs text-muted-foreground">{formatShortDate(row.order_created_at)}</div>
                                )}
                              </td>
                              <td className="p-3">
                                {row.order_amount !== null && row.order_amount !== undefined ? formatCurrency(row.order_amount) : '—'}
                              </td>
                              <td className="p-3">{formatDays(row.days_to_convert)}</td>
                              <td className="p-3">{getConversionRowStatus(row)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Leads by Source */}
        {stats.leads_by_source && stats.leads_by_source.length > 0 && (
          <Card className="mb-8">
            <CardHeader>
              <CardTitle className="text-lg">Leads by Source</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
                {stats.leads_by_source.map((item) => (
                  <Link
                    key={item.source}
                    href={`/leads?lead_source=${item.source}`}
                    className="flex items-center justify-between p-4 rounded-lg border border-border hover:border-primary/50 transition-colors"
                  >
                    <span className="font-medium">
                      {item.source.replace(/_/g, ' ')}
                    </span>
                    <span className="text-lg font-bold">{item.count}</span>
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stale Items Summary */}
        {staleSummary && staleSummary.total_reminders > 0 && (
          <Card className="mb-8">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5" />
                Stale Items Requiring Attention
              </CardTitle>
              <Link href="/reminders">
                <Button variant="outline" size="sm">
                  View All
                  <ArrowRight className="h-4 w-4 ml-2" />
                </Button>
              </Link>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div>
                  <div className="text-2xl font-bold">{staleSummary.total_reminders}</div>
                  <div className="text-sm text-muted-foreground">Total Reminders</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-red-600">{staleSummary.urgent_count}</div>
                  <div className="text-sm text-muted-foreground">Urgent</div>
                </div>
                <div>
                  <div className="text-2xl font-bold">{staleSummary.stale_leads_count}</div>
                  <div className="text-sm text-muted-foreground">Stale Leads</div>
                </div>
                <div>
                  <div className="text-2xl font-bold">{staleSummary.stale_quotes_count}</div>
                  <div className="text-sm text-muted-foreground">Stale Quotes</div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Unread SMS */}
        {unreadSms && unreadSms.count > 0 && (
          <Card className="mb-8">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5" />
                Unread SMS
              </CardTitle>
              <span className="text-sm text-muted-foreground">{unreadSms.count} to deal with</span>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {unreadSms.messages.slice(0, 5).map((msg) => (
                  <div
                    key={msg.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-card border border-border"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-medium truncate">{msg.customer_name}</p>
                      <p className="text-sm text-muted-foreground truncate">{msg.body}</p>
                    </div>
                    <Link href={`/customers/${msg.customer_id}/sms`}>
                      <Button variant="outline" size="sm">
                        View
                        <ArrowRight className="h-4 w-4 ml-1" />
                      </Button>
                    </Link>
                  </div>
                ))}
              </div>
              {unreadSms.messages.length > 5 && (
                <p className="text-sm text-muted-foreground mt-2">
                  +{unreadSms.count - 5} more — open a conversation above to clear them
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Unread Messenger */}
        {unreadMessenger && unreadMessenger.count > 0 && (
          <Card className="mb-8">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5" />
                Unread Messenger
              </CardTitle>
              <span className="text-sm text-muted-foreground">{unreadMessenger.count} to deal with</span>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {unreadMessenger.messages.slice(0, 5).map((msg) => (
                  <div
                    key={msg.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-card border border-border"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-medium truncate">{msg.customer_name}</p>
                      <p className="text-sm text-muted-foreground truncate">{msg.body}</p>
                    </div>
                    <Link href={`/customers/${msg.customer_id}/messenger`}>
                      <Button variant="outline" size="sm">
                        View
                        <ArrowRight className="h-4 w-4 ml-1" />
                      </Button>
                    </Link>
                  </div>
                ))}
              </div>
              {unreadMessenger.messages.length > 5 && (
                <p className="text-sm text-muted-foreground mt-2">
                  +{unreadMessenger.count - 5} more — open a conversation above to clear them
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Reminders List */}
        <div className="mb-8">
          <ReminderList limit={5} showActions={true} />
        </div>

      </main>
    </div>
  );
}
