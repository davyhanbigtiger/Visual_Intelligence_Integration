const SENTENCE_END = /([。！？.!?\n]+)/;

/** Join two sentences; no space is added after full-width punctuation or between CJK characters. */
function join(a: string, b: string): string {
  if (!a) return b;
  return /[。！？，；：、一-鿿]$/.test(a) ? `${a}${b}` : `${a} ${b}`;
}

/**
 * Split text into pieces no longer than `maxLength` for the system speech engine (it rejects very long input),
 * preferring sentence boundaries and never cutting inside a word when avoidable.
 */
export function splitForSpeech(text: string, maxLength: number): string[] {
  const limit = Math.max(20, Math.floor(maxLength));
  const clean = text.replace(/[ \t]+/g, ' ').trim();
  if (!clean) return [];
  if (clean.length <= limit) return [clean];

  const sentences: string[] = [];
  const parts = clean.split(SENTENCE_END);
  for (let i = 0; i < parts.length; i += 2) {
    const sentence = `${parts[i] ?? ''}${parts[i + 1] ?? ''}`.trim();
    if (sentence) sentences.push(sentence);
  }

  const chunks: string[] = [];
  let current = '';
  const flush = () => {
    if (current.trim()) chunks.push(current.trim());
    current = '';
  };
  for (const sentence of sentences) {
    if (sentence.length > limit) {
      flush();
      let rest = sentence;
      while (rest.length > limit) {
        const window = rest.slice(0, limit);
        const cut = Math.max(window.lastIndexOf(' '), window.lastIndexOf('，'), window.lastIndexOf(','));
        const at = cut > limit / 2 ? cut + 1 : limit;
        chunks.push(rest.slice(0, at).trim());
        rest = rest.slice(at);
      }
      current = rest;
    } else if (join(current, sentence).length <= limit) {
      current = join(current, sentence);
    } else {
      flush();
      current = sentence;
    }
  }
  flush();
  return chunks;
}
