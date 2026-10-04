import {
  CONFIDENCES,
  HAZARDS,
  ProviderError,
  SCENES,
  type Confidence,
  type Hazard,
  type Language,
  type Scene,
  type SceneResult,
} from './types';

/** JSON schema sent to both providers (llama.cpp converts it to a grammar, so the enums are enforced). */
export const SCENE_SCHEMA = {
  type: 'object',
  properties: {
    answer: { type: 'string' },
    scene: { type: 'string', enum: [...SCENES] },
    hazard: { type: 'string', enum: [...HAZARDS] },
    hazard_confidence: { type: 'string', enum: [...CONFIDENCES] },
  },
  required: ['answer', 'scene', 'hazard', 'hazard_confidence'],
  additionalProperties: false,
} as const;

const OUTPUT_LANGUAGE: Record<Language, string> = { zh: 'Simplified Chinese', en: 'English' };

/**
 * The prompt asks only for observation and classification. It deliberately forbids advice and safety
 * judgments: what the user hears about hazards comes from fixed, reviewed phrases (see safety/phrases.ts).
 */
export function buildPrompt(language: Language): string {
  return [
    'You are looking at one camera frame for a person who may have limited sight.',
    `Return JSON with exactly these fields. "answer": one or two short factual sentences in ${OUTPUT_LANGUAGE[language]}, ` +
      'at most 35 words, describing only what is clearly visible: the setting, any people, and prominent objects. ' +
      'Do not guess hidden things, identities or intentions. Do not give advice, commands or safety judgments.',
    '"scene": one of road, beach, indoor, nature, crowd, other, unclear.',
    '"hazard": the visible hazard category if one is clearly visible: vehicle (a car, motorcycle, bus or bicycle that ' +
      'appears close or moving), water_edge, height_drop (steps, stairs or a drop), crowd, animal, fire_smoke, ' +
      'obstacle (something blocking the way); none if nothing like that is visible; unclear if the image is too dark, ' +
      'blurry or close-up to tell.',
    '"hazard_confidence": low, medium or high.',
  ].join('\n');
}

function isMember<T extends string>(values: readonly T[], value: unknown): value is T {
  return typeof value === 'string' && (values as readonly string[]).includes(value);
}

/** Models sometimes end a sentence with a stray ")" (seen in testing); drop it when unbalanced. */
function tidyAnswer(text: string): string {
  let out = text.replace(/\s+/g, ' ').trim();
  const opens = (out.match(/[(（]/g) ?? []).length;
  const closes = (out.match(/[)）]/g) ?? []).length;
  while (closes > opens && /[)）]$/.test(out)) {
    out = out.slice(0, -1).trimEnd();
    if ((out.match(/[)）]/g) ?? []).length <= opens) break;
  }
  return out;
}

/** Parse and validate the model output; anything malformed is an `invalid_output` error, never a guess. */
export function parseSceneResult(text: string): SceneResult {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new ProviderError('invalid_output', 'The model did not return valid JSON.');
  }
  if (typeof data !== 'object' || data === null) {
    throw new ProviderError('invalid_output', 'The model output is not a JSON object.');
  }
  const record = data as Record<string, unknown>;
  const answer = typeof record.answer === 'string' ? tidyAnswer(record.answer) : '';
  if (!answer) throw new ProviderError('invalid_output', 'The model output has no answer.');
  const scene: Scene | undefined = isMember(SCENES, record.scene) ? record.scene : undefined;
  const hazard: Hazard | undefined = isMember(HAZARDS, record.hazard) ? record.hazard : undefined;
  if (!scene || !hazard) {
    throw new ProviderError('invalid_output', 'The model output has an unknown scene or hazard value.');
  }
  const hazardConfidence: Confidence = isMember(CONFIDENCES, record.hazard_confidence)
    ? record.hazard_confidence
    : 'low';
  return { answer: answer.slice(0, 600), scene, hazard, hazardConfidence };
}
