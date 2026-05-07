import type { Metadata } from 'next';
import AccessSheetClient from './AccessSheetClient';

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

export default function AccessSheetPage() {
  return <AccessSheetClient />;
}
