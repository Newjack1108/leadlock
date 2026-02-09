import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

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
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
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
