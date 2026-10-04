/**
 * expo-camera's `zoom` prop is a 0..1 fraction of the device's maximum zoom, not a magnification factor, so the
 * UI shows a percentage. Discrete levels keep voice steps predictable ("zoom in" always moves one step).
 */
export const ZOOM_LEVELS = [0, 0.08, 0.16, 0.3, 0.45, 0.65, 0.85, 1] as const;
const EPSILON = 1e-6;

export function clampZoom(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

export function zoomIn(level: number): number {
  const current = clampZoom(level);
  return ZOOM_LEVELS.find((step) => step > current + EPSILON) ?? ZOOM_LEVELS[ZOOM_LEVELS.length - 1];
}

export function zoomOut(level: number): number {
  const current = clampZoom(level);
  for (let i = ZOOM_LEVELS.length - 1; i >= 0; i -= 1) {
    if (ZOOM_LEVELS[i] < current - EPSILON) return ZOOM_LEVELS[i];
  }
  return ZOOM_LEVELS[0];
}

export function zoomReset(): number {
  return 0;
}

export function zoomPercent(level: number): number {
  return Math.round(clampZoom(level) * 100);
}
