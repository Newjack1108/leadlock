'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, XCircle, Lock, Unlock } from 'lucide-react';
import { Customer } from '@/lib/types';

interface QuoteLockCardProps {
  customer: Customer;
  quoteLocked?: boolean;
  quoteLockReason?: {
    error: string;
    missing?: string[];
    message?: string;
  };
}

export default function QuoteLockCard({ customer, quoteLocked = false, quoteLockReason }: QuoteLockCardProps) {
  const isLocked = quoteLocked;
  const reason = quoteLockReason;

  const missingItems = reason?.missing || [];
  const hasAddressLine1 = !!customer.address_line1;
  const hasCity = !!customer.city;
  const hasCounty = !!customer.county;
  const hasPostcode = !!customer.postcode;
  const hasEmail = !!customer.email;
  const hasPhone = !!customer.phone;

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
                <div className="mt-3 pt-3 border-t border-border space-y-2">
                  <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                    Engagement Proof Required
                  </div>
                  <div className="flex items-center gap-2">
                    <XCircle className="h-4 w-4 text-destructive" />
                    <span className="text-destructive text-sm">
                      {reason?.message || "No engagement proof found. Log a Live Call, send an email, or wait for customer response."}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    Required activities: SMS_RECEIVED, EMAIL_RECEIVED, EMAIL_SENT, WHATSAPP_RECEIVED, or LIVE_CALL
                  </p>
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
