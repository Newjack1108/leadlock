import PublicCustomerDocumentView from '@/components/PublicCustomerDocumentView';
import { externalPageMetadata } from '@/lib/externalPageMetadata';

export const metadata = externalPageMetadata;

export default function PublicOrderViewPage() {
  return <PublicCustomerDocumentView />;
}
