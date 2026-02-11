'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Mail, ArrowLeft, Reply, Send } from 'lucide-react';
import { getCustomerEmails, sendEmail } from '@/lib/api';
import { formatDateTime } from '@/lib/utils';
import { Email, EmailDirection, Customer } from '@/lib/types';
import { toast } from 'sonner';
import api from '@/lib/api';
import ComposeEmailDialog from '@/components/ComposeEmailDialog';

export default function CustomerEmailsPage() {
  const router = useRouter();
  const params = useParams();
  const customerId = parseInt(params.id as string);

  const [emails, setEmails] = useState<Email[]>([]);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedThread, setSelectedThread] = useState<string | null>(null);
  const [composeEmailDialogOpen, setComposeEmailDialogOpen] = useState(false);

  useEffect(() => {
    if (customerId) {
      fetchCustomer();
      fetchEmails();
    }
  }, [customerId]);

  const fetchCustomer = async () => {
    try {
      const response = await api.get(`/api/customers/${customerId}`);
      setCustomer(response.data);
    } catch (error: any) {
      toast.error('Failed to load customer');
    }
  };

  const fetchEmails = async () => {
    try {
      const data = await getCustomerEmails(customerId);
      setEmails(data);
    } catch (error: any) {
      toast.error('Failed to load emails');
      if (error.response?.status === 401) {
        router.push('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  // Group emails by thread
  const groupedEmails = emails.reduce((acc, email) => {
    const threadId = email.thread_id || email.message_id || `single-${email.id}`;
    if (!acc[threadId]) {
      acc[threadId] = [];
    }
    acc[threadId].push(email);
    return acc;
  }, {} as Record<string, Email[]>);

  // Sort emails within each thread - newest at top
  Object.keys(groupedEmails).forEach(threadId => {
    groupedEmails[threadId].sort((a, b) => 
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
  });

  const threads = Object.entries(groupedEmails).map(([threadId, threadEmails]) => ({
    threadId,
    emails: threadEmails,
    subject: threadEmails[0]?.subject || 'No Subject',
    latestDate: threadEmails[0]?.created_at
  })).sort((a, b) => 
    new Date(b.latestDate).getTime() - new Date(a.latestDate).getTime()
  );

  const selectedThreadEmails = selectedThread ? groupedEmails[selectedThread] : null;

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
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <Button
              variant="ghost"
              onClick={() => router.push(`/customers/${customerId}`)}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Customer
            </Button>
            {customer && (
              <Button
                variant="default"
                onClick={() => setComposeEmailDialogOpen(true)}
              >
                <Send className="h-4 w-4 mr-2" />
                Compose Email
              </Button>
            )}
          </div>
          <h1 className="text-3xl font-bold">
            {customer?.name ? `Emails - ${customer.name}` : 'Emails'}
          </h1>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Email Threads List */}
          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle>Email Threads</CardTitle>
              </CardHeader>
              <CardContent>
                {threads.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No emails yet</p>
                ) : (
                  <div className="space-y-2">
                    {threads.map((thread) => (
                      <div
                        key={thread.threadId}
                        className={`p-3 border rounded-md cursor-pointer hover:bg-muted ${
                          selectedThread === thread.threadId ? 'bg-muted border-primary' : ''
                        }`}
                        onClick={() => setSelectedThread(thread.threadId)}
                      >
                        <div className="font-medium text-sm truncate">
                          {thread.subject}
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          {thread.emails.length} {thread.emails.length === 1 ? 'email' : 'emails'}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {new Date(thread.latestDate).toLocaleDateString()}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Email Thread View */}
          <div className="lg:col-span-2">
            {selectedThreadEmails ? (
              <Card>
                <CardHeader>
                  <CardTitle>{selectedThreadEmails[0]?.subject || 'Email Thread'}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {selectedThreadEmails.map((email) => (
                      <div
                        key={email.id}
                        className={`p-4 border rounded-md ${
                          email.direction === EmailDirection.SENT
                            ? 'bg-blue-50 border-blue-200'
                            : 'bg-gray-50 border-gray-200'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <Badge
                              variant={email.direction === EmailDirection.SENT ? 'default' : 'secondary'}
                            >
                              {email.direction === EmailDirection.SENT ? (
                                <>
                                  <Send className="h-3 w-3 mr-1" />
                                  Sent
                                </>
                              ) : (
                                <>
                                  <Mail className="h-3 w-3 mr-1" />
                                  Received
                                </>
                              )}
                            </Badge>
                            <span className="text-sm font-medium">
                              {email.direction === EmailDirection.SENT ? email.to_email : email.from_email}
                            </span>
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {formatDateTime(email.created_at)}
                          </span>
                        </div>
                        <div className="text-sm mt-2">
                          {email.body_html ? (
                            <div
                              dangerouslySetInnerHTML={{ __html: email.body_html }}
                              className="prose prose-sm max-w-none"
                            />
                          ) : (
                            <p className="whitespace-pre-wrap">{email.body_text}</p>
                          )}
                        </div>
                        {email.direction === EmailDirection.RECEIVED && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="mt-3"
                            onClick={() => {
                              // TODO: Implement reply functionality
                              toast.info('Reply functionality coming soon');
                            }}
                          >
                            <Reply className="h-3 w-3 mr-1" />
                            Reply
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="py-12 text-center text-muted-foreground">
                  Select an email thread to view
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </main>

      {customer && (
        <ComposeEmailDialog
          open={composeEmailDialogOpen}
          onOpenChange={setComposeEmailDialogOpen}
          customer={customer}
          onSuccess={() => {
            fetchEmails();
          }}
        />
      )}
    </div>
  );
}
