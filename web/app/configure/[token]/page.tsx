'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import PublicConfigureHeader from '@/components/configurator/PublicConfigureHeader';
import ConfiguratorRegisterForm, {
  type ConfiguratorRegisterFormValues,
} from '@/components/configurator/ConfiguratorRegisterForm';
import PublicConfiguratorShell from '@/components/configurator/PublicConfiguratorShell';
import {
  getApiErrorDetail,
  getPublicConfiguratorContext,
  publicConfiguratorRegister,
} from '@/lib/api';
import type { PublicConfiguratorContext } from '@/lib/types';
import { toast } from 'sonner';

export default function PublicConfigureTokenPage() {
  const params = useParams();
  const token = typeof params.token === 'string' ? params.token : '';
  const [context, setContext] = useState<PublicConfiguratorContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [registering, setRegistering] = useState(false);
  const [customerPostcode, setCustomerPostcode] = useState('');

  const loadContext = useCallback(async () => {
    if (!token) return;
    try {
      setLoading(true);
      const data = await getPublicConfiguratorContext(token);
      setContext(data);
      setCustomerPostcode(data.customer_postcode?.trim() ?? '');
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'This layout link is invalid or has expired');
      setContext(null);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadContext();
  }, [loadContext]);

  const handleRegister = async (values: ConfiguratorRegisterFormValues) => {
    if (!values.email.trim() && !values.phone.trim()) {
      toast.error('Please enter an email or phone number.');
      return;
    }
    try {
      setRegistering(true);
      const data = await publicConfiguratorRegister(token, {
        name: values.name.trim(),
        email: values.email.trim() || undefined,
        phone: values.phone.trim() || undefined,
        postcode: values.postcode.trim() || undefined,
      });
      setContext(data);
      setCustomerPostcode((values.postcode.trim() || data.customer_postcode?.trim()) ?? '');
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Registration failed');
    } finally {
      setRegistering(false);
    }
  };

  if (!token) {
    return (
      <div className="container mx-auto py-16 text-center text-muted-foreground">Invalid link.</div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (!context) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <Card className="max-w-md">
          <CardContent className="py-8 text-center text-muted-foreground">
            This link is not available. Please contact us for a new layout link.
          </CardContent>
        </Card>
      </div>
    );
  }

  if (context.status === 'SUBMITTED') {
    return (
      <div className="min-h-screen bg-muted/30">
        <PublicConfigureHeader />
        <main className="container mx-auto px-4 py-16">
          <Card className="mx-auto max-w-lg text-center">
            <CardHeader>
              <CardTitle>Thank you</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-muted-foreground">
              <p>Your layout has been submitted. Our team will review it and contact you with a formal quote.</p>
              {context.submitted_at && (
                <p className="text-xs">
                  Submitted {new Date(context.submitted_at).toLocaleString('en-GB')}
                </p>
              )}
            </CardContent>
          </Card>
        </main>
      </div>
    );
  }

  if (context.status === 'PENDING_DETAILS') {
    return (
      <div className="min-h-screen bg-muted/30">
        <PublicConfigureHeader subtitle="Design your layout" />
        <main className="container mx-auto px-4 py-10">
          <Card className="mx-auto max-w-lg">
            <CardHeader>
              <CardTitle>Your details</CardTitle>
              <p className="text-sm text-muted-foreground font-normal">
                We need your contact details before you can build your layout.
              </p>
            </CardHeader>
            <CardContent>
              <ConfiguratorRegisterForm onSubmit={handleRegister} submitting={registering} />
            </CardContent>
          </Card>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-muted/30">
      <PublicConfigureHeader
        subtitle={context.customer_name ? `Hi ${context.customer_name}` : 'Design your layout'}
      />
      <main className="container mx-auto px-4 py-4 sm:py-6">
        <PublicConfiguratorShell
          token={token}
          initialContext={context}
          customerPostcode={customerPostcode}
          onSubmitted={() => void loadContext()}
        />
      </main>
    </div>
  );
}
