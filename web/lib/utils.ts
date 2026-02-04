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
