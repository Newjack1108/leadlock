import { Product, ProductCategory } from '@/lib/types';

/** Main catalog products selectable in sales quote product dropdowns. */
export function isQuoteCatalogProduct(product: Product): boolean {
  if (!product.is_active || product.is_extra) return false;
  if (product.category === ProductCategory.CONFIGURATOR && !product.configurator_is_starter_box) {
    return false;
  }
  return true;
}

export function filterQuoteCatalogProducts(products: Product[]): Product[] {
  return products.filter(isQuoteCatalogProduct);
}
