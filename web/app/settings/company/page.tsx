'use client';

import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Save, ChevronDown, ChevronUp, Download, Upload, FileSpreadsheet } from 'lucide-react';
import ImageUpload from '@/components/ImageUpload';
import api, {
  downloadCustomerImportExample,
  importCustomersFromCsv,
  downloadCustomerExport,
} from '@/lib/api';
import { CompanySettings, InstallationLeadTime } from '@/lib/types';
import { toast } from 'sonner';

export default function CompanySettingsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<{
    created: number;
    skipped: number;
    errors: Array<{ row: number; message: string }>;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [settings, setSettings] = useState<CompanySettings | null>(null);
  const [termsExpanded, setTermsExpanded] = useState(false);
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
    logo_url: '',
    default_terms_and_conditions: '',
    installation_lead_time: '' as InstallationLeadTime | '',
    hourly_install_rate: '',
    distance_before_overnight_miles: '',
    cost_per_mile: '',
    hotel_allowance_per_night: '',
    meal_allowance_per_day: '',
    average_speed_mph: '',
    product_import_gross_margin_pct: '',
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
        logo_url: response.data.logo_url || '',
        default_terms_and_conditions: response.data.default_terms_and_conditions || '',
        installation_lead_time: response.data.installation_lead_time || '',
        hourly_install_rate: response.data.hourly_install_rate != null ? String(response.data.hourly_install_rate) : '',
        distance_before_overnight_miles: response.data.distance_before_overnight_miles != null ? String(response.data.distance_before_overnight_miles) : '',
        cost_per_mile: response.data.cost_per_mile != null ? String(response.data.cost_per_mile) : '',
        hotel_allowance_per_night: response.data.hotel_allowance_per_night != null ? String(response.data.hotel_allowance_per_night) : '',
        meal_allowance_per_day: response.data.meal_allowance_per_day != null ? String(response.data.meal_allowance_per_day) : '',
        average_speed_mph: response.data.average_speed_mph != null ? String(response.data.average_speed_mph) : '',
        product_import_gross_margin_pct: response.data.product_import_gross_margin_pct != null ? String(response.data.product_import_gross_margin_pct) : '',
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
    const marginVal = formData.product_import_gross_margin_pct ? parseFloat(formData.product_import_gross_margin_pct) : null;
    if (marginVal != null && (marginVal < 0 || marginVal >= 99)) {
      toast.error('Gross margin % must be between 0 and 99');
      return;
    }

    try {
      setSaving(true);
      const payload: Record<string, unknown> = {
        ...formData,
        installation_lead_time: formData.installation_lead_time || undefined,
        hourly_install_rate: formData.hourly_install_rate ? parseFloat(formData.hourly_install_rate) : undefined,
        distance_before_overnight_miles: formData.distance_before_overnight_miles ? parseFloat(formData.distance_before_overnight_miles) : undefined,
        cost_per_mile: formData.cost_per_mile ? parseFloat(formData.cost_per_mile) : undefined,
        hotel_allowance_per_night: formData.hotel_allowance_per_night ? parseFloat(formData.hotel_allowance_per_night) : undefined,
        meal_allowance_per_day: formData.meal_allowance_per_day ? parseFloat(formData.meal_allowance_per_day) : undefined,
        average_speed_mph: formData.average_speed_mph ? parseFloat(formData.average_speed_mph) : undefined,
        product_import_gross_margin_pct: formData.product_import_gross_margin_pct ? parseFloat(formData.product_import_gross_margin_pct) : undefined,
      };
      if (settings) {
        // Update existing: omit logo_filename so existing value is unchanged
        delete payload.logo_filename;
        await api.put('/api/settings/company', payload);
        toast.success('Company settings updated successfully');
      } else {
        // Create new
        await api.post('/api/settings/company', payload);
        toast.success('Company settings created successfully');
      }
      fetchSettings();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save company settings');
    } finally {
      setSaving(false);
    }
  };

  const handleLogoChange = async (url: string) => {
    setFormData((prev) => ({ ...prev, logo_url: url }));
    if (!settings) return;
    try {
      setSaving(true);
      await api.put('/api/settings/company', { logo_url: url || null });
      setSettings((prev) => (prev ? { ...prev, logo_url: url || undefined } : null));
      toast.success(url ? 'Logo saved' : 'Logo removed');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save logo');
    } finally {
      setSaving(false);
    }
  };

  const handleDownloadExample = async () => {
    try {
      await downloadCustomerImportExample();
      toast.success('Example CSV downloaded');
    } catch (error: any) {
      if (error.response?.status !== 401) {
        toast.error(error.response?.data?.detail || 'Failed to download example');
      }
    }
  };

  const handleExport = async () => {
    try {
      await downloadCustomerExport();
      toast.success('Customers exported');
    } catch (error: any) {
      if (error.response?.status !== 401) {
        toast.error(error.response?.data?.detail || 'Failed to export');
      }
    }
  };

  const handleImportFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportResult(null);
    try {
      const result = await importCustomersFromCsv(file);
      setImportResult(result);
      const total = result.created + result.skipped;
      if (result.errors.length > 0) {
        toast.warning(
          `Import complete: ${result.created} created, ${result.skipped} skipped, ${result.errors.length} errors`
        );
      } else {
        toast.success(
          `Import complete: ${result.created} created, ${result.skipped} skipped`
        );
      }
    } catch (error: any) {
      if (error.response?.status !== 401) {
        toast.error(error.response?.data?.detail || 'Failed to import');
      }
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
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

            <ImageUpload
              label="Company logo (for quote PDFs)"
              value={formData.logo_url}
              onChange={handleLogoChange}
              disabled={saving}
            />

            <div className="space-y-2 border-t pt-6">
              <Label>Installation lead time</Label>
              <Select
                value={formData.installation_lead_time || ''}
                onValueChange={(v) => setFormData({ ...formData, installation_lead_time: v ? (v as InstallationLeadTime) : '' })}
                disabled={saving}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select lead time" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={InstallationLeadTime.ONE_TWO_WEEKS}>1–2 weeks</SelectItem>
                  <SelectItem value={InstallationLeadTime.TWO_THREE_WEEKS}>2–3 weeks</SelectItem>
                  <SelectItem value={InstallationLeadTime.THREE_FOUR_WEEKS}>3–4 weeks</SelectItem>
                  <SelectItem value={InstallationLeadTime.FOUR_FIVE_WEEKS}>4–5 weeks</SelectItem>
                  <SelectItem value={InstallationLeadTime.FIVE_SIX_WEEKS}>5–6 weeks</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-sm text-muted-foreground">
                Amended by production. Shown clearly on the dashboard for sales.
              </p>
            </div>

            <div className="space-y-4 border-t pt-6">
              <h3 className="text-lg font-medium">Product import from production</h3>
              <p className="text-sm text-muted-foreground">
                Applied when products are pushed from production. Cost ex VAT × (1 / (1 - margin%)) = RRP. Leave blank to use cost as RRP.
              </p>
              <div className="space-y-2">
                <Label htmlFor="product_import_gross_margin_pct">Gross margin % (RRP mark-up)</Label>
                <Input
                  id="product_import_gross_margin_pct"
                  type="number"
                  step="0.1"
                  min="0"
                  max="99"
                  value={formData.product_import_gross_margin_pct}
                  onChange={(e) => setFormData({ ...formData, product_import_gross_margin_pct: e.target.value })}
                  placeholder="e.g. 30"
                  disabled={saving}
                />
              </div>
            </div>

            <div className="space-y-4 border-t pt-6">
              <h3 className="text-lg font-medium">Installation & travel</h3>
              <p className="text-sm text-muted-foreground">
                Used for delivery & installation estimates (mileage from factory, travel time, 8hr fitting days, overnight threshold). Factory postcode is the company postcode above.
              </p>
              <div className="rounded-md border p-3 bg-muted/30">
                <Label className="text-muted-foreground">Factory postcode (for distance)</Label>
                <p className="font-medium mt-1">{formData.postcode || '—'}</p>
                <p className="text-xs text-muted-foreground mt-1">Set in Company postcode above.</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="distance_before_overnight_miles">Distance before overnight (miles)</Label>
                  <Input
                    id="distance_before_overnight_miles"
                    type="number"
                    step="0.5"
                    min="0"
                    value={formData.distance_before_overnight_miles}
                    onChange={(e) => setFormData({ ...formData, distance_before_overnight_miles: e.target.value })}
                    placeholder="e.g. 60"
                    disabled={saving}
                  />
                  <p className="text-xs text-muted-foreground">Stay away if one-way distance exceeds this.</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="hourly_install_rate">Hourly install rate (£)</Label>
                  <Input
                    id="hourly_install_rate"
                    type="number"
                    step="0.01"
                    min="0"
                    value={formData.hourly_install_rate}
                    onChange={(e) => setFormData({ ...formData, hourly_install_rate: e.target.value })}
                    placeholder="e.g. 45.00"
                    disabled={saving}
                  />
                  <p className="text-xs text-muted-foreground">Used for installation cost calculation.</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cost_per_mile">Cost per mile (£)</Label>
                  <Input
                    id="cost_per_mile"
                    type="number"
                    step="0.01"
                    min="0"
                    value={formData.cost_per_mile}
                    onChange={(e) => setFormData({ ...formData, cost_per_mile: e.target.value })}
                    placeholder="e.g. 0.45"
                    disabled={saving}
                  />
                  <p className="text-xs text-muted-foreground">Applied to return distance.</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="average_speed_mph">Average speed (mph)</Label>
                  <Input
                    id="average_speed_mph"
                    type="number"
                    step="0.1"
                    min="0"
                    value={formData.average_speed_mph}
                    onChange={(e) => setFormData({ ...formData, average_speed_mph: e.target.value })}
                    placeholder="e.g. 45"
                    disabled={saving}
                  />
                  <p className="text-xs text-muted-foreground">Used for travel time (e.g. 45).</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="hotel_allowance_per_night">Hotel allowance per night (£)</Label>
                  <Input
                    id="hotel_allowance_per_night"
                    type="number"
                    step="0.01"
                    min="0"
                    value={formData.hotel_allowance_per_night}
                    onChange={(e) => setFormData({ ...formData, hotel_allowance_per_night: e.target.value })}
                    placeholder="e.g. 80.00"
                    disabled={saving}
                  />
                  <p className="text-xs text-muted-foreground">Per person; ×2 for 2-man team.</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="meal_allowance_per_day">Meal allowance per day (£)</Label>
                  <Input
                    id="meal_allowance_per_day"
                    type="number"
                    step="0.01"
                    min="0"
                    value={formData.meal_allowance_per_day}
                    onChange={(e) => setFormData({ ...formData, meal_allowance_per_day: e.target.value })}
                    placeholder="e.g. 25.00"
                    disabled={saving}
                  />
                  <p className="text-xs text-muted-foreground">Per person when staying away.</p>
                </div>
              </div>
            </div>

            <div className="space-y-2 border-t pt-6">
              <button
                type="button"
                className="flex items-center justify-between w-full text-left font-medium leading-none hover:opacity-80 py-2"
                onClick={() => setTermsExpanded((prev) => !prev)}
              >
                <Label htmlFor="default_terms_and_conditions" className="cursor-pointer">
                  Default Terms and Conditions
                </Label>
                {termsExpanded ? (
                  <ChevronUp className="h-4 w-4 text-muted-foreground shrink-0" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
                )}
              </button>
              {termsExpanded && (
                <>
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
                </>
              )}
            </div>

            <div className="flex justify-end pt-4">
              <Button onClick={handleSave} disabled={saving || !formData.company_name.trim()}>
                <Save className="h-4 w-4 mr-2" />
                {saving ? 'Saving...' : settings ? 'Update Settings' : 'Create Settings'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="mt-8">
          <CardHeader>
            <CardTitle>Customer Data Migration</CardTitle>
            <CardDescription>
              Import customers from your old system or export in the legacy CSV format. Upload file must match the example layout.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownloadExample}
                disabled={importing}
              >
                <FileSpreadsheet className="h-4 w-4 mr-2" />
                Download example CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={importing}
              >
                <Upload className="h-4 w-4 mr-2" />
                Upload CSV
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={handleImportFileChange}
              />
              <Button
                variant="outline"
                size="sm"
                onClick={handleExport}
                disabled={importing}
              >
                <Download className="h-4 w-4 mr-2" />
                Export customers
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Example columns: First Name, Surname, Email, Phone, First of Postcode, Last modified, First of Product Type (Stables, Cabins, Sheds). Download the example to see the format.
            </p>
            {importResult && (
              <div className="rounded-md border p-3 bg-muted/30 text-sm">
                <p className="font-medium">Import result</p>
                <p className="text-muted-foreground mt-1">
                  Created: {importResult.created} · Skipped: {importResult.skipped}
                  {importResult.errors.length > 0 && (
                    <> · Errors: {importResult.errors.length}</>
                  )}
                </p>
                {importResult.errors.length > 0 && importResult.errors.length <= 10 && (
                  <ul className="mt-2 list-disc list-inside text-destructive text-xs">
                    {importResult.errors.map((err, i) => (
                      <li key={i}>Row {err.row}: {err.message}</li>
                    ))}
                  </ul>
                )}
                {importResult.errors.length > 10 && (
                  <ul className="mt-2 list-disc list-inside text-destructive text-xs">
                    {importResult.errors.slice(0, 10).map((err, i) => (
                      <li key={i}>Row {err.row}: {err.message}</li>
                    ))}
                    <li>... and {importResult.errors.length - 10} more</li>
                  </ul>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
