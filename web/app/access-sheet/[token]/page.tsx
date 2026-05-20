import { externalPageMetadata } from '@/lib/externalPageMetadata';
import AccessSheetClient from './AccessSheetClient';

export const metadata = externalPageMetadata;

export default function AccessSheetPage() {
  return <AccessSheetClient />;
}
