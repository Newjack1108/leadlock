'use client';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ConfiguratorIconToggleButtonProps {
  selected: boolean;
  onToggle: () => void;
  label: string;
  disabled?: boolean;
  children: React.ReactNode;
}

export default function ConfiguratorIconToggleButton({
  selected,
  onToggle,
  label,
  disabled,
  children,
}: ConfiguratorIconToggleButtonProps) {
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
      <span className="flex h-full w-full items-center justify-center bg-muted">{children}</span>
    </Button>
  );
}
