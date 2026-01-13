'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Lock, Unlock, Clock, Search } from 'lucide-react';
import api from '@/lib/api';
import { Lead, LeadStatus } from '@/lib/types';
import { toast } from 'sonner';
import Link from 'next/link';

const statusColors: Record<LeadStatus, string> = {
  NEW: 'bg-blue-500/20 text-blue-300',
  CONTACT_ATTEMPTED: 'bg-yellow-500/20 text-yellow-300',
  ENGAGED: 'bg-purple-500/20 text-purple-300',
  QUALIFIED: 'bg-primary/20 text-primary',
  QUOTED: 'bg-secondary/20 text-secondary',
  WON: 'bg-success/20 text-success',
  LOST: 'bg-destructive/20 text-destructive',
};

function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

export default function LeadsPage() {
  const router = useRouter();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<LeadStatus | 'ALL'>('ALL');
  const [search, setSearch] = useState('');
  const [myLeadsOnly, setMyLeadsOnly] = useState(false);

  useEffect(() => {
    fetchLeads();
  }, [statusFilter, search, myLeadsOnly]);

  const fetchLeads = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (statusFilter !== 'ALL') {
        params.status = statusFilter;
      }
      if (search) {
        params.search = search;
      }
      if (myLeadsOnly) {
        params.myLeads = true;
      }

      const response = await api.get('/api/leads', { params });
      setLeads(response.data);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load leads');
      }
    } finally {
      setLoading(false);
    }
  };

  const statusTabs: (LeadStatus | 'ALL')[] = ['ALL', ...Object.values(LeadStatus)];

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-semibold mb-6">Leads</h1>
          
          {/* Filters */}
          <div className="flex flex-col md:flex-row gap-4 mb-6">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search by name, phone, email, postcode..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>
            <Button
              variant={myLeadsOnly ? 'default' : 'outline'}
              onClick={() => setMyLeadsOnly(!myLeadsOnly)}
            >
              My Leads
            </Button>
          </div>

          {/* Status Tabs */}
          <div className="flex flex-wrap gap-2 mb-6">
            {statusTabs.map((status) => (
              <Button
                key={status}
                variant={statusFilter === status ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter(status)}
              >
                {status === 'ALL' ? 'All' : status.replace('_', ' ')}
              </Button>
            ))}
          </div>
        </div>

        {/* Leads List */}
        {loading ? (
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        ) : leads.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">No leads found</div>
        ) : (
          <div className="grid gap-4">
            {leads.map((lead) => (
              <Link key={lead.id} href={`/leads/${lead.id}`}>
                <Card className="hover:border-primary/50 transition-colors cursor-pointer">
                  <CardContent className="p-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <h3 className="text-lg font-semibold">{lead.name}</h3>
                          <Badge className={statusColors[lead.status]}>
                            {lead.status.replace('_', ' ')}
                          </Badge>
                          {lead.quote_locked && lead.status === LeadStatus.QUALIFIED && (
                            <Lock className="h-4 w-4 text-destructive" />
                          )}
                          {!lead.quote_locked && lead.status === LeadStatus.QUALIFIED && (
                            <Unlock className="h-4 w-4 text-success" />
                          )}
                          {lead.sla_badge && (
                            <Badge
                              variant={lead.sla_badge === 'red' ? 'destructive' : 'default'}
                              className="ml-2"
                            >
                              <Clock className="h-3 w-3 mr-1" />
                              Overdue
                            </Badge>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                          {lead.phone && <span>{lead.phone}</span>}
                          {lead.email && <span>{lead.email}</span>}
                          {lead.postcode && <span>{lead.postcode}</span>}
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {formatTimeAgo(lead.created_at)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
