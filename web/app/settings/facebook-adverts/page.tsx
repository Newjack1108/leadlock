'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { FacebookAdvertProfile } from '@/lib/types';
import { createFacebookAdvert, listFacebookAdverts, updateFacebookAdvert } from '@/lib/api';
import { toast } from 'sonner';
import { Pencil, Plus, Save } from 'lucide-react';
import ImageUpload from '@/components/ImageUpload';

type FormState = {
  name: string;
  offer_type: string;
  image_url: string;
  is_active: boolean;
};

const emptyForm: FormState = {
  name: '',
  offer_type: '',
  image_url: '',
  is_active: true,
};

export default function FacebookAdvertsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [profiles, setProfiles] = useState<FacebookAdvertProfile[]>([]);
  const [editingProfileId, setEditingProfileId] = useState<number | null>(null);
  const [formData, setFormData] = useState<FormState>(emptyForm);

  useEffect(() => {
    fetchProfiles();
  }, []);

  const fetchProfiles = async () => {
    try {
      setLoading(true);
      const data = await listFacebookAdverts();
      setProfiles(data);
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load Facebook adverts');
      }
    } finally {
      setLoading(false);
    }
  };

  const startCreate = () => {
    setEditingProfileId(null);
    setFormData(emptyForm);
  };

  const startEdit = (profile: FacebookAdvertProfile) => {
    setEditingProfileId(profile.id);
    setFormData({
      name: profile.name,
      offer_type: profile.offer_type || '',
      image_url: profile.image_url || '',
      is_active: profile.is_active,
    });
  };

  const handleSave = async () => {
    if (!formData.name.trim()) {
      toast.error('Advert name is required');
      return;
    }

    try {
      setSaving(true);
      if (editingProfileId) {
        await updateFacebookAdvert(editingProfileId, {
          name: formData.name.trim(),
          offer_type: formData.offer_type.trim() || undefined,
          image_url: formData.image_url.trim() || undefined,
          is_active: formData.is_active,
        });
        toast.success('Facebook advert updated');
      } else {
        await createFacebookAdvert({
          name: formData.name.trim(),
          offer_type: formData.offer_type.trim() || undefined,
          image_url: formData.image_url.trim() || undefined,
          is_active: formData.is_active,
        });
        toast.success('Facebook advert created');
      }
      setFormData(emptyForm);
      setEditingProfileId(null);
      fetchProfiles();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save Facebook advert');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (profile: FacebookAdvertProfile) => {
    try {
      await updateFacebookAdvert(profile.id, { is_active: !profile.is_active });
      toast.success(profile.is_active ? 'Advert archived' : 'Advert reactivated');
      fetchProfiles();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update advert status');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="container mx-auto px-4 sm:px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="container mx-auto px-4 sm:px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold mb-2">Facebook Adverts</h1>
            <p className="text-muted-foreground">
              Create visual advert profiles for lead attribution and sales context.
            </p>
          </div>
          <Button onClick={startCreate} variant="outline">
            <Plus className="h-4 w-4 mr-2" />
            New Advert
          </Button>
        </div>

        <Card className="mb-6">
          <CardHeader>
            <CardTitle>{editingProfileId ? 'Edit advert profile' : 'Create advert profile'}</CardTitle>
            <CardDescription>
              Add the advert name, offer type and image used on Facebook.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="advert_name">Advert name</Label>
              <Input
                id="advert_name"
                value={formData.name}
                onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="Spring Sale Carousel"
                disabled={saving}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="offer_type">Offer type</Label>
              <Input
                id="offer_type"
                value={formData.offer_type}
                onChange={(e) => setFormData((prev) => ({ ...prev, offer_type: e.target.value }))}
                placeholder="10% Off / Free Design Visit / Finance Offer"
                disabled={saving}
              />
            </div>
            <ImageUpload
              label="Advert image (thumbnail)"
              value={formData.image_url}
              onChange={(url) => setFormData((prev) => ({ ...prev, image_url: url }))}
              disabled={saving}
            />
            <div className="flex items-center gap-2">
              <input
                id="is_active"
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) => setFormData((prev) => ({ ...prev, is_active: e.target.checked }))}
                className="rounded"
                disabled={saving}
              />
              <Label htmlFor="is_active">Active</Label>
            </div>
            <div className="flex justify-end">
              <Button onClick={handleSave} disabled={saving || !formData.name.trim()}>
                <Save className="h-4 w-4 mr-2" />
                {saving ? 'Saving...' : editingProfileId ? 'Update advert' : 'Create advert'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {profiles.map((profile) => (
            <Card key={profile.id}>
              <CardHeader>
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-lg">{profile.name}</CardTitle>
                  <Badge variant={profile.is_active ? 'default' : 'secondary'}>
                    {profile.is_active ? 'Active' : 'Archived'}
                  </Badge>
                </div>
                <CardDescription>{profile.offer_type || 'No offer type set'}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {profile.image_url ? (
                  <img
                    src={profile.image_url}
                    alt={profile.name}
                    className="h-24 w-full rounded-md border object-cover"
                  />
                ) : (
                  <div className="h-24 w-full rounded-md border bg-muted/40 flex items-center justify-center text-xs text-muted-foreground">
                    No image
                  </div>
                )}
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => startEdit(profile)} className="flex-1">
                    <Pencil className="h-4 w-4 mr-2" />
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleToggleActive(profile)}
                    className="flex-1"
                  >
                    {profile.is_active ? 'Archive' : 'Activate'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>
    </div>
  );
}
