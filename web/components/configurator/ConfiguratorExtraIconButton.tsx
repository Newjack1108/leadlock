'use client';

import { Package } from 'lucide-react';

import type { Product } from '@/lib/types';
import ConfiguratorIconToggleButton from '@/components/configurator/ConfiguratorIconToggleButton';

interface ConfiguratorExtraIconButtonProps {
  product: Product;
  selected: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export default function ConfiguratorExtraIconButton({
  product,
  selected,
  onToggle,
  disabled,
}: ConfiguratorExtraIconButtonProps) {
  const label = selected ? `Remove ${product.name}` : `Include ${product.name}`;

  return (
    <ConfiguratorIconToggleButton selected={selected} onToggle={onToggle} label={label} disabled={disabled}>
      {product.image_url ? (
        <img src={product.image_url} alt="" className="h-full w-full object-cover" />
      ) : (
        <Package className="h-5 w-5 text-muted-foreground" aria-hidden />
      )}
    </ConfiguratorIconToggleButton>
  );
}
