'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import ReminderList from '@/components/ReminderList';
import {
  getQualifiedForQuoting,
  getUnreadSms,
  getUnreadMessenger,
  getSalesDocuments,
  downloadSalesDocument,
} from '@/lib/api';
import type {
  QualifiedForQuotingSummary,
  UnreadSmsSummary,
  UnreadMessengerSummary,
  SalesDocument,
} from '@/lib/types';
import { toast } from 'sonner';
import {
  FileText,
  ArrowRight,
  MessageSquare,
  Bell,
  FolderOpen,
  Download,
  LayoutDashboard,
} from 'lucide-react';

function formatTimeAgo(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

export default function CloserDashboardPage() {
  const router = useRouter();
  const [qualified, setQualified] = useState<QualifiedForQuotingSummary | null>(null);
  const [unreadSms, setUnreadSms] = useState<UnreadSmsSummary | null>(null);
  const [unreadMessenger, setUnreadMessenger] = useState<UnreadMessengerSummary | null>(null);
  const [documents, setDocuments] = useState<SalesDocument[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboard();
  }, []);

  const fetchDashboard = async () => {
    try {
      const [qualifiedRes, smsRes, messengerRes, docsRes] = await Promise.all([
        getQualifiedForQuoting().catch(() => ({ count: 0, leads: [] })),
        getUnreadSms().catch(() => ({ count: 0, messages: [] })),
        getUnreadMessenger().catch(() => ({ count: 0, messages: [] })),
        getSalesDocuments().catch(() => []),
      ]);
      setQualified(qualifiedRes);
      setUnreadSms(smsRes ?? { count: 0, messages: [] });
      setUnreadMessenger(messengerRes ?? { count: 0, messages: [] });
      setDocuments(Array.isArray(docsRes) ? docsRes : []);
    } catch (error: unknown) {
      const err = error as { response?: { status?: number } };
      if (err.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load dashboard');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadDoc = async (doc: SalesDocument) => {
    try {
      const blob = await downloadSalesDocument(doc.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Failed to download document');
    }
  };

  const totalUnread = (unreadSms?.count ?? 0) + (unreadMessenger?.count ?? 0);

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
        <div className="flex items-center gap-2 mb-8">
          <LayoutDashboard className="h-8 w-8 text-primary" />
          <h1 className="text-3xl font-semibold">Closer Dashboard</h1>
        </div>

        {/* Qualified for Quoting */}
        <Card className="mb-8 border-primary/30 bg-primary/5">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Qualified for Quoting
            </CardTitle>
            <span className="text-sm text-muted-foreground">
              {qualified?.count ?? 0} ready for quote
            </span>
          </CardHeader>
          <CardContent>
            {qualified && qualified.leads.length > 0 ? (
              <div className="space-y-2">
                {qualified.leads.slice(0, 10).map((lead) => (
                  <Link
                    key={lead.id}
                    href={`/leads/${lead.id}`}
                    className="flex items-center justify-between p-3 rounded-lg bg-card border border-border cursor-pointer hover:border-primary/50 transition-colors block"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-medium truncate">{lead.name}</p>
                      <p className="text-sm text-muted-foreground truncate">
                        {lead.customer_name || 'No customer linked'} · {formatTimeAgo(lead.updated_at)}
                      </p>
                    </div>
                    <span className="text-sm text-primary font-medium shrink-0">
                      Start quote
                      <ArrowRight className="h-4 w-4 ml-1 inline" />
                    </span>
                  </Link>
                ))}
                {qualified.leads.length > 10 && (
                  <p className="text-sm text-muted-foreground pt-2">
                    +{qualified.leads.length - 10} more — use Opportunities to view all
                  </p>
                )}
              </div>
            ) : (
              <p className="text-muted-foreground py-4">No qualified leads at the moment.</p>
            )}
          </CardContent>
        </Card>

        {/* New Messages */}
        {totalUnread > 0 && (
          <Card className="mb-8">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5" />
                New Messages
              </CardTitle>
              <span className="text-sm text-muted-foreground">{totalUnread} unread</span>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {unreadSms?.messages?.slice(0, 5).map((msg) => (
                  <div
                    key={`sms-${msg.id}`}
                    className="flex items-center justify-between p-3 rounded-lg bg-card border border-border"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-medium truncate">{msg.customer_name}</p>
                      <p className="text-sm text-muted-foreground truncate">{msg.body}</p>
                    </div>
                    <Button variant="outline" size="sm" asChild>
                      <Link href={`/customers/${msg.customer_id}/sms`}>
                        View
                        <ArrowRight className="h-4 w-4 ml-1" />
                      </Link>
                    </Button>
                  </div>
                ))}
                {unreadMessenger?.messages?.slice(0, 5).map((msg) => (
                  <div
                    key={`msg-${msg.id}`}
                    className="flex items-center justify-between p-3 rounded-lg bg-card border border-border"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-medium truncate">{msg.customer_name}</p>
                      <p className="text-sm text-muted-foreground truncate">{msg.body}</p>
                    </div>
                    <Button variant="outline" size="sm" asChild>
                      <Link href={`/customers/${msg.customer_id}/messenger`}>
                        View
                        <ArrowRight className="h-4 w-4 ml-1" />
                      </Link>
                    </Button>
                  </div>
                ))}
              </div>
              <Button variant="ghost" size="sm" className="mt-4" asChild>
                <Link href="/customers?has_unread=1">View all conversations</Link>
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Reminders */}
        <div className="mb-8">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5" />
                Reminders
              </CardTitle>
              <Button variant="outline" size="sm" asChild>
                <Link href="/reminders">
                  View all
                  <ArrowRight className="h-4 w-4 ml-2" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent>
              <ReminderList limit={5} showActions={true} />
            </CardContent>
          </Card>
        </div>

        {/* Quick Documents */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <FolderOpen className="h-5 w-5" />
              Quick Documents
            </CardTitle>
            <Button variant="outline" size="sm" asChild>
              <Link href="/sales-documents">
                View all
                <ArrowRight className="h-4 w-4 ml-2" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {documents.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                {documents.slice(0, 9).map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between p-3 rounded-lg border border-border hover:border-primary/30 transition-colors"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-medium truncate">{doc.name}</p>
                      {doc.category && (
                        <p className="text-xs text-muted-foreground">{doc.category}</p>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDownloadDoc(doc)}
                      className="shrink-0"
                    >
                      <Download className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground py-4">No documents available.</p>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
