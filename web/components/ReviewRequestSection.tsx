'use client';

import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { CompanySettings } from '@/lib/types';
import {
  getConfiguredReviewLinks,
  getReviewRequestStatusMessage,
} from '@/lib/reviewRequest';
import { formatDateTime } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Copy, ExternalLink, Send, Star } from 'lucide-react';
import { toast } from 'sonner';

type ReviewRequestSectionProps = {
  companySettings: CompanySettings | null;
  installationCompleted: boolean;
  installationCompletedAt?: string | null;
  reviewRequestCustomerSentAt?: string | null;
  reviewRequestCustomerChannel?: string | null;
  reviewHubUrl?: string | null;
  isReturningCustomer?: boolean;
  onSendReviewRequest?: () => void | Promise<void>;
  sendingReviewRequest?: boolean;
  showSendButton?: boolean;
  compact?: boolean;
};

export default function ReviewRequestSection({
  companySettings,
  installationCompleted,
  installationCompletedAt,
  reviewRequestCustomerSentAt,
  reviewRequestCustomerChannel,
  reviewHubUrl,
  isReturningCustomer = false,
  onSendReviewRequest,
  sendingReviewRequest = false,
  showSendButton = true,
  compact = false,
}: ReviewRequestSectionProps) {
  if (!installationCompleted) return null;

  const status = getReviewRequestStatusMessage({
    installationCompleted,
    installationCompletedAt,
    reviewRequestCustomerSentAt,
    reviewRequestCustomerChannel,
    delayDays: companySettings?.review_request_delay_days ?? 3,
  });
  const reviewLinks = getConfiguredReviewLinks(companySettings);
  const outreachEnabled = companySettings?.review_request_customer_outreach_enabled ?? false;

  const copyLink = async (url: string, label: string) => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success(`${label} link copied`);
    } catch {
      toast.error('Could not copy link');
    }
  };

  return (
    <div
      className={
        compact
          ? 'rounded-md border bg-muted/40 p-3 space-y-3'
          : 'rounded-lg border bg-teal-50/40 dark:bg-teal-950/20 border-teal-200/80 dark:border-teal-900/60 p-4 space-y-4'
      }
    >
      <div className="flex items-start gap-2">
        <Star className={`shrink-0 text-teal-600 ${compact ? 'h-4 w-4 mt-0.5' : 'h-5 w-5'}`} />
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className={`font-medium ${compact ? 'text-sm' : ''}`}>Review request</p>
            {isReturningCustomer ? (
              <Badge variant="secondary" className={compact ? 'text-[10px] px-1.5 py-0' : ''}>
                Returning customer
              </Badge>
            ) : null}
          </div>
          {isReturningCustomer ? (
            <p className="text-xs text-muted-foreground">
              Manual send can use the 2-review free gift template when configured in Company Settings.
            </p>
          ) : null}
          {installationCompletedAt ? (
            <p className="text-xs text-muted-foreground">
              Installation completed {formatDateTime(installationCompletedAt)}
            </p>
          ) : null}
          {status ? <p className="text-sm text-muted-foreground">{status}</p> : null}
          {outreachEnabled ? (
            <p className="text-xs text-muted-foreground">
              Automated customer outreach is enabled after the delay (channel set in Company Settings).
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              Customer outreach is off — use the links below or send manually by email or SMS.
            </p>
          )}
        </div>
      </div>

      {reviewHubUrl ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="default" asChild className={compact ? 'h-7 text-xs' : ''}>
            <a href={reviewHubUrl} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-3.5 w-3.5 mr-1" />
              Open customer review page
            </a>
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className={compact ? 'h-7 text-xs' : ''}
            onClick={() => void copyLink(reviewHubUrl, 'Review hub')}
          >
            <Copy className="h-3.5 w-3.5 mr-1" />
            Copy hub link
          </Button>
        </div>
      ) : null}

      <div className="space-y-2">
        <p className={`font-medium ${compact ? 'text-xs' : 'text-sm'}`}>Direct platform links</p>
        {reviewLinks.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {reviewLinks.map((link) => (
              <div key={link.label} className="flex items-center gap-1">
                <Button size="sm" variant="outline" asChild className={compact ? 'h-7 text-xs' : ''}>
                  <a href={link.url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-3.5 w-3.5 mr-1" />
                    {link.label}
                  </a>
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className={compact ? 'h-7 w-7 p-0' : 'h-8 w-8 p-0'}
                  title={`Copy ${link.label} link`}
                  onClick={() => void copyLink(link.url, link.label)}
                >
                  <Copy className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No review URLs configured.{' '}
            <Link href="/settings/company" className="text-primary underline hover:no-underline">
              Add them in Company Settings
            </Link>
            .
          </p>
        )}
      </div>

      {showSendButton && onSendReviewRequest ? (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => void onSendReviewRequest()}
          disabled={sendingReviewRequest}
          className={compact ? 'h-7 text-xs' : ''}
        >
          <Send className="h-4 w-4 mr-1" />
          {sendingReviewRequest ? 'Sending…' : 'Send review request to customer'}
        </Button>
      ) : null}
    </div>
  );
}
