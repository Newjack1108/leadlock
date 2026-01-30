'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { createDiscountRequest } from '@/lib/api';
import { DiscountType, DiscountScope } from '@/lib/types';
import { toast } from 'sonner';

interface RequestDiscountDialogProps {
  quoteId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

export default function RequestDiscountDialog({
  quoteId,
  open,
  onOpenChange,
  onSuccess,
}: RequestDiscountDialogProps) {
  const [discountType, setDiscountType] = useState<DiscountType>(DiscountType.PERCENTAGE);
  const [discountValue, setDiscountValue] = useState<string>('');
  const [scope, setScope] = useState<DiscountScope>(DiscountScope.QUOTE);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const valueNum = parseFloat(discountValue);
    if (isNaN(valueNum) || valueNum < 0) {
      toast.error('Please enter a valid discount value');
      return;
    }
    if (discountType === DiscountType.PERCENTAGE && valueNum > 100) {
      toast.error('Percentage cannot exceed 100');
      return;
    }
    setSubmitting(true);
    try {
      await createDiscountRequest(quoteId, {
        discount_type: discountType,
        discount_value: valueNum,
        scope,
        reason: reason.trim() || undefined,
      });
      toast.success('Discount request submitted. It will be reviewed by a manager.');
      setDiscountValue('');
      setReason('');
      onOpenChange(false);
      onSuccess();
    } catch (error: any) {
      const msg = error.response?.data?.detail || error.message || 'Failed to submit request';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Request a discount (requires approval)</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>Discount type</Label>
            <Select
              value={discountType}
              onValueChange={(v) => setDiscountType(v as DiscountType)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DiscountType.PERCENTAGE}>Percentage</SelectItem>
                <SelectItem value={DiscountType.FIXED_AMOUNT}>Fixed amount (£)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>{discountType === DiscountType.PERCENTAGE ? 'Percentage (%)' : 'Amount (£)'}</Label>
            <Input
              type="number"
              step={discountType === DiscountType.PERCENTAGE ? 1 : 0.01}
              min={0}
              max={discountType === DiscountType.PERCENTAGE ? 100 : undefined}
              value={discountValue}
              onChange={(e) => setDiscountValue(e.target.value)}
              placeholder={discountType === DiscountType.PERCENTAGE ? 'e.g. 10' : 'e.g. 50'}
              required
            />
          </div>
          <div className="space-y-2">
            <Label>Scope</Label>
            <Select value={scope} onValueChange={(v) => setScope(v as DiscountScope)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DiscountScope.QUOTE}>Entire quote</SelectItem>
                <SelectItem value={DiscountScope.PRODUCT}>Per product</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Reason (optional)</Label>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why is this discount needed?"
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Submitting...' : 'Submit request'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
