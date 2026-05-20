import { externalPageMetadata } from '@/lib/externalPageMetadata';

export const metadata = externalPageMetadata;

export default function ConfigureLayout({ children }: { children: React.ReactNode }) {
  return children;
}
