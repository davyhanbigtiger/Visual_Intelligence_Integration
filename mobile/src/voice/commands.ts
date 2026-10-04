import type { Language } from '../core/types';

export type VoiceCommand =
  | { type: 'analyze' }
  | { type: 'zoom_in' }
  | { type: 'zoom_out' }
  | { type: 'zoom_reset' }
  | { type: 'repeat' }
  | { type: 'stop' }
  | { type: 'language'; language: Language }
  | { type: 'unknown'; text: string };

/** Lowercase, drop punctuation and collapse whitespace; Chinese is also compared without spaces. */
export function normalizeUtterance(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[.,!?;:'"`~()[\]{}<>。，！？；：、“”‘’（）【】《》…—-]/g, (ch) => (ch === "'" || ch === '’' ? "'" : ' '))
    .replace(/\s+/g, ' ')
    .trim();
}

const RULES: readonly { command: VoiceCommand; pattern: RegExp }[] = [
  // Stop must win over everything, including negations such as "别说了".
  { command: { type: 'stop' }, pattern: /(停止|别说了|不要说了|不说了|安静|闭嘴|^停$|\bstop\b|\bquiet\b|\bshut up\b|\bbe quiet\b)/ },
  { command: { type: 'language', language: 'en' }, pattern: /(切换(到)?英[文语]|说英[文语]|用英[文语]|\bswitch to english\b|\bspeak english\b|^english$)/ },
  { command: { type: 'language', language: 'zh' }, pattern: /(切换(到)?(中文|汉语|普通话)|说(中文|汉语|普通话)|用(中文|汉语)|\bswitch to chinese\b|\bspeak chinese\b|^chinese$)/ },
  { command: { type: 'zoom_reset' }, pattern: /(还原|恢复(原样|默认|变焦)?|重置|复位|默认缩放|\breset( the)? zoom\b|\bzoom reset\b|\bnormal zoom\b|\bzoom (back )?to normal\b|\bno zoom\b)/ },
  { command: { type: 'zoom_out' }, pattern: /(缩小|拉远|远一点|远一些|\bzoom out\b|\bfarther\b|\bfurther away\b|\bwider\b|\bback up\b)/ },
  { command: { type: 'zoom_in' }, pattern: /(放大|拉近|近一点|近一些|靠近一点|\bzoom in\b|\bcloser\b|\bmagnify\b|\bbigger\b|\bzoom\b$)/ },
  { command: { type: 'repeat' }, pattern: /(重复|再说一遍|再说一次|再读一遍|再读一次|\brepeat\b|\bsay (that )?again\b|\bonce more\b)/ },
  {
    command: { type: 'analyze' },
    pattern:
      /(看看|看一下|描述|分析|识别|这是什么|有什么|前面有什么|周围有什么|\bwhat do you see\b|\bwhat('?s| is) (this|that|ahead|in front|around)\b|\bdescribe\b|\banaly[sz]e\b|\blook\b|\bscan\b|\btell me what\b)/,
  },
];

// A negation anywhere ("不要放大", "don't zoom") means we are not sure what was meant: do nothing.
const NEGATION = /(不要|别|不用|不必|没有|\bdon't\b|\bdo not\b|\bnot\b|\bno\b(?! zoom))/;

export function parseCommand(raw: string): VoiceCommand {
  const text = normalizeUtterance(raw);
  if (!text) return { type: 'unknown', text: raw };
  const stop = RULES[0];
  if (stop.pattern.test(text)) return stop.command;
  if (NEGATION.test(text)) return { type: 'unknown', text: raw };
  for (const rule of RULES.slice(1)) {
    if (rule.pattern.test(text)) return rule.command;
  }
  return { type: 'unknown', text: raw };
}
