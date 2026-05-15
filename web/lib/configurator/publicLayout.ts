import {
  ProductCategory,
  type ConfiguratorBoxPlacement,
  type ConfiguratorConnectionProfile,
  type ConfiguratorFrontFace,
  type Product,
  type PublicLayoutBox,
  type PublicQuoteLayout,
} from '@/lib/types';

export function publicLayoutToCanvasInputs(layout: PublicQuoteLayout): {
  boxes: ConfiguratorBoxPlacement[];
  productMap: Record<number, Product>;
} {
  const productMap: Record<number, Product> = {};
  const boxes: ConfiguratorBoxPlacement[] = layout.boxes.map((box, index) => {
    const productId = index + 1;
    productMap[productId] = publicLayoutBoxToProduct(box, productId);
    return {
      id: box.id,
      product_id: productId,
      x: Number(box.x),
      y: Number(box.y),
      rotation: box.rotation,
    };
  });
  return { boxes, productMap };
}

function publicLayoutBoxToProduct(box: PublicLayoutBox, productId: number): Product {
  const now = new Date(0).toISOString();
  return {
    id: productId,
    name: box.label,
    category: ProductCategory.CONFIGURATOR,
    is_extra: false,
    allow_trade_dealer_sale: false,
    base_price: 0,
    unit: 'unit',
    is_active: true,
    allow_in_configurator: false,
    is_production_synced: false,
    created_at: now,
    updated_at: now,
    configurator_width: Number(box.width),
    configurator_length: Number(box.length),
    configurator_is_corner_box: box.is_corner_box,
    configurator_front_face: box.front_face ?? null,
    configurator_connection_profile: box.connection_profile ?? null,
  };
}
