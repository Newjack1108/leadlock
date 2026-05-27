'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Image from 'next/image';
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
  Plus,
  History,
  FileText,
  CheckCircle,
  XCircle,
  Clock,
  User,
  Building,
  ShoppingBag,
  Eye,
  Globe,
  ChevronDown,
  ChevronUp,
  Pencil,
  Trash2,
  Upload,
  BellOff,
  Bell,
  Info,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import api, {
  getCustomerHistory,
  getCustomerCommunicationStats,
  createLeadFromCustomer,
  getCustomerUnreadChannels,
  deleteCustomer,
} from '@/lib/api';
import { formatDateTime, formatActivityTypeLabel } from '@/lib/utils';
import { Customer, Activity, ActivityType, Lead, CustomerHistoryEvent, CustomerHistoryEventType, WebsiteVisit, Order, CustomerCommunicationStats } from '@/lib/types';
import SendQuoteEmailDialog from '@/components/SendQuoteEmailDialog';
import SendConfiguratorLinkDialog from '@/components/configurator/SendConfiguratorLinkDialog';
import ComposeEmailDialog from '@/components/ComposeEmailDialog';
import CallNotesDialog from '@/components/CallNotesDialog';
import AddManualActivityDialog from '@/components/AddManualActivityDialog';
import NinoxBadge from '@/components/NinoxBadge';
import TestCustomerBadge from '@/components/TestCustomerBadge';
import CustomerCommunicationBarChart from '@/components/CustomerCommunicationBarChart';
import FilesCard from '@/components/FilesCard';
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

const historyIcons: Record<CustomerHistoryEventType, any> = {
  ACTIVITY: MessageSquare,
  LEAD_STATUS_CHANGE: ArrowRight,
  LEAD_QUALIFIED: CheckCircle,
  QUOTE_CREATED: FileText,
  QUOTE_SENT: Send,
  QUOTE_VIEWED: Eye,
  QUOTE_ACCEPTED: CheckCircle,
  QUOTE_REJECTED: XCircle,
  QUOTE_EXPIRED: Clock,
  QUOTE_UPDATED: FileText,
  EMAIL_SENT: Mail,
  EMAIL_RECEIVED: Mail,
  CUSTOMER_CREATED: Building,
  CUSTOMER_UPDATED: Building,
  OPPORTUNITY_CREATED: FileText,
  ORDER_CREATED: ShoppingBag,
  ORDER_REMOVED: Trash2,
  ORDER_PAYMENT_UPDATED: CheckCircle,
  ORDER_INSTALLATION_UPDATED: CheckCircle,
  ORDER_ACCESS_SHEET_SENT: Send,
  ORDER_ACCESS_SHEET_COMPLETED: CheckCircle,
  ORDER_SENT_TO_PRODUCTION: Send,
  ORDER_XERO_PUSHED: Upload,
  ORDER_INVOICE_ACTION: FileText,
};

const historyColors: Record<CustomerHistoryEventType, string> = {
  ACTIVITY: 'text-blue-600',
  LEAD_STATUS_CHANGE: 'text-yellow-600',
  LEAD_QUALIFIED: 'text-green-600',
  QUOTE_CREATED: 'text-blue-600',
  QUOTE_SENT: 'text-blue-600',
  QUOTE_VIEWED: 'text-purple-600',
  QUOTE_ACCEPTED: 'text-green-600',
  QUOTE_REJECTED: 'text-red-600',
  QUOTE_EXPIRED: 'text-orange-600',
  QUOTE_UPDATED: 'text-blue-600',
  EMAIL_SENT: 'text-blue-600',
  EMAIL_RECEIVED: 'text-green-600',
  CUSTOMER_CREATED: 'text-green-600',
  CUSTOMER_UPDATED: 'text-yellow-600',
  OPPORTUNITY_CREATED: 'text-blue-600',
  ORDER_CREATED: 'text-green-600',
  ORDER_REMOVED: 'text-red-600',
  ORDER_PAYMENT_UPDATED: 'text-green-600',
  ORDER_INSTALLATION_UPDATED: 'text-blue-600',
  ORDER_ACCESS_SHEET_SENT: 'text-blue-600',
  ORDER_ACCESS_SHEET_COMPLETED: 'text-green-600',
  ORDER_SENT_TO_PRODUCTION: 'text-purple-600',
  ORDER_XERO_PUSHED: 'text-blue-600',
  ORDER_INVOICE_ACTION: 'text-blue-600',
};

