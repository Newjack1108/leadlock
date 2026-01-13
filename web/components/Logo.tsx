import React from 'react';

export default function Logo() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex flex-col">
        <span className="text-xl font-semibold text-white tracking-tight">
          LeadLock
        </span>
        <span className="text-xs text-muted-foreground">
          Cheshire Stables Sales Control
        </span>
      </div>
    </div>
  );
}
