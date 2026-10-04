/** Resize argument keeping the aspect ratio with the longest side at `maxSide`; null when no shrinking is needed. */
export function computeResize(width: number, height: number, maxSide: number): { width: number } | { height: number } | null {
  if (!(width > 0) || !(height > 0) || !(maxSide > 0)) return null;
  if (Math.max(width, height) <= maxSide) return null;
  return width >= height ? { width: Math.round(maxSide) } : { height: Math.round(maxSide) };
}
