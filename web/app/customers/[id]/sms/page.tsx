'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
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
import { MessageSquare, ArrowLeft, Send, CalendarClock, RefreshCw } from 'lucide-react';
import { formatDateTime } from '@/lib/utils';
import {
  getCustomerSms,
  sendSms,
  createScheduledSms,
  getScheduledSms,
  cancelScheduledSms,
  getSmsTemplates,
  previewSmsTemplate,
  markCustomerSmsRead,
} from '@/lib/api';
import {
  SmsMessage,
  SmsDirection,
  Customer,
  SmsScheduled,
  ScheduledSmsStatus,
  SmsTemplate,
} from '@/lib/types';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Link from 'next/link';
import { toast } from 'sonner';
import api from '@/lib/api';

export default function CustomerSmsPage() {
  const router = useRouter();
  const params = useParams();
  const customerId = parseInt(params.id as string);

  const [messages, setMessages] = useState<SmsMessage[]>([]);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [scheduled, setScheduled] = useState<SmsScheduled[]>([]);
  const [composeToPhone, setComposeToPhone] = useState('');
  const [composeBody, setComposeBody] = useState('');
  const [sending, setSending] = useState(false);
  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false);
  const [scheduleToPhone, setScheduleToPhone] = useState('');
  const [scheduleBody, setScheduleBody] = useState('');
  const [scheduleDatetime, setScheduleDatetime] = useState('');
  const [scheduling, setScheduling] = useState(false);
  const [smsTemplates, setSmsTemplates] = useState<SmsTemplate[]>([]);
  const [selectedComposeTemplateId, setSelectedComposeTemplateId] = useState<string>('none');
  const [selectedScheduleTemplateId, setSelectedScheduleTemplateId] = useState<string>('none');
  const [loadingComposeTemplate, setLoadingComposeTemplate] = useState(false);
  const [loadingScheduleTemplate, setLoadingScheduleTemplate] = useState(false);

  useEffect(() => {
    if (!customerId) return;
    fetchCustomer();
    fetchMessages();
    fetchScheduled();
    fetchSmsTemplates();
    const pollMs = 25 * 1000;
    const interval = setInterval(() => {
      fetchMessages();
      fetchScheduled();
    }, pollMs);
    return () => clearInterval(interval);
  }, [customerId]);

  const fetchSmsTemplates = async () => {
    try {
      const data = await getSmsTemplates();
      setSmsTemplates(data);
    } catch {
      setSmsTemplates([]);
    }
  };

  const fetchCustomer = async () => {
    try {
      const response = await api.get(`/api/customers/${customerId}`);
      setCustomer(response.data);
      setComposeToPhone(response.data.phone || '');
      setScheduleToPhone(response.data.phone || '');
    } catch (error: unknown) {
      toast.error('Failed to load customer');
    }
  };

  const fetchMessages = async () => {
    try {
      const data = await getCustomerSms(customerId);
      setMessages(data);
      // Mark received messages as read so dashboard unread count updates
      markCustomerSmsRead(customerId).catch(() => {});
    } catch (error: unknown) {
      toast.error('Failed to load messages');
      if (error && typeof error === 'object' && 'response' in error) {
        const err = error as { response?: { status?: number } };
        if (err.response?.status === 401) router.push('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  const fetchScheduled = async () => {
    try {
      const data = await getScheduledSms({
        customer_id: customerId,
        status: ScheduledSmsStatus.PENDING,
      });
      setScheduled(data);
    } catch {
      setScheduled([]);
    }
  };

  const handleSend = async () => {
    const to = composeToPhone?.trim();
    if (!to || !composeBody?.trim()) {
      toast.error('Enter phone number and message');
      return;
    }
    setSending(true);
    try {
      await sendSms({
        customer_id: customerId,
        to_phone: to,
        body: composeBody.trim(),
      });
      setComposeBody('');
      toast.success('Message sent');
      fetchMessages();
    } catch (error: unknown) {
      const msg = error && typeof error === 'object' && 'response' in error
        ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : 'Failed to send';
      toast.error(String(msg));
    } finally {
      setSending(false);
    }
  };

  const handleSchedule = async () => {
    const to = scheduleToPhone?.trim();
    if (!to || !scheduleBody?.trim() || !scheduleDatetime) {
      toast.error('Enter phone number, message, and date/time');
      return;
    }
    setScheduling(true);
    try {
      await createScheduledSms({
        customer_id: customerId,
        to_phone: to,
        body: scheduleBody.trim(),
        scheduled_at: new Date(scheduleDatetime).toISOString(),
      });
      toast.success('Message scheduled');
      setScheduleDialogOpen(false);
      setScheduleBody('');
      setScheduleDatetime('');
      setSelectedScheduleTemplateId('none');
      fetchScheduled();
    } catch (error: unknown) {
      const msg = error && typeof error === 'object' && 'response' in error
        ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : 'Failed to schedule';
      toast.error(String(msg));
    } finally {
      setScheduling(false);
    }
  };

  const handleCancelScheduled = async (id: number) => {
    try {
      await cancelScheduledSms(id);
      toast.success('Scheduled message cancelled');
      fetchScheduled();
    } catch {
      toast.error('Failed to cancel');
    }
  };

  const handleComposeTemplateChange = async (value: string) => {
    setSelectedComposeTemplateId(value);
    if (value === 'none') {
      setComposeBody('');
      return;
    }
    setLoadingComposeTemplate(true);
    try {
      const preview = await previewSmsTemplate(parseInt(value, 10), {
        customer_id: customerId,
      });
      setComposeBody(preview.body);
    } catch {
      toast.error('Failed to load template');
    } finally {
      setLoadingComposeTemplate(false);
    }
  };

  const handleScheduleTemplateChange = async (value: string) => {
    setSelectedScheduleTemplateId(value);
    if (value === 'none') {
      setScheduleBody('');
      return;
    }
    setLoadingScheduleTemplate(true);
    try {
      const preview = await previewSmsTemplate(parseInt(value, 10), {
        customer_id: customerId,
      });
      setScheduleBody(preview.body);
    } catch {
      toast.error('Failed to load template');
    } finally {
      setLoadingScheduleTemplate(false);
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

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <Button
              variant="ghost"
              onClick={() => router.push(`/customers/${customerId}`)}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Customer
            </Button>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => setScheduleDialogOpen(true)}
              >
                <CalendarClock className="h-4 w-4 mr-2" />
                Schedule message
              </Button>
            </div>
          </div>
          <h1 className="text-3xl font-bold">
            {customer?.name ? `SMS - ${customer.name}` : 'SMS'}
          </h1>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Send message</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <Label htmlFor="to_phone">To (phone)</Label>
                  <Input
                    id="to_phone"
                    value={composeToPhone}
                    onChange={(e) => setComposeToPhone(e.target.value)}
                    placeholder="+44 7700 900000"
                  />
                </div>
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <Label>Template</Label>
                    <Link
                      href="/settings/sms-templates"
                      className="text-xs text-primary hover:underline"
                    >
                      Manage templates
                    </Link>
                  </div>
                  <Select
                    value={selectedComposeTemplateId}
                    onValueChange={handleComposeTemplateChange}
                    disabled={loadingComposeTemplate}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="No template" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">No template</SelectItem>
                      {smsTemplates.map((t) => (
                        <SelectItem key={t.id} value={String(t.id)}>
                          {t.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {loadingComposeTemplate && (
                    <p className="text-xs text-muted-foreground mt-1">Loading template...</p>
                  )}
                </div>
                <div>
                  <Label htmlFor="body">Message</Label>
                  <Textarea
                    id="body"
                    value={composeBody}
                    onChange={(e) => setComposeBody(e.target.value)}
                    placeholder="Your message..."
                    rows={3}
                  />
                </div>
                <Button onClick={handleSend} disabled={sending}>
                  <Send className="h-4 w-4 mr-2" />
                  {sending ? 'Sending...' : 'Send'}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Conversation</CardTitle>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => { fetchMessages(); fetchScheduled(); }}
                    title="Refresh messages"
                  >
                    <RefreshCw className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {messages.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No messages yet</p>
                ) : (
                  <div className="space-y-3">
                    {messages.map((msg) => (
                      <div
                        key={msg.id}
                        className={`p-4 border rounded-md ${
                          msg.direction === SmsDirection.SENT
                            ? 'bg-blue-50 border-blue-200 ml-4'
                            : 'bg-gray-50 border-gray-200 mr-4'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <Badge
                            variant={
                              msg.direction === SmsDirection.SENT ? 'default' : 'secondary'
                            }
                          >
                            <MessageSquare className="h-3 w-3 mr-1" />
                            {msg.direction === SmsDirection.SENT ? 'Sent' : 'Received'}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {formatDateTime(msg.created_at)}
                          </span>
                        </div>
                        <div className="text-xs text-muted-foreground mb-1">
                          {msg.direction === SmsDirection.SENT
                            ? `To: ${msg.to_phone}`
                            : `From: ${msg.from_phone}`}
                        </div>
                        <p className="text-sm whitespace-pre-wrap">{msg.body}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div>
            <Card>
              <CardHeader>
                <CardTitle>Scheduled</CardTitle>
              </CardHeader>
              <CardContent>
                {scheduled.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No scheduled messages</p>
                ) : (
                  <div className="space-y-2">
                    {scheduled.map((s) => (
                      <div
                        key={s.id}
                        className="p-3 border rounded-md flex justify-between items-start gap-2"
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium">{s.to_phone}</p>
                          <p className="text-xs text-muted-foreground truncate">
                            {s.body}
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {formatDateTime(s.scheduled_at)}
                          </p>
                        </div>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="shrink-0"
                          onClick={() => handleCancelScheduled(s.id)}
                        >
                          Cancel
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </main>

      <Dialog open={scheduleDialogOpen} onOpenChange={setScheduleDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Schedule SMS</DialogTitle>
            <DialogDescription>
              Choose when to send this message. It will be sent automatically at the scheduled time.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-4">
            <div>
              <Label htmlFor="schedule_to">To (phone)</Label>
              <Input
                id="schedule_to"
                value={scheduleToPhone}
                onChange={(e) => setScheduleToPhone(e.target.value)}
                placeholder="+44 7700 900000"
              />
            </div>
            <div>
              <Label>Template</Label>
              <Select
                value={selectedScheduleTemplateId}
                onValueChange={handleScheduleTemplateChange}
                disabled={loadingScheduleTemplate}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="No template" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No template</SelectItem>
                  {smsTemplates.map((t) => (
                    <SelectItem key={t.id} value={String(t.id)}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {loadingScheduleTemplate && (
                <p className="text-xs text-muted-foreground mt-1">Loading template...</p>
              )}
            </div>
            <div>
              <Label htmlFor="schedule_body">Message</Label>
              <Textarea
                id="schedule_body"
                value={scheduleBody}
                onChange={(e) => setScheduleBody(e.target.value)}
                placeholder="Your message..."
                rows={3}
              />
            </div>
            <div>
              <Label htmlFor="schedule_at">Date & time</Label>
              <Input
                id="schedule_at"
                type="datetime-local"
                value={scheduleDatetime}
                onChange={(e) => setScheduleDatetime(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setScheduleDialogOpen(false)}>
              Close
            </Button>
            <Button onClick={handleSchedule} disabled={scheduling}>
              {scheduling ? 'Scheduling...' : 'Schedule'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
