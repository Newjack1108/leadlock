'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Lock, Unlock, Clock, Search, Plus } from 'lucide-react';
import api from '@/lib/api';
import { Lead, LeadStatus, LeadType, LeadSource } from '@/lib/types';
import { toast } from 'sonner';
import Link from 'next/link';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const statusColors: Record<LeadStatus, string> = {
  NEW: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300',
  CONTACT_ATTEMPTED: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/20 dark:text-yellow-300',
  ENGAGED: 'bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-300',
  QUALIFIED: 'bg-primary/10 text-primary',
  QUOTED: 'bg-secondary/10 text-secondary',
  WON: 'bg-success/10 text-success',
  LOST: 'bg-destructive/10 text-destructive',
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
  const [leadTypeFilter, setLeadTypeFilter] = useState<LeadType | 'ALL'>('ALL');
  const [leadSourceFilter, setLeadSourceFilter] = useState<LeadSource | 'ALL'>('ALL');
  const [search, setSearch] = useState('');
  const [searchDebounced, setSearchDebounced] = useState('');
  const [myLeadsOnly, setMyLeadsOnly] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newLead, setNewLead] = useState({
    name: '',
    email: '',
    phone: '',
    postcode: '',
    description: '',
    lead_type: LeadType.UNKNOWN,
    lead_source: LeadSource.MANUAL_ENTRY,
  });

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchDebounced(search);
    }, 300);

    return () => clearTimeout(timer);
  }, [search]);

  // Fetch leads when filters change
  useEffect(() => {
    fetchLeads();
  }, [statusFilter, leadTypeFilter, leadSourceFilter, searchDebounced, myLeadsOnly]);

  const fetchLeads = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (statusFilter !== 'ALL') {
        params.status = statusFilter;
      }
      if (leadTypeFilter !== 'ALL') {
        params.lead_type = leadTypeFilter;
      }
      if (leadSourceFilter !== 'ALL') {
        params.lead_source = leadSourceFilter;
      }
      if (searchDebounced) {
        params.search = searchDebounced;
      }
      if (myLeadsOnly) {
        params.myLeads = true;
      }

      const response = await api.get('/api/leads', { params });
      // Filter out QUOTED, WON, and LOST leads
      const filteredLeads = response.data.filter((lead: Lead) => !['QUOTED', 'WON', 'LOST'].includes(lead.status));
      setLeads(filteredLeads);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        toast.error('Server is not responding. Check that the API is running.');
      } else if (!error.response) {
        toast.error('Cannot reach server. Check your connection and API URL.');
      } else {
        toast.error('Failed to load leads');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCreateLead = async () => {
    if (!newLead.name.trim()) {
      toast.error('Name is required');
      return;
    }

    try {
      setCreating(true);
      await api.post('/api/leads', {
        name: newLead.name.trim(),
        email: newLead.email.trim() || undefined,
        phone: newLead.phone.trim() || undefined,
        postcode: newLead.postcode.trim() || undefined,
        description: newLead.description.trim() || undefined,
        lead_type: newLead.lead_type,
        lead_source: newLead.lead_source,
      });
      
      toast.success('Lead created successfully');
      setCreateDialogOpen(false);
      setNewLead({ name: '', email: '', phone: '', postcode: '', description: '', lead_type: LeadType.UNKNOWN, lead_source: LeadSource.MANUAL_ENTRY });
      fetchLeads();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to create lead');
    } finally {
      setCreating(false);
    }
  };

  const statusTabs: (LeadStatus | 'ALL')[] = ['ALL', ...Object.values(LeadStatus).filter(status => !['QUOTED', 'WON', 'LOST'].includes(status))];

  return (
    <div className="min-h-screen">
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
            <Select value={leadTypeFilter} onValueChange={(value) => setLeadTypeFilter(value as LeadType | 'ALL')}>
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder="Lead Type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All Types</SelectItem>
                {Object.values(LeadType).map((type) => (
                  <SelectItem key={type} value={type}>{type}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={leadSourceFilter} onValueChange={(value) => setLeadSourceFilter(value as LeadSource | 'ALL')}>
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder="Lead Source" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All Sources</SelectItem>
                {Object.values(LeadSource).map((source) => (
                  <SelectItem key={source} value={source}>{source.replace('_', ' ')}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant={myLeadsOnly ? 'default' : 'outline'}
              onClick={() => setMyLeadsOnly(!myLeadsOnly)}
            >
              My Leads
            </Button>
            <Button
              onClick={() => setCreateDialogOpen(true)}
              className="bg-primary hover:bg-primary/90"
            >
              <Plus className="h-4 w-4 mr-2" />
              Create Lead
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
                          <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                            {lead.lead_type}
                          </Badge>
                          <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                            {lead.lead_source.replace('_', ' ')}
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

        {/* Create Lead Dialog */}
        <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Lead</DialogTitle>
              <DialogDescription>
                Add a new lead to the system. Name is required.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="name">
                  Name <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="name"
                  value={newLead.name}
                  onChange={(e) => setNewLead({ ...newLead, name: e.target.value })}
                  placeholder="John Doe"
                  disabled={creating}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={newLead.email}
                  onChange={(e) => setNewLead({ ...newLead, email: e.target.value })}
                  placeholder="john@example.com"
                  disabled={creating}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="phone">Phone</Label>
                <Input
                  id="phone"
                  value={newLead.phone}
                  onChange={(e) => setNewLead({ ...newLead, phone: e.target.value })}
                  placeholder="+44 1234 567890"
                  disabled={creating}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="postcode">Postcode</Label>
                <Input
                  id="postcode"
                  value={newLead.postcode}
                  onChange={(e) => setNewLead({ ...newLead, postcode: e.target.value })}
                  placeholder="CW1 2AB"
                  disabled={creating}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={newLead.description}
                  onChange={(e) => setNewLead({ ...newLead, description: e.target.value })}
                  placeholder="Additional information about the lead..."
                  disabled={creating}
                  rows={4}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="lead_type">Lead Type</Label>
                <Select
                  value={newLead.lead_type}
                  onValueChange={(value) => setNewLead({ ...newLead, lead_type: value as LeadType })}
                  disabled={creating}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.values(LeadType).map((type) => (
                      <SelectItem key={type} value={type}>{type}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="lead_source">Lead Source</Label>
                <Select
                  value={newLead.lead_source}
                  onValueChange={(value) => setNewLead({ ...newLead, lead_source: value as LeadSource })}
                  disabled={creating}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.values(LeadSource).map((source) => (
                      <SelectItem key={source} value={source}>{source.replace('_', ' ')}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setCreateDialogOpen(false);
                  setNewLead({ name: '', email: '', phone: '', postcode: '', description: '', lead_type: LeadType.UNKNOWN, lead_source: LeadSource.MANUAL_ENTRY });
                }}
                disabled={creating}
              >
                Cancel
              </Button>
              <Button onClick={handleCreateLead} disabled={creating || !newLead.name.trim()}>
                {creating ? 'Creating...' : 'Create Lead'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}
