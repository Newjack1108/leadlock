'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  getDiscountRequests,
  approveDiscountRequest,
  rejectDiscountRequest,
} from '@/lib/api';
import { DiscountRequest, DiscountType, DiscountScope } from '@/lib/types';
import { toast } from 'sonner';
import { Check, X, Loader2, FileText } from 'lucide-react';
import api from '@/lib/api';

export default function DiscountRequestsPage() {
  const router = useRouter();
  const [requests, setRequests] = useState<DiscountRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [approvingId, setApprovingId] = useState<number | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const canApprove = userRole === 'DIRECTOR' || userRole === 'SALES_MANAGER';

  const fetchRequests = async () => {
    try {
      setLoading(true);
      const list = await getDiscountRequests({ status: 'PENDING' });
      setRequests(list);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load discount requests');
      }
      setRequests([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const response = await api.get('/api/auth/me');
        setUserRole(response.data.role);
      } catch {
        setUserRole(null);
      }
    };
    fetchUser();
  }, []);

  useEffect(() => {
    fetchRequests();
  }, []);

  const handleApprove = async (id: number) => {
    try {
      setApprovingId(id);
      await approveDiscountRequest(id);
      toast.success('Discount request approved and applied to quote');
      fetchRequests();
    } catch (error: any) {
      const msg = error.response?.data?.detail || error.message || 'Failed to approve';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setApprovingId(null);
    }
  };

  const openRejectDialog = (id: number) => {
    setRejectingId(id);
    setRejectionReason('');
    setRejectDialogOpen(true);
  };

  const handleReject = async () => {
    if (rejectingId == null) return;
    try {
      setActionLoading(true);
      await rejectDiscountRequest(rejectingId, rejectionReason.trim() || undefined);
      toast.success('Discount request rejected');
      setRejectDialogOpen(false);
      setRejectingId(null);
      fetchRequests();
    } catch (error: any) {
      const msg = error.response?.data?.detail || error.message || 'Failed to reject';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setActionLoading(false);
    }
  };

  const formatDiscount = (dr: DiscountRequest) => {
    const value =
      dr.discount_type === DiscountType.PERCENTAGE
        ? `${dr.discount_value}%`
        : `£${Number(dr.discount_value).toFixed(2)}`;
    const scope = dr.scope === DiscountScope.QUOTE ? 'quote' : 'products';
    return `${value} off ${scope}`;
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
        <div className="mb-6">
          <h1 className="text-3xl font-semibold mb-2">Discount requests</h1>
          <p className="text-muted-foreground">
            Review and approve or reject discount requests from sales
          </p>
        </div>

        {!canApprove ? (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              You do not have permission to approve discount requests. You can submit requests from
              a quote edit or detail page.
            </CardContent>
          </Card>
        ) : requests.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              No pending discount requests.
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Pending requests ({requests.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {requests.map((dr) => (
                  <div
                    key={dr.id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 border rounded-lg"
                  >
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Link
                          href={`/quotes/${dr.quote_id}`}
                          className="font-medium text-primary hover:underline flex items-center gap-1"
                        >
                          <FileText className="h-4 w-4" />
                          {dr.quote_number ?? `Quote #${dr.quote_id}`}
                        </Link>
                      </div>
                      <p className="text-sm font-medium">{formatDiscount(dr)}</p>
                      {dr.requested_by_name && (
                        <p className="text-sm text-muted-foreground">
                          Requested by {dr.requested_by_name}
                        </p>
                      )}
                      {dr.reason && (
                        <p className="text-sm text-muted-foreground mt-1">{dr.reason}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        size="sm"
                        onClick={() => handleApprove(dr.id)}
                        disabled={approvingId != null}
                      >
                        {approvingId === dr.id ? (
                          <Loader2 className="h-4 w-4 animate-spin mr-1" />
                        ) : (
                          <Check className="h-4 w-4 mr-1" />
                        )}
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => openRejectDialog(dr.id)}
                        disabled={actionLoading}
                      >
                        <X className="h-4 w-4 mr-1" />
                        Reject
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Reject discount request</DialogTitle>
            </DialogHeader>
            <div className="space-y-2">
              <Label>Reason (optional)</Label>
              <Textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="Let the requester know why this was rejected..."
                rows={3}
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejectDialogOpen(false)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={handleReject} disabled={actionLoading}>
                {actionLoading ? 'Rejecting...' : 'Reject'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}
