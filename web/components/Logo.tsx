'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { getPublicCompanyLogo } from '@/lib/api';

const STATIC_FALLBACKS = ['/logo.png', '/logo1.jpg', '/logo1.png'];

const logoWrapperClass = 'flex items-center py-2';

export default function Logo({ disableLink = false }: { disableLink?: boolean }) {
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

  const content = imgSrc === null ? (
    <div className="relative h-20 w-auto flex-shrink-0 animate-pulse bg-muted rounded" style={{ minWidth: '80px' }} />
  ) : (
    <div className="relative h-20 w-auto flex-shrink-0">
      <img
        src={imgSrc}
        alt="LeadLock Logo"
        className="h-20 w-auto object-contain"
        style={{ maxWidth: '380px' }}
        onLoad={handleImageLoad}
        onError={handleImageError}
      />
      {imgError && (
        <div className="text-xs text-red-500">
          Failed to load: {imgSrc}
        </div>
      )}
    </div>
  );

  if (disableLink) {
    return <div className={logoWrapperClass}>{content}</div>;
  }

  return (
    <Link href="/dashboard" className={`${logoWrapperClass} cursor-pointer hover:opacity-80 transition-opacity`}>
      {content}
    </Link>
  );
}
