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
  
  // Map missing field names to display names
  const fieldDisplayNames: Record<string, string> = {
    'address_line1': 'Address Line 1',
    'city': 'City',
    'county': 'County',
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
                  <XCircle className="h-4 w-4 text-destructive" />
                )}
                <span className={hasAddressLine1 ? 'text-foreground' : missingItems.includes('address_line1') ? 'text-destructive font-medium' : 'text-muted-foreground'}>
                  Address Line 1
                  {missingItems.includes('address_line1') && <span className="ml-1 text-xs">(Required)</span>}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasCity ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" />
                )}
                <span className={hasCity ? 'text-foreground' : missingItems.includes('city') ? 'text-destructive font-medium' : 'text-muted-foreground'}>
                  City
                  {missingItems.includes('city') && <span className="ml-1 text-xs">(Required)</span>}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasCounty ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" />
                )}
                <span className={hasCounty ? 'text-foreground' : missingItems.includes('county') ? 'text-destructive font-medium' : 'text-muted-foreground'}>
                  County
                  {missingItems.includes('county') && <span className="ml-1 text-xs">(Required)</span>}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasPostcode ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" />
                )}
                <span className={hasPostcode ? 'text-foreground' : missingItems.includes('postcode') ? 'text-destructive font-medium' : 'text-muted-foreground'}>
                  Postcode
                  {missingItems.includes('postcode') && <span className="ml-1 text-xs">(Required)</span>}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasEmail ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" />
                )}
                <span className={hasEmail ? 'text-foreground' : missingItems.includes('email') ? 'text-destructive font-medium' : 'text-muted-foreground'}>
                  Email
                  {missingItems.includes('email') && <span className="ml-1 text-xs">(Required)</span>}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {hasPhone ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" />
                )}
                <span className={hasPhone ? 'text-foreground' : missingItems.includes('phone') ? 'text-destructive font-medium' : 'text-muted-foreground'}>
                  Phone
                  {missingItems.includes('phone') && <span className="ml-1 text-xs">(Required)</span>}
                </span>
              </div>
              {reason?.error === 'QUOTE_PREREQS_MISSING' && missingItems.length > 0 && (
                <div className="mt-3 pt-3 border-t border-border space-y-2">
                  <div className="text-xs font-semibold text-destructive uppercase tracking-wide mb-2">
                    Missing Required Fields
                  </div>
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
              All requirements met. You can now send a quote.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
