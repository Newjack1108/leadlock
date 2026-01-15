'use client';

import React from 'react';
import Link from 'next/link';

export default function Logo() {
  return (
    <Link href="/dashboard" className="flex items-center cursor-pointer hover:opacity-80 transition-opacity">
      {/* Logo Image - using regular img tag for reliability */}
      <div className="relative h-32 w-auto flex-shrink-0">
        <img
          src="/logo.png"
          alt="LeadLock Logo"
          className="h-32 w-auto object-contain"
          style={{ maxWidth: '600px' }}
        />
      </div>
    </Link>
  );
}
