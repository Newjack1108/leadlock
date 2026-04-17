'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { getDealerProfile, updateDealerProfile, uploadDealerLogo } from '@/lib/api';
import type { DealerProfile } from '@/lib/types';

export default function DealerProfilePage() {
  const [profile, setProfile] = useState<DealerProfile | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    getDealerProfile().then(setProfile).catch(() => setProfile(null));
  }, []);

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
    } finally {
      setUploading(false);
    }
  };

  if (!profile) {
    return <main className="container mx-auto px-4 py-6 sm:px-6 text-sm text-muted-foreground">Loading profile...</main>;
  }

  return (
    <main className="container mx-auto px-4 py-6 sm:px-6">
      <Card>
        <CardHeader>
          <CardTitle>Dealer Profile</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSave} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div><Label>Dealer name</Label><Input value={profile.name || ''} onChange={(e) => update('name', e.target.value)} /></div>
              <div><Label>Company / trading name</Label><Input value={profile.company_name || ''} onChange={(e) => update('company_name', e.target.value)} /></div>
              <div><Label>Primary contact name</Label><Input value={profile.contact_name || ''} onChange={(e) => update('contact_name', e.target.value)} /></div>
              <div><Label>Email</Label><Input type="email" value={profile.email || ''} onChange={(e) => update('email', e.target.value)} /></div>
              <div><Label>Phone</Label><Input value={profile.phone || ''} onChange={(e) => update('phone', e.target.value)} /></div>
              <div><Label>Website</Label><Input value={profile.website || ''} onChange={(e) => update('website', e.target.value)} /></div>
              <div><Label>VAT number</Label><Input value={profile.vat_number || ''} onChange={(e) => update('vat_number', e.target.value)} /></div>
              <div><Label>Company registration number</Label><Input value={profile.registration_number || ''} onChange={(e) => update('registration_number', e.target.value)} /></div>
              <div className="sm:col-span-2"><Label>Address</Label><Textarea value={profile.address || ''} onChange={(e) => update('address', e.target.value)} /></div>
            </div>
            <div className="space-y-2 border-t pt-4">
              <Label htmlFor="dealer-logo">Trader logo</Label>
              <Input id="dealer-logo" type="file" accept="image/*" onChange={(e) => onLogoChange(e.target.files?.[0] || null)} />
              {profile.logo_url && <a className="text-sm text-blue-600 underline" href={profile.logo_url} target="_blank" rel="noreferrer">View current logo</a>}
              {uploading && <p className="text-sm text-muted-foreground">Uploading logo...</p>}
            </div>
            <div className="flex justify-end">
              <Button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save profile'}</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
