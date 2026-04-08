import { getProducts, getProduct } from '@/lib/api';
import type { Product, QuoteItemCreate } from '@/lib/types';

/** Full product details (incl. optional_extras) for quote lines; list API omits nested extras. */
export async function prefetchProductDetailsForQuoteItems(
  formItems: QuoteItemCreate[]
): Promise<Record<number, Product>> {
  const ids = [
    ...new Set(formItems.map((it) => it.product_id).filter((id): id is number => id != null)),
  ];
  if (ids.length === 0) return {};

  let catalog: Product[] = [];
  try {
    catalog = await getProducts();
  } catch {
    catalog = [];
  }

  const out: Record<number, Product> = {};
  await Promise.all(
    ids.map(async (id) => {
      try {
        out[id] = await getProduct(id);
      } catch {
        const stub = catalog.find((p) => p.id === id);
        if (stub) out[id] = stub;
      }
    })
  );
  return out;
}
