'use client';

import React from 'react';

export default function Logo() {
  return (
    <div className="flex items-center">
      {/* Logo Image - using regular img tag for reliability */}
      <div className="relative h-32 w-auto flex-shrink-0">
        <img
          src="/logo.png"
          alt="LeadLock Logo"
          className="h-32 w-auto object-contain"
          style={{ maxWidth: '600px' }}
        />
      </div>
    </div>
  );
}
