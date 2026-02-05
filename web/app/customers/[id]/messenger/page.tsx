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
import { MessageCircle, ArrowLeft, Send, RefreshCw } from 'lucide-react';
import {
  getCustomerMessenger,
  sendMessengerMessage,
  markCustomerMessengerRead,
} from '@/lib/api';
import { MessengerMessage, MessengerDirection, Customer } from '@/lib/types';
import { formatDateTime } from '@/lib/utils';
import { toast } from 'sonner';
import api from '@/lib/api';

export default function CustomerMessengerPage() {
  const router = useRouter();
  const params = useParams();
  const customerId = parseInt(params.id as string);

  const [messages, setMessages] = useState<MessengerMessage[]>([]);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [composeBody, setComposeBody] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!customerId) return;
    fetchCustomer();
    fetchMessages();
    const pollMs = 25 * 1000;
    const interval = setInterval(() => {
      fetchMessages();
    }, pollMs);
    return () => clearInterval(interval);
  }, [customerId]);

  const fetchCustomer = async () => {
    try {
      const response = await api.get(`/api/customers/${customerId}`);
      setCustomer(response.data);
    } catch (error: unknown) {
      toast.error('Failed to load customer');
    }
  };

  const fetchMessages = async () => {
    try {
      const data = await getCustomerMessenger(customerId);
      setMessages(data);
      markCustomerMessengerRead(customerId).catch(() => {});
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

  const handleSend = async () => {
    if (!composeBody?.trim()) {
      toast.error('Enter a message');
      return;
    }
    if (!customer?.messenger_psid) {
      toast.error('Customer is not linked to Messenger; they must message your Page first.');
      return;
    }
    setSending(true);
    try {
      await sendMessengerMessage({
        customer_id: customerId,
        body: composeBody.trim(),
      });
      setComposeBody('');
      toast.success('Message sent');
      fetchMessages();
    } catch (error: unknown) {
      const msg =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Failed to send';
      toast.error(String(msg));
    } finally {
      setSending(false);
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
          </div>
          <h1 className="text-3xl font-bold">
            {customer?.name ? `Messenger - ${customer.name}` : 'Messenger'}
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
                  <Label htmlFor="to_psid">To</Label>
                  <Input
                    id="to_psid"
                    value={customer?.messenger_psid ? 'Linked via Facebook' : 'Not linked — customer must message your Page first'}
                    readOnly
                    className="bg-muted"
                  />
                </div>
                <div>
                  <Label htmlFor="body">Message</Label>
                  <Textarea
                    id="body"
                    value={composeBody}
                    onChange={(e) => setComposeBody(e.target.value)}
                    placeholder="Your message..."
                    rows={3}
                    disabled={!customer?.messenger_psid}
                  />
                </div>
                <Button
                  onClick={handleSend}
                  disabled={sending || !customer?.messenger_psid}
                >
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
                    onClick={() => fetchMessages()}
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
                          msg.direction === MessengerDirection.SENT
                            ? 'bg-blue-50 border-blue-200 ml-4 dark:bg-blue-950/30 dark:border-blue-800'
                            : 'bg-gray-50 border-gray-200 mr-4 dark:bg-gray-900/50 dark:border-gray-700'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <Badge
                            variant={
                              msg.direction === MessengerDirection.SENT
                                ? 'default'
                                : 'secondary'
                            }
                          >
                            <MessageCircle className="h-3 w-3 mr-1" />
                            {msg.direction === MessengerDirection.SENT
                              ? 'Sent'
                              : 'Received'}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {formatDateTime(msg.created_at)}
                          </span>
                        </div>
                        <div className="text-xs text-muted-foreground mb-1">
                          {msg.direction === MessengerDirection.SENT
                            ? `To: ${msg.to_psid || '—'}`
                            : `From: ${msg.from_psid}`}
                        </div>
                        <p className="text-sm whitespace-pre-wrap">{msg.body}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
