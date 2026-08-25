import type { Metadata } from 'next';
import Link from 'next/link';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import Logo from '@/components/Logo';

export const metadata: Metadata = {
  title: 'Privacy Policy | Cheshire Stables',
  description:
    'How Cheshire Stables (CSGB Group) / LeadLock uses Facebook and Instagram data for sales enquiries.',
};

const CONTACT_EMAIL = 'cheshirestables@csgbsales.co.uk';

export default function PrivacyPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <Card className="w-full max-w-2xl shadow-lg">
        <CardHeader className="space-y-6">
          <div className="flex justify-center">
            <Logo />
          </div>
          <div className="space-y-2">
            <CardTitle className="text-2xl text-center">Privacy Policy</CardTitle>
            <CardDescription className="text-center">
              Cheshire Stables (CSGB Group) / LeadLock
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-6 text-sm leading-relaxed text-foreground">
          <section className="space-y-2">
            <h2 className="text-base font-semibold">Overview</h2>
            <p className="text-muted-foreground">
              This page describes how LeadLock, the sales CRM used by Cheshire Stables (CSGB
              Group), handles personal data received through Facebook and Instagram (Messenger and
              Lead Ads). It applies to the LeadLock Meta app integration used to manage sales
              enquiries — not to Facebook Login for consumer accounts.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">Data we collect from Facebook / Instagram</h2>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              <li>
                <strong className="font-medium text-foreground">Lead Ads:</strong> name, email,
                phone, and other fields you submit on a lead form
              </li>
              <li>
                <strong className="font-medium text-foreground">Messenger:</strong> display name,
                Page-Scoped ID (PSID), and the content of messages you send to our Page
              </li>
            </ul>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">How we use this data</h2>
            <p className="text-muted-foreground">
              We use this information solely to respond to your sales enquiry, create or update a
              customer/lead record in LeadLock, and communicate with you about products and
              services from Cheshire Stables (CSGB Group).
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">Storage and access</h2>
            <p className="text-muted-foreground">
              Data is stored in LeadLock and accessible only to authorised staff. We do not sell
              this data. We retain it while needed to handle your enquiry and related business
              records, unless you ask us to delete it sooner.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">Requesting deletion of your data</h2>
            <p className="text-muted-foreground">
              You can request deletion of your Facebook/Instagram-related data from LeadLock by
              following the instructions on our{' '}
              <Link
                href="/data-deletion"
                className="font-medium text-primary underline underline-offset-2"
              >
                User Data Deletion
              </Link>{' '}
              page, or by emailing{' '}
              <a
                href={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent('Data deletion request')}`}
                className="font-medium text-primary underline underline-offset-2"
              >
                {CONTACT_EMAIL}
              </a>
              .
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">Contact</h2>
            <p className="text-muted-foreground">
              For privacy questions related to LeadLock and Facebook/Instagram data, contact{' '}
              <a
                href={`mailto:${CONTACT_EMAIL}`}
                className="font-medium text-primary underline underline-offset-2"
              >
                {CONTACT_EMAIL}
              </a>
              .
            </p>
          </section>
        </CardContent>
      </Card>
    </div>
  );
}
