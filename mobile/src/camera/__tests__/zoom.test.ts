import { clampZoom, zoomIn, zoomOut, zoomPercent, zoomReset, ZOOM_LEVELS } from '../zoom';

describe('zoom levels', () => {
  it('starts at 0, ends at 1 and is strictly increasing', () => {
    expect(ZOOM_LEVELS[0]).toBe(0);
    expect(ZOOM_LEVELS[ZOOM_LEVELS.length - 1]).toBe(1);
    for (let i = 1; i < ZOOM_LEVELS.length; i += 1) expect(ZOOM_LEVELS[i]).toBeGreaterThan(ZOOM_LEVELS[i - 1]);
  });

  it('moves exactly one step per command and stops at the ends', () => {
    expect(zoomIn(0)).toBe(0.08);
    expect(zoomIn(0.08)).toBe(0.16);
    expect(zoomIn(1)).toBe(1);
    expect(zoomOut(0.3)).toBe(0.16);
    expect(zoomOut(0)).toBe(0);
    expect(zoomReset()).toBe(0);
  });

  it('snaps values that are between levels to the next level in the requested direction', () => {
    expect(zoomIn(0.2)).toBe(0.3);
    expect(zoomOut(0.2)).toBe(0.16);
  });

  it('walks the whole range in and back out', () => {
    let level = 0;
    for (let i = 0; i < 20; i += 1) level = zoomIn(level);
    expect(level).toBe(1);
    for (let i = 0; i < 20; i += 1) level = zoomOut(level);
    expect(level).toBe(0);
  });

  it('clamps garbage and reports a percentage', () => {
    expect(clampZoom(NaN)).toBe(0);
    expect(clampZoom(-3)).toBe(0);
    expect(clampZoom(7)).toBe(1);
    expect(zoomPercent(0.45)).toBe(45);
    expect(zoomIn(NaN)).toBe(0.08);
  });
});
