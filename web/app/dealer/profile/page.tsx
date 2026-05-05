'use client';

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { getDealerProfile, updateDealerProfile, uploadDealerLogo } from '@/lib/api';
import type { DealerProfile } from '@/lib/types';
import type { AxiosError } from 'axios';

function apiErrorMessage(err: unknown, fallback: string): string {
  const ax = err as AxiosError<{ detail?: unknown }>;
  const d = ax.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length && typeof d[0] === 'object' && d[0] && 'msg' in d[0]) {
    return String((d[0] as { msg: string }).msg);
  }
  return fallback;
}

export default function DealerProfilePage() {
  const [profile, setProfile] = useState<DealerProfile | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [initialLoad, setInitialLoad] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const fetchProfile = useCallback(() => {
    setInitialLoad(true);
    setLoadError(null);
    return getDealerProfile()
      .then((p) => {
        setProfile(p);
        setLoadError(null);
      })
      .catch((err) => {
        setProfile(null);
        setLoadError(apiErrorMessage(err, 'Failed to load profile'));
      })
      .finally(() => setInitialLoad(false));
  }, []);

  useEffect(() => {
    void fetchProfile();
  }, [fetchProfile]);

  const update = (key: keyof DealerProfile, value: string) => {
    setProfile((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profile) return;
    setSaving(true);
    try {
      const next = await updateDealerProfile({
        name: profile.name,
        company_name: profile.company_name || undefined,
        contact_name: profile.contact_name || undefined,
        email: profile.email || undefined,
        phone: profile.phone || undefined,
        address: profile.address || undefined,
        vat_number: profile.vat_number || undefined,
        registration_number: profile.registration_number || undefined,
        website: profile.website || undefined,
      });
      setProfile(next);
      toast.success('Profile saved');
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Failed to save profile'));
    } finally {
      setSaving(false);
    }
  };

  const onLogoChange = async (file: File | null) => {
    if (!file) return;
    setUploading(true);
    try {
      const next = await uploadDealerLogo(file);
      setProfile(next);
      toast.success('Logo uploaded');
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Failed to upload logo'));
    } finally {
      setUploading(false);
    }
  };

  if (initialLoad) {
    return (
      <main className="container mx-auto px-4 py-6 sm:px-6 text-sm text-muted-foreground">
        Loading profile...
      </main>
    );
  }

  if (loadError && !profile) {
    return (
      <main className="container mx-auto px-4 py-6 sm:px-6 space-y-4">
        <p className="text-sm text-destructive">{loadError}</p>
        <Button type="button" variant="outline" onClick={() => void fetchProfile()}>
          Retry
        </Button>
      </main>
    );
  }

  if (!profile) {
    return null;
  }

  return (
    <main className="container mx-auto px-4 py-6 sm:px-6">
      <div className="mx-auto w-full max-w-4xl">
      <Card>
        <CardHeader>
          <CardTitle>Dealer Profile</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSave} className="space-y-5">
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">
                Keep your trading details up to date for quote PDFs and customer-facing documents.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="dealer-name">Dealer name</Label>
                <Input
                  id="dealer-name"
                  value={profile.name || ''}
                  onChange={(e) => update('name', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="dealer-company-name">Company / trading name</Label>
                <Input
                  id="dealer-company-name"
                  value={profile.company_name || ''}
                  onChange={(e) => update('company_name', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="dealer-contact-name">Primary contact name</Label>
                <Input
                  id="dealer-contact-name"
                  value={profile.contact_name || ''}
                  onChange={(e) => update('contact_name', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="dealer-email">Email</Label>
                <Input
                  id="dealer-email"
                  type="email"
                  value={profile.email || ''}
                  onChange={(e) => update('email', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="dealer-phone">Phone</Label>
                <Input
                  id="dealer-phone"
                  value={profile.phone || ''}
                  onChange={(e) => update('phone', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="dealer-website">Website</Label>
                <Input
                  id="dealer-website"
                  value={profile.website || ''}
                  onChange={(e) => update('website', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="dealer-vat-number">VAT number</Label>
                <Input
                  id="dealer-vat-number"
                  value={profile.vat_number || ''}
                  onChange={(e) => update('vat_number', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="dealer-registration-number">Company registration number</Label>
                <Input
                  id="dealer-registration-number"
                  value={profile.registration_number || ''}
                  onChange={(e) => update('registration_number', e.target.value)}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="dealer-address">Address</Label>
                <Textarea
                  id="dealer-address"
                  value={profile.address || ''}
                  onChange={(e) => update('address', e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-3 border-t pt-4">
              <Label htmlFor="dealer-logo">Trader logo</Label>
              <Input
                id="dealer-logo"
                type="file"
                accept="image/*"
                onChange={(e) => onLogoChange(e.target.files?.[0] || null)}
              />
              {profile.logo_url && (
                <div className="flex flex-col gap-3 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={profile.logo_url}
                    alt="Current dealer logo"
                    className="max-h-24 w-full max-w-[220px] object-contain rounded border bg-muted p-1"
                  />
                  <a
                    className="text-sm text-blue-600 underline shrink-0"
                    href={profile.logo_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open full size
                  </a>
                </div>
              )}
              {uploading && <p className="text-sm text-muted-foreground">Uploading logo...</p>}
            </div>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button type="submit" disabled={saving} className="w-full sm:w-auto">
                {saving ? 'Saving...' : 'Save profile'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      </div>
    </main>
  );
}
