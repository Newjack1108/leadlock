'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Settings, Save } from 'lucide-react';
import api from '@/lib/api';
import { CompanySettings } from '@/lib/types';
import { toast } from 'sonner';

export default function CompanySettingsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState<CompanySettings | null>(null);
  const [formData, setFormData] = useState({
    company_name: '',
    trading_name: '',
    company_registration_number: '',
    vat_number: '',
    address_line1: '',
    address_line2: '',
    city: '',
    county: '',
    postcode: '',
    country: 'United Kingdom',
    phone: '',
    email: '',
    website: '',
    logo_filename: 'logo1.jpg',
    default_terms_and_conditions: '',
  });

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const response = await api.get('/api/settings/company');
      setSettings(response.data);
      setFormData({
        company_name: response.data.company_name || '',
        trading_name: response.data.trading_name || '',
        company_registration_number: response.data.company_registration_number || '',
        vat_number: response.data.vat_number || '',
        address_line1: response.data.address_line1 || '',
        address_line2: response.data.address_line2 || '',
        city: response.data.city || '',
        county: response.data.county || '',
        postcode: response.data.postcode || '',
        country: response.data.country || 'United Kingdom',
        phone: response.data.phone || '',
        email: response.data.email || '',
        website: response.data.website || '',
        logo_filename: response.data.logo_filename || 'logo1.jpg',
        default_terms_and_conditions: response.data.default_terms_and_conditions || '',
      });
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else if (error.response?.status === 404) {
        // Settings don't exist yet, that's okay - user can create them
        setSettings(null);
      } else {
        toast.error('Failed to load company settings');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!formData.company_name.trim()) {
      toast.error('Company name is required');
      return;
    }

    try {
      setSaving(true);
      if (settings) {
        // Update existing
        await api.put('/api/settings/company', formData);
        toast.success('Company settings updated successfully');
      } else {
        // Create new
        await api.post('/api/settings/company', formData);
        toast.success('Company settings created successfully');
      }
      fetchSettings();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save company settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <main className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-semibold mb-2">Company Settings</h1>
          <p className="text-muted-foreground">
            Configure company information for quote PDFs and documents
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Company Information</CardTitle>
            <CardDescription>
              This information will appear on all quote PDFs and documents
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="company_name">
                Company Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="company_name"
                value={formData.company_name}
                onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
                placeholder="Registered company name"
                disabled={saving}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="trading_name">Trading Name</Label>
              <Input
                id="trading_name"
                value={formData.trading_name}
                onChange={(e) => setFormData({ ...formData, trading_name: e.target.value })}
                placeholder="Cheshire Stables"
                disabled={saving}
              />
              <p className="text-xs text-muted-foreground">
                Used on quote headers and branding. Registered name remains in the footer.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="company_registration_number">Company Registration Number</Label>
                <Input
                  id="company_registration_number"
                  value={formData.company_registration_number}
                  onChange={(e) => setFormData({ ...formData, company_registration_number: e.target.value })}
                  placeholder="12345678"
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="vat_number">VAT Number</Label>
                <Input
                  id="vat_number"
                  value={formData.vat_number}
                  onChange={(e) => setFormData({ ...formData, vat_number: e.target.value })}
                  placeholder="GB123456789"
                  disabled={saving}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="address_line1">Address Line 1</Label>
              <Input
                id="address_line1"
                value={formData.address_line1}
                onChange={(e) => setFormData({ ...formData, address_line1: e.target.value })}
                placeholder="123 Stable Road"
                disabled={saving}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="address_line2">Address Line 2</Label>
              <Input
                id="address_line2"
                value={formData.address_line2}
                onChange={(e) => setFormData({ ...formData, address_line2: e.target.value })}
                placeholder="Suite 100"
                disabled={saving}
              />
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="city">City</Label>
                <Input
                  id="city"
                  value={formData.city}
                  onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                  placeholder="Cheshire"
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="county">County</Label>
                <Input
                  id="county"
                  value={formData.county}
                  onChange={(e) => setFormData({ ...formData, county: e.target.value })}
                  placeholder="Cheshire"
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="postcode">Postcode</Label>
                <Input
                  id="postcode"
                  value={formData.postcode}
                  onChange={(e) => setFormData({ ...formData, postcode: e.target.value })}
                  placeholder="CW1 2AB"
                  disabled={saving}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="country">Country</Label>
              <Input
                id="country"
                value={formData.country}
                onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                placeholder="United Kingdom"
                disabled={saving}
              />
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="phone">Phone</Label>
                <Input
                  id="phone"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  placeholder="+44 1234 567890"
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="info@cheshirestables.com"
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="website">Website</Label>
                <Input
                  id="website"
                  value={formData.website}
                  onChange={(e) => setFormData({ ...formData, website: e.target.value })}
                  placeholder="https://cheshirestables.com"
                  disabled={saving}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="logo_filename">Logo Filename</Label>
              <Input
                id="logo_filename"
                value={formData.logo_filename}
                onChange={(e) => setFormData({ ...formData, logo_filename: e.target.value })}
                placeholder="logo1.jpg"
                disabled={saving}
              />
              <p className="text-sm text-muted-foreground">
                Logo file should be placed in <code className="text-xs bg-muted px-1 py-0.5 rounded">web/public/</code> directory
              </p>
            </div>

            <div className="space-y-2 border-t pt-6">
              <Label htmlFor="default_terms_and_conditions">Default Terms and Conditions</Label>
              <Textarea
                id="default_terms_and_conditions"
                value={formData.default_terms_and_conditions}
                onChange={(e) => setFormData({ ...formData, default_terms_and_conditions: e.target.value })}
                placeholder="Enter default terms and conditions that will be pre-filled when creating quotes..."
                rows={12}
                disabled={saving}
                className="font-mono text-sm"
              />
              <p className="text-sm text-muted-foreground">
                These terms will be automatically pre-filled when creating new quotes. Users can still edit them before submitting.
              </p>
            </div>

            <div className="flex justify-end pt-4">
              <Button onClick={handleSave} disabled={saving || !formData.company_name.trim()}>
                <Save className="h-4 w-4 mr-2" />
                {saving ? 'Saving...' : settings ? 'Update Settings' : 'Create Settings'}
              </Button>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
