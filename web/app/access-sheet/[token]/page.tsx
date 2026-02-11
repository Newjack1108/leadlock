'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { getAccessSheetContext, submitAccessSheet } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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

const GROUND_TYPES = [
  { value: 'NEW_CONCRETE', label: 'New Concrete' },
  { value: 'OLD_CONCRETE', label: 'Old Concrete' },
  { value: 'GRASS_FIELD', label: 'Grass/Field' },
  { value: 'HARDCORE', label: 'Hardcore' },
] as const;

type YesNo = 'yes' | 'no';

const YES_NO_QUESTIONS: { key: string; notesKey: string; label: string }[] = [
  { key: 'access_4x4_trailer', notesKey: 'access_4x4_notes', label: 'Is the access suitable for a 4x4 and trailer?' },
  { key: 'drive_near_build', notesKey: 'drive_near_build_notes', label: 'Can we drive up to or near the position of the new build?' },
  { key: 'permission_drive_land', notesKey: 'permission_drive_land_notes', label: 'Permission to drive on the land (tracks in the field will be made)' },
  { key: 'balances_paid_before', notesKey: 'balances_paid_before_notes', label: 'Aware that all outstanding balances must be paid day before delivery' },
  { key: 'horses_contained', notesKey: 'horses_contained_notes', label: 'Horses will be contained away during installation' },
  { key: 'site_level', notesKey: 'site_level_notes', label: 'Is the install site perfectly level?' },
  { key: 'area_clear', notesKey: 'area_clear_notes', label: 'Is the area fully clear of long grass and shrubs?' },
  { key: 'brickwork_if_concrete', notesKey: 'brickwork_notes', label: 'If concrete, will there be a course of brickwork?' },
  { key: 'electricity_available', notesKey: 'electricity_notes', label: 'Electricity available onsite near the installation' },
  { key: 'toilet_facilities', notesKey: 'toilet_notes', label: 'Are there toilet facilities available on site or nearby?' },
];

function YesNoField({
  value,
  onChange,
  onNotesChange,
  notesValue,
  label,
  fieldKey,
}: {
  value: YesNo | '';
  onChange: (v: YesNo) => void;
  onNotesChange: (v: string) => void;
  notesValue: string;
  label: string;
  fieldKey: string;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="radio"
            name={fieldKey}
            checked={value === 'yes'}
            onChange={() => onChange('yes')}
            className="h-4 w-4"
          />
          <span>Yes</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="radio"
            name={fieldKey}
            checked={value === 'no'}
            onChange={() => onChange('no')}
            className="h-4 w-4"
          />
          <span>No</span>
        </label>
      </div>
      <Textarea
        placeholder="Notes (optional)"
        value={notesValue}
        onChange={(e) => onNotesChange(e.target.value)}
        rows={2}
        className="resize-none"
      />
    </div>
  );
}

export default function AccessSheetPage() {
  const params = useParams();
  const token = params.token as string;

  const [customerName, setCustomerName] = useState('');
  const [orderNumber, setOrderNumber] = useState('');
  const [completed, setCompleted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  const [formData, setFormData] = useState<Record<string, string>>({});

  const setField = (key: string, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };
  const getField = (key: string) => formData[key] ?? '';

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    getAccessSheetContext(token)
      .then((res) => {
        if (!cancelled) {
          setCustomerName(res.customer_name);
          setOrderNumber(res.order_number);
          setCompleted(res.completed);
          if (res.answers) {
            setFormData(res.answers as Record<string, string>);
          }
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.response?.status === 404 ? 'Access sheet not found' : 'Failed to load form');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || submitting || completed) return;

    setSubmitting(true);
    setError(null);
    try {
      const payload: Record<string, string> = {};
      for (const q of YES_NO_QUESTIONS) {
        const v = getField(q.key);
        if (v) payload[q.key] = v;
        const notes = getField(q.notesKey);
        if (notes) payload[q.notesKey] = notes;
      }
      const ground = getField('ground_type');
      if (ground) payload.ground_type = ground;
      const sig = getField('customer_signature');
      if (sig) payload.customer_signature = sig;
      const extraNotes = getField('notes');
      if (extraNotes) payload.notes = extraNotes;

      await submitAccessSheet(token, payload);
      setSubmitSuccess(true);
      setCompleted(true);
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Failed to submit. Please try again.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-muted/30 flex items-center justify-center p-6">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (error && !submitSuccess) {
    return (
      <div className="min-h-screen bg-muted/30 flex items-center justify-center p-6">
        <div className="text-center">
          <p className="text-destructive font-medium">{error}</p>
          <p className="text-sm text-muted-foreground mt-2">The link may have expired or be invalid.</p>
        </div>
      </div>
    );
  }

  if (submitSuccess || completed) {
    return (
      <div className="min-h-screen bg-muted/30 flex items-center justify-center p-6">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle>Thank you</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">
              Your access sheet has been submitted successfully. We will use this information to plan a smooth
              installation.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-muted/30 py-8 px-4">
      <div className="max-w-2xl mx-auto">
        <Card>
          <CardHeader>
            <CardTitle>Pre Fitting Check List</CardTitle>
            <p className="text-sm text-muted-foreground">
              This will help us plan a smooth installation. Thank you for choosing Cheshire Stables.
            </p>
            <div className="grid grid-cols-2 gap-4 pt-2 text-sm">
              <div>
                <span className="text-muted-foreground">Customer: </span>
                <span className="font-medium">{customerName}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Order: </span>
                <span className="font-medium">{orderNumber}</span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              {YES_NO_QUESTIONS.map((q) => (
                <YesNoField
                  key={q.key}
                  label={q.label}
                  fieldKey={q.key}
                  value={(getField(q.key) as YesNo) || ''}
                  onChange={(v) => setField(q.key, v)}
                  notesValue={getField(q.notesKey)}
                  onNotesChange={(v) => setField(q.notesKey, v)}
                />
              ))}

              <div className="space-y-2">
                <Label>What type of ground is the building to be built on?</Label>
                <Select
                  value={getField('ground_type')}
                  onValueChange={(v) => setField('ground_type', v)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select ground type" />
                  </SelectTrigger>
                  <SelectContent>
                    {GROUND_TYPES.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Customer signature (type your full name to confirm)</Label>
                <Input
                  value={getField('customer_signature')}
                  onChange={(e) => setField('customer_signature', e.target.value)}
                  placeholder="Your full name"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label>Additional notes</Label>
                <Textarea
                  value={getField('notes')}
                  onChange={(e) => setField('notes', e.target.value)}
                  placeholder="Any other information we should know..."
                  rows={4}
                  className="resize-none"
                />
              </div>

              {error && (
                <p className="text-sm text-destructive">{error}</p>
              )}

              <Button type="submit" disabled={submitting} className="w-full">
                {submitting ? 'Submitting...' : 'Submit Access Sheet'}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
