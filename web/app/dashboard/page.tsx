'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import ReminderList from '@/components/ReminderList';
import api, { getStaleSummary, getCompanySettings, getUnreadSms, getUnreadMessenger, getLeadLocations } from '@/lib/api';
import { DashboardStats, StaleSummary, CompanySettings, UnreadSmsSummary, UnreadMessengerSummary, LeadLocationItem } from '@/lib/types';
import { toast } from 'sonner';
import { TrendingUp, Users, CheckCircle2, Trophy, Bell, ArrowRight, Clock, MessageSquare } from 'lucide-react';
import StatusPieChart from '@/components/StatusPieChart';
import LeadsBySourceBarChart from '@/components/LeadsBySourceBarChart';

const LeadMap = dynamic(() => import('@/components/LeadMap'), { ssr: false });

type DatePeriod = 'all' | 'week' | 'month' | 'quarter' | 'year';

export default function DashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [companySettings, setCompanySettings] = useState<CompanySettings | null>(null);
  const [stuckLeads, setStuckLeads] = useState<any[]>([]);
  const [staleSummary, setStaleSummary] = useState<StaleSummary | null>(null);
  const [unreadSms, setUnreadSms] = useState<UnreadSmsSummary | null>(null);
  const [unreadMessenger, setUnreadMessenger] = useState<UnreadMessengerSummary | null>(null);
  const [leadLocations, setLeadLocations] = useState<LeadLocationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [datePeriod, setDatePeriod] = useState<DatePeriod>('all');

  useEffect(() => {
    fetchDashboard();
  }, [datePeriod]);

  const fetchDashboard = async () => {
    try {
      const [statsRes, stuckRes, staleRes, companyRes, unreadSmsRes, unreadMessengerRes, locationsRes] = await Promise.all([
        api.get('/api/dashboard/stats', { params: datePeriod === 'all' ? {} : { period: datePeriod } }),
        api.get('/api/dashboard/stuck-leads'),
        getStaleSummary().catch(() => null), // Don't fail if reminders not available
        getCompanySettings().catch(() => null), // Don't fail if settings not set up yet
        getUnreadSms().catch(() => ({ count: 0, messages: [] })),
        getUnreadMessenger().catch(() => ({ count: 0, messages: [] })),
        getLeadLocations(datePeriod === 'all' ? undefined : datePeriod).catch(() => []),
      ]);
      setStats(statsRes.data);
      setStuckLeads(stuckRes.data);
      setStaleSummary(staleRes);
      setCompanySettings(companyRes ?? null);
      setUnreadSms(unreadSmsRes ?? { count: 0, messages: [] });
      setUnreadMessenger(unreadMessengerRes ?? { count: 0, messages: [] });
      setLeadLocations(Array.isArray(locationsRes) ? locationsRes : []);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load dashboard');
      }
    } finally {
      setLoading(false);
    }
  };

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

  if (!stats) {
    return null;
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <h1 className="text-3xl font-semibold">Dashboard</h1>
          <div className="flex gap-2">
            {(['all', 'week', 'month', 'quarter', 'year'] as const).map((period) => (
              <Button
                key={period}
                variant={datePeriod === period ? 'default' : 'outline'}
                size="sm"
                onClick={() => setDatePeriod(period)}
              >
                {period === 'all' ? 'All' : period.charAt(0).toUpperCase() + period.slice(1)}
              </Button>
            ))}
          </div>
        </div>

        {/* Installation lead time – clear indicator for sales */}
        {companySettings?.installation_lead_time && (
          <Card className="mb-8 border-primary/30 bg-primary/5">
            <CardContent className="py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                    <Clock className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      Current installation lead time
                    </p>
                    <p className="text-2xl font-bold">{companySettings.installation_lead_time}</p>
                  </div>
                </div>
                <Link href="/settings/company">
                  <Button variant="outline" size="sm">
                    Edit in Company Settings
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
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
                  {stats.quoted_count} quoted
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
                quotedCount={stats.quoted_count}
                wonCount={stats.won_count}
                lostCount={stats.lost_count}
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
              <LeadMap locations={leadLocations} loading={loading} />
            </CardContent>
          </Card>
        </div>

        {/* Status Breakdown */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
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
                <div className="text-3xl font-bold">{stats.quoted_count}</div>
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
        </div>

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

        {/* Stuck Leads */}
        {stuckLeads.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Stuck Leads</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {stuckLeads.map((lead) => (
                  <div
                    key={lead.id}
                    onClick={() => router.push(`/leads/${lead.id}`)}
                    className="flex items-center justify-between p-3 rounded-lg bg-card border border-border cursor-pointer hover:bg-muted transition-colors"
                  >
                    <div>
                      <p className="font-medium">{lead.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {lead.status} • {lead.days_old} days old
                      </p>
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
