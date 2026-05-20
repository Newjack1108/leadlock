'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { getPublicCompanyLogo } from '@/lib/api';

const STATIC_FALLBACKS = ['/logo.png', '/logo1.jpg', '/logo1.png'];

const logoWrapperClass = 'flex items-center py-2';

type LogoSize = 'default' | 'sm' | 'header' | 'public';

const sizeConfig: Record<
  LogoSize,
  { wrapper: string; img: string; skeletonMinW: string; maxWidth: string }
> = {
  default: {
    wrapper: 'relative h-20 w-auto flex-shrink-0',
    img: 'h-20 w-auto object-contain',
    skeletonMinW: '80px',
    maxWidth: '380px',
  },
  sm: {
    wrapper: 'relative h-5 w-auto flex-shrink-0',
    img: 'h-5 w-auto object-contain',
    skeletonMinW: '28px',
    maxWidth: '96px',
  },
  header: {
    wrapper: 'relative h-12 w-auto flex-shrink-0 lg:h-20',
    img: 'h-12 w-auto object-contain lg:h-20',
    skeletonMinW: '56px',
    maxWidth: '280px',
  },
  public: {
    wrapper: 'relative h-10 w-auto shrink-0 sm:h-11',
    img: 'h-10 w-auto max-h-10 object-contain sm:h-11 sm:max-h-11',
    skeletonMinW: '48px',
    maxWidth: '140px',
  },
};

export default function Logo({
  disableLink = false,
  size = 'default',
  linkHref = '/dashboard',
}: {
  disableLink?: boolean;
  size?: LogoSize;
  /** Home link when the logo is clickable (e.g. `/dealer` for trade dealers). */
  linkHref?: string;
}) {
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

  const cfg = sizeConfig[size];
  const content = imgSrc === null ? (
    <div
      className={`${cfg.wrapper} animate-pulse bg-muted rounded`}
      style={{ minWidth: cfg.skeletonMinW }}
    />
  ) : (
    <div className={cfg.wrapper}>
      <img
        src={imgSrc}
        alt="LeadLock Logo"
        className={cfg.img}
        style={{ maxWidth: cfg.maxWidth }}
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

  const outerClass =
    size === 'sm'
      ? 'flex items-center'
      : size === 'header'
        ? 'flex items-center py-0 lg:py-2'
        : size === 'public'
          ? 'flex items-center'
          : logoWrapperClass;

  if (disableLink) {
    return <div className={outerClass}>{content}</div>;
  }

  return (
    <Link href={linkHref} className={`${outerClass} cursor-pointer hover:opacity-80 transition-opacity`}>
      {content}
    </Link>
  );
}
