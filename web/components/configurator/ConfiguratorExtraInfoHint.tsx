'use client';

import { useEffect, useState } from 'react';
import { Info, Package } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import type { Product } from '@/lib/types';

function usePrefersNoHover() {
  const [prefersNoHover, setPrefersNoHover] = useState(false);

  useEffect(() => {
    const media = window.matchMedia('(hover: none)');
    const update = () => setPrefersNoHover(media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  return prefersNoHover;
}

interface ConfiguratorExtraInfoHintProps {
  product: Product;
}

export default function ConfiguratorExtraInfoHint({ product }: ConfiguratorExtraInfoHintProps) {
  const touchMode = usePrefersNoHover();
  const [open, setOpen] = useState(false);

  return (
    <HoverCard
      open={touchMode ? open : undefined}
      onOpenChange={touchMode ? setOpen : undefined}
      openDelay={200}
      closeDelay={100}
    >
      <HoverCardTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0 text-muted-foreground hover:text-foreground"
          aria-label={`More information about ${product.name}`}
          onClick={(event) => {
            if (touchMode) {
              event.preventDefault();
              event.stopPropagation();
              setOpen((current) => !current);
            }
          }}
        >
          <Info className="h-3.5 w-3.5" aria-hidden />
        </Button>
      </HoverCardTrigger>
      <HoverCardContent side="right" align="start" className="w-60 p-3">
        <div className="space-y-2">
          {product.image_url ? (
            <img
              src={product.image_url}
              alt=""
              className="aspect-[4/3] w-full rounded-md border object-cover"
            />
          ) : (
            <div className="flex aspect-[4/3] w-full items-center justify-center rounded-md border bg-muted">
              <Package className="h-8 w-8 text-muted-foreground" aria-hidden />
            </div>
          )}
          <p className="text-sm font-semibold leading-snug">{product.name}</p>
          <p className="max-h-40 overflow-y-auto text-xs text-muted-foreground whitespace-pre-wrap">
            {product.description?.trim() || 'No description.'}
          </p>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
