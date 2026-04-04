'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import ReminderList from '@/components/ReminderList';
import StatusPieChart from '@/components/StatusPieChart';
import LeadsBySourceBarChart from '@/components/LeadsBySourceBarChart';
import api, {
  getQualifiedForQuoting,
  getUnreadSms,
  getUnreadMessenger,
  getSalesDocuments,
  downloadSalesDocument,
  getCompanySettings,
  getLeadLocations,
} from '@/lib/api';
import type {
  QualifiedForQuotingSummary,
  UnreadSmsSummary,
  UnreadMessengerSummary,
  SalesDocument,
  DashboardStats,
  CompanySettings,
  LeadLocationItem,
} from '@/lib/types';
import { toast } from 'sonner';
import {
  FileText,
  ArrowRight,
  MessageSquare,
  FolderOpen,
  Download,
  LayoutDashboard,
  Clock,
} from 'lucide-react';

const LeadMap = dynamic(() => import('@/components/LeadMap'), { ssr: false });

type DatePeriod = 'all' | 'week' | 'month' | 'quarter' | 'year';

function formatTimeAgo(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

function getFirstName(fullName: string): string {
  const trimmed = (fullName || '').trim();
  if (!trimmed) return 'there';
  const parts = trimmed.split(/\s+/);
  return parts[0];
}

export default function CloserDashboardPage() {
  const router = useRouter();
  const [qualified, setQualified] = useState<QualifiedForQuotingSummary | null>(null);
  const [unreadSms, setUnreadSms] = useState<UnreadSmsSummary | null>(null);
  const [unreadMessenger, setUnreadMessenger] = useState<UnreadMessengerSummary | null>(null);
  const [documents, setDocuments] = useState<SalesDocument[]>([]);
  const [user, setUser] = useState<{ full_name: string } | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [companySettings, setCompanySettings] = useState<CompanySettings | null>(null);
  const [leadLocations, setLeadLocations] = useState<LeadLocationItem[]>([]);
  const [datePeriod, setDatePeriod] = useState<DatePeriod>('week');
  const [loadingPhase1, setLoadingPhase1] = useState(true);
  const [loadingPhase2, setLoadingPhase2] = useState(true);
  const [loadingPhase3, setLoadingPhase3] = useState(true);

  // Phase 1: Critical - auth, qualified, documents (main features; not period-dependent)
  useEffect(() => {
    const phase1Promises = [
      api.get('/api/auth/me').then((r) => r.data).catch((err: { response?: { status?: number } }) => {
        if (err?.response?.status === 401) router.push('/login');
        return null;
      }),
      getQualifiedForQuoting().catch(() => ({ count: 0, leads: [] })),
      getSalesDocuments().catch(() => []),
    ];
    Promise.all(phase1Promises).then(([meRes, qualifiedRes, docsRes]) => {
      setUser(meRes ? { full_name: meRes.full_name || '' } : null);
      setQualified(qualifiedRes);
      setDocuments(Array.isArray(docsRes) ? docsRes : []);
    }).catch(() => toast.error('Failed to load dashboard')).finally(() => setLoadingPhase1(false));
  }, [router]);

  // Phase 2 & 3: Period-dependent data
  useEffect(() => {
    const params = datePeriod === 'all' ? {} : { period: datePeriod };
    const locationsParam = datePeriod === 'all' ? undefined : datePeriod;

    setLoadingPhase2(true);
    setLoadingPhase3(true);

    // Phase 2: Company settings, stats (installation lead time, charts)
    Promise.all([
      getCompanySettings().catch(() => null),
      api.get('/api/dashboard/stats', { params }).then((r) => r.data).catch(() => null),
    ]).then(([companyRes, statsRes]) => {
      setCompanySettings(companyRes ?? null);
      setStats(statsRes);
    }).catch(() => toast.error('Failed to load dashboard stats')).finally(() => setLoadingPhase2(false));

    // Phase 3: Lead locations, unread messages
    Promise.all([
      getLeadLocations(locationsParam).catch(() => []),
      getUnreadSms().catch(() => ({ count: 0, messages: [] })),
      getUnreadMessenger().catch(() => ({ count: 0, messages: [] })),
    ]).then(([locationsRes, smsRes, messengerRes]) => {
      setLeadLocations(Array.isArray(locationsRes) ? locationsRes : []);
      setUnreadSms(smsRes ?? { count: 0, messages: [] });
      setUnreadMessenger(messengerRes ?? { count: 0, messages: [] });
    }).catch(() => toast.error('Failed to load messages')).finally(() => setLoadingPhase3(false));
  }, [datePeriod]);

  const handleDownloadDoc = async (doc: SalesDocument) => {
    try {
      const blob = await downloadSalesDocument(doc.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Failed to download document');
    }
  };

  const totalUnread = (unreadSms?.count ?? 0) + (unreadMessenger?.count ?? 0);

  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 container mx-auto px-6 py-4 overflow-y-auto">
        <div className="shrink-0 mb-4">
          <p className="text-2xl font-bold">
            {getGreeting()}
            {loadingPhase1 && !user ? (
              <span className="ml-2 inline-block h-7 w-24 animate-pulse rounded bg-muted" />
            ) : user?.full_name ? (
              `, ${getFirstName(user.full_name)}`
            ) : null}
          </p>
          <div className="flex items-center gap-2 mt-1">
            <LayoutDashboard className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-semibold">Closer Dashboard</h1>
          </div>
        </div>

        {/* Installation lead time */}
        {loadingPhase2 && !companySettings ? (
          <Card className="shrink-0 mb-4 border-primary/30 bg-primary/5">
            <CardContent className="py-3 px-4">
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 animate-pulse rounded-lg bg-muted" />
                <div>
                  <p className="text-xs font-medium text-muted-foreground">
                    Current installation lead time
                  </p>
                  <div className="mt-1 h-6 w-24 animate-pulse rounded bg-muted" />
                </div>
              </div>
            </CardContent>
          </Card>
        ) : companySettings?.installation_lead_time ? (
          <Card className="shrink-0 mb-4 border-primary/30 bg-primary/5">
            <CardContent className="py-3 px-4">
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                  <Clock className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">
                    Current installation lead time
                  </p>
                  <p className="text-lg font-bold">{companySettings.installation_lead_time}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {/* Period filter */}
        <div className="flex gap-2 mb-4 shrink-0">
          {(['all', 'week', 'month', 'quarter', 'year'] as const).map((period) => (
            <Button
              key={period}
              variant={datePeriod === period ? 'default' : 'outline'}
              size="sm"
              className="h-7 text-xs"
              onClick={() => setDatePeriod(period)}
            >
              {period === 'all' ? 'All' : period.charAt(0).toUpperCase() + period.slice(1)}
            </Button>
          ))}
        </div>

        {/* Qualified for Quoting, Reminders, Quick Documents - three equal-size cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4 shrink-0">
          <Card className="shrink-0 min-h-[200px] border-primary/30 bg-primary/5">
            <CardHeader className="py-3 px-4 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <FileText className="h-4 w-4" />
                New qualified leads
              </CardTitle>
              <span className="text-xs text-muted-foreground">
                {qualified?.count ?? 0} need attention
              </span>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
              {loadingPhase1 ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="flex gap-2 p-2 rounded-md border border-border">
                      <div className="h-4 flex-1 animate-pulse rounded bg-muted" />
                      <div className="h-3 w-20 animate-pulse rounded bg-muted" />
                    </div>
                  ))}
                </div>
              ) : qualified && qualified.leads.length > 0 ? (
                <div className="max-h-[280px] overflow-y-auto space-y-1.5">
                  {qualified.leads.map((lead) => (
                    <Link
                      key={lead.id}
                      href={`/leads/${lead.id}`}
                      className="flex items-center justify-between p-2 rounded-md bg-card border border-border cursor-pointer hover:border-primary/50 transition-colors block"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{lead.name}</p>
                        <p className="text-xs text-muted-foreground truncate">
                          {lead.customer_name || 'No customer'} · {formatTimeAgo(lead.updated_at)}
                        </p>
                      </div>
                      <ArrowRight className="h-3.5 w-3.5 text-primary shrink-0 ml-2" />
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground py-2">No new qualified leads.</p>
              )}
            </CardContent>
          </Card>
          <div className="shrink-0">
            <ReminderList limit={5} showActions={true} compact={true} />
          </div>
          <Card className="shrink-0 min-h-[200px]">
            <CardHeader className="py-3 px-4 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <FolderOpen className="h-4 w-4" />
                Quick Documents
              </CardTitle>
              <Button variant="outline" size="sm" className="h-7 text-xs" asChild>
                <Link href="/sales-documents">View all</Link>
              </Button>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
              {loadingPhase1 ? (
                <div className="space-y-2">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="flex gap-2 p-2 rounded-md border border-border">
                      <div className="h-4 flex-1 animate-pulse rounded bg-muted" />
                      <div className="h-7 w-7 shrink-0 animate-pulse rounded bg-muted" />
                    </div>
                  ))}
                </div>
              ) : documents.length > 0 ? (
                <div className="max-h-[280px] overflow-y-auto space-y-1.5">
                  {documents.slice(0, 6).map((doc) => (
                    <div
                      key={doc.id}
                      className="flex items-center justify-between p-2 rounded-md border border-border hover:border-primary/30 transition-colors"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{doc.name}</p>
                        {doc.category && (
                          <p className="text-xs text-muted-foreground">{doc.category}</p>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 shrink-0 p-0"
                        onClick={() => handleDownloadDoc(doc)}
                      >
                        <Download className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground py-2">No documents available.</p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Pipeline overview: Status, Leads by source, Map */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4 shrink-0">
          <Card>
            <CardHeader className="py-2 px-4">
              <CardTitle className="text-sm font-medium">Lead Status</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
              {loadingPhase2 ? (
                <div className="h-[180px] flex items-center justify-center">
                  <div className="h-32 w-32 animate-pulse rounded-full bg-muted" />
                </div>
              ) : (
                <StatusPieChart
                  height={180}
                  newCount={stats?.new_count ?? 0}
                  quotedCount={stats?.leads_with_sent_quotes_count ?? 0}
                  wonCount={stats?.won_count ?? 0}
                  lostCount={stats?.lost_count ?? 0}
                />
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="py-2 px-4">
              <CardTitle className="text-sm font-medium">Leads by Source</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
              {loadingPhase2 ? (
                <div className="h-[180px] space-y-2">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="h-6 animate-pulse rounded bg-muted" style={{ width: `${60 + i * 10}%` }} />
                  ))}
                </div>
              ) : (
                <LeadsBySourceBarChart data={stats?.leads_by_source ?? []} height={180} />
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="py-2 px-4">
              <CardTitle className="text-sm font-medium">Lead Locations</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
              {loadingPhase3 ? (
                <div className="h-[200px] animate-pulse rounded bg-muted" />
              ) : (
                <LeadMap locations={leadLocations} period={datePeriod} height={200} />
              )}
            </CardContent>
          </Card>
        </div>

        {/* New Messages - full width when there are unread */}
        {totalUnread > 0 && (
          <Card className="shrink-0 mb-4">
            <CardHeader className="py-3 px-4 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <MessageSquare className="h-4 w-4" />
                New Messages
              </CardTitle>
              <span className="text-xs text-muted-foreground">{totalUnread} unread</span>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
              <div className="space-y-1.5">
                {unreadSms?.messages?.slice(0, 4).map((msg) => (
                  <div
                    key={`sms-${msg.id}`}
                    className="flex items-center justify-between p-2 rounded-md bg-card border border-border"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{msg.customer_name}</p>
                      <p className="text-xs text-muted-foreground truncate">{msg.body}</p>
                    </div>
                    <Button variant="outline" size="sm" className="h-7 text-xs" asChild>
                      <Link href={`/customers/${msg.customer_id}/sms`}>View</Link>
                    </Button>
                  </div>
                ))}
                {unreadMessenger?.messages?.slice(0, 4).map((msg) => (
                  <div
                    key={`msg-${msg.id}`}
                    className="flex items-center justify-between p-2 rounded-md bg-card border border-border"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{msg.customer_name}</p>
                      <p className="text-xs text-muted-foreground truncate">{msg.body}</p>
                    </div>
                    <Button variant="outline" size="sm" className="h-7 text-xs" asChild>
                      <Link href={`/customers/${msg.customer_id}/messenger`}>View</Link>
                    </Button>
                  </div>
                ))}
              </div>
              <Button variant="ghost" size="sm" className="h-7 text-xs mt-2" asChild>
                <Link href="/customers?has_unread=1">View all</Link>
              </Button>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
