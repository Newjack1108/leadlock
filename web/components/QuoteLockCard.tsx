'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, XCircle, Lock, Unlock } from 'lucide-react';
import { Lead, Timeframe } from '@/lib/types';

interface QuoteLockCardProps {
  lead: Lead;
}

export default function QuoteLockCard({ lead }: QuoteLockCardProps) {
  const isLocked = lead.quote_locked;
  const reason = lead.quote_lock_reason;

  if (lead.status !== 'QUALIFIED') {
    return null;
  }

  const missingItems = reason?.missing || [];
  const hasPostcode = !!lead.postcode;
  const hasTimeframe = lead.timeframe !== Timeframe.UNKNOWN;
  const hasScopeOrInterest = !!(lead.scope_notes || lead.product_interest);
  const hasAddressLine1 = !!lead.address_line1;
  const hasCity = !!lead.city;
  const hasCounty = !!lead.county;
  const hasEmail = !!lead.email;
  const hasPhone = !!lead.phone;

  return (
    <Card className={`${isLocked ? 'border-destructive/50' : 'border-success/50'}`}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {isLocked ? (
            <>
              <Lock className="h-5 w-5 text-destructive" />
              <span>Quote Locked</span>
            </>
          ) : (
            <>
              <Unlock className="h-5 w-5 text-success" />
              <span className="text-success">Quote Unlocked</span>
            </>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLocked ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Complete the requirements below to unlock quote sending:
            </p>
            <div className="space-y-2">
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Lead Information
              </div>
              <div className="flex items-center gap-2">
                {hasPostcode ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-muted-foreground" />
                )}
                <span className={hasPostcode ? 'text-foreground' : 'text-muted-foreground'}>
                  Postcode
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasTimeframe ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-muted-foreground" />
                )}
                <span className={hasTimeframe ? 'text-foreground' : 'text-muted-foreground'}>
                  Timeframe
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasScopeOrInterest ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-muted-foreground" />
                )}
                <span className={hasScopeOrInterest ? 'text-foreground' : 'text-muted-foreground'}>
                  Scope Notes or Product Interest
                </span>
              </div>
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mt-4 mb-2">
                Customer Profile
              </div>
              <div className="flex items-center gap-2">
                {hasAddressLine1 ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-muted-foreground" />
                )}
                <span className={hasAddressLine1 ? 'text-foreground' : 'text-muted-foreground'}>
                  Address Line 1
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasCity ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-muted-foreground" />
                )}
                <span className={hasCity ? 'text-foreground' : 'text-muted-foreground'}>
                  City
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasCounty ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-muted-foreground" />
                )}
                <span className={hasCounty ? 'text-foreground' : 'text-muted-foreground'}>
                  County
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasEmail ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-muted-foreground" />
                )}
                <span className={hasEmail ? 'text-foreground' : 'text-muted-foreground'}>
                  Email
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasPhone ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-muted-foreground" />
                )}
                <span className={hasPhone ? 'text-foreground' : 'text-muted-foreground'}>
                  Phone
                </span>
              </div>
              {reason?.error === 'NO_ENGAGEMENT_PROOF' && (
                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-border">
                  <XCircle className="h-4 w-4 text-destructive" />
                  <span className="text-destructive text-sm">
                    Engagement proof required (SMS/Email/WhatsApp received or Live Call)
                  </span>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-success">
            <CheckCircle2 className="h-5 w-5" />
            <p className="text-sm font-medium">
              All requirements met. You can now send a quote.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
