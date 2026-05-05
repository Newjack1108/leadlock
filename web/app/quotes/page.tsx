'use client';

import { Suspense, useCallback, useEffect, useLayoutEffect, useState, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import api, { cancelDraftQuote, getQuotes, previewQuotePdf } from '@/lib/api';
import { LeadType, Quote, QuoteStatus, QuoteTemperature, OpportunityStage } from '@/lib/types';
import { toast } from 'sonner';
import Link from 'next/link';
import { FileText, Eye, Pencil, List, LayoutGrid, ShoppingCart, SendHorizontal, MessageCircle, MinusCircle, Trash2 } from 'lucide-react';

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

/** Hide deal temperature on list rows once the quote is ordered / won. */
function showQuoteTemperatureBadge(quote: Quote): boolean {
  if (!quote.temperature) return false;
  if (quote.order_id) return false;
  if (quote.status === QuoteStatus.ACCEPTED) return false;
  if (quote.opportunity_stage === OpportunityStage.WON) return false;
  if (quote.accepted_at) return false;
  return true;
}

function quoteCustomerViewed(quote: Quote): boolean {
  return Boolean(
    quote.viewed_at ||
      quote.last_viewed_at ||
      (quote.total_open_count ?? 0) > 0,
  );
}

/** Sent / viewed / replied — data populated on paginated quote list from API. */
function QuoteListEngagementBadges({ quote }: { quote: Quote }) {
  const leadCountKnown = quote.lead_id != null && quote.lead_quotes_sent_count != null;
  const opens = quote.total_open_count ?? 0;
  const viewed = quoteCustomerViewed(quote);
  const replyCount = quote.inbound_count_since_quote_sent ?? 0;
  const replied = quote.customer_replied_since_quote_sent === true || replyCount > 0;

  if (!leadCountKnown && !viewed && !replied) return null;

  return (
    <>
      {leadCountKnown && (
        <Badge
          variant="outline"
          className="text-xs gap-1 font-normal border-sky-200 bg-sky-50 text-sky-900 dark:bg-sky-950/40 dark:text-sky-100 dark:border-sky-800"
          title="Quotes on this lead that have been sent (have a sent date), including this one when applicable."
        >
          <SendHorizontal className="h-3 w-3 shrink-0" aria-hidden />
          {quote.lead_quotes_sent_count} on lead
        </Badge>
      )}
      {viewed && (
        <Badge
          variant="outline"
          className="text-xs gap-1 font-normal border-amber-200 bg-amber-50 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100 dark:border-amber-800"
          title={
            opens > 0
              ? `Customer opened the quote link (${opens} open${opens === 1 ? '' : 's'} tracked).`
              : 'Customer opened the quote view link.'
          }
        >
          <Eye className="h-3 w-3 shrink-0" aria-hidden />
          Viewed
          {opens > 0 ? ` · ${opens} open${opens === 1 ? '' : 's'}` : ''}
        </Badge>
      )}
      {replied && (
        <Badge
          variant="outline"
          className="text-xs gap-1 font-normal border-violet-200 bg-violet-50 text-violet-950 dark:bg-violet-950/30 dark:text-violet-100 dark:border-violet-800"
          title="Inbound email, SMS, or Messenger from the customer after this quote was sent."
        >
          <MessageCircle className="h-3 w-3 shrink-0" aria-hidden />
          Replied
          {replyCount > 1 ? ` ×${replyCount}` : ''}
        </Badge>
      )}
    </>
  );
}

const VALID_QUOTE_STATUSES = Object.values(QuoteStatus);

type QuotesListFilter = QuoteStatus | 'ALL' | 'LIVE' | 'CLOSED';

function isConcreteQuoteStatus(f: QuotesListFilter): f is QuoteStatus {
  return f !== 'ALL' && f !== 'LIVE' && f !== 'CLOSED';
}

/** URL → filter (default LIVE when no relevant params). ALL uses pipeline=1. */
function parseFilterFromSearchParams(sp: { get: (key: string) => string | null }): QuotesListFilter {
  const status = sp.get('status');
  if (status && VALID_QUOTE_STATUSES.includes(status as QuoteStatus)) {
    return status as QuoteStatus;
  }
  if (sp.get('lifecycle') === 'closed') return 'CLOSED';
  if (sp.get('lifecycle') === 'live') return 'LIVE';
  if (sp.get('pipeline') === '1') return 'ALL';
  return 'LIVE';
}

/** Filter → query string (null means bare /quotes). */
function filterToSearchString(filter: QuotesListFilter): string | null {
  if (isConcreteQuoteStatus(filter)) {
    return new URLSearchParams({ status: filter }).toString();
  }
  if (filter === 'CLOSED') {
    return new URLSearchParams({ lifecycle: 'closed' }).toString();
  }
  if (filter === 'ALL') {
    return new URLSearchParams({ pipeline: '1' }).toString();
  }
  return null;
}

const QUOTES_PAGE_SIZE = 50;

type QuotesSortBy = 'last_contacted' | 'created';

function sortKeyLastContactedMs(q: Quote): number {
  if (!q.customer_last_interacted_at) return Number.NEGATIVE_INFINITY;
  const t = new Date(q.customer_last_interacted_at).getTime();
  return Number.isNaN(t) ? Number.NEGATIVE_INFINITY : t;
}

function sortKeyCreatedMs(q: Quote): number {
  const t = new Date(q.created_at).getTime();
  return Number.isNaN(t) ? Number.NEGATIVE_INFINITY : t;
}

function getDisplayLeadType(leadType?: LeadType | null): LeadType | null {
  if (!leadType || leadType === LeadType.UNKNOWN) return null;
  return leadType;
}

function quoteIsClosable(quote: Quote): boolean {
  return quote.status === QuoteStatus.SENT || quote.status === QuoteStatus.VIEWED;
}

function QuotesPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<'list' | 'tile'>('list');
  const [statusFilter, setStatusFilter] = useState<QuotesListFilter>(() => parseFilterFromSearchParams(searchParams));
  const [temperatureFilter, setTemperatureFilter] = useState<QuoteTemperature | 'ALL'>('ALL');
  const [searchDraft, setSearchDraft] = useState('');
  const [searchApplied, setSearchApplied] = useState('');
  const [sortBy, setSortBy] = useState<QuotesSortBy>('last_contacted');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [closeDialogOpen, setCloseDialogOpen] = useState(false);
  const [quotePendingClose, setQuotePendingClose] = useState<Quote | null>(null);
  const [markingClose, setMarkingClose] = useState(false);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [quotePendingCancel, setQuotePendingCancel] = useState<Quote | null>(null);
  const [cancellingDraft, setCancellingDraft] = useState(false);

  // Sync filter from URL (back/forward, dashboard links, shared URLs)
  useEffect(() => {
    const parsed = parseFilterFromSearchParams(searchParams);
    setStatusFilter((prev) => (prev === parsed ? prev : parsed));
  }, [searchParams]);

  const onStatusFilterChange = useCallback(
    (v: string) => {
      const next = v as QuotesListFilter;
      setStatusFilter(next);
      const qs = filterToSearchString(next);
      router.replace(qs ? `/quotes?${qs}` : '/quotes', { scroll: false });
    },
    [router],
  );

  useLayoutEffect(() => {
    setPage(1);
  }, [statusFilter, temperatureFilter, searchApplied, includeArchived]);

  const fetchQuotes = useCallback(async () => {
    try {
      setLoading(true);
      const searchValue = searchApplied.trim() || undefined;
      const data = await getQuotes({
        status: isConcreteQuoteStatus(statusFilter) ? statusFilter : undefined,
        lifecycle:
          statusFilter === 'LIVE' ? 'live' : statusFilter === 'CLOSED' ? 'closed' : undefined,
        search: searchValue,
        temperature: temperatureFilter === 'ALL' ? undefined : temperatureFilter,
        page,
        page_size: QUOTES_PAGE_SIZE,
        includeArchived: includeArchived || undefined,
      });
      setQuotes(data.items);
      setTotal(data.total);
    } catch (error: any) {
      toast.error('Failed to load quotes');
      if (error.response?.status === 401) {
        router.push('/login');
      }
    } finally {
      setLoading(false);
    }
  }, [statusFilter, temperatureFilter, searchApplied, page, includeArchived, router]);

  useEffect(() => {
    fetchQuotes();
  }, [fetchQuotes]);

  const openCloseDialog = useCallback((quote: Quote) => {
    setQuotePendingClose(quote);
    setCloseDialogOpen(true);
  }, []);

  const handleCloseQuote = useCallback(async () => {
    if (!quotePendingClose) return;
    try {
      setMarkingClose(true);
      await api.post(`/api/quotes/opportunities/${quotePendingClose.id}/close`, {});
      toast.success('Quote closed. Lead status unchanged (another quote may have won).');
      setCloseDialogOpen(false);
      setQuotePendingClose(null);
      await fetchQuotes();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to close quote');
    } finally {
      setMarkingClose(false);
    }
  }, [quotePendingClose, fetchQuotes]);

  const openCancelDraftDialog = useCallback((quote: Quote) => {
    setQuotePendingCancel(quote);
    setCancelDialogOpen(true);
  }, []);

  const handleCancelDraftQuote = useCallback(async () => {
    if (!quotePendingCancel) return;
    try {
      setCancellingDraft(true);
      await cancelDraftQuote(quotePendingCancel.id);
      toast.success('Draft quote cancelled.');
      setCancelDialogOpen(false);
      setQuotePendingCancel(null);
      await fetchQuotes();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to cancel draft quote');
    } finally {
      setCancellingDraft(false);
    }
  }, [quotePendingCancel, fetchQuotes]);

  // Auto-refresh when user returns to this tab/window
  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchQuotes();
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, [fetchQuotes]);

  const filteredQuotes = useMemo(() => {
    const sorted = [...quotes];
    if (sortBy === 'last_contacted') {
      sorted.sort((a, b) => {
        const diff = sortKeyLastContactedMs(b) - sortKeyLastContactedMs(a);
        if (diff !== 0) return diff;
        return b.id - a.id;
      });
    } else {
      sorted.sort((a, b) => {
        const diff = sortKeyCreatedMs(b) - sortKeyCreatedMs(a);
        if (diff !== 0) return diff;
        return b.id - a.id;
      });
    }
    return sorted;
  }, [quotes, sortBy]);

  const totalPages = Math.max(1, Math.ceil(total / QUOTES_PAGE_SIZE));

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 sm:px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-3xl font-semibold">Quotes</h1>
          {total > 0 && (
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

        <div className="flex flex-col lg:flex-row flex-wrap gap-4 mb-6 items-end">
            <Select value={statusFilter} onValueChange={onStatusFilterChange}>
              <SelectTrigger className="w-full md:w-[220px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="LIVE">Live quotes</SelectItem>
                <SelectItem value="CLOSED">Closed quotes</SelectItem>
                <SelectItem value="ALL">All statuses (excl. rejected & expired)</SelectItem>
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
            <Select value={sortBy} onValueChange={(v) => setSortBy(v as QuotesSortBy)}>
              <SelectTrigger className="w-full md:w-[220px]">
                <SelectValue placeholder="Sort" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="last_contacted">Last contacted (newest)</SelectItem>
                <SelectItem value="created">Created (newest)</SelectItem>
              </SelectContent>
            </Select>
            <Input
              placeholder="Search by quote #, customer, or lead type..."
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  setSearchApplied(searchDraft);
                }
              }}
              className="w-full md:w-[260px]"
            />
            <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer select-none pb-2">
              <input
                type="checkbox"
                className="rounded border-input"
                checked={includeArchived}
                onChange={(e) => setIncludeArchived(e.target.checked)}
              />
              Include archived
            </label>
          </div>

        {total === 0 ? (
          <Card>
            <CardContent className="p-6">
              <div className="text-center text-muted-foreground py-12">
                <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No quotes found</p>
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
                    <th className="text-left p-3 font-medium">Lead type</th>
                    <th className="text-left p-3 font-medium">Last contacted</th>
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
                      className={
                        quote.status === 'DRAFT'
                          ? 'border-b last:border-0 border-l-4 border-l-violet-500 bg-violet-50/50 dark:bg-violet-950/20 hover:bg-violet-100/60 dark:hover:bg-violet-950/30 cursor-pointer transition-colors'
                          : 'border-b last:border-0 hover:bg-muted/30 cursor-pointer transition-colors'
                      }
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
                        {getDisplayLeadType(quote.lead_type) ? (
                          <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">
                            {quote.lead_type}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground text-sm">—</span>
                        )}
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {quote.customer_last_interacted_at
                          ? new Date(quote.customer_last_interacted_at).toLocaleDateString('en-GB')
                          : '—'}
                      </td>
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
                          {showQuoteTemperatureBadge(quote) && (
                            <Badge className={temperatureColors[quote.temperature!]}>
                              {quote.temperature}
                            </Badge>
                          )}
                          {quote.archived_at && (
                            <Badge variant="outline" className="text-muted-foreground">
                              Archived
                            </Badge>
                          )}
                          <QuoteListEngagementBadges quote={quote} />
                        </div>
                      </td>
                      <td className="p-3 font-semibold">£{Number(quote.total_amount).toFixed(2)}</td>
                      <td className="p-3 text-muted-foreground">
                        {quote.valid_until
                          ? new Date(quote.valid_until).toLocaleDateString('en-GB')
                          : '—'}
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {new Date(quote.created_at).toLocaleDateString('en-GB')}
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
                          {quote.status === 'DRAFT' && (
                            <Button
                              variant="destructive"
                              size="sm"
                              onClick={() => openCancelDraftDialog(quote)}
                              disabled={cancellingDraft && quotePendingCancel?.id === quote.id}
                            >
                              <Trash2 className="h-4 w-4 mr-1" />
                              Cancel Draft
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
                          {quoteIsClosable(quote) && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => openCloseDialog(quote)}
                              disabled={markingClose && quotePendingClose?.id === quote.id}
                            >
                              <MinusCircle className="h-4 w-4 mr-1" />
                              Close
                            </Button>
                          )}
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
              <Card
                key={quote.id}
                className={
                  quote.status === 'DRAFT'
                    ? 'border-l-4 border-l-violet-500 bg-violet-50/50 dark:bg-violet-950/20 hover:shadow-md transition-shadow'
                    : 'hover:shadow-md transition-shadow'
                }
              >
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
                        {getDisplayLeadType(quote.lead_type) && (
                          <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">
                            {quote.lead_type}
                          </Badge>
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
                        {showQuoteTemperatureBadge(quote) && (
                          <Badge className={temperatureColors[quote.temperature!]}>
                            {quote.temperature}
                          </Badge>
                        )}
                        {quote.archived_at && (
                          <Badge variant="outline" className="text-muted-foreground">
                            Archived
                          </Badge>
                        )}
                        <QuoteListEngagementBadges quote={quote} />
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
                            Valid until: {new Date(quote.valid_until).toLocaleDateString('en-GB')}
                          </p>
                        )}
                        <p>Created: {new Date(quote.created_at).toLocaleDateString('en-GB')}</p>
                        <p>
                          Last contacted: {quote.customer_last_interacted_at
                            ? new Date(quote.customer_last_interacted_at).toLocaleDateString('en-GB')
                            : '—'}
                        </p>
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
                      {quote.status === 'DRAFT' && (
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => openCancelDraftDialog(quote)}
                          disabled={cancellingDraft && quotePendingCancel?.id === quote.id}
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          Cancel Draft
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
                      {quoteIsClosable(quote) && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openCloseDialog(quote)}
                          disabled={markingClose && quotePendingClose?.id === quote.id}
                        >
                          <MinusCircle className="h-4 w-4 mr-2" />
                          Close
                        </Button>
                      )}
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

        {total > 0 && (
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4 mt-6 py-4 border-t">
            <p className="text-sm text-muted-foreground">
              Showing {(page - 1) * QUOTES_PAGE_SIZE + 1}–{Math.min(page * QUOTES_PAGE_SIZE, total)} of {total}
              {totalPages > 1 ? ` · Page ${page} of ${totalPages}` : ''}
            </p>
            <div className="flex gap-2 justify-end">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}

        <Dialog
          open={closeDialogOpen}
          onOpenChange={(open) => {
            if (!markingClose) {
              setCloseDialogOpen(open);
              if (!open) setQuotePendingClose(null);
            }
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Close Quote</DialogTitle>
              <DialogDescription>
                Close this quote without changing the lead status. Use when another quote from the same lead may have won.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setCloseDialogOpen(false);
                  setQuotePendingClose(null);
                }}
                disabled={markingClose}
              >
                Cancel
              </Button>
              <Button onClick={() => void handleCloseQuote()} disabled={markingClose || !quotePendingClose}>
                {markingClose ? 'Closing...' : 'Close Quote'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog
          open={cancelDialogOpen}
          onOpenChange={(open) => {
            if (!cancellingDraft) {
              setCancelDialogOpen(open);
              if (!open) setQuotePendingCancel(null);
            }
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Cancel Draft</DialogTitle>
              <DialogDescription>
                Are you sure? This cannot be undone. The draft quote will be permanently deleted.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setCancelDialogOpen(false);
                  setQuotePendingCancel(null);
                }}
                disabled={cancellingDraft}
              >
                Keep Draft
              </Button>
              <Button
                variant="destructive"
                onClick={() => void handleCancelDraftQuote()}
                disabled={cancellingDraft || !quotePendingCancel}
              >
                {cancellingDraft ? 'Cancelling...' : 'Cancel Draft'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}

export default function QuotesPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen">
        <Header />
        <main className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </main>
      </div>
    }>
      <QuotesPageContent />
    </Suspense>
  );
}
