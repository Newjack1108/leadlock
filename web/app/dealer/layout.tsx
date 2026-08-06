'use client';

import Header from '@/components/Header';

export default function DealerLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="min-h-screen bg-[linear-gradient(180deg,#eef7f1_0%,#fafafa_220px,#fafafa_100%)]">
      <div className="h-1.5 w-full bg-gradient-to-r from-primary via-secondary to-primary" aria-hidden />
      <Header />
      {children}
    </div>
  );
}
