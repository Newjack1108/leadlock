import type { Metadata } from 'next';

/** Title / link-preview branding for customer-facing public pages (quotes, orders, configurator, etc.). */
export const EXTERNAL_PAGE_BRAND = 'Cheshire Stables (CSGB Group)';

export const externalPageMetadata: Metadata = {
  title: EXTERNAL_PAGE_BRAND,
  applicationName: EXTERNAL_PAGE_BRAND,
  openGraph: {
    title: EXTERNAL_PAGE_BRAND,
  },
  twitter: {
    title: EXTERNAL_PAGE_BRAND,
  },
};
