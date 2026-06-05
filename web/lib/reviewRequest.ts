import { CompanySettings } from '@/lib/types';
import { formatDateTime } from '@/lib/utils';

export type ReviewLink = {
  label: string;
  url: string;
};

export function getConfiguredReviewLinks(settings: CompanySettings | null): ReviewLink[] {
  if (!settings) return [];
  const links: ReviewLink[] = [];
  if (settings.review_google_url?.trim()) {
    links.push({ label: 'Google', url: settings.review_google_url.trim() });
  }
  if (settings.review_facebook_url?.trim()) {
    links.push({ label: 'Facebook', url: settings.review_facebook_url.trim() });
  }
  if (settings.review_trustpilot_url?.trim()) {
    links.push({ label: 'Trustpilot', url: settings.review_trustpilot_url.trim() });
  }
  return links;
}

export function getReviewRequestStatusMessage({
  installationCompleted,
  installationCompletedAt,
  reviewRequestCustomerSentAt,
  reviewRequestCustomerChannel,
  delayDays = 3,
}: {
  installationCompleted: boolean;
  installationCompletedAt?: string | null;
  reviewRequestCustomerSentAt?: string | null;
  reviewRequestCustomerChannel?: string | null;
  delayDays?: number;
}): string | null {
  if (!installationCompleted) return null;
  if (!installationCompletedAt) {
    return 'Toggle installation completed again to schedule a review reminder.';
  }
  if (reviewRequestCustomerSentAt) {
    const sent = formatDateTime(reviewRequestCustomerSentAt);
    const channel = reviewRequestCustomerChannel ? ` via ${reviewRequestCustomerChannel}` : '';
    return `Customer review request sent${channel} on ${sent}.`;
  }
  const completedAt = new Date(installationCompletedAt);
  const dueAt = new Date(completedAt);
  dueAt.setDate(dueAt.getDate() + delayDays);
  const now = new Date();
  if (now < dueAt) {
    const daysLeft = Math.ceil((dueAt.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
    return `Review request due in ${daysLeft} day${daysLeft === 1 ? '' : 's'} (staff reminder + optional customer message).`;
  }
  return 'Review request is due — check Reminders or send now below.';
}
