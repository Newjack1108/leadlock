'use client';

import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { getSalesDocuments, downloadSalesDocument } from '@/lib/api';
import { MAX_ATTACHMENT_BYTES_PER_FILE, MAX_ATTACHMENTS_TOTAL_BYTES } from '@/lib/attachmentLimits';
import type { SalesDocument } from '@/lib/types';
import { toast } from 'sonner';

export interface SalesDocumentAttachDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Current attachment payload size in bytes (files already on the email). */
  getExistingTotalBytes: () => number;
  /** Defaults to server limit (25MB total including new files). */
  maxTotalBytes?: number;
  onAdded: (files: File[]) => void;
}

export default function SalesDocumentAttachDialog({
  open,
  onOpenChange,
  getExistingTotalBytes,
  maxTotalBytes = MAX_ATTACHMENTS_TOTAL_BYTES,
  onAdded,
}: SalesDocumentAttachDialogProps) {
  const [docs, setDocs] = useState<SalesDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSelected(new Set());
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const list = await getSalesDocuments();
        if (!cancelled) setDocs(list);
      } catch {
        if (!cancelled) {
          toast.error('Failed to load sales documents');
          setDocs([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleAdd = async () => {
    if (selected.size === 0) {
      toast.error('Select at least one document');
      return;
    }
    const baseTotal = getExistingTotalBytes();
    const ids = Array.from(selected);
    try {
      setAdding(true);
      const newFiles: File[] = [];
      for (const id of ids) {
        const doc = docs.find((d) => d.id === id);
        if (!doc) continue;
        const blob = await downloadSalesDocument(id);
        if (blob.size > MAX_ATTACHMENT_BYTES_PER_FILE) {
          toast.error(`"${doc.name}" exceeds 10MB per-file limit`);
          continue;
        }
        const totalWithNew = baseTotal + newFiles.reduce((s, f) => s + f.size, 0) + blob.size;
        if (totalWithNew > maxTotalBytes) {
          toast.error('Total attachments would exceed 25MB limit');
          break;
        }
        const file = new File([blob], doc.filename, {
          type: doc.content_type || 'application/octet-stream',
        });
        newFiles.push(file);
      }
      if (newFiles.length > 0) {
        onAdded(newFiles);
        onOpenChange(false);
      }
    } catch {
      toast.error('Failed to add documents');
    } finally {
      setAdding(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Attach from sales documents</DialogTitle>
          <DialogDescription>
            Choose files from the Sales Documents library (same list as{' '}
            <a href="/sales-documents" className="text-primary underline underline-offset-2" target="_blank" rel="noreferrer">
              Sales Documents
            </a>
            ).
          </DialogDescription>
        </DialogHeader>
        {loading ? (
          <div className="py-8 text-center text-muted-foreground">Loading...</div>
        ) : docs.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">
            No documents in the library. Upload files on the{' '}
            <a href="/sales-documents" className="text-primary underline underline-offset-2" target="_blank" rel="noreferrer">
              Sales Documents
            </a>{' '}
            page.
          </div>
        ) : (
          <div className="max-h-[300px] overflow-y-auto space-y-2 py-2">
            {docs.map((doc) => (
              <label
                key={doc.id}
                className="flex items-center gap-3 p-2 rounded-md border cursor-pointer hover:bg-muted/50"
              >
                <input
                  type="checkbox"
                  checked={selected.has(doc.id)}
                  onChange={() => toggle(doc.id)}
                />
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{doc.name}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {doc.filename}
                    {doc.file_size != null ? ` · ${(doc.file_size / 1024).toFixed(1)} KB` : ''}
                  </p>
                </div>
              </label>
            ))}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-4">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleAdd}
            disabled={loading || docs.length === 0 || selected.size === 0 || adding}
          >
            {adding ? 'Adding...' : `Add ${selected.size} selected`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
