'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import api, { getQuotes, previewQuotePdf } from '@/lib/api';
import { Quote, QuoteStatus } from '@/lib/types';
import { toast } from 'sonner';
import Link from 'next/link';
import { FileText, Eye, Pencil } from 'lucide-react';

const statusColors: Record<QuoteStatus, string> = {
  DRAFT: 'bg-gray-100 text-gray-700',
  SENT: 'bg-blue-100 text-blue-700',
  VIEWED: 'bg-yellow-100 text-yellow-700',
  ACCEPTED: 'bg-green-100 text-green-700',
  REJECTED: 'bg-red-100 text-red-700',
  EXPIRED: 'bg-orange-100 text-orange-700',
};

export default function QuotesPage() {
  const router = useRouter();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchQuotes();
  }, []);

  const fetchQuotes = async () => {
    try {
      setLoading(true);
      const data = await getQuotes();
      setQuotes(data);
    } catch (error: any) {
      toast.error('Failed to load quotes');
      if (error.response?.status === 401) {
        router.push('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-semibold">Quotes</h1>
        </div>

        {quotes.length === 0 ? (
          <Card>
            <CardContent className="p-6">
              <div className="text-center text-muted-foreground py-12">
                <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No quotes found</p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {quotes.map((quote) => (
              <Card key={quote.id} className="hover:shadow-md transition-shadow">
                <CardContent className="p-6">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <Link
                          href={`/quotes/${quote.id}`}
                          className="font-semibold text-lg hover:text-primary"
                        >
                          {quote.quote_number}
                        </Link>
                        {quote.customer_name && (
                          <span className="text-muted-foreground">— {quote.customer_name}</span>
                        )}
                        <Badge className={statusColors[quote.status]}>
                          {quote.status}
                        </Badge>
                        {quote.version > 1 && (
                          <span className="text-sm text-muted-foreground">
                            v{quote.version}
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-muted-foreground space-y-1">
                        <p>Total: £{Number(quote.total_amount).toFixed(2)}</p>
                        {quote.valid_until && (
                          <p>
                            Valid until: {new Date(quote.valid_until).toLocaleDateString()}
                          </p>
                        )}
                        <p>Created: {new Date(quote.created_at).toLocaleDateString()}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      {quote.status === 'DRAFT' && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => router.push(`/quotes/${quote.id}/edit`)}
                        >
                          <Pencil className="h-4 w-4 mr-2" />
                          Edit
                        </Button>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={async () => {
                          try {
                            await previewQuotePdf(quote.id);
                          } catch (error: any) {
                            toast.error(error.response?.data?.detail || error.message || 'Failed to preview PDF');
                          }
                        }}
                      >
                        <Eye className="h-4 w-4 mr-2" />
                        Preview
                      </Button>
                      <Button
                        variant="default"
                        size="sm"
                        onClick={() => router.push(`/quotes/${quote.id}`)}
                      >
                        View Details
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
