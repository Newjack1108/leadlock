/** Short confetti burst for quote acceptance — skips when user prefers reduced motion. */
export async function celebrateQuoteAccept(): Promise<void> {
  if (typeof window === 'undefined') return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const confetti = (await import('canvas-confetti')).default;
  await confetti({
    particleCount: 90,
    spread: 62,
    startVelocity: 38,
    gravity: 0.95,
    ticks: 175,
    origin: { x: 0.5, y: 0.35 },
    colors: ['#22c55e', '#16a34a', '#eab308', '#f97316', '#3b82f6'],
  });
}
