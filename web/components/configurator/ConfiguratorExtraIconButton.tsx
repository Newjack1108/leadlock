'use client';

import { Package } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { Product } from '@/lib/types';
import { cn } from '@/lib/utils';

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
    <Button
      type="button"
      variant="outline"
      size="icon"
      disabled={disabled}
      aria-pressed={selected}
      aria-label={label}
      title={label}
      onClick={onToggle}
      className={cn(
        'h-12 w-12 shrink-0 overflow-hidden p-0',
        selected && 'ring-2 ring-primary ring-offset-2 ring-offset-background'
      )}
    >
      {product.image_url ? (
        <img src={product.image_url} alt="" className="h-full w-full object-cover" />
      ) : (
        <span className="flex h-full w-full items-center justify-center bg-muted">
          <Package className="h-5 w-5 text-muted-foreground" aria-hidden />
        </span>
      )}
    </Button>
  );
}
