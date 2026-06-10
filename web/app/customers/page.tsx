'use client';

import { Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { getApiBaseUrl, getApiErrorDetail, getCustomers, getDataSummary, getUnreadCountsByCustomer } from '@/lib/api';
import { Customer } from '@/lib/types';
import { getTelUrl } from '@/lib/utils';
import { toast } from 'sonner';
import { Search, ChevronRight, X } from 'lucide-react';
import CallNotesDialog from '@/components/CallNotesDialog';
import NinoxBadge from '@/components/NinoxBadge';
import { parsePageFromSearchParams, saveCustomersListReturnUrl } from '@/lib/customersList';

const CUSTOMERS_PAGE_SIZE = 50;

function CustomersPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const hasUnreadFilter = searchParams.get('has_unread') === '1';
  const smsOptedOutFilter = searchParams.get('sms_opted_out') === '1';
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [unreadByCustomer, setUnreadByCustomer] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const [searchDraft, setSearchDraft] = useState('');
  const [searchApplied, setSearchApplied] = useState('');
  const [page, setPage] = useState(() => parsePageFromSearchParams(searchParams));
  const [total, setTotal] = useState(0);
  const [fetchState, setFetchState] = useState<'idle' | 'ok' | 'error'>('idle');
  const [fetchErrorDetail, setFetchErrorDetail] = useState<string | null>(null);
  const [dbSummaryCustomers, setDbSummaryCustomers] = useState<number | null>(null);
  const [callNotesOpen, setCallNotesOpen] = useState(false);
  const [callNotesCustomer, setCallNotesCustomer] = useState<{ id: number; name: string; phone: string } | null>(null);
  const resetPageDepsRef = useRef({ searchApplied, smsOptedOutFilter, hasUnreadFilter });

  useEffect(() => {
    const urlPage = parsePageFromSearchParams(searchParams);
    setPage((prev) => (prev === urlPage ? prev : urlPage));
  }, [searchParams]);

  useLayoutEffect(() => {
    const prev = resetPageDepsRef.current;
    const depsChanged =
      prev.searchApplied !== searchApplied ||
      prev.smsOptedOutFilter !== smsOptedOutFilter ||
      prev.hasUnreadFilter !== hasUnreadFilter;
    resetPageDepsRef.current = { searchApplied, smsOptedOutFilter, hasUnreadFilter };
    if (!depsChanged) return;

    setPage(1);
    const next = new URLSearchParams(searchParams.toString());
    if (!next.has('page')) return;
    next.delete('page');
    const qs = next.toString();
    router.replace(qs ? `/customers?${qs}` : '/customers', { scroll: false });
  }, [searchApplied, smsOptedOutFilter, hasUnreadFilter, router, searchParams]);

  const fetchCustomers = useCallback(async () => {
    try {
      setLoading(true);
      setFetchState('idle');
      setFetchErrorDetail(null);
      const searchValue = searchApplied.trim() || undefined;
      const summaryPromise = getDataSummary().catch(() => null);

      const customersData = await getCustomers({
        search: searchValue,
        sms_opted_out: smsOptedOutFilter || undefined,
        has_unread: hasUnreadFilter || undefined,
        include_total: Boolean(searchValue || smsOptedOutFilter || hasUnreadFilter),
        page,
        page_size: CUSTOMERS_PAGE_SIZE,
      });
      setCustomers(customersData.items ?? []);

      const summary = await summaryPromise;
      setDbSummaryCustomers(summary?.customers ?? null);

      const listTotal = typeof customersData.total === 'number' ? customersData.total : 0;
      const summaryTotal = summary?.customers ?? 0;
      setTotal(
        listTotal > 0
          ? listTotal
          : summaryTotal > 0 && !searchValue && !smsOptedOutFilter && !hasUnreadFilter
            ? summaryTotal
            : listTotal
      );
      setFetchState('ok');

      const loadUnreadBadges = () => {
        void getUnreadCountsByCustomer()
          .then((unreadRes) =>
            setUnreadByCustomer(
              Object.fromEntries((unreadRes || []).map((d) => [d.customer_id, d.unread_count]))
            )
          )
          .catch(() => setUnreadByCustomer({}));
      };
      if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
        window.requestIdleCallback(loadUnreadBadges, { timeout: 2500 });
      } else {
        setTimeout(loadUnreadBadges, 100);
      }
    } catch (error: unknown) {
      setFetchState('error');
      setFetchErrorDetail(getApiErrorDetail(error));
      toast.error('Failed to load customers');
      if (typeof error === 'object' && error !== null && 'response' in error) {
        const status = (error as { response?: { status?: number } }).response?.status;
        if (status === 401) {
          router.push('/login');
        }
      }
    } finally {
      setLoading(false);
    }
  }, [searchApplied, smsOptedOutFilter, hasUnreadFilter, page, router]);

  useEffect(() => {
    void fetchCustomers();
  }, [fetchCustomers]);

  useEffect(() => {
    if (loading || total === 0) return;
    const maxPage = Math.max(1, Math.ceil(total / CUSTOMERS_PAGE_SIZE));
    if (page <= maxPage) return;
    setPage(maxPage);
    const next = new URLSearchParams(searchParams.toString());
    if (maxPage <= 1) next.delete('page');
    else next.set('page', String(maxPage));
    const qs = next.toString();
    router.replace(qs ? `/customers?${qs}` : '/customers', { scroll: false });
  }, [loading, total, page, searchParams, router]);

  function syncPageToUrl(newPage: number) {
    const next = new URLSearchParams(searchParams.toString());
    if (newPage <= 1) next.delete('page');
    else next.set('page', String(newPage));
    const qs = next.toString();
    router.replace(qs ? `/customers?${qs}` : '/customers', { scroll: false });
  }

  function navigateToCustomer(customerId: number) {
    saveCustomersListReturnUrl();
    router.push(`/customers/${customerId}`);
  }

  function locationText(c: Customer): string {
    if (c.city && c.county) return `${c.city}, ${c.county}`;
    if (c.city) return c.city;
    if (c.postcode) return c.postcode;
    return '—';
  }

  function goToPage(updater: (p: number) => number) {
    setPage((prev) => {
      const newPage = updater(prev);
      syncPageToUrl(newPage);
      return newPage;
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  const totalPages = Math.max(1, Math.ceil(total / CUSTOMERS_PAGE_SIZE));

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
        <div className="mb-6 flex flex-col gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <h1 className="text-3xl font-semibold">Customers</h1>
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
              placeholder="Search by name, email, phone..."
                value={searchDraft}
                onChange={(e) => setSearchDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    setSearchApplied(searchDraft);
                  }
                }}
                className="pl-9"
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant={smsOptedOutFilter ? 'default' : 'outline'}
              size="sm"
              onClick={() => {
                const next = new URLSearchParams(searchParams.toString());
                next.delete('page');
                if (smsOptedOutFilter) next.delete('sms_opted_out');
                else next.set('sms_opted_out', '1');
                const qs = next.toString();
                router.push(qs ? `/customers?${qs}` : '/customers');
              }}
            >
              SMS opted out
            </Button>
          </div>
          {hasUnreadFilter && (
            <div className="flex items-center gap-2 rounded-lg border bg-muted/50 px-4 py-2 text-sm">
              <span className="text-muted-foreground">
                Showing customers with unread SMS, Messenger, or email
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 gap-1 px-2"
                onClick={() => {
                  const next = new URLSearchParams(searchParams.toString());
                  next.delete('page');
                  next.delete('has_unread');
                  const qs = next.toString();
                  router.push(qs ? `/customers?${qs}` : '/customers');
                }}
              >
                <X className="h-3.5 w-3.5" />
                Clear filter
              </Button>
            </div>
          )}
          {smsOptedOutFilter && (
            <div className="flex items-center gap-2 rounded-lg border bg-muted/50 px-4 py-2 text-sm">
              <span className="text-muted-foreground">
                Showing customers opted out of automated SMS outreach
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 gap-1 px-2"
                onClick={() => {
                  const next = new URLSearchParams(searchParams.toString());
                  next.delete('page');
                  next.delete('sms_opted_out');
                  const qs = next.toString();
                  router.push(qs ? `/customers?${qs}` : '/customers');
                }}
              >
                <X className="h-3.5 w-3.5" />
                Clear filter
              </Button>
            </div>
          )}
        </div>

        <Card>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-3 font-medium">Customer #</th>
                  <th className="text-left p-3 font-medium">Name</th>
                  <th className="text-left p-3 font-medium">Email</th>
                  <th className="text-left p-3 font-medium">Phone</th>
                  <th className="text-left p-3 font-medium">Location</th>
                  <th className="text-left p-3 font-medium">Customer since</th>
                  <th className="text-center p-3 font-medium w-20">Unread</th>
                  <th className="text-right p-3 font-medium w-16" aria-hidden />
                </tr>
              </thead>
              <tbody>
                {customers.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-8 text-center text-muted-foreground">
                      {hasUnreadFilter
                        ? 'No customers with unread SMS, Messenger, or email'
                        : smsOptedOutFilter
                        ? 'No customers currently flagged as SMS opted out'
                        : searchApplied.trim()
                        ? 'No customers match your search'
                        : fetchState === 'error'
                        ? `Could not load customers: ${fetchErrorDetail ?? 'request failed'}. API base: ${getApiBaseUrl() || '(same-origin /api — set API_URL on frontend)'}`
                        : fetchState === 'ok' && total === 0 && dbSummaryCustomers != null && dbSummaryCustomers > 0
                        ? `List returned 0 customers but /api/auth/data-summary reports ${dbSummaryCustomers} in the database — check filters (unread/SMS) or redeploy frontend with API_URL set.`
                        : fetchState === 'ok' && total === 0
                        ? `No customers in this database (list total: 0). API: ${getApiBaseUrl() || 'same-origin'}`
                        : 'No customers found'}
                    </td>
                  </tr>
                ) : (
                  customers.map((customer) => (
                    <tr
                      key={customer.id}
                      className="border-b last:border-0 hover:bg-muted/30 cursor-pointer transition-colors"
                      onClick={() => navigateToCustomer(customer.id)}
                    >
                      <td className="p-3 text-muted-foreground font-mono text-sm">
                        {customer.customer_number}
                      </td>
                      <td className="p-3 font-semibold">
                        <span className="inline-flex items-center gap-1.5">
                          {customer.name}
                          {customer.source_system === 'Ninox' && (
                            <NinoxBadge className="h-auto px-1.5 py-0.5 text-xs" />
                          )}
                        </span>
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {customer.email || '—'}
                      </td>
                      <td className="p-3 text-muted-foreground" onClick={(e) => e.stopPropagation()}>
                        {customer.phone ? (
                          <button
                            type="button"
                            className="text-primary hover:underline text-left"
                            onClick={(e) => {
                              e.preventDefault();
                              setCallNotesCustomer({ id: customer.id, name: customer.name, phone: customer.phone! });
                              setCallNotesOpen(true);
                            }}
                          >
                            {customer.phone}
                          </button>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {locationText(customer)}
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {new Date(customer.customer_since).toLocaleDateString('en-GB')}
                      </td>
                      <td className="p-3 text-center">
                        {unreadByCustomer[customer.id] > 0 ? (
                          <span className="inline-flex min-w-[20px] h-5 px-1 rounded-full bg-red-500 text-white text-xs font-semibold items-center justify-center">
                            {unreadByCustomer[customer.id] > 99 ? '99+' : unreadByCustomer[customer.id]}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="p-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => navigateToCustomer(customer.id)}
                        >
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {total > 0 && (
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4 mt-6 py-4 border-t">
            <p className="text-sm text-muted-foreground">
              Showing {(page - 1) * CUSTOMERS_PAGE_SIZE + 1}–{Math.min(page * CUSTOMERS_PAGE_SIZE, total)} of {total}
              {totalPages > 1 ? ` · Page ${page} of ${totalPages}` : ''}
            </p>
            <div className="flex gap-2 justify-end">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => goToPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => goToPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </main>

      {callNotesCustomer && (
        <CallNotesDialog
          open={callNotesOpen}
          onOpenChange={setCallNotesOpen}
          customerId={callNotesCustomer.id}
          customerName={callNotesCustomer.name}
          phone={callNotesCustomer.phone}
        />
      )}
    </div>
  );
}

export default function CustomersPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen">
          <Header />
          <main className="container mx-auto px-4 sm:px-6 py-8">
            <div className="text-center py-12 text-muted-foreground">Loading...</div>
          </main>
        </div>
      }
    >
      <CustomersPageContent />
    </Suspense>
  );
}
