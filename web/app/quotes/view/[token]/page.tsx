import PublicCustomerDocumentView from '@/components/PublicCustomerDocumentView';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Cheshire Stables',
  applicationName: 'Cheshire Stables',
  openGraph: {
    title: 'Cheshire Stables',
  },
  twitter: {
    title: 'Cheshire Stables',
  },
};

export default function PublicQuoteViewPage() {
  return <PublicCustomerDocumentView />;
}
