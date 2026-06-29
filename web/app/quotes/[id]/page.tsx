'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import api, { getQuote, previewQuotePdf, getDiscountRequestsForQuote, getQuoteViewLink, acceptQuote, ensureQuoteOrder, cancelDraftQuote, duplicateQuoteToDraft, deleteDiscountRequest, patchQuote } from '@/lib/api';
import {
  Quote,
  QuoteItem,
  Customer,
  QuoteDiscount,
  DiscountRequest,
  DiscountRequestStatus,
  QuoteTemperature,
  LossCategory,
  OpportunityStage,
  QuoteStatus,
} from '@/lib/types';
import {
  QUOTE_BALANCE_BEFORE_COLLECTION_NOTE,
  QUOTE_BALANCE_BEFORE_DELIVERY_NOTE,
} from '@/lib/quoteCopy';
import SendQuoteEmailDialog from '@/components/SendQuoteEmailDialog';
import SendPaymentLinkDialog from '@/components/SendPaymentLinkDialog';
import CallNotesDialog from '@/components/CallNotesDialog';
import FilesCard from '@/components/FilesCard';
import { toast } from 'sonner';
import Link from 'next/link';
import { formatDateTime } from '@/lib/utils';
import { ArrowLeft, Mail, Eye, Tag, Pencil, ChevronDown, ChevronUp, Send, ExternalLink, CheckCircle, ShoppingBag, XCircle, MinusCircle, FileSearch, Trash2, Copy, AlertTriangle, CreditCard } from 'lucide-react';
import DraftConfiguratorLink from '@/components/configurator/DraftConfiguratorLink';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import RequestDiscountDialog from '@/components/RequestDiscountDialog';
import { celebrateQuoteAccept } from '@/lib/celebrate';

function showEditableTemperature(quote: Quote): boolean {
  if (quote.order_id) return false;
  if (quote.status === QuoteStatus.ACCEPTED) return false;
  if (quote.opportunity_stage === OpportunityStage.WON) return false;
  if (quote.accepted_at) return false;
  return true;
}

