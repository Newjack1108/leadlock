import type { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';
import { markConfiguratorInviteViewed } from '@/lib/api';
import type { ConfiguratorInvite } from '@/lib/types';

/** Mark a customer submission as seen and navigate to review it. */
export async function openConfiguratorSubmission(
  invite: ConfiguratorInvite,
  router: AppRouterInstance
): Promise<void> {
  await markConfiguratorInviteViewed(invite.id);
  if (invite.quote_id != null) {
    router.push(`/quotes/${invite.quote_id}/configure`);
    return;
  }
  if (invite.lead_id != null) {
    router.push(`/leads/${invite.lead_id}`);
    return;
  }
}
