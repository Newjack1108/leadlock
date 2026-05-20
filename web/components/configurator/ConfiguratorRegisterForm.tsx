'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface ConfiguratorRegisterFormValues {
  name: string;
  email: string;
  phone: string;
  postcode: string;
}

interface ConfiguratorRegisterFormProps {
  onSubmit: (values: ConfiguratorRegisterFormValues) => void | Promise<void>;
  submitting?: boolean;
  submitLabel?: string;
}

export default function ConfiguratorRegisterForm({
  onSubmit,
  submitting,
  submitLabel = 'Continue to layout builder',
}: ConfiguratorRegisterFormProps) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [postcode, setPostcode] = useState('');

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void onSubmit({ name, email, phone, postcode });
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-md space-y-4">
      <div className="space-y-2">
        <Label htmlFor="cfg-name">Full name</Label>
        <Input
          id="cfg-name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your name"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="cfg-email">Email</Label>
        <Input
          id="cfg-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="cfg-phone">Phone</Label>
        <Input
          id="cfg-phone"
          type="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="07…"
        />
      </div>
      <p className="text-xs text-muted-foreground">Email or phone is required so we can contact you about your layout.</p>
      <div className="space-y-2">
        <Label htmlFor="cfg-postcode">Delivery postcode</Label>
        <Input
          id="cfg-postcode"
          value={postcode}
          onChange={(e) => setPostcode(e.target.value)}
          placeholder="e.g. CW1 2AB"
        />
        <p className="text-xs text-muted-foreground">Used to estimate delivery and installation if you add those options.</p>
      </div>
      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting ? 'Please wait…' : submitLabel}
      </Button>
    </form>
  );
}
