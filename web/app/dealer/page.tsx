'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getDealerWelcome } from '@/lib/api';
import type { DealerWelcome } from '@/lib/types';

export default function DealerWelcomePage() {
  const [welcome, setWelcome] = useState<DealerWelcome | null>(null);

  useEffect(() => {
    getDealerWelcome().then(setWelcome).catch(() => setWelcome(null));
  }, []);

  return (
    <main className="container mx-auto px-4 py-6 sm:px-6">
      <Card>
        <CardHeader>
          <CardTitle>Welcome to the Trade Dealer Portal</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Build simple quotes from your approved products and download PDF documents.
          </p>
          <p className="text-sm text-muted-foreground">
            Add your logo and company details in Dealer profile — they appear on quote PDFs.
          </p>
          {welcome && (
            <div className="grid gap-2 text-sm">
              <p><strong>Dealer:</strong> {welcome.dealer_name}</p>
              <p><strong>User:</strong> {welcome.user_name}</p>
              <p><strong>Commission:</strong> {welcome.commission_pct}%</p>
            </div>
          )}
          <div className="flex flex-wrap gap-3">
            <Link href="/dealer/quotes">
              <Button>View quotes</Button>
            </Link>
            <Link href="/dealer/quotes/new">
              <Button variant="outline">Create quote</Button>
            </Link>
            <Link href="/dealer/profile">
              <Button variant="outline">Dealer profile</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
