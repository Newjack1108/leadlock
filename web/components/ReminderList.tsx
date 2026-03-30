'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Reminder, ReminderPriority, SuggestedAction, ReminderType } from '@/lib/types';
import { 
  getReminders, dismissReminder, actOnReminder,
  generateReminders 
} from '@/lib/api';
import { toast } from 'sonner';
import { 
  RefreshCw, X, CheckCircle2, Mail, Phone, 
  FileText, ArrowRight, AlertCircle 
} from 'lucide-react';
import { useRouter } from 'next/navigation';

interface ReminderListProps {
  limit?: number;
  showActions?: boolean;
  onReminderAction?: () => void;
  priorityFilter?: ReminderPriority;
  typeFilter?: ReminderType;
  /** When true, only reminders assigned to the current user (API filter). */
  assignedToMe?: boolean;
  compact?: boolean;
  mode?: 'active' | 'done';
  refreshTrigger?: number;
  showHeaderActions?: boolean;
}

export default function ReminderList({ 
  limit, 
  showActions = true,
  onReminderAction,
  priorityFilter,
  typeFilter,
  assignedToMe,
  compact = false,
  mode = 'active',
  refreshTrigger,
  showHeaderActions = true,
}: ReminderListProps) {
  const router = useRouter();
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  const fetchReminders = async () => {
    try {
      setLoading(true);
      const params: Record<string, unknown> =
        mode === 'done' ? { done: true } : { dismissed: false };
      if (priorityFilter) params.priority = priorityFilter;
      if (typeFilter) params.reminder_type = typeFilter;
      if (assignedToMe === true) params.assigned_to_me = true;
      const data = await getReminders(params);
      const sorted = mode === 'done'
        ? data.sort((a: Reminder, b: Reminder) => {
            const aDate = a.acted_upon_at ? new Date(a.acted_upon_at).getTime() : 0;
            const bDate = b.acted_upon_at ? new Date(b.acted_upon_at).getTime() : 0;
            return bDate - aDate;
          })
        : data.sort((a: Reminder, b: Reminder) => {
            const priorityOrder = {
              [ReminderPriority.URGENT]: 0,
              [ReminderPriority.HIGH]: 1,
              [ReminderPriority.MEDIUM]: 2,
              [ReminderPriority.LOW]: 3,
            };
            const priorityDiff = priorityOrder[a.priority] - priorityOrder[b.priority];
            if (priorityDiff !== 0) return priorityDiff;
            return b.days_stale - a.days_stale;
          });
      setReminders(limit ? sorted.slice(0, limit) : sorted);
    } catch (error: any) {
      toast.error('Failed to load reminders');
      console.error('Error fetching reminders:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReminders();
  }, [mode, priorityFilter, typeFilter, assignedToMe, limit, refreshTrigger]);

  const isTaskOverdue = (r: Reminder) => {
    if (r.reminder_type !== ReminderType.USER_TASK || !r.due_date) return false;
    const d = new Date(`${r.due_date}T12:00:00`);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    d.setHours(0, 0, 0, 0);
    return d < today;
  };

  const staleLabel = (r: Reminder) => {
    if (r.reminder_type === ReminderType.USER_TASK && r.due_date) {
      const due = new Date(`${r.due_date}T12:00:00`);
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      due.setHours(0, 0, 0, 0);
      if (due < today) {
        return `${r.days_stale} day${r.days_stale === 1 ? '' : 's'} overdue`;
      }
      if (due.getTime() === today.getTime()) {
        return 'Due today';
      }
      return `Due ${new Date(r.due_date).toLocaleDateString()}`;
    }
    return `${r.days_stale} days stale`;
  };

  const handleDismiss = async (reminderId: number) => {
    try {
      await dismissReminder(reminderId);
      toast.success('Reminder dismissed');
      fetchReminders();
      onReminderAction?.();
    } catch (error: any) {
      toast.error('Failed to dismiss reminder');
      console.error('Error dismissing reminder:', error);
    }
  };

  const handleAct = async (reminderId: number, action: SuggestedAction) => {
    try {
      await actOnReminder(reminderId, action);
      toast.success('Reminder marked as acted upon');
      fetchReminders();
      onReminderAction?.();
    } catch (error: any) {
      toast.error('Failed to mark reminder as acted upon');
      console.error('Error acting on reminder:', error);
    }
  };

  const handleGenerate = async () => {
    try {
      setGenerating(true);
      const result = await generateReminders();
      toast.success(`Generated ${result.count} reminders`);
      fetchReminders();
    } catch (error: any) {
      toast.error('Failed to generate reminders');
      console.error('Error generating reminders:', error);
    } finally {
      setGenerating(false);
    }
  };

  const handleQuickAction = (reminder: Reminder, action: SuggestedAction) => {
    if (action === SuggestedAction.FOLLOW_UP || action === SuggestedAction.CONTACT_CUSTOMER || action === SuggestedAction.PHONE_CALL) {
      if (reminder.customer_id) {
        router.push(`/customers/${reminder.customer_id}`);
      } else if (reminder.quote_id) {
        router.push(`/quotes/${reminder.quote_id}`);
      } else if (reminder.lead_id) {
        router.push(`/leads/${reminder.lead_id}`);
      }
    } else if (action === SuggestedAction.RESEND_QUOTE || action === SuggestedAction.REVIEW_QUOTE) {
      if (reminder.quote_id) {
        router.push(`/quotes/${reminder.quote_id}`);
      }
    } else if (action === SuggestedAction.MARK_LOST) {
      if (reminder.lead_id) {
        router.push(`/leads/${reminder.lead_id}`);
      }
    }
  };

  const getPriorityColor = (priority: ReminderPriority) => {
    switch (priority) {
      case ReminderPriority.URGENT:
        return 'text-red-600 bg-red-50 border-red-200';
      case ReminderPriority.HIGH:
        return 'text-orange-600 bg-orange-50 border-orange-200';
      case ReminderPriority.MEDIUM:
        return 'text-yellow-600 bg-yellow-50 border-yellow-200';
      case ReminderPriority.LOW:
        return 'text-blue-600 bg-blue-50 border-blue-200';
      default:
        return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  const getActionIcon = (action: SuggestedAction) => {
    switch (action) {
      case SuggestedAction.FOLLOW_UP:
      case SuggestedAction.CONTACT_CUSTOMER:
        return <Mail className="h-4 w-4" />;
      case SuggestedAction.PHONE_CALL:
        return <Phone className="h-4 w-4" />;
      case SuggestedAction.RESEND_QUOTE:
        return <FileText className="h-4 w-4" />;
      case SuggestedAction.REVIEW_QUOTE:
        return <FileText className="h-4 w-4" />;
      case SuggestedAction.MARK_LOST:
        return <X className="h-4 w-4" />;
      default:
        return <ArrowRight className="h-4 w-4" />;
    }
  };

  const getActionLabel = (action: SuggestedAction) => {
    switch (action) {
      case SuggestedAction.FOLLOW_UP:
        return 'Follow Up';
      case SuggestedAction.CONTACT_CUSTOMER:
        return 'Contact';
      case SuggestedAction.PHONE_CALL:
        return 'Phone call';
      case SuggestedAction.RESEND_QUOTE:
        return 'Resend Quote';
      case SuggestedAction.REVIEW_QUOTE:
        return 'Review Quote';
      case SuggestedAction.MARK_LOST:
        return 'Mark Lost';
      default:
        return 'View';
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="text-center text-muted-foreground">Loading reminders...</div>
        </CardContent>
      </Card>
    );
  }

  if (reminders.length === 0) {
    const isDoneMode = mode === 'done';
    return (
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>{isDoneMode ? 'Completed Reminders' : 'Reminders'}</CardTitle>
          {!isDoneMode && showHeaderActions && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleGenerate}
              disabled={generating}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${generating ? 'animate-spin' : ''}`} />
              Generate
            </Button>
          )}
        </CardHeader>
        <CardContent>
          <div className="text-center text-muted-foreground py-8">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>{isDoneMode ? 'No completed reminders' : 'No active reminders'}</p>
            {!isDoneMode && <p className="text-sm mt-2">Click "Generate" to scan for stale items</p>}
          </div>
        </CardContent>
      </Card>
    );
  }

  const isDoneMode = mode === 'done';
  return (
    <Card className={compact ? 'min-h-[200px]' : ''}>
      <CardHeader className={`flex flex-row items-center justify-between ${compact ? 'py-2 px-4' : ''}`}>
        <CardTitle className={compact ? 'text-sm font-medium' : ''}>
          {isDoneMode ? 'Completed Reminders' : 'Reminders'} ({reminders.length})
        </CardTitle>
        {showHeaderActions && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className={compact ? 'h-7 text-xs' : ''}
              onClick={fetchReminders}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            {!isDoneMode && (
              <Button
                variant="outline"
                size="sm"
                className={compact ? 'h-7 text-xs' : ''}
                onClick={handleGenerate}
                disabled={generating}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${generating ? 'animate-spin' : ''}`} />
                Generate
              </Button>
            )}
          </div>
        )}
      </CardHeader>
      <CardContent className={compact ? 'px-4 pb-4 pt-0' : ''}>
        <div className={compact ? 'max-h-[280px] overflow-y-auto space-y-2' : 'space-y-3'}>
          {reminders.map((reminder) => (
            <div
              key={reminder.id}
              className={`border rounded-lg ${isDoneMode ? 'bg-muted/50 border-muted-foreground/20 text-muted-foreground' : getPriorityColor(reminder.priority)} ${!isDoneMode && isTaskOverdue(reminder) ? 'ring-2 ring-destructive/40' : ''} ${compact ? 'p-3' : 'p-4'}`}
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <Badge variant={reminder.priority === ReminderPriority.URGENT ? 'destructive' : 'secondary'}>
                      {reminder.priority}
                    </Badge>
                    {reminder.reminder_type === ReminderType.USER_TASK && (
                      <Badge variant="outline">Task</Badge>
                    )}
                    <span className="font-semibold">{reminder.title}</span>
                  </div>
                  <p className="text-sm text-muted-foreground mb-2">{reminder.message}</p>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {reminder.lead_name && (
                      <span>Lead: {reminder.lead_name}</span>
                    )}
                    {reminder.quote_number && (
                      <span>Quote: {reminder.quote_number}</span>
                    )}
                    {reminder.customer_name && (
                      <span>Customer: {reminder.customer_name}</span>
                    )}
                    {reminder.reminder_type === ReminderType.USER_TASK && reminder.assigned_to_name && (
                      <span>Assignee: {reminder.assigned_to_name}</span>
                    )}
                    {reminder.reminder_type === ReminderType.USER_TASK && reminder.created_by_name && (
                      <span>Created by: {reminder.created_by_name}</span>
                    )}
                    <span className={isTaskOverdue(reminder) ? 'font-medium text-destructive' : ''}>
                      {staleLabel(reminder)}
                    </span>
                    {isDoneMode && reminder.acted_upon_at && (
                      <span>
                        Completed on {new Date(reminder.acted_upon_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              {showActions && !isDoneMode && (
                <div className={`flex items-center gap-2 border-t ${compact ? 'mt-2 pt-2' : 'mt-3 pt-3'}`}>
                  <Button
                    size="sm"
                    variant="default"
                    className={compact ? 'h-7 text-xs' : ''}
                    onClick={() => {
                      handleQuickAction(reminder, reminder.suggested_action);
                      handleAct(reminder.id, reminder.suggested_action);
                    }}
                  >
                    {getActionIcon(reminder.suggested_action)}
                    <span className="ml-2">{getActionLabel(reminder.suggested_action)}</span>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className={compact ? 'h-7 text-xs' : ''}
                    onClick={() => handleDismiss(reminder.id)}
                  >
                    <X className="h-4 w-4 mr-2" />
                    Dismiss
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className={compact ? 'h-7 text-xs' : ''}
                    onClick={() => handleAct(reminder.id, reminder.suggested_action)}
                  >
                    <CheckCircle2 className="h-4 w-4 mr-2" />
                    Mark Done
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
        {limit && reminders.length >= limit && (
          <div className="mt-4 text-center">
            <Button
              variant="outline"
              onClick={() => router.push('/reminders')}
            >
              View All Reminders
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
