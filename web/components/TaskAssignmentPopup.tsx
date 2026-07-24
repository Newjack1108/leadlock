'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { ListTodo } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { getAuthMe, getMyAssignedTasks, invalidateStaleSummaryCache } from '@/lib/api';
import { loginGreetingPathShouldSuppress } from '@/lib/loginGreeting';
import type { AuthMe, Reminder } from '@/lib/types';

const POLL_MS = 30_000;

function seenStorageKey(userId: number): string {
  return `leadlock:seenTaskIds:${userId}`;
}

function readSeenIds(userId: number): Set<number> {
  try {
    const raw = localStorage.getItem(seenStorageKey(userId));
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((id): id is number => typeof id === 'number'));
  } catch {
    return new Set();
  }
}

function writeSeenIds(userId: number, ids: Set<number>): void {
  localStorage.setItem(seenStorageKey(userId), JSON.stringify([...ids]));
}

function formatDueDate(dueDate?: string | null): string | null {
  if (!dueDate) return null;
  const d = new Date(`${dueDate}T12:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function TaskAssignmentPopup() {
  const pathname = usePathname();
  const router = useRouter();
  const [queue, setQueue] = useState<Reminder[]>([]);
  const baselinedRef = useRef(false);
  const currentUserRef = useRef<AuthMe | null>(null);
  const tokenRef = useRef<string | null>(null);
  const queueIdsRef = useRef<Set<number>>(new Set());

  const activeTask = queue[0] ?? null;

  const acknowledge = useCallback((taskId: number) => {
    const user = currentUserRef.current;
    if (user) {
      const seen = readSeenIds(user.id);
      seen.add(taskId);
      writeSeenIds(user.id, seen);
    }
    queueIdsRef.current.delete(taskId);
    setQueue((prev) => prev.filter((t) => t.id !== taskId));
    invalidateStaleSummaryCache();
  }, []);

  const poll = useCallback(async () => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('token');
    if (!token) return;
    if (loginGreetingPathShouldSuppress(pathname)) return;

    if (token !== tokenRef.current) {
      tokenRef.current = token;
      currentUserRef.current = null;
      baselinedRef.current = false;
      queueIdsRef.current = new Set();
      setQueue([]);
    }

    let user = currentUserRef.current;
    if (!user) {
      try {
        user = await getAuthMe();
        currentUserRef.current = user;
      } catch {
        return;
      }
    }

    let tasks: Reminder[];
    try {
      tasks = await getMyAssignedTasks();
    } catch {
      return;
    }

    const openIds = new Set(tasks.map((t) => t.id));

    if (!baselinedRef.current) {
      const existing = readSeenIds(user.id);
      for (const id of openIds) existing.add(id);
      writeSeenIds(user.id, existing);
      baselinedRef.current = true;
      return;
    }

    const seen = readSeenIds(user.id);
    for (const id of [...seen]) {
      if (!openIds.has(id)) seen.delete(id);
    }

    const fresh: Reminder[] = [];
    for (const task of tasks) {
      if (seen.has(task.id) || queueIdsRef.current.has(task.id)) continue;
      if (task.created_by_id == null || task.created_by_id === user.id) {
        seen.add(task.id);
        continue;
      }
      fresh.push(task);
      queueIdsRef.current.add(task.id);
    }
    writeSeenIds(user.id, seen);

    if (fresh.length > 0) {
      setQueue((prev) => [...prev, ...fresh]);
    }
  }, [pathname]);

  useEffect(() => {
    if (loginGreetingPathShouldSuppress(pathname)) return;
    if (typeof window === 'undefined' || !localStorage.getItem('token')) return;

    void poll();
    const id = window.setInterval(() => {
      void poll();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [pathname, poll]);

  const dueLabel = activeTask ? formatDueDate(activeTask.due_date) : null;
  const details =
    activeTask?.message && activeTask.message.trim() && activeTask.message.trim() !== ' '
      ? activeTask.message.trim()
      : null;

  return (
    <Dialog
      open={activeTask != null}
      onOpenChange={(open) => {
        if (!open && activeTask) acknowledge(activeTask.id);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ListTodo className="h-5 w-5 text-sky-600" />
            New task
          </DialogTitle>
          <DialogDescription>
            You have been assigned a new task
            {activeTask?.created_by_name ? ` by ${activeTask.created_by_name}` : ''}.
          </DialogDescription>
        </DialogHeader>
        {activeTask && (
          <div className="space-y-2 py-1">
            <p className="font-semibold text-foreground">{activeTask.title}</p>
            {details ? <p className="text-sm text-muted-foreground whitespace-pre-wrap">{details}</p> : null}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {dueLabel ? <span>Due {dueLabel}</span> : null}
              {activeTask.customer_name ? <span>Customer: {activeTask.customer_name}</span> : null}
            </div>
          </div>
        )}
        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              if (!activeTask) return;
              const id = activeTask.id;
              acknowledge(id);
              router.push('/reminders');
            }}
          >
            View reminders
          </Button>
          <Button
            type="button"
            onClick={() => {
              if (activeTask) acknowledge(activeTask.id);
            }}
          >
            OK
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
