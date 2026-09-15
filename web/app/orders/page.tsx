'use client';

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import axios from 'axios';
import { toast } from 'sonner';
import { ChevronDown, ChevronUp, ExternalLink, FileDown, FileText } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { downloadOrdersPdf, getOrders } from '@/lib/api';
import { LeadType, Order } from '@/lib/types';
import { Badge } from '@/components/ui/badge';
import NinoxBadge from '@/components/NinoxBadge';
import { isDepositPaid, isPaidInFull } from '@/lib/orderPayment';

const ORDERS_PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;

type OrderStatusFilter = 'new' | 'deposit_paid' | 'installation_booked' | 'installation_completed' | 'completed' | 'all';
type LeadTypeFilter = 'all' | LeadType | 'unknown';
type OrdersSortBy =
  | 'order_number'
  | 'customer'
  | 'customer_since'
  | 'lead_type'
  | 'lead_source'
  | 'total'
  | 'install_booked'
  | 'created';
type OrdersSortDir = 'asc' | 'desc';

function formatCurrency(amount: number, currency: string = 'GBP'): string {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

function getDisplayLeadType(leadType?: LeadType | null): LeadType | null {
  if (!leadType || leadType === LeadType.UNKNOWN) return null;
  return leadType;
}

function formatLeadSource(source?: string | null): string {
  if (!source || source === 'UNKNOWN') return '—';
  return source.replace(/_/g, ' ');
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString('en-GB');
}

function hasActiveFilters(
  statusFilter: OrderStatusFilter,
  leadTypeFilter: LeadTypeFilter,
  searchApplied: string,
  createdFrom: string,
  createdTo: string,
): boolean {
  return (
    statusFilter !== 'all' ||
    leadTypeFilter !== 'all' ||
    searchApplied.trim().length > 0 ||
    createdFrom.trim().length > 0 ||
    createdTo.trim().length > 0
  );
}

function SortHeader({
  label,
  column,
  sortBy,
  sortDir,
  onSort,
  className = 'text-left',
}: {
  label: string;
  column: OrdersSortBy;
  sortBy: OrdersSortBy;
  sortDir: OrdersSortDir;
  onSort: (column: OrdersSortBy) => void;
  className?: string;
}) {
  const active = sortBy === column;
  return (
    <th className={`p-3 font-medium ${className}`}>
      <button
        type="button"
        onClick={() => onSort(column)}
        className="inline-flex items-center gap-1 hover:text-foreground"
      >
        {label}
        {active ? (
          sortDir === 'asc' ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )
        ) : null}
      </button>
    </th>
  );
}

