'use client';

import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
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
  getSmsTemplates,
  getEmailTemplates,
} from '@/lib/api';
import { CompanySettings, EmailTemplate, InstallationLeadTime, SmsBotMode, SmsTemplate } from '@/lib/types';
import { toast } from 'sonner';

type WeekdayKey = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun';
type BotDaySchedule = { enabled: boolean; start: string; end: string };
type BotWeekSchedule = Record<WeekdayKey, BotDaySchedule>;
const WEEKDAYS: Array<{ key: WeekdayKey; label: string }> = [
  { key: 'mon', label: 'Monday' },
  { key: 'tue', label: 'Tuesday' },
  { key: 'wed', label: 'Wednesday' },
  { key: 'thu', label: 'Thursday' },
  { key: 'fri', label: 'Friday' },
  { key: 'sat', label: 'Saturday' },
  { key: 'sun', label: 'Sunday' },
];

const INSTALLATION_LEAD_TIME_OPTIONS: Array<{ value: InstallationLeadTime; label: string }> = [
  { value: InstallationLeadTime.ONE_TWO_WEEKS, label: '1–2 weeks' },
  { value: InstallationLeadTime.TWO_THREE_WEEKS, label: '2–3 weeks' },
  { value: InstallationLeadTime.THREE_FOUR_WEEKS, label: '3–4 weeks' },
  { value: InstallationLeadTime.FOUR_FIVE_WEEKS, label: '4–5 weeks' },
  { value: InstallationLeadTime.FIVE_SIX_WEEKS, label: '5–6 weeks' },
];

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
  const [smsTemplates, setSmsTemplates] = useState<SmsTemplate[]>([]);
  const [emailTemplates, setEmailTemplates] = useState<EmailTemplate[]>([]);
  const [reviewExpanded, setReviewExpanded] = useState(false);
  const [botAvatarMissing, setBotAvatarMissing] = useState(false);
  const [termsExpanded, setTermsExpanded] = useState(false);
  const [smsBotInstructionsExpanded, setSmsBotInstructionsExpanded] = useState(false);
  const defaultBotHours: BotWeekSchedule = {
    mon: { enabled: true, start: '09:00', end: '17:00' },
    tue: { enabled: true, start: '09:00', end: '17:00' },
    wed: { enabled: true, start: '09:00', end: '17:00' },
    thu: { enabled: true, start: '09:00', end: '17:00' },
    fri: { enabled: true, start: '09:00', end: '17:00' },
    sat: { enabled: false, start: '09:00', end: '17:00' },
    sun: { enabled: false, start: '09:00', end: '17:00' },
  };
  const [botSchedule, setBotSchedule] = useState<BotWeekSchedule>(defaultBotHours);
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
    footer_logo_url: '',
    default_terms_and_conditions: '',
    email_disclaimer: '',
    default_email_signature: '',
    installation_lead_time_stables: '' as InstallationLeadTime | '',
    installation_lead_time_sheds: '' as InstallationLeadTime | '',
    installation_lead_time_cabins: '' as InstallationLeadTime | '',
    hourly_install_rate: '',
    distance_before_overnight_miles: '',
    cost_per_mile: '',
    hotel_allowance_per_night: '',
    meal_allowance_per_day: '',
    average_speed_mph: '',
    install_quote_margin_pct: '30',
    product_import_gross_margin_pct: '',
    sms_bot_mode: SmsBotMode.OFF as SmsBotMode,
    sms_bot_timezone: 'Europe/London',
    sms_bot_business_hours_json: JSON.stringify(defaultBotHours),
    sms_bot_fallback_message: 'Thanks for your message. Our team is currently out of hours and will reply as soon as we are back.',
    sms_bot_max_replies_per_thread: '3',
    sms_bot_pause_minutes_after_handover: '720',
    sms_bot_system_instructions: '',
    bank_name: '',
    bank_account_name: '',
    account_number: '',
    sort_code: '',
    require_engagement_proof: false,
    duplicate_sms_template_id: '' as string,
    duplicate_sms_cooldown_days: '7',
    auto_close_duplicate_leads: true,
    review_request_delay_days: '3',
    review_google_url: '',
    review_facebook_url: '',
    review_trustpilot_url: '',
    review_request_customer_outreach_enabled: false,
    review_request_sms_template_id: '' as string,
    review_request_email_template_id: '' as string,
  });

  useEffect(() => {
    fetchSettings();
    void (async () => {
      try {
        const [sms, email] = await Promise.all([getSmsTemplates(), getEmailTemplates()]);
        setSmsTemplates(sms);
        setEmailTemplates(email);
      } catch {
        // Non-blocking; template sections still usable after templates load on retry
      }
    })();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const response = await api.get('/api/settings/company');
      setSettings(response.data);
      let parsedSchedule = defaultBotHours;
      try {
        const loaded = JSON.parse(response.data.sms_bot_business_hours_json || '{}');
        parsedSchedule = { ...defaultBotHours, ...loaded };
      } catch {
        parsedSchedule = defaultBotHours;
      }
      setBotSchedule(parsedSchedule);
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
        footer_logo_url: response.data.footer_logo_url || '',
        default_terms_and_conditions: response.data.default_terms_and_conditions || '',
        email_disclaimer: response.data.email_disclaimer || '',
        default_email_signature: response.data.default_email_signature || '',
        installation_lead_time_stables:
          response.data.installation_lead_time_stables ||
          response.data.installation_lead_time ||
          '',
        installation_lead_time_sheds:
          response.data.installation_lead_time_sheds ||
          response.data.installation_lead_time ||
          '',
        installation_lead_time_cabins:
          response.data.installation_lead_time_cabins ||
          response.data.installation_lead_time ||
          '',
        hourly_install_rate: response.data.hourly_install_rate != null ? String(response.data.hourly_install_rate) : '',
        distance_before_overnight_miles: response.data.distance_before_overnight_miles != null ? String(response.data.distance_before_overnight_miles) : '',
        cost_per_mile: response.data.cost_per_mile != null ? String(response.data.cost_per_mile) : '',
        hotel_allowance_per_night: response.data.hotel_allowance_per_night != null ? String(response.data.hotel_allowance_per_night) : '',
        meal_allowance_per_day: response.data.meal_allowance_per_day != null ? String(response.data.meal_allowance_per_day) : '',
        average_speed_mph: response.data.average_speed_mph != null ? String(response.data.average_speed_mph) : '',
        install_quote_margin_pct: response.data.install_quote_margin_pct != null ? String(response.data.install_quote_margin_pct) : '30',
        product_import_gross_margin_pct: response.data.product_import_gross_margin_pct != null ? String(response.data.product_import_gross_margin_pct) : '',
        sms_bot_mode: response.data.sms_bot_mode || SmsBotMode.OFF,
        sms_bot_timezone: response.data.sms_bot_timezone || 'Europe/London',
        sms_bot_business_hours_json: response.data.sms_bot_business_hours_json || JSON.stringify(parsedSchedule),
        sms_bot_fallback_message: response.data.sms_bot_fallback_message || 'Thanks for your message. Our team is currently out of hours and will reply as soon as we are back.',
        sms_bot_max_replies_per_thread: response.data.sms_bot_max_replies_per_thread != null ? String(response.data.sms_bot_max_replies_per_thread) : '3',
        sms_bot_pause_minutes_after_handover: response.data.sms_bot_pause_minutes_after_handover != null ? String(response.data.sms_bot_pause_minutes_after_handover) : '720',
        sms_bot_system_instructions: response.data.sms_bot_system_instructions ?? '',
        bank_name: response.data.bank_name || '',
        bank_account_name: response.data.bank_account_name || '',
        account_number: response.data.account_number || '',
        sort_code: response.data.sort_code || '',
        require_engagement_proof: response.data.require_engagement_proof ?? false,
        duplicate_sms_template_id:
          response.data.duplicate_sms_template_id != null
            ? String(response.data.duplicate_sms_template_id)
            : '',
        duplicate_sms_cooldown_days:
          response.data.duplicate_sms_cooldown_days != null
            ? String(response.data.duplicate_sms_cooldown_days)
            : '7',
        auto_close_duplicate_leads: response.data.auto_close_duplicate_leads ?? true,
        review_request_delay_days:
          response.data.review_request_delay_days != null
            ? String(response.data.review_request_delay_days)
            : '3',
        review_google_url: response.data.review_google_url || '',
        review_facebook_url: response.data.review_facebook_url || '',
        review_trustpilot_url: response.data.review_trustpilot_url || '',
        review_request_customer_outreach_enabled:
          response.data.review_request_customer_outreach_enabled ?? false,
        review_request_sms_template_id:
          response.data.review_request_sms_template_id != null
            ? String(response.data.review_request_sms_template_id)
            : '',
        review_request_email_template_id:
          response.data.review_request_email_template_id != null
            ? String(response.data.review_request_email_template_id)
            : '',
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
    const productMarginVal = formData.product_import_gross_margin_pct ? parseFloat(formData.product_import_gross_margin_pct) : null;
    if (productMarginVal != null && (productMarginVal < 0 || productMarginVal >= 99)) {
      toast.error('Product gross margin % must be between 0 and 99');
      return;
    }
    const installMarginVal = formData.install_quote_margin_pct ? parseFloat(formData.install_quote_margin_pct) : null;
    if (installMarginVal != null && (installMarginVal < 0 || installMarginVal >= 99)) {
      toast.error('Install quote margin % must be between 0 and 99');
      return;
    }
    const duplicateCooldownVal = formData.duplicate_sms_cooldown_days
      ? parseInt(formData.duplicate_sms_cooldown_days, 10)
      : 7;
    if (Number.isNaN(duplicateCooldownVal) || duplicateCooldownVal < 0) {
      toast.error('Duplicate SMS cooldown must be 0 or more days');
      return;
    }
    const reviewDelayVal = formData.review_request_delay_days
      ? parseInt(formData.review_request_delay_days, 10)
      : 3;
    if (Number.isNaN(reviewDelayVal) || reviewDelayVal < 0) {
      toast.error('Review request delay must be 0 or more days');
      return;
    }

    try {
      setSaving(true);
      const payload: Record<string, unknown> = {
        ...formData,
        installation_lead_time_stables: formData.installation_lead_time_stables || undefined,
        installation_lead_time_sheds: formData.installation_lead_time_sheds || undefined,
        installation_lead_time_cabins: formData.installation_lead_time_cabins || undefined,
        hourly_install_rate: formData.hourly_install_rate ? parseFloat(formData.hourly_install_rate) : undefined,
        distance_before_overnight_miles: formData.distance_before_overnight_miles ? parseFloat(formData.distance_before_overnight_miles) : undefined,
        cost_per_mile: formData.cost_per_mile ? parseFloat(formData.cost_per_mile) : undefined,
        hotel_allowance_per_night: formData.hotel_allowance_per_night ? parseFloat(formData.hotel_allowance_per_night) : undefined,
        meal_allowance_per_day: formData.meal_allowance_per_day ? parseFloat(formData.meal_allowance_per_day) : undefined,
        average_speed_mph: formData.average_speed_mph ? parseFloat(formData.average_speed_mph) : undefined,
        install_quote_margin_pct: formData.install_quote_margin_pct ? parseFloat(formData.install_quote_margin_pct) : undefined,
        product_import_gross_margin_pct: formData.product_import_gross_margin_pct ? parseFloat(formData.product_import_gross_margin_pct) : undefined,
        sms_bot_max_replies_per_thread: formData.sms_bot_max_replies_per_thread ? parseInt(formData.sms_bot_max_replies_per_thread, 10) : undefined,
        sms_bot_pause_minutes_after_handover: formData.sms_bot_pause_minutes_after_handover ? parseInt(formData.sms_bot_pause_minutes_after_handover, 10) : undefined,
        sms_bot_business_hours_json: JSON.stringify(botSchedule),
        sms_bot_system_instructions:
          formData.sms_bot_system_instructions.trim() === '' ? null : formData.sms_bot_system_instructions.trim(),
        duplicate_sms_template_id:
          formData.duplicate_sms_template_id.trim() === ''
            ? null
            : parseInt(formData.duplicate_sms_template_id, 10),
        duplicate_sms_cooldown_days: duplicateCooldownVal,
        auto_close_duplicate_leads: formData.auto_close_duplicate_leads,
        review_request_delay_days: reviewDelayVal,
        review_google_url: formData.review_google_url.trim() || null,
        review_facebook_url: formData.review_facebook_url.trim() || null,
        review_trustpilot_url: formData.review_trustpilot_url.trim() || null,
        review_request_customer_outreach_enabled: formData.review_request_customer_outreach_enabled,
        review_request_sms_template_id:
          formData.review_request_sms_template_id.trim() === ''
            ? null
            : parseInt(formData.review_request_sms_template_id, 10),
        review_request_email_template_id:
          formData.review_request_email_template_id.trim() === ''
            ? null
            : parseInt(formData.review_request_email_template_id, 10),
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
      toast.success(url ? 'Header logo saved' : 'Header logo removed');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save logo');
    } finally {
      setSaving(false);
    }
  };

  const handleFooterLogoChange = async (url: string) => {
    setFormData((prev) => ({ ...prev, footer_logo_url: url }));
    if (!settings) return;
    try {
      setSaving(true);
      await api.put('/api/settings/company', { footer_logo_url: url || null });
      setSettings((prev) => (prev ? { ...prev, footer_logo_url: url || undefined } : null));
      toast.success(url ? 'Footer logo saved' : 'Footer logo removed');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save footer logo');
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
            <div className="rounded-lg p-4 bg-blue-50/30 dark:bg-blue-950/20 border-l-4 border-l-blue-200 dark:border-l-blue-800 space-y-4">
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

            </div>

            <div className="rounded-lg p-4 bg-sky-50/30 dark:bg-sky-950/20 border-l-4 border-l-sky-200 dark:border-l-sky-800 mt-6 space-y-4">
              <div>
                <h3 className="text-lg font-medium">Duplicate lead handling</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  When someone submits another enquiry (e.g. Cheshire Stables and CSGB), link it to their existing lead,
                  send a repeat SMS instead of the welcome message, and optionally close the duplicate for your team.
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="duplicate_sms_template_id">Repeat enquiry SMS template</Label>
                  <Select
                    value={formData.duplicate_sms_template_id || 'none'}
                    onValueChange={(v) =>
                      setFormData({
                        ...formData,
                        duplicate_sms_template_id: v === 'none' ? '' : v,
                      })
                    }
                    disabled={saving}
                  >
                    <SelectTrigger id="duplicate_sms_template_id">
                      <SelectValue placeholder="Choose template" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">None (no repeat SMS)</SelectItem>
                      {smsTemplates.map((t) => (
                        <SelectItem key={t.id} value={String(t.id)}>
                          {t.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    Sent instead of the welcome SMS when a duplicate is detected. Fallback name:{' '}
                    <span className="font-medium">Duplicate Lead Notice</span>.{' '}
                    <Link href="/settings/sms-templates" className="text-primary underline hover:no-underline">
                      Manage SMS templates
                    </Link>
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="duplicate_sms_cooldown_days">Repeat SMS cooldown (days)</Label>
                  <Input
                    id="duplicate_sms_cooldown_days"
                    type="number"
                    min="0"
                    step="1"
                    value={formData.duplicate_sms_cooldown_days}
                    onChange={(e) =>
                      setFormData({ ...formData, duplicate_sms_cooldown_days: e.target.value })
                    }
                    disabled={saving}
                  />
                  <p className="text-xs text-muted-foreground">
                    Minimum days before sending another repeat SMS to the same customer on a new duplicate lead.
                  </p>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="auto_close_duplicate_leads"
                  checked={formData.auto_close_duplicate_leads}
                  onChange={(e) =>
                    setFormData({ ...formData, auto_close_duplicate_leads: e.target.checked })
                  }
                  className="rounded"
                  disabled={saving}
                />
                <Label htmlFor="auto_close_duplicate_leads">
                  Automatically close duplicate leads (keeps them for source reporting)
                </Label>
              </div>
            </div>

            <div className="rounded-lg p-4 bg-teal-50/30 dark:bg-teal-950/20 border-l-4 border-l-teal-200 dark:border-l-teal-800 mt-6 space-y-4">
              <button
                type="button"
                className="flex w-full items-center justify-between text-left"
                onClick={() => setReviewExpanded((v) => !v)}
              >
                <div>
                  <h3 className="text-lg font-medium">Post-install review requests</h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    After staff mark installation complete, create a staff reminder and optionally send customers
                    Google, Facebook, and Trustpilot review links.
                  </p>
                </div>
                {reviewExpanded ? <ChevronUp className="h-5 w-5 shrink-0" /> : <ChevronDown className="h-5 w-5 shrink-0" />}
              </button>
              {reviewExpanded && (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="review_request_delay_days">Delay after install complete (days)</Label>
                      <Input
                        id="review_request_delay_days"
                        type="number"
                        min="0"
                        step="1"
                        value={formData.review_request_delay_days}
                        onChange={(e) =>
                          setFormData({ ...formData, review_request_delay_days: e.target.value })
                        }
                        disabled={saving}
                      />
                    </div>
                    <div className="flex items-center space-x-2 pt-8">
                      <input
                        type="checkbox"
                        id="review_request_customer_outreach_enabled"
                        checked={formData.review_request_customer_outreach_enabled}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            review_request_customer_outreach_enabled: e.target.checked,
                          })
                        }
                        className="rounded"
                        disabled={saving}
                      />
                      <Label htmlFor="review_request_customer_outreach_enabled">
                        Automatically send review request to customer (SMS preferred, else email)
                      </Label>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="review_google_url">Google review URL</Label>
                      <Input
                        id="review_google_url"
                        type="url"
                        value={formData.review_google_url}
                        onChange={(e) => setFormData({ ...formData, review_google_url: e.target.value })}
                        disabled={saving}
                        placeholder="https://..."
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="review_facebook_url">Facebook review URL</Label>
                      <Input
                        id="review_facebook_url"
                        type="url"
                        value={formData.review_facebook_url}
                        onChange={(e) => setFormData({ ...formData, review_facebook_url: e.target.value })}
                        disabled={saving}
                        placeholder="https://..."
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="review_trustpilot_url">Trustpilot review URL</Label>
                      <Input
                        id="review_trustpilot_url"
                        type="url"
                        value={formData.review_trustpilot_url}
                        onChange={(e) => setFormData({ ...formData, review_trustpilot_url: e.target.value })}
                        disabled={saving}
                        placeholder="https://..."
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="review_request_sms_template_id">Review request SMS template</Label>
                      <Select
                        value={formData.review_request_sms_template_id || 'none'}
                        onValueChange={(v) =>
                          setFormData({
                            ...formData,
                            review_request_sms_template_id: v === 'none' ? '' : v,
                          })
                        }
                        disabled={saving}
                      >
                        <SelectTrigger id="review_request_sms_template_id">
                          <SelectValue placeholder="Choose template" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">None</SelectItem>
                          {smsTemplates.map((t) => (
                            <SelectItem key={t.id} value={String(t.id)}>
                              {t.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        Variables: <code className="text-xs">{'{{ review.google_url }}'}</code>,{' '}
                        <code className="text-xs">{'{{ review.facebook_url }}'}</code>,{' '}
                        <code className="text-xs">{'{{ review.trustpilot_url }}'}</code>.{' '}
                        <Link href="/settings/sms-templates" className="text-primary underline hover:no-underline">
                          Manage SMS templates
                        </Link>
                      </p>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="review_request_email_template_id">Review request email template</Label>
                      <Select
                        value={formData.review_request_email_template_id || 'none'}
                        onValueChange={(v) =>
                          setFormData({
                            ...formData,
                            review_request_email_template_id: v === 'none' ? '' : v,
                          })
                        }
                        disabled={saving}
                      >
                        <SelectTrigger id="review_request_email_template_id">
                          <SelectValue placeholder="Choose template" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">None</SelectItem>
                          {emailTemplates.map((t) => (
                            <SelectItem key={t.id} value={String(t.id)}>
                              {t.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        Used when no SMS template is set.{' '}
                        <Link href="/settings/email-templates" className="text-primary underline hover:no-underline">
                          Manage email templates
                        </Link>
                      </p>
                    </div>
                  </div>
                </>
              )}
            </div>

            <div className="rounded-lg p-4 bg-amber-50/30 dark:bg-amber-950/20 border-l-4 border-l-amber-200 dark:border-l-amber-800 mt-6">
              <h3 className="text-lg font-medium">Quote requirements</h3>
              <p className="text-sm text-muted-foreground mt-1">
                When enabled, customers must have at least one engagement activity (SMS, email, WhatsApp, or live call) before a quote can be sent.
              </p>
              <div className="flex items-center space-x-2 mt-3">
                <input
                  type="checkbox"
                  id="require_engagement_proof"
                  checked={formData.require_engagement_proof}
                  onChange={(e) => setFormData({ ...formData, require_engagement_proof: e.target.checked })}
                  className="rounded"
                  disabled={saving}
                />
                <Label htmlFor="require_engagement_proof">Require engagement proof before quoting</Label>
              </div>
            </div>

            <div className="rounded-lg p-4 bg-emerald-50/30 dark:bg-emerald-950/20 border-l-4 border-l-emerald-200 dark:border-l-emerald-800 mt-6">
              <h3 className="text-lg font-medium">Bank details</h3>
              <p className="text-sm text-muted-foreground">
                Shown on quote and invoice PDFs for payment instructions.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="bank_name">Bank Name</Label>
                  <Input
                    id="bank_name"
                    value={formData.bank_name}
                    onChange={(e) => setFormData({ ...formData, bank_name: e.target.value })}
                    placeholder="e.g. Barclays"
                    disabled={saving}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bank_account_name">Account Name</Label>
                  <Input
                    id="bank_account_name"
                    value={formData.bank_account_name}
                    onChange={(e) => setFormData({ ...formData, bank_account_name: e.target.value })}
                    placeholder="e.g. Cheshire Stables Ltd"
                    disabled={saving}
                  />
                  <p className="text-xs text-muted-foreground">Name on the account for BACS payments</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="account_number">Account Number</Label>
                  <Input
                    id="account_number"
                    value={formData.account_number}
                    onChange={(e) => setFormData({ ...formData, account_number: e.target.value })}
                    placeholder="e.g. 12345678"
                    disabled={saving}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sort_code">Sort Code</Label>
                  <Input
                    id="sort_code"
                    value={formData.sort_code}
                    onChange={(e) => setFormData({ ...formData, sort_code: e.target.value })}
                    placeholder="e.g. 12-34-56"
                    disabled={saving}
                  />
                </div>
              </div>
            </div>

            <div className="rounded-lg p-4 bg-slate-50/30 dark:bg-slate-950/20 border-l-4 border-l-slate-200 dark:border-l-slate-800 mt-6 space-y-4">
              <h3 className="text-lg font-medium">Contact & branding</h3>
              <p className="text-sm text-muted-foreground">
                Contact details and logos used on quotes and invoices.
              </p>
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
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <ImageUpload
                  label="Header logo (quote/invoice PDFs)"
                  value={formData.logo_url}
                  onChange={handleLogoChange}
                  disabled={saving}
                />
                <ImageUpload
                  label="Footer logo (PDF footer)"
                  value={formData.footer_logo_url}
                  onChange={handleFooterLogoChange}
                  disabled={saving}
                />
              </div>
            </div>

            <div className="rounded-lg p-4 bg-violet-50/30 dark:bg-violet-950/20 border-l-4 border-l-violet-200 dark:border-l-violet-800 mt-6 space-y-4">
              <h3 className="text-lg font-medium">Installation lead time by product type</h3>
              <p className="text-sm text-muted-foreground">
                Amended by production. Shown on the dashboard for sales. Quotes use the time for the lead line (or product categories on the quote).
              </p>
              <div className="grid gap-4 sm:grid-cols-3">
                {(
                  [
                    { key: 'installation_lead_time_stables' as const, label: 'Stables' },
                    { key: 'installation_lead_time_sheds' as const, label: 'Sheds' },
                    { key: 'installation_lead_time_cabins' as const, label: 'Cabins' },
                  ] as const
                ).map(({ key, label }) => (
                  <div key={key} className="space-y-2">
                    <Label>{label}</Label>
                    <Select
                      value={formData[key] || ''}
                      onValueChange={(v) =>
                        setFormData({
                          ...formData,
                          [key]: v ? (v as InstallationLeadTime) : '',
                        })
                      }
                      disabled={saving}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select lead time" />
                      </SelectTrigger>
                      <SelectContent>
                        {INSTALLATION_LEAD_TIME_OPTIONS.map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-lg p-4 bg-indigo-50/30 dark:bg-indigo-950/20 border-l-4 border-l-indigo-200 dark:border-l-indigo-800 mt-6 space-y-4">
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

            <div className="rounded-xl border border-rose-200/70 bg-gradient-to-br from-rose-50 via-rose-50/70 to-white p-5 shadow-sm dark:border-rose-900/80 dark:from-rose-950/20 dark:via-rose-950/10 dark:to-background mt-6 space-y-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-3">
                  {botAvatarMissing ? (
                    <div className="flex h-12 w-12 items-center justify-center rounded-full border border-rose-200 bg-white text-xs font-semibold text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-200">
                      BOT
                    </div>
                  ) : (
                    <img
                      src="/chat-bot.png"
                      alt="SMS bot profile"
                      className="h-12 w-12 rounded-full border border-rose-200 object-cover shadow-sm dark:border-rose-800"
                      onError={() => setBotAvatarMissing(true)}
                    />
                  )}
                  <div>
                    <h3 className="text-lg font-semibold">Out-of-hours SMS bot</h3>
                    <p className="text-sm text-muted-foreground">
                      Configure automated SMS replies for out-of-hours support using Twilio + AI assistant.
                    </p>
                  </div>
                </div>
                <div className="inline-flex items-center rounded-full border border-rose-200 bg-white px-3 py-1.5 text-xs font-semibold shadow-sm dark:border-rose-800 dark:bg-rose-950/40">
                  {formData.sms_bot_mode === SmsBotMode.ON
                    ? 'Live now (manual ON)'
                    : formData.sms_bot_mode === SmsBotMode.AUTO
                      ? 'Auto schedule mode'
                      : 'Bot currently OFF'}
                </div>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <button
                  type="button"
                  className={`rounded-lg border p-3 text-left transition ${
                    formData.sms_bot_mode === SmsBotMode.OFF
                      ? 'border-slate-900 bg-slate-900 text-white shadow-md dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900'
                      : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-background'
                  }`}
                  onClick={() => setFormData({ ...formData, sms_bot_mode: SmsBotMode.OFF })}
                  disabled={saving}
                >
                  <p className="text-sm font-semibold">Bot Off</p>
                  <p className={`mt-1 text-xs ${formData.sms_bot_mode === SmsBotMode.OFF ? 'text-slate-100/90 dark:text-slate-800' : 'text-muted-foreground'}`}>
                    Disable all automatic replies.
                  </p>
                </button>
                <button
                  type="button"
                  className={`rounded-lg border p-3 text-left transition ${
                    formData.sms_bot_mode === SmsBotMode.AUTO
                      ? 'border-amber-500 bg-amber-500 text-white shadow-md dark:border-amber-400 dark:bg-amber-400 dark:text-amber-950'
                      : 'border-amber-200 bg-amber-50/40 hover:border-amber-300 dark:border-amber-900 dark:bg-amber-950/20'
                  }`}
                  onClick={() => setFormData({ ...formData, sms_bot_mode: SmsBotMode.AUTO })}
                  disabled={saving}
                >
                  <p className="text-sm font-semibold">Bot Auto</p>
                  <p className={`mt-1 text-xs ${formData.sms_bot_mode === SmsBotMode.AUTO ? 'text-amber-50 dark:text-amber-950/90' : 'text-muted-foreground'}`}>
                    Follow business hours schedule.
                  </p>
                </button>
                <button
                  type="button"
                  className={`rounded-lg border p-3 text-left transition ${
                    formData.sms_bot_mode === SmsBotMode.ON
                      ? 'border-emerald-600 bg-emerald-600 text-white shadow-md dark:border-emerald-500 dark:bg-emerald-500 dark:text-emerald-950'
                      : 'border-emerald-200 bg-emerald-50/50 hover:border-emerald-300 dark:border-emerald-900 dark:bg-emerald-950/20'
                  }`}
                  onClick={() => setFormData({ ...formData, sms_bot_mode: SmsBotMode.ON })}
                  disabled={saving}
                >
                  <p className="text-sm font-semibold">Bot On</p>
                  <p className={`mt-1 text-xs ${formData.sms_bot_mode === SmsBotMode.ON ? 'text-emerald-50 dark:text-emerald-950/90' : 'text-muted-foreground'}`}>
                    Reply at all times (manual override).
                  </p>
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="sms_bot_timezone">Timezone</Label>
                  <Input
                    id="sms_bot_timezone"
                    value={formData.sms_bot_timezone}
                    onChange={(e) => setFormData({ ...formData, sms_bot_timezone: e.target.value })}
                    placeholder="Europe/London"
                    disabled={saving}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sms_bot_max_replies_per_thread">Max replies per thread</Label>
                  <Input
                    id="sms_bot_max_replies_per_thread"
                    type="number"
                    min="1"
                    step="1"
                    value={formData.sms_bot_max_replies_per_thread}
                    onChange={(e) => setFormData({ ...formData, sms_bot_max_replies_per_thread: e.target.value })}
                    disabled={saving}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sms_bot_pause_minutes_after_handover">Pause after handover (minutes)</Label>
                  <Input
                    id="sms_bot_pause_minutes_after_handover"
                    type="number"
                    min="0"
                    step="1"
                    value={formData.sms_bot_pause_minutes_after_handover}
                    onChange={(e) => setFormData({ ...formData, sms_bot_pause_minutes_after_handover: e.target.value })}
                    disabled={saving}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="sms_bot_fallback_message">Fallback message</Label>
                <Textarea
                  id="sms_bot_fallback_message"
                  value={formData.sms_bot_fallback_message}
                  onChange={(e) => setFormData({ ...formData, sms_bot_fallback_message: e.target.value })}
                  rows={3}
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <button
                  type="button"
                  className="flex items-center justify-between w-full text-left font-medium leading-none hover:opacity-80 py-2 rounded-md -mx-1 px-1"
                  onClick={() => setSmsBotInstructionsExpanded((prev) => !prev)}
                >
                  <Label htmlFor="sms_bot_system_instructions" className="cursor-pointer">
                    SMS bot system instructions
                  </Label>
                  {smsBotInstructionsExpanded ? (
                    <ChevronUp className="h-4 w-4 text-muted-foreground shrink-0" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
                  )}
                </button>
                {smsBotInstructionsExpanded && (
                  <>
                    <Textarea
                      id="sms_bot_system_instructions"
                      value={formData.sms_bot_system_instructions}
                      onChange={(e) => setFormData({ ...formData, sms_bot_system_instructions: e.target.value })}
                      rows={6}
                      disabled={saving}
                      placeholder="e.g. what you sell, tone, topics to hand off to a human…"
                    />
                    <p className="text-sm text-muted-foreground">
                      Optional. When set, this is appended to the AI system prompt after built-in rules. Company name (trading
                      name if set), phone, and website from this page are included automatically when filled in. Keep it
                      concise. The bot still limits reply length and escalates pricing, complaints, and complex questions.
                    </p>
                  </>
                )}
              </div>
              <div className="space-y-2">
                <Label>Business hours by weekday (AUTO mode)</Label>
                <div className="space-y-2 rounded-md border p-3 bg-muted/20">
                  {WEEKDAYS.map((day) => (
                    <div key={day.key} className="grid grid-cols-1 md:grid-cols-4 gap-2 items-center">
                      <div className="font-medium text-sm">{day.label}</div>
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={botSchedule[day.key].enabled}
                          onChange={(e) =>
                            setBotSchedule((prev) => ({
                              ...prev,
                              [day.key]: { ...prev[day.key], enabled: e.target.checked },
                            }))
                          }
                          disabled={saving}
                        />
                        Open
                      </label>
                      <Input
                        type="time"
                        value={botSchedule[day.key].start}
                        onChange={(e) =>
                          setBotSchedule((prev) => ({
                            ...prev,
                            [day.key]: { ...prev[day.key], start: e.target.value },
                          }))
                        }
                        disabled={saving || !botSchedule[day.key].enabled}
                      />
                      <Input
                        type="time"
                        value={botSchedule[day.key].end}
                        onChange={(e) =>
                          setBotSchedule((prev) => ({
                            ...prev,
                            [day.key]: { ...prev[day.key], end: e.target.value },
                          }))
                        }
                        disabled={saving || !botSchedule[day.key].enabled}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="rounded-lg p-4 bg-teal-50/30 dark:bg-teal-950/20 border-l-4 border-l-teal-200 dark:border-l-teal-800 mt-6 space-y-4">
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
                  <Label htmlFor="install_quote_margin_pct">Install quote margin %</Label>
                  <Input
                    id="install_quote_margin_pct"
                    type="number"
                    step="0.1"
                    min="0"
                    max="99"
                    value={formData.install_quote_margin_pct}
                    onChange={(e) => setFormData({ ...formData, install_quote_margin_pct: e.target.value })}
                    placeholder="e.g. 30"
                    disabled={saving}
                  />
                  <p className="text-xs text-muted-foreground">Margin added to delivery &amp; installation cost (0–99). Default 30%.</p>
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

            <div className="rounded-lg p-4 bg-stone-50/30 dark:bg-stone-950/20 border-l-4 border-l-stone-200 dark:border-l-stone-800 mt-6 space-y-2">
              <h3 className="text-lg font-medium">Terms and Conditions</h3>
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

            <div className="rounded-lg p-4 bg-zinc-50/30 dark:bg-zinc-950/20 border-l-4 border-l-zinc-200 dark:border-l-zinc-800 mt-6 space-y-2">
              <h3 className="text-lg font-medium">Default email signature (system sends)</h3>
              <Label htmlFor="default_email_signature">Default email signature</Label>
              <Textarea
                id="default_email_signature"
                value={formData.default_email_signature}
                onChange={(e) => setFormData({ ...formData, default_email_signature: e.target.value })}
                placeholder="HTML signature used only when email is sent without a logged-in user (e.g. future automations). Normal sends use each user’s signature from My Settings."
                rows={5}
                disabled={saving}
                className="font-mono text-sm"
              />
              <p className="text-sm text-muted-foreground">
                Per-user signatures in My Settings take precedence for compose, replies, and quote emails.
              </p>
            </div>

            <div className="rounded-lg p-4 bg-zinc-50/30 dark:bg-zinc-950/20 border-l-4 border-l-zinc-200 dark:border-l-zinc-800 mt-6 space-y-2">
              <h3 className="text-lg font-medium">Email disclaimer</h3>
              <Label htmlFor="email_disclaimer">Email disclaimer</Label>
              <Textarea
                id="email_disclaimer"
                value={formData.email_disclaimer}
                onChange={(e) => setFormData({ ...formData, email_disclaimer: e.target.value })}
                placeholder="e.g. This email and any attachments are confidential. If you are not the intended recipient, please delete it immediately."
                rows={4}
                disabled={saving}
              />
              <p className="text-sm text-muted-foreground">
                Appended to all outgoing emails (quotes, orders, compose, replies). HTML supported. Leave blank for no disclaimer.
              </p>
            </div>

            <div className="flex justify-end pt-4 mt-6">
              <Button onClick={handleSave} disabled={saving || !formData.company_name.trim()}>
                <Save className="h-4 w-4 mr-2" />
                {saving ? 'Saving...' : settings ? 'Update Settings' : 'Create Settings'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="mt-8 bg-muted/20 dark:bg-muted/10">
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
              Example columns: First Name, Surname, Email, Phone, First of Postcode, Last modified, First of Product Type (Stables, Cabins, Sheds), optional Lead Status (Quoted, Ordered, or Qualified — blank defaults to Qualified). Older 7-column files still import.
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
