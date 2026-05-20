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
        'h-12 w-12 min-h-[48px] min-w-[48px] shrink-0 overflow-hidden p-0 touch-manipulation',
        'transition-all duration-150 active:scale-[0.92]',
        selected
          ? 'border-primary bg-primary/20 ring-2 ring-primary ring-offset-2 ring-offset-background active:bg-primary/35'
          : 'active:border-primary active:bg-primary/15',
        !selected && 'hover:border-primary/60'
      )}
    >
      <span className="flex h-full w-full items-center justify-center bg-muted">{children}</span>
    </Button>
  );
}
