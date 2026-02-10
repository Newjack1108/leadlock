'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Image from 'next/image';
import Header from '@/components/Header';
import QuoteLockCard from '@/components/QuoteLockCard';
import ComposeEmailDialog from '@/components/ComposeEmailDialog';
import CallNotesDialog from '@/components/CallNotesDialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Phone,
  Mail,
  MessageSquare,
  PhoneCall,
  Clock,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import api from '@/lib/api';
import { formatDateTime } from '@/lib/utils';
import { Lead, Activity, ActivityType, LeadStatus, Timeframe, LeadType, LeadSource } from '@/lib/types';
import { toast } from 'sonner';

const activityIcons: Record<ActivityType, any> = {
  SMS_SENT: MessageSquare,
  SMS_RECEIVED: MessageSquare,
  EMAIL_SENT: Mail,
  EMAIL_RECEIVED: Mail,
  CALL_ATTEMPTED: Phone,
  LIVE_CALL: PhoneCall,
  WHATSAPP_SENT: MessageSquare,
  WHATSAPP_RECEIVED: MessageSquare,
  MESSENGER_SENT: MessageSquare,
  MESSENGER_RECEIVED: MessageSquare,
  NOTE: MessageSquare,
};

const activityColors: Record<ActivityType, string> = {
  SMS_SENT: 'text-blue-600',
  SMS_RECEIVED: 'text-green-600',
  EMAIL_SENT: 'text-blue-600',
  EMAIL_RECEIVED: 'text-green-600',
  CALL_ATTEMPTED: 'text-yellow-600',
  LIVE_CALL: 'text-green-600',
  WHATSAPP_SENT: 'text-blue-600',
  WHATSAPP_RECEIVED: 'text-green-600',
  MESSENGER_SENT: 'text-blue-600',
  MESSENGER_RECEIVED: 'text-green-600',
  NOTE: 'text-muted-foreground',
};

