import type { CompanySettings } from '@/lib/types';
import type { InstallationLeadTime } from '@/lib/types';

export type InstallationLeadTimeRow = { label: string; value: InstallationLeadTime };

/** Rows to show on dashboards: per-type values, or legacy single value for all three when per-type unset. */
export function getInstallationLeadTimeRows(settings: CompanySettings): InstallationLeadTimeRow[] {
  const legacy = settings.installation_lead_time;
  const stables = settings.installation_lead_time_stables;
  const sheds = settings.installation_lead_time_sheds;
  const cabins = settings.installation_lead_time_cabins;
  const useLegacyFallback = !stables && !sheds && !cabins && legacy;
  const rows: InstallationLeadTimeRow[] = [];
  const push = (label: string, specific?: InstallationLeadTime) => {
    const v = specific ?? (useLegacyFallback ? legacy : undefined);
    if (v) rows.push({ label, value: v });
  };
  push('Stables', stables);
  push('Sheds', sheds);
  push('Cabins', cabins);
  return rows;
}

export function hasAnyInstallationLeadTime(settings: CompanySettings | null | undefined): boolean {
  if (!settings) return false;
  return getInstallationLeadTimeRows(settings).length > 0;
}
