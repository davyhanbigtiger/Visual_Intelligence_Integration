/**
 * Conservative guard for obvious commands (ported from the Python engine's `_COMMAND_PATTERN`, plus Chinese).
 * It is NOT a semantic safety validator: it only stops free-form model text that starts a sentence with an
 * imperative from reaching the user as if it were an instruction.
 */
const EN_COMMAND =
  /(?:^|[.!?,;:\n]\s*)(?:do not\b|don't\b|go\b|turn\b|walk\b|move\b|cross\b|use\b|consider\b|proceed\b|stop\b|pause\b|avoid\b|keep\b|take\b|ensure\b|run\b|jump\b|leave\b|get out\b|watch out\b|you must\b|you should\b|must\b)/i;

const ZH_COMMAND =
  /(?:^|[。！？，；：.!?,;:\n]\s*)(?:请|不要|别|必须|务必|赶紧|马上|立即|立刻|快(?:跑|走|躲|离开|停)|往[左右前后]|向[左右前后]走|[左右]转|离开|远离|躲开|小心)/;

export function isCommandLike(text: string): boolean {
  return EN_COMMAND.test(text) || ZH_COMMAND.test(text);
}

/** Returns the description when it is safe to read out, or null when it must be withheld. */
export function guardDescription(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return isCommandLike(trimmed) ? null : trimmed;
}
