'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { logCustomerNote } from '@/lib/api';
import { toast } from 'sonner';

interface AddManualActivityDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerId: number;
  onSuccess?: () => void;
}

export default function AddManualActivityDialog({
  open,
  onOpenChange,
  customerId,
  onSuccess,
}: AddManualActivityDialogProps) {
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const resetForm = () => {
    setNotes('');
  };

  const handleClose = (next: boolean) => {
    if (!next) resetForm();
    onOpenChange(next);
  };

  const handleSubmit = async () => {
    const trimmed = notes.trim();
    if (!trimmed) {
      toast.error('Please enter a note');
      return;
    }
    setSubmitting(true);
    try {
      await logCustomerNote(customerId, trimmed);
      toast.success('Note added');
      onSuccess?.();
      handleClose(false);
    } catch {
      toast.error('Failed to add note');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add note</DialogTitle>
          <DialogDescription>
            Adds a manual entry to this customer&apos;s activity timeline.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Label htmlFor="manual-activity-notes">Note</Label>
          <Textarea
            id="manual-activity-notes"
            placeholder="What happened or what should the team know?"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="min-h-[100px]"
            rows={4}
          />
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