export default function CustomerDetailPage() {
  const router = useRouter();
  const params = useParams();
  const customerId = parseInt(params.id as string);

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [history, setHistory] = useState<CustomerHistoryEvent[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [quotes, setQuotes] = useState<any[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [ordersLoadError, setOrdersLoadError] = useState<string | null>(null);
  const [websiteVisits, setWebsiteVisits] = useState<WebsiteVisit[]>([]);
  const [communicationStats, setCommunicationStats] = useState<CustomerCommunicationStats>({
    email: { sent: 0, received: 0 },
    sms: { sent: 0, received: 0 },
    phone: { sent: 0, received: 0 },
    phone_answered: 0,
    phone_unanswered: 0,
  });
  const [loading, setLoading] = useState(true);
  const [quoteLocked, setQuoteLocked] = useState(false);
  const [quoteLockReason, setQuoteLockReason] = useState<any>(null);
  const [sendEmailDialogOpen, setSendEmailDialogOpen] = useState(false);
  const [configureLinkOpen, setConfigureLinkOpen] = useState(false);
  const [selectedQuoteId, setSelectedQuoteId] = useState<number | null>(null);
  const [composeEmailDialogOpen, setComposeEmailDialogOpen] = useState(false);
  const [callNotesDialogOpen, setCallNotesDialogOpen] = useState(false);
  const [manualActivityDialogOpen, setManualActivityDialogOpen] = useState(false);
  const [expandedActivityNotes, setExpandedActivityNotes] = useState<Record<number, boolean>>({});
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameBeforeEdit, setNameBeforeEdit] = useState('');
  const [createLeadLoading, setCreateLeadLoading] = useState(false);
  const [unreadChannels, setUnreadChannels] = useState({
    sms_unread: 0,
    messenger_unread: 0,
    email_unread: 0,
  });
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [outreachOptOutLoading, setOutreachOptOutLoading] = useState(false);

  useEffect(() => {
    if (customerId) {
      fetchCustomer();
      fetchActivities();
      fetchHistory();
      fetchLeads();
      fetchQuotes();
      fetchOrders();
      fetchWebsiteVisits();
      fetchUnreadChannels();
      fetchCommunicationStats();
    }
  }, [customerId]);

  useEffect(() => {
    const onFocus = () => {
      if (customerId) fetchUnreadChannels();
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
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

  const fetchHistory = async () => {
    try {
      const response = await getCustomerHistory(customerId);
      setHistory(response.events || []);
    } catch (error: any) {
      console.error('Failed to load history');
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

  const fetchOrders = async () => {
    setOrdersLoading(true);
    setOrdersLoadError(null);
    try {
      const response = await api.get(`/api/customers/${customerId}/orders`);
      setOrders(response.data);
    } catch (error: any) {
      console.error('Failed to load orders', error);
      setOrdersLoadError('Could not load this customer\'s orders right now.');
      toast.error('Failed to load customer orders');
    } finally {
      setOrdersLoading(false);
    }
  };

  const fetchWebsiteVisits = async () => {
    try {
      const response = await api.get(`/api/customers/${customerId}/website-visits`);
      setWebsiteVisits(response.data.visits || []);
    } catch (error: any) {
      console.error('Failed to load website visits');
    }
  };

  const fetchUnreadChannels = async () => {
    try {
      const data = await getCustomerUnreadChannels(customerId);
      setUnreadChannels(data);
    } catch {
      // Non-blocking; detail page still usable without unread counts
    }
  };

  const fetchCommunicationStats = async () => {
    try {
      const data = await getCustomerCommunicationStats(customerId);
      setCommunicationStats(data);
    } catch {
      // Non-blocking; profile page remains usable without analytics card
    }
  };

  const checkQuotePrerequisites = async () => {
    try {
      const response = await api.get(`/api/customers/${customerId}/quote-status`);
      setQuoteLocked(response.data.quote_locked);
      setQuoteLockReason(response.data.quote_lock_reason);
      // Log for debugging
      if (response.data.quote_locked) {
        console.log('Quote locked reason:', response.data.quote_lock_reason);
      }
    } catch (error) {
      console.error('Failed to check quote prerequisites:', error);
    }
  };

  const handleFieldChange = (field: string, value: string) => {
    setCustomer((prev) => (prev ? { ...prev, [field]: value } : null));
  };

  const handleUpdateCustomer = async (field: string, value: any) => {
    try {
      await api.patch(`/api/customers/${customerId}`, {
        [field]: value,
      });
      fetchHistory();
      checkQuotePrerequisites();
    } catch (error: any) {
      toast.error('Failed to update');
    }
  };

  const handleAutomatedOutreachOptOut = async (optOut: boolean) => {
    setOutreachOptOutLoading(true);
    try {
      await api.patch(`/api/customers/${customerId}`, {
        automated_reminder_outreach_opt_out: optOut,
      });
      setCustomer((prev) => (prev ? { ...prev, automated_reminder_outreach_opt_out: optOut } : null));
      toast.success(
        optOut
          ? 'Automated reminder SMS and email from rules are stopped for this customer.'
          : 'Automated reminder messages from rules are enabled again.'
      );
      fetchHistory();
    } catch {
      toast.error('Failed to update automated message setting');
    } finally {
      setOutreachOptOutLoading(false);
    }
  };

  const handleWrongEmailAddress = async (wrongEmail: boolean) => {
    try {
      await api.patch(`/api/customers/${customerId}`, {
        wrong_email_address: wrongEmail,
      });
      setCustomer((prev) => (prev ? { ...prev, wrong_email_address: wrongEmail } : null));
      toast.success(
        wrongEmail
          ? 'Wrong email flag enabled. Automated emails will be suppressed.'
          : 'Wrong email flag removed. Automated emails can send again.'
      );
      fetchHistory();
    } catch {
      toast.error('Failed to update wrong email setting');
    }
  };

  const handleDeleteCustomer = async () => {
    if (
      !window.confirm(
        `Delete ${customer?.name ?? 'this customer'} permanently? This removes quotes, orders, leads, and all related activity. This cannot be undone.`
      )
    ) {
      return;
    }
    setDeleteLoading(true);
    try {
      await deleteCustomer(customerId);
      toast.success('Customer removed');
      router.push('/customers');
    } catch (error: any) {
      const detail = error.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to delete customer');
    } finally {
      setDeleteLoading(false);
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

  if (!customer) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Customer not found</div>
        </div>
      </div>
    );
  }

  const preferredChannel = [
    { name: 'Email', received: communicationStats.email.received },
    { name: 'SMS', received: communicationStats.sms.received },
    { name: 'Phone', received: communicationStats.phone.received },
  ].sort((a, b) => b.received - a.received)[0];

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 sm:px-6 py-8">
        <div className="mb-6">
          <Button variant="ghost" onClick={() => router.push('/customers')} className="mb-4">
            ← Back to Customers
          </Button>
          <div className="flex items-center gap-2 flex-wrap">
            {editingName ? (
              <Input
                className="text-3xl font-semibold h-12 max-w-md"
                value={customer.name}
                onChange={(e) => handleFieldChange('name', e.target.value)}
                onBlur={async (e) => {
                  const v = e.target.value.trim();
                  if (v && v !== nameBeforeEdit) {
                    await handleUpdateCustomer('name', v);
                  } else if (!v) {
                    handleFieldChange('name', nameBeforeEdit);
                  }
                  setEditingName(false);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.currentTarget.blur();
                  } else if (e.key === 'Escape') {
                    handleFieldChange('name', nameBeforeEdit);
                    setEditingName(false);
                    (e.target as HTMLInputElement).blur();
                  }
                }}
                autoFocus
              />
            ) : (
              <h1 className="text-3xl font-semibold">{customer.name}</h1>
            )}
            {!editingName && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="shrink-0"
                title="Edit name"
                onClick={() => {
                  setNameBeforeEdit(customer.name);
                  setEditingName(true);
                }}
              >
                <Pencil className="h-4 w-4" />
              </Button>
            )}
            {customer.exclude_from_stats && <TestCustomerBadge />}
            {customer.source_system === 'Ninox' && (
              <NinoxBadge />
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="text-destructive border-destructive/40 hover:bg-destructive/10 ml-auto"
              disabled={deleteLoading}
              onClick={handleDeleteCustomer}
            >
              <Trash2 className="h-4 w-4 mr-1.5" />
              {deleteLoading ? 'Removing…' : 'Remove customer'}
            </Button>
          </div>
        </div>

        {customer.exclude_from_stats && (
          <div className="mb-4 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
            <Info className="h-4 w-4 shrink-0 mt-0.5" />
            <p>
              This is the sandbox customer. Use it to run leads, quotes, and messages without affecting
              dashboard stats or automated reminder outreach. Manual sends still work.
            </p>
          </div>
        )}

        <div className="space-y-6">
            {/* Customer Profile + Contact Methods */}
            <div className="flex flex-col md:flex-row gap-6">
              <Card className="flex-1 min-w-0">
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
                      Customer since: {new Date(customer.customer_since).toLocaleDateString('en-GB')}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label>Email <span className="text-destructive">*</span></Label>
                      <Input
                        value={customer.email || ''}
                        onChange={(e) => handleFieldChange('email', e.target.value)}
                        onBlur={(e) => handleUpdateCustomer('email', e.target.value)}
                      />
                      <label className="mt-2 inline-flex items-center gap-2 text-sm font-bold text-foreground">
                        <input
                          type="checkbox"
                          className="h-4 w-4 rounded border-input"
                          checked={!!customer.wrong_email_address}
                          onChange={(e) => handleWrongEmailAddress(e.target.checked)}
                        />
                        Wrong email address (stop automated emails)
                      </label>
                    </div>
                    <div>
                      <Label>Phone <span className="text-destructive">*</span></Label>
                      <div className="flex gap-2 items-center">
                        <Input
                          className="flex-1"
                          value={customer.phone || ''}
                          onChange={(e) => handleFieldChange('phone', e.target.value)}
                          onBlur={(e) => handleUpdateCustomer('phone', e.target.value)}
                        />
                        {customer.phone && (
                          <Button
                            type="button"
                            variant="outline"
                            size="icon"
                            className="shrink-0"
                            title="Call"
                            onClick={() => setCallNotesDialogOpen(true)}
                          >
                            <Phone className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </div>
                    <div className="col-span-2">
                      <Label>Address Line 1 <span className="text-destructive">*</span></Label>
                      <Input
                        value={customer.address_line1 || ''}
                        onChange={(e) => handleFieldChange('address_line1', e.target.value)}
                        onBlur={(e) => handleUpdateCustomer('address_line1', e.target.value)}
                      />
                    </div>
                    <div className="col-span-2">
                      <Label>Address Line 2 (Optional)</Label>
                      <Input
                        value={customer.address_line2 || ''}
                        onChange={(e) => handleFieldChange('address_line2', e.target.value)}
                        onBlur={(e) => handleUpdateCustomer('address_line2', e.target.value)}
                      />
                    </div>
                    <div>
                      <Label>City <span className="text-destructive">*</span></Label>
                      <Input
                        value={customer.city || ''}
                        onChange={(e) => handleFieldChange('city', e.target.value)}
                        onBlur={(e) => handleUpdateCustomer('city', e.target.value)}
                      />
                    </div>
                    <div>
                      <Label>County <span className="text-destructive">*</span></Label>
                      <Input
                        value={customer.county || ''}
                        onChange={(e) => handleFieldChange('county', e.target.value)}
                        onBlur={(e) => handleUpdateCustomer('county', e.target.value)}
                      />
                    </div>
                    <div>
                      <Label>Postcode <span className="text-destructive">*</span></Label>
                      <Input
                        value={customer.postcode || ''}
                        onChange={(e) => handleFieldChange('postcode', e.target.value)}
                        onBlur={(e) => handleUpdateCustomer('postcode', e.target.value)}
                      />
                    </div>
                    <div>
                      <Label>Country</Label>
                      <Input
                        value={customer.country || 'United Kingdom'}
                        onChange={(e) => handleFieldChange('country', e.target.value)}
                        onBlur={(e) => handleUpdateCustomer('country', e.target.value)}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>
              <div className="flex flex-col gap-4 md:w-80 md:flex-shrink-0 md:min-h-0">
                <Card className="flex-1 min-h-0 flex flex-col">
                  <CardHeader>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Image src="/email-icon.png" alt="" width={32} height={32} className="shrink-0" />
                      <CardTitle>Emails</CardTitle>
                      {unreadChannels.email_unread > 0 && (
                        <span className="inline-flex min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold items-center justify-center">
                          {unreadChannels.email_unread > 99 ? '99+' : unreadChannels.email_unread}
                        </span>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={() => setComposeEmailDialogOpen(true)}
                    >
                      Compose Email
                    </Button>
                    <Button
                      variant="link"
                      className="w-full p-0 h-auto text-muted-foreground hover:text-primary"
                      onClick={() => router.push(`/customers/${customerId}/emails`)}
                    >
                      View all emails
                    </Button>
                  </CardContent>
                </Card>
                <Card className="flex-1 min-h-0 flex flex-col">
                  <CardHeader>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Image src="/sms-icon.png" alt="" width={32} height={32} className="shrink-0" />
                      <CardTitle>SMS</CardTitle>
                      {unreadChannels.sms_unread > 0 && (
                        <span className="inline-flex min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold items-center justify-center">
                          {unreadChannels.sms_unread > 99 ? '99+' : unreadChannels.sms_unread}
                        </span>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent>
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={() => router.push(`/customers/${customerId}/sms`)}
                    >
                      View SMS
                    </Button>
                  </CardContent>
                </Card>
                <Card className="flex-1 min-h-0 flex flex-col">
                  <CardHeader>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Image src="/messenger-icon.png" alt="" width={32} height={32} className="shrink-0" />
                      <CardTitle>Messenger</CardTitle>
                      {unreadChannels.messenger_unread > 0 && (
                        <span className="inline-flex min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold items-center justify-center">
                          {unreadChannels.messenger_unread > 99 ? '99+' : unreadChannels.messenger_unread}
                        </span>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent>
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={() => router.push(`/customers/${customerId}/messenger`)}
                    >
                      View Messenger
                    </Button>
                  </CardContent>
                </Card>
                <Card className="border-dashed">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-2">
                        {customer.automated_reminder_outreach_opt_out ? (
                          <BellOff className="h-5 w-5 text-muted-foreground shrink-0" aria-hidden />
                        ) : (
                          <Bell className="h-5 w-5 text-muted-foreground shrink-0" aria-hidden />
                        )}
                        <CardTitle className="text-base">Automated reminder messages</CardTitle>
                      </div>
                      <label className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                        <input
                          type="checkbox"
                          className="h-4 w-4 rounded border-muted-foreground/40"
                          checked={!!customer.automated_reminder_outreach_opt_out}
                          disabled={outreachOptOutLoading}
                          onChange={(e) => handleAutomatedOutreachOptOut(e.target.checked)}
                        />
                        <span>Stop automated messages</span>
                      </label>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3 pt-0">
                    <p className="text-xs text-muted-foreground leading-relaxed whitespace-normal break-words">
                      Preferred channel based on customer responses:{' '}
                      <span className="font-medium text-foreground">
                        {preferredChannel.name} ({preferredChannel.received} received)
                      </span>
                      .
                    </p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>What this controls</span>
                      <div className="relative group">
                        <button
                          type="button"
                          className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-muted-foreground/40"
                          aria-label="What automated reminder messages control"
                        >
                          <Info className="h-3.5 w-3.5" />
                        </button>
                        <div className="pointer-events-none absolute bottom-7 left-1/2 z-20 hidden w-64 -translate-x-1/2 rounded-md border bg-popover p-2 text-xs text-popover-foreground shadow-md group-hover:block group-focus-within:block">
                          This only stops automatic SMS or email sent by reminder rules. Messages you send from LeadLock (compose email, SMS thread, quotes) are not affected.
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <CardTitle>Communication Preference</CardTitle>
                  <Badge variant="secondary" className="max-w-full whitespace-normal break-words text-right sm:text-left">
                    Preferred: {preferredChannel.name} ({preferredChannel.received} received)
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Sent vs received by channel. Phone uses answered (live call) and non-answered (call attempted) logs.
                </p>
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline">Phone answered: {communicationStats.phone_answered}</Badge>
                  <Badge variant="outline">Phone non-answered: {communicationStats.phone_unanswered}</Badge>
                </div>
                <CustomerCommunicationBarChart stats={communicationStats} />
              </CardContent>
            </Card>

            {/* Quote Lock Card */}
            <QuoteLockCard 
              customer={customer}
              quoteLocked={quoteLocked}
              quoteLockReason={quoteLockReason}
            />

            {/* Quotes and Opportunities - side by side */}
            <div className="flex flex-col md:flex-row gap-6">
            <Card className="flex-1 min-w-0">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Quotes</CardTitle>
                  <div className="flex flex-wrap items-center gap-2">
                  {!quoteLocked && (
                    <Button variant="outline" size="sm" onClick={() => setConfigureLinkOpen(true)}>
                      Layout link
                    </Button>
                  )}
                  {!quoteLocked && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="sm">
                          <Plus className="h-4 w-4 mr-2" />
                          Create Quote
                          <ChevronDown className="h-4 w-4 ml-1" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {leads.length > 0 && leads.map((lead) => (
                          <DropdownMenuItem
                            key={lead.id}
                            onClick={() => router.push(`/quotes/create?customer_id=${customerId}&lead_id=${lead.id}`)}
                          >
                            From lead: {lead.name} ({new Date(lead.created_at).toLocaleDateString('en-GB')})
                          </DropdownMenuItem>
                        ))}
                        <DropdownMenuItem
                          disabled={createLeadLoading}
                          onClick={async () => {
                            setCreateLeadLoading(true);
                            try {
                              const newLead = await createLeadFromCustomer(customerId);
                              toast.success('Pre-qualified lead created');
                              fetchLeads();
                              router.push(`/quotes/create?customer_id=${customerId}&lead_id=${newLead.id}`);
                            } catch (err: any) {
                              toast.error(err.response?.data?.detail || 'Failed to create lead');
                            } finally {
                              setCreateLeadLoading(false);
                            }
                          }}
                        >
                          {createLeadLoading ? 'Creating...' : 'Create new lead (pre-qualified) and quote'}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {quotes.length === 0 ? (
                  <div className="space-y-3">
                    <p className="text-sm text-muted-foreground">No quotes yet</p>
                    {!quoteLocked && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="outline" className="w-full">
                            <Plus className="h-4 w-4 mr-2" />
                            Create First Quote
                            <ChevronDown className="h-4 w-4 ml-1" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start" className="w-56">
                          {leads.length > 0 && leads.map((lead) => (
                            <DropdownMenuItem
                              key={lead.id}
                              onClick={() => router.push(`/quotes/create?customer_id=${customerId}&lead_id=${lead.id}`)}
                            >
                              From lead: {lead.name} ({new Date(lead.created_at).toLocaleDateString('en-GB')})
                            </DropdownMenuItem>
                          ))}
                          <DropdownMenuItem
                            disabled={createLeadLoading}
                            onClick={async () => {
                              setCreateLeadLoading(true);
                              try {
                                const newLead = await createLeadFromCustomer(customerId);
                                toast.success('Pre-qualified lead created');
                                fetchLeads();
                                router.push(`/quotes/create?customer_id=${customerId}&lead_id=${newLead.id}`);
                              } catch (err: any) {
                                toast.error(err.response?.data?.detail || 'Failed to create lead');
                              } finally {
                                setCreateLeadLoading(false);
                              }
                            }}
                          >
                            {createLeadLoading ? 'Creating...' : 'Create new lead (pre-qualified) and quote'}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
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
                            {quote.lead_name && (
                              <span className="text-muted-foreground text-xs ml-2">
                                (from lead: {quote.lead_name})
                              </span>
                            )}
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
                              {quote.order_id ? 'Send order' : 'Send quote'}
                            </Button>
                          </div>
                        </div>
                        <div 
                          className="text-sm text-muted-foreground cursor-pointer hover:text-primary"
                          onClick={() => router.push(`/quotes/${quote.id}`)}
                        >
                          £{Number(quote.total_amount).toFixed(2)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="flex-1 min-w-0">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Orders</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {ordersLoadError && (
                  <div className="mb-3 rounded-md border border-destructive/30 bg-destructive/5 p-3">
                    <p className="text-sm font-medium text-destructive">{ordersLoadError}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Retry to confirm whether this customer has no orders or the request failed.
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-3"
                      onClick={fetchOrders}
                      disabled={ordersLoading}
                    >
                      {ordersLoading ? 'Retrying...' : 'Retry orders'}
                    </Button>
                  </div>
                )}
                {!ordersLoadError && orders.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No orders yet. Orders are created when quotes are accepted.</p>
                ) : orders.length > 0 ? (
                  <div className="space-y-2">
                    {orders.map((order) => (
                      <div
                        key={order.id}
                        className="p-3 border rounded-md"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div
                            className="flex-1 cursor-pointer hover:text-primary"
                            onClick={() => router.push(`/orders/${order.id}`)}
                          >
                            <span className="inline-flex items-center gap-1.5">
                              <span className="font-medium">{order.order_number}</span>
                              {order.is_ninox_origin && <NinoxBadge className="h-auto px-1.5 py-0.5 text-xs" />}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            {(order.deposit_paid ?? false) && (
                              <Badge variant="secondary" className="text-xs">Deposit paid</Badge>
                            )}
                            {(order.installation_booked ?? false) && (
                              <Badge variant="secondary" className="text-xs">Inst. booked</Badge>
                            )}
                            {(order.installation_completed ?? false) && (
                              <Badge variant="default" className="text-xs">Inst. done</Badge>
                            )}
                          </div>
                        </div>
                        <div
                          className="text-sm text-muted-foreground cursor-pointer hover:text-primary"
                          onClick={() => router.push(`/orders/${order.id}`)}
                        >
                          £{Number(order.total_amount).toFixed(2)}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </CardContent>
            </Card>
            </div>

            {/* Customer-level files */}
            <FilesCard context="customer" id={customerId} />

            {/* Websites Visited Card */}
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Globe className="h-5 w-5 shrink-0" />
                  <CardTitle>Websites Visited</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {websiteVisits.length === 0 ? (
                  <div className="space-y-1">
                    <p className="text-sm text-muted-foreground">No website visits recorded</p>
                    <p className="text-xs text-muted-foreground">
                      Visits are tracked when the customer uses a link that includes their tracking token (e.g. in emails you send).
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {websiteVisits.map((visit, index) => (
                      <div key={index} className="flex items-center justify-between p-2 rounded-md border">
                        <span className="font-medium">
                          {visit.site === 'CHESHIRE_STABLES'
                            ? 'Cheshire Stables'
                            : visit.site === 'CSGB'
                              ? 'CSGB'
                              : visit.site === 'BLC'
                                ? 'BLC'
                                : visit.site.replace('_', ' ')}
                        </span>
                        <span className="text-sm text-muted-foreground">
                          {formatDateTime(visit.visited_at)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
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
                          <span className="inline-flex items-center gap-1.5">
                            <span className="font-medium">{lead.name}</span>
                            {(lead.lead_source === 'NINOX' || lead.customer?.source_system === 'Ninox') && (
                              <NinoxBadge className="h-auto px-1.5 py-0.5 text-xs" />
                            )}
                          </span>
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
                <div className="flex items-center justify-between gap-2">
                  <CardTitle>Activity Timeline</CardTitle>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setManualActivityDialogOpen(true)}
                  >
                    <Plus className="h-4 w-4 mr-1.5" />
                    Add note
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 max-h-[480px] overflow-y-auto">
                  {activities.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No activities yet</p>
                  ) : (
                    activities.map((activity) => {
                      const Icon = activityIcons[activity.activity_type];
                      const isNotesExpanded = !!expandedActivityNotes[activity.id];
                      return (
                        <div key={activity.id} className="flex gap-3 items-start py-1">
                          <div className={`${activityColors[activity.activity_type]}`}>
                            <Icon className="h-4 w-4" />
                          </div>
                          <div className="flex-1 min-w-0 space-y-1">
                            <div className="flex items-center gap-2 min-w-0">
                              <span
                                className="font-medium text-sm truncate block min-w-0 flex-1"
                                title={formatActivityTypeLabel(activity.activity_type)}
                              >
                                {formatActivityTypeLabel(activity.activity_type)}
                              </span>
                              <span className="text-xs text-muted-foreground shrink-0">
                                {formatDateTime(activity.created_at)}
                              </span>
                            </div>
                            {activity.notes && (
                              <div className="min-w-0">
                                <p
                                  className={`text-xs text-muted-foreground ${isNotesExpanded ? 'whitespace-pre-wrap break-words' : 'truncate'}`}
                                  title={isNotesExpanded ? undefined : activity.notes}
                                >
                                  {activity.notes}
                                </p>
                                <button
                                  type="button"
                                  className="text-xs text-primary hover:underline mt-0.5"
                                  onClick={() =>
                                    setExpandedActivityNotes((prev) => ({
                                      ...prev,
                                      [activity.id]: !prev[activity.id],
                                    }))
                                  }
                                >
                                  {isNotesExpanded ? 'Show less' : 'Show more'}
                                </button>
                              </div>
                            )}
                            {activity.created_by_name && (
                              <p className="text-xs text-muted-foreground truncate" title={`by ${activity.created_by_name}`}>
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

            {/* Customer History Timeline - Collapsible */}
            <Card>
              <CardHeader
                className="cursor-pointer select-none hover:bg-muted/50 rounded-t-lg transition-colors"
                onClick={() => setHistoryExpanded(!historyExpanded)}
              >
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <History className="h-5 w-5" />
                    Customer History
                    {history.length > 0 && (
                      <span className="text-sm font-normal text-muted-foreground">
                        ({history.length} events)
                      </span>
                    )}
                  </CardTitle>
                  {historyExpanded ? (
                    <ChevronUp className="h-5 w-5 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="h-5 w-5 text-muted-foreground" />
                  )}
                </div>
              </CardHeader>
              {historyExpanded && (
                <CardContent>
                  <div className="space-y-2">
                    {history.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No history yet</p>
                    ) : (
                      history.map((event, index) => {
                        const Icon = historyIcons[event.event_type] || History;
                        const color = historyColors[event.event_type] || 'text-muted-foreground';
                        const quoteNumber =
                          typeof event.metadata?.quote_number === 'string' ? event.metadata.quote_number : null;
                        const orderNumber =
                          typeof event.metadata?.order_number === 'string' ? event.metadata.order_number : null;
                        const leadName =
                          typeof event.metadata?.lead_name === 'string' ? event.metadata.lead_name : null;
                        const oldStatus =
                          typeof event.metadata?.old_status === 'string' ? event.metadata.old_status : null;
                        const newStatus =
                          typeof event.metadata?.new_status === 'string' ? event.metadata.new_status : null;
                        return (
                          <div key={index} className="flex gap-3 relative items-start py-1">
                            <div className={`${color} flex-shrink-0`}>
                              <Icon className="h-4 w-4" />
                            </div>
                            <div className="flex-1 min-w-0 space-y-1">
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="font-medium text-sm truncate block min-w-0 flex-1" title={event.title}>
                                  {event.title}
                                </span>
                                <span className="text-xs text-muted-foreground shrink-0">
                                  {formatDateTime(event.timestamp)}
                                </span>
                              </div>
                              {event.description && (
                                <p className="text-xs text-muted-foreground truncate" title={event.description}>
                                  {event.description}
                                </p>
                              )}
                              {event.created_by_name && (
                                <p className="text-xs text-muted-foreground truncate" title={`by ${event.created_by_name}`}>
                                  by {event.created_by_name}
                                </p>
                              )}
                              {event.metadata && Object.keys(event.metadata).length > 0 && (
                                <div className="flex gap-1 overflow-hidden whitespace-nowrap">
                                  {orderNumber && (
                                    <Badge
                                      variant="outline"
                                      className="text-xs shrink-0 max-w-[180px] truncate"
                                      title={`Order: ${orderNumber}`}
                                    >
                                      Order: {orderNumber}
                                    </Badge>
                                  )}
                                  {quoteNumber && (
                                    <Badge
                                      variant="outline"
                                      className="text-xs shrink-0 max-w-[180px] truncate"
                                      title={`Quote: ${quoteNumber}`}
                                    >
                                      Quote: {quoteNumber}
                                    </Badge>
                                  )}
                                  {leadName && (
                                    <Badge
                                      variant="outline"
                                      className="text-xs shrink-0 max-w-[180px] truncate"
                                      title={`Lead: ${leadName}`}
                                    >
                                      Lead: {leadName}
                                    </Badge>
                                  )}
                                  {oldStatus && newStatus && (
                                    <Badge
                                      variant="outline"
                                      className="text-xs shrink-0 max-w-[220px] truncate"
                                      title={`${oldStatus} → ${newStatus}`}
                                    >
                                      {oldStatus} → {newStatus}
                                    </Badge>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </CardContent>
              )}
            </Card>
          </div>
      </main>

      {customer && (
        <SendConfiguratorLinkDialog
          open={configureLinkOpen}
          onOpenChange={setConfigureLinkOpen}
          customerId={customerId}
          leadId={leads[0]?.id}
          customerName={customer.name}
        />
      )}

      {customer && selectedQuoteId && (
        <SendQuoteEmailDialog
          open={sendEmailDialogOpen}
          onOpenChange={setSendEmailDialogOpen}
          quoteId={selectedQuoteId}
          customer={customer}
          variant={
            quotes.find((q) => q.id === selectedQuoteId)?.order_id ? 'order' : 'quote'
          }
          onSuccess={() => {
            fetchQuotes();
            fetchActivities();
            fetchHistory();
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
            fetchHistory();
            // Add small delay to ensure database transaction is committed
            setTimeout(() => {
              checkQuotePrerequisites();
            }, 200);
          }}
        />
      )}

      {customer && customer.phone && (
        <CallNotesDialog
          open={callNotesDialogOpen}
          onOpenChange={setCallNotesDialogOpen}
          customerId={customerId}
          customerName={customer.name}
          phone={customer.phone}
          onSuccess={() => {
            fetchHistory();
            fetchActivities();
          }}
        />
      )}

      {customer && (
        <AddManualActivityDialog
          open={manualActivityDialogOpen}
          onOpenChange={setManualActivityDialogOpen}
          customerId={customerId}
          onSuccess={() => {
            fetchActivities();
            fetchHistory();
          }}
        />
      )}

    </div>
  );
}
