import { computeResize } from '../../image/resize';
import { splitForSpeech } from '../speechChunks';

describe('splitForSpeech', () => {
  it('returns short text as one chunk and empty text as none', () => {
    expect(splitForSpeech('Hello there.', 100)).toEqual(['Hello there.']);
    expect(splitForSpeech('   ', 100)).toEqual([]);
  });

  it('packs whole sentences up to the limit', () => {
    const text = 'One two three. Four five six. Seven eight nine.';
    const chunks = splitForSpeech(text, 32);
    expect(chunks.every((c) => c.length <= 32)).toBe(true);
    expect(chunks.join(' ')).toBe(text);
  });

  it('splits Chinese on full-width punctuation', () => {
    const text = '前面有一条路。左边有几辆车。右边是一片草地。';
    const chunks = splitForSpeech(text, 20);
    expect(chunks.every((c) => c.length <= 20)).toBe(true);
    expect(chunks.join('')).toBe(text);
  });

  it('breaks a single over-long sentence without losing words', () => {
    const text = 'word '.repeat(60).trim();
    const chunks = splitForSpeech(text, 50);
    expect(chunks.every((c) => c.length <= 50)).toBe(true);
    expect(chunks.join(' ').split(' ').length).toBe(60);
  });

  it('loses no characters on a long unbroken string', () => {
    const text = 'a'.repeat(205);
    const chunks = splitForSpeech(text, 50);
    expect(chunks.every((c) => c.length <= 50)).toBe(true);
    expect(chunks.join('')).toBe(text);
  });
});

describe('computeResize', () => {
  it('shrinks the longest side only', () => {
    expect(computeResize(1920, 1080, 640)).toEqual({ width: 640 });
    expect(computeResize(1080, 1920, 640)).toEqual({ height: 640 });
    expect(computeResize(1000, 1000, 640)).toEqual({ width: 640 });
  });

  it('never upscales and ignores nonsense', () => {
    expect(computeResize(640, 480, 640)).toBeNull();
    expect(computeResize(320, 180, 640)).toBeNull();
    expect(computeResize(0, 480, 640)).toBeNull();
    expect(computeResize(NaN, 480, 640)).toBeNull();
    expect(computeResize(1920, 1080, 0)).toBeNull();
  });
});
