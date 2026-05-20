'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { listConfiguratorInvites } from '@/lib/api';
import { openConfiguratorSubmission } from '@/lib/configurator/openSubmission';
import { isConfiguratorSubmissionUnread, type ConfiguratorInvite } from '@/lib/types';
import { cn } from '@/lib/utils';
import Link from 'next/link';

export default function ConfiguratorSubmissionsPage() {
  const router = useRouter();
  const [items, setItems] = useState<ConfiguratorInvite[]>([]);
  const [loading, setLoading] = useState(true);
  const [openingId, setOpeningId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listConfiguratorInvites({ status: 'SUBMITTED', limit: 100 });
      setItems(data.items);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleOpen = async (invite: ConfiguratorInvite) => {
    try {
      setOpeningId(invite.id);
      await openConfiguratorSubmission(invite, router);
      setItems((prev) =>
        prev.map((row) =>
          row.id === invite.id
            ? { ...row, staff_viewed_at: row.staff_viewed_at ?? new Date().toISOString() }
            : row
        )
      );
    } finally {
      setOpeningId(null);
    }
  };

  const unreadCount = items.filter(isConfiguratorSubmissionUnread).length;

  return (
    <div className="min-h-screen bg-muted/30">
      <Header />
      <main className="container mx-auto px-4 py-6">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle>Customer layout submissions</CardTitle>
              {unreadCount > 0 && (
                <Badge variant="destructive">{unreadCount} new</Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground font-normal">
              Layouts customers submitted from public configurator links. Open a row to review and
              apply to the draft quote.
            </p>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground py-8 text-center">Loading…</p>
            ) : items.length === 0 ? (
              <p className="text-sm text-muted-foreground py-8 text-center">
                No submitted layouts yet.
              </p>
            ) : (
              <ul className="space-y-2">
                {items.map((invite) => {
                  const unread = isConfiguratorSubmissionUnread(invite);
                  return (
                    <li
                      key={invite.id}
                      className={cn(
                        'flex flex-wrap items-center justify-between gap-3 rounded-md border px-3 py-3 text-sm',
                        unread && 'border-primary/40 bg-primary/5'
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          {unread && (
                            <span
                              className="h-2 w-2 shrink-0 rounded-full bg-red-500"
                              aria-label="New submission"
                            />
                          )}
                          <p className={cn('font-medium truncate', unread && 'text-foreground')}>
                            {invite.customer_name || 'Customer layout'}
                          </p>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {invite.submitted_at
                            ? `Submitted ${new Date(invite.submitted_at).toLocaleString('en-GB')}`
                            : 'Submitted'}
                          {invite.campaign_slug ? ` · ${invite.campaign_slug}` : ''}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {invite.lead_id != null && (
                          <Button variant="outline" size="sm" asChild>
                            <Link href={`/leads/${invite.lead_id}`}>Lead</Link>
                          </Button>
                        )}
                        <Button
                          size="sm"
                          disabled={openingId === invite.id || invite.quote_id == null}
                          onClick={() => void handleOpen(invite)}
                        >
                          {openingId === invite.id ? 'Opening…' : unread ? 'Review new layout' : 'Review layout'}
                        </Button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
