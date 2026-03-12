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
  const [datePeriod, setDatePeriod] = useState<DatePeriod>('all');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboard();
  }, [datePeriod]);

  const fetchDashboard = async () => {
    try {
      const [
        meRes,
        qualifiedRes,
        smsRes,
        messengerRes,
        docsRes,
        statsRes,
        companyRes,
        locationsRes,
      ] = await Promise.all([
        api.get('/api/auth/me').then((r) => r.data).catch(() => null),
        getQualifiedForQuoting().catch(() => ({ count: 0, leads: [] })),
        getUnreadSms().catch(() => ({ count: 0, messages: [] })),
        getUnreadMessenger().catch(() => ({ count: 0, messages: [] })),
        getSalesDocuments().catch(() => []),
        api.get('/api/dashboard/stats', { params: datePeriod === 'all' ? {} : { period: datePeriod } }).then((r) => r.data).catch(() => null),
        getCompanySettings().catch(() => null),
        getLeadLocations(datePeriod === 'all' ? undefined : datePeriod).catch(() => []),
      ]);
      setUser(meRes ? { full_name: meRes.full_name || '' } : null);
      setQualified(qualifiedRes);
      setUnreadSms(smsRes ?? { count: 0, messages: [] });
      setUnreadMessenger(messengerRes ?? { count: 0, messages: [] });
      setDocuments(Array.isArray(docsRes) ? docsRes : []);
      setStats(statsRes);
      setCompanySettings(companyRes ?? null);
      setLeadLocations(Array.isArray(locationsRes) ? locationsRes : []);
    } catch (error: unknown) {
      const err = error as { response?: { status?: number } };
      if (err.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load dashboard');
      }
    } finally {
      setLoading(false);
    }
  };

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
    <div className="h-screen flex flex-col overflow-hidden">
      <Header />
      <main className="flex-1 container mx-auto px-6 py-4 overflow-hidden flex flex-col min-h-0">
        <div className="shrink-0 mb-4">
          <p className="text-2xl font-bold">
            {getGreeting()}{user?.full_name ? `, ${getFirstName(user.full_name)}` : ''}
          </p>
          <div className="flex items-center gap-2 mt-1">
            <LayoutDashboard className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-semibold">Closer Dashboard</h1>
          </div>
        </div>

        {/* Installation lead time */}
        {companySettings?.installation_lead_time && (
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
        )}

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

        {/* Pipeline overview: Status, Leads by source, Map */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4 shrink-0">
          <Card>
            <CardHeader className="py-2 px-4">
              <CardTitle className="text-sm font-medium">Lead Status</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
              <StatusPieChart
                height={180}
                newCount={stats?.new_count ?? 0}
                quotedCount={stats?.leads_with_sent_quotes_count ?? 0}
                wonCount={stats?.won_count ?? 0}
                lostCount={stats?.lost_count ?? 0}
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="py-2 px-4">
              <CardTitle className="text-sm font-medium">Leads by Source</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
              <LeadsBySourceBarChart data={stats?.leads_by_source ?? []} height={180} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="py-2 px-4">
              <CardTitle className="text-sm font-medium">Lead Locations</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0">
              <LeadMap locations={leadLocations} period={datePeriod} height={200} />
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 flex-1 min-h-0 overflow-y-auto lg:overflow-hidden">
          {/* Left column */}
          <div className="flex flex-col gap-4 overflow-y-auto min-h-0 lg:pr-1">
            {/* Qualified for Quoting */}
            <Card className="shrink-0 border-primary/30 bg-primary/5">
              <CardHeader className="py-3 px-4 flex flex-row items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Qualified for Quoting
                </CardTitle>
                <span className="text-xs text-muted-foreground">
                  {qualified?.count ?? 0} ready
                </span>
              </CardHeader>
              <CardContent className="px-4 pb-4 pt-0">
            {qualified && qualified.leads.length > 0 ? (
              <div className="space-y-1.5">
                {qualified.leads.slice(0, 8).map((lead) => (
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
                {qualified.leads.length > 8 && (
                  <p className="text-xs text-muted-foreground pt-1">+{qualified.leads.length - 8} more</p>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground py-2">No qualified leads.</p>
            )}
              </CardContent>
            </Card>

            {/* New Messages */}
            {totalUnread > 0 && (
              <Card className="shrink-0">
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
          </div>

          {/* Right column */}
          <div className="flex flex-col gap-4 overflow-y-auto min-h-0 lg:pl-1">
            {/* Reminders */}
            <div className="shrink-0">
              <ReminderList limit={5} showActions={true} />
            </div>

            {/* Quick Documents */}
            <Card className="shrink-0">
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
                {documents.length > 0 ? (
                  <div className="space-y-1.5">
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
        </div>
      </main>
    </div>
  );
}
