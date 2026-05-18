import { cn } from '@/lib/utils';

interface ConfiguratorLogoProps {
  className?: string;
}

export default function ConfiguratorLogo({ className }: ConfiguratorLogoProps) {
  return (
    <img
      src="/config.png"
      alt="Configurator"
      className={cn('h-14 w-auto max-w-full object-contain', className)}
    />
  );
}
