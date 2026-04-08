'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { updateDraftQuote } from '@/lib/api';
import type { QuoteDraftPayload } from '@/lib/quoteDraftPayload';
import { stableDraftPayloadKey } from '@/lib/quoteDraftPayload';

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export function useDraftAutosave(options: {
  quoteId: number | null;
  enabled: boolean;
  debounceMs?: number;
  buildPayload: () => QuoteDraftPayload;
  /** When this changes (e.g. useMemo over form fields), a debounced save is scheduled */
  formSignature: string;
}) {
  const { quoteId, enabled, debounceMs = 1500, buildPayload, formSignature } = options;
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const lastSavedKeyRef = useRef<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const buildPayloadRef = useRef(buildPayload);
  buildPayloadRef.current = buildPayload;
  const quoteIdRef = useRef(quoteId);
  quoteIdRef.current = quoteId;
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const markClean = useCallback(() => {
    const payload = buildPayloadRef.current();
    lastSavedKeyRef.current = stableDraftPayloadKey(payload);
    setSaveStatus('idle');
  }, []);

  const flushDraft = useCallback(async (): Promise<void> => {
    const id = quoteId;
    if (!id || !enabled) return;
    for (let guard = 0; guard < 10; guard++) {
      const payload = buildPayloadRef.current();
      const key = stableDraftPayloadKey(payload);
      if (key === lastSavedKeyRef.current) return;
      setSaveStatus('saving');
      try {
        await updateDraftQuote(id, payload);
        lastSavedKeyRef.current = key;
        setSaveStatus('saved');
      } catch {
        setSaveStatus('error');
        throw new Error('Failed to save draft');
      }
    }
  }, [quoteId, enabled]);

  const isDirty = useCallback(() => {
    if (!quoteIdRef.current || !enabledRef.current) return false;
    const payload = buildPayloadRef.current();
    return stableDraftPayloadKey(payload) !== lastSavedKeyRef.current;
  }, []);

  useEffect(() => {
    if (!enabled || !quoteId) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      flushDraft().catch(() => {
        /* toast optional; status already error */
      });
    }, debounceMs);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [enabled, quoteId, debounceMs, flushDraft, formSignature]);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!enabledRef.current || !quoteIdRef.current) return;
      const payload = buildPayloadRef.current();
      const key = stableDraftPayloadKey(payload);
      if (key === lastSavedKeyRef.current) return;
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, []);

  useEffect(() => {
    return () => {
      const id = quoteIdRef.current;
      if (!id || !enabledRef.current) return;
      const payload = buildPayloadRef.current();
      const key = stableDraftPayloadKey(payload);
      if (key === lastSavedKeyRef.current) return;
      void updateDraftQuote(id, payload).catch(() => {});
    };
  }, []);

  return {
    saveStatus,
    flushDraft,
    markClean,
    isDirty,
  };
}
