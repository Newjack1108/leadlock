'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { FolderOpen, Plus, Download, Trash2, Search } from 'lucide-react';
import {
  getSalesDocuments,
  uploadSalesDocument,
  downloadSalesDocument,
  deleteSalesDocument,
} from '@/lib/api';
import { SalesDocument } from '@/lib/types';
import { toast } from 'sonner';
import api from '@/lib/api';

const CATEGORIES = ['Price List', 'Spec Sheet', 'Brochure', 'Other'];

function formatFileSize(bytes?: number): string {
  if (bytes == null) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso?: string): string {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleDateString();
}

export default function SalesDocumentsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [documents, setDocuments] = useState<SalesDocument[]>([]);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [uploadCategory, setUploadCategory] = useState<string>('none');
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const canManage = userRole === 'DIRECTOR' || userRole === 'SALES_MANAGER';

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

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      const category = categoryFilter === 'all' ? undefined : categoryFilter;
      const data = await getSalesDocuments(category);
      setDocuments(data);
    } catch (error: unknown) {
      const err = error as { response?: { status?: number } };
      if (err.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load documents');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [categoryFilter]);

  const handleUpload = async () => {
    if (!uploadFile) {
      toast.error('Please select a file');
      return;
    }
    const name = uploadName.trim() || uploadFile.name;
    if (!name) {
      toast.error('Please enter a display name');
      return;
    }
    try {
      setUploading(true);
      await uploadSalesDocument(uploadFile, name, uploadCategory && uploadCategory !== 'none' ? uploadCategory : undefined);
      toast.success('Document uploaded successfully');
      setUploadDialogOpen(false);
      setUploadFile(null);
      setUploadName('');
      setUploadCategory('none');
      fetchDocuments();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error(err.response?.data?.detail || 'Failed to upload document');
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (doc: SalesDocument) => {
    try {
      const blob = await downloadSalesDocument(doc.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error: unknown) {
      toast.error('Failed to download document');
    }
  };

  const handleDelete = async (doc: SalesDocument) => {
    if (!confirm(`Delete "${doc.name}"? This cannot be undone.`)) return;
    try {
      setDeletingId(doc.id);
      await deleteSalesDocument(doc.id);
      toast.success('Document deleted');
      fetchDocuments();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error(err.response?.data?.detail || 'Failed to delete document');
    } finally {
      setDeletingId(null);
    }
  };

  const filteredDocuments = documents.filter((d) => {
    const matchesSearch =
      !searchQuery ||
      d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (d.filename && d.filename.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (d.category && d.category.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchesSearch;
  });

  if (loading && documents.length === 0) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 sm:px-6 py-8">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold">Sales Documents</h1>
            <p className="text-muted-foreground mt-2">
              Price lists, spec sheets, and brochures for attaching to emails
            </p>
          </div>
          {canManage && (
            <Button onClick={() => setUploadDialogOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Upload Document
            </Button>
          )}
        </div>

        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search by name, filename, or category..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select value={categoryFilter} onValueChange={setCategoryFilter}>
            <SelectTrigger className="w-full sm:w-[180px]">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {CATEGORIES.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {documents.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <FolderOpen className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No documents yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Upload price lists, spec sheets, and brochures to attach to emails
              </p>
              {canManage && (
                <Button onClick={() => setUploadDialogOpen(true)} className="mt-4">
                  <Plus className="h-4 w-4 mr-2" />
                  Upload Your First Document
                </Button>
              )}
            </CardContent>
          </Card>
        ) : (
          <div className="rounded-md border">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left text-sm font-medium">Name</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Category</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Size</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Uploaded</th>
                  <th className="px-4 py-3 text-right text-sm font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredDocuments.map((doc) => (
                  <tr key={doc.id} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <div>
                        <p className="font-medium">{doc.name}</p>
                        {doc.filename !== doc.name && (
                          <p className="text-xs text-muted-foreground">{doc.filename}</p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {doc.category ? (
                        <span className="text-sm">{doc.category}</span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {formatFileSize(doc.file_size)}
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {formatDate(doc.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDownload(doc)}
                        >
                          <Download className="h-3 w-3 mr-1" />
                          Download
                        </Button>
                        {canManage && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleDelete(doc)}
                            disabled={deletingId === doc.id}
                          >
                            <Trash2 className="h-3 w-3 mr-1" />
                            Delete
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredDocuments.length === 0 && searchQuery && (
              <p className="py-8 text-center text-muted-foreground">
                No documents match your search
              </p>
            )}
          </div>
        )}
      </main>

      <Dialog open={uploadDialogOpen} onOpenChange={setUploadDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Document</DialogTitle>
            <DialogDescription>
              Upload a price list, spec sheet, or brochure. Max 10MB. PDF, Excel, CSV, and images
              are supported.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="upload-file">File</Label>
              <Input
                id="upload-file"
                type="file"
                accept=".pdf,.xls,.xlsx,.csv,.jpg,.jpeg,.png,.gif,.webp,image/*,application/pdf"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  setUploadFile(f || null);
                  if (f && !uploadName) setUploadName(f.name.replace(/\.[^/.]+$/, ''));
                }}
              />
              {uploadFile && (
                <p className="text-sm text-muted-foreground mt-1">
                  {uploadFile.name} ({(uploadFile.size / 1024).toFixed(1)} KB)
                </p>
              )}
            </div>
            <div>
              <Label htmlFor="upload-name">Display name</Label>
              <Input
                id="upload-name"
                value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
                placeholder="e.g. 2024 Price List"
              />
            </div>
            <div>
              <Label htmlFor="upload-category">Category</Label>
              <Select value={uploadCategory} onValueChange={setUploadCategory}>
                <SelectTrigger id="upload-category">
                  <SelectValue placeholder="Select category (optional)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUploadDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleUpload} disabled={!uploadFile || uploading}>
              {uploading ? 'Uploading...' : 'Upload'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
