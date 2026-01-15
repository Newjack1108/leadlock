'use client';

import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function OrdersPage() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <h1 className="text-3xl font-semibold mb-8">Orders</h1>
        
        <Card>
          <CardHeader>
            <CardTitle>Orders</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center py-12 text-muted-foreground">
              <p className="text-lg mb-2">Coming Soon</p>
              <p className="text-sm">Orders management feature will be available here.</p>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
