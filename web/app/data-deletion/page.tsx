import type { Metadata } from 'next';
import Link from 'next/link';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import Logo from '@/components/Logo';

export const metadata: Metadata = {
  title: 'User Data Deletion | Cheshire Stables',
  description:
    'How to request deletion of your Facebook or Instagram data held by Cheshire Stables (CSGB Group) / LeadLock.',
};

const CONTACT_EMAIL = 'cheshirestables@csgbsales.co.uk';

export default function DataDeletionPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <Card className="w-full max-w-2xl shadow-lg">
        <CardHeader className="space-y-6">
          <div className="flex justify-center">
            <Logo />
          </div>
          <div className="space-y-2">
            <CardTitle className="text-2xl text-center">User Data Deletion</CardTitle>
            <CardDescription className="text-center">
              Cheshire Stables (CSGB Group) / LeadLock
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-6 text-sm leading-relaxed text-foreground">
          <section className="space-y-2">
            <h2 className="text-base font-semibold">Who we are</h2>
            <p className="text-muted-foreground">
              LeadLock is the sales and customer management system used by Cheshire Stables
              (CSGB Group). When you contact us via Facebook Messenger or submit a Facebook or
              Instagram Lead Ad form, we may store limited personal data so we can respond to your
              enquiry.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">What Facebook / Instagram data we store</h2>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              <li>
                Lead Ad form details such as name, email, phone number, and answers you submitted
              </li>
              <li>Messenger display name and Page-Scoped ID (PSID)</li>
              <li>Message history from conversations with our Facebook Page</li>
            </ul>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">How to request deletion</h2>
            <p className="text-muted-foreground">
              To request that we delete your data from LeadLock, email us at{' '}
              <a
                href={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent('Data deletion request')}`}
                className="font-medium text-primary underline underline-offset-2"
              >
                {CONTACT_EMAIL}
              </a>
              .
            </p>
            <p className="text-muted-foreground">Please include:</p>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              <li>Your full name</li>
              <li>The email address and/or phone number you used with us</li>
              <li>Your Facebook name (if you contacted us via Messenger)</li>
            </ul>
          </section>

          <section className="space-y-2">
            <h2 className="text-base font-semibold">What happens next</h2>
            <p className="text-muted-foreground">
              Our staff will locate matching customer, lead, and Messenger records and delete them
              from LeadLock. We aim to complete deletion requests within 30 days of receiving a
              verifiable request.
            </p>
          </section>

          <p className="text-muted-foreground">
            For how we use this data more generally, see our{' '}
            <Link href="/privacy" className="font-medium text-primary underline underline-offset-2">
              Privacy Policy
            </Link>
            .
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
