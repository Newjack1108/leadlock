'use client';

import { useEffect, useRef, useState, DragEvent } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Download, FileText, Image as ImageIcon, Trash2, Upload } from 'lucide-react';
import {
  deleteCustomerFile,
  listCustomerFiles,
  listOrderFiles,
  listQuoteFiles,
  uploadCustomerFile,
  uploadOrderFile,
  uploadQuoteFile,
} from '@/lib/api';
import { CustomerFile, CustomerFileKind } from '@/lib/types';
import { toast } from 'sonner';
import { formatDateTime } from '@/lib/utils';

export type FilesContext = 'customer' | 'quote' | 'order';

interface FilesCardProps {
  context: FilesContext;
  id: number;
  title?: string;
  description?: string;
}

const ACCEPT = 'application/pdf,image/jpeg,image/png';
const ACCEPTED_TYPES = new Set(['application/pdf', 'image/jpeg', 'image/png']);
const MAX_BYTES = 25 * 1024 * 1024;

const KIND_LABELS: Record<CustomerFileKind, string> = {
  [CustomerFileKind.PLAN]: 'Plan',
  [CustomerFileKind.PHOTO]: 'Photo',
  [CustomerFileKind.OTHER]: 'Other',
};

const DEFAULT_TITLE: Record<FilesContext, string> = {
  customer: 'Files',
  quote: 'Plans & Documents',
  order: 'Plans & Documents',
};

const DEFAULT_DESCRIPTION: Record<FilesContext, string> = {
  customer:
    'Documents that apply to the customer (e.g. ID, site survey). Quote and order plans are kept on those pages.',
  quote:
    'Building plans for this quote. Auto-attach to the order if accepted.',
  order:
    'Plans and photos for this order. Files uploaded to the originating quote appear here too.',
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isImageContentType(contentType: string): boolean {
  return contentType.startsWith('image/');
}

async function listFor(context: FilesContext, id: number): Promise<CustomerFile[]> {
  if (context === 'customer') return listCustomerFiles(id);
  if (context === 'quote') return listQuoteFiles(id);
  return listOrderFiles(id);
}

async function uploadFor(
  context: FilesContext,
  id: number,
  file: File,
  kind: CustomerFileKind
): Promise<CustomerFile> {
  if (context === 'customer') return uploadCustomerFile(id, file, kind);
  if (context === 'quote') return uploadQuoteFile(id, file, kind);
  return uploadOrderFile(id, file, kind);
}

export default function FilesCard({ context, id, title, description }: FilesCardProps) {
  const [files, setFiles] = useState<CustomerFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [kind, setKind] = useState<CustomerFileKind>(CustomerFileKind.PLAN);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        const data = await listFor(context, id);
        if (!cancelled) setFiles(data);
      } catch {
        if (!cancelled) toast.error('Failed to load files');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [context, id]);

  const validateFile = (file: File): boolean => {
    if (!ACCEPTED_TYPES.has(file.type)) {
      toast.error(`${file.name}: must be a PDF, JPG or PNG`);
      return false;
    }
    if (file.size > MAX_BYTES) {
      toast.error(`${file.name}: must be 25 MB or less`);
      return false;
    }
    return true;
  };

  const handleFiles = async (incoming: FileList | File[]) => {
    const list = Array.from(incoming).filter(validateFile);
    if (list.length === 0) return;
    setUploading(true);
    try {
      const uploaded: CustomerFile[] = [];
      for (const f of list) {
        try {
          const created = await uploadFor(context, id, f, kind);
          uploaded.push(created);
        } catch (error: unknown) {
          const detail =
            (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
          toast.error(detail || `Failed to upload ${f.name}`);
        }
      }
      if (uploaded.length > 0) {
        setFiles((prev) => [...uploaded, ...prev]);
        toast.success(
          uploaded.length === 1
            ? 'File uploaded'
            : `${uploaded.length} files uploaded`
        );
      }
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDrag = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(e.target.files);
    }
  };

  const handleDelete = async (file: CustomerFile) => {
    if (!window.confirm(`Delete "${file.original_filename}"? This cannot be undone.`)) {
      return;
    }
    setDeletingId(file.id);
    try {
      await deleteCustomerFile(file.id);
      setFiles((prev) => prev.filter((f) => f.id !== file.id));
      toast.success('File removed');
    } catch (error: unknown) {
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Failed to delete file');
    } finally {
      setDeletingId(null);
    }
  };

  const cardTitle = title ?? DEFAULT_TITLE[context];
  const cardDescription = description ?? DEFAULT_DESCRIPTION[context];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{cardTitle}</CardTitle>
        <p className="text-sm text-muted-foreground">{cardDescription}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground uppercase tracking-wide">
              File type
            </label>
            <Select value={kind} onValueChange={(v) => setKind(v as CustomerFileKind)}>
              <SelectTrigger className="w-full sm:w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={CustomerFileKind.PLAN}>Plan</SelectItem>
                <SelectItem value={CustomerFileKind.PHOTO}>Photo</SelectItem>
                <SelectItem value={CustomerFileKind.OTHER}>Other</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          className={`
            border-2 border-dashed rounded-md p-6 text-center transition-colors
            ${dragActive ? 'border-primary bg-primary/5' : 'border-muted-foreground/25'}
            ${uploading ? 'opacity-70' : ''}
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPT}
            onChange={handleFileInput}
            disabled={uploading}
            className="hidden"
          />
          <div className="flex flex-col items-center gap-3">
            {uploading ? (
              <>
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                <p className="text-sm text-muted-foreground">Uploading…</p>
              </>
            ) : (
              <>
                <Upload className="h-8 w-8 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">
                    Drag and drop files here, or click to select
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    PDF, JPG or PNG up to 25 MB. Multiple files supported.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="h-4 w-4 mr-2" />
                  Select files
                </Button>
              </>
            )}
          </div>
        </div>

        {loading ? (
          <div className="text-center py-6 text-sm text-muted-foreground">Loading files…</div>
        ) : files.length === 0 ? (
          <div className="text-center py-6 text-sm text-muted-foreground">
            No files yet — drop PDFs or images here.
          </div>
        ) : (
          <div className="border rounded-md divide-y">
            {files.map((file) => {
              const isImage = isImageContentType(file.content_type);
              return (
                <div
                  key={file.id}
                  className="flex items-center gap-3 p-3"
                >
                  <div className="shrink-0 w-12 h-12 bg-muted rounded flex items-center justify-center overflow-hidden">
                    {isImage ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={file.secure_url}
                        alt={file.original_filename}
                        className="w-full h-full object-cover"
                      />
                    ) : file.content_type === 'application/pdf' ? (
                      <FileText className="h-6 w-6 text-muted-foreground" />
                    ) : (
                      <ImageIcon className="h-6 w-6 text-muted-foreground" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium truncate" title={file.original_filename}>
                        {file.original_filename}
                      </span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {KIND_LABELS[file.kind]}
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground truncate">
                      {formatFileSize(file.size_bytes)} · uploaded by{' '}
                      {file.uploaded_by_name || 'unknown'} · {formatDateTime(file.created_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      asChild
                      title="Download / open"
                    >
                      <a
                        href={file.secure_url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <Download className="h-4 w-4" />
                      </a>
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(file)}
                      disabled={deletingId === file.id}
                      className="text-destructive hover:text-destructive hover:bg-destructive/10"
                      title="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
