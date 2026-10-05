'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { getMyDashboardActivity } from '@/lib/api';
import { DashboardMyActivityItem } from '@/lib/types';
import { formatActivityTypeLabel, formatDateTime } from '@/lib/utils';
import { Activity, ArrowRight } from 'lucide-react';

interface RecentActivityCardProps {
  compact?: boolean;
}

function notePreview(notes?: string | null): string | null {
  if (!notes) return null;
  const firstLine = notes.split('\n').find((line) => line.trim())?.trim();
  if (!firstLine) return null;
  return firstLine.length > 80 ? `${firstLine.slice(0, 77)}…` : firstLine;
}

export default function RecentActivityCard({ compact = false }: RecentActivityCardProps) {
  const [items, setItems] = useState<DashboardMyActivityItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getMyDashboardActivity()
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card className={compact ? 'shrink-0' : undefined}>
      <CardHeader
        className={
          compact
            ? 'py-3 px-4 flex flex-row items-center justify-between'
            : 'flex flex-row items-center justify-between'
        }
      >
        <CardTitle
          className={
            compact
              ? 'text-sm font-medium flex items-center gap-2'
              : 'text-lg flex items-center gap-2'
          }
        >
          <Activity className={compact ? 'h-4 w-4' : 'h-5 w-5'} />
          Recent activity
        </CardTitle>
        <span className="text-xs text-muted-foreground">Last 10</span>
      </CardHeader>
      <CardContent className={compact ? 'px-4 pb-4 pt-0' : undefined}>
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex gap-2 p-2 rounded-md border border-border">
                <div className="h-4 flex-1 animate-pulse rounded bg-muted" />
                <div className="h-3 w-20 animate-pulse rounded bg-muted" />
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground py-2">No recent activity.</p>
        ) : (
          <div className={compact ? 'max-h-[280px] overflow-y-auto space-y-1.5' : 'space-y-2'}>
            {items.map((item) => {
              const preview = notePreview(item.notes);
              const content = (
                <>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {formatActivityTypeLabel(item.activity_type)}
                      </p>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {formatDateTime(item.created_at)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground truncate">
                      {item.customer_name || 'Unknown customer'}
                      {preview ? ` · ${preview}` : ''}
                    </p>
                  </div>
                  {item.customer_id ? (
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0 ml-2" />
                  ) : null}
                </>
              );

              if (item.customer_id) {
                return (
                  <Link
                    key={item.id}
                    href={`/customers/${item.customer_id}`}
                    className="flex items-center justify-between p-2 rounded-md bg-card border border-border hover:border-primary/50 transition-colors"
                  >
                    {content}
                  </Link>
                );
              }

              return (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-2 rounded-md bg-card border border-border"
                >
                  {content}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
