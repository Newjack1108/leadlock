'use client';

import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import api, { getQuotes, previewQuotePdf } from '@/lib/api';
import { Quote, QuoteStatus, QuoteTemperature } from '@/lib/types';
import { toast } from 'sonner';
import Link from 'next/link';
import { FileText, Eye, Pencil, List, LayoutGrid, ShoppingCart } from 'lucide-react';

const statusColors: Record<QuoteStatus, string> = {
  DRAFT: 'bg-gray-100 text-gray-700',
  SENT: 'bg-blue-100 text-blue-700',
  VIEWED: 'bg-yellow-100 text-yellow-700',
  ACCEPTED: 'bg-green-100 text-green-700',
  REJECTED: 'bg-red-100 text-red-700',
  EXPIRED: 'bg-orange-100 text-orange-700',
};

const temperatureColors: Record<QuoteTemperature, string> = {
  HOT: 'bg-red-100 text-red-700',
  WARM: 'bg-amber-100 text-amber-700',
  COLD: 'bg-slate-100 text-slate-600',
};

export default function QuotesPage() {
  const router = useRouter();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<'list' | 'tile'>('list');
  const [statusFilter, setStatusFilter] = useState<QuoteStatus | 'ALL'>(QuoteStatus.SENT);
  const [temperatureFilter, setTemperatureFilter] = useState<QuoteTemperature | 'ALL'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchQuotes();
  }, []);

  // Auto-refresh when user returns to this tab/window
  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchQuotes();
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
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

  const filteredQuotes = useMemo(() => {
    let result = quotes;
    if (statusFilter !== 'ALL') {
      result = result.filter((q) => q.status === statusFilter);
    }
    if (temperatureFilter !== 'ALL') {
      result = result.filter((q) => q.temperature === temperatureFilter);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter(
        (quote) =>
          quote.quote_number?.toLowerCase().includes(q) ||
          quote.customer_name?.toLowerCase().includes(q)
      );
    }
    return result;
  }, [quotes, statusFilter, temperatureFilter, searchQuery]);

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-3xl font-semibold">Quotes</h1>
          {quotes.length > 0 && (
            <div className="flex gap-1 border rounded-md p-1 bg-muted/30">
              <Button
                variant={viewMode === 'list' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('list')}
                title="List view"
              >
                <List className="h-4 w-4" />
              </Button>
              <Button
                variant={viewMode === 'tile' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('tile')}
                title="Tile view"
              >
                <LayoutGrid className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>

        {quotes.length > 0 && (
          <div className="flex flex-col md:flex-row gap-4 mb-6">
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as QuoteStatus | 'ALL')}>
              <SelectTrigger className="w-full md:w-[200px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All statuses</SelectItem>
                {Object.values(QuoteStatus).map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={temperatureFilter} onValueChange={(v) => setTemperatureFilter(v as QuoteTemperature | 'ALL')}>
              <SelectTrigger className="w-full md:w-[180px]">
                <SelectValue placeholder="Temperature" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All temperatures</SelectItem>
                {Object.values(QuoteTemperature).map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              placeholder="Search by quote # or customer..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full md:w-[260px]"
            />
          </div>
        )}

        {quotes.length === 0 ? (
          <Card>
            <CardContent className="p-6">
              <div className="text-center text-muted-foreground py-12">
                <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No quotes found</p>
              </div>
            </CardContent>
          </Card>
        ) : filteredQuotes.length === 0 ? (
          <Card>
            <CardContent className="p-6">
              <div className="text-center text-muted-foreground py-12">
                <p>No quotes match your filters</p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-4"
                  onClick={() => {
                    setStatusFilter('ALL');
                    setTemperatureFilter('ALL');
                    setSearchQuery('');
                  }}
                >
                  Clear filters
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : viewMode === 'list' ? (
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-3 font-medium">Quote #</th>
                    <th className="text-left p-3 font-medium">Customer</th>
                    <th className="text-left p-3 font-medium">Status</th>
                    <th className="text-left p-3 font-medium">Total</th>
                    <th className="text-left p-3 font-medium">Valid until</th>
                    <th className="text-left p-3 font-medium">Created</th>
                    <th className="text-right p-3 font-medium w-[180px]">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredQuotes.map((quote) => (
                    <tr
                      key={quote.id}
                      className="border-b last:border-0 hover:bg-muted/30 cursor-pointer transition-colors"
                      onClick={() => router.push(`/quotes/${quote.id}`)}
                    >
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">{quote.quote_number}</span>
                          {quote.version > 1 && (
                            <span className="text-sm text-muted-foreground">v{quote.version}</span>
                          )}
                        </div>
                      </td>
                      <td className="p-3 text-muted-foreground">{quote.customer_name || '—'}</td>
                      <td className="p-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge className={statusColors[quote.status]}>
                            {quote.status}
                          </Badge>
                          {quote.order_id && (
                            <Badge variant="outline" className="gap-1 border-emerald-500 text-emerald-700 bg-emerald-50">
                              <ShoppingCart className="h-3 w-3" />
                              Ordered
                            </Badge>
                          )}
                          {quote.temperature && (
                            <Badge className={temperatureColors[quote.temperature]}>
                              {quote.temperature}
                            </Badge>
                          )}
                        </div>
                      </td>
                      <td className="p-3 font-semibold">£{Number(quote.total_amount).toFixed(2)}</td>
                      <td className="p-3 text-muted-foreground">
                        {quote.valid_until
                          ? new Date(quote.valid_until).toLocaleDateString()
                          : '—'}
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {new Date(quote.created_at).toLocaleDateString()}
                      </td>
                      <td className="p-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex gap-2 justify-end">
                          {quote.status === 'DRAFT' && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => router.push(`/quotes/${quote.id}/edit`)}
                            >
                              <Pencil className="h-4 w-4 mr-1" />
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
                                toast.error(error.response?.data?.detail || error.message || 'Failed to download PDF');
                              }
                            }}
                          >
                            <Eye className="h-4 w-4 mr-1" />
                            Download PDF
                          </Button>
                          <Button
                            variant="default"
                            size="sm"
                            onClick={() => router.push(`/quotes/${quote.id}`)}
                          >
                            View
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        ) : (
          <div className="space-y-4">
            {filteredQuotes.map((quote) => (
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
                        {quote.order_id && (
                          <Badge variant="outline" className="gap-1 border-emerald-500 text-emerald-700 bg-emerald-50">
                            <ShoppingCart className="h-3 w-3" />
                            Ordered
                          </Badge>
                        )}
                        {quote.temperature && (
                          <Badge className={temperatureColors[quote.temperature]}>
                            {quote.temperature}
                          </Badge>
                        )}
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
                            toast.error(error.response?.data?.detail || error.message || 'Failed to download PDF');
                          }
                        }}
                      >
                        <Eye className="h-4 w-4 mr-2" />
                        Download PDF
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
