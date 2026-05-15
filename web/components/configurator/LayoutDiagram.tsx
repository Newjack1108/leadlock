'use client';

import { useMemo } from 'react';

import ConfiguratorCanvas from '@/components/configurator/ConfiguratorCanvas';
import { publicLayoutToCanvasInputs } from '@/lib/configurator/publicLayout';
import type { PublicQuoteLayout } from '@/lib/types';

interface LayoutDiagramProps {
  layout: PublicQuoteLayout;
}

export default function LayoutDiagram({ layout }: LayoutDiagramProps) {
  const { boxes, productMap } = useMemo(() => publicLayoutToCanvasInputs(layout), [layout]);

  if (boxes.length === 0) {
    return null;
  }

  return (
    <ConfiguratorCanvas
      boxes={boxes}
      productMap={productMap}
      readOnly
      viewportHeight="min(56vh, 520px)"
    />
  );
}
