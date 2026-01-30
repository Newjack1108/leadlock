'use client';

import React, { useState } from 'react';
import Link from 'next/link';

export default function Logo() {
  const [imgSrc, setImgSrc] = useState('/logo1.jpg');
  const [imgError, setImgError] = useState(false);

  const handleImageLoad = () => {
    setImgError(false);
  };

  const handleImageError = () => {
    setImgError(true);
  };

  return (
    <Link href="/dashboard" className="flex items-center cursor-pointer hover:opacity-80 transition-opacity">
      {/* Logo Image - using regular img tag for reliability */}
      <div className="relative h-32 w-auto flex-shrink-0">
        <img
          src={imgSrc}
          alt="LeadLock Logo"
          className="h-32 w-auto object-contain"
          style={{ maxWidth: '600px' }}
          onLoad={handleImageLoad}
          onError={handleImageError}
        />
        {imgError && (
          <div className="text-xs text-red-500">
            Failed to load: {imgSrc}
          </div>
        )}
      </div>
    </Link>
  );
}
