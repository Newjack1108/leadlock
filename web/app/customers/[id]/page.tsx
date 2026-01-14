'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import QuoteLockCard from '@/components/QuoteLockCard';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Phone,
  Mail,
  MessageSquare,
  PhoneCall,
  ArrowRight,
  Send,
} from 'lucide-react';
import api from '@/lib/api';
import { Customer, Activity, ActivityType, Lead } from '@/lib/types';
import { toast } from 'sonner';
import SendQuoteEmailDialog from '@/components/SendQuoteEmailDialog';
import ComposeEmailDialog from '@/components/ComposeEmailDialog';

const activityIcons: Record<ActivityType, any> = {
  SMS_SENT: MessageSquare,
  SMS_RECEIVED: MessageSquare,
  EMAIL_SENT: Mail,
  EMAIL_RECEIVED: Mail,
  CALL_ATTEMPTED: Phone,
  LIVE_CALL: PhoneCall,
  WHATSAPP_SENT: MessageSquare,
  WHATSAPP_RECEIVED: MessageSquare,
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
  NOTE: 'text-muted-foreground',
};

export default function CustomerDetailPage() {
  const router = useRouter();
  const params = useParams();
  const customerId = parseInt(params.id as string);

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [quotes, setQuotes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [quoteLocked, setQuoteLocked] = useState(false);
  const [quoteLockReason, setQuoteLockReason] = useState<any>(null);
  const [sendEmailDialogOpen, setSendEmailDialogOpen] = useState(false);
  const [selectedQuoteId, setSelectedQuoteId] = useState<number | null>(null);
  const [composeEmailDialogOpen, setComposeEmailDialogOpen] = useState(false);

  useEffect(() => {
    if (customerId) {
      fetchCustomer();
      fetchActivities();
      fetchLeads();
      fetchQuotes();
    }
  }, [customerId]);

  useEffect(() => {
    if (customer) {
      checkQuotePrerequisites();
    }
  }, [customer]);

  const fetchCustomer = async () => {
    try {
      const response = await api.get(`/api/customers/${customerId}`);
      setCustomer(response.data);
    } catch (error: any) {
      toast.error('Failed to load customer');
      if (error.response?.status === 401) {
        router.push('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  const fetchActivities = async () => {
    try {
      const response = await api.get(`/api/customers/${customerId}/activities`);
      setActivities(response.data);
    } catch (error: any) {
      console.error('Failed to load activities');
    }
  };

  const fetchLeads = async () => {
    try {
      const response = await api.get(`/api/customers/${customerId}/leads`);
      setLeads(response.data);
    } catch (error: any) {
      console.error('Failed to load leads');
    }
  };

  const fetchQuotes = async () => {
    try {
      const response = await api.get(`/api/customers/${customerId}/quotes`);
      setQuotes(response.data);
    } catch (error: any) {
      console.error('Failed to load quotes');
    }
  };

  const checkQuotePrerequisites = async () => {
    try {
      const response = await api.get(`/api/customers/${customerId}/quote-status`);
      setQuoteLocked(response.data.quote_locked);
      setQuoteLockReason(response.data.quote_lock_reason);
    } catch (error) {
      console.error('Failed to check quote prerequisites');
    }
  };

  const handleQuickLog = async (activityType: ActivityType) => {
    try {
      await api.post(`/api/customers/${customerId}/activities`, {
        activity_type: activityType,
      });
      toast.success('Activity logged');
      fetchActivities();
      checkQuotePrerequisites();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to log activity');
    }
  };

  const handleUpdateCustomer = async (field: string, value: any) => {
    try {
      await api.patch(`/api/customers/${customerId}`, {
        [field]: value,
      });
      fetchCustomer();
      checkQuotePrerequisites();
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

  if (!customer) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Customer not found</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <Button variant="ghost" onClick={() => router.push('/customers')} className="mb-4">
            ← Back to Customers
          </Button>
          <h1 className="text-3xl font-semibold">{customer.name}</h1>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Customer Profile Card */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Customer Profile</CardTitle>
                  <Badge className="bg-primary/20 text-primary">
                    {customer.customer_number}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="mb-4 p-3 bg-muted rounded-md">
                  <div className="text-sm font-medium">Customer Number</div>
                  <div className="text-lg font-semibold">{customer.customer_number}</div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Customer since: {new Date(customer.customer_since).toLocaleDateString()}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Email <span className="text-destructive">*</span></Label>
                    <Input
                      value={customer.email || ''}
                      onChange={(e) => handleUpdateCustomer('email', e.target.value)}
                      onBlur={(e) => handleUpdateCustomer('email', e.target.value)}
                    />
                  </div>
                  <div>
                    <Label>Phone <span className="text-destructive">*</span></Label>
                    <Input
                      value={customer.phone || ''}
                      onChange={(e) => handleUpdateCustomer('phone', e.target.value)}
                      onBlur={(e) => handleUpdateCustomer('phone', e.target.value)}
                    />
                  </div>
                  <div className="col-span-2">
                    <Label>Address Line 1 <span className="text-destructive">*</span></Label>
                    <Input
                      value={customer.address_line1 || ''}
                      onChange={(e) => handleUpdateCustomer('address_line1', e.target.value)}
                      onBlur={(e) => handleUpdateCustomer('address_line1', e.target.value)}
                    />
                  </div>
                  <div className="col-span-2">
                    <Label>Address Line 2 (Optional)</Label>
                    <Input
                      value={customer.address_line2 || ''}
                      onChange={(e) => handleUpdateCustomer('address_line2', e.target.value)}
                      onBlur={(e) => handleUpdateCustomer('address_line2', e.target.value)}
                    />
                  </div>
                  <div>
                    <Label>City <span className="text-destructive">*</span></Label>
                    <Input
                      value={customer.city || ''}
                      onChange={(e) => handleUpdateCustomer('city', e.target.value)}
                      onBlur={(e) => handleUpdateCustomer('city', e.target.value)}
                    />
                  </div>
                  <div>
                    <Label>County <span className="text-destructive">*</span></Label>
                    <Input
                      value={customer.county || ''}
                      onChange={(e) => handleUpdateCustomer('county', e.target.value)}
                      onBlur={(e) => handleUpdateCustomer('county', e.target.value)}
                    />
                  </div>
                  <div>
                    <Label>Postcode <span className="text-destructive">*</span></Label>
                    <Input
                      value={customer.postcode || ''}
                      onChange={(e) => handleUpdateCustomer('postcode', e.target.value)}
                      onBlur={(e) => handleUpdateCustomer('postcode', e.target.value)}
                    />
                  </div>
                  <div>
                    <Label>Country</Label>
                    <Input
                      value={customer.country || 'United Kingdom'}
                      onChange={(e) => handleUpdateCustomer('country', e.target.value)}
                      onBlur={(e) => handleUpdateCustomer('country', e.target.value)}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Quote Lock Card */}
            <QuoteLockCard 
              customer={customer}
              quoteLocked={quoteLocked}
              quoteLockReason={quoteLockReason}
            />

            {/* Quotes Card */}
            <Card>
              <CardHeader>
                <CardTitle>Quotes</CardTitle>
              </CardHeader>
              <CardContent>
                {quotes.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No quotes yet</p>
                ) : (
                  <div className="space-y-2">
                    {quotes.map((quote) => (
                      <div
                        key={quote.id}
                        className="p-3 border rounded-md"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div 
                            className="flex-1 cursor-pointer hover:text-primary"
                            onClick={() => router.push(`/quotes/${quote.id}`)}
                          >
                            <span className="font-medium">{quote.quote_number}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge>{quote.status}</Badge>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedQuoteId(quote.id);
                                setSendEmailDialogOpen(true);
                              }}
                            >
                              Send Quote
                            </Button>
                          </div>
                        </div>
                        <div 
                          className="text-sm text-muted-foreground cursor-pointer hover:text-primary"
                          onClick={() => router.push(`/quotes/${quote.id}`)}
                        >
                          £{quote.total_amount.toFixed(2)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Emails Card */}
            <Card>
              <CardHeader>
                <CardTitle>Emails</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <Button
                  variant="default"
                  className="w-full"
                  onClick={() => setComposeEmailDialogOpen(true)}
                >
                  <Send className="h-4 w-4 mr-2" />
                  Compose Email
                </Button>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => router.push(`/customers/${customerId}/emails`)}
                >
                  <Mail className="h-4 w-4 mr-2" />
                  View All Emails
                </Button>
              </CardContent>
            </Card>

            {/* Related Leads Card */}
            <Card>
              <CardHeader>
                <CardTitle>Related Leads</CardTitle>
              </CardHeader>
              <CardContent>
                {leads.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No related leads</p>
                ) : (
                  <div className="space-y-2">
                    {leads.map((lead) => (
                      <div
                        key={lead.id}
                        className="p-3 border rounded-md cursor-pointer hover:bg-muted"
                        onClick={() => router.push(`/leads/${lead.id}`)}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{lead.name}</span>
                          <Badge>{lead.status.replace('_', ' ')}</Badge>
                        </div>
                        <div className="text-sm text-muted-foreground mt-1">
                          {lead.lead_type} • {lead.lead_source}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

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
                                {new Date(activity.created_at).toLocaleString()}
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

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Quick Log */}
            <Card>
              <CardHeader>
                <CardTitle>Quick Log</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <Button
                  variant="outline"
                  className="w-full justify-start"
                  onClick={() => handleQuickLog(ActivityType.CALL_ATTEMPTED)}
                >
                  <Phone className="h-4 w-4 mr-2" />
                  Call Attempted
                </Button>
                <Button
                  variant="outline"
                  className="w-full justify-start"
                  onClick={() => handleQuickLog(ActivityType.SMS_SENT)}
                >
                  <MessageSquare className="h-4 w-4 mr-2" />
                  SMS Sent
                </Button>
                <Button
                  variant="outline"
                  className="w-full justify-start"
                  onClick={() => handleQuickLog(ActivityType.SMS_RECEIVED)}
                >
                  <MessageSquare className="h-4 w-4 mr-2" />
                  SMS Received
                </Button>
                <Button
                  variant="outline"
                  className="w-full justify-start"
                  onClick={() => handleQuickLog(ActivityType.LIVE_CALL)}
                >
                  <PhoneCall className="h-4 w-4 mr-2" />
                  Live Call
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>

      {customer && selectedQuoteId && (
        <SendQuoteEmailDialog
          open={sendEmailDialogOpen}
          onOpenChange={setSendEmailDialogOpen}
          quoteId={selectedQuoteId}
          customer={customer}
          onSuccess={() => {
            fetchQuotes();
            fetchActivities();
          }}
        />
      )}

      {customer && (
        <ComposeEmailDialog
          open={composeEmailDialogOpen}
          onOpenChange={setComposeEmailDialogOpen}
          customer={customer}
          onSuccess={() => {
            fetchActivities();
            checkQuotePrerequisites();
          }}
        />
      )}
    </div>
  );
}
