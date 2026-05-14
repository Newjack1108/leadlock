import type { ConfiguratorPreviewResponse } from '@/lib/types';

export function getPreviewIssueCount(
  preview: ConfiguratorPreviewResponse | null,
  severity: 'error' | 'warning'
) {
  if (!preview) return 0;
  return preview.issues.filter((issue) => issue.severity === severity).length;
}

export function formatCurrency(value: number) {
  return `£${Number(value || 0).toFixed(2)}`;
}
