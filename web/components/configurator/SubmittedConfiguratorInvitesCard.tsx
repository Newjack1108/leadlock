'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { listConfiguratorInvites } from '@/lib/api';
import type { ConfiguratorInvite } from '@/lib/types';

export default function SubmittedConfiguratorInvitesCard() {
  const [items, setItems] = useState<ConfiguratorInvite[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await listConfiguratorInvites({ status: 'SUBMITTED', limit: 8 });
        if (!cancelled) setItems(data.items);
      } catch {
        if (!cancelled) setItems([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading || items.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Submitted customer layouts</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.map((invite) => (
          <div
            key={invite.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm"
          >
            <div className="min-w-0">
              <p className="font-medium truncate">{invite.customer_name || 'Customer layout'}</p>
              <p className="text-xs text-muted-foreground">
                {invite.submitted_at
                  ? new Date(invite.submitted_at).toLocaleString('en-GB')
                  : 'Submitted'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {invite.lead_id != null && (
                <Button variant="outline" size="sm" asChild>
                  <Link href={`/leads/${invite.lead_id}`}>Lead</Link>
                </Button>
              )}
              {invite.quote_id != null && (
                <>
                  <Button variant="outline" size="sm" asChild>
                    <Link href={`/quotes/${invite.quote_id}/configure`}>Configurator</Link>
                  </Button>
                  <Button variant="default" size="sm" asChild>
                    <Link href={`/quotes/${invite.quote_id}/edit`}>Quote</Link>
                  </Button>
                </>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
