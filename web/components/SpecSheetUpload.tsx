'use client';

import { useState, useRef, DragEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Upload, X, Image as ImageIcon, FileText } from 'lucide-react';
import { uploadSpecificationSheetFile } from '@/lib/api';
import { toast } from 'sonner';

interface SpecSheetUploadProps {
  value?: string;
  onChange: (url: string) => void;
  disabled?: boolean;
  label?: string;
}

const ACCEPT = 'image/*,application/pdf,.pdf';

function isPdfUrl(url: string): boolean {
  return url.toLowerCase().split('?')[0].endsWith('.pdf');
}

function isAcceptedFile(file: File): boolean {
  if (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) {
    return true;
  }
  return file.type.startsWith('image/');
}

export default function SpecSheetUpload({
  value,
  onChange,
  disabled,
  label = 'Specification sheet file',
}: SpecSheetUploadProps) {
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    if (!isAcceptedFile(file)) {
      toast.error('Please upload a PDF or image file');
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      toast.error('File size must be less than 10MB');
      return;
    }

    setUploading(true);
    try {
      const fileUrl = await uploadSpecificationSheetFile(file);
      onChange(fileUrl);
      toast.success('File uploaded successfully');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to upload file');
    } finally {
      setUploading(false);
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

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  const handleRemove = () => {
    onChange('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {value ? (
        <div className="relative">
          <div className="relative w-full min-h-64 border rounded-md overflow-hidden bg-muted">
            {isPdfUrl(value) ? (
              <div className="flex flex-col items-center justify-center gap-3 p-8 h-64">
                <FileText className="h-16 w-16 text-muted-foreground" />
                <p className="text-sm font-medium">PDF specification sheet uploaded</p>
                <a
                  href={value}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-primary hover:underline"
                >
                  View PDF
                </a>
              </div>
            ) : (
              <img
                src={value}
                alt="Specification sheet"
                className="w-full h-64 object-contain"
              />
            )}
            {!disabled && (
              <Button
                type="button"
                variant="destructive"
                size="sm"
                className="absolute top-2 right-2"
                onClick={handleRemove}
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          className={`
            border-2 border-dashed rounded-md p-8 text-center
            transition-colors
            ${dragActive ? 'border-primary bg-primary/5' : 'border-muted-foreground/25'}
            ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-primary/50'}
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT}
            onChange={handleFileInput}
            disabled={disabled || uploading}
            className="hidden"
          />
          <div className="flex flex-col items-center gap-4">
            {uploading ? (
              <>
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
                <p className="text-sm text-muted-foreground">Uploading...</p>
              </>
            ) : (
              <>
                <ImageIcon className="h-12 w-12 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">
                    Drag and drop a PDF or image here, or click to select
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    PDF, PNG, JPG, GIF up to 10MB
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={disabled || uploading}
                >
                  <Upload className="h-4 w-4 mr-2" />
                  Select File
                </Button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
