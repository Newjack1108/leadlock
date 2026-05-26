import { Lead, LeadStatus } from '@/lib/types';

export const PRE_QUALIFY_SPAM_STATUSES: LeadStatus[] = [
  LeadStatus.NEW,
  LeadStatus.CONTACT_ATTEMPTED,
  LeadStatus.ENGAGED,
];

export function canRemoveSpamLead(
  userRole: string | null,
  lead: Pick<Lead, 'status'>
): boolean {
  return (
    (userRole === 'DIRECTOR' || userRole === 'SALES_MANAGER') &&
    PRE_QUALIFY_SPAM_STATUSES.includes(lead.status)
  );
}
