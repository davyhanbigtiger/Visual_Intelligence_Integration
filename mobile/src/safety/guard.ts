/**
 * Guards for the model's free-text description. Not a semantic safety validator; they stop three things seen in live
 * testing (2026-10-04) from reaching the user:
 *  1. imperatives ("Go left", "请向左走") - ported from the Python engine's `_COMMAND_PATTERN`, plus Chinese;
 *  2. safety assertions ("环境安全", "无危险", "no danger") - the prompt forbids them but the model still wrote them;
 *  3. leaks of the prompt's own wording about the reader's eyesight ("视力不佳者…").
 * Offending sentences are dropped and the rest is kept; if nothing is left the description is withheld.
 */
const EN_COMMAND =
  /(?:^|[.!?,;:\n]\s*)(?:do not\b|don't\b|go\b|turn\b|walk\b|move\b|cross\b|use\b|consider\b|proceed\b|stop\b|pause\b|avoid\b|keep\b|take\b|ensure\b|run\b|jump\b|leave\b|get out\b|watch out\b|you must\b|you should\b|must\b)/i;

const ZH_COMMAND =
  /(?:^|[。！？，；：.!?,;:\n]\s*)(?:请|不要|别|必须|务必|赶紧|马上|立即|立刻|快(?:跑|走|躲|离开|停)|往[左右前后]|向[左右前后]走|[左右]转|离开|远离|躲开|小心)|(?:需要?|务必|请|要)小心|当心/;

const SAFETY_CLAIM =
  /安全|危险|风险|放心|担心|不用怕|无障碍物|没有障碍|无障碍(?!设施)|\b(?:safe|safely|safety|unsafe|danger|dangerous|hazard|hazardous|risk|risky|harmless|worry|no obstacles?|no threats?)\b/i;

const PROMPT_LEAK = /视力|视障|盲人|使用者|用户|\b(?:limited sight|visually impaired|low vision|blind person|the user|the reader)\b/i;

export function isCommandLike(text: string): boolean {
  return EN_COMMAND.test(text) || ZH_COMMAND.test(text);
}

export function isSafetyClaim(text: string): boolean {
  return SAFETY_CLAIM.test(text);
}

function splitSentences(text: string): string[] {
  return (text.match(/[^。！？.!?\n]+[。！？.!?]*/g) ?? []).map((s) => s.trim()).filter(Boolean);
}

function joinSentences(sentences: string[]): string {
  return sentences.reduce((acc, s) => (acc ? (/[。！？，；：、一-鿿]$/.test(acc) ? `${acc}${s}` : `${acc} ${s}`) : s), '');
}

/** The description with unsafe sentences removed, or null when nothing readable is left. */
export function guardDescription(text: string): string | null {
  const kept = splitSentences(text).filter((s) => !isCommandLike(s) && !isSafetyClaim(s) && !PROMPT_LEAK.test(s));
  const joined = joinSentences(kept);
  return joined || null;
}
