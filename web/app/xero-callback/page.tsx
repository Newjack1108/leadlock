'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';
import { Button } from '@/components/ui/button';

function XeroCallbackContent() {
  const searchParams = useSearchParams();
  const code = searchParams.get('code');
  const error = searchParams.get('error');
  const [copied, setCopied] = useState(false);

  if (error) {
    return (
      <div className="max-w-lg mx-auto p-8 space-y-4">
        <h1 className="text-xl font-semibold text-destructive">XERO Authorization Failed</h1>
        <p className="text-muted-foreground">
          Error: {error}. {searchParams.get('error_description') || 'Check your app configuration and try again.'}
        </p>
        <Button variant="outline" onClick={() => window.close()}>
          Close
        </Button>
      </div>
    );
  }

  if (!code) {
    return (
      <div className="max-w-lg mx-auto p-8 space-y-4">
        <h1 className="text-xl font-semibold">XERO Authorization</h1>
        <p className="text-muted-foreground">
          No authorization code received. You may have landed here by accident, or the authorization was cancelled.
        </p>
        <p className="text-sm text-muted-foreground">
          To connect XERO: use the authorization URL from XERO_SETUP.md, sign in to XERO, and authorize the app.
        </p>
      </div>
    );
  }

  const copyCode = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="max-w-lg mx-auto p-8 space-y-6">
      <h1 className="text-xl font-semibold text-green-600">XERO Authorization Complete</h1>
      <p className="text-muted-foreground">
        Copy the code below and use it in Step 2.3 of XERO_SETUP.md to exchange for tokens. The code expires in a few
        minutes.
      </p>
      <div className="space-y-2">
        <div className="flex gap-2">
          <textarea
            readOnly
            value={code}
            className="flex min-h-[80px] w-full rounded-md border border-input bg-muted px-3 py-2 text-sm font-mono"
          />
        </div>
        <Button onClick={copyCode} variant="outline" size="sm">
          {copied ? 'Copied!' : 'Copy code'}
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Next: Run the token exchange (PowerShell or curl) from XERO_SETUP.md Part 2, Step 2.3, then get your tenant ID
        from the Connections API (Step 2.4).
      </p>
    </div>
  );
}

export default function XeroCallbackPage() {
  return (
    <div className="min-h-screen bg-background flex items-start justify-center pt-16">
      <Suspense fallback={<div className="text-muted-foreground">Loading...</div>}>
        <XeroCallbackContent />
      </Suspense>
    </div>
  );
}