export default function OrdersPage() {
  const router = useRouter();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [statusFilter, setStatusFilter] = useState<OrderStatusFilter>('all');
  const [leadTypeFilter, setLeadTypeFilter] = useState<LeadTypeFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchApplied, setSearchApplied] = useState('');
  const [createdFrom, setCreatedFrom] = useState('');
  const [createdTo, setCreatedTo] = useState('');
  const [sortBy, setSortBy] = useState<OrdersSortBy>('created');
  const [sortDir, setSortDir] = useState<OrdersSortDir>('desc');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const hasLoadedRef = useRef(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchApplied(searchQuery);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [searchQuery]);

  useLayoutEffect(() => {
    setPage(1);
  }, [statusFilter, leadTypeFilter, searchApplied, createdFrom, createdTo, sortBy, sortDir]);

  const listQuery = {
    search: searchApplied.trim() || undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    lead_type: leadTypeFilter !== 'all' ? leadTypeFilter : undefined,
    createdFrom: createdFrom.trim() || undefined,
    createdTo: createdTo.trim() || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
  };

  const fetchOrders = useCallback(async () => {
    try {
      if (!hasLoadedRef.current) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }
      const data = await getOrders({
        page,
        page_size: ORDERS_PAGE_SIZE,
        search: searchApplied.trim() || undefined,
        status: statusFilter !== 'all' ? statusFilter : undefined,
        lead_type: leadTypeFilter !== 'all' ? leadTypeFilter : undefined,
        createdFrom: createdFrom.trim() || undefined,
        createdTo: createdTo.trim() || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      setOrders(data.items);
      setTotal(data.total);
      hasLoadedRef.current = true;
    } catch (error: unknown) {
      toast.error('Failed to load orders');
      if (axios.isAxiosError(error) && error.response?.status === 401) router.push('/login');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [page, statusFilter, leadTypeFilter, searchApplied, createdFrom, createdTo, sortBy, sortDir, router]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  const filtersActive = hasActiveFilters(statusFilter, leadTypeFilter, searchApplied, createdFrom, createdTo);
  const totalPages = Math.max(1, Math.ceil(total / ORDERS_PAGE_SIZE));

  const clearFilters = () => {
    setStatusFilter('all');
    setLeadTypeFilter('all');
    setSearchQuery('');
    setSearchApplied('');
    setCreatedFrom('');
    setCreatedTo('');
    setSortBy('created');
    setSortDir('desc');
  };

  const handleSort = (column: OrdersSortBy) => {
    if (sortBy === column) {
      setSortDir((dir) => (dir === 'desc' ? 'asc' : 'desc'));
      return;
    }
    setSortBy(column);
    setSortDir('desc');
  };

  const handleDownloadPdf = async () => {
    try {
      setDownloadingPdf(true);
      await downloadOrdersPdf(listQuery);
    } catch (error: unknown) {
      toast.error('Failed to download PDF');
      if (axios.isAxiosError(error) && error.response?.status === 401) router.push('/login');
    } finally {
      setDownloadingPdf(false);
    }
  };

  if (loading && orders.length === 0 && total === 0) {
    return (
      <div className="min-h-screen">
        <div className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 sm:px-6 py-8">
        <h1 className="text-3xl font-semibold mb-6">Orders</h1>

        {(total > 0 || filtersActive) && (
          <div className="flex flex-col lg:flex-row flex-wrap gap-4 mb-6 items-end">
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as OrderStatusFilter)}>
              <SelectTrigger className="w-full md:w-[200px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="new">New</SelectItem>
                <SelectItem value="deposit_paid">Deposit paid</SelectItem>
                <SelectItem value="installation_booked">Installation booked</SelectItem>
                <SelectItem value="installation_completed">Installation completed</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
                <SelectItem value="all">All</SelectItem>
              </SelectContent>
            </Select>
            <Select value={leadTypeFilter} onValueChange={(v) => setLeadTypeFilter(v as LeadTypeFilter)}>
              <SelectTrigger className="w-full md:w-[200px]">
                <SelectValue placeholder="Lead type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All lead types</SelectItem>
                <SelectItem value={LeadType.STABLES}>Stables</SelectItem>
                <SelectItem value={LeadType.SHEDS}>Sheds</SelectItem>
                <SelectItem value={LeadType.CABINS}>Cabins</SelectItem>
                <SelectItem value="unknown">Unknown / not set</SelectItem>
              </SelectContent>
            </Select>
            <div className="w-full md:w-auto">
              <p className="mb-1 text-xs text-muted-foreground">Created from</p>
              <Input
                type="date"
                value={createdFrom}
                onChange={(e) => setCreatedFrom(e.target.value)}
                className="w-full md:w-[160px]"
              />
            </div>
            <div className="w-full md:w-auto">
              <p className="mb-1 text-xs text-muted-foreground">Created to</p>
              <Input
                type="date"
                value={createdTo}
                onChange={(e) => setCreatedTo(e.target.value)}
                className="w-full md:w-[160px]"
              />
            </div>
            <Input
              placeholder="Search by order # or customer..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full md:w-[260px]"
            />
            <Button
              variant="outline"
              size="sm"
              className="mb-0.5"
              disabled={total === 0 || downloadingPdf}
              title={total === 0 ? 'No orders to export' : 'Download matching orders as PDF'}
              onClick={handleDownloadPdf}
            >
              <FileDown className="h-4 w-4 mr-1" />
              {downloadingPdf ? 'Downloading…' : 'Download PDF'}
            </Button>
          </div>
        )}

        {total === 0 && !filtersActive ? (
          <Card>
            <CardContent className="p-6">
              <div className="text-center text-muted-foreground py-12">
                <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No orders yet</p>
                <p className="text-sm mt-2">Orders are created when a quote is accepted.</p>
              </div>
            </CardContent>
          </Card>
        ) : total === 0 && filtersActive ? (
          <Card>
            <CardContent className="p-6">
              <div className="text-center text-muted-foreground py-12">
                <p>No orders match your filters</p>
                <Button variant="outline" size="sm" className="mt-4" onClick={clearFilters}>
                  Clear filters
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          <>
            <Card className={refreshing ? 'opacity-60 pointer-events-none transition-opacity' : undefined}>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <SortHeader label="Order #" column="order_number" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                      <SortHeader label="Customer" column="customer" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                      <SortHeader label="Customer since" column="customer_since" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                      <SortHeader label="Lead type" column="lead_type" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                      <SortHeader label="Lead source" column="lead_source" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                      <SortHeader label="Total" column="total" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                      <th className="text-left p-3 font-medium">Status</th>
                      <SortHeader label="Install booked" column="install_booked" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                      <SortHeader label="Created" column="created" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
                      <th className="text-right p-3 font-medium">Quote</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map((order) => (
                      <tr
                        key={order.id}
                        className="border-b last:border-0 hover:bg-muted/30 transition-colors cursor-pointer"
                        onClick={() => router.push(`/orders/${order.id}`)}
                      >
                        <td className="p-3 font-semibold">{order.order_number}</td>
                        <td className="p-3 text-muted-foreground">
                          <span className="inline-flex items-center gap-1.5">
                            {order.customer_name ?? '—'}
                            {order.is_ninox_origin && <NinoxBadge className="h-auto px-1.5 py-0.5 text-xs" />}
                          </span>
                        </td>
                        <td className="p-3 text-muted-foreground">{formatDate(order.customer_since)}</td>
                        <td className="p-3">
                          {getDisplayLeadType(order.lead_type) ? (
                            <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">
                              {order.lead_type}
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground text-sm">—</span>
                          )}
                        </td>
                        <td className="p-3 text-muted-foreground text-sm">{formatLeadSource(order.lead_source)}</td>
                        <td className="p-3 font-semibold">
                          {formatCurrency(order.total_amount, order.currency)}
                        </td>
                        <td className="p-3">
                          <div className="flex flex-wrap gap-1">
                            {isDepositPaid(order) && (
                              <Badge variant="secondary" className="text-xs">Deposit paid</Badge>
                            )}
                            {isPaidInFull(order) && (
                              <Badge variant="secondary" className="text-xs">Paid in full</Badge>
                            )}
                            {(order.installation_booked ?? false) && (
                              <Badge variant="secondary" className="text-xs">Inst. booked</Badge>
                            )}
                            {(order.installation_completed ?? false) && (
                              <Badge variant="default" className="text-xs">Inst. done</Badge>
                            )}
                            {order.access_sheet && (
                              <Badge
                                variant={order.access_sheet.completed ? 'default' : 'outline'}
                                className="text-xs"
                                title={order.access_sheet.completed ? 'Access sheet completed' : 'Access sheet sent'}
                              >
                                {order.access_sheet.completed ? 'Access done' : 'Access sent'}
                              </Badge>
                            )}
                            {!isDepositPaid(order) && !isPaidInFull(order) && !(order.installation_booked ?? false) && !(order.installation_completed ?? false) && !order.access_sheet && (
                              <span className="text-muted-foreground text-sm">—</span>
                            )}
                          </div>
                        </td>
                        <td className="p-3 text-muted-foreground">
                          {formatDate(order.installation_scheduled_at)}
                        </td>
                        <td className="p-3 text-muted-foreground">
                          {formatDate(order.created_at)}
                        </td>
                        <td className="p-3 text-right" onClick={(e) => e.stopPropagation()}>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => router.push(`/quotes/${order.quote_id}`)}
                            title="View quote"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            {total > 0 && (
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4 mt-6 py-4 border-t">
                <p className="text-sm text-muted-foreground">
                  Showing {(page - 1) * ORDERS_PAGE_SIZE + 1}–{Math.min(page * ORDERS_PAGE_SIZE, total)} of {total}
                  {totalPages > 1 ? ` · Page ${page} of ${totalPages}` : ''}
                </p>
                <div className="flex gap-2 justify-end">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1 || refreshing}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages || refreshing}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
