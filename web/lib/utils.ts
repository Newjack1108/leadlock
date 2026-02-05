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
