'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import ReminderList from '@/components/ReminderList';
import api, { getStaleSummary } from '@/lib/api';
import { DashboardStats, StaleSummary } from '@/lib/types';
import { toast } from 'sonner';
import { TrendingUp, Users, CheckCircle2, DollarSign, Bell, ArrowRight } from 'lucide-react';

export default function DashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [stuckLeads, setStuckLeads] = useState<any[]>([]);
  const [staleSummary, setStaleSummary] = useState<StaleSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboard();
  }, []);

  const fetchDashboard = async () => {
    try {
      const [statsRes, stuckRes, staleRes] = await Promise.all([
        api.get('/api/dashboard/stats'),
        api.get('/api/dashboard/stuck-leads'),
        getStaleSummary().catch(() => null), // Don't fail if reminders not available
      ]);
      setStats(statsRes.data);
      setStuckLeads(stuckRes.data);
      setStaleSummary(staleRes);
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
      <div className="min-h-screen bg-background">
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
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <h1 className="text-3xl font-semibold mb-8">Dashboard</h1>

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

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Won</CardTitle>
              <DollarSign className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.won_count}</div>
              <p className="text-xs text-muted-foreground">
                {stats.quoted_count} quoted
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Status Breakdown */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">New</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{stats.new_count}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Quoted</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{stats.quoted_count}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Lost</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{stats.lost_count}</div>
            </CardContent>
          </Card>
        </div>

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
                    className="flex items-center justify-between p-3 rounded-lg bg-card border border-border"
                  >
                    <div>
                      <p className="font-medium">{lead.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {lead.status} • {lead.days_old} days old
                      </p>
                    </div>
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
