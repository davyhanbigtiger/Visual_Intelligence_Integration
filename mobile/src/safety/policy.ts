import type { Hazard, Language, SceneResult } from '../core/types';
import { guardDescription } from './guard';
import { PHRASES, type ActionableHazard } from './phrases';

export interface SpeechPlan {
  /** Fixed hazard alert (spoken first), or null. */
  alert: string | null;
  /** The model's factual description after the guards, or null if nothing readable was left. */
  description: string | null;
  /** True when the whole description was withheld by the guards. */
  descriptionWithheld: boolean;
  /** Fixed line for images the model could not judge, or null. */
  uncertainty: string | null;
  /** Spoken only once per session. */
  disclaimer: string | null;
  /** Text to read out, in order. */
  spoken: string[];
}

function isActionable(hazard: Hazard): hazard is ActionableHazard {
  return hazard !== 'none' && hazard !== 'unclear';
}

/**
 * Never reassures: there is deliberately no "no danger seen" line, because hazard detection is unproven and an absent
 * alert must not be heard as "all clear".
 */
export function planSpeech(result: SceneResult, language: Language, options: { firstInSession: boolean }): SpeechPlan {
  const phrases = PHRASES[language];
  const description = guardDescription(result.answer);
  const descriptionWithheld = description === null;
  const alert = isActionable(result.hazard) ? phrases.hazard[result.hazard] : null;
  const uncertainty = result.hazard === 'unclear' ? phrases.unclear : null;
  const disclaimer = options.firstInSession ? phrases.disclaimer : null;

  const spoken: string[] = [];
  if (alert) spoken.push(alert);
  spoken.push(descriptionWithheld ? phrases.withheld : (description as string));
  if (uncertainty) spoken.push(uncertainty);
  if (disclaimer) spoken.push(disclaimer);

  return { alert, description, descriptionWithheld, uncertainty, disclaimer, spoken };
}
