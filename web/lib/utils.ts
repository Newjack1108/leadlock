import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import { ActivityType } from '@/lib/types'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Build a tel: URL from a phone number (strips spaces). */
export function getTelUrl(phone: string): string {
  const normalized = (phone || '').replace(/\s/g, '')
  return normalized ? `tel:${normalized}` : ''
}

/** Format date and time as locale string without seconds (HH:MM). */
export function formatDateTime(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' })
}

/** Human-readable label for activity timeline (e.g. LIVE_CALL -> "Call accepted"). */
export function formatActivityTypeLabel(type: ActivityType): string {
  if (type === ActivityType.LIVE_CALL) return 'Call accepted'
  return type
    .replace(/_/g, ' ')
    .toLowerCase()
    .split(' ')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/** Format decimal hours as "X hrs Y min" (e.g. 2.5 -> "2 hrs 30 min"). */
export function formatHoursMinutes(decHours: number): string {
  if (!Number.isFinite(decHours) || decHours < 0) return '0 hrs 0 min'
  const h = Math.floor(decHours)
  const m = Math.round((decHours - h) * 60)
  if (m === 0) return h === 1 ? '1 hr' : `${h} hrs`
  if (h === 0) return `${m} min`
  return h === 1 ? `1 hr ${m} min` : `${h} hrs ${m} min`
}

export type ProductFilterQueryParams = {
  category?: string
  is_extra?: boolean
  is_active?: boolean
  subcategories?: string[]
  trade_only?: boolean
}

/** Build query string for product list / price-list PDF (repeated subcategory keys for FastAPI). */
export function buildProductFilterQueryString(params: ProductFilterQueryParams): string {
  const searchParams = new URLSearchParams()
  searchParams.set('is_active', String(params.is_active ?? true))
  if (params.category) {
    searchParams.set('category', params.category)
  }
  if (params.is_extra !== undefined) {
    searchParams.set('is_extra', String(params.is_extra))
  }
  for (const sub of params.subcategories ?? []) {
    searchParams.append('subcategory', sub)
  }
  if (params.trade_only) {
    searchParams.set('trade_only', 'true')
  }
  return searchParams.toString()
}
