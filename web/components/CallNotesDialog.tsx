'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { logCallActivity, createManualReminder } from '@/lib/api';
import { getTelUrl } from '@/lib/utils';
import { toast } from 'sonner';
import { Phone, PhoneOff, MessageSquare, Bell } from 'lucide-react';

interface CallNotesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerId: number;
  customerName: string;
  phone: string;
  onSuccess?: () => void;
}

function combineNotes(prefix: string, freeNotes?: string): string {
  if (!freeNotes?.trim()) return prefix;
  return `${prefix}. ${freeNotes.trim()}`;
}

export default function CallNotesDialog({
  open,
  onOpenChange,
  customerId,
  customerName,
  phone,
  onSuccess,
}: CallNotesDialogProps) {
  const [notes, setNotes] = useState('');
  const [showSetReminder, setShowSetReminder] = useState(false);
  const [reminderDate, setReminderDate] = useState('');
  const [reminderMessage, setReminderMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [callInProgress, setCallInProgress] = useState(false);

  const resetForm = () => {
    setNotes('');
    setShowSetReminder(false);
    setReminderDate('');
    setReminderMessage('');
    setCallInProgress(false);
  };

  const handleClose = (open: boolean) => {
    if (!open) resetForm();
    onOpenChange(open);
  };

  const handleCall = () => {
    const telUrl = getTelUrl(phone);
    if (telUrl && typeof window !== 'undefined') {
      window.location.href = telUrl;
    }
    setCallInProgress(true);
  };

  const handleEndCallAndSave = async () => {
    if (!notes.trim()) {
      toast.error('Please add notes before ending the call');
      return;
    }
    setSubmitting(true);
    try {
      await logCallActivity(customerId, notes.trim());
      toast.success('Call logged');
      onSuccess?.();
      handleClose(false);
    } catch {
      toast.error('Failed to log call');
    } finally {
      setSubmitting(false);
    }
  };

  const handleNoAnswer = async () => {
    setSubmitting(true);
    try {
      await logCallActivity(customerId, combineNotes('No answer', notes));
      toast.success('Call logged (No answer)');
      onSuccess?.();
      handleClose(false);
    } catch {
      toast.error('Failed to log call');
    } finally {
      setSubmitting(false);
    }
  };

  const handleLeftMessage = async () => {
    setSubmitting(true);
    try {
      await logCallActivity(customerId, combineNotes('Left message', notes));
      toast.success('Call logged (Left message)');
      onSuccess?.();
      handleClose(false);
    } catch {
      toast.error('Failed to log call');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSetReminder = async () => {
    if (!reminderDate.trim()) {
      toast.error('Please select a reminder date');
      return;
    }
    setSubmitting(true);
    try {
      await createManualReminder({
        customer_id: customerId,
        title: `Call back: ${customerName}`,
        message: reminderMessage.trim() || `Follow up call - ${reminderDate}`,
        reminder_date: reminderDate,
      });
      const activityNote = combineNotes(`Set reminder: ${reminderDate}`, notes);
      await logCallActivity(customerId, activityNote);
      toast.success('Reminder set and call logged');
      onSuccess?.();
      handleClose(false);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to set reminder';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setSubmitting(false);
    }
  };

  const today = new Date().toISOString().slice(0, 10);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Call {customerName}</DialogTitle>
          <DialogDescription>{phone}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label htmlFor="call-notes">{callInProgress ? 'Notes (required)' : 'Notes (optional)'}</Label>
            <Textarea
              id="call-notes"
              placeholder="Add any notes..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="mt-1 min-h-[60px]"
              rows={2}
            />
          </div>

          {callInProgress ? (
            <Button
              type="button"
              onClick={handleEndCallAndSave}
              disabled={submitting || !notes.trim()}
              className="w-full"
            >
              <PhoneOff className="h-4 w-4 mr-2" />
              End call & save
            </Button>
          ) : showSetReminder ? (
            <div className="space-y-3 rounded-md border p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Set reminder</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowSetReminder(false)}
                >
                  Cancel
                </Button>
              </div>
              <div>
                <Label htmlFor="reminder-date">Reminder date</Label>
                <Input
                  id="reminder-date"
                  type="date"
                  min={today}
                  value={reminderDate}
                  onChange={(e) => setReminderDate(e.target.value)}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="reminder-message">Message (optional)</Label>
                <Input
                  id="reminder-message"
                  placeholder="e.g. Call back about quote"
                  value={reminderMessage}
                  onChange={(e) => setReminderMessage(e.target.value)}
                  className="mt-1"
                />
              </div>
              <Button
                type="button"
                onClick={handleSetReminder}
                disabled={submitting || !reminderDate}
                className="w-full"
              >
                <Bell className="h-4 w-4 mr-2" />
                Set reminder & log call
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <Button
                type="button"
                onClick={handleCall}
                disabled={submitting}
                className="w-full justify-start"
              >
                <Phone className="h-4 w-4 mr-2" />
                Call
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleNoAnswer}
                disabled={submitting}
                className="w-full justify-start"
              >
                <PhoneOff className="h-4 w-4 mr-2" />
                No answer
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleLeftMessage}
                disabled={submitting}
                className="w-full justify-start"
              >
                <MessageSquare className="h-4 w-4 mr-2" />
                Left message
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowSetReminder(true)}
                disabled={submitting}
                className="w-full justify-start"
              >
                <Bell className="h-4 w-4 mr-2" />
                Set reminder
              </Button>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => handleClose(false)}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