export default function QuoteDetailPage() {
  const router = useRouter();
  const params = useParams();
  const quoteId = parseInt(params.id as string);

  const [quote, setQuote] = useState<Quote | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [sendEmailDialogOpen, setSendEmailDialogOpen] = useState(false);
  const [sendPaymentLinkOpen, setSendPaymentLinkOpen] = useState(false);
  const [termsExpanded, setTermsExpanded] = useState(false);
  const [specSheetExpanded, setSpecSheetExpanded] = useState(false);
  const [discountRequests, setDiscountRequests] = useState<DiscountRequest[]>([]);
  const [requestDialogOpen, setRequestDialogOpen] = useState(false);
  const [callNotesOpen, setCallNotesOpen] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const [repairingOrder, setRepairingOrder] = useState(false);
  const [lostDialogOpen, setLostDialogOpen] = useState(false);
  const [closeDialogOpen, setCloseDialogOpen] = useState(false);
  const [lossReason, setLossReason] = useState('');
  const [lossCategory, setLossCategory] = useState<LossCategory | ''>('');
  const [markingLost, setMarkingLost] = useState(false);
  const [markingClose, setMarkingClose] = useState(false);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [duplicating, setDuplicating] = useState(false);
  const [removingDiscountRequestId, setRemovingDiscountRequestId] = useState<number | null>(null);
  const [savingTemperature, setSavingTemperature] = useState(false);

  useEffect(() => {
    if (quoteId) {
      fetchQuote();
    }
  }, [quoteId]);

  const fetchDiscountRequests = async () => {
    try {
      const list = await getDiscountRequestsForQuote(quoteId);
      setDiscountRequests(list);
    } catch {
      setDiscountRequests([]);
    }
  };

  const fetchQuote = async () => {
    try {
      setLoading(true);
      const response = await getQuote(quoteId);
      setQuote(response);
      
      // Fetch customer if we have customer_id
      if (response.customer_id) {
        try {
          const customerResponse = await api.get(`/api/customers/${response.customer_id}`);
          setCustomer(customerResponse.data);
        } catch (error) {
          console.error('Failed to load customer');
        }
      }
      await fetchDiscountRequests();
    } catch (error: any) {
      toast.error('Failed to load quote');
      if (error.response?.status === 401) {
        router.push('/login');
      } else if (error.response?.status === 404) {
        router.push('/customers');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleMarkLost = async () => {
    if (!lossReason || !lossCategory) {
      toast.error('Loss reason and category are required');
      return;
    }
    try {
      setMarkingLost(true);
      await api.post(`/api/quotes/opportunities/${quoteId}/lost`, {
        loss_reason: lossReason,
        loss_category: lossCategory,
      });
      toast.success('Quote marked as lost. Lead updated to LOST.');
      setLostDialogOpen(false);
      setLossReason('');
      setLossCategory('');
      fetchQuote();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to mark quote as lost');
    } finally {
      setMarkingLost(false);
    }
  };

  const handleClose = async () => {
    try {
      setMarkingClose(true);
      await api.post(`/api/quotes/opportunities/${quoteId}/close`, {});
      toast.success('Quote closed. Lead status unchanged (another quote may have won).');
      setCloseDialogOpen(false);
      fetchQuote();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to close quote');
    } finally {
      setMarkingClose(false);
    }
  };

  const handleCancelDraft = async () => {
    try {
      setCancelling(true);
      await cancelDraftQuote(quoteId);
      toast.success('Draft quote cancelled.');
      setCancelDialogOpen(false);
      router.push('/quotes');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to cancel draft quote');
    } finally {
      setCancelling(false);
    }
  };

  const handleDuplicateAsDraft = async () => {
    try {
      setDuplicating(true);
      const newQuote = await duplicateQuoteToDraft(quoteId);
      toast.success(`New draft ${newQuote.quote_number} created`);
      router.push(`/quotes/${newQuote.id}/edit`);
    } catch (error: any) {
      const d = error.response?.data?.detail;
      toast.error(typeof d === 'string' ? d : error.message || 'Failed to duplicate quote');
    } finally {
      setDuplicating(false);
    }
  };

  const handleTemperatureChange = async (newTemperature: QuoteTemperature) => {
    if (!quote || newTemperature === quote.temperature) return;

    const payload: Record<string, unknown> = { temperature: newTemperature };
    if (
      quote.opportunity_stage &&
      quote.opportunity_stage !== OpportunityStage.WON &&
      quote.opportunity_stage !== OpportunityStage.LOST
    ) {
      payload.next_action = quote.next_action ?? undefined;
      payload.next_action_due_date = quote.next_action_due_date ?? undefined;
    }

    try {
      setSavingTemperature(true);
      await patchQuote(quoteId, payload);
      setQuote({ ...quote, temperature: newTemperature });
      toast.success('Temperature updated');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update temperature');
    } finally {
      setSavingTemperature(false);
    }
  };

  const handleRemoveDiscountRequest = async (requestId: number) => {
    try {
      setRemovingDiscountRequestId(requestId);
      await deleteDiscountRequest(requestId);
      toast.success('Discount request removed');
      await fetchDiscountRequests();
      await fetchQuote();
    } catch (error: any) {
      const msg = error.response?.data?.detail || error.message || 'Failed to remove discount request';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setRemovingDiscountRequestId(null);
    }
  };

  const isClosable = quote && ['SENT', 'VIEWED'].includes(quote.status);

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

  if (!quote) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Quote not found</div>
        </div>
      </div>
    );
  }

  const isAccepted =
    quote.status === QuoteStatus.ACCEPTED ||
    quote.opportunity_stage === OpportunityStage.WON ||
    Boolean(quote.accepted_at) ||
    Boolean(quote.order_id);
  const missingAcceptedOrder = isAccepted && !quote.order_id;

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 sm:px-6 py-8">
        <div className="mb-6">
          <Button variant="ghost" onClick={() => router.back()} className="mb-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <div className="space-y-3">
            <div>
              <h1 className="text-3xl font-semibold">{quote.quote_number}</h1>
              {customer && (
                <p className="text-muted-foreground mt-1">
                  For {customer.name}
                  {quote.lead_id && quote.lead_name && (
                    <>
                      {' · '}
                      <Link href={`/leads/${quote.lead_id}`} className="text-primary hover:underline">
                        From lead: {quote.lead_name}
                      </Link>
                    </>
                  )}
                </p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="text-sm">{quote.status}</Badge>
              {quote.fulfillment_method === 'COLLECTION' && (
                <Badge variant="secondary" className="text-sm">
                  Collection
                </Badge>
              )}
              {showEditableTemperature(quote) && (
                <Select
                  value={quote.temperature || ''}
                  onValueChange={(v) => void handleTemperatureChange(v as QuoteTemperature)}
                  disabled={savingTemperature}
                >
                  <SelectTrigger className="w-[120px] h-8">
                    <SelectValue placeholder="Temperature" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={QuoteTemperature.HOT}>Hot</SelectItem>
                    <SelectItem value={QuoteTemperature.WARM}>Warm</SelectItem>
                    <SelectItem value={QuoteTemperature.COLD}>Cold</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {quote.status === 'DRAFT' && (
                <>
                  <Button variant="outline" asChild>
                    <Link href={`/quotes/${quote.id}/edit`}>
                      <Pencil className="h-4 w-4 mr-2" />
                      Edit Draft
                    </Link>
                  </Button>
                  <DraftConfiguratorLink quoteId={quote.id} variant="outline" />
                </>
              )}
              <Button
                variant="outline"
                onClick={async () => {
                  if (!quote) return;
                  try {
                    await previewQuotePdf(quoteId, {
                      includeSpecificationSheet:
                        quote.include_specification_sheet ||
                        Boolean(quote.has_specification_sheet_content),
                    });
                  } catch (error: any) {
                    toast.error(error.response?.data?.detail || error.message || 'Failed to download PDF');
                  }
                }}
              >
                <Eye className="h-4 w-4 mr-2" />
                Download PDF
              </Button>
              <Button
                onClick={() => setSendEmailDialogOpen(true)}
                disabled={!customer}
              >
                <Mail className="h-4 w-4 mr-2" />
                Send Quote
              </Button>
              {!isAccepted && ['DRAFT', 'SENT', 'VIEWED'].includes(quote.status) && (
                <Button
                  onClick={async () => {
                    try {
                      setAccepting(true);
                      const updated = await acceptQuote(quoteId);
                      void celebrateQuoteAccept();
                      if (updated?.order_id) {
                        toast.success('Quote accepted. Order created.');
                        setTimeout(() => {
                          router.push(`/orders/${updated.order_id}`);
                        }, 520);
                      } else {
                        await fetchQuote();
                        toast.success('Quote accepted. Order created.');
                      }
                    } catch (error: any) {
                      const d = error.response?.data?.detail;
                      const msg =
                        typeof d === 'string'
                          ? d
                          : Array.isArray(d)
                            ? d.map((x: { msg?: string }) => x?.msg).filter(Boolean).join(' ')
                            : 'Failed to accept quote';
                      toast.error(msg || 'Failed to accept quote');
                    } finally {
                      setAccepting(false);
                    }
                  }}
                  disabled={accepting}
                >
                  <CheckCircle className="h-4 w-4 mr-2" />
                  Accept quote
                </Button>
              )}
              {quote.status === 'ACCEPTED' && quote.order_id && (
                <Button variant="outline" asChild>
                  <Link href={quote.order_id ? `/orders/${quote.order_id}` : '/orders'}>
                    <ShoppingBag className="h-4 w-4 mr-2" />
                    View order
                  </Link>
                </Button>
              )}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button type="button" variant="outline">
                    More
                    <ChevronDown className="h-4 w-4 ml-2" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  {quote.lead_id && (
                    <DropdownMenuItem asChild>
                      <Link href={`/leads/${quote.lead_id}`}>
                        <FileSearch className="h-4 w-4 mr-2" />
                        View Enquiry
                      </Link>
                    </DropdownMenuItem>
                  )}
                  {quote.status !== 'DRAFT' && (
                    <DropdownMenuItem
                      onClick={() => void handleDuplicateAsDraft()}
                      disabled={duplicating}
                    >
                      <Copy className="h-4 w-4 mr-2" />
                      {duplicating ? 'Duplicating…' : 'Duplicate as draft'}
                    </DropdownMenuItem>
                  )}
                  {customer && (
                    <DropdownMenuItem onClick={() => setSendPaymentLinkOpen(true)}>
                      <CreditCard className="h-4 w-4 mr-2" />
                      Send payment link
                    </DropdownMenuItem>
                  )}
                  {quote.status === 'SENT' && (
                    <DropdownMenuItem
                      onClick={async () => {
                        try {
                          const { view_url } = await getQuoteViewLink(quoteId);
                          if (view_url) window.open(view_url, '_blank');
                          else toast.error('No view link available. Set FRONTEND_BASE_URL (or FRONTEND_URL) on the API.');
                        } catch {
                          toast.error('Failed to get view link');
                        }
                      }}
                    >
                      <ExternalLink className="h-4 w-4 mr-2" />
                      Open customer view
                    </DropdownMenuItem>
                  )}
                  {quote.status === 'DRAFT' && (
                    <DropdownMenuItem
                      onClick={() => setCancelDialogOpen(true)}
                      className="text-destructive focus:text-destructive"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Cancel Draft
                    </DropdownMenuItem>
                  )}
                  {isClosable && (
                    <>
                      <DropdownMenuItem
                        onClick={() => setLostDialogOpen(true)}
                        className="text-destructive focus:text-destructive"
                      >
                        <XCircle className="h-4 w-4 mr-2" />
                        Lose
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setCloseDialogOpen(true)}>
                        <MinusCircle className="h-4 w-4 mr-2" />
                        Close
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
                </DropdownMenu>
            </div>
          </div>
        </div>

        {missingAcceptedOrder && (
          <div className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950/30">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700 dark:text-amber-300" />
              <div className="flex-1">
                <p className="font-medium text-amber-800 dark:text-amber-200">
                  This quote is accepted but no order exists for it.
                </p>
                <p className="mt-1 text-amber-700 dark:text-amber-300">
                  Recreate the missing order from this accepted quote to restore the normal order workflow.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  disabled={repairingOrder}
                  onClick={async () => {
                    try {
                      setRepairingOrder(true);
                      const updated = await ensureQuoteOrder(quote.id);
                      setQuote(updated);
                      if (updated?.order_id) {
                        toast.success('Missing order recreated.');
                        router.push(`/orders/${updated.order_id}`);
                      } else {
                        toast.error('Order repair did not return an order.');
                      }
                    } catch (error: any) {
                      toast.error(error.response?.data?.detail || 'Failed to recreate order');
                    } finally {
                      setRepairingOrder(false);
                    }
                  }}
                >
                  <ShoppingBag className="h-4 w-4 mr-2" />
                  {repairingOrder ? 'Recreating order…' : 'Recreate missing order'}
                </Button>
              </div>
            </div>
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Quote Items */}
            <Card>
              <CardHeader>
                <CardTitle>Quote Items</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left py-2 px-3">Description</th>
                          <th className="text-right py-2 px-3">Quantity</th>
                          <th className="text-right py-2 px-3">Unit Price</th>
                          <th className="text-right py-2 px-3">Line Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {quote.items && quote.items.length > 0 ? (
                          (() => {
                            const allItems = quote.items!;
                            const getChildren = (parentId: number) =>
                              allItems
                                .filter((i: QuoteItem) => i.parent_quote_item_id === parentId)
                                .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));

                            const renderItemRows = (item: QuoteItem, depth: number): ReactNode[] => {
                              const isChild = depth > 0;
                              const hasDiscount = item.discount_amount > 0;
                              const rows: ReactNode[] = [
                                <tr
                                  key={item.id}
                                  className={`border-b${isChild ? ' bg-muted/30' : ''}`}
                                >
                                  <td
                                    className={`py-2 px-3${isChild ? ' text-muted-foreground' : ''}`}
                                    style={
                                      isChild ? { paddingLeft: `${8 + (depth - 1) * 16}px` } : undefined
                                    }
                                  >
                                    {isChild && (
                                      <span className="text-muted-foreground/80">— </span>
                                    )}
                                    {item.description}
                                    {!isChild && item.include_in_building_discount === false && (
                                      <span className="block text-xs text-muted-foreground mt-0.5">
                                        Not included in &apos;building items only&apos; discounts
                                      </span>
                                    )}
                                    {hasDiscount && (
                                      <Badge variant="outline" className="ml-2 text-xs">
                                        Discounted
                                      </Badge>
                                    )}
                                  </td>
                                  <td className="text-right py-2 px-3">
                                    {Number(item.quantity).toFixed(2)}
                                  </td>
                                  <td className="text-right py-2 px-3">
                                    £{Number(item.unit_price).toFixed(2)}
                                  </td>
                                  <td className="text-right py-2 px-3">
                                    {hasDiscount ? (
                                      <div>
                                        <div className="text-muted-foreground line-through text-sm">
                                          £{Number(item.line_total).toFixed(2)}
                                        </div>
                                        <div className="font-medium text-destructive">
                                          £{Number(item.final_line_total).toFixed(2)}
                                        </div>
                                      </div>
                                    ) : (
                                      <span className="font-medium">
                                        £{Number(item.line_total).toFixed(2)}
                                      </span>
                                    )}
                                  </td>
                                </tr>,
                              ];
                              getChildren(item.id).forEach((child) => {
                                rows.push(...renderItemRows(child, depth + 1));
                              });
                              return rows;
                            };

                            const mainItems = allItems
                              .filter((i: QuoteItem) => i.parent_quote_item_id == null)
                              .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
                            return mainItems.flatMap((item: QuoteItem) => renderItemRows(item, 0));
                          })()
                        ) : (
                          <tr>
                            <td colSpan={4} className="text-center py-4 text-muted-foreground">
                              No items in this quote
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                  
                  <div className="border-t pt-4 space-y-2">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Subtotal (Ex VAT):</span>
                      <span className="font-medium">£{Number(quote.subtotal).toFixed(2)}</span>
                    </div>
                    {Number(quote.discount_total) > 0 && (
                      <div className="flex justify-between text-destructive">
                        <span>Total Discount:</span>
                        <span>-£{Number(quote.discount_total).toFixed(2)}</span>
                      </div>
                    )}
                    <div className="flex justify-between font-semibold border-t pt-2">
                      <span>Total (Ex VAT):</span>
                      <span>£{Number(quote.total_amount).toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">VAT @ 20%:</span>
                      <span className="font-medium">£{Number(quote.vat_amount ?? Number(quote.total_amount) * 0.2).toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-lg font-semibold border-t pt-2">
                      <span>Total (inc VAT):</span>
                      <span>£{Number(quote.total_amount_inc_vat ?? Number(quote.total_amount) * 1.2).toFixed(2)}</span>
                    </div>
                    {Number(quote.deposit_amount) > 0 && (
                      <>
                        <div className="flex justify-between border-t pt-2">
                          <span className="font-medium">Deposit (on order, inc VAT):</span>
                          <span className="font-medium">£{Number(quote.deposit_amount).toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="font-medium">Balance (inc VAT):</span>
                          <span className="font-medium">£{Number(quote.balance_amount).toFixed(2)}</span>
                        </div>
                      </>
                    )}
                    <p className="text-sm pt-3 mt-2 border-t border-border">
                      {quote.fulfillment_method === 'COLLECTION'
                        ? QUOTE_BALANCE_BEFORE_COLLECTION_NOTE
                        : QUOTE_BALANCE_BEFORE_DELIVERY_NOTE}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Plans & Documents */}
            <FilesCard context="quote" id={quoteId} />

            {/* Applied Discounts */}
            {quote.discounts && quote.discounts.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Applied Discounts</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {quote.discounts.map((discount: QuoteDiscount) => (
                      <div
                        key={discount.id}
                        className="flex items-start justify-between p-3 border rounded-md"
                      >
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <Tag className="h-4 w-4 text-muted-foreground" />
                            <p className="font-medium">{discount.description}</p>
                            {discount.scope === 'PRODUCT' && (
                              <Badge variant="outline" className="text-xs">
                                Building Only
                              </Badge>
                            )}
                            {discount.scope === 'QUOTE' && (
                              <Badge variant="outline" className="text-xs">
                                Entire Quote
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">
                            {discount.discount_type === 'PERCENTAGE'
                              ? `${discount.discount_value}%`
                              : `£${Number(discount.discount_value).toFixed(2)}`}{' '}
                            discount
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="font-semibold text-destructive">
                            -£{Number(discount.discount_amount).toFixed(2)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Discount requests */}
            <Card>
              <CardHeader>
                <CardTitle>Discount requests</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {quote.status === 'DRAFT' && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setRequestDialogOpen(true)}
                  >
                    <Send className="h-4 w-4 mr-2" />
                    Request a discount (requires approval)
                  </Button>
                )}
                {discountRequests.length > 0 ? (
                  <div className="space-y-2">
                    {discountRequests.map((dr) => (
                      <div
                        key={dr.id}
                        className="flex items-center justify-between gap-3 p-3 border rounded-md text-sm"
                      >
                        <div>
                          <span className="font-medium">
                            {dr.discount_type === 'PERCENTAGE'
                              ? `${dr.discount_value}%`
                              : `£${Number(dr.discount_value).toFixed(2)}`}{' '}
                            off {dr.scope === 'PRODUCT' ? 'building items only' : 'entire quote'}
                          </span>
                          {dr.reason && (
                            <p className="text-muted-foreground mt-1">{dr.reason}</p>
                          )}
                          {dr.status === DiscountRequestStatus.REJECTED && dr.rejection_reason && (
                            <p className="text-destructive text-xs mt-1">{dr.rejection_reason}</p>
                          )}
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <Badge
                            variant={
                              dr.status === DiscountRequestStatus.APPROVED
                                ? 'default'
                                : dr.status === DiscountRequestStatus.REJECTED
                                  ? 'destructive'
                                  : 'secondary'
                            }
                          >
                            {dr.status}
                          </Badge>
                          {quote.status === 'DRAFT' &&
                            (dr.status === DiscountRequestStatus.PENDING ||
                              dr.status === DiscountRequestStatus.APPROVED) && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              disabled={removingDiscountRequestId === dr.id}
                              onClick={() => void handleRemoveDiscountRequest(dr.id)}
                            >
                              {removingDiscountRequestId === dr.id ? 'Removing...' : 'Remove'}
                            </Button>
                            )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No discount requests for this quote.</p>
                )}
              </CardContent>
            </Card>

            <RequestDiscountDialog
              quoteId={quoteId}
              open={requestDialogOpen}
              onOpenChange={setRequestDialogOpen}
              onSuccess={() => {
                fetchDiscountRequests();
                fetchQuote();
              }}
            />

            {/* Terms and Conditions */}
            {quote.terms_and_conditions && (
              <Card>
                <CardHeader
                  className="cursor-pointer hover:bg-muted/50 transition-colors rounded-t-lg"
                  onClick={() => setTermsExpanded((prev) => !prev)}
                >
                  <div className="flex items-center justify-between">
                    <CardTitle>Terms and Conditions</CardTitle>
                    {termsExpanded ? (
                      <ChevronUp className="h-5 w-5 text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronDown className="h-5 w-5 text-muted-foreground shrink-0" />
                    )}
                  </div>
                </CardHeader>
                {termsExpanded && (
                  <CardContent>
                    <div className="whitespace-pre-wrap text-sm">
                      {quote.terms_and_conditions}
                    </div>
                  </CardContent>
                )}
              </Card>
            )}

            {/* Specification Sheet */}
            {quote.has_specification_sheet_content && (
              <Card>
                <CardHeader
                  className="cursor-pointer hover:bg-muted/50 transition-colors rounded-t-lg"
                  onClick={() => setSpecSheetExpanded((prev) => !prev)}
                >
                  <div className="flex items-center justify-between">
                    <CardTitle>Specification Sheet</CardTitle>
                    {specSheetExpanded ? (
                      <ChevronUp className="h-5 w-5 text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronDown className="h-5 w-5 text-muted-foreground shrink-0" />
                    )}
                  </div>
                </CardHeader>
                {specSheetExpanded && (
                  <CardContent className="space-y-4">
                    <p className="text-xs text-muted-foreground">
                      {quote.include_specification_sheet
                        ? 'Included when sending to customer'
                        : quote.status !== 'DRAFT'
                          ? 'Not on the customer PDF yet — open Send Quote, check “Include specification sheet in customer view”, then resend or copy the customer link.'
                          : 'Not included when sending — enable on Edit quote or in Send Quote'}
                    </p>
                    {quote.company_specification_sheet_url && (
                      <div className="space-y-2">
                        <p className="text-sm font-medium">Company specification sheet</p>
                        {(() => {
                          const url = quote.company_specification_sheet_url;
                          const isPdf =
                            url.toLowerCase().split('?')[0].endsWith('.pdf') ||
                            url.includes('/raw/upload/');
                          if (isPdf) {
                            return (
                              <a
                                href={url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-2 text-sm text-primary hover:underline"
                              >
                                <ExternalLink className="h-4 w-4" />
                                View specification sheet PDF
                              </a>
                            );
                          }
                          return (
                            <img
                              src={url}
                              alt="Company specification sheet"
                              className="max-w-full rounded-md border"
                            />
                          );
                        })()}
                      </div>
                    )}
                    {quote.resolved_specification_sheet_text && (
                      <div className="whitespace-pre-wrap text-sm">
                        {quote.resolved_specification_sheet_text}
                      </div>
                    )}
                  </CardContent>
                )}
              </Card>
            )}

            {/* Notes (Internal) */}
            {quote.notes && (
              <Card>
                <CardHeader>
                  <CardTitle>Internal Notes</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="whitespace-pre-wrap text-sm text-muted-foreground">
                    {quote.notes}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Quote Details */}
            <Card>
              <CardHeader>
                <CardTitle>Quote Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Quote Number</div>
                  <div className="font-medium">{quote.quote_number}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Version</div>
                  <div className="font-medium">{quote.version}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Status</div>
                  <Badge>{quote.status}</Badge>
                </div>
                {quote.valid_until && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Valid Until</div>
                    <div className="font-medium">
                      {new Date(quote.valid_until).toLocaleDateString('en-GB')}
                    </div>
                  </div>
                )}
                {quote.sent_at && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Sent At</div>
                    <div className="text-sm">
                      {formatDateTime(quote.sent_at)}
                    </div>
                  </div>
                )}
                {quote.viewed_at != null && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">First viewed at</div>
                    <div className="text-sm">
                      {formatDateTime(quote.viewed_at)}
                    </div>
                  </div>
                )}
                {quote.last_viewed_at != null && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Last viewed at</div>
                    <div className="text-sm">
                      {formatDateTime(quote.last_viewed_at)}
                    </div>
                  </div>
                )}
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Times viewed</div>
                  <div className="text-sm font-medium">{quote.total_open_count ?? 0}</div>
                </div>
                {quote.accepted_at && (
                  <div>
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Accepted At</div>
                    <div className="text-sm">
                      {formatDateTime(quote.accepted_at)}
                    </div>
                  </div>
                )}
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Created</div>
                  <div className="text-sm">
                    {formatDateTime(quote.created_at)}
                  </div>
                </div>
                {quote.use_alternate_delivery_address && quote.fulfillment_method !== 'COLLECTION' && (
                  <div className="pt-3 border-t">
                    <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                      Delivery Location
                    </div>
                    <div className="text-sm whitespace-pre-wrap">
                      {[
                        quote.delivery_address_line1,
                        quote.delivery_address_line2,
                        quote.delivery_city,
                        quote.delivery_county,
                        quote.delivery_postcode,
                        quote.delivery_country,
                      ]
                        .filter(Boolean)
                        .join(', ')}
                    </div>
                    {quote.delivery_location_notes && (
                      <div className="text-xs text-muted-foreground mt-1">
                        Notes: {quote.delivery_location_notes}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Customer Info */}
            {customer && (
              <Card>
                <CardHeader>
                  <CardTitle>Customer</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Name</div>
                      <div className="font-medium">{customer.name}</div>
                    </div>
                    {customer.email && (
                      <div>
                        <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Email</div>
                        <div className="text-sm">{customer.email}</div>
                      </div>
                    )}
                    {customer.phone && (
                      <div>
                        <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Phone</div>
                        <button
                          type="button"
                          className="text-sm text-primary hover:underline text-left"
                          onClick={() => setCallNotesOpen(true)}
                        >
                          {customer.phone}
                        </button>
                      </div>
                    )}
                    <Button
                      variant="outline"
                      className="w-full mt-4"
                      onClick={() => router.push(`/customers/${customer.id}`)}
                    >
                      View Customer Profile →
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </main>

        {/* Lost Dialog */}
        <Dialog open={lostDialogOpen} onOpenChange={setLostDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Lose Quote</DialogTitle>
              <DialogDescription>
                This will mark the quote as lost and transition associated leads to LOST status.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div>
                <Label>Loss Category *</Label>
                <Select
                  value={lossCategory}
                  onValueChange={(value) => setLossCategory(value as LossCategory)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select category" />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.values(LossCategory).map((category) => (
                      <SelectItem key={category} value={category}>
                        {category}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Loss Reason *</Label>
                <Textarea
                  value={lossReason}
                  onChange={(e) => setLossReason(e.target.value)}
                  placeholder="Explain why this quote was lost..."
                  rows={4}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setLostDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleMarkLost}
                disabled={markingLost || !lossReason || !lossCategory}
                variant="destructive"
              >
                {markingLost ? 'Marking...' : 'Mark as Lost'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Close Dialog */}
        <Dialog open={closeDialogOpen} onOpenChange={setCloseDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Close Quote</DialogTitle>
              <DialogDescription>
                Close this quote without changing the lead status. Use when another quote from the same lead may have won.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCloseDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleClose} disabled={markingClose}>
                {markingClose ? 'Closing...' : 'Close Quote'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Cancel Draft Dialog */}
        <Dialog open={cancelDialogOpen} onOpenChange={setCancelDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Cancel Draft</DialogTitle>
              <DialogDescription>
                Are you sure? This cannot be undone. The draft quote will be permanently deleted.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCancelDialogOpen(false)}>
                Keep Draft
              </Button>
              <Button variant="destructive" onClick={handleCancelDraft} disabled={cancelling}>
                {cancelling ? 'Cancelling...' : 'Cancel Draft'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

      {customer && (
        <SendQuoteEmailDialog
          open={sendEmailDialogOpen}
          onOpenChange={setSendEmailDialogOpen}
          quoteId={quoteId}
          customer={customer}
          variant={quote.order_id ? 'order' : 'quote'}
          onSuccess={() => {
            fetchQuote();
          }}
        />
      )}

      {customer && quote && (
        <SendPaymentLinkDialog
          open={sendPaymentLinkOpen}
          onOpenChange={setSendPaymentLinkOpen}
          quote={quote}
          customer={customer}
          onSuccess={() => {
            fetchQuote();
          }}
        />
      )}

      {customer && customer.phone && (
        <CallNotesDialog
          open={callNotesOpen}
          onOpenChange={setCallNotesOpen}
          customerId={customer.id}
          customerName={customer.name}
          phone={customer.phone}
          onSuccess={() => fetchQuote()}
        />
      )}
    </div>
  );
}
