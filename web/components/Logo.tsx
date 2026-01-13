import React from 'react';
import Image from 'next/image';

export default function Logo() {
  return (
    <div className="flex items-center gap-4">
      {/* Logo Image */}
      <div className="relative h-12 w-12 flex-shrink-0">
        <Image
          src="/logo.png"
          alt="LeadLock Logo"
          fill
          className="object-contain"
          priority
        />
      </div>
      
      {/* Logo Text */}
      <div className="flex flex-col">
        <span className="text-xl font-semibold text-white tracking-tight leading-tight">
          LeadLock
        </span>
        <span className="text-xs text-muted-foreground leading-tight">
          SALES CONTROL —
        </span>
      </div>
    </div>
  );
}
