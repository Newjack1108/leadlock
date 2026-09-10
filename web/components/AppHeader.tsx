'use client';

import { usePathname } from 'next/navigation';
import Header from '@/components/Header';
import { appHeaderPathShouldHide } from '@/lib/appChrome';

/** Persistent chrome so the header does not remount (and refetch badges) on every route. */
export default function AppHeader() {
  const pathname = usePathname();
  if (appHeaderPathShouldHide(pathname)) return null;
  return <Header />;
}
