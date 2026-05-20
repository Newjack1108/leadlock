'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import ConfiguratorLogo from '@/components/configurator/ConfiguratorLogo';
import ConfiguratorRegisterForm, {
  type ConfiguratorRegisterFormValues,
} from '@/components/configurator/ConfiguratorRegisterForm';
import {
  getApiErrorDetail,
  publicConfiguratorRegister,
  publicConfiguratorStart,
} from '@/lib/api';
import { toast } from 'sonner';

export default function PublicConfigureLandingPage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (values: ConfiguratorRegisterFormValues) => {
    if (!values.email.trim() && !values.phone.trim()) {
      toast.error('Please enter an email or phone number.');
      return;
    }
    try {
      setSubmitting(true);
      const started = await publicConfiguratorStart('configure');
      await publicConfiguratorRegister(started.access_token, {
        name: values.name.trim(),
        email: values.email.trim() || undefined,
        phone: values.phone.trim() || undefined,
        postcode: values.postcode.trim() || undefined,
      });
      router.push(`/configure/${started.access_token}`);
    } catch (error) {
      toast.error(getApiErrorDetail(error) || 'Could not start your layout session');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="border-b bg-background px-4 py-4">
        <div className="container mx-auto flex items-center gap-3">
          <ConfiguratorLogo className="h-9" />
          <span className="text-sm font-medium">Design your building layout</span>
        </div>
      </header>
      <main className="container mx-auto px-4 py-10">
        <Card className="mx-auto max-w-lg">
          <CardHeader>
            <CardTitle>Start your layout</CardTitle>
            <p className="text-sm text-muted-foreground font-normal">
              Tell us how to reach you, then build a draft layout our team will turn into a formal quote.
            </p>
          </CardHeader>
          <CardContent>
            <ConfiguratorRegisterForm onSubmit={handleSubmit} submitting={submitting} />
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
