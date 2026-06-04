import { LeadSource, LeadType } from '@/lib/types';

const DISALLOWED_SOURCES_FOR_QUALIFY = new Set<LeadSource>([
  LeadSource.MANUAL_ENTRY,
  LeadSource.OTHER,
]);

export const STAFF_SELECTABLE_LEAD_SOURCES = Object.values(LeadSource).filter(
  (s) => s !== LeadSource.WEBSITE && !DISALLOWED_SOURCES_FOR_QUALIFY.has(s)
);

export const SELECTABLE_LEAD_TYPES = [
  LeadType.STABLES,
  LeadType.SHEDS,
  LeadType.CABINS,
] as const;

export function leadSourceAllowsQualify(source: LeadSource | string | null | undefined): boolean {
  if (!source) return false;
  return !DISALLOWED_SOURCES_FOR_QUALIFY.has(source as LeadSource);
}

export function leadTypeAllowsQualify(leadType: LeadType | string | null | undefined): boolean {
  if (!leadType) return false;
  return leadType !== LeadType.UNKNOWN;
}

export function leadFieldsAllowQualify(
  source: LeadSource | string | null | undefined,
  leadType: LeadType | string | null | undefined
): boolean {
  return leadSourceAllowsQualify(source) && leadTypeAllowsQualify(leadType);
}

export function qualifyFieldsMessage(
  source: LeadSource | string | null | undefined,
  leadType: LeadType | string | null | undefined
): string {
  const parts: string[] = [];
  if (!leadSourceAllowsQualify(source)) {
    parts.push('select a lead source (not Manual entry or Other)');
  }
  if (!leadTypeAllowsQualify(leadType)) {
    parts.push('select a lead type (Stables, Sheds, or Cabins)');
  }
  return parts.length ? `Before qualifying: ${parts.join('; ')}.` : '';
}

/** Options for a Select including a legacy value not in the selectable list. */
export function leadSourceSelectOptions(current: LeadSource | string | null | undefined): LeadSource[] {
  const base = [...STAFF_SELECTABLE_LEAD_SOURCES];
  if (
    current &&
    !base.includes(current as LeadSource) &&
    Object.values(LeadSource).includes(current as LeadSource)
  ) {
    return [current as LeadSource, ...base];
  }
  return base;
}

export function leadTypeSelectOptions(current: LeadType | string | null | undefined): LeadType[] {
  const base = [...SELECTABLE_LEAD_TYPES];
  if (current === LeadType.UNKNOWN) {
    return [LeadType.UNKNOWN, ...base];
  }
  return base;
}
