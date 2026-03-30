'use client';

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
import { createUserTask, getAssignableUsers, getAuthMe } from '@/lib/api';
import type { AssignableUser } from '@/lib/types';
import { toast } from 'sonner';

function todayIsoDate(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

interface CreateTaskDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: () => void;
}

export default function CreateTaskDialog({ open, onOpenChange, onCreated }: CreateTaskDialogProps) {
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [dueDate, setDueDate] = useState(todayIsoDate());
  const [assigneeId, setAssigneeId] = useState<string>('');
  const [users, setUsers] = useState<AssignableUser[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        setLoadingUsers(true);
        const [list, me] = await Promise.all([getAssignableUsers(), getAuthMe()]);
        if (cancelled) return;
        setUsers(list);
        const myId = me?.id;
        if (myId != null) {
          setAssigneeId(String(myId));
        } else if (list.length > 0) {
          setAssigneeId(String(list[0].id));
        }
      } catch (e) {
        console.error(e);
        toast.error('Failed to load users');
      } finally {
        if (!cancelled) setLoadingUsers(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      toast.error('Title is required');
      return;
    }
    if (!dueDate) {
      toast.error('Due date is required');
      return;
    }
    const aid = assigneeId ? parseInt(assigneeId, 10) : undefined;
    if (aid == null || Number.isNaN(aid)) {
      toast.error('Choose an assignee');
      return;
    }
    try {
      setSubmitting(true);
      await createUserTask({
        title: title.trim(),
        message: message.trim() || ' ',
        due_date: dueDate,
        assigned_to_id: aid,
      });
      toast.success('Task created');
      setTitle('');
      setMessage('');
      setDueDate(todayIsoDate());
      onOpenChange(false);
      onCreated?.();
    } catch (err: unknown) {
      console.error(err);
      toast.error('Failed to create task');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Create task</DialogTitle>
            <DialogDescription>
              Tasks appear in reminders and escalate when overdue.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="task-title">Title</Label>
              <Input
                id="task-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="What needs to be done?"
                autoComplete="off"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="task-message">Details</Label>
              <Textarea
                id="task-message"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Optional notes"
                rows={3}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="task-due">Due date</Label>
              <Input
                id="task-due"
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Assign to</Label>
              <Select
                value={assigneeId}
                onValueChange={setAssigneeId}
                disabled={loadingUsers || users.length === 0}
              >
                <SelectTrigger>
                  <SelectValue placeholder={loadingUsers ? 'Loading…' : 'Select user'} />
                </SelectTrigger>
                <SelectContent>
                  {users.map((u) => (
                    <SelectItem key={u.id} value={String(u.id)}>
                      {u.full_name} ({u.email})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || loadingUsers}>
              {submitting ? 'Creating…' : 'Create task'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
