'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
  const hasPostcode = !!customer.postcode;
  const hasEmail = !!customer.email;
  const hasPhone = !!customer.phone;
  const prereqsMissing = reason?.error === 'QUOTE_PREREQS_MISSING';

  // Map missing field names to display names
  const fieldDisplayNames: Record<string, string> = {
    'postcode': 'Postcode',
    'email': 'Email',
    'phone': 'Phone',
  };

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
              {prereqsMissing
                ? 'You need at least two of postcode, email, and phone on the customer to unlock quoting.'
                : reason?.error === 'NO_ENGAGEMENT_PROOF'
                  ? 'Contact details meet the two-of-three rule. Your company still requires engagement proof before quoting.'
                  : 'Complete the requirements below to unlock quote sending.'}
            </p>
            <div className="space-y-2">
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Customer profile (any two unlock)
              </div>
              <div className="flex items-center gap-2">
                {hasPostcode ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" />
                )}
                <span className={hasPostcode ? 'text-foreground' : prereqsMissing && missingItems.includes('postcode') ? 'text-destructive font-medium' : 'text-muted-foreground'}>
                  Postcode
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasEmail ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" />
                )}
                <span className={hasEmail ? 'text-foreground' : prereqsMissing && missingItems.includes('email') ? 'text-destructive font-medium' : 'text-muted-foreground'}>
                  Email
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasPhone ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" />
                )}
                <span className={hasPhone ? 'text-foreground' : prereqsMissing && missingItems.includes('phone') ? 'text-destructive font-medium' : 'text-muted-foreground'}>
                  Phone
                </span>
              </div>
              {prereqsMissing && missingItems.length > 0 && (
                <div className="mt-3 pt-3 border-t border-border space-y-2">
                  <div className="text-xs font-semibold text-destructive uppercase tracking-wide mb-2">
                    Still needed for quote unlock
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {reason?.message ||
                      `Fill in any ${missingItems.length === 3 ? 'two' : 'one'} of: ${missingItems.map((f) => fieldDisplayNames[f] || f).join(', ')}.`}
                  </p>
                  {missingItems.map((field: string) => (
                    <div key={field} className="flex items-center gap-2">
                      <XCircle className="h-4 w-4 text-destructive" />
                      <span className="text-destructive text-sm">
                        {fieldDisplayNames[field] || field}
                      </span>
                    </div>
                  ))}
                </div>
              )}
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
              Contact details and other quote rules are satisfied. You can send a quote.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
