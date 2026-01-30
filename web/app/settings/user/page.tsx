'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/Header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Settings, Save, Mail, FileText } from 'lucide-react';
import { getUserEmailSettings, updateUserEmailSettings } from '@/lib/api';
import { UserEmailSettings } from '@/lib/types';
import { toast } from 'sonner';

export default function UserSettingsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState<UserEmailSettings | null>(null);
  const [emailFormData, setEmailFormData] = useState({
    smtp_host: '',
    smtp_port: '',
    smtp_user: '',
    smtp_password: '',
    smtp_use_tls: true,
    smtp_from_email: '',
    smtp_from_name: '',
    imap_host: '',
    imap_port: '',
    imap_user: '',
    imap_password: '',
    imap_use_ssl: true,
    email_test_mode: false,
  });
  const [signature, setSignature] = useState('');

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const response = await getUserEmailSettings();
      setSettings(response);
      setEmailFormData({
        smtp_host: response.smtp_host || '',
        smtp_port: response.smtp_port?.toString() || '',
        smtp_user: response.smtp_user || '',
        smtp_password: '', // Don't pre-fill password
        smtp_use_tls: response.smtp_use_tls ?? true,
        smtp_from_email: response.smtp_from_email || '',
        smtp_from_name: response.smtp_from_name || '',
        imap_host: response.imap_host || '',
        imap_port: response.imap_port?.toString() || '',
        imap_user: response.imap_user || '',
        imap_password: '', // Don't pre-fill password
        imap_use_ssl: response.imap_use_ssl ?? true,
        email_test_mode: response.email_test_mode ?? false,
      });
      setSignature(response.email_signature || '');
    } catch (error: any) {
      if (error.response?.status === 401) {
        router.push('/login');
      } else {
        toast.error('Failed to load email settings');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSaveEmailSettings = async () => {
    try {
      setSaving(true);
      const updateData: any = {
        smtp_host: emailFormData.smtp_host || undefined,
        smtp_port: emailFormData.smtp_port ? parseInt(emailFormData.smtp_port) : undefined,
        smtp_user: emailFormData.smtp_user || undefined,
        smtp_use_tls: emailFormData.smtp_use_tls,
        smtp_from_email: emailFormData.smtp_from_email || undefined,
        smtp_from_name: emailFormData.smtp_from_name || undefined,
        imap_host: emailFormData.imap_host || undefined,
        imap_port: emailFormData.imap_port ? parseInt(emailFormData.imap_port) : undefined,
        imap_user: emailFormData.imap_user || undefined,
        imap_use_ssl: emailFormData.imap_use_ssl,
        email_test_mode: emailFormData.email_test_mode,
      };

      // Only include password if it was changed (not empty)
      if (emailFormData.smtp_password) {
        updateData.smtp_password = emailFormData.smtp_password;
      }
      if (emailFormData.imap_password) {
        updateData.imap_password = emailFormData.imap_password;
      }

      await updateUserEmailSettings(updateData);
      toast.success('Email settings updated successfully');
      fetchSettings();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save email settings');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveSignature = async () => {
    try {
      setSaving(true);
      await updateUserEmailSettings({ email_signature: signature });
      toast.success('Signature updated successfully');
      fetchSettings();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save signature');
    } finally {
      setSaving(false);
    }
  };

  const insertLogo = () => {
    // Use absolute URL to ensure logo loads correctly from any page
    const logoUrl = typeof window !== 'undefined' 
      ? `${window.location.origin}/logo1.jpg`
      : '/logo1.jpg';
    const logoHtml = `<img src="${logoUrl}" alt="Company Logo" style="max-height: 60px; margin: 10px 0;" />`;
    setSignature(signature + '\n' + logoHtml);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-6 py-8">
          <div className="text-center py-12 text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">My Settings</h1>
          <p className="text-muted-foreground mt-2">
            Configure your email settings and signature
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Email Settings Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mail className="h-5 w-5" />
                Email Settings
              </CardTitle>
              <CardDescription>
                Configure your SMTP and IMAP credentials for sending and receiving emails
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-4">
                <div>
                  <h3 className="font-semibold mb-3">SMTP Settings (Outgoing)</h3>
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label htmlFor="smtp_host">SMTP Host</Label>
                        <Input
                          id="smtp_host"
                          value={emailFormData.smtp_host}
                          onChange={(e) => setEmailFormData({ ...emailFormData, smtp_host: e.target.value })}
                          placeholder="smtp.gmail.com"
                          disabled={saving}
                        />
                      </div>
                      <div>
                        <Label htmlFor="smtp_port">SMTP Port</Label>
                        <Input
                          id="smtp_port"
                          type="number"
                          value={emailFormData.smtp_port}
                          onChange={(e) => setEmailFormData({ ...emailFormData, smtp_port: e.target.value })}
                          placeholder="587"
                          disabled={saving}
                        />
                      </div>
                    </div>
                    <div>
                      <Label htmlFor="smtp_user">SMTP Username</Label>
                      <Input
                        id="smtp_user"
                        type="email"
                        value={emailFormData.smtp_user}
                        onChange={(e) => setEmailFormData({ ...emailFormData, smtp_user: e.target.value })}
                        placeholder="your-email@gmail.com"
                        disabled={saving}
                      />
                    </div>
                    <div>
                      <Label htmlFor="smtp_password">SMTP Password</Label>
                      <Input
                        id="smtp_password"
                        type="password"
                        value={emailFormData.smtp_password}
                        onChange={(e) => setEmailFormData({ ...emailFormData, smtp_password: e.target.value })}
                        placeholder="Leave blank to keep current password"
                        disabled={saving}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label htmlFor="smtp_from_email">From Email</Label>
                        <Input
                          id="smtp_from_email"
                          type="email"
                          value={emailFormData.smtp_from_email}
                          onChange={(e) => setEmailFormData({ ...emailFormData, smtp_from_email: e.target.value })}
                          placeholder="noreply@example.com"
                          disabled={saving}
                        />
                      </div>
                      <div>
                        <Label htmlFor="smtp_from_name">From Name</Label>
                        <Input
                          id="smtp_from_name"
                          value={emailFormData.smtp_from_name}
                          onChange={(e) => setEmailFormData({ ...emailFormData, smtp_from_name: e.target.value })}
                          placeholder="Your Name"
                          disabled={saving}
                        />
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        id="smtp_use_tls"
                        checked={emailFormData.smtp_use_tls}
                        onChange={(e) => setEmailFormData({ ...emailFormData, smtp_use_tls: e.target.checked })}
                        className="rounded"
                        disabled={saving}
                      />
                      <Label htmlFor="smtp_use_tls">Use TLS</Label>
                    </div>
                  </div>
                </div>

                <div className="border-t pt-4">
                  <h3 className="font-semibold mb-3">IMAP Settings (Incoming)</h3>
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label htmlFor="imap_host">IMAP Host</Label>
                        <Input
                          id="imap_host"
                          value={emailFormData.imap_host}
                          onChange={(e) => setEmailFormData({ ...emailFormData, imap_host: e.target.value })}
                          placeholder="imap.gmail.com"
                          disabled={saving}
                        />
                      </div>
                      <div>
                        <Label htmlFor="imap_port">IMAP Port</Label>
                        <Input
                          id="imap_port"
                          type="number"
                          value={emailFormData.imap_port}
                          onChange={(e) => setEmailFormData({ ...emailFormData, imap_port: e.target.value })}
                          placeholder="993"
                          disabled={saving}
                        />
                      </div>
                    </div>
                    <div>
                      <Label htmlFor="imap_user">IMAP Username</Label>
                      <Input
                        id="imap_user"
                        type="email"
                        value={emailFormData.imap_user}
                        onChange={(e) => setEmailFormData({ ...emailFormData, imap_user: e.target.value })}
                        placeholder="your-email@gmail.com"
                        disabled={saving}
                      />
                    </div>
                    <div>
                      <Label htmlFor="imap_password">IMAP Password</Label>
                      <Input
                        id="imap_password"
                        type="password"
                        value={emailFormData.imap_password}
                        onChange={(e) => setEmailFormData({ ...emailFormData, imap_password: e.target.value })}
                        placeholder="Leave blank to keep current password"
                        disabled={saving}
                      />
                    </div>
                    <div className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        id="imap_use_ssl"
                        checked={emailFormData.imap_use_ssl}
                        onChange={(e) => setEmailFormData({ ...emailFormData, imap_use_ssl: e.target.checked })}
                        className="rounded"
                        disabled={saving}
                      />
                      <Label htmlFor="imap_use_ssl">Use SSL</Label>
                    </div>
                  </div>
                </div>

                <div className="border-t pt-4">
                  <h3 className="font-semibold mb-3">Test Mode</h3>
                  <div className="space-y-3">
                    <div className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        id="email_test_mode"
                        checked={emailFormData.email_test_mode}
                        onChange={(e) => setEmailFormData({ ...emailFormData, email_test_mode: e.target.checked })}
                        className="rounded"
                        disabled={saving}
                      />
                      <Label htmlFor="email_test_mode">Enable Email Test Mode</Label>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      When enabled, emails will be saved to the database but not actually sent via SMTP. 
                      This allows you to test email templates, signatures, and other features without sending real emails.
                    </p>
                  </div>
                </div>

                <div className="pt-4 border-t">
                  <Button onClick={handleSaveEmailSettings} disabled={saving} className="w-full">
                    <Save className="h-4 w-4 mr-2" />
                    {saving ? 'Saving...' : 'Save Email Settings'}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Email Signature Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Email Signature
              </CardTitle>
              <CardDescription>
                Create your email signature. It will be automatically appended to your emails.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="signature">Signature (HTML supported)</Label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={insertLogo}
                  >
                    Insert Logo
                  </Button>
                </div>
                <Textarea
                  id="signature"
                  value={signature}
                  onChange={(e) => setSignature(e.target.value)}
                  placeholder='Enter your HTML signature here. Use the "Insert Logo" button to add the company logo.'
                  rows={12}
                  className="font-mono text-sm"
                  disabled={saving}
                />
                <p className="text-xs text-muted-foreground">
                  Use HTML to format your signature. Click "Insert Logo" to add the company logo.
                </p>
              </div>

              {signature && (
                <div className="mt-4 pt-4 border-t">
                  <Label>Preview</Label>
                  <div
                    className="mt-2 p-4 bg-muted rounded-md border"
                    dangerouslySetInnerHTML={{ __html: signature }}
                  />
                </div>
              )}

              <div className="pt-4">
                <Button onClick={handleSaveSignature} disabled={saving} className="w-full">
                  <Save className="h-4 w-4 mr-2" />
                  {saving ? 'Saving...' : 'Save Signature'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="mt-6 p-4 bg-muted rounded-md">
          <h3 className="font-semibold mb-2">Note</h3>
          <p className="text-sm text-muted-foreground">
            If you don't configure your own email settings, the system will use the default environment variables.
            Your signature will be automatically appended to all emails you send.
          </p>
        </div>
      </main>
    </div>
  );
}
