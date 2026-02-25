'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { getPublicCompanyLogo } from '@/lib/api';

const STATIC_FALLBACKS = ['/logo.png', '/logo1.jpg', '/logo1.png'];

export default function Logo() {
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    getPublicCompanyLogo()
      .then(({ logo_url }) => {
        if (logo_url) {
          setImgSrc(logo_url);
        } else {
          setImgSrc(STATIC_FALLBACKS[0]);
        }
      })
      .catch(() => {
        setImgSrc(STATIC_FALLBACKS[0]);
      });
  }, []);

  const handleImageLoad = () => {
    setImgError(false);
  };

  const handleImageError = () => {
    const idx = STATIC_FALLBACKS.indexOf(imgSrc || '');
    if (idx >= 0 && idx < STATIC_FALLBACKS.length - 1) {
      setImgSrc(STATIC_FALLBACKS[idx + 1]);
      setImgError(false);
    } else if (idx === -1) {
      // Company logo failed; fall back to static
      setImgSrc(STATIC_FALLBACKS[0]);
      setImgError(false);
    } else {
      setImgError(true);
    }
  };

  if (imgSrc === null) {
    return (
      <Link href="/dashboard" className="flex items-center cursor-pointer hover:opacity-80 transition-opacity">
        <div className="relative h-32 w-auto flex-shrink-0 animate-pulse bg-muted rounded" style={{ minWidth: '120px' }} />
      </Link>
    );
  }

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
