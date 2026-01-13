import React from 'react';
import Image from 'next/image';

export default function Logo() {
  return (
    <div className="flex items-center">
      {/* Logo Image - larger size since it includes text */}
      <div className="relative h-16 w-auto flex-shrink-0">
        <Image
          src="/logo.png"
          alt="LeadLock Logo"
          width={200}
          height={64}
          className="object-contain h-full w-auto"
          priority
        />
      </div>
    </div>
  );
}