export default function LeadDetailPage() {
  const router = useRouter();
  const params = useParams();
  const leadId = parseInt(params.id as string);

  const [lead, setLead] = useState<Lead | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [allowedTransitions, setAllowedTransitions] = useState<string[]>([]);
  const [qualifyLoading, setQualifyLoading] = useState(false);
  const [rejectLoading, setRejectLoading] = useState(false);
  const [composeEmailOpen, setComposeEmailOpen] = useState(false);
  const [callNotesDialogOpen, setCallNotesDialogOpen] = useState(false);
  const [ensureCustomerLoading, setEnsureCustomerLoading] = useState(false);

  useEffect(() => {
    if (leadId) {
      fetchLead();
      fetchActivities();
    }
  }, [leadId]);

  const fetchLead = async () => {
    try {
      const response = await api.get(`/api/leads/${leadId}`);
      setLead(response.data);
      try {
        const transitionsRes = await api.get(`/api/leads/${leadId}/allowed-transitions`);
        setAllowedTransitions(transitionsRes.data.allowed_transitions || []);
      } catch {
        setAllowedTransitions([]);
      }
    } catch (error: any) {
      toast.error('Failed to load lead');
      if (error.response?.status === 401) {
        router.push('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  const fetchActivities = async () => {
    try {
      const response = await api.get(`/api/leads/${leadId}/activities`);
      setActivities(response.data);
    } catch (error: any) {
      console.error('Failed to load activities');
    }
  };

  const ensureCustomerThen = async (): Promise<Lead | null> => {
    if (lead?.customer) return lead;
    setEnsureCustomerLoading(true);
    try {
      await api.post(`/api/leads/${leadId}/activities`, { activity_type: 'NOTE', notes: 'Contact initiated' });
      const response = await api.get(`/api/leads/${leadId}`);
      setLead(response.data);
      return response.data;
    } catch {
      toast.error('Failed to initialize contact');
      return null;
    } finally {
      setEnsureCustomerLoading(false);
    }
  };

  const handleComposeEmail = async () => {
    const updated = await ensureCustomerThen();
    if (updated?.customer) setComposeEmailOpen(true);
  };

  const handleViewEmails = async () => {
    const updated = await ensureCustomerThen();
    if (updated?.customer) router.push(`/customers/${updated.customer!.id}/emails`);
  };

  const handleViewSms = async () => {
    const updated = await ensureCustomerThen();
    if (updated?.customer) router.push(`/customers/${updated.customer!.id}/sms`);
  };

  const handleViewMessenger = async () => {
    const updated = await ensureCustomerThen();
    if (updated?.customer) router.push(`/customers/${updated.customer!.id}/messenger`);
  };

  const handleCallClick = async () => {
    const updated = await ensureCustomerThen();
    if (updated?.customer && updated.phone) setCallNotesDialogOpen(true);
  };

  const handleQualify = async () => {
    if (!allowedTransitions.includes('QUALIFIED')) return;
    setQualifyLoading(true);
    try {
      await api.post(`/api/leads/${leadId}/transition`, { new_status: 'QUALIFIED' });
      toast.success('Lead qualified');
      fetchLead();
      fetchActivities();
    } catch (error: any) {
      toast.error(error.response?.data?.detail?.message || error.response?.data?.detail || 'Failed to qualify lead');
    } finally {
      setQualifyLoading(false);
    }
  };

  const handleReject = async () => {
    if (!allowedTransitions.includes('LOST')) return;
    if (!window.confirm('Are you sure you want to reject this lead? This will mark the lead as lost.')) return;
    setRejectLoading(true);
    try {
      await api.post(`/api/leads/${leadId}/transition`, { new_status: 'LOST' });
      toast.success('Lead rejected');
      fetchLead();
      fetchActivities();
    } catch (error: any) {
      toast.error(error.response?.data?.detail?.message || error.response?.data?.detail || 'Failed to reject lead');
    } finally {
      setRejectLoading(false);
    }
  };

  const handleUpdateLead = async (field: string, value: any) => {
    try {
      await api.patch(`/api/leads/${leadId}`, {
        [field]: value,
      });
      fetchLead();
    } catch (error: any) {
      toast.error('Failed to update');
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

  if (!lead) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Lead not found</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <Button variant="ghost" onClick={() => router.push('/leads')} className="mb-4">
            ← Back to Leads
          </Button>
          <h1 className="text-3xl font-semibold">{lead.name}</h1>
        </div>

        <div className="space-y-6">
          {/* Two-column layout: Lead Info | Contact cards */}
          <div className="flex flex-col md:flex-row gap-6">
            {/* Left: Lead Information */}
            <Card className="flex-1 min-w-0">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Lead Information</CardTitle>
                  <div className="flex items-center gap-2">
                    {allowedTransitions.includes('QUALIFIED') && lead.status !== LeadStatus.QUALIFIED && (
                      <Button
                        size="sm"
                        onClick={handleQualify}
                        disabled={qualifyLoading}
                        className="gap-1"
                      >
                        <CheckCircle className="h-4 w-4" />
                        {qualifyLoading ? 'Qualifying...' : 'Qualify'}
                      </Button>
                    )}
                    {allowedTransitions.includes('LOST') && lead.status !== LeadStatus.LOST && (
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={handleReject}
                        disabled={rejectLoading}
                        className="gap-1"
                      >
                        <XCircle className="h-4 w-4" />
                        {rejectLoading ? 'Rejecting...' : 'Reject'}
                      </Button>
                    )}
                    <Badge className="bg-primary/20 text-primary">
                      {lead.status.replace('_', ' ')}
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Email</Label>
                    <Input
                      value={lead.email || ''}
                      onChange={(e) => handleUpdateLead('email', e.target.value)}
                      onBlur={(e) => handleUpdateLead('email', e.target.value)}
                    />
                  </div>
                  <div>
                    <Label>Phone</Label>
                    <div className="flex gap-2 items-center">
                      <Input
                        className="flex-1"
                        value={lead.phone || ''}
                        onChange={(e) => handleUpdateLead('phone', e.target.value)}
                        onBlur={(e) => handleUpdateLead('phone', e.target.value)}
                      />
                      {lead.phone && (
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="shrink-0"
                          title="Call"
                          onClick={handleCallClick}
                          disabled={ensureCustomerLoading}
                        >
                          <Phone className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                  <div>
                    <Label>Postcode</Label>
                    <Input
                      value={lead.postcode || ''}
                      onChange={(e) => handleUpdateLead('postcode', e.target.value)}
                      onBlur={(e) => handleUpdateLead('postcode', e.target.value)}
                    />
                  </div>
                  <div>
                    <Label>Timeframe</Label>
                    <Select
                      value={lead.timeframe}
                      onValueChange={(value) => handleUpdateLead('timeframe', value)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.values(Timeframe).map((tf) => (
                          <SelectItem key={tf} value={tf}>
                            {tf.replace('_', ' ')}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Lead Type</Label>
                    <Select
                      value={lead.lead_type}
                      onValueChange={(value) => handleUpdateLead('lead_type', value)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.values(LeadType).map((type) => (
                          <SelectItem key={type} value={type}>
                            {type}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Lead Source</Label>
                    <Select
                      value={lead.lead_source}
                      onValueChange={(value) => handleUpdateLead('lead_source', value)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.values(LeadSource).map((source) => (
                          <SelectItem key={source} value={source}>
                            {source.replace('_', ' ')}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div>
                  <Label>Description</Label>
                  <Textarea
                    value={lead.description || ''}
                    onChange={(e) => handleUpdateLead('description', e.target.value)}
                    onBlur={(e) => handleUpdateLead('description', e.target.value)}
                    rows={3}
                    placeholder="Additional information about the lead..."
                  />
                </div>
                <div>
                  <Label>Scope Notes</Label>
                  <Textarea
                    value={lead.scope_notes || ''}
                    onChange={(e) => handleUpdateLead('scope_notes', e.target.value)}
                    onBlur={(e) => handleUpdateLead('scope_notes', e.target.value)}
                    rows={3}
                  />
                </div>
                <div>
                  <Label>Product Interest</Label>
                  <Textarea
                    value={lead.product_interest || ''}
                    onChange={(e) => handleUpdateLead('product_interest', e.target.value)}
                    onBlur={(e) => handleUpdateLead('product_interest', e.target.value)}
                    rows={2}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Right: Contact cards stacked */}
            <div className="flex flex-col gap-4 md:w-80 md:flex-shrink-0 md:min-h-0">
              <Card className="flex-1 min-h-0 flex flex-col">
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Image src="/email-icon.png" alt="" width={32} height={32} className="shrink-0" />
                    <CardTitle>Emails</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={handleComposeEmail}
                    disabled={ensureCustomerLoading}
                  >
                    Compose Email
                  </Button>
                  <Button
                    variant="link"
                    className="w-full p-0 h-auto text-muted-foreground hover:text-primary"
                    onClick={handleViewEmails}
                    disabled={ensureCustomerLoading}
                  >
                    View all emails
                  </Button>
                </CardContent>
              </Card>
              <Card className="flex-1 min-h-0 flex flex-col">
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Image src="/sms-icon.png" alt="" width={32} height={32} className="shrink-0" />
                    <CardTitle>SMS</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={handleViewSms}
                    disabled={ensureCustomerLoading}
                  >
                    View SMS
                  </Button>
                </CardContent>
              </Card>
              <Card className="flex-1 min-h-0 flex flex-col">
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Image src="/messenger-icon.png" alt="" width={32} height={32} className="shrink-0" />
                    <CardTitle>Messenger</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <Button
                    variant="outline"
                    className="w-full"
                    onClick={handleViewMessenger}
                    disabled={ensureCustomerLoading}
                  >
                    View Messenger
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>

            {/* Customer Link Card */}
            {lead.customer && (
              <Card>
                <CardHeader>
                  <CardTitle>Customer Profile</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="mb-4 p-3 bg-muted rounded-md">
                    <div className="text-sm font-medium">Customer Number</div>
                    <div className="text-lg font-semibold">{lead.customer.customer_number}</div>
                    <div className="text-xs text-muted-foreground mt-1">
                      Customer since: {new Date(lead.customer.customer_since).toLocaleDateString()}
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    onClick={() => router.push(`/customers/${lead.customer!.id}`)}
                    className="w-full"
                  >
                    View Customer Profile →
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* Quote Lock Card */}
            {lead.status === LeadStatus.QUALIFIED && lead.customer && (
              <QuoteLockCard 
                customer={lead.customer} 
                quoteLocked={lead.quote_locked}
                quoteLockReason={lead.quote_lock_reason}
              />
            )}

            {/* Activity Timeline */}
            <Card>
              <CardHeader>
                <CardTitle>Activity Timeline</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {activities.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No activities yet</p>
                  ) : (
                    activities.map((activity) => {
                      const Icon = activityIcons[activity.activity_type];
                      return (
                        <div key={activity.id} className="flex gap-4">
                          <div className={`${activityColors[activity.activity_type]}`}>
                            <Icon className="h-5 w-5" />
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-medium">
                                {activity.activity_type.replace('_', ' ')}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {formatDateTime(activity.created_at)}
                              </span>
                            </div>
                            {activity.notes && (
                              <p className="text-sm text-muted-foreground mt-1">
                                {activity.notes}
                              </p>
                            )}
                            {activity.created_by_name && (
                              <p className="text-xs text-muted-foreground mt-1">
                                by {activity.created_by_name}
                              </p>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

        {lead.customer && (
          <ComposeEmailDialog
            open={composeEmailOpen}
            onOpenChange={setComposeEmailOpen}
            customer={lead.customer}
            onSuccess={() => {
              fetchLead();
              fetchActivities();
            }}
          />
        )}

        {lead.customer && lead.phone && (
          <CallNotesDialog
            open={callNotesDialogOpen}
            onOpenChange={setCallNotesDialogOpen}
            customerId={lead.customer.id}
            customerName={lead.name}
            phone={lead.phone}
            onSuccess={() => {
              fetchLead();
              fetchActivities();
            }}
          />
        )}
      </main>
    </div>
  );
}
