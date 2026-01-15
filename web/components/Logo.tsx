'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';

export default function Logo() {
  const [imgSrc, setImgSrc] = useState('/logo.png');
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    // #region agent log
    fetch('http://127.0.0.1:7243/ingest/5f6616a2-cda8-4249-a2cd-9eef4a062c60',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'Logo.tsx:useEffect',message:'Logo component mounted',data:{imgSrc,windowOrigin:typeof window!=='undefined'?window.location.origin:'SSR'},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'A'})}).catch(()=>{});
    // #endregion
  }, []);

  const handleImageLoad = () => {
    // #region agent log
    fetch('http://127.0.0.1:7243/ingest/5f6616a2-cda8-4249-a2cd-9eef4a062c60',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'Logo.tsx:handleImageLoad',message:'Image loaded successfully',data:{imgSrc,resolvedUrl:typeof window!=='undefined'?new URL(imgSrc,window.location.origin).href:'SSR'},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'B'})}).catch(()=>{});
    // #endregion
    setImgError(false);
  };

  const handleImageError = (e: React.SyntheticEvent<HTMLImageElement, Event>) => {
    const target = e.target as HTMLImageElement;
    // #region agent log
    fetch('http://127.0.0.1:7243/ingest/5f6616a2-cda8-4249-a2cd-9eef4a062c60',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'Logo.tsx:handleImageError',message:'Image failed to load',data:{imgSrc,currentSrc:target.currentSrc,resolvedUrl:typeof window!=='undefined'?new URL(imgSrc,window.location.origin).href:'SSR',windowOrigin:typeof window!=='undefined'?window.location.origin:'SSR'},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
    // #endregion
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
