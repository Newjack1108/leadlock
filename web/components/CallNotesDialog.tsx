'use client';

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
import { ActivityType } from '@/lib/types';
import { getTelUrl } from '@/lib/utils';
import { toast } from 'sonner';
import { Phone, PhoneOff, MessageSquare, Bell, PanelBottom } from 'lucide-react';
import { useCallSession } from '@/components/callSessionContext';
import { useState } from 'react';

function combineNotes(prefix: string, freeNotes?: string): string {
  if (!freeNotes?.trim()) return prefix;
  return `${prefix}. ${freeNotes.trim()}`;
}

function openTelLink(phone: string) {
  const telUrl = getTelUrl(phone);
  if (!telUrl || typeof window === 'undefined') return;
  const anchor = document.createElement('a');
  anchor.href = telUrl;
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}

export default function CallNotesDialog() {
  const {
    session,
    minimize,
    expand,
    endSession,
    updateSession,
    notifyCallLogged,
  } = useCallSession();
  const [submitting, setSubmitting] = useState(false);

  const open = Boolean(session?.expanded);
  const callInProgress = Boolean(session?.callInProgress);
  const notes = session?.notes ?? '';
  const showSetReminder = Boolean(session?.showSetReminder);
  const reminderDate = session?.reminderDate ?? '';
  const reminderMessage = session?.reminderMessage ?? '';

  const handleOpenChange = (nextOpen: boolean) => {
    if (nextOpen) {
      expand();
      return;
    }
    // After Call: X / overlay minimize. Before Call: dismiss without logging.
    if (callInProgress) {
      minimize();
    } else {
      endSession();
    }
  };

  const handleCall = () => {
    if (!session) return;
    openTelLink(session.phone);
    updateSession({ callInProgress: true });
  };

  const finishLogged = (customerId: number) => {
    notifyCallLogged(customerId);
    endSession();
  };

  const handleEndCallAndSave = async () => {
    if (!session) return;
    if (!notes.trim()) {
      toast.error('Please add notes before ending the call');
      return;
    }
    setSubmitting(true);
    try {
      await logCallActivity(session.customerId, notes.trim(), ActivityType.LIVE_CALL);
      toast.success('Call logged');
      finishLogged(session.customerId);
    } catch {
      toast.error('Failed to log call');
    } finally {
      setSubmitting(false);
    }
  };

  const handleNoAnswer = async () => {
    if (!session) return;
    setSubmitting(true);
    try {
      await logCallActivity(session.customerId, combineNotes('No answer', notes));
      toast.success('Call logged (No answer)');
      finishLogged(session.customerId);
    } catch {
      toast.error('Failed to log call');
    } finally {
      setSubmitting(false);
    }
  };

  const handleLeftMessage = async () => {
    if (!session) return;
    if (!notes.trim()) {
      toast.error('Please add a note for left message');
      return;
    }
    setSubmitting(true);
    try {
      await logCallActivity(session.customerId, combineNotes('Left message', notes));
      toast.success('Call logged (Left message)');
      finishLogged(session.customerId);
    } catch {
      toast.error('Failed to log call');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSetReminder = async () => {
    if (!session) return;
    if (!reminderDate.trim()) {
      toast.error('Please select a reminder date');
      return;
    }
    setSubmitting(true);
    try {
      await createManualReminder({
        customer_id: session.customerId,
        title: `Call back: ${session.customerName}`,
        message: reminderMessage.trim() || `Follow up call - ${reminderDate}`,
        reminder_date: reminderDate,
      });
      const activityNote = combineNotes(`Set reminder: ${reminderDate}`, notes);
      await logCallActivity(session.customerId, activityNote);
      toast.success('Reminder set and call logged');
      finishLogged(session.customerId);
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: unknown } } };
      const msg = ax.response?.data?.detail || 'Failed to set reminder';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setSubmitting(false);
    }
  };

  const today = new Date().toISOString().slice(0, 10);

  const notesLabel = callInProgress
    ? 'Notes (required for End call & save or Left message)'
    : 'Notes (optional for No answer; required for Left message)';

  const notesPlaceholder = callInProgress
    ? 'What was discussed, or what message was left?'
    : 'Add notes (required if you choose Left message)';

  if (!session) return null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Call {session.customerName}</DialogTitle>
          <DialogDescription>{session.phone}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label htmlFor="call-notes">{notesLabel}</Label>
            <Textarea
              id="call-notes"
              placeholder={notesPlaceholder}
              value={notes}
              onChange={(e) => updateSession({ notes: e.target.value })}
              className="mt-1 min-h-[60px]"
              rows={2}
            />
          </div>

          {showSetReminder ? (
            <div className="space-y-3 rounded-md border p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Set reminder</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => updateSession({ showSetReminder: false })}
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
                  onChange={(e) => updateSession({ reminderDate: e.target.value })}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="reminder-message">Message (optional)</Label>
                <Input
                  id="reminder-message"
                  placeholder="e.g. Call back about quote"
                  value={reminderMessage}
                  onChange={(e) => updateSession({ reminderMessage: e.target.value })}
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
              {!callInProgress ? (
                <Button
                  type="button"
                  onClick={handleCall}
                  disabled={submitting}
                  className="w-full justify-start"
                >
                  <Phone className="h-4 w-4 mr-2" />
                  Call
                </Button>
              ) : (
                <>
                  <Button
                    type="button"
                    onClick={handleEndCallAndSave}
                    disabled={submitting || !notes.trim()}
                    className="w-full justify-start"
                  >
                    <PhoneOff className="h-4 w-4 mr-2" />
                    End call & save
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={minimize}
                    disabled={submitting}
                    className="w-full justify-start"
                  >
                    <PanelBottom className="h-4 w-4 mr-2" />
                    Browse system
                  </Button>
                </>
              )}
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
                disabled={submitting || !notes.trim()}
                className="w-full justify-start"
              >
                <MessageSquare className="h-4 w-4 mr-2" />
                Left message
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => updateSession({ showSetReminder: true })}
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
          <Button type="button" variant="ghost" onClick={() => endSession()}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
