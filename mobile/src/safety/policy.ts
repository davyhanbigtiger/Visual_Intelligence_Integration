import type { Hazard, Language, SceneResult } from '../core/types';
import { guardDescription } from './guard';
import { PHRASES, type ActionableHazard } from './phrases';

export interface SpeechPlan {
  /** Fixed hazard alert (spoken first), or null. */
  alert: string | null;
  /** The model's factual description after the command guard, or null if it was withheld. */
  description: string | null;
  /** True when the model's description was withheld by the guard. */
  descriptionWithheld: boolean;
  /** Fixed line for unclear images / unsure hazards, or null. */
  uncertainty: string | null;
  /** Fixed friendly scene line, only when there is no alert or uncertainty. */
  sceneLine: string | null;
  /** Shown on screen (not spoken) when no hazard was seen; deliberately never says "safe". */
  noHazardNote: string | null;
  /** Spoken only once per session. */
  disclaimer: string | null;
  /** Text to read out, in order. */
  spoken: string[];
}

function isActionable(hazard: Hazard): hazard is ActionableHazard {
  return hazard !== 'none' && hazard !== 'unclear';
}

export function planSpeech(
  result: SceneResult,
  language: Language,
  options: { firstInSession: boolean },
): SpeechPlan {
  const phrases = PHRASES[language];
  const description = guardDescription(result.answer);
  const descriptionWithheld = description === null;
  const confident = result.hazardConfidence === 'medium' || result.hazardConfidence === 'high';

  const alert = isActionable(result.hazard) && confident ? phrases.hazard[result.hazard] : null;

  let uncertainty: string | null = null;
  if (result.hazard === 'unclear' || result.scene === 'unclear') uncertainty = phrases.unclear;
  else if (isActionable(result.hazard) && !confident) uncertainty = phrases.uncertainHazard;

  const sceneLine = !alert && !uncertainty ? (phrases.scene[result.scene] ?? null) : null;
  const noHazardNote = result.hazard === 'none' && confident ? phrases.noHazardNote : null;
  const disclaimer = options.firstInSession ? phrases.disclaimer : null;

  const spoken: string[] = [];
  if (alert) spoken.push(alert);
  spoken.push(descriptionWithheld ? phrases.withheld : (description as string));
  if (uncertainty) spoken.push(uncertainty);
  if (sceneLine) spoken.push(sceneLine);
  if (disclaimer) spoken.push(disclaimer);

  return { alert, description, descriptionWithheld, uncertainty, sceneLine, noHazardNote, disclaimer, spoken };
}
