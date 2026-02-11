'use client';

import { usePathname } from 'next/navigation';

const areaBackgroundClasses: Record<string, string> = {
  leads: 'bg-[var(--area-leads)]',
  customers: 'bg-[var(--area-customers)]',
  quotes: 'bg-[var(--area-quotes)]',
  orders: 'bg-[var(--area-orders)]',
  default: 'bg-background',
};

function getAreaFromPathname(pathname: string | null): string {
  if (!pathname) return 'default';
  if (pathname.startsWith('/leads')) return 'leads';
  if (pathname.startsWith('/customers')) return 'customers';
  if (pathname.startsWith('/quotes')) return 'quotes';
  if (pathname.startsWith('/orders')) return 'orders';
  return 'default';
}

export default function AreaBackgroundWrapper({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const area = getAreaFromPathname(pathname);
  const bgClass = areaBackgroundClasses[area] ?? areaBackgroundClasses.default;

  return (
    <div className={`min-h-screen ${bgClass}`}>
      {children}
    </div>
  );
}
